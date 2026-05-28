import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.ai_assets import (
    build_live_system_instruction,
    build_mode_activation_instruction,
    build_pre_query_brief,
)
from app.models.negotiation import NegotiationSession, NegotiationState
from app.services.gemini_client import GeminiClient
from app.services.negotiation_engine import NegotiationEngine


@pytest.fixture(autouse=True)
def suppress_conversation_audit(monkeypatch):
    monkeypatch.setattr("app.services.negotiation_engine.log_conversation_event", lambda **_kwargs: None)


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
async def test_press_opens_ask_window(monkeypatch):
    """Pressing the orb must set ask_window_active so any AI response during/after
    the hold is classified as 'ask_ai' (the bug from session d56d9a7a where
    native-audio responses leaked into the public Conversation panel)."""
    from app.config import settings as _settings
    monkeypatch.setattr(_settings, "ASK_AI_NATIVE_AUDIO", False)  # focus on flag-independent behavior

    session = NegotiationSession(session_id="test-session", state=NegotiationState.ACTIVE)
    session.live_session = Mock()
    session.live_session.send_client_content = AsyncMock()
    assert session.ask_window_active is False

    websocket = AsyncMock()
    with patch("app.services.negotiation_engine.session_store.persist_session"):
        await NegotiationEngine.handle_user_addressing_ai(
            session, {"active": True}, websocket
        )
    assert session.ask_window_active is True


@pytest.mark.asyncio
async def test_release_skips_text_send_when_native_audio_on(monkeypatch):
    """When ASK_AI_NATIVE_AUDIO=True, the release handler must NOT call
    send_client_content with the question text — the audio was already streamed
    and a redundant text turn causes the empty 'I didn't catch' fallback."""
    from app.config import settings as _settings
    monkeypatch.setattr(_settings, "ASK_AI_NATIVE_AUDIO", True)

    session = NegotiationSession(session_id="test-session", state=NegotiationState.ACTIVE)
    session.user_addressing_ai = True
    session.ask_window_active = True
    session.question_capture_bytes = b"\x00" * 6400
    session.question_capture_chunk_count = 3
    session.question_capture_id = "ask_ai_native"
    session.question_capture_started_at = 1000.0
    session.companion_partial_text["ask_ai"] = "Some question"
    session.live_session = Mock()
    session.live_session.send_client_content = AsyncMock()
    session.live_session.send_realtime_input = AsyncMock()
    session.listener_agent = Mock()
    session.listener_agent._fast_transcribe = Mock(return_value="batch text")

    websocket = AsyncMock()
    spawned_tasks: list[asyncio.Task] = []
    real_create_task = asyncio.create_task

    def spawn_now(coro, *args, **kwargs):
        task = real_create_task(coro, *args, **kwargs)
        spawned_tasks.append(task)
        return task

    with patch("app.services.negotiation_engine.asyncio.create_task", side_effect=spawn_now):
        with patch("app.services.negotiation_engine.session_store.persist_session"):
            await NegotiationEngine.handle_user_addressing_ai(session, {"active": False}, websocket)

    # Drain only the question task; we'll let the safety timer task linger.
    for t in spawned_tasks:
        if "_close_ask_window_if_orphaned" not in (t.get_name() or ""):
            try:
                await asyncio.wait_for(t, timeout=1.0)
            except Exception:
                pass
    for t in spawned_tasks:
        if not t.done():
            t.cancel()

    # Question text must NOT have been sent via send_client_content during the
    # release. activity_end IS sent via send_realtime_input — that's expected.
    text_sends = [
        call for call in session.live_session.send_client_content.await_args_list
        if call.kwargs.get("turn_complete") is True
    ]
    assert text_sends == [], (
        "When ASK_AI_NATIVE_AUDIO=True the release handler must skip the redundant "
        "text-question send; got: %r" % text_sends
    )


