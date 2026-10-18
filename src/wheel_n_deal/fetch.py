import re
from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import version
from urllib.parse import urljoin, urlsplit

import httpx

USER_AGENT = f"wheel-n-deal/{version('wheel-n-deal')} (+personal price tracker)"
TIMEOUT_SECONDS = 30
SHORT_LINK_HOSTS = frozenset({"a.co", "amzn.to"})
MAX_SHORT_LINK_HOPS = 5
BLOCKED_HTTP_STATUSES = frozenset({403, 429, 503})
# Markers of bot walls and CAPTCHA interstitials. We only detect them: a blocked page is
# recorded and reported, never solved or worked around.
BOT_WALL_MARKERS = (
    "/errors/validatecaptcha",
    "enter the characters you see below",
    "px-captcha",
    "<title>just a moment...</title>",
    "challenge-form",
    "<h1>access denied</h1>",
    "pardon our interruption",
)
_AMAZON_ASIN = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)")


class FetchStatus(StrEnum):
    OK = "ok"
    BLOCKED = "blocked"
    ERROR = "error"


@dataclass(frozen=True)
class FetchResult:
    url: str
    status: FetchStatus
    http_status: int | None = None
    body: str | None = None
    reason: str | None = None


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
        follow_redirects=True,
    )


def canonical_amazon_url(url: str) -> str:
    parts = urlsplit(url)
    match = _AMAZON_ASIN.search(parts.path)
    if "amazon." not in parts.netloc or not match:
        return url
    return f"{parts.scheme}://{parts.netloc}/dp/{match.group(1)}"


def block_reason(http_status: int, body: str) -> str | None:
    if http_status in BLOCKED_HTTP_STATUSES:
        return f"http {http_status}"
    if not body.strip():
        return "empty body"
    lowered = body.lower()
    for marker in BOT_WALL_MARKERS:
        if marker in lowered:
            return f"bot wall ({marker})"
    return None


async def resolve_short_link(client: httpx.AsyncClient, url: str) -> str:
    for _ in range(MAX_SHORT_LINK_HOPS):
        if urlsplit(url).hostname not in SHORT_LINK_HOSTS:
            break
        response = await client.head(url, follow_redirects=False)
        location = response.headers.get("location")
        if not location:
            break
        url = urljoin(url, location)
    return canonical_amazon_url(url)


async def fetch(client: httpx.AsyncClient, url: str) -> FetchResult:
    try:
        url = await resolve_short_link(client, url)
        response = await client.get(url)
    except httpx.HTTPError as exc:
        return FetchResult(url=url, status=FetchStatus.ERROR, reason=type(exc).__name__)
    final_url = str(response.url)
    reason = block_reason(response.status_code, response.text)
    if reason:
        return FetchResult(final_url, FetchStatus.BLOCKED, response.status_code, reason=reason)
    if response.is_error:
        return FetchResult(
            final_url,
            FetchStatus.ERROR,
            response.status_code,
            reason=f"http {response.status_code}",
        )
    return FetchResult(final_url, FetchStatus.OK, response.status_code, body=response.text)
