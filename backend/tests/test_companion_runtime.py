import asyncio
import base64
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.models.companion import SourceMode
from app.models.negotiation import NegotiationSession, NegotiationState
from app.services.companion_runtime import companion_runtime, filter_ai_voice_leak
from app.services.negotiation_engine import NegotiationEngine
from app.services.session_store import SessionStore


def test_companion_session_defaults():
    session = NegotiationSession(session_id="companion-defaults")

    assert session.source_mode == SourceMode.IN_PERSON_WEB.value
    assert session.meeting_binding["is_bound"] is False
    assert session.capture_health["remote_audio_ok"] is False
    assert session.hold_state["active"] is False
    assert session.companion_quality_mode == "inactive"
    assert session.ai_audio_playing is False


def test_apply_start_payload_sets_companion_mode_defaults():
    session = NegotiationSession(session_id="companion-start")

    companion_runtime.apply_start_payload(
        session,
        {
            "source_mode": SourceMode.VIRTUAL_COMPANION_DESKTOP.value,
            "capture_preset": "meeting_window_default",
            "companion_quality_mode": "companion_ready",
            "meeting_binding": {
                "target_id": "window-1",
                "window_title": "Zoom Meeting",
                "process_name": "Zoom.exe",
                "platform_hint": "zoom",
                "is_bound": True,
            },
            "selected_output_device": {
                "device_id": "speaker-default",
                "label": "Default Speakers",
            },
        },
    )

    assert session.source_mode == SourceMode.VIRTUAL_COMPANION_DESKTOP.value
    assert session.meeting_binding["window_title"] == "Zoom Meeting"
    assert session.audio_sources_active["remote_app"] is True
    assert session.capture_preset == "meeting_window_default"
    assert session.companion_quality_mode == "companion_ready"
    assert session.selected_output_device_id == "speaker-default"


def test_remote_audio_is_not_admitted_when_binding_is_unsafe():
    session = NegotiationSession(session_id="companion-unsafe")
    session.source_mode = SourceMode.VIRTUAL_COMPANION_DESKTOP.value
    session.meeting_binding = {"is_bound": True}
    session.capture_health = {"remote_audio_ok": True, "unsafe_device_loopback": True}

    assert companion_runtime.source_admissible(session, companion_runtime.REMOTE_APP_MESSAGE) is False


def test_ai_voice_leak_filter_catches_claude_as_cloud_after_playback():
    session = NegotiationSession(session_id="companion-ai-leak-filter")
    session.ai_audio_playing = False
    session.last_ai_audio_played_at = time.time() - 0.5
    session.recent_ai_responses = [
        "The best model depends on your coding needs. Claude Opus is strong for complex debugging."
    ]

    assert filter_ai_voice_leak("Cloud", session) == ""


def test_ai_voice_leak_filter_catches_hyphenated_compound_words():
    session = NegotiationSession(session_id="companion-ai-leak-compound")
    session.ai_audio_playing = True
    session.recent_ai_responses = [
        "A Pre-Trained Transformer is a base model trained on a large amount of data."
    ]

    assert filter_ai_voice_leak("Pretrained", session) == ""


