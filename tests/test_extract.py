import json
from pathlib import Path

import pytest

from wheel_n_deal.extract import (
    Extraction,
    extract,
    extract_shopify_js,
    parse_price,
    shopify_js_url,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.mark.parametrize(
    "value, expected",
    [
        ("$1,299.99", 1299.99),
        ("149.99", 149.99),
        (199, 199.0),
        (68.5, 68.5),
        ("USD 10", 10.0),
        ("Price not found", None),
        ("", None),
        (None, None),
        ("0.00", None),
    ],
)
def test_parse_price(value, expected):
    assert parse_price(value) == expected


def test_json_ld_product_offer():
    result = extract(fixture("jsonld_product.html"), "https://shop.example/products/grinder")
    assert result == Extraction(
        price=149.99, currency="USD", in_stock=True, source="jsonld:Product.offers.price"
    )


def test_json_ld_graph_with_aggregate_offer_list():
    result = extract(fixture("jsonld_graph_aggregate.html"), "https://store.example/p/headphones")
    assert result == Extraction(
        price=199.0, currency="USD", in_stock=False, source="jsonld:Product.offers[0].lowPrice"
    )


def test_json_ld_product_group_picks_variant_from_url():
    url = "https://www.sephora.com/product/example-P000001?skuId=2222222"
    result = extract(fixture("sephora_product_group.html"), url)
    assert result == Extraction(
        price=135.0,
        currency="USD",
        in_stock=False,
        source="jsonld:ProductGroup.hasVariant[sku=2222222].offers.price",
    )


def test_json_ld_product_group_defaults_to_first_variant():
    result = extract(
        fixture("sephora_product_group.html"), "https://www.sephora.com/product/example"
    )
    assert result is not None
    assert result.price == 68.0
    assert result.source == "jsonld:ProductGroup.hasVariant[sku=1111111].offers.price"


def test_meta_product_price():
    result = extract(fixture("meta_og.html"), "https://shop.example/kettle")
    assert result == Extraction(
        price=1049.0, currency="USD", in_stock=True, source="meta:product:price:amount"
    )


def test_itemprop_price():
    result = extract(fixture("itemprop.html"), "https://shop.example/burrs")
    assert result == Extraction(price=39.5, currency="USD", in_stock=False, source="itemprop:price")


def test_amazon_site_selector_prefers_core_price():
    result = extract(fixture("amazon.html"), "https://www.amazon.com/dp/B0ABCDEF12")
    assert result is not None
    assert result.price == 129.95
    assert result.source == "css:#corePrice_feature_div .a-offscreen"


def test_costco_site_selector():
    result = extract(fixture("costco.html"), "https://www.costco.com/p/-/grinder/4000123456")
    assert result is not None
    assert result.price == 119.99
    assert result.source == "css:[automation-id='productPrice']"


def test_site_selectors_only_apply_to_their_site():
    assert extract(fixture("amazon.html"), "https://shop.example/x") is None


def test_no_price_returns_none():
    assert extract("<html><title>x</title><h1>x</h1></html>", "https://shop.example/x") is None


def test_broken_json_ld_is_skipped():
    html = '<script type="application/ld+json">{not json</script>' + fixture("meta_og.html")
    result = extract(html, "https://shop.example/kettle")
    assert result is not None
    assert result.source == "meta:product:price:amount"


def test_shopify_js_url_detected():
    url = "https://store.example/collections/all/products/example-fragrance?variant=2000000002"
    assert shopify_js_url(fixture("shopify_page.html"), url) == (
        "https://store.example/products/example-fragrance.js"
    )


def test_shopify_js_url_requires_shopify_store():
    assert shopify_js_url(fixture("meta_og.html"), "https://shop.example/products/x") is None


def test_shopify_js_url_requires_product_path():
    assert shopify_js_url(fixture("shopify_page.html"), "https://store.example/pages/about") is None


def test_shopify_js_selects_variant_from_url():
    data = json.loads(fixture("shopify_product.js"))
    url = "https://store.example/products/example-fragrance?variant=2000000002"
    assert extract_shopify_js(data, url) == Extraction(
        price=148.0, currency=None, in_stock=False, source="shopify:variants[id=2000000002].price"
    )


def test_shopify_js_defaults_to_product_price():
    data = json.loads(fixture("shopify_product.js"))
    assert extract_shopify_js(data, "https://store.example/products/example-fragrance") == (
        Extraction(price=96.0, currency=None, in_stock=True, source="shopify:price")
    )
