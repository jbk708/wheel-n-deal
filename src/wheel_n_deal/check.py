import json
import logging
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import replace

from wheel_n_deal.config import WatchItem
from wheel_n_deal.extract import Extraction, extract, extract_shopify_js, shopify_js_url
from wheel_n_deal.fetch import FetchResult, FetchStatus, ShopClient, fetch
from wheel_n_deal.learned import derive_selector, price_on_page, read_price
from wheel_n_deal.llm import MiMo
from wheel_n_deal.store import (
    Observation,
    Status,
    create_observation,
    delete_selector,
    read_last_priced,
    read_selector,
    write_selector,
)

logger = logging.getLogger(__name__)

Render = Callable[[str], Awaitable[FetchResult]]


async def read_shopify_extraction(client: ShopClient, html: str, url: str) -> Extraction | None:
    js_url = shopify_js_url(html, url)
    if not js_url:
        return None
    fetched = await fetch(client, js_url)
    if fetched.status is not FetchStatus.OK:
        return None
    try:
        return extract_shopify_js(json.loads(fetched.body), url)
    except (json.JSONDecodeError, AttributeError):
        return None


def _read_learned(
    conn: sqlite3.Connection, item_id: int, item: WatchItem, page: FetchResult
) -> Extraction | None:
    selector = read_selector(conn, item_id)
    if not selector:
        return None
    price = read_price(page.body, selector)
    if price:
        return Extraction(price, None, None, selector)
    logger.warning("learned selector broke: %s", item.name)
    delete_selector(conn, item_id)
    return None


Outcome = tuple[Status, Extraction | None, str | None]


def _last_known(conn: sqlite3.Connection, item_id: int, reason: str) -> Outcome:
    last = read_last_priced(conn, item_id)
    if not last:
        return Status.STALE, None, reason
    return (
        Status.STALE,
        Extraction(last.price, last.currency, last.in_stock, "last-known"),
        reason,
    )


async def _read_with_mimo(
    conn: sqlite3.Connection,
    mimo: MiMo,
    item_id: int,
    item: WatchItem,
    page: FetchResult,
    checked_at: str,
) -> Outcome:
    answer = await mimo.extract(page.url, page.body)
    if answer is None:
        logger.warning("stale: %s (MiMo unavailable, keeping last known price)", item.name)
        return _last_known(conn, item_id, "MiMo unavailable")
    if answer.blocked:
        logger.warning("blocked: %s (MiMo saw a bot wall)", item.name)
        return Status.BLOCKED, None, "bot wall (seen by MiMo)"
    if answer.price is None:
        logger.warning("no price found: %s", item.name)
        return Status.ERROR, None, "no price found"
    selector = derive_selector(page.body, answer.price, answer.evidence)
    if selector:
        write_selector(conn, item_id, selector, checked_at)
    elif not price_on_page(page.body, answer.price):
        # Never alert on a price the page does not show (hallucinated or wrong product).
        logger.warning(
            "stale: %s (MiMo price %.2f not on page, keeping last known price)",
            item.name,
            answer.price,
        )
        return _last_known(conn, item_id, "MiMo price not on page")
    logger.info("ok: %s %.2f via mimo (learned: %s)", item.name, answer.price, selector)
    return Status.OK, Extraction(answer.price, answer.currency, answer.in_stock, "mimo"), None


async def _read_page(
    client: ShopClient,
    conn: sqlite3.Connection,
    mimo: MiMo,
    item_id: int,
    item: WatchItem,
    page: FetchResult,
    checked_at: str,
) -> Outcome:
    found = (
        extract(page.body, page.url)
        or await read_shopify_extraction(client, page.body, page.url)
        or _read_learned(conn, item_id, item, page)
    )
    if found:
        logger.info("ok: %s %.2f via %s", item.name, found.price, found.source)
        return Status.OK, found, None
    return await _read_with_mimo(conn, mimo, item_id, item, page, checked_at)


async def _retry_headless(item: WatchItem, blocked: FetchResult, render: Render) -> FetchResult:
    logger.warning("plain fetch blocked: %s (%s), retrying headless", item.name, blocked.reason)
    rendered = await render(blocked.url)
    logger.info(
        "headless fetch: %s -> %s (http %s%s)",
        item.name,
        rendered.status.value,
        rendered.http_status,
        f", {rendered.reason}" if rendered.reason else "",
    )
    if rendered.status is FetchStatus.OK:
        return rendered
    return replace(rendered, reason=f"{blocked.reason}; headless: {rendered.reason}")


async def check_item(
    client: ShopClient,
    conn: sqlite3.Connection,
    mimo: MiMo,
    item_id: int,
    item: WatchItem,
    checked_at: str,
    render: Render,
) -> tuple[Observation, str | None]:
    """Return the stored observation and, when the page was fetched, its HTML."""
    fetched = await fetch(client, item.url)
    if fetched.status is FetchStatus.BLOCKED:
        fetched = await _retry_headless(item, fetched, render)
    found = None
    reason = fetched.reason
    if fetched.status is FetchStatus.BLOCKED:
        logger.warning("blocked: %s (%s)", item.name, fetched.reason)
        status = Status.BLOCKED
    elif fetched.status is FetchStatus.ERROR:
        logger.warning("fetch error: %s (%s)", item.name, fetched.reason)
        status = Status.ERROR
    else:
        status, found, reason = await _read_page(
            client, conn, mimo, item_id, item, fetched, checked_at
        )
    obs = Observation(
        item_id=item_id,
        checked_at=checked_at,
        status=status,
        price=found.price if found else None,
        currency=found.currency if found else None,
        in_stock=found.in_stock if found else None,
        http_status=fetched.http_status,
        block_reason=reason,
    )
    create_observation(conn, obs)
    return obs, fetched.body if fetched.status is FetchStatus.OK else None