@pytest.mark.asyncio
async def test_deepgram_final_segments_update_one_transcript_row_until_speech_final():
    class FakeDeepgramSession:
        def __init__(self):
            self.callbacks = {}

        def register_callback(self, source, callback):
            self.callbacks[source] = callback

        async def push(self, source, pcm_bytes, language="en-US"):
            return None

    fake_dg = FakeDeepgramSession()
    session = NegotiationSession(session_id="companion-segment-assembler")
    session.source_mode = SourceMode.VIRTUAL_COMPANION_DESKTOP.value
    session.listener_agent = Mock()
    session.listener_agent._session_start_time = time.time()
    session.listener_agent._append_accumulated_transcript = Mock()
    session.listener_agent._run_text_extraction_cycle = AsyncMock()
    websocket = AsyncMock()

    with patch(
        "app.services.deepgram_stream.DeepgramStreamSession.get_or_create",
        return_value=fake_dg,
    ):
        await companion_runtime._push_to_deepgram_stream(session, websocket, "local_mic", b"\x00" * 1600)

    callback = fake_dg.callbacks["local_mic"]
    await callback("Currently, I'm looking at the file that shows me", True, False, 0.99)
    await callback("the best model that I can use for coding.", True, True, 0.99)
    await asyncio.sleep(0)

    updates = [
        call.args[0]["payload"]
        for call in websocket.send_json.await_args_list
        if call.args and call.args[0].get("type") == "TRANSCRIPT_UPDATE"
    ]
    assert len(updates) == 2
    assert updates[0]["id"] == updates[1]["id"]
    assert updates[0]["text"] == "Currently, I'm looking at the file that shows me"
    assert updates[1]["text"] == (
        "Currently, I'm looking at the file that shows me "
        "the best model that I can use for coding."
    )
    session.listener_agent._append_accumulated_transcript.assert_called_once()
    assert session.listener_agent._append_accumulated_transcript.call_args.args[1] == updates[1]["text"]


@pytest.mark.asyncio
async def test_companion_audio_uses_source_derived_speaker():
    session = NegotiationSession(session_id="companion-audio")
    session.source_mode = SourceMode.VIRTUAL_COMPANION_DESKTOP.value
    session.meeting_binding = {"is_bound": True}
    session.capture_health = {"remote_audio_ok": True, "unsafe_device_loopback": False}
    session.listener_agent = AsyncMock()
    websocket = AsyncMock()
    pcm = b"\x01\x02" * 8000

    with patch("app.services.companion_runtime._deepgram_streaming_enabled", return_value=False), \
         patch("app.services.companion_runtime.session_store.persist_session") as persist_mock:
        await companion_runtime.handle_audio_payload(
            session,
            websocket,
            {
                "pcm_base64": base64.b64encode(pcm).decode("ascii"),
                "timestamp_ms": 1234567890,
                "started_at_ms": 1234567000,
                "utterance_id": "remote-turn-1",
                "is_final": True,
            },
            companion_runtime.REMOTE_APP_MESSAGE,
        )

    session.listener_agent.process_diarized_utterance.assert_awaited_once()
    utterance = session.listener_agent.process_diarized_utterance.await_args.args[0]
    assert utterance.speaker == "counterparty"
    assert utterance.source == "desktop_remote_app"
    assert utterance.metadata["participant_origin"] == "remote_counterparty"
    persist_mock.assert_called_once()


@pytest.mark.asyncio
async def test_remote_audio_is_processed_while_ai_audio_is_playing():
    session = NegotiationSession(session_id="companion-ai-audio-gate")
    session.source_mode = SourceMode.VIRTUAL_COMPANION_DESKTOP.value
    session.meeting_binding = {"is_bound": True}
    session.capture_health = {"remote_audio_ok": True, "unsafe_device_loopback": False}
    session.listener_agent = AsyncMock()
    session.ai_audio_playing = True
    websocket = AsyncMock()
    pcm = b"\x01\x02" * 8000

    with patch("app.services.companion_runtime.session_store.persist_session") as persist_mock:
        await companion_runtime.handle_audio_payload(
            session,
            websocket,
            {
                "pcm_base64": base64.b64encode(pcm).decode("ascii"),
                "timestamp_ms": 1234567890,
                "started_at_ms": 1234567000,
                "utterance_id": "remote-turn-muted",
                "is_final": True,
            },
            companion_runtime.REMOTE_APP_MESSAGE,
        )

    session.listener_agent.process_diarized_utterance.assert_awaited_once()
    utterance = session.listener_agent.process_diarized_utterance.await_args.args[0]
    assert utterance.speaker == "counterparty"
    assert utterance.source == "desktop_remote_app"
    persist_mock.assert_called_once()


