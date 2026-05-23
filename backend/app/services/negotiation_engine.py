import base64
import logging
import asyncio
from typing import Dict
import time
import re
import json

from fastapi import WebSocket
from google.genai import types

from app.ai_assets import (
    build_copilot_priming_text,
    build_critical_event_block,
    build_listener_intel_block,
    build_mode_activation_instruction,
    build_pre_query_brief,
    build_single_context_intel_text,
)
from app.models.negotiation import NegotiationSession, NegotiationState
from app.models.companion import SourceMode
from app.services.companion_runtime import companion_runtime
from app.services.gemini_client import (
    open_live_session,
    send_vision_frame,
    send_audio_chunk,
    receive_responses,
    keepalive_ping,
    handle_gemini_text,
)
from app.services.audio_buffer import AudioBuffer
from app.services.listener_agent import ListenerAgent
from app.services.stt_service import SpeechTranscriptionService
from app.services.utterance_types import FinalizedUtterance
from app.config import settings
from app.services.capability_registry import capability_registry
from app.services.speaker_mapping_service import SpeakerMappingService
from app.services.speechbrain_service import speechbrain_service
from app.services.session_store import session_store
from app.utils.conversation_audit import log_conversation_event
from app.utils.speaker_debug import log_speaker_debug

logger = logging.getLogger(__name__)

# Valid messages per state
VALID_MESSAGES: Dict[NegotiationState, list[str]] = {
    NegotiationState.IDLE:      ["PRIVACY_CONSENT_GRANTED", "TRACE_CLIENT_EVENT", "CAPTURE_HEALTH"],
    NegotiationState.CONSENTED: ["START_NEGOTIATION", "ENROLLMENT_START", "ENROLLMENT_AUDIO", "TRACE_CLIENT_EVENT", "CAPTURE_HEALTH"],
    NegotiationState.ACTIVE:    [
        "VISION_FRAME",
        "SCREEN_FRAME",
        "AUDIO_CHUNK",
        "LOCAL_MIC_PCM",
        "REMOTE_APP_PCM",
        "ASK_AI_PCM",
        "AI_PLAYBACK_DONE",
        "TRACE_CLIENT_EVENT",
        "MEETING_BINDING",
        "CAPTURE_HEALTH",
        "HOLD_TO_ASK_STATE",
        "END_NEGOTIATION",
        "STATE_UPDATE",
        "ASK_ADVICE",
        "SPEAKER_IDENTIFIED",
        "SPEAKER_STOPPED",
        "USER_ADDRESSING_AI",
        "START_COPILOT",
        "SET_RESPONSE_MODE",
        "SET_RESPONSE_LANGUAGE",
        "SPEAKER_MODE_CHANGE",
        "UTTERANCE_END",
        "SIMULATED_NEGOTIATION_TURN",
    ],
    NegotiationState.ENDING:    [],
}

# Error codes per state
ERROR_CODES: Dict[NegotiationState, Dict[str, str]] = {
    NegotiationState.IDLE:      {"code": "NOT_CONSENTED",   "message": "Please accept privacy terms first."},
    NegotiationState.CONSENTED: {"code": "NOT_STARTED",     "message": "Start a negotiation session first."},
    NegotiationState.ACTIVE:    {"code": "ALREADY_ACTIVE",  "message": "Session already in progress."},
    NegotiationState.ENDING:    {"code": "SESSION_ENDING",  "message": "Session is ending, please wait."},
}

