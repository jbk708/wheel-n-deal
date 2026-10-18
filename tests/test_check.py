from pathlib import Path

import pytest
import respx

from wheel_n_deal.check import check_item
from wheel_n_deal.config import WatchItem
from wheel_n_deal.fetch import make_client
from wheel_n_deal.store import Status, open_store, read_observations, write_item

FIXTURES = Path(__file__).parent / "fixtures"
AT = "2026-10-18T12:00:00+00:00"


@pytest.fixture
async def client():
    async with make_client() as c:
        yield c


@pytest.fixture
def conn(tmp_path):
    return open_store(tmp_path / "state.db")


async def _check(client, conn, url: str) -> tuple[Status, list]:
    item = WatchItem(url=url, name="Thing", target_price=100)
    item_id = write_item(conn, item.url, item.name, item.target_price)
    status = await check_item(client, conn, item_id, item, AT)
    return status, read_observations(conn, item_id)


async def test_ok_stores_price(client, conn):
    url = "https://shop.example/products/grinder"
    with respx.mock:
        respx.get(url).respond(200, text=(FIXTURES / "jsonld_product.html").read_text())
        status, [obs] = await _check(client, conn, url)
    assert status is Status.OK
    assert (obs.status, obs.price, obs.currency, obs.in_stock, obs.checked_at) == (
        Status.OK,
        149.99,
        "USD",
        True,
        AT,
    )


async def test_blocked_stores_blocked_without_price(client, conn):
    url = "https://shop.example/products/grinder"
    with respx.mock:
        route = respx.get(url).respond(403, text="denied")
        status, [obs] = await _check(client, conn, url)
    assert route.call_count == 1
    assert status is Status.BLOCKED
    assert (obs.status, obs.price) == (Status.BLOCKED, None)


async def test_no_price_stores_error(client, conn):
    url = "https://shop.example/products/grinder"
    with respx.mock:
        respx.get(url).respond(200, text="<title>Grinder</title><h1>Grinder</h1>")
        status, [obs] = await _check(client, conn, url)
    assert status is Status.ERROR
    assert obs.price is None


async def test_shopify_falls_back_to_product_js(client, conn):
    url = "https://store.example/products/example-fragrance?variant=2000000002"
    with respx.mock:
        respx.get(url).respond(200, text=(FIXTURES / "shopify_page.html").read_text())
        respx.get("https://store.example/products/example-fragrance.js").respond(
            200, text=(FIXTURES / "shopify_product.js").read_text()
        )
        status, [obs] = await _check(client, conn, url)
    assert status is Status.OK
    assert (obs.price, obs.in_stock) == (148.0, False)


async def test_shopify_js_bad_json_is_error(client, conn):
    url = "https://store.example/products/example-fragrance"
    with respx.mock:
        respx.get(url).respond(200, text=(FIXTURES / "shopify_page.html").read_text())
        respx.get("https://store.example/products/example-fragrance.js").respond(
            200, text="<html>not json</html>"
        )
        status, _ = await _check(client, conn, url)
    assert status is Status.ERROR