@pytest.mark.asyncio
async def test_deepgram_stream_receives_remote_pcm_while_ai_playback_active():
    class FakeDeepgramSession:
        def __init__(self):
            self.push = AsyncMock()
            self.callbacks = {}

        def register_callback(self, source, callback):
            self.callbacks[source] = callback

    fake_dg = FakeDeepgramSession()
    session = NegotiationSession(session_id="companion-ai-stream-gate")
    session.source_mode = SourceMode.VIRTUAL_COMPANION_DESKTOP.value
    session.meeting_binding = {"is_bound": True}
    session.capture_health = {"remote_audio_ok": True, "unsafe_device_loopback": False}
    session.listener_agent = AsyncMock()
    session.ai_audio_playing = True
    websocket = AsyncMock()
    pcm = b"\x01\x02" * 2000

    with patch("app.services.companion_runtime._deepgram_streaming_enabled", return_value=True):
        with patch("app.services.deepgram_stream.DeepgramStreamSession.get_or_create", return_value=fake_dg):
            await companion_runtime.handle_audio_payload(
                session,
                websocket,
                {
                    "pcm_base64": base64.b64encode(pcm).decode("ascii"),
                    "timestamp_ms": 1234567890,
                    "started_at_ms": 1234567000,
                    "utterance_id": "remote-turn-stream-muted",
                    "is_final": True,
                },
                companion_runtime.REMOTE_APP_MESSAGE,
            )

    assert "remote_app" in fake_dg.callbacks
    fake_dg.push.assert_awaited_once()
    websocket.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_local_mic_tail_is_dropped_during_post_hold_grace():
    session = NegotiationSession(session_id="companion-post-hold-tail")
    session.source_mode = SourceMode.VIRTUAL_COMPANION_DESKTOP.value
    session.meeting_binding = {"is_bound": True}
    session.capture_health = {"remote_audio_ok": True, "unsafe_device_loopback": False}
    session.listener_agent = AsyncMock()
    session.ignore_local_mic_until = 9999999999.0
    websocket = AsyncMock()
    pcm = b"\x01\x02" * 2000

    with patch("app.services.companion_runtime.session_store.persist_session") as persist_mock:
        await companion_runtime.handle_audio_payload(
            session,
            websocket,
            {
                "pcm_base64": base64.b64encode(pcm).decode("ascii"),
                "timestamp_ms": 1234567890,
                "started_at_ms": 1234567000,
                "utterance_id": "local-tail",
                "is_final": True,
            },
            companion_runtime.LOCAL_MIC_MESSAGE,
        )

    session.listener_agent.process_diarized_utterance.assert_not_awaited()
    persist_mock.assert_not_called()


@pytest.mark.asyncio
async def test_dedicated_ask_ai_pcm_is_buffered_without_public_transcript():
    session = NegotiationSession(session_id="companion-ask-ai")
    session.source_mode = SourceMode.VIRTUAL_COMPANION_DESKTOP.value
    session.meeting_binding = {"is_bound": True}
    session.capture_health = {"remote_audio_ok": True, "unsafe_device_loopback": False}
    session.listener_agent = AsyncMock()
    websocket = AsyncMock()
    pcm = b"\x01\x02" * 2000

    with patch("app.services.companion_runtime.session_store.persist_session") as persist_mock:
        await companion_runtime.handle_audio_payload(
            session,
            websocket,
            {
                "pcm_base64": base64.b64encode(pcm).decode("ascii"),
                "timestamp_ms": 1234567890,
                "started_at_ms": 1234567000,
                "utterance_id": "ask-ai-turn",
                "is_final": True,
            },
            companion_runtime.ASK_AI_MESSAGE,
        )

    assert session.question_capture_bytes == pcm
    assert session.question_capture_chunk_count == 1
    assert session.current_ask_capture["transport"] == "desktop_ask_ai_pcm"
    session.listener_agent.process_diarized_utterance.assert_not_awaited()
    persist_mock.assert_not_called()


