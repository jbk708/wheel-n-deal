import logging
import random
from datetime import datetime
from pathlib import Path

import respx

from wheel_n_deal.config import Config, load_config
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


def _config(tmp_path: Path, urls: list[str]) -> Config:
    return Config.model_validate(
        {
            "watch": [{"url": url, "name": url[-1], "target_price": 1} for url in urls],
            "ntfy": {"url": "https://ntfy.example"},
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
    config = _config(tmp_path, [URL_A, URL_B])
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
        async with make_client() as client:
            try:
                await run_forever(
                    config,
                    conn,
                    client,
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


def test_restart_respects_interval_since_last_check(tmp_path):
    config = _config(tmp_path, [URL_A, URL_B])
    conn = open_store(tmp_path / "state.db")
    ids = sync_watch_list(conn, config)
    obs = Observation(ids[URL_A], "2026-10-18T10:00:00+00:00", Status.OK, 1.0, "USD", True)
    create_observation(conn, obs)
    now = datetime.fromisoformat("2026-10-18T12:00:00+00:00").timestamp()
    schedule = load_schedule(conn, config, ids, now, random.Random())
    assert schedule == {"shop.example": now + 4 * HOUR}
