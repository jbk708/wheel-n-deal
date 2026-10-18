import json
import logging
import sqlite3

import httpx

from wheel_n_deal.config import WatchItem
from wheel_n_deal.extract import Extraction, extract, extract_shopify_js, shopify_js_url
from wheel_n_deal.fetch import FetchResult, FetchStatus, fetch
from wheel_n_deal.llm import MiMo
from wheel_n_deal.store import Observation, Status, create_observation, read_last_priced

logger = logging.getLogger(__name__)


async def read_shopify_extraction(
    client: httpx.AsyncClient, html: str, url: str
) -> Extraction | None:
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


async def _read_page(
    client: httpx.AsyncClient,
    conn: sqlite3.Connection,
    mimo: MiMo,
    item_id: int,
    item: WatchItem,
    page: FetchResult,
) -> tuple[Status, Extraction | None]:
    found = extract(page.body, page.url) or await read_shopify_extraction(
        client, page.body, page.url
    )
    if found:
        logger.info("ok: %s %.2f via %s", item.name, found.price, found.source)
        return Status.OK, found
    answer = await mimo.extract(page.url, page.body)
    if answer is None:
        last = read_last_priced(conn, item_id)
        logger.warning("stale: %s (MiMo unavailable, keeping last known price)", item.name)
        if not last:
            return Status.STALE, None
        return Status.STALE, Extraction(last.price, last.currency, last.in_stock, "last-known")
    if answer.blocked:
        logger.warning("blocked: %s (MiMo saw a bot wall)", item.name)
        return Status.BLOCKED, None
    if answer.price is None:
        logger.warning("no price found: %s", item.name)
        return Status.ERROR, None
    logger.info("ok: %s %.2f via mimo", item.name, answer.price)
    return Status.OK, Extraction(answer.price, answer.currency, answer.in_stock, "mimo")


async def check_item(
    client: httpx.AsyncClient,
    conn: sqlite3.Connection,
    mimo: MiMo,
    item_id: int,
    item: WatchItem,
    checked_at: str,
) -> Observation:
    fetched = await fetch(client, item.url)
    found = None
    if fetched.status is FetchStatus.BLOCKED:
        logger.warning("blocked: %s (%s)", item.name, fetched.reason)
        status = Status.BLOCKED
    elif fetched.status is FetchStatus.ERROR:
        logger.warning("fetch error: %s (%s)", item.name, fetched.reason)
        status = Status.ERROR
    else:
        status, found = await _read_page(client, conn, mimo, item_id, item, fetched)
    obs = Observation(
        item_id=item_id,
        checked_at=checked_at,
        status=status,
        price=found.price if found else None,
        currency=found.currency if found else None,
        in_stock=found.in_stock if found else None,
    )
    create_observation(conn, obs)
    return obs
