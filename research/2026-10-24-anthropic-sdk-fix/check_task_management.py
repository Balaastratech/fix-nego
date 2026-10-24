"""Offline check of the task-management project's two Claude calls on the installed SDK.

Sends the same keyword arguments its app/routes/ai.py uses, with the patched model,
through the real AsyncAnthropic client over an in-memory transport. No network, no spend.
Usage: python check_task_management.py
"""

import asyncio
import json

import anthropic

try:  # anthropic >=1.0 runs on httpx2; 0.x on httpx
    import httpx2 as hx
except ImportError:
    import httpx as hx

MODEL = "claude-haiku-4-5"
sent: list[dict] = []


def handler(request):
    sent.append(json.loads(request.content))
    return hx.Response(200, json={
        "id": "msg_test", "type": "message", "role": "assistant", "model": MODEL,
        "stop_reason": "end_turn", "stop_sequence": None,
        "content": [{"type": "text", "text": "[]"}],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    })


async def main():
    client = anthropic.AsyncAnthropic(
        api_key="sk-ant-test-placeholder",
        http_client=hx.AsyncClient(transport=hx.MockTransport(handler)),
    )
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
    assert [b["max_tokens"] for b in sent] == [1024, 500]
    assert all(b["model"] == MODEL and "temperature" not in b for b in sent)
    print(f"PASS anthropic {anthropic.__version__}: 2 offline requests, shapes as expected")


asyncio.run(main())
