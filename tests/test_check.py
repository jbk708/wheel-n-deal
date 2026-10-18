import json
from pathlib import Path

import httpx
import pytest
import respx

from wheel_n_deal.check import check_item
from wheel_n_deal.config import LLMConfig, WatchItem
from wheel_n_deal.fetch import make_client
from wheel_n_deal.llm import MiMo
from wheel_n_deal.store import (
    Observation,
    Status,
    create_observation,
    open_store,
    read_observations,
    read_selector,
    write_item,
)

FIXTURES = Path(__file__).parent / "fixtures"
AT = "2026-10-18T12:00:00+00:00"
COMPLETIONS = "https://llm.example/v1/chat/completions"
NO_PRICE_PAGE = "<title>Grinder</title><h1>Grinder</h1><p>Now $87.00</p>"


def _llm_answer(**overrides: object) -> dict:
    answer = {
        "price": 87.0,
        "currency": "USD",
        "in_stock": True,
        "variant": None,
        "condition": "new",
        "list_price": None,
        "blocked": False,
        "evidence": "Now $87.00",
    }
    answer.update(overrides)
    content = json.dumps(answer)
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


@pytest.fixture
async def client():
    async with make_client() as c:
        yield c


@pytest.fixture
def conn(tmp_path):
    return open_store(tmp_path / "state.db")


async def _check(client, conn, url: str, previous: list[Observation] = ()) -> tuple[Status, list]:
    item = WatchItem(url=url, name="Thing", target_price=100)
    item_id = write_item(conn, item.url, item.name, item.target_price)
    for obs in previous:
        create_observation(conn, obs)
    mimo = MiMo(client, LLMConfig(base_url="https://llm.example/v1"), "k")
    obs, _ = await check_item(client, conn, mimo, item_id, item, AT)
    assert obs == read_observations(conn, item_id, limit=1)[0]
    return obs.status, [obs]


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


async def test_check_item_returns_page_only_when_fetched(client, conn):
    url = "https://shop.example/products/grinder"
    item = WatchItem(url=url, name="Thing", target_price=100)
    item_id = write_item(conn, item.url, item.name, item.target_price)
    mimo = MiMo(client, LLMConfig(base_url="https://llm.example/v1"), "k")
    html = (FIXTURES / "jsonld_product.html").read_text()
    with respx.mock:
        route = respx.get(url).respond(200, text=html)
        assert (await check_item(client, conn, mimo, item_id, item, AT))[1] == html
        route.respond(403, text="denied")
        assert (await check_item(client, conn, mimo, item_id, item, AT))[1] is None


async def test_blocked_stores_blocked_without_price(client, conn):
    url = "https://shop.example/products/grinder"
    with respx.mock:
        route = respx.get(url).respond(403, text="denied")
        status, [obs] = await _check(client, conn, url)
    assert route.call_count == 1
    assert status is Status.BLOCKED
    assert (obs.status, obs.price) == (Status.BLOCKED, None)


async def test_structured_price_skips_mimo(client, conn):
    url = "https://shop.example/products/grinder"
    with respx.mock:
        respx.get(url).respond(200, text=(FIXTURES / "jsonld_product.html").read_text())
        llm = respx.post(COMPLETIONS)
        await _check(client, conn, url)
    assert llm.call_count == 0


async def test_blocked_page_skips_mimo(client, conn):
    url = "https://shop.example/products/grinder"
    with respx.mock:
        respx.get(url).respond(403, text="denied")
        llm = respx.post(COMPLETIONS)
        await _check(client, conn, url)
    assert llm.call_count == 0


async def test_no_structured_price_uses_mimo(client, conn):
    url = "https://shop.example/products/grinder"
    with respx.mock:
        respx.get(url).respond(200, text=NO_PRICE_PAGE)
        respx.post(COMPLETIONS).respond(200, json=_llm_answer())
        status, [obs] = await _check(client, conn, url)
    assert status is Status.OK
    assert (obs.price, obs.currency, obs.in_stock) == (87.0, "USD", True)


async def test_mimo_finds_no_price_stores_error(client, conn):
    url = "https://shop.example/products/grinder"
    with respx.mock:
        respx.get(url).respond(200, text=NO_PRICE_PAGE)
        respx.post(COMPLETIONS).respond(200, json=_llm_answer(price=None, evidence=None))
        status, [obs] = await _check(client, conn, url)
    assert status is Status.ERROR
    assert obs.price is None


async def test_mimo_sees_bot_wall_stores_blocked(client, conn):
    url = "https://shop.example/products/grinder"
    with respx.mock:
        respx.get(url).respond(200, text=NO_PRICE_PAGE)
        respx.post(COMPLETIONS).respond(200, json=_llm_answer(price=None, blocked=True))
        status, [obs] = await _check(client, conn, url)
    assert status is Status.BLOCKED
    assert obs.price is None


