"""Every Anthropic call goes through the API credit fence (DEC-20261103-API-CREDIT-ADAPTIVE).

Fake client only: no network, no real key, no spend. The fence is either a small
stand-in written to a temp MC_HOME, Mission Control's real api_credit.py (skipped
when it is not on this machine; its ledger goes to a throwaway folder under tests),
or absent (a deployed server).
"""

import json
import os
import textwrap
from pathlib import Path
from types import SimpleNamespace

import anthropic
import pytest

from app.providers import credit_fence, runtime_config, text_client

FAKE_FENCE = textwrap.dedent('''
    import json, os
    LOG = os.environ["FAKE_FENCE_LOG"]
    class Refused(RuntimeError):
        pass
    def _log(*row):
        with open(LOG, "a") as f:
            f.write(json.dumps(row, default=str) + "\\n")
    def estimate(model, kwargs):
        return 0.01
    def hold(category, who, model, usd):
        if os.environ.get("FAKE_FENCE_REFUSE"):
            raise Refused("credit used up")
        _log("hold", category, who, model, usd)
        return 7
    def settle(hold_id, model, usage, failed=False):
        u = usage if isinstance(usage, dict) else (vars(usage) if usage is not None else None)
        _log("settle", hold_id, model, u, failed)
''')

USAGE = {"input_tokens": 1234, "output_tokens": 56,
         "cache_creation_input_tokens": 7, "cache_read_input_tokens": 8}


class FakeAsyncAnthropic:
    """Stands in for anthropic.AsyncAnthropic; counts calls, never touches the network."""
    calls: list[dict] = []
    fail = False

    def __init__(self, *args, **kwargs):
        self.messages = self

    async def create(self, **kwargs):
        FakeAsyncAnthropic.calls.append(kwargs)
        if FakeAsyncAnthropic.fail:
            raise RuntimeError("boom")
        return SimpleNamespace(
            model=kwargs["model"],
            content=[SimpleNamespace(type="text", text=" ok ")],
            usage=SimpleNamespace(**USAGE),
        )


@pytest.fixture
def fake_client(monkeypatch):
    FakeAsyncAnthropic.calls = []
    FakeAsyncAnthropic.fail = False
    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeAsyncAnthropic)
    return FakeAsyncAnthropic


@pytest.fixture
def fake_fence(tmp_path, monkeypatch):
    bridge = tmp_path / "mc" / "voice" / "bridge"
    bridge.mkdir(parents=True)
    (bridge / "api_credit.py").write_text(FAKE_FENCE)
    log = tmp_path / "fence.log"
    monkeypatch.setenv("MC_HOME", str(tmp_path / "mc"))
    monkeypatch.setenv("FAKE_FENCE_LOG", str(log))
    monkeypatch.setenv("API_CREDIT_UNRECORDED_PATH", str(tmp_path / "unrecorded.jsonl"))
    monkeypatch.delenv("FAKE_FENCE_REFUSE", raising=False)
    return lambda: [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []


@pytest.fixture
def no_fence(tmp_path, monkeypatch):
    monkeypatch.setenv("MC_HOME", str(tmp_path / "no-mission-control-here"))
    out = tmp_path / "unrecorded.jsonl"
    monkeypatch.setenv("API_CREDIT_UNRECORDED_PATH", str(out))
    return out


async def _generate(model="claude-sonnet-4-6"):
    return await text_client._generate_anthropic(
        model, "fake-test-credential", "sys", "hello", None, "image/png",
        False, 0.2, 64, 5.0,
    )


async def test_refused_call_never_reaches_the_client(fake_client, fake_fence, monkeypatch):
    monkeypatch.setenv("FAKE_FENCE_REFUSE", "1")
    with pytest.raises(credit_fence.Refused, match="credit used up"):
        await _generate()
    assert fake_client.calls == []


async def test_allowed_call_records_the_real_usage(fake_client, fake_fence):
    assert await _generate("claude-haiku-4-5") == "ok"
    assert len(fake_client.calls) == 1
    hold, settle = fake_fence()
    assert hold[:4] == ["hold", "product", "negotiation-copilot", "claude-haiku-4-5"]
    assert settle == ["settle", 7, "claude-haiku-4-5", USAGE, False]


async def test_failed_call_settles_at_zero(fake_client, fake_fence):
    fake_client.fail = True
    with pytest.raises(RuntimeError, match="boom"):
        await _generate()
    assert fake_fence()[-1] == ["settle", 7, "claude-sonnet-4-6", None, True]


async def test_session_own_key_skips_the_team_credit(fake_client, fake_fence, monkeypatch):
    token = runtime_config._session_overrides.set({"keys": {"anthropic": "sk-ant-their-own"}})
    try:
        assert await _generate() == "ok"
    finally:
        runtime_config._session_overrides.reset(token)
    assert len(fake_client.calls) == 1
    assert fake_fence() == []


async def test_no_fence_product_call_goes_ahead_and_is_kept_locally(fake_client, no_fence):
    assert await _generate("claude-opus-4-8") == "ok"
    rows = [json.loads(x) for x in no_fence.read_text().splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert {k: row[k] for k in ("category", "who", "model", "input", "output", "cache_write", "cache_read")} == {
        "category": "product", "who": "negotiation-copilot", "model": "claude-opus-4-8",
        "input": 1234, "output": 56, "cache_write": 7, "cache_read": 8}
    assert "at" in row
    assert "sk-ant" not in no_fence.read_text()  # never a key


@pytest.mark.parametrize("category", ["demo", "internal", "planner"])
async def test_no_fence_non_product_call_is_refused(fake_client, no_fence, category):
    with pytest.raises(credit_fence.Refused, match="unreachable"):
        await credit_fence.create(FakeAsyncAnthropic(), category=category,
                                  model="claude-sonnet-4-6", max_tokens=10, messages=[])
    assert fake_client.calls == []
    assert not no_fence.exists()


REAL_MC = Path(os.environ.get("MC_HOME") or r"C:\Balaastra\MISSION-CONTROL")


@pytest.mark.skipif(not (REAL_MC / "voice" / "bridge" / "api_credit.py").is_file(),
                    reason="Mission Control's credit fence is not on this machine")
async def test_real_fence_ledger_gets_the_real_usage(fake_client, monkeypatch, tmp_path):
    monkeypatch.setenv("MC_HOME", str(REAL_MC))
    monkeypatch.setenv("API_CREDIT_UNRECORDED_PATH", str(tmp_path / "unrecorded.jsonl"))
    fence = credit_fence._fence()
    assert fence is not None
    # under pytest the fence's ledger lives in a throwaway folder, never the live one
    assert ".mc-voice" not in str(fence.ledger_dir())  # live-path-ok: asserts the ledger is not the live folder
    assert await _generate("claude-sonnet-4-6") == "ok"
    import sqlite3
    db = fence.ledger_dir() / f"{fence.cycle().key}.db"
    with sqlite3.connect(db) as c:
        row = c.execute("SELECT category, who, model, input, output, cache_write, cache_read, status "
                        "FROM calls ORDER BY id DESC LIMIT 1").fetchone()
    assert row == ("product", "negotiation-copilot", "claude-sonnet-4-6", 1234, 56, 7, 8, "done")
    assert not (tmp_path / "unrecorded.jsonl").exists()
