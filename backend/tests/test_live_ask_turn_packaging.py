import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.ai_assets import (
    build_live_system_instruction,
    build_mode_activation_instruction,
    build_pre_query_brief,
)
from app.models.negotiation import NegotiationSession, NegotiationState
from app.services.negotiation_engine import NegotiationEngine


def test_pre_query_brief_and_mode_instruction_avoid_control_markers():
    brief = build_pre_query_brief(
        context={"item": "iPhone 15 Pro Max", "negotiation_type": "sale"},
        market_info="$750-$820",
        transcript_text="User wants a fast sale.",
        vision_observation=None,
    )
    advice_mode = build_mode_activation_instruction("advice")
    command_mode = build_mode_activation_instruction("command")

    assert "[LISTENER_INTEL:" not in brief
    assert "[LISTENER_INTEL]" not in brief
    assert "wait for the user to speak" not in brief.lower()
    assert "[SYSTEM:" not in advice_mode
    assert "[SYSTEM:" not in command_mode
    assert "command mode is active" not in command_mode.lower()
    assert "advice mode is active" not in advice_mode.lower()
    assert "wait for it" not in advice_mode.lower()
    assert "wait for it" not in command_mode.lower()


def test_live_system_prompt_preserves_advisor_prompt_without_spoken_mode_labels():
    system_instruction = build_live_system_instruction("Desktop companion virtual meeting session")

    assert "You are a negotiation commander." in system_instruction
    assert "QUESTION ANSWERING - HIGHEST PRIORITY:" in system_instruction
    assert "TWO MODES" not in system_instruction
    assert "COMMAND MODE" not in system_instruction
    assert "ADVICE MODE" not in system_instruction
    assert "DIRECTIVE SHAPE" in system_instruction
    assert "ANALYSIS SHAPE" in system_instruction
    assert "VOICE CONSISTENCY RULES:" in system_instruction


@pytest.mark.asyncio
async def test_release_sends_explicit_user_turn_with_question_hint():
    session = NegotiationSession(session_id="test-session", state=NegotiationState.ACTIVE)
    session.user_addressing_ai = True
    session.question_capture_bytes = b"\x00" * 6400
    session.question_capture_chunk_count = 3
    session.question_capture_id = "ask_ai_1"
    session.question_capture_started_at = 1000.0
    session.companion_partial_text["ask_ai"] = "What should I do?"
    session.live_session = Mock()
    session.live_session.send_client_content = AsyncMock()
    session.listener_agent = None

    websocket = AsyncMock()
    spawned_tasks: list[asyncio.Task] = []
    real_create_task = asyncio.create_task

    def spawn_now(coro, *args, **kwargs):
        task = real_create_task(coro)
        spawned_tasks.append(task)
        return task

    with patch("app.services.negotiation_engine.asyncio.create_task", side_effect=spawn_now):
        with patch("app.services.negotiation_engine.session_store.persist_session"):
            await NegotiationEngine.handle_user_addressing_ai(session, {"active": False}, websocket)

    await asyncio.gather(*spawned_tasks)

    send_call = session.live_session.send_client_content.await_args
    assert send_call.kwargs["turn_complete"] is True
    expected_msg = (
        "[USER'S EXACT QUESTION]: What should I do?\n"
        "Answer this specific question directly. "
        "Do not give a generic strategy overview. "
        "Use the intel briefing above as background only."
    )
    assert send_call.kwargs["turns"].parts[0].text == expected_msg


