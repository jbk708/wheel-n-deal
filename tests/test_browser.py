from wheel_n_deal.browser import render
from wheel_n_deal.fetch import FetchStatus


async def test_render_failure_is_an_error_result_not_an_exception():
    # Port 9 is closed; with or without a local Chromium this must come back as ERROR.
    result = await render("http://127.0.0.1:9/")
    assert result.status is FetchStatus.ERROR
    assert result.reason
    assert result.body is None
