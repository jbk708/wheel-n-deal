"""MiMo extraction fallback for pages where structured extraction found no price, and the
optional deal verdict on a below-target alert.

MiMo runs as a requeue-prone Slurm job behind LiteLLM and Cloudflare, so it can be gone for
hours: every failure returns None and the caller keeps the last known price."""

import asyncio
import json
import logging
import re
import time
from typing import Literal

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from wheel_n_deal.config import LLMConfig, WatchItem
from wheel_n_deal.fetch import APP_USER_AGENT
from wheel_n_deal.notify import money
from wheel_n_deal.store import Observation, Status

logger = logging.getLogger(__name__)

PAGE_VIEW_CHARS = 12_000
# Cloudflare cuts responses at ~100s time-to-first-byte.
_TIMEOUT = httpx.Timeout(85.0, connect=10.0)
# Headroom so the model's reasoning tokens don't crowd out the answer.
_MAX_TOKENS = 4096
_HEADLINE_CHARS = 500
_JSON_LD_CHARS = 4000
_META_CHARS = 2000
_META_PREFIXES = ("og:", "product:", "twitter:")
_NOISE_TAGS = ("script", "style", "noscript", "svg", "template", "nav", "footer", "iframe")
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_OBJECT = re.compile(r"\{.*\}", re.DOTALL)

_INSTRUCTIONS = """\
You extract the current price of the product on a shopping page.
The page view below has the page title, the H1, any JSON-LD, product meta tags, and the main text.

Reply with only a JSON object with exactly these keys, no prose:
{"price": number or null, "currency": ISO 4217 code or null, "in_stock": true/false/null,
 "variant": string or null, "condition": "new"/"used"/"refurbished" or null,
 "list_price": number or null, "blocked": true/false, "evidence": string or null}

Rules:
- "price" is what a shopper pays now for the main product (the variant in the URL if any),
  not prices of recommended or related products, shipping, or per-unit prices.
- "list_price" is the struck-through "was"/list price, if shown.
- "evidence" is the exact text copied verbatim from the page view that shows the price.
- "blocked" is true when the page is a bot check, CAPTCHA, or access-denied page instead of
  a product page; then "price" is null.
- If there is no price for the product, "price" is null.
"""


_VERDICT_INSTRUCTIONS = """\
A price tracker alert fired: the product below dropped under the shopper's target price.
Judge whether it is a real deal, using the item's own price history and the page view.

Reply with only a JSON object with exactly these keys, no prose:
{"real_deal": true/false, "flags": [zero or more of "inflated_list_price",
 "refurbished_or_used", "membership_only", "not_lowest_seen"], "reason": one short sentence}

Flags:
- "inflated_list_price": the "was"/list price is far above what the history shows it sells for.
- "refurbished_or_used": the offer is refurbished, renewed, open-box, or used.
- "membership_only": the price needs a membership, subscription, or club card.
- "not_lowest_seen": the history has a clearly lower price than now.
"""

_HISTORY_ROWS = 60

VerdictFlag = Literal[
    "inflated_list_price", "refurbished_or_used", "membership_only", "not_lowest_seen"
]


class LLMExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    price: float | None = Field(gt=0)
    currency: str | None
    in_stock: bool | None
    variant: str | None
    condition: str | None
    list_price: float | None = Field(gt=0)
    blocked: bool
    evidence: str | None


class LLMVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    real_deal: bool
    flags: list[VerdictFlag]
    reason: str


def _text(tag) -> str:
    return " ".join(tag.get_text(" ").split()) if tag else ""


def _meta_lines(soup: BeautifulSoup) -> list[str]:
    lines = []
    for tag in soup.find_all("meta"):
        key = tag.get("property") or tag.get("name") or tag.get("itemprop") or ""
        if tag.get("content") and (key.startswith(_META_PREFIXES) or tag.get("itemprop")):
            lines.append(f"{key}: {tag['content']}")
    return lines