class NegotiationEngine:
    @staticmethod
    async def validate_message(
        websocket: WebSocket,
        session: NegotiationSession,
        message_type: str
    ) -> bool:
        allowed = VALID_MESSAGES.get(session.state, [])
        # Skip logging for high-frequency messages to prevent I/O flooding
        _high_freq = {"AUDIO_CHUNK", "VISION_FRAME", "SCREEN_FRAME", "LOCAL_MIC_PCM", "REMOTE_APP_PCM"}
        if message_type not in _high_freq:
            logger.info(f"Validating message: {message_type}, state: {session.state}, allowed: {allowed}")
        if message_type not in allowed:
            # Silently drop early audio chunks to prevent log spam and frontend errors
            if message_type in {"AUDIO_CHUNK", "LOCAL_MIC_PCM", "REMOTE_APP_PCM"} and session.state in (NegotiationState.IDLE, NegotiationState.CONSENTED):
                return False

            error = ERROR_CODES.get(session.state, {"code": "INVALID_STATE", "message": "Invalid operation."})
            await websocket.send_json({"type": "ERROR", "payload": error})
            logger.warning(
                f"Rejected {message_type} in state {session.state} "
                f"[session={session.session_id}]"
            )
            return False
        return True

    @staticmethod
    async def transition_state(
        session: NegotiationSession,
        new_state: NegotiationState,
        websocket: WebSocket
    ) -> None:
        old_state = session.state
        session.state = new_state
        logger.info(
            f"State transition",
            extra={"old_state": old_state.value, "new_state": new_state.value, "session_id": session.session_id},
        )
        session_store.persist_session(session, ended=new_state == NegotiationState.IDLE)
        
        # Broadcast state transition to frontend
        await websocket.send_json({
            "type": "NEGOTIATION_STATE_CHANGED",
            "payload": {
                "previous_state": old_state.value,
                "current_state": new_state.value,
                "timestamp": time.time()
            }
        })

    @staticmethod
    async def handle_consent(session: NegotiationSession, payload: dict, websocket: WebSocket) -> None:
        session.consent_version = payload.get("version", "1.0")
        session.consent_mode = payload.get("mode", "live")
        if session.consent_mode == "roleplay" or settings.EVAL_MODE_ENABLED:
            session.session_resumable = False
        session.response_language = session.response_language or session.language or "en-US"
        await NegotiationEngine.transition_state(session, NegotiationState.CONSENTED, websocket)
        await websocket.send_json({
            "type": "CONSENT_ACKNOWLEDGED",
            "payload": {
                "mode": session.consent_mode,
                "recording_active": True
            }
        })
    
    @staticmethod
    async def handle_enrollment_start(session: NegotiationSession, payload: dict, websocket: WebSocket) -> None:
        """
        Start voice enrollment process.
        
        Creates an EnrollmentService instance and begins capturing 5 seconds of audio
        for voice fingerprint generation.
        
        Args:
            session: Current negotiation session
            payload: Empty payload (no parameters needed)
            websocket: WebSocket connection for sending enrollment status
        """
        from app.services.speaker_enrollment import SpeakerEnrollmentService
        
        logger.info(f"Enrollment start requested [session={session.session_id}]")
        
        # Create enrollment service instance
        session.enrollment_service = SpeakerEnrollmentService(session)
        
        # Start enrollment and send response to frontend
        result = await session.enrollment_service.start_enrollment()
        await websocket.send_json(result)
        
    @staticmethod
    async def handle_start(session: NegotiationSession, payload: dict, websocket: WebSocket, api_key: str) -> None:
        context = payload.get("context", "")
        user_context = payload.get("user_context", {})
        audio_eval_only = bool(payload.get("audio_eval_only"))
        session.context = context
        session.user_context = user_context
        session.api_key = api_key  # stored for auto-reconnect on 1007
        session.started_at = session.started_at or time.time()
        session.response_language = session.response_language or session.language or "en-US"
        if audio_eval_only:
            session.degraded_mode = "audio_eval_only"
        companion_runtime.apply_start_payload(session, payload)

        logger.info(
            "Starting new negotiation",
            extra={
                "session_id": session.session_id,
                "context": context,
                "user_context": user_context,
                "source_mode": session.source_mode,
                "meeting_binding": session.meeting_binding,
            },
        )

        await NegotiationEngine.transition_state(session, NegotiationState.ACTIVE, websocket)

        if not audio_eval_only:
            # Send "connecting" message to frontend so they know we're working on it
            try:
                await websocket.send_json({
                    "type": "AI_CONNECTING",
                    "payload": {"message": "Connecting to AI advisor..."}
                })
            except Exception:
                logger.warning(f"Failed to send AI_CONNECTING message (WebSocket may be closed)")
                # Don't fail here - continue trying to connect

        try:
            if audio_eval_only:
                logger.info(
                    "Starting audio-eval-only session without Gemini Live [session=%s]",
                    session.session_id,
                )
            else:
                live_session_cm = open_live_session(api_key=api_key, context=context)
                session.live_session_cm = live_session_cm
                
                # Add timeout to prevent hanging forever - increased to 60s for slower connections
                try:
                    logger.info(f"Attempting to establish Gemini Live connection [session={session.session_id}]")
                    session.live_session = await asyncio.wait_for(
                        live_session_cm.__aenter__(),
                        timeout=60.0  # 60 second timeout (increased from 30s)
                    )
                    logger.info(f"Gemini Live connection established successfully [session={session.session_id}]")
                except asyncio.TimeoutError:
                    logger.error(f"Gemini Live session connection timed out after 60s [session={session.session_id}]")
                    await websocket.send_json({
                        "type": "ERROR",
                        "payload": {"code": "CONNECTION_TIMEOUT", "message": "AI connection timed out. Please check your network and try again."}
                    })
                    await NegotiationEngine.transition_state(session, NegotiationState.IDLE, websocket)
                    return
                except Exception as e:
                    logger.error(f"Failed to establish Gemini Live connection: {e} [session={session.session_id}]", exc_info=True)
                    await websocket.send_json({
                        "type": "ERROR",
                        "payload": {"code": "CONNECTION_FAILED", "message": f"AI connection failed: {str(e)}"}
                    })
                    await NegotiationEngine.transition_state(session, NegotiationState.IDLE, websocket)
                    return

            # ── Dual-Model: initialise buffer + listener ─────────────────────
            audio_buffer = AudioBuffer(max_seconds=90)
            session.audio_buffer = audio_buffer
            session.speech_transcriber = SpeechTranscriptionService(session)

            # C4e — Async callback: forwards every ListenerAgent cycle to Live AI injector
            async def _context_ready_handler(ctx, evts):
                await NegotiationEngine._inject_context_to_live_ai(session, ctx, evts)

            listener = ListenerAgent(
                session=session,
                audio_buffer=audio_buffer,
                gemini_send_lock=session.gemini_send_lock,
                websocket=websocket,
                on_context_ready=_context_ready_handler,
            )
            session.listener_agent = listener
            listener.start()
            if session.source_mode == SourceMode.VIRTUAL_COMPANION_DESKTOP.value:
                logger.info(
                    "Companion mode activated",
                    extra={
                        "session_id": session.session_id,
                        "source_mode": session.source_mode,
                        "meeting_binding": session.meeting_binding,
                        "capture_preset": session.capture_preset,
                    },
                )
                # Pre-warm the gRPC/STT connection so the first real utterance
                # doesn't hit a 12-15s TLS cold-start delay.
                async def _warmup_stt():
                    is_desktop = getattr(session, "source_mode", None) == SourceMode.VIRTUAL_COMPANION_DESKTOP.value
                    if is_desktop:
                        logger.info("Skipping batch STT warmup for desktop companion session [session=%s]", session.session_id)
                        return
                    try:
                        from app.services.stt_service import SpeechTranscriptionService as _STT
                        from app.services.utterance_types import FinalizedUtterance as _FU
                        import time as _time
                        _svc = _STT(session)
                        _dummy = _FU(
                            utterance_id="warmup",
                            audio=b"\x00" * 3200,  # 100 ms silence
                            started_at=_time.time(),
                            ended_at=_time.time() + 0.1,
                            duration_ms=100,
                            rms=0.0,
                            source="warmup",
                            speaker="user",
                            speaker_confidence=1.0,
                        )
                        await _svc.transcribe(_dummy)
                        logger.info("STT gRPC warmup complete [session=%s]", session.session_id)
                    except Exception as _exc:
                        logger.debug("STT warmup (non-fatal): %s", _exc)
                asyncio.create_task(_warmup_stt())
            else:
                SpeakerMappingService(session).begin_calibration()
                log_speaker_debug(
                    "SESSION_SPEAKER_PATH",
                    session_id=session.session_id,
                    speaker_mode=session.speaker_mode,
                    speechbrain_enabled=settings.SPEECHBRAIN_ENABLED,
                    transcription_provider=settings.TRANSCRIPTION_PROVIDER,
                    flow="browser_pcm -> utterance_end -> google_stt_diarization -> speechbrain_mapping",
                    realtime_speaker_service_enabled=False,
                )
            
            # Single active path: browser PCM -> utterance finalization -> Google STT -> SpeechBrain mapping.
            
            # Initialize SpeakerService if speaker recognition is enabled (Requirement 6.3)
            if False and (
                settings.SPEAKER_RECOGNITION_ENABLED
                and (settings.RESEMBLYZER_ENABLED or settings.SPEECHBRAIN_ENABLED)
                and session.speaker_mode == "auto"
            ):
                try:
                    from app.services.speaker_service import SpeakerService
                    
                    # Create callback for segment completion (VAD detected silence after speech)
                    async def on_segment_complete(speaker: str, audio: bytes, timestamp: float, speaker_changed: bool):
                        """Handle automatic segment completion - transcribe every segment."""
                        duration_s = len(audio) / 32000
                        logger.info(f"🎤 Auto segment complete: {speaker} ({duration_s:.1f}s, changed={speaker_changed})")
                        
                        # Transcribe this segment with the identified speaker
                        if session.listener_agent and len(audio) >= 3200:  # at least 0.1s
                            asyncio.create_task(
                                session.listener_agent.transcribe_segment(
                                    speaker=speaker,
                                    audio=audio,
                                    start_time=timestamp - duration_s,
                                    end_time=timestamp,
                                )
                            )
                    
                    session.speaker_service = SpeakerService(session, on_segment_complete_callback=None)
                    logger.info(f"SpeakerService initialized [session={session.session_id}]")
                except Exception as e:
                    logger.error(f"Failed to initialize SpeakerService: {e}", exc_info=True)
                    # Graceful degradation: continue without speaker recognition
            # ─────────────────────────────────────────────────────────────────

            if session.live_session:
                session.live_session_receive_task = asyncio.create_task(
                    receive_responses(session.live_session, websocket, session.session_id, session)
                )
                session.live_session_keepalive_task = asyncio.create_task(keepalive_ping(session))

            # Try to send SESSION_STARTED, but handle WebSocket disconnect gracefully
            try:
                await websocket.send_json({
                    "type": "SESSION_STARTED",
                    "payload": {
                        "session_id": session.session_id,
                        "model": (settings.GEMINI_MODEL if session.live_session else "disabled"),
                        "features": {
                            "audio": True,
                            "vision": settings.VISION_ENABLED,
                            "web_search": bool(session.live_session),
                            "dual_model": False,
                            "persistence": False,
                            "session_resume": False,
                            "audio_eval_only": audio_eval_only,
                            "source_mode": session.source_mode,
                            "companion_mode": session.source_mode == SourceMode.VIRTUAL_COMPANION_DESKTOP.value,
                        }
                    }
                })
                await websocket.send_json({
                    "type": "PERSISTENCE_STATUS",
                    "payload": {"ready": False, "session_id": session.session_id},
                })
                await websocket.send_json({
                    "type": "LANGUAGE_UPDATE",
                    "payload": {
                        "language": session.language,
                        "response_language": session.response_language,
                    },
                })
            except Exception as ws_error:
                logger.warning(
                    f"Failed to send SESSION_STARTED (WebSocket closed): {ws_error} "
                    f"[session={session.session_id}]"
                )
                # WebSocket is closed, clean up the Gemini session
                if session.listener_agent:
                    await session.listener_agent.stop()
                    session.listener_agent = None
                if session.live_session_cm:
                    try:
                        await session.live_session_cm.__aexit__(None, None, None)
                    except Exception:
                        pass
                    session.live_session = None
                raise  # Re-raise to trigger outer exception handler
                
        except Exception as e:
            logger.error(f"Failed to start Gemini session", exc_info=True, extra={"session_id": session.session_id})
            # Only try to send error if WebSocket is still open
            try:
                await websocket.send_json({
                    "type": "ERROR",
                    "payload": {"code": "GEMINI_UNAVAILABLE", "message": "AI service unavailable. Please try again."}
                })
            except Exception:
                logger.warning(f"Could not send error message (WebSocket closed) [session={session.session_id}]")
            
            # Clean up and transition back to IDLE
            try:
                await NegotiationEngine.transition_state(session, NegotiationState.IDLE, websocket)
            except Exception:
                logger.warning(f"Could not transition to IDLE (WebSocket closed) [session={session.session_id}]")

    @staticmethod
    async def handle_vision_frame(session: NegotiationSession, payload: dict, websocket: WebSocket | None = None) -> None:
        """Two-tier vision routing:

        Tier 1 — Continuous Pro Analysis (all frames):
          Scene-change detection → ring buffer → Pro call every ~3s when scene changed.
          Result stored in session.vision_observations and broadcast as VISION_INTEL.

        Tier 2 — Live Vision (during hold-to-talk only):
          Frames also forwarded to Gemini Live via send_realtime_input so the Live
          model can see while listening and responding.
        """
        # payload["image"] can be None if key exists but value is None — use `or ""`
        image_b64 = payload.get("image") or ""
        if not image_b64:
            return

        import hashlib as _hashlib

        # Robustly decode: strip whitespace/newlines that JSON encoding may inject,
        # fix missing padding, handle both str and bytes input.
        try:
            raw = image_b64 if isinstance(image_b64, (str, bytes)) else str(image_b64)
            if isinstance(raw, str):
                raw = raw.strip().replace("\n", "").replace("\r", "").replace(" ", "")
            # Add padding if necessary (base64 strings must be a multiple of 4 bytes)
            if isinstance(raw, str):
                padding_needed = (4 - len(raw) % 4) % 4
                raw = raw + "=" * padding_needed
            frame_bytes = base64.b64decode(raw)
        except Exception as decode_exc:
            logger.warning(
                "[Vision] Failed to decode base64 frame type=%s value_len=%s exc=%s [session=%s]",
                type(image_b64).__name__,
                len(image_b64) if hasattr(image_b64, "__len__") else "?",
                decode_exc,
                session.session_id,
            )
            return

        is_live_mode = bool(payload.get("live_mode", False)) or (session.source_mode == SourceMode.VIRTUAL_COMPANION_DESKTOP.value)
        now = time.time()

        # ── Tier 2: forward to Gemini Live during hold-to-talk ────────────────
        if is_live_mode and session.live_session:
            session.vision_live_pending_frame_b64 = image_b64
            if session.vision_live_send_task is None or session.vision_live_send_task.done():
                session.vision_live_send_task = asyncio.create_task(
                    NegotiationEngine._drain_live_vision_frames(session),
                    name=f"vision-live-{session.session_id[:8]}",
                )

        # ── Tier 1: scene-change detection + Pro analysis ─────────────────────
        if not settings.VISION_PRO_ENABLED:
            return

        # Compute a lightweight hash of a 64×64 thumbnail for scene-change detection.
        # We use a simple approach: take every Nth byte of the JPEG to approximate
        # a thumbnail fingerprint without decoding the full image.
        sample_step = max(1, len(frame_bytes) // 4096)
        sample = bytes(frame_bytes[i] for i in range(0, len(frame_bytes), sample_step))
        frame_hash = _hashlib.md5(sample).hexdigest()

        # Check scene similarity against last stored hash
        last_hash = session.vision_last_hash
        scene_changed = (not last_hash) or (frame_hash != last_hash)

        if not scene_changed:
            # Scene is similar — don't burn Pro budget
            return

        # Scene changed: update hash, buffer the frame
        session.vision_last_hash = frame_hash
        max_frames = max(1, settings.VISION_PRO_MAX_FRAMES)
        session.vision_frame_buffer.append(frame_bytes)
        if len(session.vision_frame_buffer) > max_frames:
            session.vision_frame_buffer = session.vision_frame_buffer[-max_frames:]
        session.vision_needs_analysis = True

        # Determine cooldown based on whether Live mode is active (slower rate during Live)
        cooldown = (
            settings.VISION_PRO_LIVE_COOLDOWN_SECONDS if is_live_mode
            else settings.VISION_PRO_COOLDOWN_SECONDS
        )
        enough_frames = len(session.vision_frame_buffer) >= settings.VISION_PRO_MIN_FRAMES
        cooldown_elapsed = (now - session.vision_last_pro_call_at) >= cooldown

        if not (enough_frames and cooldown_elapsed and session.vision_needs_analysis):
            return

        if session.vision_analysis_task and not session.vision_analysis_task.done():
            return

        # Snapshot the buffer and launch Pro analysis as a background task
        frames_to_analyze = list(session.vision_frame_buffer)
        session.vision_needs_analysis = False
        session.vision_last_pro_call_at = now

        # Build transcript hint from last 2 transcript entries
        transcript_hint = ""
        if session.listener_agent and hasattr(session.listener_agent, "accumulated_transcript"):
            full = session.listener_agent.accumulated_transcript or ""
            lines = [l.strip() for l in full.strip().splitlines() if l.strip()]
            transcript_hint = "\n".join(lines[-2:])

        session_context = (
            f"Negotiating {session.context or 'unknown item'}. "
            f"User: {session.user_context.get('item', '') if isinstance(session.user_context, dict) else ''}"
        ).strip()

        async def _run_vision_analysis():
            from app.services.gemini_client import analyze_vision_frames
            from app.ai_assets import build_vision_intel_block

            obs = await analyze_vision_frames(
                session=session,
                frames=frames_to_analyze,
                transcript_hint=transcript_hint,
                session_context=session_context,
            )
            if obs is None:
                return

            # Store observation
            session.vision_observations.append(obs)
            session.vision_observations = session.vision_observations[-settings.VISION_OBS_MAX_HISTORY:]

            # Log metadata only (no raw image bytes)
            event_payload = {
                "timestamp": int(obs["timestamp"] * 1000),
                "event": "vision_intel",
                "scene_type": obs.get("scene_type"),
                "confidence": obs.get("confidence"),
                "frame_count": obs.get("frame_count", len(frames_to_analyze)),
            }
            session.vision_history.append(event_payload)
            session.vision_history = session.vision_history[-settings.RESEARCH_HISTORY_LIMIT:]
            session_store.record_vision_event(session.session_id, event_payload)

            # Broadcast VISION_INTEL to frontend
            if websocket is not None:
                try:
                    await websocket.send_json({
                        "type": "VISION_INTEL",
                        "payload": {
                            "scene_type": obs.get("scene_type"),
                            "scene_summary": obs.get("scene_summary"),
                            "item": obs.get("item"),
                            "condition": obs.get("condition"),
                            "defects_visible": obs.get("defects_visible") or [],
                            "document_text": obs.get("document_text"),
                            "prices_visible": obs.get("prices_visible") or [],
                            "terms_visible": obs.get("terms_visible") or [],
                            "body_language": obs.get("body_language") or {},
                            "confidence": obs.get("confidence"),
                            "advice_hint": obs.get("advice_hint"),
                            "timestamp": obs["timestamp"],
                            "frame_count": obs.get("frame_count"),
                        },
                    })
                except Exception as ws_exc:
                    logger.warning("[Vision] Failed to send VISION_INTEL ws error=%s", ws_exc)

        session.vision_analysis_task = asyncio.create_task(
            _run_vision_analysis(),
            name=f"vision-pro-{session.session_id[:8]}",
        )

    @staticmethod
    async def _drain_live_vision_frames(session: NegotiationSession) -> None:
        try:
            while session.live_session and session.state == NegotiationState.ACTIVE:
                frame = session.vision_live_pending_frame_b64
                if not frame:
                    break

                if not session.user_addressing_ai or session.direct_query_in_flight:
                    session.vision_live_pending_frame_b64 = None
                    break

                wait_for = settings.VISION_LIVE_SEND_INTERVAL_SECONDS - (
                    time.time() - session.vision_live_last_sent_at
                )
                if wait_for > 0:
                    await asyncio.sleep(wait_for)

                frame = session.vision_live_pending_frame_b64
                if not frame:
                    break

                session.vision_live_pending_frame_b64 = None
                try:
                    async with session.gemini_send_lock:
                        await send_vision_frame(session.live_session, frame, session.session_id)
                    session.vision_live_last_sent_at = time.time()
                except Exception as exc:
                    session.vision_live_drop_count += 1
                    logger.warning("[Vision] Live frame dropped [session=%s]: %s", session.session_id, exc)
                    break
        finally:
            session.vision_live_send_task = None

    @staticmethod
    async def handle_audio_chunk(session: NegotiationSession, raw_bytes: bytes) -> None:
        if session.live_session or session.degraded_mode == "audio_eval_only":
            if getattr(session, "user_addressing_ai", False):
                # ── Ask AI mode ──────────────────────────────────────────────
                # Capture audio locally for question transcription.
                # Do NOT push to listener buffer (prevents question from
                # polluting negotiation context extraction).
                # Do NOT stream to Live AI (we'll send as text after transcription).
                session.question_capture_bytes += raw_bytes
            elif session.audio_buffer and session.current_speaker != "ai":
                # ── Normal negotiation mode ──────────────────────────────────
                # Push to listener buffer for context extraction.
                session.audio_buffer.push(raw_bytes)
                # Accumulate into the per-segment buffer so that on the next speaker
                # button click we transcribe EXACTLY the audio captured during this
                # speaker's turn — no timestamp arithmetic, no clock-drift issues.
                session.current_segment_audio += raw_bytes
                session.pending_utterance_audio += raw_bytes
                
                # 15.5: Cap current_segment_audio at 120 seconds
                # Evict old audio when exceeds 120s (Requirement 13.5)
                # 120 seconds at 16kHz, 16-bit mono = 120 * 16000 * 2 = 3,840,000 bytes
                MAX_SEGMENT_BYTES = 120 * 32000  # 3,840,000 bytes
                if len(session.current_segment_audio) > MAX_SEGMENT_BYTES:
                    # Keep only the last 120 seconds
                    session.current_segment_audio = session.current_segment_audio[-MAX_SEGMENT_BYTES:]
                
                # ── Audio Routing ────────────────────────
                # Route audio to appropriate service based on what's enabled
                # No parallel speaker classification or legacy listener path here.

    @staticmethod
    async def handle_companion_audio(
        session: NegotiationSession,
        websocket: WebSocket,
        payload: dict,
        message_type: str,
    ) -> None:
        await companion_runtime.handle_audio_payload(session, websocket, payload, message_type)

    @staticmethod
    async def handle_meeting_binding(session: NegotiationSession, payload: dict, websocket: WebSocket) -> None:
        binding = companion_runtime.update_meeting_binding(session, payload)
        session_store.persist_session(session, ended=False)
        await websocket.send_json(
            {
                "type": "MEETING_BINDING_UPDATE",
                "payload": {
                    "binding": binding.model_dump(),
                    "source_mode": session.source_mode,
                },
            }
        )

    @staticmethod
    async def handle_capture_health(session: NegotiationSession, payload: dict, websocket: WebSocket) -> None:
        health = companion_runtime.update_capture_health(session, payload)
        session_store.persist_session(session, ended=False)
        await websocket.send_json(
            {
                "type": "CAPTURE_HEALTH_UPDATE",
                "payload": {
                    "health": health.model_dump(),
                    "source_mode": session.source_mode,
                },
            }
        )
        if session.degraded_mode:
            await websocket.send_json(
                {
                    "type": "DEGRADED_MODE_UPDATE",
                    "payload": {
                        "active": True,
                        "mode": session.degraded_mode,
                        "reasons": list(session.degraded_reasons),
                    },
                }
            )

    @staticmethod
    async def handle_screen_frame(session: NegotiationSession, payload: dict, websocket: WebSocket) -> None:
        screen_payload = dict(payload)
        screen_payload.setdefault("source", "meeting_window")
        screen_payload.setdefault("source_mode", session.source_mode)
        await NegotiationEngine.handle_vision_frame(session, screen_payload, websocket)

    @staticmethod
    async def handle_end(session: NegotiationSession, payload: dict, websocket: WebSocket) -> None:
        await NegotiationEngine.transition_state(session, NegotiationState.ENDING, websocket)

        session.final_price = payload.get("final_price")
        session.initial_price = payload.get("initial_price")

        if session.listener_agent:
            await session.listener_agent.stop()
            session.listener_agent = None

        if session.enrollment_service:
            session.enrollment_service.cleanup()
            session.enrollment_service = None
            logger.info(f"EnrollmentService cleaned up [session={session.session_id}]")

        # Clear user embedding and enrollment audio from memory (Requirement 13.4)
        if session.enrollment_audio is not None:
            session.enrollment_audio = None
            logger.info(f"Enrollment audio cleared from memory [session={session.session_id}]")

        speechbrain_service.cleanup_session_state(session)
        logger.info(f"SpeechBrain session state cleaned up [session={session.session_id}]")
        session.pending_intel_context = None
        session.pending_intel_critical_events.clear()
        session.vision_live_pending_frame_b64 = None

        if getattr(session, "live_session_cm", None):
            try:
                await session.live_session_cm.__aexit__(None, None, None)
            except Exception:
                pass
            session.live_session = None

        for task_attr in (
            "live_session_receive_task",
            "live_session_keepalive_task",
            "live_session_monitor_task",
            "live_reconnect_task",
            "vision_live_send_task",
            "vision_analysis_task",
            "intel_injection_task",
        ):
            task = getattr(session, task_attr, None)
            if task:
                task.cancel()
                setattr(session, task_attr, None)

        logger.info(
            "Session summary",
            extra={
                "session_id": session.session_id,
                **session.session_metrics,
                "speechbrain_verification_attempts": session.speechbrain_verification_attempts,
                "speechbrain_verification_successes": session.speechbrain_verification_successes,
                "speechbrain_verification_failures": session.speechbrain_verification_failures,
                "mapping_state_transitions": session.mapping_state_transitions,
            },
        )
        logger.info(
            "SESSION_COST_SUMMARY %s",
            json.dumps(
                {
                    "session_id": session.session_id,
                    "mapping_state_summary": {
                        "state": session.speaker_mapping_state,
                        "mapping": session.speaker_mapping,
                        "contradictions": session.mapping_contradiction_count,
                    },
                    "speechbrain_counters": {
                        "verification_attempts": session.speechbrain_verification_attempts,
                        "verification_successes": session.speechbrain_verification_successes,
                        "verification_failures": session.speechbrain_verification_failures,
                        "verification_calls": session.session_metrics.get("speechbrain_verification_calls", 0),
                        "ambiguous_turns": session.session_metrics.get("speechbrain_ambiguous_turns", 0),
                    },
                    "google_stt_minutes": session.session_metrics.get("google_stt_minutes", 0.0),
                    "gemini_live_input_tokens": session.session_metrics.get("gemini_live_input_tokens", 0),
                    "gemini_live_output_tokens": session.session_metrics.get("gemini_live_output_tokens", 0),
                    "research_call_count": session.session_metrics.get("research_calls", 0),
                    "capability_path": capability_registry.active_path(),
                }
            ),
        )
        session_store.persist_session(session, ended=True)

        await websocket.send_json({
            "type": "OUTCOME_SUMMARY",
            "payload": {
                "deal_reached": session.final_price is not None,
                "initial_price": session.initial_price,
                "final_price": session.final_price,
                "savings": None,
                "savings_percentage": None,
                "market_value": None,
                "vs_market": None,
                "negotiation_duration_seconds": 0,
                "key_moves": [],
                "effectiveness_score": 0.0,
                "transcript_summary": ""
            }
        })
        await NegotiationEngine.transition_state(session, NegotiationState.IDLE, websocket)
    @staticmethod
    async def handle_state_update(session: NegotiationSession, payload: dict, websocket: WebSocket) -> None:
        """
        Handle STATE_UPDATE message from AI.
        AI extracts negotiation context from transcript and sends updates.

        Args:
            session: Current negotiation session
            payload: State updates from AI (item, prices, etc.)
            websocket: WebSocket connection to forward to frontend
        """
        logger.info(f"AI state update received [session={session.session_id}]: {payload}")       
        
        # Forward state update to frontend
        await websocket.send_json({
            "type": "STATE_UPDATE",
            "payload": payload
        })


    @staticmethod
    async def handle_speaker_identified(session: NegotiationSession, payload: dict, websocket: WebSocket, is_automatic: bool = False) -> None:
        """
        Handle SPEAKER_IDENTIFIED message from frontend voice fingerprinting or automatic classification.
        
        Updates the current speaker label and flushes any buffered transcripts
        with the correct speaker label.

        Args:
            session: Current negotiation session
            payload: Contains speaker label ('user' or 'counterparty') and timestamp (in milliseconds)
            websocket: WebSocket connection for sending buffered transcripts
            is_automatic: True if called from automatic classification, False if from manual frontend button
        """
        speaker = payload.get("speaker", "user")
        timestamp_ms = payload.get("timestamp", time.time() * 1000)
        
        # Convert frontend timestamp from milliseconds to seconds
        timestamp = timestamp_ms / 1000.0
        
        # Detect speaker change
        speaker_changed = session.current_speaker != speaker
        is_first_identification = session.speaker_last_updated == 0
        
        # Only disable automatic recognition if this is a manual button click
        # Automatic classifications should not disable the automatic system
        if not is_automatic:
            # Once a speaker button is clicked, disable automatic recognition permanently
            # (for the lifetime of this session). Only manual button clicks determine who spoke.
            session.manual_override_until = float('inf')
        
        # Store current speaker in session
        previous_speaker = session.current_speaker
        session.current_speaker = speaker
        session.speaker_last_updated = timestamp

        # Append to speaker timeline for ListenerAgent window attribution
        session.speaker_timeline.append({
            "speaker": speaker,
            "timestamp": timestamp,
        })
        # Keep only the last 5 minutes of timeline entries (cap at 300 entries at ~1/s)
        if len(session.speaker_timeline) > 300:
            session.speaker_timeline = session.speaker_timeline[-300:]
        
        # ═══════════════════════════════════════════════════════════════════
        # 🎯 BACKEND SPEAKER IDENTIFICATION LOG
        # ═══════════════════════════════════════════════════════════════════
        source = "AUTOMATIC" if is_automatic else "FRONTEND"
        log_speaker_debug(
            "SPEAKER_IDENTIFIED",
            session_id=session.session_id,
            source=source.lower(),
            previous_speaker=previous_speaker,
            new_speaker=speaker,
            speaker_mode=session.speaker_mode,
            speaker_changed=speaker_changed,
            first_identification=is_first_identification,
            manual_override_until=session.manual_override_until,
            timeline_size=len(session.speaker_timeline),
        )
        logger.info("=" * 70)
        logger.info(f"� SPEAKER IDENTIFICATION RECEIVED FROM {source}")
        logger.info("=" * 70)
        logger.info(f"📊 Speaker: {speaker.upper()}")
        logger.info(f"⏰ Timestamp: {timestamp}")
        logger.info(f"🔄 Speaker Changed: {speaker_changed}")
        logger.info(f"🆕 First Identification: {is_first_identification}")
        logger.info(f"📝 Session ID: {session.session_id}")
        
        if is_first_identification:
            logger.info(f"✓ First speaker identified: {speaker.upper()} [session={session.session_id}]")
        elif speaker_changed:
            logger.info(f"✓ Speaker changed: {session.current_speaker.upper()} → {speaker.upper()} [session={session.session_id}]")
        else:
            logger.info(f"✓ Speaker confirmed: {speaker.upper()} [session={session.session_id}]")
        
        # ── Event-driven segment transcription ──────────────────────────────
        # Button switch = previous speaker's turn is now complete.
        # Take the audio accumulated in current_segment_audio (filled by handle_audio_chunk)
        # — this is EXACTLY the audio from the last button click to now, no timestamp
        # arithmetic or clock-drift involved.
        prev_speaker = session.speaker_segment_speaker
        if speaker_changed and session.listener_agent:
            segment_audio = session.current_segment_audio
            seg_start_ts = session.speaker_segment_start  # for timestamp display only
            seg_end_ts = timestamp
            if len(segment_audio) >= 3200:  # at least 0.1s
                duration_s = len(segment_audio) / 32000
                logger.info(
                    f"[Engine] Transcribing {prev_speaker} segment: "
                    f"{duration_s:.1f}s ({len(segment_audio)} bytes)"
                )
                asyncio.create_task(
                    session.listener_agent.transcribe_segment(
                        speaker=prev_speaker,
                        audio=segment_audio,
                        start_time=seg_start_ts,
                        end_time=seg_end_ts,
                    )
                )
            else:
                logger.debug(f"[Engine] Segment too short ({len(segment_audio)} bytes), skipping")

        # Reset segment buffer and update speaker tracking for the new turn
        session.current_segment_audio = b""
        session.speaker_segment_start = timestamp
        session.speaker_segment_speaker = speaker

        # Flush any buffered transcripts — keep each transcript's ORIGINAL speaker label.
        # The label is frozen at capture time, never overwritten by a later button click.
        if session.pending_transcripts:
            logger.info(f"🔓 FLUSHING {len(session.pending_transcripts)} buffered transcripts (labels preserved)")
            for buffered_transcript in session.pending_transcripts:
                # Only fill in "unknown" labels with the PREVIOUS speaker (not the new one)
                if buffered_transcript.get("speaker") == "unknown":
                    buffered_transcript["speaker"] = prev_speaker if prev_speaker != "unknown" else speaker
                await websocket.send_json({
                    "type": "TRANSCRIPT_UPDATE",
                    "payload": buffered_transcript
                })
            session.pending_transcripts = []
        else:
            logger.info("📭 No buffered transcripts to flush")
        
        logger.info("=" * 70)
        logger.info(f"✅ SPEAKER IDENTIFICATION COMPLETE: {speaker.upper()}")
        logger.info(f"   Future transcripts will be labeled as: {speaker.upper()}")
        logger.info("=" * 70)
        logger.info("")

    @staticmethod
    async def route_message(websocket: WebSocket, session: NegotiationSession, msg_type: str, payload: dict) -> None:
        # VISION_FRAME and AUDIO_CHUNK arrive at high frequency — never log their payload
        # (logging a 31KB base64 image to disk 3×/sec blocks the entire event loop)
        _high_freq = {"AUDIO_CHUNK", "VISION_FRAME", "SCREEN_FRAME", "LOCAL_MIC_PCM", "REMOTE_APP_PCM"}
        if msg_type not in _high_freq:
            logger.info(
                f"Routing message: {msg_type}",
                extra={"message_type": msg_type, "payload": payload, "session_id": session.session_id},
            )
        if msg_type == "PRIVACY_CONSENT_GRANTED":
            await NegotiationEngine.handle_consent(session, payload, websocket)
        elif msg_type == "START_NEGOTIATION":
            await NegotiationEngine.handle_start(session, payload, websocket, settings.GEMINI_API_KEY)
        elif msg_type == "ENROLLMENT_START":
            # Voice enrollment: Start capturing user voice
            await NegotiationEngine.handle_enrollment_start(session, payload, websocket)
        elif msg_type == "VISION_FRAME":
            await NegotiationEngine.handle_vision_frame(session, payload, websocket)
        elif msg_type == "SCREEN_FRAME":
            await NegotiationEngine.handle_screen_frame(session, payload, websocket)
        elif msg_type == "LOCAL_MIC_PCM":
            await NegotiationEngine.handle_companion_audio(session, websocket, payload, msg_type)
        elif msg_type == "REMOTE_APP_PCM":
            await NegotiationEngine.handle_companion_audio(session, websocket, payload, msg_type)
        elif msg_type == "ASK_AI_PCM":
            await NegotiationEngine.handle_companion_audio(session, websocket, payload, msg_type)
        elif msg_type == "TRACE_CLIENT_EVENT":
            await NegotiationEngine.handle_trace_client_event(session, payload, websocket)
        elif msg_type == "MEETING_BINDING":
            await NegotiationEngine.handle_meeting_binding(session, payload, websocket)
        elif msg_type == "CAPTURE_HEALTH":
            await NegotiationEngine.handle_capture_health(session, payload, websocket)
        elif msg_type == "HOLD_TO_ASK_STATE":
            await NegotiationEngine.handle_user_addressing_ai(session, payload, websocket)
        elif msg_type == "END_NEGOTIATION":
            await NegotiationEngine.handle_end(session, payload, websocket)
        elif msg_type == "STATE_UPDATE":
            # Button-triggered system: AI sends state updates
            await NegotiationEngine.handle_state_update(session, payload, websocket)
        elif msg_type == "ASK_ADVICE":
            # Button-triggered system: User requests AI advice
            await NegotiationEngine.handle_ask_advice(session, payload, websocket)
        elif msg_type == "SPEAKER_IDENTIFIED":
            # Voice fingerprinting: Frontend identified speaker
            await NegotiationEngine.handle_speaker_identified(session, payload, websocket)
        elif msg_type == "SPEAKER_STOPPED":
            # VAD: User stopped speaking
            await NegotiationEngine.handle_speaker_stopped(session, websocket)
        elif msg_type == "USER_ADDRESSING_AI":
            # Long-press trigger: toggle audio gate to Live AI
            await NegotiationEngine.handle_user_addressing_ai(session, payload, websocket)
        elif msg_type == "START_COPILOT":
            # Copilot activation: start proactive monitoring mode
            await NegotiationEngine.handle_start_copilot(session, payload, websocket)
        elif msg_type == "SET_RESPONSE_MODE":
            # Set response mode (advice or command) for when user presses and holds
            await NegotiationEngine.handle_set_response_mode(session, payload, websocket)
        elif msg_type == "SET_RESPONSE_LANGUAGE":
            await NegotiationEngine.handle_set_response_language(session, payload, websocket)
        elif msg_type == "SPEAKER_MODE_CHANGE":
            # Toggle speaker mode (auto or manual)
            await NegotiationEngine.handle_speaker_mode_change(session, payload, websocket)
        elif msg_type == "UTTERANCE_END":
            await NegotiationEngine.handle_utterance_end(session, payload, websocket)
        elif msg_type == "SIMULATED_NEGOTIATION_TURN":
            await NegotiationEngine.handle_simulated_negotiation_turn(session, payload, websocket)
        elif msg_type == "AI_PLAYBACK_DONE":
            session.ai_audio_playing = False
            session.last_ai_audio_played_at = time.time()
            logger.debug("AI audio playback finished — REMOTE_APP_PCM resumed [session=%s]", session.session_id)
        else:
            logger.warning(f"Unknown message type {msg_type}")
    @staticmethod
    async def handle_trace_client_event(session: NegotiationSession, payload: dict, websocket: WebSocket) -> None:
        from app.utils.session_trace import get_session_trace
        trace = get_session_trace(session.session_id)
        if trace:
            trace.record(
                category=payload.get("surface") or "client",
                name=payload.get("event_name") or "generic_client_event",
                summary=payload.get("summary") or "",
                data=payload.get("detail") or {},
            )
    @staticmethod
    async def handle_speaker_stopped(session: NegotiationSession, websocket: WebSocket) -> None:
        """
        Handle SPEAKER_STOPPED message from frontend VAD.
        
        When user_addressing_ai is True, the user is directly speaking to the AI copilot.
        We no longer need to manually signal turn completion here because Gemini's
        native VAD handles natural pauses, and the long-press button release
        (USER_ADDRESSING_AI=OFF) handles explicit turn completion.
      
        If we send ActivityEnd here while the user is still holding the button, 
        it desynchronizes the turn state and causes the AI to get stuck.
        """
        pass

    @staticmethod
    async def handle_simulated_negotiation_turn(session: NegotiationSession, payload: dict, websocket: WebSocket) -> None:
        """Inject a text-only turn for real Live AI evaluation runs."""
        if not settings.EVAL_MODE_ENABLED:
            await websocket.send_json({
                "type": "ERROR",
                "payload": {
                    "code": "EVAL_MODE_DISABLED",
                    "message": "SIMULATED_NEGOTIATION_TURN requires EVAL_MODE_ENABLED=true.",
                },
            })
            return
        if not session.listener_agent:
            await websocket.send_json({
                "type": "ERROR",
                "payload": {
                    "code": "NO_LISTENER_AGENT",
                    "message": "Start the negotiation before injecting simulated turns.",
                },
            })
            return

        speaker = payload.get("speaker", "unknown")
        text = payload.get("text", "")
        transcript_entry = await session.listener_agent.ingest_simulated_turn(
            speaker=speaker,
            text=text,
            timestamp_ms=payload.get("timestamp_ms"),
            scenario_id=payload.get("scenario_id"),
            turn_id=payload.get("turn_id"),
        )
        if transcript_entry:
            await websocket.send_json({
                "type": "SIMULATED_TURN_ACCEPTED",
                "payload": {
                    "id": transcript_entry["id"],
                    "speaker": transcript_entry["speaker"],
                    "scenario_id": transcript_entry.get("scenario_id"),
                },
            })

    @staticmethod
    async def handle_utterance_end(session: NegotiationSession, payload: dict, websocket: WebSocket) -> None:
        """Finalize a browser-owned utterance and send it through STT + speaker verification."""
        if not session.listener_agent:
            return

        audio = session.pending_utterance_audio
        session.pending_utterance_audio = b""
        if not audio:
            return

        started_at = float(payload.get("started_at") or time.time())
        ended_at = float(payload.get("ended_at") or time.time())
        duration_ms = int(payload.get("duration_ms") or max(0, (ended_at - started_at) * 1000))
        rms = float(payload.get("rms") or 0.0)
        utterance_id = payload.get("utterance_id") or f"utt_{int(ended_at * 1000)}"

        if duration_ms < settings.MIN_TRANSCRIBE_DURATION_MS and rms <= 0:
            return

        utterance = FinalizedUtterance(
            utterance_id=utterance_id,
            audio=audio,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
            rms=rms,
            source=settings.TRANSCRIPTION_PROVIDER,
        )

        # In manual mode: speaker label comes from the button click, not from here.
        # UTTERANCE_END in manual mode only captures audio into pending_utterance_audio
        # (already done above). Transcription is handled by transcribe_segment() when
        # the button is clicked — so we skip STT here to prevent double transcripts.
        if session.speaker_mode == "manual":
            return

        # AUTO MODE: Always run SpeechBrain classification for EVERY utterance.
        # BUG FIX: the old code only ran classify_utterance() when current_speaker
        # was "unknown". After the first utterance set current_speaker="user", every
        # subsequent utterance inherited "user" without re-checking — causing ElevenLabs
        # voices, the counterparty, and any other speaker to always be labeled "user".
        if (
            session.speaker_mode == "auto"
            and settings.SPEAKER_RECOGNITION_ENABLED
            and settings.SPEECHBRAIN_ENABLED
            and session.user_embedding is not None
        ):
            try:
                if session.speaker_service is None:
                    from app.services.speaker_service import SpeakerService
                    session.speaker_service = SpeakerService(session, on_segment_complete_callback=None)
                classified_speaker, classified_confidence = await session.speaker_service.classify_utterance(
                    audio,
                    duration_ms=duration_ms,
                    transcription_confidence=None,
                    utterance_id=utterance_id,
                    timestamp=ended_at,
                )
                utterance.speaker = classified_speaker
                utterance.speaker_confidence = classified_confidence
                log_speaker_debug(
                    "UTTERANCE_CLASSIFIED",
                    session_id=session.session_id,
                    utterance_id=utterance_id,
                    classified_speaker=classified_speaker,
                    classified_confidence=classified_confidence,
                    duration_ms=duration_ms,
                    audio_bytes=len(audio),
                )
            except Exception as exc:
                logger.warning(
                    "Utterance speaker classification failed [session=%s utterance=%s]: %s",
                    session.session_id,
                    utterance_id,
                    exc,
                )
            if utterance.speaker not in {"user", "counterparty"}:
                # Not classified yet — fall back to last known speaker as hint
                utterance.speaker = session.current_speaker if session.current_speaker in {"user", "counterparty"} else "unknown"
        else:
            # No SpeechBrain — use last known speaker
            utterance.speaker = session.current_speaker if session.current_speaker in {"user", "counterparty"} else "unknown"

        log_speaker_debug(
            "UTTERANCE_END",
            session_id=session.session_id,
            utterance_id=utterance_id,
            speaker_mode=session.speaker_mode,
            current_speaker=session.current_speaker,
            assigned_speaker=utterance.speaker,
            duration_ms=duration_ms,
            rms=round(rms, 4),
            audio_bytes=len(audio),
            speechbrain_profile_state=session.speechbrain_profile_state,
            mapping_state=session.speaker_mapping_state,
            known_mapping=session.speaker_mapping,
        )

        session.session_metrics["utterance_count"] += 1
        count = session.session_metrics["utterance_count"]
        prev_avg = session.session_metrics["avg_utterance_duration_ms"]
        session.session_metrics["avg_utterance_duration_ms"] = (
            ((prev_avg * (count - 1)) + duration_ms) / count
        )

        # Fire-and-forget: run STT + transcript send as a background task so the
        # WebSocket receive loop is never blocked waiting for the STT response.
        # Blocking here caused a pipeline shift where each turn's transcript
        # arrived in the next turn's eval collection window when STT was slow.
        asyncio.create_task(
            session.listener_agent.process_diarized_utterance(utterance),
            name=f"stt-{utterance.utterance_id[:12]}",
        )

    @staticmethod
    async def handle_user_addressing_ai(session: NegotiationSession, payload: dict, websocket: WebSocket) -> None:
        """
        Handles USER_ADDRESSING_AI message from frontend long-press trigger.
        Manages the audio gate and conversation turn signals for the Live AI.
        """
        if companion_runtime.is_companion_mode(session):
            companion_runtime.update_hold_state(session, payload)
        active = bool(payload.get("active", False))
        was_active = session.user_addressing_ai
        session.user_addressing_ai = active
        session_store.persist_session(session, ended=False)

        logger.info(
            f"Audio gate to Live AI {'OPENED' if active else 'CLOSED'}. "
            f"[session={session.session_id}]"
        )

        # When user presses button (OFF -> ON)
        if active and not was_active and session.live_session:
            session.ai_audio_playing = False
            # Clear any leftover audio from a previous question
            session.question_capture_bytes = b""
            session.last_user_transcript = ""
            # Also reset the negotiation segment buffer so the Ask AI audio
            # doesn't get included in the next speaker's transcript segment.
            session.current_segment_audio = b""

            try:
                response_mode = getattr(session, 'response_mode', 'command')

                # Inject the latest full intel snapshot so the AI is briefed
                # on current context before it receives the question.
                if session.listener_agent and session.listener_agent.last_context:
                    ctx = session.listener_agent.last_context
                    market_data = ctx.get("market_data")
                    market_info = "Not yet researched"
                    if isinstance(market_data, str):
                        market_info = market_data
                    elif isinstance(market_data, dict):
                        pr = market_data.get("price_range") or {}
                        facts = market_data.get("key_facts", "")
                        leverage = market_data.get("leverage", "")
                        market_info = f"Fair range: {pr.get('min')} – {pr.get('max')} (avg {pr.get('average')})"
                        if facts:    market_info += f" | Facts: {facts}"
                        if leverage: market_info += f" | Leverage: {leverage}"

                    transcript_text = ""
                    if session.listener_agent.accumulated_transcript:
                        transcript_text = session.listener_agent.accumulated_transcript[-1500:]

                    # Attach latest vision observation if fresh
                    latest_vision = (
                        session.vision_observations[-1]
                        if getattr(session, "vision_observations", None)
                        else None
                    )

                    pre_brief = build_pre_query_brief(
                        context=ctx,
                        market_info=market_info,
                        transcript_text=transcript_text,
                        vision_observation=latest_vision,
                    )

                    async with session.gemini_send_lock:
                        await session.live_session.send_client_content(
                            turns=types.Content(
                                role="user",
                                parts=[types.Part(text=pre_brief)],
                            ),
                            turn_complete=False,
                        )
                    logger.info(f"Pre-query intel brief sent ({len(pre_brief)} chars)")

                async with session.gemini_send_lock:
                    mode_instruction = build_mode_activation_instruction(response_mode)

                    await session.live_session.send_client_content(
                        turns=types.Content(
                            role="user",
                            parts=[types.Part(text=mode_instruction)],
                        ),
                        turn_complete=False,
                    )
                logger.debug(f"Pre-brief + mode instruction sent ({response_mode}). Capturing question audio.")
            except Exception as e:
                logger.warning(f"Pre-brief send failed (session may be reconnecting): {e}")

        # When user releases button (ON -> OFF)
        if not active and was_active and session.live_session:
            # Capture real-time streaming transcript fallback if batch transcription is missing/unclear
            fallback_text = session.companion_partial_text.get("ask_ai", "").strip()
            # Clean up ask_ai partials and cancel any running background transcription task immediately to prevent late partials
            session.companion_partial_text.pop("ask_ai", None)
            session.companion_partial_started_at.pop("ask_ai", None)
            partial_task = session.companion_partial_tasks.pop("ask_ai", None)
            if partial_task and not partial_task.done():
                partial_task.cancel()

            # Take captured audio and send the question as text to Live AI.
            # Text-based questions ensure the AI answers what was actually asked,
            # not just the general context.
            question_audio = session.question_capture_bytes
            session.question_capture_bytes = b""

            async def _handle_question(
                q_audio: bytes,
                fallback_q_text: str = "",
                live_session=session.live_session,
                listener=session.listener_agent,
                lock=session.gemini_send_lock,
                ws=websocket,
                sess=session,
            ):
                try:
                    q_text = ""
                    if q_audio and len(q_audio) >= 3200 and listener:
                        q_text = await asyncio.get_event_loop().run_in_executor(
                            None, lambda: listener._fast_transcribe(q_audio)
                        )
                        q_text = (q_text or "").strip()

                    if not q_text and fallback_q_text:
                        q_text = fallback_q_text
                        logger.info(f"[Engine] Audio transcription empty, falling back to real-time partial: '{q_text}'")

                    if not q_text:
                        # No audio transcript and no fallback partial text. 
                        # Short-circuit and notify the user to try again.
                        try:
                            await ws.send_json({
                                "type": "AI_RESPONSE",
                                "payload": {
                                    "speaker": "ai",
                                    "text": "I didn't catch that clearly. Hold and ask again.",
                                    "timestamp": int(time.time() * 1000),
                                    "context": "ask_ai",
                                }
                            })
                        except Exception:
                            pass
                        logger.info("[Engine] Short-circuited empty query with 'Hold and ask again'")
                        return

                    # Show what the user asked in the sidebar transcript
                    if q_text:
                        try:
                            await ws.send_json({
                                "type": "TRANSCRIPT_UPDATE",
                                "payload": {
                                    "id": f"q_{int(time.time() * 1000)}",
                                    "speaker": "user",
                                    "text": q_text,
                                    "timestamp": int(time.time() * 1000),
                                    "context": "ask_ai",  # routes to AI Advisor panel, not Conversation panel
                                },
                            })
                        except Exception:
                            pass
                        log_conversation_event(
                            session_id=sess.session_id,
                            event="ai_query",
                            speaker="user",
                            text=q_text,
                            timestamp_ms=int(time.time() * 1000),
                            context="ask_ai",
                            response_mode=getattr(sess, "response_mode", None),
                        )
                    else:
                        log_conversation_event(
                            session_id=sess.session_id,
                            event="ai_query",
                            speaker="user",
                            text="(audio unclear)",
                            timestamp_ms=int(time.time() * 1000),
                            context="ask_ai",
                            response_mode=getattr(sess, "response_mode", None),
                        )

                    # Build the question message for Live AI
                    if q_text:
                        question_msg = (
                            f"[USER'S EXACT QUESTION]: {q_text}\n"
                            "Answer this specific question directly. "
                            "Do not give a generic strategy overview. "
                            "Use the intel briefing above as background only."
                        )
                        logger.info(f"[Engine] Sending question to Live AI: '{q_text[:80]}'")
                    else:
                        # Audio too short or transcription failed — ask for current best advice
                        question_msg = (
                            "[USER QUESTION]: (audio unclear) "
                            "Give your single most important tactical recommendation right now."
                        )
                        logger.info("[Engine] Question audio unclear, sending fallback prompt")

                    async with lock:
                        sess.direct_query_in_flight = True
                        await live_session.send_client_content(
                            turns=types.Content(
                                role="user",
                                parts=[types.Part(text=question_msg)],
                            ),
                            turn_complete=True,
                        )
                except Exception as e:
                    logger.warning(f"[Engine] Question handling failed: {e}")

            asyncio.create_task(_handle_question(question_audio, fallback_text))

    @staticmethod
    async def handle_start_copilot(session: NegotiationSession, payload: dict, websocket: WebSocket) -> None:
        """
        Handle START_COPILOT message from frontend.
        Activates proactive monitoring mode on the already-open Live session.
        """
        # 1. Idempotency check — safe to press twice
        if session.copilot_active:
            logger.info(f"START_COPILOT ignored — already active [session={session.session_id}]")
            return

        # 2. Set the flag — gates _inject_context_to_live_ai
        session.copilot_active = True
        logger.info(f"Copilot activated [session={session.session_id}]")

        # 3. Clear any critical events that were queued before activation.
        #    They are not lost; they are already part of the listener's 'last_context'
        #    and will be included in the next 'ASK_ADVICE' query.
        if session.listener_agent and session.listener_agent._pre_activation_critical_events:
            session.listener_agent._pre_activation_critical_events.clear()
            logger.info(
                f"Cleared pre-activation critical events. Context is preserved in listener state. "
                f"[session={session.session_id}]"
            )
        
        # 4. Verify Live session exists
        if session.live_session is None:
            logger.error(f"START_COPILOT failed — no Live session [session={session.session_id}]")
            await websocket.send_json({
                "type": "ERROR",
                "payload": {"code": "NO_LIVE_SESSION", "message": "Live session not available"}
            })
            return

        # 4. Empty guard — skip priming if no context accumulated yet (Risk 6)
        last_context = {}
        if session.listener_agent:
            last_context = session.listener_agent.last_context or {}
        
        if not last_context:
            logger.info(
                f"Copilot activated but no context yet — skipping priming injection "
                f"[session={session.session_id}]"
            )
            # Still confirm to frontend — copilot is active, just no data to prime with yet
            await websocket.send_json({"type": "COPILOT_STARTED", "payload": {}})
            return

        # 5. Send priming injection — format current context as [LISTENER_INTEL]
        # FIX: Use full accumulated_transcript instead of tiny transcript_snippet
        try:
            market_data = last_context.get("market_data")
            market_info = ""
            if isinstance(market_data, str):
                market_info = f"Market Research: {market_data}"
            elif isinstance(market_data, dict):
                pr = market_data.get("price_range") or {}
                market_info = f"Market Range: {pr.get('min')} – {pr.get('max')} (avg {pr.get('average')})"

            # Get full accumulated transcript for complete conversation history
            accumulated_transcript = ""
            if session.listener_agent and session.listener_agent.accumulated_transcript:
                accumulated_transcript = session.listener_agent.accumulated_transcript[-1500:] # Cap to last 1500 chars
            
            priming_text = build_copilot_priming_text(
                context=last_context,
                market_info=market_info,
                accumulated_transcript=accumulated_transcript,
            )

            async with session.gemini_send_lock:
                await session.live_session.send_client_content(
                    turns=types.Content(
                        role="system",
                        parts=[types.Part(text=priming_text)],
                    ),
                    turn_complete=False,
                )
            
            logger.info(
                f"Copilot primed with current context ({len(priming_text)} chars) "
                f"[session={session.session_id}]"
            )

        except Exception as exc:
            logger.warning(
                f"Copilot priming injection failed: {exc} "
                f"[session={session.session_id}]"
            )
            # Don't fail activation — copilot is still active, just missed the priming

        # 6. Confirm to frontend — activates "Copilot Active 🎙" indicator
        await websocket.send_json({"type": "COPILOT_STARTED", "payload": {}})

    @staticmethod
    async def handle_set_response_mode(session: NegotiationSession, payload: dict, websocket: WebSocket) -> None:
        """
        Handle SET_RESPONSE_MODE message from frontend.
        
        Sets the response mode for when user presses and holds to talk to AI:
        - "advice": Skip validation, return full AI response
        - "command": Apply validation and correction if needed (default)
        
        This doesn't send anything to AI yet - just stores the mode.
        When user presses and holds, the AI will respond based on this mode.
        """
        mode = payload.get("mode", "command")
        
        # Validate mode
        if mode not in ("advice", "command"):
            logger.warning(f"Invalid response mode: {mode}, defaulting to command")
            mode = "command"
        
        session.response_mode = mode
        logger.info(f"Response mode set to: {mode} [session={session.session_id}]")
  
        # Notify frontend of the mode change
        await websocket.send_json({
            "type": "RESPONSE_MODE_SET",
            "payload": {"mode": mode}
        })

    @staticmethod
    async def handle_set_response_language(session: NegotiationSession, payload: dict, websocket: WebSocket) -> None:
        language = payload.get("language") or session.language or "en-US"
        session.response_language = language
        session_store.persist_session(session, ended=False)
        await websocket.send_json({
            "type": "LANGUAGE_UPDATE",
            "payload": {
                "language": session.language,
                "response_language": session.response_language,
            }
        })

    @staticmethod
    async def handle_speaker_mode_change(session: NegotiationSession, payload: dict, websocket: WebSocket) -> None:
        """
        Handle SPEAKER_MODE_CHANGE message from frontend.
        
        Toggles between automatic and manual speaker identification modes:
        - "auto": Use voice fingerprinting for automatic classification
        - "manual": Use button clicks for manual speaker selection
        
        Requirements: 4.1, 4.2, 4.3, 4.4
        """
        mode = payload.get("mode", "manual")
        
        # Validate mode
        if mode not in ("auto", "manual"):
            logger.warning(f"Invalid speaker mode: {mode}, defaulting to manual")
            mode = "manual"
        
        # Update session state
        session.speaker_mode = mode
        
        # Set manual override based on mode (Requirement 4.3, 4.4)
        if mode == "manual":
            # Disable automatic classification indefinitely
            session.manual_override_until = float('inf')
            logger.info(f"Speaker mode changed to MANUAL (automatic classification disabled) [session={session.session_id}]")
        else:
            # Enable automatic classification
            session.manual_override_until = None
            logger.info(f"Speaker mode changed to AUTO (automatic classification enabled) [session={session.session_id}]")
        log_speaker_debug(
            "SPEAKER_MODE_CHANGE",
            session_id=session.session_id,
            mode=mode,
            current_speaker=session.current_speaker,
            manual_override_until=session.manual_override_until,
            speechbrain_profile_state=session.speechbrain_profile_state,
        )
        
        # Notify frontend of the mode change
        await websocket.send_json({
            "type": "SPEAKER_MODE_CHANGED",
            "payload": {"mode": mode}
        })

    @staticmethod
    async def _inject_context_to_live_ai(
        session: NegotiationSession,
        context: dict,
        critical_events: list,
    ) -> None:
        """
        Injects the full negotiation intelligence into the Live AI session.
        Called by the ListenerAgent every cycle and on critical events.

        Sends:
        - All extracted fields (prices, sentiment, leverage, key moments)
        - Market research results
        - Full labeled conversation transcript
        - Any critical events (anchor detected, pressure tactic, etc.)
        """
        if not session.copilot_active or session.live_session is None:
            return

        session.pending_live_snapshot = NegotiationEngine._build_compact_snapshot(session)
        session.pending_intel_context = dict(context or {})
        if critical_events:
            session.pending_intel_critical_events.extend(critical_events)

        if session.intel_injection_task is None or session.intel_injection_task.done():
            session.intel_injection_task = asyncio.create_task(
                NegotiationEngine._flush_latest_intel(session),
                name=f"intel-inject-{session.session_id[:8]}",
            )
        return

        # Queue injections if a user interaction is in flight to prevent double responses.
        if (getattr(session, 'user_addressing_ai', False)
                or getattr(session, 'direct_query_in_flight', False)
                or getattr(session, 'ai_is_speaking', False)):
            session.pending_injections.append((context, critical_events))
            logger.info(f"Queued injection (interaction in flight).")
            return

        # ── Build full intel block ────────────────────────────────────────────
        accumulated_transcript = ""
        if session.listener_agent and session.listener_agent.accumulated_transcript:
            accumulated_transcript = session.listener_agent.accumulated_transcript[-1500:]

        if not accumulated_transcript.strip() and not context:
            return

        # Market research formatting
        market_data = context.get("market_data")
        market_info = "Not yet researched"
        if market_data:
            if isinstance(market_data, str):
                market_info = market_data
            elif isinstance(market_data, dict):
                pr = market_data.get("price_range") or {}
                facts    = market_data.get("key_facts", "")
                leverage = market_data.get("leverage", "")
                market_info = f"Fair range: {pr.get('min')} – {pr.get('max')} (avg {pr.get('average')})"
                if facts:    market_info += f" | Facts: {facts}"
                if leverage: market_info += f" | Leverage: {leverage}"

        # Critical events block
        events_text = ""
        if critical_events:
            lines = []
            for evt in critical_events:
                lines.append(f"  ⚠ {evt.get('event_type')}: {evt.get('detail', {})}")
            events_text = "\nCRITICAL EVENTS:\n" + "\n".join(lines)

        # Determine user role from negotiation type so labels are always correct.
        # negotiation_type describes the transaction (buying_goods/selling_goods) but
        # does NOT reliably tell us which side the USER is on — Flash infers it from
        # audio context and may label it from the counterparty's perspective.
        # The authoritative source is counterparty_price vs user_price combined with
        # seller_asking_price vs buyer_offer.
        negotiation_type = context.get('negotiation_type') or 'unknown'

        # Derive user role: if user_price matches seller_asking_price → user is seller.
        # If user_price matches buyer_offer → user is buyer.
        # Fall back to negotiation_type only when prices are absent.
        user_price_val_raw = context.get('user_price')
        seller_asking = context.get('seller_asking_price')
        buyer_offer_val = context.get('buyer_offer')
        counterparty_price_raw = context.get('counterparty_price')

        if user_price_val_raw is not None and seller_asking is not None and user_price_val_raw == seller_asking:
            user_is_seller = True
            user_is_buyer = False
        elif user_price_val_raw is not None and buyer_offer_val is not None and user_price_val_raw == buyer_offer_val:
            user_is_seller = False
            user_is_buyer = True
        else:
            # Fall back to negotiation_type — treat as describing what the USER is doing
            user_is_seller = negotiation_type == 'selling_goods'
            user_is_buyer = negotiation_type == 'buying_goods'

        if user_is_seller:
            user_role = "SELLER (User is selling — counterparty is the buyer)"
            user_price_label = "My asking price (User/Seller)"
            counterparty_price_label = "Their offer (Counterparty/Buyer)"
            user_price_val = seller_asking or user_price_val_raw
            counterparty_price_val = buyer_offer_val or counterparty_price_raw
        elif user_is_buyer:
            user_role = "BUYER (User is buying — counterparty is the seller)"
            user_price_label = "My offer (User/Buyer)"
            counterparty_price_label = "Their asking price (Counterparty/Seller)"
            user_price_val = buyer_offer_val or user_price_val_raw
            counterparty_price_val = seller_asking or counterparty_price_raw
        else:
            user_role = negotiation_type
            user_price_label = "User price"
            counterparty_price_label = "Counterparty price"
            user_price_val = user_price_val_raw
            counterparty_price_val = counterparty_price_raw

        intel_block = build_listener_intel_block(
            context=context,
            negotiation_type=negotiation_type,
            user_role=user_role,
            user_price_label=user_price_label,
            user_price_val=user_price_val,
            counterparty_price_label=counterparty_price_label,
            counterparty_price_val=counterparty_price_val,
            market_info=market_info,
            events_text=events_text,
            accumulated_transcript=accumulated_transcript,
        )

        logger.info(
            f"Injecting full intel to Live AI ({len(intel_block)} chars) "
            f"[session={session.session_id}]"
        )

        try:
            async with session.gemini_send_lock:
                await session.live_session.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[types.Part(text=intel_block)],
                    ),
                    turn_complete=False,
                )
            logger.info("Intel injection successful.")
        except Exception as exc:
            logger.warning(f"Context injection failed: {exc}")

    @staticmethod
    async def _flush_latest_intel(session: NegotiationSession) -> None:
        try:
            while (
                session.copilot_active
                and session.live_session is not None
                and (session.pending_intel_context is not None or session.pending_intel_critical_events)
            ):
                if (
                    getattr(session, "user_addressing_ai", False)
                    or getattr(session, "direct_query_in_flight", False)
                    or getattr(session, "ai_is_speaking", False)
                ):
                    return

                wait_for = settings.VISION_INTEL_SEND_INTERVAL_SECONDS - (
                    time.time() - session.last_intel_injected_at
                )
                if wait_for > 0:
                    await asyncio.sleep(wait_for)

                context = dict(session.pending_intel_context or {})
                critical_events = list(session.pending_intel_critical_events or [])
                session.pending_intel_context = None
                session.pending_intel_critical_events.clear()

                await NegotiationEngine._send_coalesced_intel(session, context, critical_events)
                session.last_intel_injected_at = time.time()
        finally:
            session.intel_injection_task = None

    @staticmethod
    async def _send_coalesced_intel(
        session: NegotiationSession,
        context: dict,
        critical_events: list,
    ) -> None:
        if session.live_session is None:
            return

        accumulated_transcript = ""
        if session.listener_agent and session.listener_agent.accumulated_transcript:
            accumulated_transcript = session.listener_agent.accumulated_transcript[-1500:]

        if not accumulated_transcript.strip() and not context:
            return

        market_data = context.get("market_data")
        market_info = "Not yet researched"
        if market_data:
            if isinstance(market_data, str):
                market_info = market_data
            elif isinstance(market_data, dict):
                pr = market_data.get("price_range") or {}
                facts = market_data.get("key_facts", "")
                leverage = market_data.get("leverage", "")
                market_info = f"Fair range: {pr.get('min')} â€“ {pr.get('max')} (avg {pr.get('average')})"
                if facts:
                    market_info += f" | Facts: {facts}"
                if leverage:
                    market_info += f" | Leverage: {leverage}"

        events_text = ""
        if critical_events:
            lines = []
            for evt in critical_events:
                lines.append(f"  âš  {evt.get('event_type')}: {evt.get('detail', {})}")
            events_text = "\nCRITICAL EVENTS:\n" + "\n".join(lines)

        negotiation_type = context.get('negotiation_type') or 'unknown'
        user_price_val_raw = context.get('user_price')
        seller_asking = context.get('seller_asking_price')
        buyer_offer_val = context.get('buyer_offer')
        counterparty_price_raw = context.get('counterparty_price')

        if user_price_val_raw is not None and seller_asking is not None and user_price_val_raw == seller_asking:
            user_is_seller = True
            user_is_buyer = False
        elif user_price_val_raw is not None and buyer_offer_val is not None and user_price_val_raw == buyer_offer_val:
            user_is_seller = False
            user_is_buyer = True
        else:
            user_is_seller = negotiation_type == 'selling_goods'
            user_is_buyer = negotiation_type == 'buying_goods'

        if user_is_seller:
            user_role = "SELLER (User is selling â€” counterparty is the buyer)"
            user_price_label = "My asking price (User/Seller)"
            counterparty_price_label = "Their offer (Counterparty/Buyer)"
            user_price_val = seller_asking or user_price_val_raw
            counterparty_price_val = buyer_offer_val or counterparty_price_raw
        elif user_is_buyer:
            user_role = "BUYER (User is buying â€” counterparty is the seller)"
            user_price_label = "My offer (User/Buyer)"
            counterparty_price_label = "Their asking price (Counterparty/Seller)"
            user_price_val = buyer_offer_val or user_price_val_raw
            counterparty_price_val = seller_asking or counterparty_price_raw
        else:
            user_role = negotiation_type
            user_price_label = "User price"
            counterparty_price_label = "Counterparty price"
            user_price_val = user_price_val_raw
            counterparty_price_val = counterparty_price_raw

        intel_block = build_listener_intel_block(
            context=context,
            negotiation_type=negotiation_type,
            user_role=user_role,
            user_price_label=user_price_label,
            user_price_val=user_price_val,
            counterparty_price_label=counterparty_price_label,
            counterparty_price_val=counterparty_price_val,
            market_info=market_info,
            events_text=events_text,
            accumulated_transcript=accumulated_transcript,
        )

        logger.info(
            "Injecting coalesced intel to Live AI (%s chars) [session=%s]",
            len(intel_block),
            session.session_id,
        )

        try:
            async with session.gemini_send_lock:
                await session.live_session.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[types.Part(text=intel_block)],
                    ),
                    turn_complete=False,
                )
            logger.info("Intel injection successful.")
        except Exception as exc:
            logger.warning(f"Context injection failed: {exc}")

    @staticmethod
    async def flush_pending_injections(session: NegotiationSession) -> None:
        """
        Flush any pending intel injections that were queued while AI was speaking.
        
        Called when AI completes a turn (turn_complete) to deliver all missed
        context updates to the AI.
        """
        if session.pending_intel_context is not None or session.pending_intel_critical_events:
            logger.info("Flushing coalesced intel injection [session=%s]", session.session_id)
            if session.intel_injection_task is None or session.intel_injection_task.done():
                session.intel_injection_task = asyncio.create_task(
                    NegotiationEngine._flush_latest_intel(session),
                    name=f"intel-inject-{session.session_id[:8]}",
                )
            return

        if not session.pending_injections:
            return
        
        pending_count = len(session.pending_injections)
        
        # Take a snapshot of the pending injections and clear the queue immediately
        # to prevent race conditions with new injections arriving during the flush.
        injections_to_flush = list(session.pending_injections)
        session.pending_injections.clear()

        logger.info(
            f"[CopilotEngine] DBG: Flushing {pending_count} pending injections. "
            f"Queue is now {len(session.pending_injections)}."
        )

        all_contexts = [ctx for ctx, _ in injections_to_flush]
        all_critical_events = [evt for _, evts in injections_to_flush for evt in evts]

        # Send each context as a separate injection
        for context in all_contexts:
            await NegotiationEngine._inject_single_context(session, context)
        
        # If there were any critical events, inject them silently.
        if all_critical_events:
            await NegotiationEngine._inject_critical_events(session, all_critical_events, prompt_evaluation=False)
        
        logger.info(
            f"[CopilotEngine] Flushed {pending_count} pending injections complete "
            f"[session={session.session_id}]"
        )

    @staticmethod
    async def _reconnect_live_session(session: NegotiationSession, websocket: WebSocket, attempt: int = 1) -> None:
        """
        Auto-reconnect the Gemini Live session after a connection drop.

        Handles 1006 (abnormal closure), 1007 (codec error), 1011 (keepalive ping timeout),
        and any other recoverable WebSocket disconnects from the Gemini Live API.

        Recovery strategy:
          1. Close the broken session (it's already dead, so ignore close errors)
          2. Open a fresh Live session with exponential backoff (max 3 attempts)
          3. Re-inject the last LISTENER_INTEL context to prime the new session
          4. Start a new receive_responses loop on the fresh session

        All session state (transcript, strategy_history, copilot_active, etc.) is preserved.
        """
        MAX_RECONNECT_ATTEMPTS = 3
        session_id = session.session_id
        session.session_metrics["gemini_reconnect_count"] += 1
        session.degraded_mode = "advisor_reconnecting"
        logger.info(f"[Reconnect] Attempt {attempt}/{MAX_RECONNECT_ATTEMPTS} [{session_id}]")
        try:
            await websocket.send_json({
                "type": "DEGRADED_MODE_UPDATE",
                "payload": {"active": True, "mode": session.degraded_mode},
            })
        except Exception:
            pass

        # Exponential backoff: 0.5s, 2s, 5s
        backoff = [0.5, 2.0, 5.0][min(attempt - 1, 2)]
        await asyncio.sleep(backoff)

        # ── 1. Close the broken session ──────────────────────────────────────
        if session.live_session_cm:
            try:
                await session.live_session_cm.__aexit__(None, None, None)
            except Exception:
                pass  # Already broken — ignore close errors
        session.live_session = None

        # ── 2. Open a fresh session ──────────────────────────────────────────
        try:
            api_key = getattr(session, 'api_key', None) or settings.GEMINI_API_KEY
            new_cm = open_live_session(api_key=api_key, context=session.context)
            session.live_session_cm = new_cm
            session.live_session = await new_cm.__aenter__()

            # Reset transient AI state — the new session starts clean
            session.ai_is_speaking = False
            session.direct_query_in_flight = False
            session.pending_injections.clear()
            session.pending_intel_context = None
            session.pending_intel_critical_events.clear()

            logger.info(f"[Reconnect] New Live session opened (attempt {attempt}) [{session_id}]")

        except Exception as e:
            logger.error(f"[Reconnect] Failed to open new session (attempt {attempt}) [{session_id}]: {e}", exc_info=True)
            if attempt < MAX_RECONNECT_ATTEMPTS:
                logger.info(f"[Reconnect] Retrying... [{session_id}]")
                session.live_reconnect_task = asyncio.create_task(
                    NegotiationEngine._reconnect_live_session(session, websocket, attempt + 1)
                )
            else:
                logger.error(f"[Reconnect] All {MAX_RECONNECT_ATTEMPTS} attempts failed [{session_id}]")
                session.degraded_mode = "manual_only"
                try:
                    await websocket.send_json({
                        "type": "DEGRADED_MODE_UPDATE",
                        "payload": {"active": True, "mode": session.degraded_mode},
                    })
                    await websocket.send_json({
                        "type": "AI_DEGRADED",
                        "payload": {
                            "message": "AI advisor reconnect failed after multiple attempts. Please refresh.",
                            "mode": session.degraded_mode,
                        }
                    })
                except Exception:
                    pass
            return

        # ── 3. Restore speaker service if needed (Requirement 11.4) ──────────
        if False and (
            settings.SPEAKER_RECOGNITION_ENABLED
            and (settings.RESEMBLYZER_ENABLED or settings.SPEECHBRAIN_ENABLED)
            and session.speaker_mode == "auto"
            and session.user_embedding is not None
        ):
            try:
                from app.services.speaker_service import SpeakerService
                
                # Create callback for segment completion (VAD detected silence after speech)
                async def on_segment_complete(speaker: str, audio: bytes, timestamp: float, speaker_changed: bool):
                    """Handle automatic segment completion - transcribe every segment."""
                    duration_s = len(audio) / 32000
                    logger.info(f"🎤 Auto segment complete: {speaker} ({duration_s:.1f}s, changed={speaker_changed})")
                    
                    # Transcribe this segment with the identified speaker
                    if session.listener_agent and len(audio) >= 3200:  # at least 0.1s
                        asyncio.create_task(
                            session.listener_agent.transcribe_segment(
                                speaker=speaker,
                                audio=audio,
                                start_time=timestamp - duration_s,
                                end_time=timestamp,
                            )
                        )
                
                session.speaker_service = SpeakerService(session, on_segment_complete_callback=None)
                logger.info(f"[Reconnect] SpeakerService restored [session={session_id}]")
            except Exception as e:
                logger.error(f"[Reconnect] Failed to restore SpeakerService: {e}", exc_info=True)
                # Graceful degradation: continue without speaker recognition

