"""Offline check: the Anthropic adapter works on the installed anthropic SDK.

Runs the real `_generate_anthropic` against the real SDK with an in-memory
HTTP transport (no network, no spend). Covers SDK 0.x (httpx) and >=1.0
(httpx2, `temperature` removed from messages.create).
"""

import json

import anthropic
import pytest

from app.providers import text_client

try:  # anthropic >=1.0 runs on httpx2; 0.x on httpx
    import httpx2 as hx
except ImportError:
    import httpx as hx


@pytest.fixture
def captured(monkeypatch, tmp_path):
    # the credit fence may keep usage locally; never in the repo's data folder
    monkeypatch.setenv("API_CREDIT_UNRECORDED_PATH", str(tmp_path / "unrecorded.jsonl"))
    requests: list[dict] = []

    def handler(request):
        requests.append(json.loads(request.content))
        return hx.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant",
            "model": requests[-1]["model"], "stop_reason": "end_turn",
            "stop_sequence": None,
            "content": [{"type": "text", "text": " ok "}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        })

    real_init = anthropic.AsyncAnthropic.__init__

    def init(self, *args, **kwargs):
        kwargs["http_client"] = hx.AsyncClient(transport=hx.MockTransport(handler))
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(anthropic.AsyncAnthropic, "__init__", init)
    return requests


async def _call(model, images=None):
    return await text_client._generate_anthropic(
        model, "sk-ant-test-placeholder", "sys", "hello", images, "image/png",
        True, 0.2, 64, 5.0,
    )


async def test_temperature_sent_to_models_that_accept_it(captured):
    assert await _call("claude-haiku-4-5") == "ok"
    body = captured[0]
    assert body["temperature"] == 0.2
    assert body["system"] == "sys"
    assert body["max_tokens"] == 64


async def test_temperature_omitted_for_models_that_reject_it(captured):
    assert await _call("claude-opus-4-8") == "ok"
    assert "temperature" not in captured[0]


async def test_vision_request_shape(captured):
    assert await _call("claude-sonnet-4-6", images=[b"\x89PNG"]) == "ok"
    image, text = captured[0]["messages"][0]["content"]
    assert image["type"] == "image" and image["source"]["media_type"] == "image/png"
    assert text["type"] == "text"


@pytest.mark.parametrize("model, ok", [
    ("claude-haiku-4-5", True),
    ("claude-haiku-4-5-20251001", True),
    ("claude-sonnet-4-6", True),
    ("claude-opus-4-6", True),
    ("claude-sonnet-4-20250514", True),
    ("claude-opus-4-1-20250805", True),
    ("claude-3-7-sonnet-20250219", True),
    ("claude-3-5-haiku-latest", True),
    ("claude-opus-4-7", False),
    ("claude-opus-4-8", False),
    ("claude-sonnet-5", False),
    ("claude-sonnet-5-5", False),
    ("claude-haiku-5-5", False),
    ("claude-opus-5-5", False),
    ("claude-fable-5-1", False),
])
def test_temperature_allow_list(model, ok):
    assert text_client._anthropic_accepts_temperature(model) is ok
