import logging
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx

from wheel_n_deal.config import NtfyConfig, WatchItem
from wheel_n_deal.store import Observation, Status, read_alert_armed, update_alert_armed

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


@dataclass(frozen=True)
class Message:
    title: str
    message: str
    tags: list[str] = field(default_factory=list)
    priority: int = 3
    click: str | None = None


def money(amount: float, currency: str | None) -> str:
    if currency in (None, "USD"):
        return f"${amount:.2f}"
    return f"{amount:.2f} {currency}"


def price_drop_message(
    item: WatchItem, price: float, currency: str | None, verdict: str | None = None
) -> Message:
    text = (
        f"{item.name} is {money(price, currency)}, below your "
        f"{money(item.target_price, currency)} target."
    )
    return Message(
        title=f"Price drop: {item.name}",
        message=f"{text}\n\n{verdict}" if verdict else text,
        tags=["moneybag"],
        priority=4,
        click=item.url,
    )


def blocked_message(names: list[str]) -> Message:
    return Message(
        title=f"{len(names)} item(s) blocked",
        message="These sites refused the price check, so prices are not updating:\n"
        + "\n".join(f"- {name}" for name in names),
        tags=["no_entry"],
        priority=2,
    )


def _payload(topic: str, message: Message) -> dict:
    payload = {
        "topic": topic,
        "title": message.title,
        "message": message.message,
        "tags": message.tags,
        "priority": message.priority,
    }
    if message.click:
        payload["click"] = message.click
        payload["actions"] = [{"action": "view", "label": "Open", "url": message.click}]
    return payload


async def publish(
    client: httpx.AsyncClient, ntfy: NtfyConfig, token: str | None, message: Message
) -> bool:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = await client.post(
            f"{ntfy.url.rstrip('/')}/",
            json=_payload(ntfy.topic, message),
            headers=headers,
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning("ntfy publish failed: HTTP %d", exc.response.status_code)
        return False
    except httpx.HTTPError as exc:
        logger.warning("ntfy publish failed: %s", type(exc).__name__)
        return False
    logger.info("ntfy sent: %s", message.title)
    return True


def next_alert_state(armed: bool, price: float, target: float) -> tuple[bool, bool]:
    """Return (fire, armed): fire once below target, re-arm only once back above it."""
    if price < target:
        return armed, False
    if price > target:
        return False, True
    return False, armed


async def alert_on_price(
    client: httpx.AsyncClient,
    conn: sqlite3.Connection,
    ntfy: NtfyConfig,
    token: str | None,
    item_id: int,
    item: WatchItem,
    obs: Observation,
    verdict: Callable[[], Awaitable[str | None]] | None = None,
) -> bool:
    if obs.status is not Status.OK or obs.price is None:
        return False
    armed = read_alert_armed(conn, item_id)
    fire, next_armed = next_alert_state(armed, obs.price, item.target_price)
    sent = False
    if fire:
        note = await verdict() if verdict else None
        message = price_drop_message(item, obs.price, obs.currency, note)
        sent = await publish(client, ntfy, token, message)
    # A failed publish leaves the alert armed so the next check retries it.
    if next_armed != armed and (sent or not fire):
        update_alert_armed(conn, item_id, next_armed, obs.checked_at)
    return sent
