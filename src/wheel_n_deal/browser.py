"""Headless Chromium for pages that refuse a plain request.

A browser is launched per call and closed afterwards: it is only needed for the occasional
blocked page, and keeping one alive would hold a few hundred MB between checks.
"""

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from wheel_n_deal.fetch import (
    BROWSER_USER_AGENT,
    CHROME_MAJOR,
    FetchResult,
    FetchStatus,
    classify,
)

NAVIGATION_TIMEOUT_MS = 45_000
NETWORK_IDLE_TIMEOUT_MS = 15_000
LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
]
# Makes navigator.userAgentData, navigator.platform and the sec-ch-ua headers agree with
# the Windows Chrome User-Agent instead of reporting headless Linux.
USER_AGENT_OVERRIDE = {
    "userAgent": BROWSER_USER_AGENT,
    "acceptLanguage": "en-US,en",
    "platform": "Win32",
    "userAgentMetadata": {
        "brands": [
            {"brand": "Google Chrome", "version": str(CHROME_MAJOR)},
            {"brand": "Chromium", "version": str(CHROME_MAJOR)},
            {"brand": "Not)A;Brand", "version": "24"},
        ],
        "fullVersion": f"{CHROME_MAJOR}.0.0.0",
        "platform": "Windows",
        "platformVersion": "19.0.0",
        "architecture": "x86",
        "model": "",
        "mobile": False,
        "bitness": "64",
    },
}


async def render(url: str) -> FetchResult:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chromium", args=LAUNCH_ARGS)
            try:
                context = await browser.new_context(
                    user_agent=BROWSER_USER_AGENT,
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                    timezone_id="America/Los_Angeles",
                )
                page = await context.new_page()
                cdp = await context.new_cdp_session(page)
                await cdp.send("Network.setUserAgentOverride", USER_AGENT_OVERRIDE)
                response = await page.goto(
                    url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS
                )
                try:
                    await page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
                except PlaywrightTimeoutError:
                    pass  # Busy pages never go idle; what has rendered by now is enough.
                html = await page.content()
                final_url = page.url
            finally:
                await browser.close()
    except PlaywrightError as exc:
        return FetchResult(url, FetchStatus.ERROR, reason=exc.message.splitlines()[0])
    if response is None:
        return FetchResult(final_url, FetchStatus.ERROR, reason="no response")
    return classify(final_url, response.status, html)
