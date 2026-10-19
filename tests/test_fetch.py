import httpx
import pytest
import respx

from wheel_n_deal.fetch import (
    APP_USER_AGENT,
    BROWSER_HEADERS,
    FetchStatus,
    block_reason,
    canonical_amazon_url,
    canonical_url,
    fetch,
    make_client,
    make_shop_client,
)

PRODUCT_HTML = "<html><head><title>Grinder</title></head><body><h1>Grinder</h1></body></html>"


@pytest.fixture
async def client():
    async with make_shop_client() as c:
        yield c


def test_app_user_agent_names_the_app():
    assert APP_USER_AGENT.startswith("wheel-n-deal/")
    version = APP_USER_AGENT.split("/", 1)[1].split(" ", 1)[0]
    assert version[0].isdigit()


def test_browser_headers_look_like_desktop_chrome():
    ua = BROWSER_HEADERS["User-Agent"]
    major = ua.split("Chrome/", 1)[1].split(".", 1)[0]
    assert ua.startswith("Mozilla/5.0 (Windows NT 10.0; Win64; x64)") and "Headless" not in ua
    assert f'"Google Chrome";v="{major}"' in BROWSER_HEADERS["sec-ch-ua"]
    assert BROWSER_HEADERS["sec-ch-ua-platform"] == '"Windows"'
    assert BROWSER_HEADERS["Accept-Language"].startswith("en-US")
    assert BROWSER_HEADERS["Accept"].startswith("text/html")


async def test_shop_client_decodes_brotli_and_zstd():
    import brotli
    import zstandard

    async with make_shop_client() as shop:
        with respx.mock:
            respx.get("https://shop.example/br").respond(
                200, content=brotli.compress(b"<h1>br</h1>"), headers={"content-encoding": "br"}
            )
            respx.get("https://shop.example/zstd").respond(
                200,
                content=zstandard.ZstdCompressor().compress(b"<h1>zstd</h1>"),
                headers={"content-encoding": "zstd"},
            )
            assert (await fetch(shop, "https://shop.example/br")).body == "<h1>br</h1>"
            assert (await fetch(shop, "https://shop.example/zstd")).body == "<h1>zstd</h1>"


async def test_app_client_keeps_the_app_user_agent():
    async with make_client() as app:
        assert app.headers["user-agent"] == APP_USER_AGENT
        assert "sec-ch-ua" not in app.headers


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "https://www.amazon.com/Some-Product-Name/dp/B0ABCDEF12/ref=sr_1_1?tag=x",
            "https://www.amazon.com/dp/B0ABCDEF12",
        ),
        (
            "https://www.amazon.com/gp/product/B0ABCDEF12?psc=1",
            "https://www.amazon.com/dp/B0ABCDEF12",
        ),
        (
            "http://www.amazon.com/dp/B0CRS3N43Q?ref=cm_sw_r_cp_ud_dp&th=1",
            "https://www.amazon.com/dp/B0CRS3N43Q",
        ),
        ("https://www.amazon.com/s?k=grinder", "https://www.amazon.com/s?k=grinder"),
        ("https://shop.example/products/x", "https://shop.example/products/x"),
    ],
)
def test_canonical_amazon_url(url, expected):
    assert canonical_amazon_url(url) == expected


@pytest.mark.parametrize(
    "status, body, blocked",
    [
        (200, PRODUCT_HTML, False),
        (403, PRODUCT_HTML, True),
        (429, PRODUCT_HTML, True),
        (503, PRODUCT_HTML, True),
        (200, "", True),
        (200, "   \n", True),
        (
            200,
            "<p>Enter the characters you see below</p><form action='/errors/validateCaptcha'>",
            True,
        ),
        (200, "<form method='get' action='/errors_page/validateCaptcha'>", True),
        (200, "<form action='/ERRORS_PAGE/VALIDATECAPTCHA'>", True),
        (200, "<title>Just a moment...</title><div id='challenge-form'>", True),
        (200, "<div id='px-captcha'></div>", True),
        (200, "<h1>Access Denied</h1>You don't have permission to access", True),
        (200, "<title>Pardon Our Interruption</title>", True),
    ],
)
def test_block_reason(status, body, blocked):
    assert (block_reason(status, body) is not None) is blocked


