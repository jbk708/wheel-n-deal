import re

import pytest
from camoufox.pkgman import INSTALL_DIR

from wheel_n_deal.browser import CAMOUFOX_OPTIONS, render
from wheel_n_deal.fetch import FetchStatus

# Launching without a fetched build makes Camoufox download one (~2.4 GB), so tests that
# launch the browser only run where it is installed (the image, a dev machine), not on CI.
requires_camoufox = pytest.mark.skipif(
    not (INSTALL_DIR / "browsers").is_dir(), reason="no local Camoufox (uv run camoufox fetch)"
)
# A fetched Camoufox whose system libraries are missing (e.g. a dev machine without them).
BROWSER_UNRUNNABLE = re.compile(r"Failed to launch|cannot open shared object", re.IGNORECASE)

PAGE = "<html><head><title>Grinder</title></head><body><h1>$149.99</h1></body></html>"


@requires_camoufox
async def test_render_failure_is_an_error_result_not_an_exception(dead_proxy_url):
    # Nothing listens on the proxy port.
    result = await render("http://127.0.0.1:9/", dead_proxy_url)
    assert result.status is FetchStatus.ERROR
    assert result.reason
    assert result.body is None


@requires_camoufox
async def test_render_through_unreachable_proxy_is_an_error(dead_proxy_url):
    result = await render("http://127.0.0.1:9/", dead_proxy_url)
    assert result.status is FetchStatus.ERROR


@pytest.mark.parametrize("proxy_url", [None, ""])
async def test_render_requires_a_proxy(proxy_url):
    with pytest.raises(ValueError, match="proxy"):
        await render("https://shop.example/p", proxy_url)


@requires_camoufox
async def test_loopback_pages_go_through_the_proxy_too(local_proxy, dead_proxy_url, monkeypatch):
    # Firefox bypasses proxies for loopback unless told not to; wheel-n-deal runs with host
    # networking, so a direct loopback request would reach the host's own services. Nothing
    # listens on the target port: only the proxy can answer.
    # The geoip exit-IP lookup needs a real proxy with CONNECT; this stand-in only relays GET.
    monkeypatch.setitem(CAMOUFOX_OPTIONS, "geoip", False)
    target = f"{dead_proxy_url}/p"
    local_proxy.responses[target] = (200, {"Content-Type": "text/html"}, PAGE)
    result = await render(target, local_proxy.url)
    if result.status is FetchStatus.ERROR and BROWSER_UNRUNNABLE.search(result.reason or ""):
        pytest.skip(f"local Camoufox cannot start: {result.reason}")
    assert result.status is FetchStatus.OK
    assert target in local_proxy.requests


def test_webrtc_cannot_bypass_the_proxy():
    assert CAMOUFOX_OPTIONS["block_webrtc"] is True


def test_fingerprint_follows_the_proxy_exit_not_this_host():
    assert CAMOUFOX_OPTIONS["geoip"] is True


def test_pages_come_back_in_english():
    assert CAMOUFOX_OPTIONS["locale"] == "en-US"


def test_loopback_is_not_exempt_from_the_proxy():
    prefs = CAMOUFOX_OPTIONS["firefox_user_prefs"]
    assert prefs["network.proxy.allow_hijacking_localhost"] is True
