from wheel_n_deal.browser import LAUNCH_ARGS, render
from wheel_n_deal.fetch import FetchStatus


async def test_render_failure_is_an_error_result_not_an_exception():
    # Port 9 is closed; with or without a local Chromium this must come back as ERROR.
    result = await render("http://127.0.0.1:9/", None)
    assert result.status is FetchStatus.ERROR
    assert result.reason
    assert result.body is None


async def test_render_through_unreachable_proxy_is_an_error(dead_proxy_url):
    result = await render("http://127.0.0.1:9/", dead_proxy_url)
    assert result.status is FetchStatus.ERROR


def test_webrtc_cannot_bypass_the_proxy():
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in LAUNCH_ARGS
    assert "--webrtc-ip-handling-policy=disable_non_proxied_udp" in LAUNCH_ARGS
