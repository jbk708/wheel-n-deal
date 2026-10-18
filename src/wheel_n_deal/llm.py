"""MiMo extraction fallback for pages where structured extraction found no price.

MiMo runs as a requeue-prone Slurm job behind LiteLLM and Cloudflare, so it can be gone for
hours: every failure returns None and the caller keeps the last known price."""

import asyncio
import json
import logging
import re
import time

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from wheel_n_deal.config import LLMConfig
from wheel_n_deal.fetch import USER_AGENT

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


def parse_extraction(content: str | None) -> LLMExtraction | None:
    for candidate in _candidates(content or ""):
        try:
            return LLMExtraction.model_validate(json.loads(candidate))
        except (json.JSONDecodeError, ValidationError):
            continue
    return None


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
            headers={"Authorization": f"Bearer {self._api_key}", "User-Agent": USER_AGENT},
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

    async def extract(self, url: str, html: str) -> LLMExtraction | None:
        if not self._api_key:
            logger.warning("MiMo skipped: LLM_API_KEY is not set")
            return None
        prompt = f"{_INSTRUCTIONS}\nURL: {url}\n\n{trim_page(html)}"
        async with self._lock:
            try:
                content = await self._complete(prompt)
            except httpx.HTTPStatusError as exc:
                logger.warning("MiMo unavailable: HTTP %d", exc.response.status_code)
                return None
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                logger.warning("MiMo unavailable: %s", type(exc).__name__)
                return None
        result = parse_extraction(content)
        if result is None:
            logger.warning("MiMo answer is not valid extraction JSON: %.200r", content)
        return result
