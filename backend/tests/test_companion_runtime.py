import base64
from unittest.mock import AsyncMock, patch

import pytest

from app.models.companion import SourceMode
from app.models.negotiation import NegotiationSession
from app.services.companion_runtime import companion_runtime
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


@pytest.mark.asyncio
async def test_companion_audio_uses_source_derived_speaker():
    session = NegotiationSession(session_id="companion-audio")
    session.source_mode = SourceMode.VIRTUAL_COMPANION_DESKTOP.value
    session.meeting_binding = {"is_bound": True}
    session.capture_health = {"remote_audio_ok": True, "unsafe_device_loopback": False}
    session.listener_agent = AsyncMock()
    websocket = AsyncMock()
    pcm = b"\x01\x02" * 2000

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
async def test_remote_audio_is_dropped_while_ai_audio_is_playing():
    session = NegotiationSession(session_id="companion-ai-audio-gate")
    session.source_mode = SourceMode.VIRTUAL_COMPANION_DESKTOP.value
    session.meeting_binding = {"is_bound": True}
    session.capture_health = {"remote_audio_ok": True, "unsafe_device_loopback": False}
    session.listener_agent = AsyncMock()
    session.ai_audio_playing = True
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
                "utterance_id": "remote-turn-muted",
                "is_final": True,
            },
            companion_runtime.REMOTE_APP_MESSAGE,
        )

    session.listener_agent.process_diarized_utterance.assert_not_awaited()
    persist_mock.assert_not_called()


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
