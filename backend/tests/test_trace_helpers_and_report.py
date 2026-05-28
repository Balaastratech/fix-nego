"""Smoke tests for the enriched trace pipeline and report renderer."""
import time
from pathlib import Path

import pytest

from app.utils.session_trace import SessionTrace
from app.utils.trace_helpers import (
    TraceTimer, model_block, model_route, text_preview,
    extract_token_usage, finish_reason, safe_record,
)


def test_model_block_minimal():
    mb = model_block("gemini-2.5-pro", route="api", purpose="ask_ai", timeout_s=3.0)
    assert mb == {
        "name": "gemini-2.5-pro",
        "route": "api",
        "purpose": "ask_ai",
        "timeout_s": 3.0,
    }


def test_model_route_returns_string():
    r = model_route()
    assert r in {"api", "vertex"}


def test_text_preview_truncates():
    txt = "a b c d " * 200
    out = text_preview(txt, limit=100)
    assert len(out) <= 100
    assert out.endswith("…")


def test_text_preview_empty():
    assert text_preview("") == ""
    assert text_preview(None) == ""


def test_extract_token_usage_handles_missing():
    class _R:
        usage_metadata = None
    assert extract_token_usage(_R()) == {}


def test_extract_token_usage_reads_fields():
    class _U:
        prompt_token_count = 100
        candidates_token_count = 50
        thoughts_token_count = 20
        total_token_count = 170

    class _R:
        usage_metadata = _U()

    out = extract_token_usage(_R())
    assert out["prompt_tokens"] == 100
    assert out["candidates_tokens"] == 50
    assert out["thoughts_tokens"] == 20
    assert out["total_tokens"] == 170


def test_finish_reason_extracts():
    class _C:
        finish_reason = "STOP"

    class _R:
        candidates = [_C()]

    assert finish_reason(_R()) == "STOP"


def test_finish_reason_missing():
    class _R:
        candidates = []
    assert finish_reason(_R()) is None


def test_safe_record_returns_none_when_no_trace():
    assert safe_record("nonexistent-session", category="x", name="y", summary="z") is None


def test_report_renders_conversation_summary_and_data(tmp_path: Path):
    trace = SessionTrace("smoke-1", root_dir=tmp_path)
    trace.record(
        category="transcript", name="stream_transcript_final",
        summary="hi", data={
            "speaker": "counterparty",
            "text": "Our Year 1 budget ceiling is $1,100,000.",
            "confidence": 0.92,
            "stt": {"provider": "deepgram", "model": "nova-3", "language": "en-US"},
        },
    )
    trace.record(
        category="ask_ai", name="question_text_ready",
        summary="ask", data={
            "question_text": "What now?",
            "question_chars": 9,
            "source": "gemini_live_input",
            "ask_shape": "vague",
            "native_audio": True,
        },
    )
    trace.record(
        category="ask_ai", name="pro_advice_completed",
        summary="pro done", data={
            "model": model_block("gemini-2.5-pro", route="api", purpose="ask_ai_pro_preflight"),
            "latency_ms": 1842,
            "advice_text": "Counter at $1.17M with Net-60, protect auto-renewal.",
            "advice_chars": 60,
            "tokens": {"prompt_tokens": 320, "candidates_tokens": 80, "total_tokens": 400},
            "finish_reason": "STOP",
        },
    )
    trace.record(
        category="ai", name="ai_response_completed",
        summary="live done", data={
            "context": "ask_ai",
            "model": model_block("gemini-live-2.5-flash-native-audio", route="api"),
            "response_text": "Say: I can offer $1.17M for Year 1 with Net-60.",
            "hold_to_response_ms": 2120,
        },
    )
    trace.record(
        category="vision", name="vision_analysis_completed",
        summary="vision", data={
            "model": model_block("gemini-2.5-flash", route="api", purpose="vision_analysis"),
            "latency_ms": 1100,
            "scene_type": "screen",
            "advice_hint": "Order form shows auto-renewal — protect this clause.",
            "prices_visible_count": 2,
            "terms_visible_count": 5,
        },
    )
    out_path = trace.finalize()
    text = out_path.read_text(encoding="utf-8")

    # Section headers present
    assert "## Conversation Summary" in text
    assert "## Event Counts by Category" in text
    assert "## Event Timeline (chronological)" in text

    # Conversation summary entries
    assert "COUNTERPARTY heard" in text
    assert "$1,100,000" in text
    assert "USER asked" in text
    assert "Pro pre-flight advice" in text
    assert "AI spoke" in text
    assert "Vision saw" in text

    # Detailed timeline shows full data — including long text rendered in fenced block
    assert "advice_text:" in text
    assert "response_text:" in text
    assert "Counter at $1.17M" in text
    assert "hold_to_response_ms" in text
    # Model block surfaces uniformly
    assert "gemini-2.5-pro" in text
    assert "gemini-live-2.5-flash-native-audio" in text
    assert "purpose" in text
    # STT attribution
    assert "deepgram" in text and "nova-3" in text


def test_trace_timer_emits_started_and_completed(tmp_path: Path):
    trace = SessionTrace("smoke-2", root_dir=tmp_path)
    # Inject this trace into the global registry so safe_record finds it.
    from app.utils import session_trace as st_mod
    st_mod._traces["smoke-2"] = trace
    try:
        with TraceTimer(
            "smoke-2",
            category="ask_ai",
            name="pro_advice",
            summary="x",
            started_data={"model": model_block("gemini-2.5-pro")},
        ) as t:
            time.sleep(0.01)
            t.complete(data={"advice_text": "hello", "advice_chars": 5})
    finally:
        st_mod._traces.pop("smoke-2", None)

    names = [e["name"] for e in trace._events]
    assert "pro_advice_started" in names
    assert "pro_advice_completed" in names
    completed = next(e for e in trace._events if e["name"] == "pro_advice_completed")
    assert completed["data"]["advice_text"] == "hello"
    assert completed["data"]["latency_ms"] >= 0


def test_trace_timer_fail_emits_failed_event(tmp_path: Path):
    trace = SessionTrace("smoke-3", root_dir=tmp_path)
    from app.utils import session_trace as st_mod
    st_mod._traces["smoke-3"] = trace
    try:
        with TraceTimer("smoke-3", category="ask_ai", name="pro_advice", summary="x") as t:
            t.fail(reason="empty_response")
    finally:
        st_mod._traces.pop("smoke-3", None)
    names = [e["name"] for e in trace._events]
    assert "pro_advice_started" in names
    assert "pro_advice_failed" in names
    failed = next(e for e in trace._events if e["name"] == "pro_advice_failed")
    assert failed["data"]["reason"] == "empty_response"