async def test_fetch_ok_sends_browser_headers(client):
    with respx.mock:
        route = respx.get("https://shop.example/products/x").respond(200, text=PRODUCT_HTML)
        result = await fetch(client, "https://shop.example/products/x")
    assert result.status is FetchStatus.OK
    assert result.body == PRODUCT_HTML
    sent = route.calls.last.request.headers
    for name, value in BROWSER_HEADERS.items():
        assert sent[name] == value


async def test_fetch_follows_redirects(client):
    with respx.mock:
        respx.get("https://shop.example/old").respond(
            301, headers={"location": "https://shop.example/new"}
        )
        respx.get("https://shop.example/new").respond(200, text=PRODUCT_HTML)
        result = await fetch(client, "https://shop.example/old")
    assert result.status is FetchStatus.OK
    assert result.url == "https://shop.example/new"


@pytest.mark.parametrize("short", ["https://a.co/d/abc123", "https://amzn.to/3xYz"])
async def test_fetch_resolves_amazon_short_links(client, short):
    long_url = "https://www.amazon.com/Grinder-Thing/dp/B0ABCDEF12/ref=x?tag=y"
    with respx.mock:
        respx.head(short).respond(404)
        respx.get(short).respond(301, headers={"location": long_url})
        page = respx.get("https://www.amazon.com/dp/B0ABCDEF12").respond(200, text=PRODUCT_HTML)
        result = await fetch(client, short)
    assert page.called
    assert result.status is FetchStatus.OK
    assert result.url == "https://www.amazon.com/dp/B0ABCDEF12"


async def test_fetch_accepts_costco_p_urls(client):
    url = "https://www.costco.com/p/-/espresso-grinder/4000123456"
    with respx.mock:
        respx.get(url).respond(200, text=PRODUCT_HTML)
        result = await fetch(client, url)
    assert result.status is FetchStatus.OK
    assert result.url == url


async def test_fetch_blocked_is_not_retried(client):
    with respx.mock:
        route = respx.get("https://shop.example/products/x").respond(403, text="nope")
        result = await fetch(client, "https://shop.example/products/x")
    assert result.status is FetchStatus.BLOCKED
    assert result.http_status == 403
    assert result.reason
    assert route.call_count == 1


async def test_fetch_network_error_is_error_not_exception(client):
    with respx.mock:
        respx.get("https://shop.example/products/x").mock(side_effect=httpx.ConnectTimeout("t"))
        result = await fetch(client, "https://shop.example/products/x")
    assert result.status is FetchStatus.ERROR
    assert result.body is None


async def test_fetch_http_error_status_is_error(client):
    with respx.mock:
        respx.get("https://shop.example/gone").respond(404, text="not found")
        result = await fetch(client, "https://shop.example/gone")
    assert result.status is FetchStatus.ERROR
    assert result.http_status == 404


async def test_canonical_url_resolves_short_link_with_get_without_fetching_the_page(client):
    with respx.mock:
        respx.get("https://a.co/d/0e5nj345").respond(
            301,
            headers={"location": "https://www.amazon.com/dp/B0CRS3N43Q?ref=cm_sw_r_cp_ud_dp"},
        )
        assert await canonical_url(client, "https://a.co/d/0e5nj345") == (
            "https://www.amazon.com/dp/B0CRS3N43Q"
        )
        assert respx.calls.call_count == 1


async def test_canonical_url_follows_short_link_chains(client):
    with respx.mock:
        respx.get("https://amzn.to/x").respond(301, headers={"location": "https://a.co/d/y"})
        respx.get("https://a.co/d/y").respond(
            302, headers={"location": "https://www.amazon.com/Thing/dp/B0ABCDEF12/ref=x"}
        )
        assert await canonical_url(client, "https://amzn.to/x") == (
            "https://www.amazon.com/dp/B0ABCDEF12"
        )


async def test_canonical_url_needs_no_network_for_long_urls(client):
    with respx.mock:
        assert await canonical_url(client, "https://www.amazon.com/x/dp/B0ABCDEF12?tag=t") == (
            "https://www.amazon.com/dp/B0ABCDEF12"
        )
        assert await canonical_url(client, "https://shop.example/p?id=1") == (
            "https://shop.example/p?id=1"
        )
