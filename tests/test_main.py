import json
import logging
import random
import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import httpx
import respx

from wheel_n_deal.config import Config, Secrets, WatchItem, load_config
from wheel_n_deal.fetch import FetchResult, FetchStatus, make_client, make_shop_client
from wheel_n_deal.main import load_schedule, run_forever, seed_watch_list, touch_heartbeat
from wheel_n_deal.store import (
    Observation,
    Status,
    create_item,
    create_observation,
    delete_item,
    open_store,
    read_item_id,
    read_items,
    read_observations,
    seed_item,
)

# respx answers before anything reaches this address.
PROXY = "http://proxy.invalid:8888"

ROOT = Path(__file__).parent.parent
URL_A = "https://shop.example/products/a"
URL_B = "https://shop.example/products/b"
HOUR = 3600


HEARTBEAT = "https://status.example/api/push/token"


def _config(tmp_path: Path, urls: list[str], target_price: float = 1) -> Config:
    return Config.model_validate(
        {
            "watch": [{"url": url, "name": url[-1], "target_price": target_price} for url in urls],
            "ntfy": {"url": "https://ntfy.example"},
            "heartbeat_url": HEARTBEAT,
            "llm": {"base_url": "https://llm.example/v1"},
            "politeness": {"min_interval_hours": 6, "jitter_minutes": 0},
            "fetch": {"proxy_url": PROXY},
            "data_dir": str(tmp_path),
        }
    )


class _Stop(Exception):
    pass


async def still_blocked(url: str) -> FetchResult:
    return FetchResult(url, FetchStatus.BLOCKED, 403, reason="http 403")


async def test_seed_watch_list_imports_every_item_once(tmp_path):
    config = load_config(ROOT / "config.example.yaml")
    conn = open_store(tmp_path / "state.db")
    async with make_shop_client(PROXY) as client:
        await seed_watch_list(conn, config, client)
        first = read_items(conn)
        assert sorted(first.values(), key=lambda i: i.url) == sorted(
            config.watch, key=lambda i: i.url
        )
        delete_item(conn, read_item_id(conn, config.watch[0].url), "2026-10-18T00:00:00+00:00")
        await seed_watch_list(conn, config, client)
    assert config.watch[0] not in read_items(conn).values()
    assert len(read_items(conn)) == len(config.watch) - 1


async def test_seed_canonicalizes_and_skips_unresolvable_short_links(tmp_path, caplog):
    long_url = "https://www.amazon.com/Thing/dp/B0ABCDEF12?tag=x"
    config = _config(tmp_path, [long_url, "https://a.co/d/broken"])
    conn = open_store(tmp_path / "state.db")
    async with make_shop_client(PROXY) as client:
        with respx.mock:
            respx.get("https://a.co/d/broken").mock(side_effect=httpx.ConnectError("down"))
            await seed_watch_list(conn, config, client)
    assert [i.url for i in read_items(conn).values()] == ["https://www.amazon.com/dp/B0ABCDEF12"]
    assert "https://a.co/d/broken" in caplog.text


async def test_run_forever_checks_items_from_the_database(tmp_path):
    config = _config(tmp_path, [URL_A])
    conn = open_store(tmp_path / "state.db")
    for item in config.watch:
        seed_item(conn, item)
    delete_item(conn, read_item_id(conn, URL_A), "2026-10-18T00:00:00+00:00")
    create_item(conn, WatchItem(url=URL_B, name="b", target_price=1))

    async def stop(seconds: float) -> None:
        raise _Stop

    with respx.mock:
        a = respx.get(URL_A).respond(200, text="<title>a</title>")
        b = respx.get(URL_B).respond(429)
        respx.post("https://ntfy.example/").respond(200)
        respx.get(HEARTBEAT).respond(200)
        async with make_client() as client, make_shop_client(PROXY) as shop:
            try:
                await run_forever(
                    config, conn, client, shop, Secrets(None, "t"), still_blocked, sleep=stop
                )
            except _Stop:
                pass
    assert a.call_count == 0
    assert b.call_count == 1


async def test_run_forever_checks_then_sleeps_until_next_slot(tmp_path, caplog):
    config = _config(tmp_path, [URL_A, URL_B], target_price=200)
    conn = open_store(tmp_path / "state.db")
    start = 1_800_000_000.0
    now = [start]
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        if now[0] >= start + 6 * HOUR:
            raise _Stop
        sleeps.append(seconds)
        now[0] += seconds

    page = (ROOT / "tests" / "fixtures" / "jsonld_product.html").read_text()
    caplog.set_level(logging.INFO)
    with respx.mock:
        respx.get(URL_A).respond(200, text=page)
        respx.get(URL_B).respond(429)
        ntfy = respx.post("https://ntfy.example/").respond(200)
        heartbeat = respx.get(HEARTBEAT).respond(200)
        async with make_client() as client, make_shop_client(PROXY) as shop:
            try:
                await run_forever(
                    config,
                    conn,
                    client,
                    shop,
                    Secrets(llm_api_key=None, ntfy_token="t"),
                    still_blocked,
                    clock=lambda: now[0],
                    sleep=fake_sleep,
                    rng=random.Random(1),
                )
            except _Stop:
                pass

    assert set(sleeps) == {60} and len(sleeps) == 6 * 60
    statuses_a = [o.status for o in read_observations(conn, read_item_id(conn, URL_A))]
    statuses_b = [o.status for o in read_observations(conn, read_item_id(conn, URL_B))]
    assert statuses_a == [Status.OK, Status.OK]
    assert statuses_b == [Status.BLOCKED, Status.BLOCKED]
    assert caplog.text.count("run: checked=2 ok=1 blocked=1 failed=0") == 2
    titles = sorted(json.loads(call.request.content)["title"] for call in ntfy.calls)
    assert titles == ["1 item(s) blocked", "Price drop: a"]
    assert heartbeat.call_count == 2


