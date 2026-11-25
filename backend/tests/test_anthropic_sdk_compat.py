"""Offline check: the Anthropic adapter works on the installed anthropic SDK.

Runs the real `_generate_anthropic` against the real SDK, no network, no spend:
- only the network layer is faked (the httpx/httpx2 transport), so the SDK still
  builds its own default HTTP client (catches e.g. anthropic <0.40 + httpx 0.28,
  which crashes on the removed `proxies` argument);
- the fake server enforces the API rules the adapter must respect, by the
  `anthropic-version` header the SDK sends: on 2026-10-21 (SDK >=2.0) any
  temperature/top_p/top_k is a 400 on every model; on any version, models
  that take only default sampling (Opus 4.7+, 5.x) reject temperature.
Covers SDK 0.x (httpx, 2023-06-01), 1.x (httpx2, 2023-06-01) and 2.x (2026-10-21).
"""

import json
import re

import pytest

from app.providers import text_client

try:  # anthropic >=1.0 runs on httpx2; 0.x on httpx
    import httpx2 as hx
except ImportError:
    import httpx as hx

SAMPLING = ("temperature", "top_p", "top_k")
# The server's own list (independent of the adapter's allow-list).
DEFAULT_SAMPLING_ONLY = re.compile(r"^claude-(opus-4-[789]|(opus|sonnet|haiku|fable|mythos)-5)")


def _error(message):
    return hx.Response(400, json={"type": "error", "error": {
        "type": "invalid_request_error", "message": message}})


@pytest.fixture
def captured(monkeypatch):
    requests: list[dict] = []

    def handler(request):
        body = json.loads(request.content)
        version = request.headers.get("anthropic-version", "")
        requests.append({"body": body, "version": version})
        sent = [k for k in SAMPLING if k in body]
        if sent and version != "2023-06-01":
            return _error(f"{sent} not supported on API version {version}")
        if "temperature" in body and DEFAULT_SAMPLING_ONLY.match(body["model"]):
            return _error(f"temperature is not supported for {body['model']}")
        return hx.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant",
            "model": body["model"], "stop_reason": "end_turn",
            "stop_sequence": None,
            "content": [{"type": "text", "text": " ok "}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        })

    real_init = hx.AsyncClient.__init__

    def init(self, *args, **kwargs):
        kwargs["transport"] = hx.MockTransport(handler)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(hx.AsyncClient, "__init__", init)
    return requests


async def _call(model, images=None):
    return await text_client._generate_anthropic(
        model, "sk-ant-fake-test-placeholder", "sys", "hello", images, "image/png",
        True, 0.2, 64, 5.0,
    )


async def test_older_model_call_succeeds_on_this_sdk(captured):
    assert await _call("claude-haiku-4-5") == "ok"
    req = captured[0]
    assert req["body"]["system"] == "sys"
    assert req["body"]["max_tokens"] == 64
    # Temperature only where the API version still takes it.
    assert ("temperature" in req["body"]) is (req["version"] == "2023-06-01")
    if req["version"] == "2023-06-01":
        assert req["body"]["temperature"] == 0.2


async def test_temperature_omitted_for_models_that_reject_it(captured):
    assert await _call("claude-opus-4-8") == "ok"
    assert not any(k in captured[0]["body"] for k in SAMPLING)


async def test_vision_request_shape(captured):
    assert await _call("claude-sonnet-4-6", images=[b"\x89PNG"]) == "ok"
    image, text = captured[0]["body"]["messages"][0]["content"]
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


class _Client:
    def __init__(self, headers):
        self.default_headers = headers


@pytest.mark.parametrize("headers, model, sends", [
    ({"anthropic-version": "2023-06-01"}, "claude-haiku-4-5", True),
    ({"anthropic-version": "2026-10-21"}, "claude-haiku-4-5", False),
    ({}, "claude-haiku-4-5", False),  # unknown version: treated as new
    ({"anthropic-version": "2023-06-01"}, "claude-opus-4-8", False),
])
def test_temperature_follows_api_version(headers, model, sends):
    assert text_client._anthropic_sends_temperature(_Client(headers), model) is sends
