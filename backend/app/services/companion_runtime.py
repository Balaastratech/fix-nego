from __future__ import annotations

import asyncio
import base64
import logging
import time
import uuid
from typing import Any

from fastapi import WebSocket

from app.config import settings
from app.models.companion import CaptureHealth, CompanionHoldState, MeetingBinding, ParticipantOrigin, SourceMode
from app.services.session_store import session_store
from app.services.stt_service import SpeechTranscriptionService
from app.services.utterance_types import FinalizedUtterance
from app.utils.conversation_audit import log_conversation_event
from app.utils.session_trace import get_session_trace

logger = logging.getLogger(__name__)

def _deepgram_streaming_enabled() -> bool:
    return (
        getattr(settings, "TRANSCRIPTION_PROVIDER", "").strip().lower() == "deepgram"
        and bool(getattr(settings, "DEEPGRAM_API_KEY", ""))
    )


def levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def filter_ai_voice_leak(text: str, session: Any) -> str:
    is_playing = getattr(session, "ai_audio_playing", False)
    time_since_played = time.time() - getattr(session, "last_ai_audio_played_at", 0.0)
    if not is_playing and time_since_played >= 5.0:
        return text

    recent_responses = []
    if hasattr(session, "recent_ai_responses") and session.recent_ai_responses:
        recent_responses.extend(session.recent_ai_responses)
    if hasattr(session, "current_ai_response") and session.current_ai_response:
        recent_responses.append(session.current_ai_response)

    if not recent_responses:
        return text

    def get_words(t: str) -> list[str]:
        cleaned = "".join(c if c.isalnum() else " " for c in t.lower())
        return cleaned.split()

    ai_words = set()
    for resp in recent_responses:
        ai_words.update(get_words(resp))

    def is_ai_word(w: str) -> bool:
        w_lower = w.lower()
        if w_lower in ai_words:
            return True
        # Common homophones / mis-transcriptions
        homophones = {
            "dallas": "analysis",
            "dialysis": "analysis",
            "shaped": "shape",
            "the": "the",
            "is": "is",
            "to": "to",
        }
        if w_lower in homophones and homophones[w_lower] in ai_words:
            return True

        # Fuzzy distance check for mis-transcriptions
        for aw in ai_words:
            if len(aw) >= 4 and len(w_lower) >= 4:
                if abs(len(aw) - len(w_lower)) <= 1:
                    if levenshtein_distance(aw, w_lower) <= 1:
                        return True
        return False

    tx_words = get_words(text)
    filtered = []
    for w in tx_words:
        if not is_ai_word(w):
            filtered.append(w)

    if not filtered:
        return ""
    return " ".join(filtered).capitalize()


def is_ai_voice_leak(text: str, session: Any) -> bool:
    filtered = filter_ai_voice_leak(text, session)
    return filtered != text


