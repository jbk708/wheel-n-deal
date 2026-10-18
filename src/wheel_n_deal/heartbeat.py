"""Success heartbeat for an Uptime Kuma push monitor: Kuma alerts when the pings stop, so a
failed ping must never fail the run that earned it."""

import logging

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0


async def ping(client: httpx.AsyncClient, url: str | None) -> None:
    if url is None:
        return
    try:
        response = await client.get(url, timeout=_TIMEOUT)
        response.raise_for_status()
    # The URL carries the push token, so neither message may echo it.
    except httpx.HTTPStatusError as exc:
        logger.warning("heartbeat ping failed: HTTP %d", exc.response.status_code)
        return
    except httpx.HTTPError as exc:
        logger.warning("heartbeat ping failed: %s", type(exc).__name__)
        return
    logger.info("heartbeat ping sent")