async def test_mimo_down_keeps_last_known_price_as_stale(client, conn):
    url = "https://shop.example/products/grinder"
    earlier = [
        Observation(1, "2026-10-17T00:00:00+00:00", Status.OK, 95.0, "USD", True),
        Observation(1, "2026-10-17T06:00:00+00:00", Status.ERROR, None, None, None),
    ]
    with respx.mock:
        respx.get(url).respond(200, text=NO_PRICE_PAGE)
        respx.post(COMPLETIONS).mock(side_effect=httpx.ConnectError("down"))
        status, [obs] = await _check(client, conn, url, earlier)
    assert status is Status.STALE
    assert (obs.price, obs.currency, obs.in_stock) == (95.0, "USD", True)


async def test_mimo_down_without_history_is_stale_without_price(client, conn):
    url = "https://shop.example/products/grinder"
    with respx.mock:
        respx.get(url).respond(200, text=NO_PRICE_PAGE)
        respx.post(COMPLETIONS).respond(200, json={"choices": [{"message": {"content": "?"}}]})
        status, [obs] = await _check(client, conn, url)
    assert status is Status.STALE
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


async def test_shopify_js_bad_json_falls_back_to_mimo(client, conn):
    url = "https://store.example/products/example-fragrance"
    with respx.mock:
        respx.get(url).respond(200, text=(FIXTURES / "shopify_page.html").read_text())
        respx.get("https://store.example/products/example-fragrance.js").respond(
            200, text="<html>not json</html>"
        )
        llm = respx.post(COMPLETIONS).respond(200, json=_llm_answer())
        status, _ = await _check(client, conn, url)
    assert llm.call_count == 1
    assert status is Status.OK


LEARNABLE_PAGE = "<html><body><h1>Grinder</h1><div id='buy'><b>Now $87.00</b></div></body></html>"
MOVED_PAGE = "<html><body><h1>Grinder</h1><section><i>Now $79.00</i></section></body></html>"


async def test_learned_selector_skips_mimo_until_it_breaks(client, conn):
    url = "https://shop.example/products/grinder"
    item = WatchItem(url=url, name="Thing", target_price=100)
    item_id = write_item(conn, item.url, item.name, item.target_price)
    mimo = MiMo(client, LLMConfig(base_url="https://llm.example/v1"), "k")
    with respx.mock:
        page = respx.get(url).respond(200, text=LEARNABLE_PAGE)
        llm = respx.post(COMPLETIONS).respond(200, json=_llm_answer())
        first, _ = await check_item(client, conn, mimo, item_id, item, AT)
        assert read_selector(conn, item_id) == "css:#buy > b:nth-of-type(1)"

        second, _ = await check_item(client, conn, mimo, item_id, item, AT)
        assert llm.call_count == 1

        page.respond(200, text=MOVED_PAGE)
        llm.respond(200, json=_llm_answer(price=79.0, evidence="Now $79.00"))
        third, _ = await check_item(client, conn, mimo, item_id, item, AT)
    assert llm.call_count == 2
    assert [o.price for o in (first, second, third)] == [87.0, 87.0, 79.0]
    assert all(o.status is Status.OK for o in (first, second, third))
    assert read_selector(conn, item_id) == (
        "css:body:nth-of-type(1) > section:nth-of-type(1) > i:nth-of-type(1)"
    )


async def test_price_not_on_page_saves_no_selector(client, conn):
    url = "https://shop.example/products/grinder"
    with respx.mock:
        respx.get(url).respond(200, text=NO_PRICE_PAGE)
        respx.post(COMPLETIONS).respond(200, json=_llm_answer(price=85.0, evidence="$85"))
        status, _ = await _check(client, conn, url)
    assert status is Status.OK
    assert read_selector(conn, 1) is None


async def test_broken_selector_with_mimo_down_is_dropped_and_stale(client, conn):
    url = "https://shop.example/products/grinder"
    item = WatchItem(url=url, name="Thing", target_price=100)
    item_id = write_item(conn, item.url, item.name, item.target_price)
    mimo = MiMo(client, LLMConfig(base_url="https://llm.example/v1"), "k")
    with respx.mock:
        respx.get(url).respond(200, text=LEARNABLE_PAGE)
        respx.post(COMPLETIONS).respond(200, json=_llm_answer())
        await check_item(client, conn, mimo, item_id, item, AT)
    with respx.mock:
        respx.get(url).respond(200, text=MOVED_PAGE)
        respx.post(COMPLETIONS).mock(side_effect=httpx.ConnectError("down"))
        obs, _ = await check_item(client, conn, mimo, item_id, item, AT)
    assert (obs.status, obs.price) == (Status.STALE, 87.0)
    assert read_selector(conn, item_id) is None