def trim_page(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    headline = (
        f"Title: {_text(soup.title)[:_HEADLINE_CHARS]}\nH1: {_text(soup.h1)[:_HEADLINE_CHARS]}\n"
    )
    json_ld = "\n".join(
        (script.string or "").strip()
        for script in soup.find_all("script", type="application/ld+json")
    )
    meta = "\n".join(_meta_lines(soup))
    for tag in soup.find_all(_NOISE_TAGS):
        tag.decompose()
    main_text = _text(soup.find("main") or soup.body or soup)
    rest = (
        f"\nJSON-LD:\n{json_ld[:_JSON_LD_CHARS]}\n"
        f"\nMeta:\n{meta[:_META_CHARS]}\n"
        f"\nText:\n{main_text}"
    )
    return headline + rest[: PAGE_VIEW_CHARS - len(headline)]


def _candidates(content: str) -> list[str]:
    stripped = _THINK.sub("", content).strip()
    stripped = stripped.removeprefix("```json").removeprefix("```").removesuffix("```")
    return [stripped, *_OBJECT.findall(stripped)]


def _parse[M: BaseModel](model: type[M], content: str | None) -> M | None:
    for candidate in _candidates(content or ""):
        try:
            return model.model_validate(json.loads(candidate))
        except (json.JSONDecodeError, ValidationError):
            continue
    return None


def parse_extraction(content: str | None) -> LLMExtraction | None:
    return _parse(LLMExtraction, content)


def parse_verdict(content: str | None) -> LLMVerdict | None:
    return _parse(LLMVerdict, content)


def verdict_prompt(
    item: WatchItem, price: float, currency: str | None, history: list[Observation], html: str
) -> str:
    rows = [
        f"{obs.checked_at[:10]}: {money(obs.price, obs.currency)}"
        for obs in history[:_HISTORY_ROWS]
        if obs.status is Status.OK and obs.price is not None
    ]
    notes = f"Shopper notes: {item.notes}\n" if item.notes else ""
    return (
        f"{_VERDICT_INSTRUCTIONS}\nProduct: {item.name}\nURL: {item.url}\n{notes}"
        f"Now {money(price, currency)}, target {money(item.target_price, currency)}\n"
        f"\nPrice history, newest first:\n" + "\n".join(rows) + f"\n\n{trim_page(html)}"
    )


def format_verdict(verdict: LLMVerdict) -> str:
    if verdict.real_deal:
        head = "real deal"
    else:
        flags = ", ".join(flag.replace("_", " ") for flag in verdict.flags)
        head = f"doubtful ({flags})" if flags else "doubtful"
    return f"Verdict: {head}. {verdict.reason}"


class MiMo:
    def __init__(self, client: httpx.AsyncClient, config: LLMConfig, api_key: str | None):
        self._client = client
        self._config = config
        self._api_key = api_key
        # The backend has few slots shared with interactive users; never queue more than one.
        self._lock = asyncio.Lock()

    async def _complete(self, prompt: str) -> str | None:
        started = time.monotonic()
        response = await self._client.post(
            f"{self._config.base_url.rstrip('/')}/chat/completions",
            json={
                "model": self._config.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": _MAX_TOKENS,
            },
            headers={"Authorization": f"Bearer {self._api_key}", "User-Agent": APP_USER_AGENT},
            timeout=_TIMEOUT,
        )
        logger.info(
            "MiMo %s %d in %.1fs",
            self._config.model,
            response.status_code,
            time.monotonic() - started,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    async def _ask(self, prompt: str) -> str | None:
        if not self._api_key:
            logger.warning("MiMo skipped: LLM_API_KEY is not set")
            return None
        async with self._lock:
            try:
                return await self._complete(prompt)
            except httpx.HTTPStatusError as exc:
                logger.warning("MiMo unavailable: HTTP %d", exc.response.status_code)
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                logger.warning("MiMo unavailable: %s", type(exc).__name__)
        return None

    async def extract(self, url: str, html: str) -> LLMExtraction | None:
        content = await self._ask(f"{_INSTRUCTIONS}\nURL: {url}\n\n{trim_page(html)}")
        if content is None:
            return None
        result = parse_extraction(content)
        if result is None:
            logger.warning("MiMo answer is not valid extraction JSON: %.200r", content)
        return result

    async def verdict(
        self,
        item: WatchItem,
        price: float,
        currency: str | None,
        history: list[Observation],
        html: str,
    ) -> LLMVerdict | None:
        content = await self._ask(verdict_prompt(item, price, currency, history, html))
        if content is None:
            return None
        result = parse_verdict(content)
        if result is None:
            logger.warning("MiMo answer is not valid verdict JSON: %.200r", content)
        return result
