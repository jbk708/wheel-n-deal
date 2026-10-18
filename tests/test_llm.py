import asyncio
import json

import httpx
import pytest
import respx

from wheel_n_deal.config import LLMConfig, WatchItem
from wheel_n_deal.fetch import make_client
from wheel_n_deal.llm import (
    PAGE_VIEW_CHARS,
    LLMVerdict,
    MiMo,
    format_verdict,
    parse_extraction,
    parse_verdict,
    trim_page,
    verdict_prompt,
)
from wheel_n_deal.store import Observation, Status

LLM = LLMConfig(base_url="https://llm.example/v1")
COMPLETIONS = "https://llm.example/v1/chat/completions"
KEY = "test-llm-key"
ANSWER = {
    "price": 42.5,
    "currency": "USD",
    "in_stock": True,
    "variant": "Large",
    "condition": "new",
    "list_price": 60.0,
    "blocked": False,
    "evidence": "Now $42.50",
}
PAGE = (
    "<html><head><title>Kettle | Shop</title>"
    '<meta property="og:title" content="Kettle">'
    '<meta name="viewport" content="width=device-width">'
    '<script type="application/ld+json">{"@type": "Product", "name": "Kettle"}</script>'
    "<script>var tracking = 1;</script><style>.x{}</style></head>"
    "<body><nav>Menu</nav><h1>Electric Kettle</h1><main><p>Now $42.50</p></main></body></html>"
)


def _completion(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


@pytest.fixture
async def client():
    async with make_client() as c:
        yield c


def test_trim_keeps_title_h1_json_ld_meta_and_text():
    view = trim_page(PAGE)
    assert "Kettle | Shop" in view
    assert "Electric Kettle" in view
    assert '"@type": "Product"' in view
    assert "og:title: Kettle" in view
    assert "Now $42.50" in view
    assert "tracking" not in view
    assert "viewport" not in view


def test_trim_caps_size_but_keeps_title_and_h1():
    huge = PAGE.replace("<p>Now $42.50</p>", "<p>" + "filler " * 10_000 + "</p>")
    huge = huge.replace('"name": "Kettle"', '"name": "' + "x" * 20_000 + '"')
    view = trim_page(huge)
    assert len(view) <= PAGE_VIEW_CHARS
    assert view.startswith("Title: Kettle | Shop\nH1: Electric Kettle\n")
    assert "filler" in view


@pytest.mark.parametrize(
    "content",
    [
        json.dumps(ANSWER),
        "```json\n" + json.dumps(ANSWER) + "\n```",
        "<think>the price is near the h1</think>\n" + json.dumps(ANSWER),
    ],
)
def test_parse_extraction_accepts_json(content):
    result = parse_extraction(content)
    assert result is not None
    assert (result.price, result.evidence, result.blocked) == (42.5, "Now $42.50", False)


@pytest.mark.parametrize(
    "content",
    [
        None,
        "the price is $42.50",
        json.dumps({k: v for k, v in ANSWER.items() if k != "evidence"}),
        json.dumps({**ANSWER, "extra": 1}),
        json.dumps({**ANSWER, "price": "$42.50"}),
        json.dumps({**ANSWER, "price": -1}),
    ],
)
def test_parse_extraction_rejects_invalid(content):
    assert parse_extraction(content) is None


async def test_extract_success_request_shape(client):
    mimo = MiMo(client, LLM, KEY)
    with respx.mock:
        route = respx.post(COMPLETIONS).respond(200, json=_completion(json.dumps(ANSWER)))
        result = await mimo.extract("https://shop.example/kettle", PAGE)
    assert result is not None and result.price == 42.5
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert request.headers["User-Agent"].startswith("wheel-n-deal/")
    assert request.extensions["timeout"]["read"] <= 90
    body = json.loads(request.content)
    assert body["model"] == "mimo-v2.6-flash"
    assert "Electric Kettle" in body["messages"][-1]["content"]


@pytest.mark.parametrize(
    "side_effect",
    [
        httpx.ReadTimeout("slow"),
        httpx.ConnectError("down"),
        httpx.Response(502),
        httpx.Response(200, json=_completion("not json at all")),
        httpx.Response(200, json={"error": "weird"}),
        httpx.Response(200, text="<html>gateway</html>"),
    ],
)
async def test_extract_failures_return_none(client, caplog, side_effect):
    mimo = MiMo(client, LLM, KEY)
    with respx.mock:
        respx.post(COMPLETIONS).mock(side_effect=[side_effect])
        assert await mimo.extract("https://shop.example/kettle", PAGE) is None
    assert KEY not in caplog.text


async def test_extract_without_key_skips_request(client):
    mimo = MiMo(client, LLM, None)
    with respx.mock:
        route = respx.post(COMPLETIONS)
        assert await mimo.extract("https://shop.example/kettle", PAGE) is None
    assert route.call_count == 0


async def test_extract_one_request_at_a_time(client):
    mimo = MiMo(client, LLM, KEY)
    in_flight = 0
    peak = 0

    async def slow_answer(request):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200, json=_completion(json.dumps(ANSWER)))

    with respx.mock:
        respx.post(COMPLETIONS).mock(side_effect=slow_answer)
        results = await asyncio.gather(*(mimo.extract("https://s.example", PAGE) for _ in range(3)))
    assert all(results)
    assert peak == 1


