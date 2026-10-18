import asyncio
import random

import pytest

from wheel_n_deal.config import WatchItem
from wheel_n_deal.scheduler import (
    due_sites,
    group_by_site,
    initial_schedule,
    next_due,
    run_sites,
    site_of,
    summary_line,
)
from wheel_n_deal.store import Status

HOUR = 3600.0


def _item(url: str) -> WatchItem:
    return WatchItem(url=url, name=url, target_price=10)


@pytest.mark.parametrize(
    "url, site",
    [
        ("https://www.amazon.com/dp/B0ABCDEF12", "amazon.com"),
        ("https://a.co/d/abc123", "amazon.com"),
        ("https://amzn.to/3xYz", "amazon.com"),
        ("https://www.costco.com/p/-/x/4000123456", "costco.com"),
        ("https://shop.example.co.uk/products/x", "example.co.uk"),
        ("https://store.example/products/x", "store.example"),
    ],
)
def test_site_of(url, site):
    assert site_of(url) == site


def test_group_by_site_keeps_order():
    items = [
        _item("https://a.co/d/1"),
        _item("https://shop.example/products/a"),
        _item("https://www.amazon.com/dp/B0ABCDEF12"),
    ]
    groups = group_by_site(items)
    assert list(groups) == ["amazon.com", "shop.example"]
    assert [i.url for i in groups["amazon.com"]] == [items[0].url, items[2].url]


def test_next_due_stays_within_interval_plus_jitter():
    rng = random.Random(7)
    offsets = [next_due(1000.0, 6 * HOUR, 1800.0, rng) - 1000.0 for _ in range(500)]
    assert min(offsets) >= 6 * HOUR
    assert max(offsets) <= 6 * HOUR + 1800.0
    assert len(set(offsets)) > 1


def test_next_due_without_jitter_is_exact():
    assert next_due(5.0, 10.0, 0.0, random.Random()) == 15.0


def test_initial_schedule_never_checked_is_due_now_and_checked_waits():
    now = 100 * HOUR
    schedule = initial_schedule(
        {"new.example": None, "recent.example": now - HOUR, "old.example": now - 7 * HOUR},
        now=now,
        interval_s=6 * HOUR,
        jitter_s=0.0,
        rng=random.Random(),
    )
    assert schedule == {
        "new.example": now,
        "recent.example": now + 5 * HOUR,
        "old.example": now - HOUR,
    }
    assert sorted(due_sites(schedule, now)) == ["new.example", "old.example"]


def test_due_sites_empty_when_nothing_due():
    assert due_sites({"a.example": 10.0}, 9.0) == []


async def test_run_sites_one_request_at_a_time_per_site():
    in_flight: dict[str, int] = {}
    max_per_site: dict[str, int] = {}
    max_total = 0

    async def check(item: WatchItem) -> Status:
        nonlocal max_total
        site = site_of(item.url)
        in_flight[site] = in_flight.get(site, 0) + 1
        max_per_site[site] = max(max_per_site.get(site, 0), in_flight[site])
        max_total = max(max_total, sum(in_flight.values()))
        await asyncio.sleep(0)
        in_flight[site] -= 1
        return Status.OK

    groups = group_by_site(
        [
            _item(f"https://{site}/products/{n}")
            for site in ("a.example", "b.example")
            for n in "xyz"
        ]
    )
    statuses = await run_sites(groups, check)
    assert statuses == [Status.OK] * 6
    assert max_per_site == {"a.example": 1, "b.example": 1}
    assert max_total == 2


async def test_run_sites_isolates_unexpected_failures():
    async def check(item: WatchItem) -> Status:
        if item.url.endswith("boom"):
            raise RuntimeError("bug")
        return Status.OK

    groups = group_by_site([_item("https://a.example/boom"), _item("https://a.example/fine")])
    assert await run_sites(groups, check) == [Status.ERROR, Status.OK]


def test_summary_line_counts():
    statuses = [Status.OK, Status.OK, Status.BLOCKED, Status.ERROR, Status.STALE]
    assert summary_line(statuses) == "run: checked=5 ok=2 blocked=1 failed=2"