@pytest.mark.asyncio
async def test_release_retries_when_question_hint_is_missing_and_audio_is_unresolved():
    session = NegotiationSession(session_id="test-session", state=NegotiationState.ACTIVE)
    session.user_addressing_ai = True
    session.question_capture_bytes = b"\x00" * 6400
    session.question_capture_chunk_count = 3
    session.question_capture_id = "ask_ai_2"
    session.question_capture_started_at = 1000.0
    session.live_session = Mock()
    session.live_session.send_client_content = AsyncMock()
    session.listener_agent = None

    websocket = AsyncMock()
    spawned_tasks: list[asyncio.Task] = []
    real_create_task = asyncio.create_task

    def spawn_now(coro, *args, **kwargs):
        task = real_create_task(coro)
        spawned_tasks.append(task)
        return task

    with patch("app.services.negotiation_engine.asyncio.create_task", side_effect=spawn_now):
        with patch("app.services.negotiation_engine.session_store.persist_session"):
            await NegotiationEngine.handle_user_addressing_ai(session, {"active": False}, websocket)

    await asyncio.gather(*spawned_tasks)

    session.live_session.send_client_content.assert_not_awaited()
    payload = websocket.send_json.await_args_list[-1].args[0]["payload"]
    assert payload["context"] == "ask_ai"
    assert "Hold and ask again" in payload["text"]


@pytest.mark.asyncio
async def test_release_uses_audio_transcription_when_hint_missing():
    session = NegotiationSession(session_id="test-session", state=NegotiationState.ACTIVE)
    session.user_addressing_ai = True
    session.question_capture_bytes = b"\x00" * 6400
    session.question_capture_chunk_count = 3
    session.question_capture_id = "ask_ai_3"
    session.question_capture_started_at = 1000.0
    session.live_session = Mock()
    session.live_session.send_client_content = AsyncMock()
    session.listener_agent = Mock()
    session.listener_agent._fast_transcribe = Mock(return_value="Should I sell my iPhone 15 Pro Max for $800?")

    websocket = AsyncMock()
    spawned_tasks: list[asyncio.Task] = []
    real_create_task = asyncio.create_task

    def spawn_now(coro, *args, **kwargs):
        task = real_create_task(coro)
        spawned_tasks.append(task)
        return task

    with patch("app.services.negotiation_engine.asyncio.create_task", side_effect=spawn_now):
        with patch("app.services.negotiation_engine.session_store.persist_session"):
            await NegotiationEngine.handle_user_addressing_ai(session, {"active": False}, websocket)

    await asyncio.gather(*spawned_tasks)

    send_call = session.live_session.send_client_content.await_args
    assert send_call.kwargs["turn_complete"] is True
    expected_msg = (
        "[USER'S EXACT QUESTION]: Should I sell my iPhone 15 Pro Max for $800?\n"
        "Answer this specific question directly. "
        "Do not give a generic strategy overview. "
        "Use the intel briefing above as background only."
    )
    assert send_call.kwargs["turns"].parts[0].text == expected_msg


@pytest.mark.asyncio
async def test_release_retries_locally_when_dedicated_ask_audio_is_too_short():
    session = NegotiationSession(session_id="test-session", state=NegotiationState.ACTIVE)
    session.user_addressing_ai = True
    session.question_capture_bytes = b"\x00" * 1600
    session.question_capture_chunk_count = 1
    session.question_capture_id = "ask_ai_4"
    session.question_capture_started_at = 1000.0
    session.live_session = Mock()
    session.live_session.send_client_content = AsyncMock()
    session.listener_agent = None

    websocket = AsyncMock()
    spawned_tasks: list[asyncio.Task] = []
    real_create_task = asyncio.create_task

    def spawn_now(coro, *args, **kwargs):
        task = real_create_task(coro)
        spawned_tasks.append(task)
        return task

    with patch("app.services.negotiation_engine.asyncio.create_task", side_effect=spawn_now):
        with patch("app.services.negotiation_engine.session_store.persist_session"):
            await NegotiationEngine.handle_user_addressing_ai(session, {"active": False}, websocket)

    await asyncio.gather(*spawned_tasks)

    session.live_session.send_client_content.assert_not_awaited()
    websocket.send_json.assert_awaited()
    payload = websocket.send_json.await_args_list[-1].args[0]["payload"]
    assert payload["context"] == "ask_ai"
    assert "Hold and ask again" in payload["text"]
