import re
from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import version
from urllib.parse import urljoin, urlsplit

import httpx

# For our own services (MiMo, ntfy, heartbeat); shops get BROWSER_HEADERS instead.
APP_USER_AGENT = f"wheel-n-deal/{version('wheel-n-deal')} (+personal price tracker)"
# Keep in step with the Chromium bundled by the pinned Playwright, so the plain request and
# the headless fallback present the same browser.
CHROME_MAJOR = 153
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    f" Chrome/{CHROME_MAJOR}.0.0.0 Safari/537.36"
)
SEC_CH_UA = (
    f'"Google Chrome";v="{CHROME_MAJOR}", "Chromium";v="{CHROME_MAJOR}", "Not)A;Brand";v="24"'
)
BROWSER_HEADERS = {
    "User-Agent": BROWSER_USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
        "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "sec-ch-ua": SEC_CH_UA,
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Priority": "u=0, i",
}
TIMEOUT_SECONDS = 30
SHORT_LINK_HOSTS = frozenset({"a.co", "amzn.to"})
MAX_SHORT_LINK_HOPS = 5
BLOCKED_HTTP_STATUSES = frozenset({403, 429, 503})
# Markers of bot walls and CAPTCHA interstitials. A blocked page gets one headless retry;
# CAPTCHAs are never solved.
BOT_WALL_MARKERS = (
    "validatecaptcha",
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


# trust_env=False: proxy environment variables must never reroute either client. Shops go
# through fetch.proxy_url only (required); our own services always go direct.
def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": APP_USER_AGENT},
        timeout=TIMEOUT_SECONDS,
        follow_redirects=True,
        trust_env=False,
    )


def require_proxy(proxy_url: str | None) -> str:
    if not proxy_url:
        raise ValueError("shop fetches need fetch.proxy_url; refusing to fetch directly")
    return proxy_url


class ShopClient(httpx.AsyncClient):
    def __init__(self, proxy_url: str) -> None:
        super().__init__(
            headers=BROWSER_HEADERS,
            timeout=TIMEOUT_SECONDS,
            follow_redirects=True,
            proxy=require_proxy(proxy_url),
            trust_env=False,
        )


def make_shop_client(proxy_url: str) -> ShopClient:
    return ShopClient(proxy_url)


def canonical_amazon_url(url: str) -> str:
    parts = urlsplit(url)
    match = _AMAZON_ASIN.search(parts.path)
    if "amazon." not in parts.netloc or not match:
        return url
    return f"https://{parts.netloc}/dp/{match.group(1)}"


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


async def canonical_url(client: ShopClient, url: str) -> str:
    """Resolve Amazon short links and drop tracking parts, so one product has one URL."""
    for _ in range(MAX_SHORT_LINK_HOPS):
        if urlsplit(url).hostname not in SHORT_LINK_HOSTS:
            break
        # a.co answers HEAD with 404, so ask with GET but stop at the redirect.
        response = await client.get(url, follow_redirects=False)
        location = response.headers.get("location")
        if not location:
            break
        url = urljoin(url, location)
    return canonical_amazon_url(url)


async def fetch(client: ShopClient, url: str) -> FetchResult:
    try:
        url = await canonical_url(client, url)
        response = await client.get(url)
    except (httpx.ProxyError, httpx.ConnectError) as exc:
        # Every connection is to the proxy, so this means it is down.
        reason = f"proxy unreachable ({type(exc).__name__})"
        return FetchResult(url, FetchStatus.ERROR, reason=reason)
    except httpx.HTTPError as exc:
        return FetchResult(url=url, status=FetchStatus.ERROR, reason=type(exc).__name__)
    return classify(str(response.url), response.status_code, response.text)


def classify(url: str, http_status: int, body: str) -> FetchResult:
    reason = block_reason(http_status, body)
    if reason:
        return FetchResult(url, FetchStatus.BLOCKED, http_status, reason=reason)
    if http_status >= 400:
        return FetchResult(url, FetchStatus.ERROR, http_status, reason=f"http {http_status}")
    return FetchResult(url, FetchStatus.OK, http_status, body=body)
