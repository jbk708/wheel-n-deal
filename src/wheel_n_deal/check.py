import json
import logging
import sqlite3

import httpx

from wheel_n_deal.config import WatchItem
from wheel_n_deal.extract import Extraction, extract, extract_shopify_js, shopify_js_url
from wheel_n_deal.fetch import FetchStatus, fetch
from wheel_n_deal.store import Observation, Status, create_observation

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


async def check_item(
    client: httpx.AsyncClient,
    conn: sqlite3.Connection,
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
        found = extract(fetched.body, fetched.url) or await read_shopify_extraction(
            client, fetched.body, fetched.url
        )
        status = Status.OK if found else Status.ERROR
        if found:
            logger.info("ok: %s %.2f via %s", item.name, found.price, found.source)
        else:
            logger.warning("no price found: %s", item.name)
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
