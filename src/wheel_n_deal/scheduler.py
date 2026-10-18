import asyncio
import logging
import random
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable
from urllib.parse import urlsplit

from wheel_n_deal.config import WatchItem
from wheel_n_deal.fetch import SHORT_LINK_HOSTS
from wheel_n_deal.store import Status

logger = logging.getLogger(__name__)

Check = Callable[[WatchItem], Awaitable[Status]]

_SECOND_LEVEL_SUFFIXES = frozenset({"co", "com", "org", "net", "ac", "gov"})


def site_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if host in SHORT_LINK_HOSTS:
        return "amazon.com"
    labels = host.split(".")
    keep = 3 if len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL_SUFFIXES else 2
    return ".".join(labels[-keep:])


def group_by_site(items: Iterable[WatchItem]) -> dict[str, list[WatchItem]]:
    groups: dict[str, list[WatchItem]] = {}
    for item in items:
        groups.setdefault(site_of(item.url), []).append(item)
    return groups


def next_due(after: float, interval_s: float, jitter_s: float, rng: random.Random) -> float:
    return after + interval_s + rng.uniform(0, jitter_s)


def initial_schedule(
    last_checked: dict[str, float | None],
    now: float,
    interval_s: float,
    jitter_s: float,
    rng: random.Random,
) -> dict[str, float]:
    return {
        site: now if last is None else next_due(last, interval_s, jitter_s, rng)
        for site, last in last_checked.items()
    }


def due_sites(schedule: dict[str, float], now: float) -> list[str]:
    return [site for site, due in schedule.items() if due <= now]


async def _check_site(items: list[WatchItem], check: Check) -> list[Status]:
    statuses = []
    for item in items:
        try:
            statuses.append(await check(item))
        except Exception:
            logger.exception("check crashed for %s", item.name)
            statuses.append(Status.ERROR)
    return statuses


async def run_sites(groups: dict[str, list[WatchItem]], check: Check) -> list[Status]:
    per_site = await asyncio.gather(*(_check_site(items, check) for items in groups.values()))
    return [status for statuses in per_site for status in statuses]


def summary_line(statuses: list[Status]) -> str:
    counts = Counter(statuses)
    failed = counts[Status.ERROR] + counts[Status.STALE]
    return (
        f"run: checked={len(statuses)} ok={counts[Status.OK]}"
        f" blocked={counts[Status.BLOCKED]} failed={failed}"
    )