@pytest.mark.asyncio
async def test_emit_partial_question_transcript_sends_private_partial_entry():
    session = NegotiationSession(session_id="companion-ask-ai-partial")
    session.question_capture_id = "ask_ai_123"
    websocket = AsyncMock()

    with patch.object(
        companion_runtime,
        "_transcribe_snapshot_text",
        new=AsyncMock(return_value="what should I say now"),
    ) as transcribe_mock:
        await companion_runtime._emit_partial_question_transcript(
            session=session,
            websocket=websocket,
            audio_snapshot=b"\x00" * 3200,
            started_at=1234.5,
        )

    transcribe_mock.assert_awaited_once()
    payloads = [
        call.args[0]["payload"]
        for call in websocket.send_json.await_args_list
        if call.args and call.args[0].get("type") == "TRANSCRIPT_PARTIAL"
    ]
    assert payloads
    assert payloads[-1]["id"] == "ask_ai_123"
    assert payloads[-1]["context"] == "ask_ai"
    assert payloads[-1]["text"] == "what should I say now"


@pytest.mark.asyncio
async def test_pause_resume_lifecycle_active_to_paused_to_active():
    session = NegotiationSession(session_id="companion-pause-resume")
    session.state = NegotiationState.ACTIVE
    session.source_mode = SourceMode.VIRTUAL_COMPANION_DESKTOP.value
    session.copilot_active = True
    session.live_session = object()
    session.listener_agent = AsyncMock()
    session.pending_intel_context = {"price": 100}
    session.vision_live_send_task = asyncio.create_task(asyncio.sleep(30))
    session.intel_injection_task = asyncio.create_task(asyncio.sleep(30))
    websocket = AsyncMock()

    with patch("app.services.negotiation_engine.session_store.persist_session"):
        await NegotiationEngine.handle_pause(session, {}, websocket)

    assert session.state == NegotiationState.PAUSED
    assert session.user_addressing_ai is False
    assert session.ai_audio_playing is False
    assert session.pending_intel_context == {"price": 100}
    assert session.vision_live_send_task is None
    assert session.intel_injection_task is None
    session.listener_agent.pause.assert_awaited_once()
    sent_types = [call.args[0]["type"] for call in websocket.send_json.await_args_list]
    assert "SESSION_PAUSED" in sent_types

    with patch("app.services.negotiation_engine.session_store.persist_session"):
        await NegotiationEngine.handle_resume(session, {}, websocket)

    assert session.state == NegotiationState.ACTIVE
    session.listener_agent.resume.assert_awaited_once()
    sent_types = [call.args[0]["type"] for call in websocket.send_json.await_args_list]
    assert "SESSION_RESUMED" in sent_types
    assert session.intel_injection_task is not None
    session.intel_injection_task.cancel()


@pytest.mark.asyncio
async def test_paused_session_rejects_or_drops_companion_pcm():
    session = NegotiationSession(session_id="companion-paused-audio")
    session.state = NegotiationState.PAUSED
    session.source_mode = SourceMode.VIRTUAL_COMPANION_DESKTOP.value
    session.meeting_binding = {"is_bound": True}
    session.capture_health = {"remote_audio_ok": True, "unsafe_device_loopback": False}
    session.listener_agent = AsyncMock()
    websocket = AsyncMock()
    pcm = b"\x01\x02" * 8000

    with patch("app.services.companion_runtime.session_store.persist_session") as persist_mock:
        await companion_runtime.handle_audio_payload(
            session,
            websocket,
            {
                "pcm_base64": base64.b64encode(pcm).decode("ascii"),
                "timestamp_ms": 1234567890,
                "started_at_ms": 1234567000,
                "utterance_id": "paused-turn",
                "is_final": True,
            },
            companion_runtime.REMOTE_APP_MESSAGE,
        )

    session.listener_agent.process_diarized_utterance.assert_not_awaited()
    persist_mock.assert_not_called()


@pytest.mark.asyncio
async def test_paused_session_ignores_screen_frames():
    session = NegotiationSession(session_id="companion-paused-screen")
    session.state = NegotiationState.PAUSED
    websocket = AsyncMock()

    await NegotiationEngine.handle_screen_frame(
        session,
        {"image": "not-even-base64", "timestamp": 123},
        websocket,
    )

    assert session.vision_live_pending_frame_b64 is None
    assert session.vision_frame_buffer == []
    assert session.vision_analysis_task is None


