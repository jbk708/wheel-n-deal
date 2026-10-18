import argparse
import asyncio
import logging
import random
import sqlite3
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx

from wheel_n_deal.check import check_item
from wheel_n_deal.config import Config, WatchItem, load_config
from wheel_n_deal.fetch import make_client
from wheel_n_deal.scheduler import (
    due_sites,
    group_by_site,
    initial_schedule,
    next_due,
    run_sites,
    summary_line,
)
from wheel_n_deal.store import Status, open_store, read_observations, write_item

logger = logging.getLogger(__name__)


def sync_watch_list(conn: sqlite3.Connection, config: Config) -> dict[str, int]:
    return {
        item.url: write_item(conn, item.url, item.name, item.target_price) for item in config.watch
    }


def _last_checked(conn: sqlite3.Connection, item_id: int) -> float | None:
    latest = read_observations(conn, item_id, limit=1)
    return datetime.fromisoformat(latest[0].checked_at).timestamp() if latest else None


def load_schedule(
    conn: sqlite3.Connection,
    config: Config,
    item_ids: dict[str, int],
    now: float,
    rng: random.Random,
) -> dict[str, float]:
    last_checked: dict[str, float | None] = {}
    for site, items in group_by_site(config.watch).items():
        times = [t for item in items if (t := _last_checked(conn, item_ids[item.url])) is not None]
        last_checked[site] = max(times, default=None)
    return initial_schedule(
        last_checked,
        now,
        config.politeness.min_interval_hours * 3600,
        config.politeness.jitter_minutes * 60,
        rng,
    )


async def run_forever(
    config: Config,
    conn: sqlite3.Connection,
    client: httpx.AsyncClient,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rng: random.Random | None = None,
) -> None:
    rng = rng or random.Random()
    interval_s = config.politeness.min_interval_hours * 3600
    jitter_s = config.politeness.jitter_minutes * 60
    item_ids = sync_watch_list(conn, config)
    groups = group_by_site(config.watch)
    schedule = load_schedule(conn, config, item_ids, clock(), rng)

    async def check(item: WatchItem) -> Status:
        checked_at = datetime.fromtimestamp(clock(), UTC).isoformat()
        return await check_item(client, conn, item_ids[item.url], item, checked_at)

    while True:
        due = due_sites(schedule, clock())
        if due:
            statuses = await run_sites({site: groups[site] for site in due}, check)
            logger.info(summary_line(statuses))
            finished = clock()
            schedule.update({site: next_due(finished, interval_s, jitter_s, rng) for site in due})
        await sleep(max(0.0, min(schedule.values(), default=clock() + interval_s) - clock()))


async def _main(config: Config) -> None:
    conn = open_store(config.data_dir / "state.db")
    async with make_client() as client:
        await run_forever(config, conn, client)


def run() -> None:
    parser = argparse.ArgumentParser(prog="wheel-n-deal")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # httpx logs every request URL at INFO; the heartbeat URL carries a token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config = load_config(args.config)
    logger.info("watching %d items", len(config.watch))
    asyncio.run(_main(config))
