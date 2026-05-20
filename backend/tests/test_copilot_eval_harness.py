import json
from unittest.mock import AsyncMock, Mock

import pytest

from app.config import settings
from app.models.negotiation import NegotiationSession
from app.services.connection_manager import ConnectionManager
from app.services.gemini_client import _append_ai_response_text, _consume_completed_ai_response, _session_text_accumulators
from app.services.gemini_client import build_advisor_query
from app.services.negotiation_engine import NegotiationEngine
from app.services.response_validator import ResponseValidator
from scripts import run_copilot_eval
from scripts.run_copilot_eval import (
    _extract_context_number,
    _wait_for_negotiation_end,
    build_failed_pair,
    build_scenario_failure_result,
    score_pair,
)


@pytest.mark.asyncio
async def test_simulated_turn_rejected_when_eval_mode_disabled(monkeypatch):
    monkeypatch.setattr(settings, "EVAL_MODE_ENABLED", False)
    websocket = AsyncMock()
    websocket.send_json = AsyncMock()
    session = NegotiationSession(session_id="eval-disabled")
    session.listener_agent = Mock()

    await NegotiationEngine.handle_simulated_negotiation_turn(
        session,
        {"speaker": "user", "text": "I can close at 80."},
        websocket,
    )

    websocket.send_json.assert_awaited_once()
    message = websocket.send_json.await_args.args[0]
    assert message["type"] == "ERROR"
    assert message["payload"]["code"] == "EVAL_MODE_DISABLED"
    session.listener_agent.ingest_simulated_turn.assert_not_called()


@pytest.mark.asyncio
async def test_roleplay_consent_disables_session_resume():
    websocket = AsyncMock()
    websocket.send_json = AsyncMock()
    session = NegotiationSession(session_id="roleplay-consent")

    await NegotiationEngine.handle_consent(
        session,
        {"version": "eval-1", "mode": "roleplay"},
        websocket,
    )

    assert session.session_resumable is False


@pytest.mark.asyncio
async def test_connection_cleanup_stops_listener_agent():
    manager = ConnectionManager()
    listener_agent = Mock()
    listener_agent.stop = AsyncMock()
    session = NegotiationSession(session_id="cleanup-listener")
    session.listener_agent = listener_agent

    await manager._finalize_session_cleanup(session)

    listener_agent.stop.assert_awaited_once()
    assert session.listener_agent is None


@pytest.mark.asyncio
async def test_simulated_turn_injected_when_eval_mode_enabled(monkeypatch):
    monkeypatch.setattr(settings, "EVAL_MODE_ENABLED", True)
    websocket = AsyncMock()
    websocket.send_json = AsyncMock()
    listener_agent = Mock()
    listener_agent.ingest_simulated_turn = AsyncMock(
        return_value={
            "id": "turn-1",
            "speaker": "counterparty",
            "scenario_id": "scenario-1",
        }
    )
    session = NegotiationSession(session_id="eval-enabled")
    session.listener_agent = listener_agent

    await NegotiationEngine.handle_simulated_negotiation_turn(
        session,
        {
            "speaker": "counterparty",
            "text": "I can move to 84 with standard terms.",
            "scenario_id": "scenario-1",
            "turn_id": "turn-1",
        },
        websocket,
    )

    listener_agent.ingest_simulated_turn.assert_awaited_once()
    websocket.send_json.assert_awaited_once()
    message = websocket.send_json.await_args.args[0]
    assert message["type"] == "SIMULATED_TURN_ACCEPTED"
    assert message["payload"]["id"] == "turn-1"


def test_advisor_query_contains_quality_rules_and_live_deal_state():
    query = build_advisor_query(
        state={
            "item": "SaaS renewal",
            "seller_price": "88",
            "target_price": "80",
            "max_price": "82",
            "response_language": "en-US",
        },
        transcript="User: My target is 80.\nCounterparty: I can do 88.",
        user_query="Should I close or counter?",
    )

    assert "ANSWER QUALITY RULES" in query
    assert "LIVE DEAL-STATE BRIEF" in query
    assert "latest offer" in query
    assert "target/cap" in query
    assert "MY REQUEST: Should I close or counter?" in query


def test_advisor_query_brief_names_active_protection_terms():
    query = build_advisor_query(
        state={"item": "SaaS renewal", "target_price": "80", "max_price": "82"},
        transcript=(
            "User: I can take eighty two only with price lock, onboarding, "
            "service credits, net sixty, and no auto-renewal.\n"
            "Counterparty: Eighty two is harder, and I need to narrow what is included."
        ),
        user_query="Which term should I trade last and which should I trade first?",
    )

    assert "Active named terms/protections" in query
    assert "price lock" in query
    assert "service credits" in query
    assert "no auto-renewal" in query


