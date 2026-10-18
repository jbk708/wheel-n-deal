import json

import httpx
import pytest
import respx

from wheel_n_deal.config import NtfyConfig, WatchItem
from wheel_n_deal.fetch import make_client
from wheel_n_deal.notify import (
    Message,
    alert_on_price,
    blocked_message,
    next_alert_state,
    price_drop_message,
    publish,
)
from wheel_n_deal.store import Observation, Status, open_store, read_alert_armed, write_item

NTFY = NtfyConfig(url="https://ntfy.example", topic="deals")
TOKEN = "test-token"
ITEM = WatchItem(url="https://shop.example/products/grinder", name="Grinder", target_price=100)
AT = "2026-10-18T12:00:00+00:00"


@pytest.fixture
async def client():
    async with make_client() as c:
        yield c


@pytest.fixture
def conn(tmp_path):
    return open_store(tmp_path / "state.db")


def _obs(price: float | None, status: Status = Status.OK) -> Observation:
    return Observation(1, AT, status, price, "USD", True)


@pytest.mark.parametrize(
    "armed, price, expected",
    [
        (True, 90, (True, False)),
        (False, 90, (False, False)),
        (False, 110, (False, True)),
        (True, 110, (False, True)),
        (False, 100, (False, False)),
        (True, 100, (False, True)),
    ],
)
def test_next_alert_state(armed, price, expected):
    assert next_alert_state(armed, price, 100) == expected


def test_price_drop_message():
    message = price_drop_message(ITEM, 89.5, "USD")
    assert message.title == "Price drop: Grinder"
    assert "$89.50" in message.message
    assert "$100.00" in message.message
    assert message.click == ITEM.url


def test_price_drop_message_other_currency():
    assert "89.50 EUR" in price_drop_message(ITEM, 89.5, "EUR").message


def test_blocked_message_lists_names():
    message = blocked_message(["Grinder", "Kettle"])
    assert "Grinder" in message.message and "Kettle" in message.message
    assert message.click is None


async def test_publish_payload_and_auth(client):
    message = Message(title="T", message="M", tags=["tag"], priority=4, click=ITEM.url)
    with respx.mock:
        route = respx.post("https://ntfy.example/").respond(200)
        assert await publish(client, NTFY, TOKEN, message) is True
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert json.loads(request.content) == {
        "topic": "deals",
        "title": "T",
        "message": "M",
        "tags": ["tag"],
        "priority": 4,
        "click": ITEM.url,
        "actions": [{"action": "view", "label": "Open", "url": ITEM.url}],
    }


async def test_publish_without_click_has_no_actions(client):
    message = Message(title="T", message="M", tags=[], priority=2)
    with respx.mock:
        route = respx.post("https://ntfy.example/").respond(200)
        await publish(client, NTFY, TOKEN, message)
    body = json.loads(route.calls.last.request.content)
    assert "click" not in body and "actions" not in body


@pytest.mark.parametrize("side_effect", [httpx.ConnectError("down"), httpx.Response(500)])
async def test_publish_failure_returns_false_without_token_in_log(client, caplog, side_effect):
    message = Message(title="T", message="M", tags=[], priority=3)
    with respx.mock:
        respx.post("https://ntfy.example/").mock(side_effect=[side_effect])
        assert await publish(client, NTFY, TOKEN, message) is False
    assert TOKEN not in caplog.text


async def test_alert_fires_once_then_rearms_after_recovery(client, conn):
    item_id = write_item(conn, ITEM.url, ITEM.name, ITEM.target_price)
    with respx.mock:
        route = respx.post("https://ntfy.example/").respond(200)
        fired = [
            await alert_on_price(client, conn, NTFY, TOKEN, item_id, ITEM, _obs(price))
            for price in (120, 90, 85, 95, 110, 80)
        ]
    assert fired == [False, True, False, False, False, True]
    assert route.call_count == 2


async def test_alert_ignores_non_ok_observations(client, conn):
    item_id = write_item(conn, ITEM.url, ITEM.name, ITEM.target_price)
    with respx.mock:
        route = respx.post("https://ntfy.example/").respond(200)
        assert not await alert_on_price(
            client, conn, NTFY, TOKEN, item_id, ITEM, _obs(50, Status.STALE)
        )
        assert not await alert_on_price(
            client, conn, NTFY, TOKEN, item_id, ITEM, _obs(None, Status.BLOCKED)
        )
    assert route.call_count == 0
    assert read_alert_armed(conn, item_id) is True


async def test_failed_publish_stays_armed_for_next_check(client, conn):
    item_id = write_item(conn, ITEM.url, ITEM.name, ITEM.target_price)
    with respx.mock:
        respx.post("https://ntfy.example/").respond(503)
        assert not await alert_on_price(client, conn, NTFY, TOKEN, item_id, ITEM, _obs(90))
    assert read_alert_armed(conn, item_id) is True


def test_price_drop_message_appends_verdict():
    message = price_drop_message(ITEM, 89.5, "USD", "Verdict: real deal. Lowest seen.")
    assert message.message.endswith("\n\nVerdict: real deal. Lowest seen.")


async def test_alert_asks_verdict_once_per_alert(client, conn):
    item_id = write_item(conn, ITEM.url, ITEM.name, ITEM.target_price)
    asked = []

    async def verdict() -> str:
        asked.append(1)
        return "Verdict: real deal. Lowest seen."

    with respx.mock:
        route = respx.post("https://ntfy.example/").respond(200)
        for price in (120, 90, 85, 110, 80):
            await alert_on_price(client, conn, NTFY, TOKEN, item_id, ITEM, _obs(price), verdict)
    assert len(asked) == 2
    bodies = [json.loads(call.request.content)["message"] for call in route.calls]
    assert all(body.endswith("Verdict: real deal. Lowest seen.") for body in bodies)


async def test_alert_without_verdict_when_mimo_down(client, conn):
    item_id = write_item(conn, ITEM.url, ITEM.name, ITEM.target_price)

    async def verdict() -> None:
        return None

    with respx.mock:
        route = respx.post("https://ntfy.example/").respond(200)
        assert await alert_on_price(client, conn, NTFY, TOKEN, item_id, ITEM, _obs(90), verdict)
    assert "Verdict" not in json.loads(route.calls.last.request.content)["message"]