@pytest.mark.asyncio
async def test_native_audio_input_transcript_routes_to_private_ask_panel(monkeypatch):
    from app.config import settings as _settings
    monkeypatch.setattr(_settings, "ASK_AI_NATIVE_AUDIO", True)
    monkeypatch.setattr(_settings, "ASK_AI_SUPPRESS_NATIVE_TRANSCRIPTION", True)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeLiveSession:
        def __init__(self):
            self.calls = 0

        def receive(self):
            self.calls += 1

            async def gen():
                if self.calls == 1:
                    yield Obj(server_content=Obj(
                        interrupted=False,
                        model_turn=None,
                        input_transcription=Obj(text="Can you explain that to me better?"),
                        output_transcription=None,
                        output_audio_transcription=None,
                        turn_complete=False,
                    ))
                    yield Obj(server_content=Obj(
                        interrupted=False,
                        model_turn=None,
                        input_transcription=None,
                        output_transcription=Obj(text="A clearer explanation."),
                        output_audio_transcription=None,
                        turn_complete=False,
                    ))
                    yield Obj(server_content=Obj(
                        interrupted=False,
                        model_turn=None,
                        input_transcription=None,
                        output_transcription=None,
                        output_audio_transcription=None,
                        turn_complete=True,
                    ))
                    return
                raise asyncio.CancelledError()

            return gen()

    session = NegotiationSession(session_id="native-input-private", state=NegotiationState.ACTIVE)
    session.ask_window_active = True
    session.current_ask_capture = {
        "transport": "desktop_ask_ai_pcm",
        "started_at_ms": 123456,
        "chunk_count": 5,
        "audio_bytes": 16000,
        "gemini_input_transcription": False,
    }
    websocket = AsyncMock()

    with pytest.raises(asyncio.CancelledError):
        await GeminiClient.receive_responses(FakeLiveSession(), websocket, session.session_id, session=session)

    transcript_payloads = [
        call.args[0]["payload"]
        for call in websocket.send_json.await_args_list
        if call.args and call.args[0].get("type") == "TRANSCRIPT_UPDATE"
    ]
    assert any(
        payload.get("text") == "Can you explain that to me better?"
        and payload.get("speaker") == "user"
        and payload.get("context") == "ask_ai"
        and payload.get("id") == "ask_ai_123456"
        for payload in transcript_payloads
    )
    ai_partial_payloads = [
        call.args[0]["payload"]
        for call in websocket.send_json.await_args_list
        if call.args
        and call.args[0].get("type") == "TRANSCRIPT_PARTIAL"
        and call.args[0]["payload"].get("speaker") == "ai"
    ]
    ai_final_payloads = [
        payload for payload in transcript_payloads
        if payload.get("speaker") == "ai" and payload.get("context") == "ask_ai"
    ]
    assert ai_partial_payloads
    assert ai_partial_payloads[-1]["id"] == "ask_ai_123456_response"
    assert ai_partial_payloads[-1]["is_partial"] is True
    assert ai_final_payloads
    assert ai_final_payloads[-1]["id"] == "ask_ai_123456_response"
    assert session.last_user_transcript == "Can you explain that to me better?"
    assert session.last_ask_response_at > 0


@pytest.mark.asyncio
async def test_native_audio_input_transcript_stays_server_side_when_display_question_already_published(monkeypatch):
    from app.config import settings as _settings
    monkeypatch.setattr(_settings, "ASK_AI_NATIVE_AUDIO", True)
    monkeypatch.setattr(_settings, "ASK_AI_SUPPRESS_NATIVE_TRANSCRIPTION", True)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeLiveSession:
        def __init__(self):
            self.calls = 0

        def receive(self):
            self.calls += 1

            async def gen():
                if self.calls == 1:
                    yield Obj(server_content=Obj(
                        interrupted=False,
                        model_turn=None,
                        input_transcription=Obj(text="Can you explain that to me better?"),
                        output_transcription=None,
                        output_audio_transcription=None,
                        turn_complete=False,
                    ))
                    return
                raise asyncio.CancelledError()

            return gen()

    session = NegotiationSession(session_id="native-input-private-suppressed", state=NegotiationState.ACTIVE)
    session.ask_window_active = True
    session.current_ask_capture = {
        "transport": "desktop_ask_ai_pcm",
        "started_at_ms": 123456,
        "chunk_count": 5,
        "audio_bytes": 16000,
        "gemini_input_transcription": False,
        "frontend_question_final_sent": True,
        "frontend_question_text": "What should I say now?",
        "frontend_question_source": "desktop_ask_ai",
    }
    websocket = AsyncMock()

    await GeminiClient.receive_responses(FakeLiveSession(), websocket, session.session_id, session=session)

    transcript_payloads = [
        call.args[0]["payload"]
        for call in websocket.send_json.await_args_list
        if call.args and call.args[0].get("type") == "TRANSCRIPT_UPDATE"
    ]
    assert all(
        payload.get("text") != "Can you explain that to me better?"
        for payload in transcript_payloads
    )
    assert session.last_user_transcript == "Can you explain that to me better?"