def test_eval_runner_extracts_target_and_cap_without_using_first_context_number():
    context = (
        "The user is buying a 120-seat SaaS renewal. "
        "User target is 80000 and cap is 82000 only with key protections."
    )

    assert _extract_context_number(context, "target") == "80000"
    assert _extract_context_number(context, "cap") == "82000"


def test_eval_scoring_normalizes_currency_k_suffixes_and_terms():
    scenario = {
        "must_track_numbers": ["195000", "35000", "80000"],
        "must_track_terms": ["sign-on", "equity", "net 60", "no auto-renewal"],
    }
    pair = {
        "query": "Give me one sentence that asks for equity and sign-on.",
        "expected_direction": "Ask for 195 base, 35 sign-on, and 80 equity while preserving no auto renewal.",
        "response": "Say: 'At $195k base, can you meet $35k sign-on and $80k equity, while keeping no auto-renewal?'",
    }

    result = score_pair(scenario, pair)

    assert result["checks"]["number_grounding"] == 1.0
    assert result["checks"]["term_grounding"] == 1.0


def test_eval_scoring_normalizes_spoken_number_words_and_payment_terms():
    scenario = {
        "must_track_numbers": ["88000", "82000", "80000"],
        "must_track_terms": ["net 60"],
    }
    pair = {
        "query": "Should I take their eighty offer instead of net sixty?",
        "expected_direction": "Recognize 80 as achieved and net 60 as the payment trade.",
        "response": "Accept the eighty thousand dollar offer; the only concession is standard payment terms.",
    }

    result = score_pair(scenario, pair)

    assert result["number_hits"] == ["80000"]
    assert result["term_hits"] == ["net 60"]


def test_response_validator_allows_question_inside_quoted_command():
    result = ResponseValidator.validate_response(
        'Ask: "Given the flexibility on equity you mentioned, could we explore increasing that and the sign-on bonus to bridge the gap?"'
    )

    assert result["valid"] is True
    assert result["violations"] == []


def test_response_validator_still_rejects_unquoted_question_and_vague_language():
    result = ResponseValidator.validate_response(
        "You could perhaps ask whether they can increase the equity?"
    )

    assert result["valid"] is False
    assert "VAGUE_LANGUAGE" in result["violations"]
    assert any(v.startswith("CONTAINS_QUESTIONS:") for v in result["violations"])
    assert ResponseValidator.should_send_correction(result["violations"]) is True


def test_ai_response_text_parts_are_consumed_when_no_output_transcription():
    session = NegotiationSession(session_id="text-parts-only")

    _append_ai_response_text(session, "Say:")
    _append_ai_response_text(session, '"Hold at 61 only if warranty delivery and replacement terms are clear."')

    result = _consume_completed_ai_response(session, session.session_id)

    assert "Hold at 61" in result
    assert getattr(session, "current_ai_response", "") == ""


def test_ai_response_consume_dedupes_text_parts_and_output_transcription():
    session = NegotiationSession(session_id="text-dedupe")
    session.current_ai_response = 'Say: "Hold at 61 only if warranty delivery and replacement terms are clear."'
    _session_text_accumulators[session.session_id] = 'Say: "Hold at 61 only if warranty delivery and replacement terms are clear."'

    result = _consume_completed_ai_response(session, session.session_id)

    assert result == 'Say: "Hold at 61 only if warranty delivery and replacement terms are clear."'


def test_build_failed_pair_includes_diagnostic_and_zero_score():
    scenario = {"must_track_numbers": ["61000"], "must_track_terms": ["warranty"]}
    query = {"text": "Give me one sentence.", "expected_direction": "Protect warranty."}
    events = [{"type": "AI_THINKING", "payload": {}}]

    pair = build_failed_pair(scenario, query, 6, "command", TimeoutError("Timed out waiting for AI response"), events)

    assert pair["error"].startswith("TimeoutError:")
    assert pair["deterministic_score"]["score"] == 0.0
    assert pair["diagnostic"]["recent_event_counts"]["AI_THINKING"] == 1


def test_build_scenario_failure_result_preserves_partial_pairs():
    scenario = {"id": "s1", "title": "Scenario", "family": "test"}
    ai_pairs = [{"deterministic_score": {"score": 0.5}}]
    result = build_scenario_failure_result(
        scenario=scenario,
        session_id="sess-1",
        events=[{"type": "AI_THINKING", "payload": {}}],
        ai_pairs=ai_pairs,
        error="TimeoutError: Timed out waiting for AI response",
        stage="query_after_turn_2",
    )

    assert result["error"].startswith("TimeoutError:")
    assert result["failure_stage"] == "query_after_turn_2"
    assert result["summary"]["query_count"] == 1


