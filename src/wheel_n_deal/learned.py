"""Selectors learned from MiMo's evidence, so later runs can read the price without MiMo.

A selector is `css:<path>` or `jsonld:<JSON list [script index, key, ...]>`. One is only kept
if reading it back from the same live page yields exactly the price MiMo reported."""

import json
import re
from collections.abc import Iterator
from typing import Any

from bs4 import BeautifulSoup, Tag

from wheel_n_deal.extract import parse_price

_SAFE_ID = re.compile(r"^[A-Za-z][\w-]*$")
_SAFE_TAG = re.compile(r"^[a-z][a-z0-9-]*$")
_SKIP_TAGS = ("script", "style", "noscript", "template", "head", "title")


def _normalized(tag: Tag) -> str:
    return " ".join(tag.get_text(" ").split())


def _deepest_containing(soup: BeautifulSoup, needle: str) -> list[Tag]:
    matches = [
        tag
        for tag in soup.find_all(True)
        if tag.name not in _SKIP_TAGS and needle in _normalized(tag)
    ]
    ancestors = {id(parent) for tag in matches for parent in tag.parents}
    return [tag for tag in matches if id(tag) not in ancestors]


def _css_path(tag: Tag) -> str | None:
    parts = []
    while tag is not None and tag.name not in ("[document]", "html"):
        tag_id = tag.get("id")
        if isinstance(tag_id, str) and _SAFE_ID.match(tag_id):
            parts.insert(0, f"#{tag_id}")
            break
        if not _SAFE_TAG.match(tag.name):
            return None
        index = 1 + sum(1 for sibling in tag.find_previous_siblings(tag.name))
        parts.insert(0, f"{tag.name}:nth-of-type({index})")
        tag = tag.parent
    return " > ".join(parts)


def _json_ld_documents(soup: BeautifulSoup) -> list[Any]:
    documents = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            documents.append(json.loads(script.string or ""))
        except json.JSONDecodeError:
            documents.append(None)
    return documents


def _scalars(data: Any, path: list) -> Iterator[tuple[list, Any]]:
    if isinstance(data, dict):
        for key, value in data.items():
            yield from _scalars(value, [*path, key])
    elif isinstance(data, list):
        for index, value in enumerate(data):
            yield from _scalars(value, [*path, index])
    else:
        yield path, data


def _css_candidates(soup: BeautifulSoup, price: float, evidence: str) -> list[str]:
    needles = [" ".join(evidence.split()), f"{price:.2f}", f"{price:,.2f}"]
    paths = [_css_path(tag) for needle in needles for tag in _deepest_containing(soup, needle)]
    return [f"css:{path}" for path in paths if path]


def _json_ld_candidates(soup: BeautifulSoup, price: float) -> list[str]:
    return [
        f"jsonld:{json.dumps([index, *path])}"
        for index, document in enumerate(_json_ld_documents(soup))
        for path, value in _scalars(document, [])
        if path and not isinstance(value, bool) and parse_price(value) == price
    ]


def _read_json_ld(soup: BeautifulSoup, keys: list) -> Any:
    documents = _json_ld_documents(soup)
    if not keys or not isinstance(keys[0], int) or keys[0] >= len(documents):
        return None
    value = documents[keys[0]]
    for key in keys[1:]:
        try:
            value = value[key]
        except (KeyError, IndexError, TypeError):
            return None
    return None if isinstance(value, dict | list | bool) else value


def _read_price(soup: BeautifulSoup, selector: str) -> float | None:
    kind, _, locator = selector.partition(":")
    if kind == "css":
        tag = soup.select_one(locator)
        return parse_price(tag.get("content") or _normalized(tag)) if tag else None
    if kind == "jsonld":
        return parse_price(_read_json_ld(soup, json.loads(locator)))
    return None


def read_price(html: str, selector: str) -> float | None:
    return _read_price(BeautifulSoup(html, "html.parser"), selector)


def derive_selector(html: str, price: float, evidence: str | None) -> str | None:
    if not evidence:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for selector in [*_css_candidates(soup, price, evidence), *_json_ld_candidates(soup, price)]:
        if _read_price(soup, selector) == price:
            return selector
    return None