URL_OTHER_SITE = "https://other.example/products/c"


async def _run_with_changes(
    tmp_path: Path, changes: dict[float, Callable], until: float
) -> tuple[sqlite3.Connection, dict[str, list[float]]]:
    """Run the loop on a fake clock, applying each change once its time (hours) is reached."""
    config = _config(tmp_path, [URL_A])
    conn = open_store(tmp_path / "state.db")
    start = 1_800_000_000.0
    now = [start]
    checked: dict[str, list[float]] = {}
    pending = dict(sorted(changes.items()))

    async def fake_sleep(seconds: float) -> None:
        now[0] += seconds
        for at in [at for at in pending if start + at * HOUR <= now[0]]:
            pending.pop(at)(conn)
        if now[0] >= start + until * HOUR:
            raise _Stop

    def record(request: httpx.Request) -> httpx.Response:
        checked.setdefault(str(request.url), []).append((now[0] - start) / HOUR)
        return httpx.Response(429)

    with respx.mock:
        respx.get(url__regex=r"https://(shop|other)\.example/.*").mock(side_effect=record)
        respx.post("https://ntfy.example/").respond(200)
        respx.get(HEARTBEAT).respond(200)
        async with make_client() as client, make_shop_client(PROXY) as shop:
            try:
                await run_forever(
                    config,
                    conn,
                    client,
                    shop,
                    Secrets(None, "t"),
                    still_blocked,
                    clock=lambda: now[0],
                    sleep=fake_sleep,
                    rng=random.Random(1),
                )
            except _Stop:
                pass
    return conn, checked


def _add(url: str) -> Callable:
    return lambda conn: create_item(conn, WatchItem(url=url, name=url[-1], target_price=1))


async def test_item_on_new_site_is_checked_within_a_minute(tmp_path):
    _, checked = await _run_with_changes(tmp_path, {1: _add(URL_OTHER_SITE)}, until=2)
    assert len(checked[URL_OTHER_SITE]) == 1
    assert 1 <= checked[URL_OTHER_SITE][0] <= 1 + 1 / 60


async def test_item_on_known_site_joins_the_sites_next_slot(tmp_path):
    _, checked = await _run_with_changes(tmp_path, {1: _add(URL_B)}, until=6.5)
    assert checked[URL_A] == [0, 6]
    assert checked[URL_B] == [6]


async def test_removed_item_is_no_longer_checked(tmp_path):
    def remove_a(conn: sqlite3.Connection) -> None:
        delete_item(conn, read_item_id(conn, URL_A), "2026-10-18T00:00:00+00:00")

    _, checked = await _run_with_changes(tmp_path, {1: remove_a}, until=13)
    assert checked[URL_A] == [0]


def test_restart_respects_interval_since_last_check(tmp_path):
    config = _config(tmp_path, [URL_A, URL_B])
    conn = open_store(tmp_path / "state.db")
    for item in config.watch:
        seed_item(conn, item)
    obs = Observation(
        read_item_id(conn, URL_A), "2026-10-18T10:00:00+00:00", Status.OK, 1.0, "USD", True
    )
    create_observation(conn, obs)
    now = datetime.fromisoformat("2026-10-18T12:00:00+00:00").timestamp()
    schedule = load_schedule(conn, read_items(conn), now, 6 * HOUR, 0, random.Random())
    assert schedule == {"shop.example": now + 4 * HOUR}


async def test_price_drop_alert_carries_mimo_verdict(tmp_path):
    config = _config(tmp_path, [URL_A], target_price=200)
    conn = open_store(tmp_path / "state.db")
    verdict = {"real_deal": True, "flags": [], "reason": "Lowest price seen."}
    completion = {"choices": [{"message": {"content": json.dumps(verdict)}}]}

    async def stop(seconds: float) -> None:
        raise _Stop

    page = (ROOT / "tests" / "fixtures" / "jsonld_product.html").read_text()
    with respx.mock:
        respx.get(URL_A).respond(200, text=page)
        llm = respx.post("https://llm.example/v1/chat/completions").respond(200, json=completion)
        ntfy = respx.post("https://ntfy.example/").respond(200)
        respx.get(HEARTBEAT).respond(200)
        async with make_client() as client, make_shop_client(PROXY) as shop:
            try:
                await run_forever(
                    config,
                    conn,
                    client,
                    shop,
                    Secrets(llm_api_key="k", ntfy_token="t"),
                    still_blocked,
                    sleep=stop,
                )
            except _Stop:
                pass
    assert llm.call_count == 1
    message = json.loads(ntfy.calls.last.request.content)["message"]
    assert message.endswith("Verdict: real deal. Lowest price seen.")


async def test_heartbeat_file_is_touched_repeatedly(tmp_path):
    path = tmp_path / "heartbeat"
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        path.unlink()
        if len(sleeps) == 2:
            raise _Stop

    try:
        await touch_heartbeat(path, sleep=fake_sleep)
    except _Stop:
        pass
    assert sleeps == [30, 30]
