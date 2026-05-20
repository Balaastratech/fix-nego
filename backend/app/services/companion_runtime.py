from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any

from fastapi import WebSocket

from app.models.companion import CaptureHealth, CompanionHoldState, MeetingBinding, ParticipantOrigin, SourceMode
from app.services.session_store import session_store
from app.services.utterance_types import FinalizedUtterance

logger = logging.getLogger(__name__)


class CompanionRuntime:
    LOCAL_MIC_MESSAGE = "LOCAL_MIC_PCM"
    REMOTE_APP_MESSAGE = "REMOTE_APP_PCM"

    def is_companion_mode(self, session: Any) -> bool:
        return getattr(session, "source_mode", SourceMode.IN_PERSON_WEB.value) == SourceMode.VIRTUAL_COMPANION_DESKTOP.value

    def apply_start_payload(self, session: Any, payload: dict[str, Any]) -> None:
        requested_mode = payload.get("source_mode") or SourceMode.IN_PERSON_WEB.value
        session.source_mode = requested_mode
        if requested_mode != SourceMode.VIRTUAL_COMPANION_DESKTOP.value:
            return

        session.speaker_recognition_enabled = False
        session.speaker_mode = "manual"
        session.audio_sources_active.update(
            {
                "local_mic": True,
                "remote_app": True,
                "screen_frame": True,
            }
        )
        session.capture_preset = payload.get("capture_preset") or "meeting_window_default"
        session.companion_quality_mode = payload.get("companion_quality_mode") or "companion_ready"
        self.update_meeting_binding(session, payload.get("meeting_binding") or {})
        selected_output = payload.get("selected_output_device") or {}
        session.selected_output_device_id = selected_output.get("device_id")
        session.selected_output_device_label = selected_output.get("label")

    def update_meeting_binding(self, session: Any, payload: dict[str, Any]) -> MeetingBinding:
        current = MeetingBinding.model_validate(payload or {})
        if current.bound_at is None and current.is_bound:
            current.bound_at = time.time()
        session.meeting_binding = current.model_dump()
        session.audio_sources_active["remote_app"] = bool(current.is_bound)
        return current

    def update_hold_state(self, session: Any, payload: dict[str, Any]) -> CompanionHoldState:
        current = CompanionHoldState.model_validate(
            {
                **(session.hold_state or {}),
                **(payload or {}),
            }
        )
        if current.active and current.started_at is None:
            current.started_at = time.time()
        if not current.active:
            current.released_at = time.time()
        session.hold_state = current.model_dump()
        return current

    def update_capture_health(self, session: Any, payload: dict[str, Any]) -> CaptureHealth:
        current = CaptureHealth.model_validate(payload or {})
        session.capture_health = current.model_dump()
        session.capture_helper_active = current.helper_active
        session.degraded_reasons = list(current.degraded_reasons)

        degraded_mode = None
        if current.unsafe_device_loopback:
            degraded_mode = "source_ambiguous"
            if "unsafe_device_loopback" not in session.degraded_reasons:
                session.degraded_reasons.append("unsafe_device_loopback")
        elif not current.frame_capture_ok:
            degraded_mode = "source_missing"
            if "frame_capture_unavailable" not in session.degraded_reasons:
                session.degraded_reasons.append("frame_capture_unavailable")
        elif not current.remote_audio_ok:
            degraded_mode = "capture_degraded"
            if "remote_audio_unavailable" not in session.degraded_reasons:
                session.degraded_reasons.append("remote_audio_unavailable")

        session.degraded_mode = degraded_mode
        return current

    def source_admissible(self, session: Any, message_type: str) -> bool:
        if message_type != self.REMOTE_APP_MESSAGE:
            return True
        binding = session.meeting_binding or {}
        health = session.capture_health or {}
        if not binding.get("is_bound"):
            return False
        if health.get("unsafe_device_loopback"):
            return False
        if not health.get("remote_audio_ok", False):
            return False
        return True

    async def handle_audio_payload(
        self,
        session: Any,
        websocket: WebSocket,
        payload: dict[str, Any],
        message_type: str,
    ) -> None:
        if not self.is_companion_mode(session):
            logger.debug("Ignoring companion audio payload outside companion mode [session=%s]", session.session_id)
            return

        if not session.listener_agent:
            logger.debug("Ignoring companion audio payload before listener init [session=%s]", session.session_id)
            return

        if not self.source_admissible(session, message_type):
            await self._emit_degraded_update(websocket, session)
            return

        pcm_b64 = payload.get("pcm_base64") or payload.get("pcm_b64") or payload.get("audio")
        if not pcm_b64:
            return

        try:
            chunk = base64.b64decode(pcm_b64)
        except Exception as exc:
            logger.warning("Failed to decode companion PCM payload [session=%s]: %s", session.session_id, exc)
            return

        if not chunk:
            return

        buffer_key = "local_mic" if message_type == self.LOCAL_MIC_MESSAGE else "remote_app"
        started_key = f"{buffer_key}_started_at"
        now = (payload.get("timestamp_ms") or int(time.time() * 1000)) / 1000.0

        if buffer_key == "local_mic" and getattr(session, "user_addressing_ai", False):
            session.question_capture_bytes += chunk
            return

        if session.companion_audio_started_at.get(started_key) is None:
            session.companion_audio_started_at[started_key] = float(payload.get("started_at_ms", 0) or payload.get("timestamp_ms", 0) or int(time.time() * 1000)) / 1000.0

        session.companion_audio_buffers[buffer_key] = session.companion_audio_buffers.get(buffer_key, b"") + chunk
        session.companion_last_chunk_at[buffer_key] = now

        if not payload.get("is_final"):
            return

        audio = session.companion_audio_buffers.pop(buffer_key, b"")
        started_at = session.companion_audio_started_at.pop(started_key, now)
        if len(audio) < 3200:
            return

        speaker = "user" if buffer_key == "local_mic" else "counterparty"
        participant_origin = (
            ParticipantOrigin.LOCAL_USER.value if buffer_key == "local_mic" else ParticipantOrigin.REMOTE_COUNTERPARTY.value
        )
        source_label = "desktop_local_mic" if buffer_key == "local_mic" else "desktop_remote_app"

        utterance = FinalizedUtterance(
            utterance_id=payload.get("utterance_id") or f"{buffer_key}_{int(now * 1000)}",
            audio=audio,
            started_at=started_at,
            ended_at=now,
            duration_ms=max(1, int((now - started_at) * 1000)),
            rms=float(payload.get("rms") or 0.0),
            source=source_label,
            speaker=speaker,
            speaker_confidence=1.0,
            metadata={
                "participant_origin": participant_origin,
                "source_mode": SourceMode.VIRTUAL_COMPANION_DESKTOP.value,
                "meeting_binding": session.meeting_binding,
            },
        )

        await session.listener_agent.process_diarized_utterance(utterance)
        session.companion_last_transcript_at[buffer_key] = now
        session_store.persist_session(session, ended=False)

    async def _emit_degraded_update(self, websocket: WebSocket, session: Any) -> None:
        try:
            await websocket.send_json(
                {
                    "type": "DEGRADED_MODE_UPDATE",
                    "payload": {
                        "active": True,
                        "mode": session.degraded_mode or "capture_degraded",
                        "reasons": list(session.degraded_reasons),
                    },
                }
            )
        except Exception:
            pass


companion_runtime = CompanionRuntime()
