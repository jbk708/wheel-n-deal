import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_SHOPIFY_PRODUCT_PATH = re.compile(r"/products/([^/?#.]+)")
_SHOPIFY_MARKERS = ("cdn.shopify.com", "Shopify.shop")
_OUT_OF_STOCK = ("outofstock", "soldout", "discontinued")
_IN_STOCK = ("instock", "limitedavailability", "onlineonly", "instoreonly")
_VARIANT_PARAMS = ("skuId", "sku", "variant")
_META_PRICE_NAMES = ("product:price:amount", "og:price:amount")
_META_CURRENCY_NAMES = ("product:price:currency", "og:price:currency")
_META_AVAILABILITY_NAMES = ("product:availability", "og:availability")

# Ported from the legacy per-site scrapers, minus Selenium and the "first element whose class
# contains 'price'" heuristics, which tend to pick up prices of recommended products.
SITE_SELECTORS: dict[str, tuple[str, ...]] = {
    "amazon.": (
        "#corePrice_feature_div .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-offscreen",
        "#apex_desktop .a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
    ),
    "walmart.": ("[data-testid='price-wrap'] [itemprop='price']", ".price-characteristic"),
    "bestbuy.": (".priceView-customer-price span",),
    "target.": ("[data-test='product-price']",),
    "ebay.": (".x-price-primary span", "#prcIsum", "#mm-saleDscPrc"),
    "sephora.": ("span[data-at='price']", "[data-comp='Price'] b"),
    "costco.": ("[automation-id='productPrice']",),
}


@dataclass(frozen=True)
class Extraction:
    price: float
    currency: str | None
    in_stock: bool | None
    source: str


def parse_price(value: Any) -> float | None:
    if isinstance(value, int | float):
        number = float(value)
    else:
        match = _NUMBER.search(str(value or "").replace(",", ""))
        if not match:
            return None
        number = float(match.group())
    return number if number > 0 else None


def parse_in_stock(value: Any) -> bool | None:
    text = re.sub(r"[\s_-]", "", str(value or "")).lower()
    if any(marker in text for marker in _OUT_OF_STOCK):
        return False
    if any(marker in text for marker in _IN_STOCK):
        return True
    return None


def _variant_hint(url: str) -> str | None:
    query = parse_qs(urlsplit(url).query)
    for param in _VARIANT_PARAMS:
        if query.get(param):
            return query[param][0]
    return None


def _types(node: dict) -> list[str]:
    value = node.get("@type")
    return value if isinstance(value, list) else [value]


def _json_ld_nodes(data: Any) -> Iterator[dict]:
    if isinstance(data, list):
        for item in data:
            yield from _json_ld_nodes(item)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _json_ld_nodes(data["@graph"])


def _from_offers(offers: Any, path: str) -> Extraction | None:
    candidates = (
        [(f"{path}[{i}]", offer) for i, offer in enumerate(offers)]
        if isinstance(offers, list)
        else [(path, offers)]
    )
    for offer_path, offer in candidates:
        if not isinstance(offer, dict):
            continue
        for key in ("price", "lowPrice"):
            price = parse_price(offer.get(key))
            if price:
                return Extraction(
                    price=price,
                    currency=offer.get("priceCurrency"),
                    in_stock=parse_in_stock(offer.get("availability")),
                    source=f"{offer_path}.{key}",
                )
    return None


def _from_product_group(group: dict, url: str) -> Extraction | None:
    variants = [v for v in group.get("hasVariant") or [] if isinstance(v, dict)]
    hint = _variant_hint(url)
    preferred = [v for v in variants if hint and hint in (v.get("sku"), v.get("productID"))]
    for variant in preferred or variants:
        found = _from_offers(
            variant.get("offers"),
            f"jsonld:ProductGroup.hasVariant[sku={variant.get('sku')}].offers",
        )
        if found:
            return found
    return _from_offers(group.get("offers"), "jsonld:ProductGroup.offers")


def extract_json_ld(soup: BeautifulSoup, url: str) -> Extraction | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        for node in _json_ld_nodes(data):
            types = _types(node)
            if "ProductGroup" in types:
                found = _from_product_group(node, url)
            elif "Product" in types:
                found = _from_offers(node.get("offers"), "jsonld:Product.offers")
            else:
                continue
            if found:
                return found
    return None


def _meta_content(soup: BeautifulSoup, names: tuple[str, ...]) -> tuple[str, str] | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return name, tag["content"]
    return None


def _itemprop_value(soup: BeautifulSoup, prop: str) -> str | None:
    tag = soup.find(attrs={"itemprop": prop})
    if not tag:
        return None
    return tag.get("content") or tag.get("href") or tag.get_text(strip=True)


def extract_meta(soup: BeautifulSoup) -> Extraction | None:
    found = _meta_content(soup, _META_PRICE_NAMES)
    price = parse_price(found[1]) if found else None
    if price:
        currency = _meta_content(soup, _META_CURRENCY_NAMES)
        availability = _meta_content(soup, _META_AVAILABILITY_NAMES)
        return Extraction(
            price=price,
            currency=currency[1] if currency else None,
            in_stock=parse_in_stock(availability[1]) if availability else None,
            source=f"meta:{found[0]}",
        )
    price = parse_price(_itemprop_value(soup, "price"))
    if price:
        return Extraction(
            price=price,
            currency=_itemprop_value(soup, "priceCurrency"),
            in_stock=parse_in_stock(_itemprop_value(soup, "availability")),
            source="itemprop:price",
        )
    return None


def extract_site(soup: BeautifulSoup, url: str) -> Extraction | None:
    host = urlsplit(url).hostname or ""
    for site, selectors in SITE_SELECTORS.items():
        if site not in host:
            continue
        for selector in selectors:
            tag = soup.select_one(selector)
            price = parse_price(tag.get("content") or tag.get_text(strip=True)) if tag else None
            if price:
                return Extraction(
                    price=price, currency=None, in_stock=None, source=f"css:{selector}"
                )
    return None


def extract(html: str, url: str) -> Extraction | None:
    soup = BeautifulSoup(html, "html.parser")
    return extract_json_ld(soup, url) or extract_meta(soup) or extract_site(soup, url)


def shopify_js_url(html: str, url: str) -> str | None:
    parts = urlsplit(url)
    match = _SHOPIFY_PRODUCT_PATH.search(parts.path)
    if not match or not any(marker in html for marker in _SHOPIFY_MARKERS):
        return None
    return f"{parts.scheme}://{parts.netloc}/products/{match.group(1)}.js"


def extract_shopify_js(data: dict, url: str) -> Extraction | None:
    hint = _variant_hint(url)
    for variant in data.get("variants") or []:
        if hint and str(variant.get("id")) == hint and variant.get("price"):
            return Extraction(
                price=variant["price"] / 100,
                currency=None,
                in_stock=variant.get("available"),
                source=f"shopify:variants[id={hint}].price",
            )
    if not data.get("price"):
        return None
    return Extraction(
        price=data["price"] / 100,
        currency=None,
        in_stock=data.get("available"),
        source="shopify:price",
    )