# ── 4. Re-prime the new session with accumulated context ─────────────
        if (session.copilot_active and session.listener_agent):
            try:
                snapshot = NegotiationEngine._build_compact_snapshot(session)
                session.pending_live_snapshot = snapshot
                await NegotiationEngine._inject_single_context(session, snapshot)
                logger.info(f"[Reconnect] Re-primed new session with compact snapshot [{session_id}]")
            except Exception as e:
                logger.warning(f"[Reconnect] Context re-prime failed (non-fatal): {e}")

        # ── 5. Start a new receive loop on the fresh session ─────────────────
        session.live_session_receive_task = asyncio.create_task(
            receive_responses(session.live_session, websocket, session_id, session)
        )
        session.degraded_mode = None
        try:
            await websocket.send_json({
                "type": "DEGRADED_MODE_UPDATE",
                "payload": {"active": False, "mode": None},
            })
        except Exception:
            pass

        logger.info(f"[Reconnect] Reconnect complete — copilot fully restored [{session_id}]")

    @staticmethod
    def _build_compact_snapshot(session: NegotiationSession) -> dict:
        context = session.listener_agent.last_context if session.listener_agent else {}
        market_data = context.get("market_data")
        if isinstance(market_data, dict):
            market_summary = {
                key: market_data.get(key)
                for key in ("price_range", "key_facts", "leverage", "tactics", "gap_answer")
            }
        else:
            market_summary = market_data

        return {
            "item": context.get("item"),
            "seller_price": context.get("counterparty_price") or context.get("seller_asking_price"),
            "user_offer": context.get("user_price") or context.get("buyer_offer"),
            "user_target_price": context.get("user_target_price"),
            "user_walk_away_price": context.get("user_walk_away_price"),
            "sentiment": context.get("counterparty_sentiment", "unknown"),
            "counterparty_goal": context.get("counterparty_goal"),
            "key_moments": (context.get("key_moments") or [])[-5:],
            "leverage_points": (context.get("leverage_points") or [])[-5:],
            "recent_turns": session.eligible_transcript_turns[-10:],
            "market_research": market_summary,
        }

    @staticmethod
    async def _inject_single_context(session: NegotiationSession, context: dict) -> None:
        """Send a single context injection to the Live AI."""
        if session.live_session is None:
            return
        
        from google.genai import types
        
        md = context.get("market_data") or context.get("market_research")
        market_info = ""
        if isinstance(md, str):
            market_info = f"Market Research: {md}"
        elif isinstance(md, dict):
            pr = md.get("price_range") or {}
            market_info = f"Market Range: {pr.get('min')} – {pr.get('max')} (avg {pr.get('average')})"
        
        accumulated_transcript = ""
        if session.listener_agent and session.listener_agent.accumulated_transcript:
            accumulated_transcript = session.listener_agent.accumulated_transcript[-800:]
        
        intel_text = build_single_context_intel_text(
            context=context,
            market_info=market_info,
            transcript_text=(
                accumulated_transcript
                or context.get('transcript_snippet', '')
                or json.dumps(context.get('recent_turns', []))
            ),
        )

        logger.info(
            "Sending single context to Live AI",
            extra={"session_id": session.session_id, "intel_text": intel_text},
        )

        try:
            async with session.gemini_send_lock:
                await session.live_session.send_client_content(
                    turns=types.Content(
                        role="system",
                        parts=[types.Part(text=intel_text)],
                    ),
                    turn_complete=False,
                )
        except Exception as exc:
            logger.warning(f"[CopilotEngine] Failed to send queued context: {exc}")

    @staticmethod
    async def _inject_critical_events(session: NegotiationSession, critical_events: list, prompt_evaluation: bool = False) -> None:
        """Send critical events injection to the Live AI."""
        if session.live_session is None or not critical_events:
            return
        
        from google.genai import types
        
        # Get the most recent transcript to provide context for the event
        accumulated_transcript = ""
        if session.listener_agent and session.listener_agent.accumulated_transcript:
            accumulated_transcript = session.listener_agent.accumulated_transcript[-800:]

        blocks = []
        for evt in critical_events:
            evt_type = evt.get("event_type", "UNKNOWN")
            detail = evt.get("detail", {})
            blocks.append(
                build_critical_event_block(
                    event_type=evt_type,
                    detail=detail,
                    transcript_text=accumulated_transcript,
                )
            )
        
        logger.info(
            "Sending critical events to Live AI",
            extra={"session_id": session.session_id, "blocks": blocks},
        )

        try:
            async with session.gemini_send_lock:
                for block in blocks:
                    await session.live_session.send_client_content(
                        turns=types.Content(
                            role="system",
                            parts=[types.Part(text=block)],
                        ),
                 turn_complete=False,
                    )
                
                if prompt_evaluation:
                    logger.info("[CopilotEngine] Prompting AI evaluation after flushing critical events.")
                    await session.live_session.send_client_content(
                        turns=types.Content(
                            role="user",
                            parts=[types.Part(text="[Evaluate the situation and advise if needed]")],
                        ),
                        turn_complete=True,
                    )
        except Exception as exc:
            logger.warning(f"[CopilotEngine] Failed to send critical events: {exc}")

    @staticmethod
    async def flush_pending_injections(session: NegotiationSession) -> None:
        """
        Flushes any pending intel injections that were queued while the AI was speaking.
        Called from gemini_client when a turn is complete or interrupted.
        """
        if session.pending_intel_context is not None or session.pending_intel_critical_events:
            logger.info("Flushing coalesced intel injection [session=%s]", session.session_id)
            if session.intel_injection_task is None or session.intel_injection_task.done():
                session.intel_injection_task = asyncio.create_task(
                    NegotiationEngine._flush_latest_intel(session),
                    name=f"intel-inject-{session.session_id[:8]}",
                )
            return

        if not hasattr(session, 'pending_injections') or not session.pending_injections:
            return
        
        pending_count = len(session.pending_injections)
        injections_to_flush = list(session.pending_injections)
        session.pending_injections.clear()

        logger.info(f"Flushing {pending_count} pending intel injections...")

        for context, critical_events in injections_to_flush:
            # Reuse the existing injector logic to send the queued data
            await NegotiationEngine._inject_context_to_live_ai(
                session, context, critical_events
            )
        
        logger.info(f"Flush complete. [session={session.session_id}]")

    @staticmethod
    async def handle_ask_advice(session: NegotiationSession, payload: dict, websocket: WebSocket) -> None:
        """
        Handle ASK_ADVICE message from frontend. It gathers the latest context,
        builds a persona-reinforcing query using build_advisor_query, and sends
        it to the AI.
        
        The payload can include 'response_mode' to control validation:
        - "advice": Skip validation, return full AI response
        - "command": Apply validation and correction if needed (default)
        """
        logger.info(f"ASK_ADVICE request received [session={session.session_id}]")

        live_session = session.live_session
        if not live_session:
            logger.error(f"No active Gemini session for ASK_ADVICE [session={session.session_id}]")
            return

        response_mode = payload.get("response_mode", "command")
        session.response_mode = response_mode
        logger.info(f"Response mode set to: {response_mode} [session={session.session_id}]")

        await websocket.send_json({"type": "AI_THINKING", "payload": {}})

        # Trigger an immediate extraction cycle so the query uses the freshest possible
        # context rather than whatever was extracted up to POLL_INTERVAL seconds ago.
        # Fire-and-forget — don't block the query on the Flash extraction.
        if session.listener_agent:
            session.listener_agent.force_immediate_cycle()

        try:
            # Gather the latest context from the listener and the user session.
            listener_ctx = session.listener_agent.last_context if session.listener_agent else {}
            user_ctx = session.user_context or {}

            # Pass the full listener context so build_advisor_query has all fields.
            # Overlay user-provided setup values (higher priority for target/walk-away).
            state_for_query = {
                **listener_ctx,
                "item":         listener_ctx.get("item") or user_ctx.get("item", ""),
                "target_price": user_ctx.get("target_price") or listener_ctx.get("user_target_price"),
                "max_price":    user_ctx.get("max_price") or listener_ctx.get("user_walk_away_price"),
                "language": session.language,
                "response_language": session.response_language or session.language or "en-US",
            }

            # Use the full accumulated transcript from the listener for the richest context
            transcript_for_query = ""
            if session.listener_agent and session.listener_agent.accumulated_transcript:
                transcript_for_query = session.listener_agent.accumulated_transcript
            
            user_query_text = payload.get("query", "Command.")
            log_conversation_event(
                session_id=session.session_id,
                event="ai_query",
                speaker="user",
                text=user_query_text,
                timestamp_ms=int(time.time() * 1000),
                context="ask_advice",
                response_mode=response_mode,
            )

            # Build the final, persona-reinforcing query.
            from app.services.gemini_client import build_advisor_query, generate_tactical_advice
            query = build_advisor_query(
                state=state_for_query,
                transcript=transcript_for_query,
                user_query=user_query_text
            )
            mode_instruction = build_mode_activation_instruction(response_mode)

            # ─── PRO PRE-FLIGHT REASONING ─────────────────────────────────────
            # Pro thinks, Flash speaks. Before the live audio model responds, call
            # gemini-2.5-pro to compute the exact tactical answer (better reasoning,
            # constraint following, anti-hallucination). Inject as [ADVISOR_OUTPUT]
            # so the live model reads it verbatim.
            pro_advice = None
            try:
                pro_advice = await asyncio.wait_for(
                    generate_tactical_advice(
                        session=session,
                        user_query=user_query_text,
                        response_mode=response_mode,
                    ),
                    timeout=settings.ADVICE_GENERATION_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Pro advice generation timed out after %.2fs; falling back to live-model reasoning [session=%s]",
                    settings.ADVICE_GENERATION_TIMEOUT_SECONDS,
                    session.session_id,
                )
            except Exception as pro_exc:
                logger.warning(
                    "Pro advice generation raised exception; falling back to live-model reasoning: %s",
                    pro_exc,
                )

            if pro_advice:
                # Build a verbatim-read injection. The live audio model gets the
                # already-validated answer and just speaks it. This guarantees
                # the Pro reasoning quality reaches the user.
                final_query = (
                    f"{mode_instruction}\n\n"
                    f"{query}\n\n"
                    f"[ADVISOR_OUTPUT - read this verbatim, do not paraphrase, do not add or remove any number or term]:\n"
                    f"{pro_advice}\n"
                    f"[/ADVISOR_OUTPUT]"
                )
                logger.info(
                    "Pro pre-flight advice ready len=%d preview=%r [session=%s]",
                    len(pro_advice),
                    pro_advice[:200],
                    session.session_id,
                )
                # Send the Pro-generated advice to the frontend transcript immediately
                # so the user sees the text the same instant the live model starts
                # speaking it. Speaker = "ai".
                try:
                    await websocket.send_json({
                        "type": "TRANSCRIPT_UPDATE",
                        "payload": {
                            "id": f"pro_advice_{int(time.time() * 1000)}",
                            "speaker": "ai",
                            "text": pro_advice,
                            "timestamp": int(time.time() * 1000),
                            "source": "pro_advice",
                            "response_mode": response_mode,
                        },
                    })
                except Exception as ws_exc:
                    logger.warning("Failed to push pro_advice TRANSCRIPT_UPDATE: %s", ws_exc)
            else:
                # Pro generation failed — fall through to the original behaviour
                # (live model generates its own response).
                final_query = f"{mode_instruction}\n\n{query}"

            logger.info(
                "Built advisor query",
                extra={
                    "session_id": session.session_id,
                    "state_for_query": state_for_query,
                    "transcript_snippet": transcript_for_query[-500:], # Log last 500 chars
                    "user_query": user_query_text,
                    "pro_advice_used": pro_advice is not None,
                    "final_query": final_query,
                },
            )

            # Set a flag to manage conversation turns.
            session.direct_query_in_flight = True

            # Send the final query to the AI.
            async with session.gemini_send_lock:
                await live_session.send(input=final_query, end_of_turn=True)

            logger.info(f"Built query sent successfully [session={session.session_id}]")

        except Exception as e:
            logger.error(f"Failed to send advice query: {e}", exc_info=True)
            await websocket.send_json({"type": "ERROR", "payload": {"message": str(e)}})
            session.direct_query_in_flight = False


def _build_context_summary(session: NegotiationSession) -> str:
    original = session.context or ""
    last_strategy = {}
    if session.strategy_history:
        last_strategy = session.strategy_history[-1]

    summary = f"Original Context: {original}\n"
    if last_strategy:
        summary += f"Last Strategy: {json.dumps(last_strategy)}\n"

    recent_transcript = session.transcript[-10:] if session.transcript else []
    if recent_transcript:
        summary += "Recent Transcript:\n"
        for entry in recent_transcript:
            speaker = entry.get("speaker", "Unknown")
            text = entry.get("text", "")
            summary += f"{speaker}: {text}\n"

    return summary