class CompanionRuntime:
    LOCAL_MIC_MESSAGE = "LOCAL_MIC_PCM"
    REMOTE_APP_MESSAGE = "REMOTE_APP_PCM"
    ASK_AI_MESSAGE = "ASK_AI_PCM"

    def is_companion_mode(self, session: Any) -> bool:
        return getattr(session, "source_mode", SourceMode.IN_PERSON_WEB.value) == SourceMode.VIRTUAL_COMPANION_DESKTOP.value

    def apply_start_payload(self, session: Any, payload: dict[str, Any]) -> None:
        requested_mode = payload.get("source_mode") or SourceMode.IN_PERSON_WEB.value
        session.source_mode = requested_mode
        if requested_mode != SourceMode.VIRTUAL_COMPANION_DESKTOP.value:
            return

        session.speaker_recognition_enabled = False
        session.speaker_mode = "auto"
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

        if not session.listener_agent and message_type != self.ASK_AI_MESSAGE:
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

        # Diagnostic: log only is_final=True chunks (one per utterance, not every frame)
        if message_type == self.ASK_AI_MESSAGE:
            buffer_key_diag = "ask_ai"
        else:
            buffer_key_diag = "local_mic" if message_type == self.LOCAL_MIC_MESSAGE else "remote_app"
        if payload.get("is_final"):
            logger.info(
                "Companion PCM finalized [session=%s source=%s bytes=%s]",
                session.session_id, buffer_key_diag, len(chunk),
            )

        if not chunk:
            return

        if message_type == self.ASK_AI_MESSAGE:
            buffer_key = "ask_ai"
        else:
            buffer_key = "local_mic" if message_type == self.LOCAL_MIC_MESSAGE else "remote_app"
        started_key = f"{buffer_key}_started_at"
        now = (payload.get("timestamp_ms") or int(time.time() * 1000)) / 1000.0
        existing_audio = session.companion_audio_buffers.get(buffer_key, b"")

        if buffer_key == "ask_ai":
            await self._capture_private_ask_audio(
                session=session,
                websocket=websocket,
                payload=payload,
                chunk=chunk,
                now=now,
            )
            return

        if (
            buffer_key == "local_mic"
            and not getattr(session, "user_addressing_ai", False)
            and now < float(getattr(session, "ignore_local_mic_until", 0.0) or 0.0)
        ):
            return

        if buffer_key == "local_mic" and getattr(session, "user_addressing_ai", False):
            logger.debug(
                "Dropping public local_mic chunk during private ask [session=%s bytes=%s]",
                session.session_id,
                len(chunk),
            )
            return

        # Drop remote_app audio while AI audio is physically playing in the user's earphone.
        # ai_audio_playing is set True when first PCM chunk is sent to frontend,
        # and cleared only when frontend sends AI_PLAYBACK_DONE (event-based, not time-based).
        # This prevents the AI's own voice from being captured by the screen loopback
        # and transcribed as counterparty speech.
        # Bypass transcription blockade for Private Advisor Copilot headphones setup:
        # if buffer_key == "remote_app" and getattr(session, "ai_audio_playing", False):
        #     return

        # ── Deepgram streaming path ───────────────────────────────────────────
        # Forward every chunk to the live stream immediately.
        # Skip batch path while streaming is healthy — streaming gives real-time results.
        # If streaming has permanently failed (HTTP 400/401), fall through to batch.
        #
        # During hold-to-ask (user_addressing_ai=True):
        #   - local_mic is suppressed (user's voice goes only to Gemini Live via ASK_AI_PCM)
        #   - remote_app KEEPS flowing to Deepgram so counterparty speech isn't missed
        _hold_active = getattr(session, "user_addressing_ai", False)
        _skip_for_hold = _hold_active and buffer_key == "local_mic"
        if _deepgram_streaming_enabled() and not _skip_for_hold:
            await self._push_to_deepgram_stream(session, websocket, buffer_key, chunk)
            # Only skip batch if streaming is NOT permanently failed
            from app.services.deepgram_stream import DeepgramStreamSession
            dg = DeepgramStreamSession.get(session.session_id)
            streaming_failed = dg and getattr(dg, f"_failed_{buffer_key}", False)
            if not streaming_failed:
                return  # streaming owns this; skip batch

        if session.companion_audio_started_at.get(started_key) is None:
            session.companion_audio_started_at[started_key] = float(payload.get("started_at_ms", 0) or payload.get("timestamp_ms", 0) or int(time.time() * 1000)) / 1000.0

        session.companion_audio_buffers[buffer_key] = existing_audio + chunk
        session.companion_last_chunk_at[buffer_key] = now
        if not existing_audio:
            logger.info(
                "Companion audio capture started [session=%s source=%s bytes=%s final=%s]",
                session.session_id,
                buffer_key,
                len(chunk),
                bool(payload.get("is_final")),
            )

        partial_audio = session.companion_audio_buffers.get(buffer_key, b"")
        partial_started_at = session.companion_audio_started_at.get(started_key, now)
        partial_task = session.companion_partial_tasks.get(buffer_key)
        if (
            len(partial_audio) >= 6400
            and (partial_task is None or partial_task.done())
        ):
            session.companion_partial_tasks[buffer_key] = asyncio.create_task(
                self._emit_partial_transcript(
                    session=session,
                    websocket=websocket,
                    buffer_key=buffer_key,
                    audio_snapshot=partial_audio,
                    started_at=partial_started_at,
                    speaker=("user" if buffer_key == "local_mic" else "counterparty"),
                    source_label=("desktop_local_mic" if buffer_key == "local_mic" else "desktop_remote_app"),
                )
            )

        if not payload.get("is_final"):
            return

        audio = session.companion_audio_buffers.pop(buffer_key, b"")
        started_at = session.companion_audio_started_at.pop(started_key, now)
        session.companion_partial_started_at.pop(buffer_key, None)
        session.companion_partial_text.pop(buffer_key, None)
        logger.info(
            "Companion audio finalized [session=%s source=%s bytes=%s duration_ms=%s]",
            session.session_id,
            buffer_key,
            len(audio),
            max(1, int((now - started_at) * 1000)),
        )
        # Drop anything under 500ms — keyboard clicks, ambient noise, brief sounds
        # all get captured by the VAD but are too short to contain real speech.
        # 500ms at 16kHz 16-bit = 16000 bytes.
        min_speech_bytes = 16000  # 500ms
        if len(audio) < min_speech_bytes:
            logger.debug(
                "Companion audio dropped as too short [session=%s source=%s bytes=%s duration_ms=%s]",
                session.session_id, buffer_key, len(audio),
                max(1, int((now - started_at) * 1000)),
            )
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

    async def _capture_private_ask_audio(
        self,
        *,
        session: Any,
        websocket: WebSocket,
        payload: dict[str, Any],
        chunk: bytes,
        now: float,
    ) -> None:
        started_at = float(payload.get("started_at_ms", 0) or payload.get("timestamp_ms", 0) or int(time.time() * 1000)) / 1000.0
        if not session.question_capture_started_at:
            session.question_capture_started_at = started_at
        if not session.question_capture_id:
            session.question_capture_id = f"ask_ai_{int(session.question_capture_started_at * 1000)}"

        session.question_capture_bytes += chunk
        session.question_capture_chunk_count += 1
        session.question_capture_last_chunk_at = now
        # NOTE: We do NOT stream via send_realtime_input during hold.
        # That API is for the continuous ambient session stream — mixing the question
        # audio into it makes Gemini unable to distinguish it from background noise.
        # Instead, after hold is released, the complete audio is sent as a discrete
        # WAV message via send_client_content so Gemini processes it as a specific question.

        capture = session.current_ask_capture or {}
        first_chunk = session.question_capture_chunk_count == 1
        if not capture:
            capture = {
                "transport": "desktop_ask_ai_pcm",
                "started_at_ms": int(session.question_capture_started_at * 1000),
                "chunk_count": 0,
                "audio_bytes": 0,
                "gemini_input_transcription": False,
            }
        if first_chunk:
            session.session_metrics["ask_capture_dedicated_count"] = session.session_metrics.get("ask_capture_dedicated_count", 0) + 1
            logger.info(
                "Companion dedicated ask-ai capture started [session=%s first_chunk_bytes=%s]",
                session.session_id,
                len(chunk),
            )
        capture["chunk_count"] = session.question_capture_chunk_count
        capture["audio_bytes"] = len(session.question_capture_bytes)
        capture["last_chunk_at_ms"] = int(now * 1000)
        session.current_ask_capture = capture

        ask_ai_partial_task = session.companion_partial_tasks.get("ask_ai")
        if (
            len(session.question_capture_bytes) >= 6400
            and (ask_ai_partial_task is None or ask_ai_partial_task.done())
        ):
            session.companion_partial_tasks["ask_ai"] = asyncio.create_task(
                self._emit_partial_question_transcript(
                    session=session,
                    websocket=websocket,
                    audio_snapshot=session.question_capture_bytes,
                    started_at=session.question_capture_started_at,
                )
            )

    async def _transcribe_snapshot_text(
        self,
        *,
        session: Any,
        audio_snapshot: bytes,
        utterance_id: str,
        started_at: float,
    ) -> str:
        transcriber = session.speech_transcriber or SpeechTranscriptionService(session)
        session.speech_transcriber = transcriber
        try:
            response = await transcriber.transcribe_audio(
                audio_snapshot,
                utterance_id=utterance_id,
                duration_ms=max(1, int((time.time() - started_at) * 1000)),
                language_hint=session.language,
                response_language_hint=session.response_language,
                timeout_seconds=min(settings.STT_END_TO_END_TIMEOUT_SECONDS, 6.0),
                count_metrics=False,
            )
            return (response.get("text") or "").strip()
        except Exception as exc:
            listener = getattr(session, "listener_agent", None)
            if not listener:
                raise exc
            logger.debug(
                "Companion snapshot Google STT failed, using Gemini fallback [session=%s utterance=%s]: %s",
                session.session_id,
                utterance_id,
                exc,
            )
            text = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: listener._fast_transcribe(audio_snapshot),
                ),
                timeout=6.0,
            )
            return (text or "").strip()

    async def _emit_partial_transcript(
        self,
        *,
        session: Any,
        websocket: WebSocket,
        buffer_key: str,
        audio_snapshot: bytes,
        started_at: float,
        speaker: str,
        source_label: str,
    ) -> None:
        try:
            text = await self._transcribe_snapshot_text(
                session=session,
                audio_snapshot=audio_snapshot,
                utterance_id=f"{buffer_key}_partial",
                started_at=started_at,
            )
            if not text:
                return
            if session.companion_partial_text.get(buffer_key) == text:
                return
            session.companion_partial_text[buffer_key] = text
            session.companion_partial_started_at.setdefault(buffer_key, started_at)
            await websocket.send_json(
                {
                    "type": "TRANSCRIPT_PARTIAL",
                    "payload": {
                        "id": f"{buffer_key}_partial",
                        "speaker": speaker,
                        "text": text,
                        "timestamp": int(started_at * 1000),
                        "is_partial": True,
                        "source": source_label,
                    },
                }
            )
        except Exception as exc:
            logger.debug(
                "Companion partial transcript skipped [session=%s source=%s]: %s",
                session.session_id,
                buffer_key,
                exc,
            )

    async def _emit_partial_question_transcript(
        self,
        *,
        session: Any,
        websocket: WebSocket,
        audio_snapshot: bytes,
        started_at: float,
    ) -> None:
        try:
            text = await self._transcribe_snapshot_text(
                session=session,
                audio_snapshot=audio_snapshot,
                utterance_id=f"{session.question_capture_id or 'ask_ai'}_partial",
                started_at=started_at,
            )
            if not text:
                return
            if session.companion_partial_text.get("ask_ai") == text:
                return
            session.companion_partial_text["ask_ai"] = text
            await websocket.send_json(
                {
                    "type": "TRANSCRIPT_PARTIAL",
                    "payload": {
                        "id": session.question_capture_id or "ask_ai_live",
                        "speaker": "user",
                        "text": text,
                        "timestamp": int(started_at * 1000),
                        "is_partial": True,
                        "context": "ask_ai",
                        "source": "desktop_ask_ai",
                    },
                }
            )
        except Exception as exc:
            logger.debug(
                "Companion ask-ai partial skipped [session=%s]: %s",
                session.session_id,
                exc,
            )

    async def _push_to_deepgram_stream(
        self,
        session: Any,
        websocket: WebSocket,
        source: str,  # "local_mic" or "remote_app"
        pcm_bytes: bytes,
    ) -> None:
        """Forward a PCM chunk to the Deepgram live stream for this session/source."""
        from app.services.deepgram_stream import DeepgramStreamSession

        dg = DeepgramStreamSession.get_or_create(session.session_id, settings.DEEPGRAM_API_KEY)

        # Register transcript callback the first time we see this source
        cb_key = f"_dg_cb_{source}"
        if not getattr(session, cb_key, False):
            speaker = "user" if source == "local_mic" else "counterparty"
            # Track a stable ID for the current utterance so partial→final replaces in place
            utterance_state = {"id": None, "started_at": None}

            async def on_transcript(text: str, is_final: bool, speech_final: bool, confidence: float) -> None:
                if not text:
                    return

                ts_now = int(time.time() * 1000)

                # Assign a stable ID at the start of each utterance; reuse it for final
                if utterance_state["id"] is None:
                    utterance_state["id"] = f"{source}_live_{ts_now}"
                    utterance_state["started_at"] = ts_now
                entry_id = utterance_state["id"]

                if source == "remote_app":
                    if getattr(session, "ai_audio_playing", False):
                        # Delay by 1.5 seconds to allow Gemini Live text chunks to fully arrive and populate recent/current responses
                        await asyncio.sleep(1.5)
                    
                    cleaned_text = filter_ai_voice_leak(text, session)
                    if not cleaned_text.strip():
                        logger.info("[DGStream] Suppressed AI voice leak in remote_app lane: %r", text)
                        try:
                            await websocket.send_json({
                                "type": "TRANSCRIPT_DELETE",
                                "payload": {"id": entry_id, "speaker": speaker}
                            })
                        except Exception:
                            pass
                        return
                    text = cleaned_text

                if not is_final:
                    # Interim word-by-word result — update the SAME entry in the UI
                    logger.info("[DGStream] Interim source=%s text=%r", source, text[:60])
                    try:
                        await websocket.send_json({
                            "type": "TRANSCRIPT_PARTIAL",
                            "payload": {
                                "id": entry_id,
                                "speaker": speaker,
                                "text": text,
                                "timestamp": utterance_state["started_at"],
                                "is_partial": True,
                                "source": f"desktop_{source}",
                            },
                        })
                    except Exception:
                        pass
                    return

                # Final transcript — replaces the partial entry in-place (same ID)
                logger.info(
                    "[DGStream] Final source=%s conf=%.2f text=%r [session=%s]",
                    source, confidence, text[:80], session.session_id[:8],
                )
                utterance_state["id"] = None  # reset for next utterance
                try:
                    await websocket.send_json({
                        "type": "TRANSCRIPT_UPDATE",
                        "payload": {
                            "id": entry_id,
                            "speaker": speaker,
                            "text": text,
                            "timestamp": utterance_state["started_at"] or ts_now,
                            "transcription_confidence": confidence,
                            "source": f"desktop_{source}",
                        },
                    })
                except Exception:
                    pass

                log_conversation_event(
                    session_id=session.session_id,
                    event="negotiation_turn",
                    speaker=speaker,
                    text=text,
                    timestamp_ms=ts_now,
                    context="conversation",
                )

                # Log to per-session file (millisecond precision)
                try:
                    from app.utils.session_logger import get_session_logger as _gsl
                    _sl = _gsl(session.session_id)
                    if _sl:
                        _sl.transcript(
                            speaker=speaker,
                            text=text,
                            confidence=confidence,
                            duration_ms=None,
                            source=f"desktop_{source}",
                        )
                except Exception:
                    pass
                trace = get_session_trace(session.session_id)
                if trace:
                    event = trace.record(
                        category="transcript",
                        name="stream_transcript_final",
                        summary=f"Final Deepgram transcript received for {speaker}",
                        data={
                            "speaker": speaker,
                            "text": text,
                            "confidence": confidence,
                            "source": f"desktop_{source}",
                            "speech_final": speech_final,
                        },
                    )
                    trace.remember("last_transcript_event_id", event["event_id"])
                    session.trace_refs["last_transcript_event_id"] = event["event_id"]

                # Feed final text into listener for context extraction
                listener = getattr(session, "listener_agent", None)
                if listener and speech_final:
                    # Inject as accumulated transcript for context extraction
                    label = "User" if speaker == "user" else "Counterparty"
                    elapsed = time.time() - listener._session_start_time
                    mins, secs = int(elapsed // 60), int(elapsed % 60)
                    listener._append_accumulated_transcript(label, text, f"{mins}:{secs:02d}")
                    asyncio.create_task(
                        listener._run_text_extraction_cycle(),
                        name=f"dg-extract-{session.session_id[:8]}",
                    )

            dg.register_callback(source, on_transcript)
            setattr(session, cb_key, True)

        language = getattr(session, "language", None) or "en-US"
        await dg.push(source, pcm_bytes, language=language)

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