ITEM = WatchItem(url="https://shop.example/kettle", name="Kettle", target_price=50)
VERDICT = {"real_deal": False, "flags": ["inflated_list_price"], "reason": "Usually $43."}
HISTORY = [
    Observation(1, "2026-10-18T12:00:00+00:00", Status.OK, 42.5, "USD", True),
    Observation(1, "2026-10-11T12:00:00+00:00", Status.OK, 43.0, "USD", True),
    Observation(1, "2026-10-04T12:00:00+00:00", Status.BLOCKED, None, None, None),
]


@pytest.mark.parametrize(
    "content",
    [
        None,
        json.dumps({**VERDICT, "flags": ["cheap"]}),
        json.dumps({**VERDICT, "extra": 1}),
        json.dumps({k: v for k, v in VERDICT.items() if k != "reason"}),
    ],
)
def test_parse_verdict_rejects_invalid(content):
    assert parse_verdict(content) is None


def test_verdict_prompt_has_history_target_and_page():
    prompt = verdict_prompt(ITEM, 42.5, "USD", HISTORY, PAGE)
    assert "Kettle" in prompt and "target $50.00" in prompt
    assert "2026-10-11: $43.00" in prompt
    assert "2026-10-04" not in prompt
    assert "Electric Kettle" in prompt


@pytest.mark.parametrize(
    "verdict, expected",
    [
        (
            LLMVerdict(real_deal=True, flags=[], reason="Lowest seen."),
            "Verdict: real deal. Lowest seen.",
        ),
        (
            LLMVerdict(
                real_deal=False, flags=["refurbished_or_used", "membership_only"], reason="Meh."
            ),
            "Verdict: doubtful (refurbished or used, membership only). Meh.",
        ),
    ],
)
def test_format_verdict(verdict, expected):
    assert format_verdict(verdict) == expected


async def test_verdict_success(client):
    mimo = MiMo(client, LLM, KEY)
    with respx.mock:
        route = respx.post(COMPLETIONS).respond(200, json=_completion(json.dumps(VERDICT)))
        result = await mimo.verdict(ITEM, 42.5, "USD", HISTORY, PAGE)
    assert result == LLMVerdict(**VERDICT)
    assert (
        "2026-10-11: $43.00"
        in json.loads(route.calls.last.request.content)["messages"][-1]["content"]
    )


@pytest.mark.parametrize(
    "side_effect", [httpx.ConnectError("down"), httpx.Response(502), httpx.Response(200, json={})]
)
async def test_verdict_failures_return_none(client, side_effect):
    mimo = MiMo(client, LLM, KEY)
    with respx.mock:
        respx.post(COMPLETIONS).mock(side_effect=[side_effect])
        assert await mimo.verdict(ITEM, 42.5, "USD", HISTORY, PAGE) is None
