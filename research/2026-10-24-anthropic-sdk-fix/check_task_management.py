"""Offline check of the task-management project's two Claude calls on the installed SDK.

Sends the same keyword arguments its app/routes/ai.py uses, with the patched model,
through the real AsyncAnthropic client, built the way that app builds it (no custom
http_client), with only the network layer faked. The fake server enforces the API
version rule: on 2026-10-21 (SDK >=2.0) temperature/top_p/top_k are a 400.
No network, no spend. Usage: python check_task_management.py
"""

import asyncio
import json

try:  # anthropic >=1.0 runs on httpx2; 0.x on httpx
    import httpx2 as hx
except ImportError:
    import httpx as hx

MODEL = "claude-haiku-4-5"
sent: list[dict] = []


def handler(request):
    body = json.loads(request.content)
    version = request.headers.get("anthropic-version", "")
    sent.append({"body": body, "version": version})
    if version != "2023-06-01" and any(k in body for k in ("temperature", "top_p", "top_k")):
        return hx.Response(400, json={"type": "error", "error": {
            "type": "invalid_request_error", "message": f"sampling not supported on {version}"}})
    return hx.Response(200, json={
        "id": "msg_test", "type": "message", "role": "assistant", "model": MODEL,
        "stop_reason": "end_turn", "stop_sequence": None,
        "content": [{"type": "text", "text": "[]"}],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    })


_real_init = hx.AsyncClient.__init__


def _init(self, *args, **kwargs):
    kwargs["transport"] = hx.MockTransport(handler)
    _real_init(self, *args, **kwargs)


hx.AsyncClient.__init__ = _init

import anthropic  # noqa: E402  (after the transport patch, like the app's import-time client)


async def main():
    client = anthropic.AsyncAnthropic(api_key="sk-ant-test-placeholder")  # as app/routes/ai.py
    gen = await client.messages.create(  # generate_tasks
        model=MODEL, max_tokens=1024, system="sys",
        messages=[{"role": "user", "content": "Goal: x"}],
    )
    chat = await client.messages.create(  # chat_with_ai
        model=MODEL, max_tokens=500, system="sys",
        messages=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"},
                  {"role": "user", "content": "help"}],
    )
    assert json.loads(gen.content[0].text) == []
    assert chat.content[0].text == "[]"
    assert [r["body"]["max_tokens"] for r in sent] == [1024, 500]
    assert all(r["body"]["model"] == MODEL and "temperature" not in r["body"] for r in sent)
    print(f"PASS anthropic {anthropic.__version__} (API {sent[0]['version']}): "
          "2 offline requests, shapes as expected")


asyncio.run(main())