@pytest.mark.asyncio
async def test_wait_for_negotiation_end_requires_outcome_and_idle():
    class FakeWS:
        def __init__(self):
            self._messages = iter([
                json.dumps({"type": "OUTCOME_SUMMARY", "payload": {"deal_reached": False}}),
                json.dumps({
                    "type": "NEGOTIATION_STATE_CHANGED",
                    "payload": {"previous_state": "ENDING", "current_state": "IDLE"},
                }),
            ])

        async def recv(self):
            return next(self._messages)

    events = []
    await _wait_for_negotiation_end(FakeWS(), events, timeout=0.5)

    assert [event["type"] for event in events] == ["OUTCOME_SUMMARY", "NEGOTIATION_STATE_CHANGED"]


@pytest.mark.asyncio
async def test_run_scenario_defers_judging_until_after_socket_closes(monkeypatch):
    scenario = {
        "id": "scenario-1",
        "title": "Test deal",
        "family": "test",
        "context": "Target is 80 and cap is 82.",
        "turns": [{"speaker": "user", "text": "My target is 80."}],
        "queries": [{"after_turn": 1, "mode": "advice", "text": "What should I do next?"}],
    }
    events = iter([
        {"type": "CONNECTION_ESTABLISHED", "payload": {"session_id": "s1"}},
        {"type": "CONSENT_ACKNOWLEDGED", "payload": {}},
        {"type": "SESSION_STARTED", "payload": {}},
        {"type": "SIMULATED_TURN_ACCEPTED", "payload": {}},
    ])
    call_order: list[str] = []

    class FakeSocket:
        async def __aenter__(self):
            call_order.append("ws_enter")
            return self

        async def __aexit__(self, exc_type, exc, tb):
            call_order.append("ws_exit")

        async def send(self, payload):
            call_order.append("ws_send")

        async def recv(self):
            return json.dumps(next(events))

    async def fake_drain(*args, **kwargs):
        call_order.append("drain")

    async def fake_wait_for_ai_response(*args, **kwargs):
        call_order.append("wait_ai_response")
        return {
            "type": "TRANSCRIPT_UPDATE",
            "payload": {"speaker": "ai", "text": "Say: 'Hold at 80.'", "timestamp": 1, "response_mode": "advice"},
        }

    async def fake_wait_for_ai_idle(*args, **kwargs):
        call_order.append("wait_ai_idle")

    def fake_judge_pair(*args, **kwargs):
        call_order.append("judge")
        return {"average": 1.0, "passed": True, "scores": {}}

    monkeypatch.setattr(run_copilot_eval.websockets, "connect", lambda *args, **kwargs: FakeSocket())
    monkeypatch.setattr(run_copilot_eval, "_drain_until_quiet", fake_drain)
    monkeypatch.setattr(run_copilot_eval, "_wait_for_ai_response", fake_wait_for_ai_response)
    monkeypatch.setattr(run_copilot_eval, "_wait_for_ai_idle", fake_wait_for_ai_idle)
    monkeypatch.setattr(run_copilot_eval, "judge_pair", fake_judge_pair)

    result = await run_copilot_eval.run_scenario(
        ws_url="ws://test/ws",
        scenario=scenario,
        query_timeout=1.0,
        turn_delay=0.1,
        judge=True,
    )

    assert result["ai_pairs"][0]["judge"]["passed"] is True
    assert "ws_exit" in call_order
    assert call_order.index("ws_exit") < call_order.index("judge")


@pytest.mark.asyncio
async def test_ask_advice_includes_response_mode_signal():
    websocket = AsyncMock()
    websocket.send_json = AsyncMock()
    live_session = Mock()
    live_session.send = AsyncMock()
    listener_agent = Mock()
    listener_agent.last_context = {
        "item": "SaaS renewal",
        "seller_price": "88",
        "user_target_price": "80",
        "user_walk_away_price": "82",
    }
    listener_agent.accumulated_transcript = (
        "User: My target is 80.\n"
        "Counterparty: I can likely move this to 88 with standard terms."
    )
    listener_agent.force_immediate_cycle = Mock()

    session = NegotiationSession(session_id="ask-advice-mode")
    session.live_session = live_session
    session.listener_agent = listener_agent
    session.user_context = {"target_price": "80", "max_price": "82"}

    await NegotiationEngine.handle_ask_advice(
        session,
        {
            "response_mode": "advice",
            "query": "What should I do with their 88 offer?",
        },
        websocket,
    )

    sent_query = live_session.send.await_args.kwargs["input"]
    assert "[SYSTEM: ADVICE MODE ACTIVE]" in sent_query
    assert "What should I do with their 88 offer?" in sent_query