@pytest.mark.asyncio
async def test_native_audio_input_transcript_routes_to_private_ask_panel_when_not_suppressed(monkeypatch):
    from app.config import settings as _settings
    monkeypatch.setattr(_settings, "ASK_AI_NATIVE_AUDIO", True)
    monkeypatch.setattr(_settings, "ASK_AI_SUPPRESS_NATIVE_TRANSCRIPTION", False)

    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeLiveSession:
        def __init__(self):
            self.calls = 0

        def receive(self):
            self.calls += 1

            async def gen():
                if self.calls == 1:
                    yield Obj(server_content=Obj(
                        interrupted=False,
                        model_turn=None,
                        input_transcription=Obj(text="Can you explain that to me better?"),
                        output_transcription=None,
                        output_audio_transcription=None,
                        turn_complete=False,
                    ))
                    yield Obj(server_content=Obj(
                        interrupted=False,
                        model_turn=None,
                        input_transcription=None,
                        output_transcription=Obj(text="A clearer explanation."),
                        output_audio_transcription=None,
                        turn_complete=False,
                    ))
                    yield Obj(server_content=Obj(
                        interrupted=False,
                        model_turn=None,
                        input_transcription=None,
                        output_transcription=None,
                        output_audio_transcription=None,
                        turn_complete=True,
                    ))
                    return
                raise asyncio.CancelledError()

            return gen()

    session = NegotiationSession(session_id="native-input-private-not-suppressed", state=NegotiationState.ACTIVE)
    session.ask_window_active = True
    session.current_ask_capture = {
        "transport": "desktop_ask_ai_pcm",
        "started_at_ms": 123456,
        "chunk_count": 5,
        "audio_bytes": 16000,
        "gemini_input_transcription": False,
    }
    websocket = AsyncMock()

    with pytest.raises(asyncio.CancelledError):
        await GeminiClient.receive_responses(FakeLiveSession(), websocket, session.session_id, session=session)

    transcript_payloads = [
        call.args[0]["payload"]
        for call in websocket.send_json.await_args_list
        if call.args and call.args[0].get("type") == "TRANSCRIPT_UPDATE"
    ]
    assert any(
        payload.get("text") == "Can you explain that to me better?"
        for payload in transcript_payloads
    )
    assert session.last_user_transcript == "Can you explain that to me better?"
    assert session.last_ask_response_at > 0


@pytest.mark.asyncio
async def test_native_audio_late_empty_batch_does_not_send_retry_after_ai_answered(monkeypatch):
    from app.config import settings as _settings
    monkeypatch.setattr(_settings, "ASK_AI_NATIVE_AUDIO", True)
    monkeypatch.setattr(_settings, "ASK_AI_BATCH_TRANSCRIBE_TIMEOUT_SECONDS", 0.01)

    session = NegotiationSession(session_id="native-late-empty", state=NegotiationState.ACTIVE)
    session.user_addressing_ai = True
    session.ask_window_active = False
    session.last_ask_response_at = time.time()
    session.question_capture_bytes = b"\x00" * 6400
    session.question_capture_chunk_count = 3
    session.question_capture_id = "ask_ai_native"
    session.question_capture_started_at = 1000.0
    session.live_session = Mock()
    session.live_session.send_client_content = AsyncMock()
    session.live_session.send_realtime_input = AsyncMock()
    session.listener_agent = Mock()

    def slow_transcribe(_audio):
        time.sleep(0.05)
        return ""

    session.listener_agent._fast_transcribe = Mock(side_effect=slow_transcribe)
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

    for task in spawned_tasks:
        if "_close_ask_window_if_orphaned" not in (task.get_name() or ""):
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except Exception:
                pass
    for task in spawned_tasks:
        if not task.done():
            task.cancel()

    retry_messages = [
        call.args[0]["payload"]["text"]
        for call in websocket.send_json.await_args_list
        if call.args
        and call.args[0].get("type") == "AI_RESPONSE"
        and "payload" in call.args[0]
    ]
    assert "I didn't catch that clearly. Hold and ask again." not in retry_messages


