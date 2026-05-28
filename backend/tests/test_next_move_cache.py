"""Tests for next_move_cache: classifier, freshness, and brief formatting."""
import time
import pytest

from app.config import settings
from app.services import next_move_cache as nm


def test_classify_short_asks_are_vague():
    for q in [
        "what now",
        "What now?",
        "say what",
        "trap",
        "Trap?",
        "accept",
        "can I accept?",
        "best counter",
        "risk?",
        "summarize",
        "next move",
        "trade what",
        "protect what",
        "read this",
    ]:
        assert nm.classify_ask(q) == "vague", f"expected vague for {q!r}"


def test_classify_detailed_prompts_are_precise():
    long = (
        "Look at my shared screen. Extract the exact renewal ARR, term length, "
        "payment terms, auto-renewal notice period, uplift cap, and SLA level "
        "from the order form. Then tell me which terms are strategically sensitive."
    )
    assert nm.classify_ask(long) == "precise"
    medium = (
        "Audit the package I just offered and identify any hidden concession I gave."
    )
    assert nm.classify_ask(medium) == "precise"


def test_format_for_brief_empty_when_no_cache():
    assert nm.format_for_brief({}) == ""
    assert nm.format_for_brief(None) == ""


def test_format_for_brief_renders_when_fresh():
    cache = {
        "text": "Counter at $1.17M with Net-60.",
        "generated_at": time.time(),
        "is_pro": True,
        "context_basis_hash": "abc",
    }
    out = nm.format_for_brief(cache)
    assert "[RECOMMENDED NEXT MOVE" in out
    assert "Counter at $1.17M" in out
    assert "tier=pro" in out


def test_format_for_brief_skips_when_stale():
    cache = {
        "text": "stale",
        "generated_at": time.time() - (settings.NEXT_MOVE_MAX_AGE_SECONDS + 5),
        "is_pro": False,
        "context_basis_hash": "abc",
    }
    assert nm.format_for_brief(cache) == ""


def test_format_for_brief_skips_empty_text():
    cache = {
        "text": "",
        "generated_at": time.time(),
        "is_pro": False,
        "context_basis_hash": "abc",
    }
    assert nm.format_for_brief(cache) == ""


class _FakeListener:
    def __init__(self, transcript="", ctx=None):
        self.accumulated_transcript = transcript
        self.last_context = ctx or {}


class _FakeSession:
    def __init__(self, **kw):
        self.session_id = "test-sess"
        self.listener_agent = kw.get("listener")
        self.vision_observations = kw.get("vision", [])
        self.next_move_cache = kw.get("cache", {})
        self.next_move_last_refresh_at = kw.get("last_refresh", 0.0)
        self.next_move_task = None


def test_should_refresh_respects_disable(monkeypatch):
    monkeypatch.setattr(settings, "NEXT_MOVE_CACHE_ENABLED", False)
    s = _FakeSession(listener=_FakeListener("hello", {}))
    assert nm.should_refresh_cache(s) is False


def test_should_refresh_blocked_by_debounce(monkeypatch):
    monkeypatch.setattr(settings, "NEXT_MOVE_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "NEXT_MOVE_BACKGROUND_DEBOUNCE_MS", 2000)
    s = _FakeSession(
        listener=_FakeListener("hello", {}),
        last_refresh=time.time(),  # just refreshed
    )
    assert nm.should_refresh_cache(s) is False


def test_should_refresh_skips_when_basis_unchanged(monkeypatch):
    monkeypatch.setattr(settings, "NEXT_MOVE_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "NEXT_MOVE_BACKGROUND_DEBOUNCE_MS", 0)
    listener = _FakeListener("transcript A", {"item": "X"})
    s = _FakeSession(listener=listener)
    basis = nm._context_basis_hash(s)
    s.next_move_cache = {
        "text": "x",
        "generated_at": time.time(),
        "context_basis_hash": basis,
        "is_pro": False,
    }
    assert nm.should_refresh_cache(s) is False


def test_should_refresh_fires_when_basis_changes(monkeypatch):
    monkeypatch.setattr(settings, "NEXT_MOVE_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "NEXT_MOVE_BACKGROUND_DEBOUNCE_MS", 0)
    listener = _FakeListener("transcript A", {"item": "X"})
    s = _FakeSession(listener=listener)
    s.next_move_cache = {
        "text": "x",
        "generated_at": time.time(),
        "context_basis_hash": "different-hash",
        "is_pro": False,
    }
    assert nm.should_refresh_cache(s) is True


def test_pre_query_brief_includes_next_move_when_supplied():
    from app.ai_assets import build_pre_query_brief
    block = nm.format_for_brief({
        "text": "Counter at $1.17M.",
        "generated_at": time.time(),
        "is_pro": False,
        "context_basis_hash": "h",
    })
    brief = build_pre_query_brief(
        context={"item": "Renewal", "negotiation_type": "saas_renewal"},
        market_info="benchmark",
        transcript_text="...",
        vision_observation=None,
        next_move_block=block,
    )
    assert "[RECOMMENDED NEXT MOVE" in brief
    assert "Counter at $1.17M." in brief


def test_pre_query_brief_omits_next_move_when_none():
    from app.ai_assets import build_pre_query_brief
    brief = build_pre_query_brief(
        context={"item": "Renewal", "negotiation_type": "saas_renewal"},
        market_info="benchmark",
        transcript_text="...",
        vision_observation=None,
        next_move_block=None,
    )
    assert "[RECOMMENDED NEXT MOVE" not in brief
