import pytest

from wheel_n_deal.learned import derive_selector, price_on_page, read_price

NESTED = (
    "<html><body><div class='recs'><span>$9.99</span></div>"
    "<section><div><p>Grinder</p><p class='p'><b>Now $42.50</b></p></div></section>"
    "</body></html>"
)
WITH_ID = "<html><body><div><span id='buy-price'>$42.50</span></div></body></html>"
JSON_LD = (
    '<html><head><script type="application/ld+json">'
    '{"@type": "Thing", "pricing": {"current": {"amountUSD": "42.50"}}}'
    "</script></head><body><h1>Grinder</h1></body></html>"
)


def test_css_path_locates_evidence():
    selector = derive_selector(NESTED, 42.5, "Now $42.50")
    assert selector is not None and selector.startswith("css:")
    assert read_price(NESTED, selector) == 42.5


def test_css_path_prefers_id():
    selector = derive_selector(WITH_ID, 42.5, "$42.50")
    assert selector == "css:#buy-price"
    assert read_price(WITH_ID, selector) == 42.5


def test_price_text_found_when_evidence_spans_elements():
    html = "<html><body><div>Our price: <em>$42.50</em> today only</div></body></html>"
    selector = derive_selector(html, 42.5, "Our price: $42.50 (today only)")
    assert selector is not None
    assert read_price(html, selector) == 42.5


def test_json_ld_key_locates_price():
    selector = derive_selector(JSON_LD, 42.5, '"amountUSD": "42.50"')
    assert selector is not None and selector.startswith("jsonld:")
    assert read_price(JSON_LD, selector) == 42.5


@pytest.mark.parametrize(
    "html, price, evidence",
    [
        ("<html><body><p>Was $60.00 Now $42.50</p></body></html>", 42.5, "Was $60.00 Now $42.50"),
        ("<html><body><p>$42.50</p></body></html>", 39.99, "$39.99"),
        ("<html><body><p>Sold out</p></body></html>", 42.5, "$42.50"),
    ],
)
def test_validation_rejects_selectors_that_do_not_read_the_price(html, price, evidence):
    assert derive_selector(html, price, evidence) is None


def test_namespaced_tags_are_skipped_not_crashed_on():
    html = "<html><body><fb:like><span>$5.00</span></fb:like></body></html>"
    assert derive_selector(html, 5.0, "$5.00") is None


def test_no_evidence_derives_nothing():
    assert derive_selector(NESTED, 42.5, None) is None


@pytest.mark.parametrize(
    "selector",
    [
        "css:section > div > p:nth-of-type(9)",
        'jsonld:[0, "pricing", "missing"]',
        'jsonld:[5, "pricing"]',
        "unknown:thing",
    ],
)
def test_broken_selector_reads_nothing(selector):
    assert read_price(NESTED + JSON_LD, selector) is None


@pytest.mark.parametrize(
    ("html", "price", "found"),
    [
        ("<p>Now $87.00</p>", 87.0, True),
        ("<p>Now $1,299.99</p>", 1299.99, True),
        ('<meta property="product:price:amount" content="42">', 42.0, True),
        ('<script>{"price": "19.5"}</script>', 19.5, True),
        ("<p>Now $87.00</p>", 12.0, False),
        ("<p>Now $87.00</p>", 8.7, False),
        ("<p>No price here</p>", 87.0, False),
    ],
)
def test_price_on_page(html, price, found):
    assert price_on_page(html, price) is found