@pytest.mark.asyncio
async def test_native_audio_release_prefers_gemini_input_transcript_over_batch(monkeypatch):
    from app.config import settings as _settings
    monkeypatch.setattr(_settings, "ASK_AI_NATIVE_AUDIO", True)

    session = NegotiationSession(session_id="native-gemini-transcript", state=NegotiationState.ACTIVE)
    session.user_addressing_ai = True
    session.ask_window_active = True
    session.question_capture_bytes = b"\x00" * 6400
    session.question_capture_chunk_count = 3
    session.question_capture_id = "ask_ai_1000000"
    session.question_capture_started_at = 1000.0
    session.current_ask_capture = {
        "transport": "desktop_ask_ai_pcm",
        "started_at_ms": 1000000,
        "chunk_count": 3,
        "audio_bytes": 6400,
        "gemini_input_transcription": True,
        "gemini_input_text": "હું ગુજરાતી માં બોલી શકું છું?",
    }
    session.live_session = Mock()
    session.live_session.send_client_content = AsyncMock()
    session.live_session.send_realtime_input = AsyncMock()
    session.listener_agent = Mock()
    session.listener_agent._fast_transcribe = Mock(return_value="Go back to Gujarati")

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

    for task in spawned_tasks:
        coro_name = getattr(task.get_coro(), "__name__", "")
        if "_close_ask_window_if_orphaned" not in coro_name:
            await asyncio.wait_for(task, timeout=1.0)
    for task in spawned_tasks:
        if not task.done():
            task.cancel()

    ask_updates = [
        call.args[0]["payload"]
        for call in websocket.send_json.await_args_list
        if call.args
        and call.args[0].get("type") == "TRANSCRIPT_UPDATE"
        and call.args[0].get("payload", {}).get("context") == "ask_ai"
    ]
    assert ask_updates
    assert ask_updates[-1]["text"] == "હું ગુજરાતી માં બોલી શકું છું?"
    assert all(payload["text"] != "Go back to Gujarati" for payload in ask_updates)
    session.listener_agent._fast_transcribe.assert_not_called()
    session.live_session.send_client_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_release_sends_explicit_user_turn_with_question_hint(monkeypatch):
    # This test covers the LEGACY text-path: force ASK_AI_NATIVE_AUDIO=False so the
    # release-handler still sends send_client_content with the question text.
    # When ASK_AI_NATIVE_AUDIO=True, that send is intentionally skipped (Gemini
    # already heard the audio) — covered by a separate test below.
    from app.config import settings as _settings
    monkeypatch.setattr(_settings, "ASK_AI_NATIVE_AUDIO", False)

    session = NegotiationSession(session_id="test-session", state=NegotiationState.ACTIVE)
    session.user_addressing_ai = True
    session.question_capture_bytes = b"\x00" * 6400
    session.question_capture_chunk_count = 3
    session.question_capture_id = "ask_ai_1"
    session.question_capture_started_at = 1000.0
    session.companion_partial_text["ask_ai"] = "What should I do?"
    session.live_session = Mock()
    session.live_session.send_client_content = AsyncMock()
    session.listener_agent = Mock()
    session.listener_agent._fast_transcribe = Mock(return_value="slow batch text")

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
    session.listener_agent._fast_transcribe.assert_not_called()
    expected_msg = (
        "[USER'S EXACT QUESTION]: What should I do?\n"
        "Answer this specific question directly. "
        "Do not give a generic strategy overview. "
        "Use the intel briefing above as background only."
    )
    assert send_call.kwargs["turns"].parts[0].text == expected_msg


@pytest.mark.asyncio
async def test_release_retries_when_question_hint_is_missing_and_audio_is_unresolved(monkeypatch):
    from app.config import settings as _settings
    monkeypatch.setattr(_settings, "ASK_AI_NATIVE_AUDIO", False)
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
async def test_release_uses_audio_transcription_when_hint_missing(monkeypatch):
    from app.config import settings as _settings
    monkeypatch.setattr(_settings, "ASK_AI_NATIVE_AUDIO", False)
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
async def test_release_waits_long_enough_for_realistic_batch_transcription(monkeypatch):
    from app.config import settings as _settings
    monkeypatch.setattr(_settings, "ASK_AI_NATIVE_AUDIO", False)
    session = NegotiationSession(session_id="test-session", state=NegotiationState.ACTIVE)
    session.user_addressing_ai = True
    session.question_capture_bytes = b"\x00" * 6400
    session.question_capture_chunk_count = 3
    session.question_capture_id = "ask_ai_3b"
    session.question_capture_started_at = 1000.0
    session.live_session = Mock()
    session.live_session.send_client_content = AsyncMock()
    session.listener_agent = Mock()

    def slow_transcribe(_audio: bytes) -> str:
        time.sleep(1.4)
        return "What should I say next?"

    session.listener_agent._fast_transcribe = Mock(side_effect=slow_transcribe)

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
    assert "What should I say next?" in send_call.kwargs["turns"].parts[0].text
    retry_payloads = [
        call.args[0]["payload"]["text"]
        for call in websocket.send_json.await_args_list
        if call.args and call.args[0].get("type") == "AI_RESPONSE"
    ]
    assert all("Hold and ask again" not in text for text in retry_payloads)


@pytest.mark.asyncio
async def test_release_retries_locally_when_dedicated_ask_audio_is_too_short(monkeypatch):
    from app.config import settings as _settings
    monkeypatch.setattr(_settings, "ASK_AI_NATIVE_AUDIO", False)
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
