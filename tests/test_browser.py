import pytest

from wheel_n_deal.browser import LAUNCH_ARGS, render
from wheel_n_deal.fetch import FetchStatus

PAGE = "<html><head><title>Grinder</title></head><body><h1>$149.99</h1></body></html>"


async def test_render_failure_is_an_error_result_not_an_exception(dead_proxy_url):
    # Nothing listens on the proxy port; with or without a local Chromium this is an ERROR.
    result = await render("http://127.0.0.1:9/", dead_proxy_url)
    assert result.status is FetchStatus.ERROR
    assert result.reason
    assert result.body is None


async def test_render_through_unreachable_proxy_is_an_error(dead_proxy_url):
    result = await render("http://127.0.0.1:9/", dead_proxy_url)
    assert result.status is FetchStatus.ERROR


@pytest.mark.parametrize("proxy_url", [None, ""])
async def test_render_requires_a_proxy(proxy_url):
    with pytest.raises(ValueError, match="proxy"):
        await render("https://shop.example/p", proxy_url)


async def test_loopback_pages_go_through_the_proxy_too(local_proxy, dead_proxy_url):
    # Chromium bypasses proxies for loopback unless told not to; wheel-n-deal runs with host
    # networking, so a direct loopback request would reach the host's own services. Nothing
    # listens on the target port: only the proxy can answer.
    target = f"{dead_proxy_url}/p"
    local_proxy.responses[target] = (200, {"Content-Type": "text/html"}, PAGE)
    result = await render(target, local_proxy.url)
    if result.status is FetchStatus.ERROR and "Executable doesn't exist" in (result.reason or ""):
        pytest.skip("no local Chromium (uv run playwright install chromium)")
    assert result.status is FetchStatus.OK
    assert target in local_proxy.requests


def test_webrtc_cannot_bypass_the_proxy():
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in LAUNCH_ARGS
    assert "--webrtc-ip-handling-policy=disable_non_proxied_udp" in LAUNCH_ARGS
