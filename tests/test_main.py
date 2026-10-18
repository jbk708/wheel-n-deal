import json
import logging
import random
from datetime import datetime
from pathlib import Path

import respx

from wheel_n_deal.config import Config, Secrets, load_config
from wheel_n_deal.fetch import make_client
from wheel_n_deal.main import load_schedule, run_forever, sync_watch_list
from wheel_n_deal.store import (
    Observation,
    Status,
    create_observation,
    open_store,
    read_item_id,
    read_observations,
)

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
            "data_dir": str(tmp_path),
        }
    )


class _Stop(Exception):
    pass


def test_sync_watch_list_writes_every_item(tmp_path):
    config = load_config(ROOT / "config.example.yaml")
    conn = open_store(tmp_path / "state.db")
    ids = sync_watch_list(conn, config)
    assert len(ids) == len(config.watch)
    for item in config.watch:
        assert read_item_id(conn, item.url) == ids[item.url]


async def test_run_forever_checks_then_sleeps_until_next_slot(tmp_path, caplog):
    config = _config(tmp_path, [URL_A, URL_B], target_price=200)
    conn = open_store(tmp_path / "state.db")
    now = [1_800_000_000.0]
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise _Stop
        now[0] += seconds

    page = (ROOT / "tests" / "fixtures" / "jsonld_product.html").read_text()
    caplog.set_level(logging.INFO)
    with respx.mock:
        respx.get(URL_A).respond(200, text=page)
        respx.get(URL_B).respond(429)
        ntfy = respx.post("https://ntfy.example/").respond(200)
        heartbeat = respx.get(HEARTBEAT).respond(200)
        async with make_client() as client:
            try:
                await run_forever(
                    config,
                    conn,
                    client,
                    Secrets(llm_api_key=None, ntfy_token="t"),
                    clock=lambda: now[0],
                    sleep=fake_sleep,
                    rng=random.Random(1),
                )
            except _Stop:
                pass

    assert sleeps[0] == 6 * HOUR
    statuses_a = [o.status for o in read_observations(conn, read_item_id(conn, URL_A))]
    statuses_b = [o.status for o in read_observations(conn, read_item_id(conn, URL_B))]
    assert statuses_a == [Status.OK, Status.OK]
    assert statuses_b == [Status.BLOCKED, Status.BLOCKED]
    assert caplog.text.count("run: checked=2 ok=1 blocked=1 failed=0") == 2
    titles = sorted(json.loads(call.request.content)["title"] for call in ntfy.calls)
    assert titles == ["1 item(s) blocked", "Price drop: a"]
    assert heartbeat.call_count == 2


def test_restart_respects_interval_since_last_check(tmp_path):
    config = _config(tmp_path, [URL_A, URL_B])
    conn = open_store(tmp_path / "state.db")
    ids = sync_watch_list(conn, config)
    obs = Observation(ids[URL_A], "2026-10-18T10:00:00+00:00", Status.OK, 1.0, "USD", True)
    create_observation(conn, obs)
    now = datetime.fromisoformat("2026-10-18T12:00:00+00:00").timestamp()
    schedule = load_schedule(conn, config, ids, now, random.Random())
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
        async with make_client() as client:
            try:
                await run_forever(
                    config, conn, client, Secrets(llm_api_key="k", ntfy_token="t"), sleep=stop
                )
            except _Stop:
                pass
    assert llm.call_count == 1
    message = json.loads(ntfy.calls.last.request.content)["message"]
    assert message.endswith("Verdict: real deal. Lowest price seen.")
