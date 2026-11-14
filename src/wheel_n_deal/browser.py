"""Headless Camoufox (anti-detect Firefox) for pages that refuse a plain request.

A browser is launched per call and closed afterwards: it is only needed for the occasional
blocked page, and keeping one alive would hold a few hundred MB between checks. Each launch
gets a fresh Linux Firefox fingerprint whose timezone and locale match the proxy's exit IP.
"""

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from wheel_n_deal.fetch import FetchResult, FetchStatus, classify, require_proxy

NAVIGATION_TIMEOUT_MS = 45_000
NETWORK_IDLE_TIMEOUT_MS = 15_000
CAMOUFOX_OPTIONS = {
    "headless": True,
    # The host is Linux: claiming another OS makes Camoufox randomise canvas and WebGL
    # readback to hide the real one, which itself reads as a privacy-hardened browser.
    "os": "linux",
    # Timezone, locale and geolocation from the proxy's exit IP, not this host.
    "geoip": True,
    # WebRTC may otherwise send UDP straight to STUN servers, revealing the real address
    # behind the proxy.
    "block_webrtc": True,
    "firefox_user_prefs": {
        # Firefox bypasses proxies for loopback by default; wheel-n-deal runs with host
        # networking, so a direct loopback request would reach the host's own services.
        "network.proxy.allow_hijacking_localhost": True,
    },
}


async def render(url: str, proxy_url: str) -> FetchResult:
    """Camoufox never falls back to a direct connection when its proxy is down."""
    proxy = {"server": require_proxy(proxy_url)}
    try:
        async with AsyncCamoufox(proxy=proxy, **CAMOUFOX_OPTIONS) as browser:
            page = await browser.new_page()
            response = await page.goto(
                url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS
            )
            try:
                await page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
            except PlaywrightTimeoutError:
                pass  # Busy pages never go idle; what has rendered by now is enough.
            html = await page.content()
            final_url = page.url
    except PlaywrightError as exc:
        return FetchResult(url, FetchStatus.ERROR, reason=exc.message.splitlines()[0])
    except Exception as exc:  # noqa: BLE001 - geoip lookup through a dead proxy, launch errors
        return FetchResult(url, FetchStatus.ERROR, reason=f"{type(exc).__name__}: {exc}"[:200])
    if response is None:
        return FetchResult(final_url, FetchStatus.ERROR, reason="no response")
    return classify(final_url, response.status, html)