@pytest.mark.asyncio
async def test_pause_preserves_pending_intel_and_resume_flushes():
    session = NegotiationSession(session_id="companion-paused-intel")
    session.state = NegotiationState.PAUSED
    session.source_mode = SourceMode.VIRTUAL_COMPANION_DESKTOP.value
    session.copilot_active = True
    session.live_session = object()
    session.pending_intel_context = {"offer": 90}
    session.pending_intel_critical_events = [{"type": "anchor"}]
    websocket = AsyncMock()

    with patch("app.services.negotiation_engine.session_store.persist_session"):
        await NegotiationEngine.handle_resume(session, {}, websocket)

    assert session.state == NegotiationState.ACTIVE
    assert session.pending_intel_context == {"offer": 90}
    assert session.pending_intel_critical_events == [{"type": "anchor"}]
    assert session.intel_injection_task is not None
    session.intel_injection_task.cancel()


@pytest.mark.asyncio
async def test_end_session_destroys_deepgram_and_closes_runtime():
    class FakeLiveSessionContext:
        def __init__(self):
            self.closed = False

        async def __aexit__(self, exc_type, exc, tb):
            self.closed = True

    session = NegotiationSession(session_id="companion-end-cleanup")
    session.state = NegotiationState.ACTIVE
    session.source_mode = SourceMode.VIRTUAL_COMPANION_DESKTOP.value
    listener_agent = AsyncMock()
    session.listener_agent = listener_agent
    session.live_session = object()
    session.live_session_cm = FakeLiveSessionContext()
    session.pending_intel_context = {"deal": "active"}
    session.question_capture_bytes = b"private"
    websocket = AsyncMock()

    with patch("app.services.negotiation_engine.session_store.persist_session"), \
         patch("app.services.deepgram_stream.DeepgramStreamSession.destroy", new_callable=AsyncMock) as destroy_mock:
        await NegotiationEngine.handle_end(session, {}, websocket)

    listener_agent.stop.assert_awaited_once()
    destroy_mock.assert_awaited_once_with(session.session_id)
    assert session.live_session is None
    assert session.live_session_cm is None
    assert session.question_capture_bytes == b""
    assert session.pending_intel_context is None
    assert session.state == NegotiationState.IDLE
    sent_types = [call.args[0]["type"] for call in websocket.send_json.await_args_list]
    assert "OUTCOME_SUMMARY" in sent_types


def test_start_after_end_uses_new_session_id_contract():
    first = NegotiationSession(session_id="first-session")
    second = NegotiationSession(session_id="second-session")

    assert first.session_id != second.session_id
    assert first.state == NegotiationState.IDLE
    assert second.state == NegotiationState.IDLE


def test_session_store_persists_companion_context(tmp_path):
    store = SessionStore(str(tmp_path / "companion.db"))
    session = NegotiationSession(session_id="companion-store")
    session.source_mode = SourceMode.VIRTUAL_COMPANION_DESKTOP.value
    session.meeting_binding = {
        "target_id": "window-7",
        "window_title": "Google Meet",
        "process_name": "chrome.exe",
        "platform_hint": "google_meet",
        "is_bound": True,
    }
    session.capture_health = {
        "remote_audio_ok": True,
        "frame_capture_ok": True,
        "reply_output_ok": True,
        "unsafe_device_loopback": False,
    }
    session.hold_state = {"active": False, "muted_to_meeting": False}
    session.capture_preset = "meeting_window_default"
    session.companion_quality_mode = "companion_ready"
    store.persist_session(session, ended=False)

    loaded = store.load_session_bundle("companion-store")
    assert loaded is not None
    assert loaded["context"]["source_mode"] == SourceMode.VIRTUAL_COMPANION_DESKTOP.value
    assert loaded["context"]["meeting_binding"]["window_title"] == "Google Meet"
    assert loaded["context"]["capture_health"]["frame_capture_ok"] is True
