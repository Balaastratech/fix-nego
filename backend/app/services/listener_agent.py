"""
listener_agent.py â€” Background context extraction agent
--------------------------------------------------------
Modified for PerfectListenerSystem integration:

Every POLL_INTERVAL seconds (5s) the agent:
  1. Reads accumulated_transcript (populated by PerfectListenerSystem)
  2. Extracts negotiation context (prices, sentiment, leverage points)
  3. Detects critical events (anchoring, pressure tactics, urgency)
  4. Triggers market research when needed
  5. Injects context into Live AI session
  6. Forwards CONTEXT_UPDATE to the frontend websocket

Design principles:
- NO transcription or speaker identification (handled by PerfectListenerSystem)
- Text-to-text extraction only (fast, 0.5-1s)
- Flash call (0.5-1s) NEVER holds the gemini_send_lock
- Lock is only grabbed for the fast inject send (< 100ms)
- A failed cycle is logged and skipped â€” never kills the loop
- Accumulated transcript is kept for the "Ask AI" query construction

Manual mode compatibility:
- transcribe_segment() method is kept for button-triggered transcription
- Used when user manually identifies speakers via button clicks
"""

import asyncio
import base64
import json
import logging
import time
import uuid
from typing import Any, Callable, Optional, TYPE_CHECKING
import numpy as np

from google import genai
from google.genai import types as genai_types

from app.ai_assets import (
    EXTRACTION_PROMPT,
    LISTENER_UTTERANCE_TRANSCRIPTION_PROMPT,
    TEXT_EXTRACTION_PROMPT,
    build_audio_extraction_prompt,
    build_market_research_prompt,
)
from app.config import settings
from app.services.bounded_async import GlobalLimiter, run_with_retries
from app.services.speaker_mapping_service import SpeakerMappingService
from app.services.stt_service import SpeechTranscriptionService
from app.services.session_store import session_store
from app.services.utterance_types import FinalizedUtterance
from app.utils.conversation_audit import log_conversation_event
from app.utils.speaker_debug import log_speaker_debug

if TYPE_CHECKING:
    from fastapi import WebSocket
    from app.models.negotiation import NegotiationSession

logger = logging.getLogger(__name__)

POLL_INTERVAL = 1.5         # seconds between extraction cycles (optimized for speed)
WINDOW_SECONDS = 20         # audio window sent to Flash each cycle (fallback audio path)
MIN_NEW_AUDIO = 1.5         # minimum seconds of new audio required before extraction (optimized for speed)
VOICE_SIMILARITY_THRESHOLD = 0.75  # Resemblyzer cosine similarity; above = same speaker
TEXT_EXTRACTION_DEBOUNCE_SECONDS = 1.5  # limit text extraction cadence (optimized for speed)

# Speaker smoothing: use rolling average of last N classifications to avoid jitter
SPEAKER_SMOOTHING_WINDOW = 3  # Consider last 3 classifications
SPEAKER_SMOOTHING_THRESHOLD = 0.55  # If avg similarity >= this, label as user
# Models are set dynamically based on Vertex AI vs Gemini API mode (see __init__)

# Text->text is faster than audio->text. Prompts live in app.ai_assets.



class ListenerAgent:
    """
    Background asyncio task that polls the AudioBuffer and extracts context.
    """

    def __init__(
        self,
        session: "NegotiationSession",
        audio_buffer: Any,
        gemini_send_lock: asyncio.Lock,
        websocket: "WebSocket",
        on_context_ready: Optional[Callable] = None,
    ):
        self.session = session
        self.session_id = session.session_id
        self.audio_buffer = audio_buffer
        self.gemini_send_lock = gemini_send_lock
        self.websocket = websocket
        self._on_context_ready = on_context_ready
        self._speech_transcriber = session.speech_transcriber or SpeechTranscriptionService(session)
        self.session.speech_transcriber = self._speech_transcriber
        self._research_limiter = GlobalLimiter.get("market_research", settings.RESEARCH_GLOBAL_CONCURRENCY)

        self._live_session: Optional[Any] = None
        self._task: Optional[asyncio.Task] = None
        self._research_task: Optional[asyncio.Task] = None
        self._background_tasks: set[asyncio.Task] = set()
        self._running = False

        # Accumulated context for "Ask AI" query enrichment
        self.last_context: dict = {}
        self.accumulated_transcript: str = ""
        self._cycle_count: int = 0
        # Dedup: track recently sent transcript lines to avoid repeating same audio window
        self._recent_transcript_hashes: set = set()
        self._recent_transcript_cycle: int = 0
        
        # Segment batching for transcription (prevents 429 errors and garbage output)
        self._pending_segments: list = []  # List of (speaker, audio, start_time, end_time)
        self._last_batch_time: float = 0.0
        self._batch_interval: float = 3.0  # Batch segments for 3 seconds before transcribing
        self._min_segment_duration: float = settings.MIN_TRANSCRIBE_DURATION_MS / 1000.0
        
        # Track the last sent context to detect changes (for deduplication)
        self._last_sent_context: dict = {}
        
        # Track audio buffer position to detect new audio
        self._last_processed_duration: float = 0.0
        
        # Force next extraction flag (set by manual speaker identification)
        self._force_next_extraction: bool = False
        
        # Research state
        self._last_research_query: str = ""
        # Time-based minimum cooldown â€” prevents spam even with event-driven triggers
        self._last_research_timestamp: float = 0.0
        # Track what item/type research was last run for â€” triggers re-research on change
        self._last_researched_item: str = ""
        self._last_researched_type: str = ""
        # Count of critical events since last research â€” triggers re-research on accumulation
        self._critical_events_since_research: int = 0
        # Last research_gap searched â€” prevents re-searching the same uncertainty
        self._last_research_gap: str = ""
        
        # Queue for critical events detected before copilot is activated
        self._pre_activation_critical_events: list[dict] = []

        # Session start time â€” used to compute relative timestamps in transcript
        self._session_start_time: float = time.time()
        
        # Speaker smoothing: track recent similarities for more stable labeling
        self._recent_similarities: list = []  # List of (similarity, timestamp)
        
        # Debounce for text extraction (max once per 1.5s)
        self._last_text_extraction_time: float = 0.0
        self._last_extracted_transcript_hash: str = ""
        self._text_extraction_in_flight: bool = False

        # Flash client - supports both Vertex AI and Gemini API
        if settings.GOOGLE_GENAI_USE_VERTEXAI:
            import os
            if settings.GOOGLE_APPLICATION_CREDENTIALS:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.GOOGLE_APPLICATION_CREDENTIALS
            if settings.GOOGLE_CLOUD_PROJECT:
                os.environ["GOOGLE_CLOUD_PROJECT"] = settings.GOOGLE_CLOUD_PROJECT
            
            self._client = genai.Client(
                vertexai=True,
                project=settings.GOOGLE_CLOUD_PROJECT,
                location=settings.GOOGLE_CLOUD_LOCATION
            )
            logger.info(f"[ListenerAgent] Using Vertex AI in {settings.GOOGLE_CLOUD_LOCATION}")
        else:
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
            logger.info("[ListenerAgent] Using Gemini API")
        
        # Use the effective model name (with google/ prefix for Vertex AI)
        self._flash_model = settings.effective_flash_model

        logger.info(f"[ListenerAgent] Initialized session={self.session_id[:8]}...")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background polling loop."""
        self._running = True
        self._task = asyncio.create_task(
            self._poll_loop(), name=f"listener-{self.session_id[:8]}"
        )
        logger.info(f"ðŸŽ§ ListenerAgent started")

    async def stop(self) -> None:
        """Gracefully stop the polling loop."""
        self._running = False
        await self._cancel_background_tasks()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=3.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        logger.info(f"ðŸ›‘ ListenerAgent stopped")

    def _create_background_task(self, coro, *, name: str) -> asyncio.Task | None:
        if not self._running:
            if hasattr(coro, "close"):
                coro.close()
            return None
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.add(task)

        def _done_callback(done_task: asyncio.Task) -> None:
            self._background_tasks.discard(done_task)
            try:
                done_task.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("[ListenerAgent] Background task failed: %s", exc, exc_info=True)

        task.add_done_callback(_done_callback)
        return task

    async def _cancel_background_tasks(self) -> None:
        tasks = list({task for task in self._background_tasks if not task.done()})
        self._background_tasks.clear()
        if self._research_task and not self._research_task.done() and self._research_task not in tasks:
            tasks.append(self._research_task)
        if not tasks:
            self._research_task = None
            return
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._research_task = None

    async def _safe_send_json(self, payload: dict) -> bool:
        if not self._running:
            return False
        try:
            await self.websocket.send_json(payload)
            return True
        except Exception as exc:
            msg = str(exc).lower()
            # Treat any disconnect/close variant as a soft failure
            if (
                "close" in msg or "closed" in msg
                or "disconnect" in msg or "cancelled" in msg
                or isinstance(exc, (RuntimeError, ConnectionError, OSError))
                or type(exc).__name__ in ("ConnectionClosedOK", "ConnectionClosedError",
                                         "WebSocketDisconnect", "CancelledError")
            ):
                logger.debug("[ListenerAgent] Skipping websocket send after disconnect: %s (%s)",
                             type(exc).__name__, exc)
                return False
            logger.warning("[ListenerAgent] Unexpected send_json error: %s: %s",
                           type(exc).__name__, exc)
            return False

    # ------------------------------------------------------------------
    # Event-driven fast transcription (called by NegotiationEngine on speaker switch)
    # ------------------------------------------------------------------

    async def transcribe_segment(
        self,
        speaker: str,
        audio: bytes,
        start_time: float,
        end_time: float,
    ) -> None:
        """
        Called by NegotiationEngine when a speaker turn ends (button switch).
        
        BATCHING STRATEGY (prevents 429 errors and garbage transcriptions):
        - Segments under 1.5s are buffered (too short = hallucinations)
        - Segments are batched for 3 seconds before transcription
        - One API call per batch instead of one per segment
        - Reduces API calls by 80% and eliminates garbage output
        """
        duration = len(audio) / 32000
        
        # Filter 1: Skip very short segments (likely noise, clicks, or UI sounds)
        if duration < self._min_segment_duration:
            logger.debug(f"[ListenerAgent] Skipping short segment: {duration:.2f}s (min {self._min_segment_duration}s)")
            return
        
        # Add to pending batch
        self._pending_segments.append((speaker, audio, start_time, end_time))
        
        current_time = time.time()
        time_since_last_batch = current_time - self._last_batch_time
        
        # Trigger batch transcription if:
        # 1. Batch interval elapsed (3 seconds)
        # 2. OR accumulated 5+ segments (prevent memory buildup)
        should_process_batch = (
            time_since_last_batch >= self._batch_interval or
            len(self._pending_segments) >= 5
        )
        
        if should_process_batch and self._pending_segments:
            self._last_batch_time = current_time
            segments_to_process = self._pending_segments.copy()
            self._pending_segments.clear()
            
            logger.info(f"ðŸ“¦ Processing batch of {len(segments_to_process)} segments")
            self._create_background_task(
                self._transcribe_batch(segments_to_process),
                name=f"listener-transcribe-batch-{self.session_id[:8]}",
            )
    
    async def _transcribe_batch(self, segments: list) -> None:
        """
        Transcribe a batch of segments in one API call.
        Concatenates audio, transcribes once, then splits result by speaker changes.
        """
        if not segments:
            return
        
        # Process each segment individually (simpler approach)
        for speaker, audio, start_time, end_time in segments:
            try:
                text = await asyncio.get_event_loop().run_in_executor(
                    None, lambda a=audio: self._fast_transcribe(a)
                )
            except Exception as exc:
                logger.warning(f"[ListenerAgent] Fast transcription failed: {exc}")
                continue

            if not text or not text.strip():
                continue

            text = text.strip()
            label = "User" if speaker == "user" else "Counterparty"

            # Timestamp relative to session start
            elapsed = start_time - self._session_start_time
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            ts_str = f"{mins}:{secs:02d}"

            # Append to accumulated transcript
            self.accumulated_transcript += f"\n{label} [{ts_str}]: {text}"
            # Keep transcript bounded
            if len(self.accumulated_transcript) > 8000:
                self.accumulated_transcript = self.accumulated_transcript[-6000:]

            logger.info(f"ðŸ’¬ {label}: {text}")

            # Push to frontend sidebar
            try:
                await self._safe_send_json({
                    "type": "TRANSCRIPT_UPDATE",
                    "payload": {
                        "id": f"seg_{int(start_time * 1000)}",
                        "speaker": speaker,
                        "text": text,
                        "timestamp": int(start_time * 1000),
                        "start_time": start_time,
                        "end_time": end_time,
                    },
                })
            except Exception as exc:
                logger.warning(f"[ListenerAgent] TRANSCRIPT_UPDATE send failed: {exc}")
            log_conversation_event(
                session_id=self.session.session_id,
                event="negotiation_turn",
                speaker=speaker,
                text=text,
                timestamp_ms=int(start_time * 1000),
                context="conversation",
            )
        
        # Extract context once after processing all segments in batch
        self._create_background_task(
            self._run_text_extraction_cycle(),
            name=f"listener-text-extract-{self.session_id[:8]}",
        )

    def _fast_transcribe(self, audio_bytes: bytes) -> str:
        """
        Synchronous STT â€” run in executor to avoid blocking the event loop.
        Converts PCM to WAV, sends to gemini-2.0-flash, returns raw transcript text.
        """
        import struct

        def _pcm_to_wav(pcm_data: bytes) -> bytes:
            sr, nc, sw = 16000, 1, 2
            br = sr * nc * sw
            ba = nc * sw
            ds = len(pcm_data)
            hdr = struct.pack(
                "<4sI4s4sIHHIIHH4sI",
                b"RIFF", 36 + ds, b"WAVE", b"fmt ", 16, 1, nc,
                sr, br, ba, sw * 8, b"data", ds,
            )
            return hdr + pcm_data

        wav_bytes = _pcm_to_wav(audio_bytes)
        audio_b64 = base64.b64encode(wav_bytes).decode()

        response = self._client.models.generate_content(
            model=self._flash_model,
            contents=[
                genai_types.Content(
                    role="user",
                    parts=[
                        genai_types.Part(
                            inline_data=genai_types.Blob(
                                data=audio_b64,
                                mime_type="audio/wav",
                            )
                        ),
                        genai_types.Part(
                            text=LISTENER_UTTERANCE_TRANSCRIPTION_PROMPT
                        ),
                    ]
                )
            ],
            config=genai_types.GenerateContentConfig(temperature=0.0),
        )
        return (response.text or "").strip()

    def _append_accumulated_transcript(self, label: str, text: str, ts_str: str) -> None:
        self.accumulated_transcript += f"\n{label} [{ts_str}]: {text}"
        if len(self.accumulated_transcript) > 8000:
            self.accumulated_transcript = self.accumulated_transcript[-6000:]

    async def _send_live_transcript_turn(self, speaker: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        if not self.session.live_session or not self.session.copilot_active:
            return
        if self.session.user_addressing_ai or self.session.ai_is_speaking:
            return

        label = {
            "user": "User",
            "counterparty": "Counterparty",
            "unknown": "Unknown",
        }.get(speaker, "Unknown")

        try:
            async with self.gemini_send_lock:
                await self.session.live_session.send_client_content(
                    turns=genai_types.Content(
                        role="system",
                        parts=[genai_types.Part(text=f"[LIVE_TRANSCRIPT]\n{label}: {text}")],
                    ),
                    turn_complete=False,
                )
        except Exception as exc:
            logger.warning(f"[ListenerAgent] Live transcript injection failed: {exc}")

    async def ingest_simulated_turn(
        self,
        *,
        speaker: str,
        text: str,
        timestamp_ms: int | None = None,
        scenario_id: str | None = None,
        turn_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Inject a text-only transcript turn for automated Live AI evaluation."""
        text = (text or "").strip()
        if not text:
            return None

        normalized_speaker = speaker if speaker in {"user", "counterparty", "unknown"} else "unknown"
        timestamp_ms = int(timestamp_ms or (time.time() * 1000))
        turn_started_at = timestamp_ms / 1000.0
        elapsed = turn_started_at - self._session_start_time
        mins = int(max(0.0, elapsed) // 60)
        secs = int(max(0.0, elapsed) % 60)
        ts_str = f"{mins}:{secs:02d}"
        label = {
            "user": "User",
            "counterparty": "Counterparty",
            "unknown": "Unknown",
        }.get(normalized_speaker, "Unknown")

        transcript_entry = {
            "id": turn_id or f"sim_{timestamp_ms}",
            "speaker": normalized_speaker,
            "language": self.session.language,
            "text": text,
            "timestamp": timestamp_ms,
            "start_time": turn_started_at,
            "end_time": turn_started_at,
            "speaker_confidence": 1.0,
            "transcription_confidence": 1.0,
            "eligible_for_context": True,
            "eligible_for_research": False,
            "source": "simulated_text",
            "scenario_id": scenario_id,
        }

        self.session.display_transcript_turns.append(transcript_entry)
        self.session.transcript.append(transcript_entry)
        self.session.transcript = self.session.transcript[-settings.TRANSCRIPT_HISTORY_LIMIT:]
        self.session.display_transcript_turns = self.session.display_transcript_turns[-50:]
        self.session.eligible_transcript_turns.append(transcript_entry)
        self.session.eligible_transcript_turns = self.session.eligible_transcript_turns[-10:]
        self._append_accumulated_transcript(label, text, ts_str)
        session_store.record_turn(self.session.session_id, transcript_entry, language=self.session.language)
        session_store.persist_session(self.session, ended=False)

        log_conversation_event(
            session_id=self.session.session_id,
            event="negotiation_turn",
            speaker=normalized_speaker,
            text=text,
            timestamp_ms=timestamp_ms,
            context="simulated_text",
            metadata={"scenario_id": scenario_id, "turn_id": transcript_entry["id"]},
        )

        await self._safe_send_json({
            "type": "TRANSCRIPT_UPDATE",
            "payload": transcript_entry,
        })
        await self._send_live_transcript_turn(normalized_speaker, text)
        self._create_background_task(
            self._run_text_extraction_cycle(),
            name=f"listener-text-extract-{self.session_id[:8]}",
        )
        return transcript_entry

    async def transcribe_utterance(self, utterance: FinalizedUtterance) -> None:
        """Transcribe one utterance and split display vs context eligibility."""
        try:
            utterance = await self._speech_transcriber.transcribe(utterance)
        except Exception as exc:
            reason = str(exc) or type(exc).__name__
            logger.warning("[ListenerAgent] STT transcription failed: %s", reason)
            return

        text = (utterance.transcript_text or "").strip()
        confidence = utterance.transcription_confidence
        detected_language = utterance.metadata.get("stt_response", {}).get("language_code")
        if detected_language and detected_language in settings.google_stt_language_codes_list:
            session_language_changed = self.session.language != detected_language
            self.session.language = detected_language
            if not self.session.response_language:
                self.session.response_language = detected_language
            if session_language_changed:
                try:
                    await self._safe_send_json({
                        "type": "LANGUAGE_UPDATE",
                        "payload": {
                            "language": self.session.language,
                            "response_language": self.session.response_language,
                        },
                    })
                except Exception:
                    logger.debug("Failed to send LANGUAGE_UPDATE", exc_info=True)
        if not text:
            return

        utterance.eligible_for_display = True
        utterance.eligible_for_context = (
            utterance.duration_ms >= settings.MIN_CONTEXT_DURATION_MS
            and (confidence is None or confidence >= 0.70)
        )
        utterance.eligible_for_research = utterance.eligible_for_context and any(
            token in text.lower()
            for token in ("$", "price", "iphone", "sell", "buy", "offer", "market", "pro max")
        )

        label = {
            "user": "User",
            "counterparty": "Counterparty",
            "unknown": "Unknown",
        }.get(utterance.speaker, "Unknown")

        elapsed = utterance.started_at - self._session_start_time
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        ts_str = f"{mins}:{secs:02d}"

        transcript_entry = {
            "id": utterance.utterance_id,
            "speaker": utterance.speaker,
            "text": text,
            "timestamp": int(utterance.started_at * 1000),
            "start_time": utterance.started_at,
            "end_time": utterance.ended_at,
            "speaker_confidence": utterance.speaker_confidence,
            "transcription_confidence": confidence,
            "eligible_for_context": utterance.eligible_for_context,
            "eligible_for_research": utterance.eligible_for_research,
            "source": utterance.source,
        }

        self.session.display_transcript_turns.append(transcript_entry)
        self.session.display_transcript_turns = self.session.display_transcript_turns[-50:]

        if utterance.eligible_for_context:
            self.session.eligible_transcript_turns.append(transcript_entry)
            self.session.eligible_transcript_turns = self.session.eligible_transcript_turns[-10:]
            self._append_accumulated_transcript(label, text, ts_str)

        logger.info(
            f"Ã°Å¸â€™Â¬ {label}: {text} [display={utterance.eligible_for_display}, "
            f"context={utterance.eligible_for_context}, stt_conf={confidence}, speaker_conf={utterance.speaker_confidence}]"
        )

        try:
            await self._safe_send_json({
                "type": "TRANSCRIPT_UPDATE",
                "payload": transcript_entry,
            })
            logger.info(
                f"ðŸ“¤ TRANSCRIPT_UPDATE sent: speaker={utterance.speaker}, "
                f"text='{text[:50]}...', confidence={utterance.speaker_confidence if utterance.speaker_confidence is not None else 'N/A'}"
            )
        except Exception as exc:
            logger.warning(f"[ListenerAgent] TRANSCRIPT_UPDATE send failed: {exc}")
        log_conversation_event(
            session_id=self.session.session_id,
            event="negotiation_turn",
            speaker=utterance.speaker,
            text=text,
            timestamp_ms=transcript_entry["timestamp"],
            context="conversation",
        )

        await self._send_live_transcript_turn(utterance.speaker, text)

        if utterance.eligible_for_context:
            self._create_background_task(
                self._run_text_extraction_cycle(),
                name=f"listener-text-extract-{self.session_id[:8]}",
            )

    async def process_diarized_utterance(self, utterance: FinalizedUtterance) -> None:
        """Transcribe one utterance and emit diarized turns with mapped speakers."""
        logger.info(
            f"ðŸŽ™ï¸ process_diarized_utterance called: utterance_id={utterance.utterance_id}, "
            f"duration_ms={utterance.duration_ms}, speaker={utterance.speaker}"
        )
        try:
            utterance = await self._speech_transcriber.transcribe(utterance)
            logger.info(
                f"âœ… Transcription complete: text='{(utterance.transcript_text or '')[:50]}...', "
                f"confidence={utterance.transcription_confidence}"
            )
        except Exception as exc:
            reason = str(exc) or type(exc).__name__
            logger.warning("[ListenerAgent] STT transcription failed: %s", reason)
            return

        text = (utterance.transcript_text or "").strip()
        confidence = utterance.transcription_confidence
        if not text:
            return

        diarized_turns = utterance.metadata.get("diarized_turns") or [{
            "diarized_speaker_id": utterance.speaker or "unknown",  # Use the already-classified speaker
            "text": text,
            "start_time": 0.0,
            "end_time": utterance.duration_ms / 1000.0,
            "transcription_confidence": confidence,
            "speaker": utterance.speaker or "unknown",  # Pre-set the speaker
        }]

        distinct_ids = {
            str(turn.get("diarized_speaker_id"))
            for turn in diarized_turns
            if turn.get("diarized_speaker_id") not in (None, "")
        }
        if utterance.speaker in {"user", "counterparty"} and len(distinct_ids) > 1:
            logger.info("[ListenerAgent] Mixed-speaker utterance detected; preserving diarized turns")
            utterance.speaker = "unknown"
        
        # Skip SpeakerMappingService if we already have a valid speaker from SpeechBrain
        if utterance.speaker in {"user", "counterparty"}:
            # Use the speaker classification from SpeechBrain directly
            logger.info(f"âœ… Using SpeechBrain classification: speaker={utterance.speaker}")
            diarized_turns = [
                {
                    **turn,
                    "speaker": utterance.speaker,
                }
                for turn in diarized_turns
            ]
        else:
            # Fall back to SpeakerMappingService for unknown speakers
            diarized_turns = await SpeakerMappingService(self.session).label_diarized_turns(
                diarized_turns,
                utterance.audio,
            )

        triggered_context = False
        for index, turn in enumerate(diarized_turns):
            turn_text = (turn.get("text") or "").strip()
            if not turn_text:
                continue

            speaker = turn.get("speaker") or "unknown"
            eligible_for_context = (
                utterance.duration_ms >= settings.MIN_CONTEXT_DURATION_MS
                and (confidence is None or confidence == 0.0 or confidence >= 0.70)  # Treat 0.0 as "no confidence data"
            )
            eligible_for_research = eligible_for_context and any(
                token in turn_text.lower()
                for token in ("$", "price", "iphone", "sell", "buy", "offer", "market", "pro max")
            )
            label = {
                "user": "User",
                "counterparty": "Counterparty",
                "unknown": "Unknown",
            }.get(speaker, "Unknown")
            turn_started_at = utterance.started_at + float(turn.get("start_time", 0.0) or 0.0)
            turn_ended_at = utterance.started_at + float(turn.get("end_time", 0.0) or 0.0)
            elapsed = turn_started_at - self._session_start_time
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            ts_str = f"{mins}:{secs:02d}"

            transcript_entry = {
                "id": f"{utterance.utterance_id}_{index}",
                "speaker": speaker,
                "language": self.session.language,
                "text": turn_text,
                "timestamp": int(turn_started_at * 1000),
                "start_time": turn_started_at,
                "end_time": turn_ended_at,
                "diarized_speaker_id": turn.get("diarized_speaker_id"),
                "speaker_confidence": turn.get("confidence"),
                "transcription_confidence": turn.get("transcription_confidence", confidence),
                "eligible_for_context": eligible_for_context,
                "eligible_for_research": eligible_for_research,
                "source": utterance.source,
            }
            log_speaker_debug(
                "TRANSCRIPT_DECISION",
                session_id=self.session.session_id,
                utterance_id=utterance.utterance_id,
                transcript_id=transcript_entry["id"],
                speaker=speaker,
                diarized_speaker_id=turn.get("diarized_speaker_id"),
                text=turn_text,
                transcription_confidence=transcript_entry["transcription_confidence"],
                speaker_confidence=turn.get("confidence"),
                eligible_for_context=eligible_for_context,
                eligible_for_research=eligible_for_research,
            )

            self.session.display_transcript_turns.append(transcript_entry)
            self.session.transcript.append(transcript_entry)
            self.session.transcript = self.session.transcript[-settings.TRANSCRIPT_HISTORY_LIMIT:]
            self.session.display_transcript_turns = self.session.display_transcript_turns[-50:]
            session_store.record_turn(self.session.session_id, transcript_entry, language=self.session.language)
            if eligible_for_context:
                triggered_context = True
                self.session.eligible_transcript_turns.append(transcript_entry)
                self.session.eligible_transcript_turns = self.session.eligible_transcript_turns[-10:]
                self._append_accumulated_transcript(label, turn_text, ts_str)

            try:
                await self._safe_send_json({
                    "type": "TRANSCRIPT_UPDATE",
                    "payload": transcript_entry,
                })
                logger.info(
                    f"ðŸ“¤ TRANSCRIPT_UPDATE sent: id={transcript_entry['id']}, "
                    f"speaker={transcript_entry['speaker']}, text='{turn_text[:30]}...'"
                )
            except Exception as exc:
                logger.warning(f"[ListenerAgent] TRANSCRIPT_UPDATE send failed: {exc}")
            log_conversation_event(
                session_id=self.session.session_id,
                event="negotiation_turn",
                speaker=speaker,
                text=turn_text,
                timestamp_ms=transcript_entry["timestamp"],
                context="conversation",
            )

            await self._send_live_transcript_turn(speaker, turn_text)

        if triggered_context:
            session_store.persist_session(self.session, ended=False)
            self._create_background_task(
                self._run_text_extraction_cycle(),
                name=f"listener-text-extract-{self.session_id[:8]}",
            )

    async def _run_text_extraction_cycle(self) -> None:
        """
        Fast context extraction from the labeled text transcript (~0.5-1s).
        Textâ†’text is 5-10x faster than the audio extraction path.
        Debounced and deduplicated to avoid hammering the API.
        """
        logger.info(f"ðŸ” _run_text_extraction_cycle called, in_flight={self._text_extraction_in_flight}")
        
        if not self._running:
            return

        if self._text_extraction_in_flight:
            logger.debug("[ListenerAgent] Skipping text extraction - request already in flight")
            return

        # Debounce
        now = time.time()
        if now - self._last_text_extraction_time < TEXT_EXTRACTION_DEBOUNCE_SECONDS:
            return

        transcript = self.accumulated_transcript.strip()
        if not transcript or len(transcript) < 20:
            return

        if getattr(self.session, "user_addressing_ai", False):
            return  # Don't extract during Ask AI window

        transcript_slice = transcript[-2500:]
        transcript_hash = str(hash(transcript_slice))
        if transcript_hash == self._last_extracted_transcript_hash:
            logger.debug("[ListenerAgent] Skipping text extraction - transcript unchanged")
            return

        prompt = TEXT_EXTRACTION_PROMPT + transcript_slice

        def do_extract():
            return self._client.models.generate_content(
                model=self._flash_model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(temperature=0.1),
            )

        try:
            self._text_extraction_in_flight = True
            self._last_text_extraction_time = now
            response = await asyncio.get_event_loop().run_in_executor(None, do_extract)
            if not self._running:
                return
            raw = (response.text or "").strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:]).rstrip("`").strip()
            if not raw:
                return
            context = json.loads(raw)
            self._last_extracted_transcript_hash = transcript_hash
        except Exception as exc:
            logger.warning(f"[ListenerAgent] Text extraction failed: {exc}")
            return
        finally:
            self._text_extraction_in_flight = False

        # Same post-processing as audio path
        await self._post_process_context(context)

    @staticmethod
    def _coerce_text_entry(value: Any) -> str:
        """Normalize structured model output into a comparable lowercase-safe string."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            for key in ("text", "moment", "detail", "summary", "message", "value"):
                item = value.get(key)
                if isinstance(item, str) and item.strip():
                    return item
            return json.dumps(value, sort_keys=True)
        if isinstance(value, list):
            return " ".join(
                part for part in (ListenerAgent._coerce_text_entry(item) for item in value) if part
            )
        return str(value)

    @classmethod
    def _normalize_text_list(cls, values: list[Any]) -> list[str]:
        """Convert mixed string/object lists into clean display/prompt strings."""
        normalized: list[str] = []
        for value in values or []:
            text = cls._coerce_text_entry(value).strip()
            if text:
                normalized.append(text)
        return normalized

    async def _post_process_context(self, context: dict) -> None:
        """
        Common post-extraction processing shared by both the audio path (_run_cycle)
        and the text path (_run_text_extraction_cycle):
          - Detect critical events
          - Merge into accumulated state
          - Send CONTEXT_UPDATE to frontend
          - Inject into Live AI (if copilot active)
          - Trigger market research if needed
        """
        # â”€â”€ Critical event detection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if not self._running:
            return

        critical_events: list[dict] = []

        new_price = context.get("seller_asking_price") or context.get("counterparty_price")
        old_price = self.last_context.get("seller_asking_price") or self.last_context.get("counterparty_price")
        if new_price is not None and new_price != old_price:
            critical_events.append({
                "event_type": "ANCHOR_DETECTED",
                "detail": {"new_price": new_price, "old_price": old_price},
            })

        prev_sentiment = self.last_context.get("counterparty_sentiment")
        new_sentiment = context.get("counterparty_sentiment")
        if prev_sentiment in ("positive", "neutral") and new_sentiment == "negative":
            critical_events.append({
                "event_type": "SENTIMENT_NEGATIVE",
                "detail": {"from": prev_sentiment, "to": new_sentiment},
            })

        _URGENCY_KEYWORDS = (
            "urgent", "deadline", "today only", "last offer", "final price",
            "need to sell", "leaving", "other buyer",
        )
        for moment in context.get("key_moments", []):
            moment_text = self._coerce_text_entry(moment).lower()
            if moment_text and any(kw in moment_text for kw in _URGENCY_KEYWORDS):
                critical_events.append({"event_type": "URGENCY_DETECTED", "detail": {"moment": moment}})
                break

        _PRESSURE_MARKERS = (
            "scarc", "limited", "only one", "last chance", "take it or leave",
            "now or never", "emotional", "guilt", "pressure", "final", "ultimatum",
        )
        for text in (context.get("leverage_points", []) + context.get("key_moments", [])):
            text_value = self._coerce_text_entry(text).lower()
            if text_value and any(m in text_value for m in _PRESSURE_MARKERS):
                critical_events.append({"event_type": "PRESSURE_TACTIC", "detail": {"text": text}})
                break

        # â”€â”€ Merge + forward â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Attach latest vision observation (if fresh) so it flows into advisor
        self._attach_vision_observation(context)

        self._merge_context(context)
        await self._send_context_update(context)

        if not self.session.copilot_active:
            if critical_events:
                self._pre_activation_critical_events.extend(critical_events)
        elif self._on_context_ready:
            context_changed = self._has_context_changed(self.last_context)
            if context_changed or critical_events:
                if context_changed:
                    self._update_last_sent_context(self.last_context)
                await self._on_context_ready(self.last_context, critical_events)

        if critical_events:
            self._critical_events_since_research += len(critical_events)

        # â”€â”€ Market research trigger â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        new_query = self.last_context.get("research_query")
        research_gap = context.get("research_gap")
        research_needed = context.get("research_needed", False)
        _RESEARCH_COOLDOWN_SECS = 90
        current_time = time.time()
        cooldown_passed = (current_time - self._last_research_timestamp) > _RESEARCH_COOLDOWN_SECS

        if cooldown_passed and not self._research_task:
            current_item = self.last_context.get("item") or ""
            current_type = self.last_context.get("negotiation_type") or ""
            market_data_missing = not self.last_context.get("market_data")
            item_changed = current_item and current_item != self._last_researched_item
            type_changed = current_type and current_type != self._last_researched_type
            critical_pressure = self._critical_events_since_research >= 2
            first_research = not self._last_researched_item
            has_price_context = any(
                self.last_context.get(f) is not None
                for f in ("seller_asking_price", "buyer_offer", "counterparty_price", "user_price", "user_target_price")
            )
            gap_is_new = (
                research_needed and research_gap and research_gap != self._last_research_gap
            )
            should_research = (
                (first_research and has_price_context)
                or item_changed or type_changed
                or (market_data_missing and current_item)
                or critical_pressure or gap_is_new
            ) and (new_query or gap_is_new)

            if should_research:
                reason = (
                    "ai_uncertainty" if gap_is_new and not (first_research or item_changed or type_changed)
                    else "first_research" if first_research
                    else "item_changed" if item_changed
                    else "type_changed" if type_changed
                    else "market_data_missing" if market_data_missing
                    else "critical_pressure"
                )
                effective_query = research_gap if gap_is_new else new_query
                logger.info(f"ðŸ”¬ Research triggered: {effective_query}")
                self._last_research_timestamp = current_time
                self._last_researched_item = current_item
                self._last_researched_type = current_type
                self._critical_events_since_research = 0
                if gap_is_new:
                    self._last_research_gap = research_gap
                self._research_task = self._create_background_task(
                    self._run_market_research(
                        effective_query,
                        reason,
                        research_gap if gap_is_new else None,
                    ),
                    name=f"listener-research-{self.session_id[:8]}",
                )

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Main loop â€” runs every POLL_INTERVAL seconds."""
        # Give the session a moment to stabilise before first poll
        await asyncio.sleep(POLL_INTERVAL)

        while self._running:
            cycle_start = time.monotonic()
            try:
                await self._run_cycle()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(
                    f"[ListenerAgent] Cycle {self._cycle_count} error "
                    f"(skipping): {exc}",
                    exc_info=True,
                )

            elapsed = time.monotonic() - cycle_start
            sleep_time = max(0.0, POLL_INTERVAL - elapsed)
            await asyncio.sleep(sleep_time)

    # ------------------------------------------------------------------
    # Single extraction cycle
    # ------------------------------------------------------------------

    async def _run_cycle(self) -> None:
        """
        Main polling cycle (every POLL_INTERVAL seconds).
        
        Modified for PerfectListenerSystem integration:
        - Reads accumulated_transcript (populated by PerfectListenerSystem)
        - Extracts context from transcript text (no audio processing)
        - Skips cycle if accumulated_transcript is empty or too short
        """
        self._cycle_count += 1
        
        logger.debug(f"ðŸ”„ Cycle {self._cycle_count} starting...")

        # Skip while user is speaking directly to the AI â€” prevents their question
        # from polluting negotiation context extraction.
        if getattr(self.session, "user_addressing_ai", False):
            logger.debug("[ListenerAgent] Skipping cycle â€” user is addressing AI")
            return

        # Check if we have transcript to process
        transcript = self.accumulated_transcript.strip()
        if not transcript or len(transcript) < 30:
            logger.debug(f"[ListenerAgent] No transcript to process (length={len(transcript)})")
            return

        # Extract context from transcript (text-to-text, fast)
        await self._run_text_extraction_cycle()

    async def _run_market_research(self, research_query: str, trigger_reason: str = "scheduled", research_gap: str = None) -> None:
        """Run asynchronous market research using Gemini Flash with Google Search."""
        try:
            self.session.session_metrics["research_requests"] += 1
            self.session.session_metrics["research_calls"] += 1
            session_store.record_research_event(
                self.session.session_id,
                research_query,
                "started",
                {"query": research_query, "trigger_reason": trigger_reason, "research_gap": research_gap},
            )

            # Notify frontend that research has started
            await self._safe_send_json({
                "type": "RESEARCH_STARTED",
                "payload": {"query": research_query}
            })

            # Build context snapshot for the prompt
            item = self.last_context.get("item") or "unknown"
            negotiation_type = self.last_context.get("negotiation_type") or "unknown"
            counterparty_goal = self.last_context.get("counterparty_goal") or "unknown"
            seller_price = (
                self.last_context.get("counterparty_price")
                or self.last_context.get("seller_asking_price")
            )
            key_moments = self._normalize_text_list(self.last_context.get("key_moments", []))
            leverage_points = self._normalize_text_list(self.last_context.get("leverage_points", []))

            context_summary = (
                f"Item/Subject: {item}\n"
                f"Negotiation Type: {negotiation_type}\n"
                f"Counterparty Goal: {counterparty_goal}\n"
                f"Counterparty's Current Price/Rate: {seller_price}\n"
                f"Key Moments So Far: {'; '.join(key_moments) if key_moments else 'none'}\n"
                f"Known Leverage Points: {'; '.join(leverage_points) if leverage_points else 'none'}\n"
                f"Research Trigger: {trigger_reason}"
            )

            research_prompt = f"""
You are providing real-time intelligence to help someone negotiate RIGHT NOW.

CURRENT NEGOTIATION CONTEXT:
{context_summary}

{"SPECIFIC KNOWLEDGE GAP TO RESOLVE: " + research_gap if research_gap else "SEARCH QUERY: " + '"' + research_query + '"'}

Search the internet and return ONLY a valid JSON object with no markdown:
{{
  "price_range": "The fair market range as a specific number range with source (e.g. '$Xâ€“$Y on Booking.com', '$Xâ€“$Y/year per Glassdoor', '$Xâ€“$Y on eBay sold listings'). null if not found.",
  "key_facts": "One critical fact that directly affects the value or negotiating position in this specific scenario â€” depreciation, seasonal demand, vacancy rate, industry benchmark, known defects, supply/demand conditions. null if not found.",
  "leverage": "One specific leverage point the user can deploy in the next 60 seconds â€” a competing alternative, a market condition, a timing pressure on the counterparty, or an information advantage. Make it concrete and actionable.",
  "tactics": "Two or three real-world negotiation tactics that expert negotiators use specifically for this type of deal ({negotiation_type}). Base these on actual negotiation research and what works in practice for this domain. Format as: 'Tactic 1: [name] â€” [one sentence how to use it]. Tactic 2: [name] â€” [one sentence]. Tactic 3: [name] â€” [one sentence].'",
  "gap_answer": "{('Direct answer to: ' + research_gap) if research_gap else 'null'} â€” answer this specific question from your search results. null if no knowledge gap was provided."
}}

Rules:
- Be specific with numbers â€” give a range, not vague language
- Tailor everything to the domain: {negotiation_type}
- tactics must be real techniques adapted to this exact scenario
- If trigger_reason is 'critical_pressure', prioritize counter-tactics to pressure moves
- If trigger_reason is 'ai_uncertainty', prioritize answering the knowledge gap directly
- If no price data found, state the closest relevant benchmark
"""

            research_prompt = build_market_research_prompt(
                context_summary=context_summary,
                research_query=research_query,
                research_gap=research_gap,
                negotiation_type=negotiation_type,
                trigger_reason=trigger_reason,
            )

            logger.info(
                "Running market research",
                extra={
                    "session_id": self.session_id,
                    "research_query": research_query,
                    "trigger_reason": trigger_reason,
                },
            )
            
            # Run the blocking API call in an executor
            def do_research():
                return self._client.models.generate_content(
                    model=self._flash_model,
                    contents=research_prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.1,
                        tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())]
                    )
                )
                
            async with self.session.research_lock:
                async with self._research_limiter:
                    async def _on_retry(_attempt: int, _exc: Exception) -> None:
                        logger.warning("[ListenerAgent] Retrying market research for %s", research_query)

                    response = await run_with_retries(
                        "market_research",
                        lambda: asyncio.get_event_loop().run_in_executor(None, do_research),
                        max_retries=settings.RESEARCH_MAX_RETRIES,
                        base_backoff_ms=settings.RESEARCH_BASE_BACKOFF_MS,
                        max_backoff_ms=settings.RESEARCH_MAX_BACKOFF_MS,
                        is_retryable=lambda exc: any(
                            marker in str(exc).lower()
                            for marker in ("429", "resource exhausted", "temporar", "timeout", "503", "500")
                        ),
                        on_retry=_on_retry,
                    )
            
            raw = response.text
            if raw:
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = "\n".join(raw.split("\n")[1:])
                    raw = raw.rstrip("`").strip()
            else:
                raw = "{}"
                
            if not raw:
                market_data = {}
            else:
                market_data = json.loads(raw)
            logger.info(f"âœ… Research complete: {market_data.get('item', 'N/A')}")
            
            # Build a rich formatted string from the structured fields
            # so all downstream code that reads market_data as a string still works
            parts = []
            if market_data.get("price_range"):
                parts.append(f"Price Range: {market_data['price_range']}")
            if market_data.get("key_facts"):
                parts.append(f"Key Facts: {market_data['key_facts']}")
            if market_data.get("leverage"):
                parts.append(f"Leverage: {market_data['leverage']}")
            if market_data.get("tactics"):
                parts.append(f"Tactics: {market_data['tactics']}")
            if market_data.get("gap_answer") and market_data["gap_answer"] != "null":
                parts.append(f"Gap Answer: {market_data['gap_answer']}")
            insights = " | ".join(parts) if parts else "No market data found."

            self.last_context["market_data"] = insights
            event_payload = {
                "query": research_query,
                "market_data": insights,
                "timestamp": time.time(),
                "trigger_reason": trigger_reason,
            }
            self.session.research_history.append(event_payload)
            self.session.research_history = self.session.research_history[-settings.RESEARCH_HISTORY_LIMIT:]
            session_store.record_research_event(
                self.session.session_id,
                research_query,
                "completed",
                event_payload,
            )
            session_store.persist_session(self.session, ended=False)
            
            # Notify frontend with results
            await self._safe_send_json({
                "type": "RESEARCH_COMPLETE",
                "payload": event_payload
            })
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.session.session_metrics["research_failures"] += 1
            logger.error(f"[ListenerAgent] Background research failed: {e}")
            session_store.record_research_event(
                self.session.session_id,
                research_query,
                "failed",
                {"query": research_query, "error": str(e), "timestamp": time.time()},
            )
            await self._safe_send_json({
                "type": "RESEARCH_FAILED",
                "payload": {"error": str(e)}
            })
        finally:
            self._research_task = None

    def _build_speaker_timeline_hint(self) -> str:
        """
        Build a speaker timeline hint for the current audio window.

        Reads the session's speaker_timeline (list of {speaker, timestamp} entries)
        and produces a human-readable map of who spoke when within the last
        WINDOW_SECONDS. This replaces the single 'primary speaker' hint so Flash
        can attribute prices to the correct person even in mixed-speaker windows.

        Returns a formatted string to prepend to the extraction prompt.
        """
        timeline = getattr(self.session, 'speaker_timeline', [])
        current_speaker = getattr(self.session, 'current_speaker', 'unknown')
        now = time.time()
        window_start = now - WINDOW_SECONDS

        # Filter to entries within the current audio window
        window_entries = [e for e in timeline if e.get("timestamp", 0) >= window_start]

        if not window_entries:
            # No timeline data yet â€” use current_speaker as fallback
            if current_speaker == "unknown":
                return (
                    "SPEAKER CONTEXT: Speaker identity not yet confirmed. "
                    "Use conversation content and context to infer who is making each statement. "
                    "Do not assume any price belongs to a specific role â€” infer from language cues "
                    "(e.g. 'I want', 'my price', 'I can offer' = likely the person speaking; "
                    "'they want', 'asking for' = referencing the other party).\n\n"
                )
            elif current_speaker == "user":
                return (
                    "SPEAKER CONTEXT: The most recently identified speaker is the USER. "
                    "Attribute price statements to user fields unless language clearly indicates "
                    "they are referencing the counterparty's price.\n\n"
                )
            else:
                return (
                    "SPEAKER CONTEXT: The most recently identified speaker is the COUNTERPARTY. "
                    "Attribute price statements to seller_price unless language clearly indicates "
                    "they are referencing the user's offer.\n\n"
                )

        # Build a relative-time timeline for the window
        lines = ["SPEAKER TIMELINE for this audio window (use this to attribute who said what):"]
        prev_ts = window_start
        for i, entry in enumerate(window_entries):
            ts = entry.get("timestamp", prev_ts)
            speaker = entry.get("speaker", "unknown")
            rel_start = max(0.0, ts - window_start)
            # End of this speaker's turn = start of next entry or end of window
            if i + 1 < len(window_entries):
                rel_end = min(WINDOW_SECONDS, window_entries[i + 1].get("timestamp", now) - window_start)
            else:
                rel_end = WINDOW_SECONDS
            lines.append(f"  {rel_start:.1f}s â€“ {rel_end:.1f}s : {speaker.upper()}")
            prev_ts = ts

        lines.append(
            "Use this timeline to determine who said each price or statement. "
            "A price mentioned during a USER turn â†’ user fields. "
            "A price mentioned during a COUNTERPARTY turn â†’ seller_price. "
            "If someone quotes the other party's price (e.g. 'you said $800'), "
            "do NOT assign it to their own fields â€” it is a reference, not an offer."
        )
        return "\n".join(lines) + "\n\n"

    def _call_flash(self, audio_bytes: bytes, segments: list = None) -> Optional[dict]:
        """
        Synchronous call to Gemini Flash (run in executor so it doesn't
        block the event loop).  Returns parsed context dict or None.

        Solution 1: If segments are provided, sends each speaker's audio chunk
        separately with a label so Flash knows exactly who said what.
        Solution 2: Also injects a speaker timeline hint for handling overlaps.
        """
        try:
            import struct
            def pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000, num_channels: int = 1, sample_width: int = 2) -> bytes:
                byte_rate = sample_rate * num_channels * sample_width
                block_align = num_channels * sample_width
                data_size = len(pcm_data)
                chunk_size = 36 + data_size
                header = struct.pack(
                    '<4sI4s4sIHHIIHH4sI',
                    b'RIFF', chunk_size, b'WAVE', b'fmt ', 16, 1, num_channels,
                    sample_rate, byte_rate, block_align, sample_width * 8, b'data', data_size
                )
                return header + pcm_data

            # Convert current audio to WAV
            wav_bytes = pcm_to_wav(audio_bytes)
            audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")

            # Build parts list
            # Note: This method is kept for manual mode compatibility (transcribe_segment)
            # PerfectListenerSystem handles automatic transcription and speaker identification
            parts = []

            # Solution 1: Add per-speaker audio segments with labels if available
            # Solution 2: Fall back to full audio + timeline hint if only one segment
            if segments and len(segments) > 1:
                # Multiple segments â€” send each chunk labeled with speaker
                for seg in segments:
                    speaker_label = seg["speaker"].upper()
                    seg_wav = pcm_to_wav(seg["audio"])
                    seg_b64 = base64.b64encode(seg_wav).decode("utf-8")
                    # Label before each audio chunk
                    parts.append(genai_types.Part(text=f"[{speaker_label} speaking â€” {seg['start_ago']:.1f}s to {seg['end_ago']:.1f}s ago]\n"))
                    parts.append(genai_types.Part(
                        inline_data=genai_types.Blob(mime_type="audio/wav", data=seg_b64)
                    ))
                timeline_hint = "SPEAKER SEGMENTS (authoritative â€” use these to attribute prices and statements):\n"
                for seg in segments:
                    timeline_hint += f"  {seg['start_ago']:.1f}sâ€“{seg['end_ago']:.1f}s ago: {seg['speaker'].upper()}\n"
                timeline_hint += "Each audio chunk above is labeled with its speaker. Attribute all statements accordingly.\n\n"
                parts.append(genai_types.Part(text=timeline_hint))
            else:
                # Single segment or no timeline â€” send full audio with timeline hint (Solution 2)
                audio_part = genai_types.Part(
                    inline_data=genai_types.Blob(mime_type="audio/wav", data=audio_b64)
                )
                parts.append(audio_part)
                if segments:
                    speaker_label = segments[0]["speaker"].upper()
                    parts.append(genai_types.Part(
                        text=f"SPEAKER CONTEXT: The speaker in this audio is {speaker_label}.\n\n"
                    ))

            # Build prompt
            known_item = self.last_context.get("item")
            if known_item:
                prompt_with_item = f"""You are analyzing a live negotiation audio recording about: {known_item}. Do TWO things simultaneously:

1. TRANSCRIBE the speech with speaker diarization.
2. EXTRACT negotiation context.

Return strict JSON only â€” no markdown, no extra text:
{{
  "item": "{known_item}",
  "negotiation_type": "one of: buying_goods | selling_goods | renting | salary | service | contract | other | unknown â€” from the USER's perspective.",
  "buyer_offer": null,
  "counterparty_price": null,
  "user_price": null,
  "user_target_price": null,
  "user_walk_away_price": null,
  "counterparty_goal": "one sentence â€” what counterparty wants beyond price. null if unknown.",
  "key_moments": ["one-sentence each â€” notable things said that shift the negotiation"],
  "leverage_points": ["one-sentence each, max 3 â€” time pressure, information asymmetry, alternatives, weaknesses, advantages"],
  "counterparty_sentiment": "positive|neutral|negative|unknown",
  "research_query": "Precise search query for fair market value of {known_item}. Include year. null if not enough specifics.",
  "transcript_snippet": "verbatim excerpt of the most important exchange (max 400 chars)",
  "diarization": [
    {{"speaker": "Speaker 1", "text": "exact words spoken", "start_time": 0.0}},
    {{"speaker": "Speaker 2", "text": "exact words spoken", "start_time": 3.5}}
  ]
}}

DIARIZATION RULES:
- Use "Speaker 1" for one voice, "Speaker 2" for the other â€” keep labels consistent.
- Start a new entry each time the speaker changes.
- If only one person spoke, return one entry under "Speaker 1".
- If audio is silent or no clear speech, return empty array: "diarization": []
- Transcribe product names, prices, and numbers exactly as spoken.

PRICE RULES: Prices are numbers only (no currency symbols). IMPORTANT: Keep item as "{known_item}"."""
            else:
                prompt_with_item = EXTRACTION_PROMPT

            prompt_with_item = build_audio_extraction_prompt(known_item)

            # diarization field is now embedded inside the JSON schema in prompt_with_item.
            # No separate diarization_prompt needed â€” Flash sees the full schema at once.
            text_part = genai_types.Part(text=prompt_with_item)
            parts.append(text_part)

            logger.debug(f"ðŸ” Flash: {len(audio_bytes) / 32000:.1f}s")
            
            response = self._client.models.generate_content(
                model=self._flash_model,
                contents=[genai_types.Content(role="user", parts=parts)],
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )

            raw = response.text
            if raw:
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = "\n".join(raw.split("\n")[1:])
                    raw = raw.rstrip("`").strip()

            if not raw:
                logger.warning("[ListenerAgent] Flash returned empty response")
                parsed = {}
            else:
                logger.info(f"[ListenerAgent] Flash raw response: {raw}")
                parsed = json.loads(raw)

            diarization_count = len(parsed.get("diarization", []))
            logger.info(f"âœ… Flash: {diarization_count} turns, item={parsed.get('item', 'N/A')}")

            # Log each turn at debug level
            for i, turn in enumerate(parsed.get("diarization", [])):
                speaker = turn.get("speaker", "UNKNOWN")
                text = turn.get("text", "")[:60]
                logger.debug(f"   Turn {i+1}: [{speaker}] {text}...")

            # Fallback: if Flash returned no diarization but audio was long enough,
            # create a single-turn entry using the transcript_snippet so something
            # always appears in the transcript panel.
            if diarization_count == 0 and len(audio_bytes) >= 32000:  # >= 1 second
                snippet = (parsed.get("transcript_snippet") or "").strip()
                logger.info(f"[ListenerAgent] Flash returned 0 turns. Snippet: '{snippet}', audio_len={len(audio_bytes)}")
                if snippet:
                    logger.info(f"Creating fallback turn from snippet: {snippet}")
                    parsed["diarization"] = [{"speaker": "Speaker 1", "text": snippet, "start_time": 0.0}]
                else:
                    logger.warning(f"[ListenerAgent] No snippet available for fallback turn")

            return parsed

        except Exception as exc:
            logger.warning(f"[ListenerAgent] Flash call failed: {exc}")
            return None

    def _attach_vision_observation(self, context: dict) -> None:
        """Attach the latest VisionObservation from the session to the context dict.

        Only attaches if the observation is fresh (< VISION_OBS_STALENESS_SECONDS old)
        and has confidence != 'low'. The observation is stored under the key
        'vision_observation' and consumed by build_pre_query_brief().
        """
        import time as _time
        obs_list = getattr(self.session, "vision_observations", None)
        if not obs_list:
            return
        latest = obs_list[-1]
        age = _time.time() - latest.get("timestamp", 0)
        from app.config import settings as _s
        if age > _s.VISION_OBS_STALENESS_SECONDS:
            return
        if latest.get("confidence") == "low":
            return
        context["vision_observation"] = latest

    def _merge_context(self, context: dict) -> None:
        """Merge new context into accumulated state (non-destructive)."""
        # Option 1 (role-agnostic) + Option 3 (role-specific) field names
        for key in ("seller_asking_price", "buyer_offer", "counterparty_price", "user_price", "user_target_price", "user_walk_away_price", "counterparty_sentiment", "research_query", "negotiation_type", "counterparty_goal"):
            if context.get(key) is not None:
                self.last_context[key] = context[key]

        # Contamination guard: if buyer_offer equals seller_asking_price, this might be
        # legitimate (they agreed on price) OR contamination (someone referenced the other's price).
        # We'll allow it but log a warning for monitoring.
        seller_price = self.last_context.get("seller_asking_price")
        buyer_price = self.last_context.get("buyer_offer")
        if seller_price is not None and buyer_price is not None and seller_price == buyer_price:
            logger.warning(
                f"[ListenerAgent] buyer_offer={buyer_price} matches seller_asking_price={seller_price}. "
                f"This could be agreement or contamination. Keeping both for now."
            )

        # FIX: Never downgrade the item - if we already have a specific item name,
        # don't overwrite it with a generic term like "phone" or "it"
        new_item = context.get("item")
        old_item = self.last_context.get("item")
        if new_item is not None:
            # Only update if: no previous item, OR new item is longer/more specific
            if old_item is None or len(new_item) > len(old_item):
                self.last_context["item"] = new_item
            # Log if we blocked a downgrade
            elif old_item and len(new_item) < len(old_item):
                logger.info(f"[ListenerAgent] Blocking item downgrade: '{old_item}' -> '{new_item}'")

        # transcript_snippet is a raw unstructured excerpt from Flash that may contain
        # BOTH speakers' words in a single string. We intentionally do NOT add it to
        # accumulated_transcript here â€” PerfectListenerSystem handles transcription with proper
        # per-turn speaker labels. Adding the mixed snippet would corrupt the transcript
        # with wrong labels (the old code assigned the whole blob to current_speaker).
        snippet = context.get("transcript_snippet", "")
        if snippet:
            logger.debug(f"[ListenerAgent] transcript_snippet (not added to transcript): '{snippet[:80]}'")


        # Accumulate key moments and leverage points (deduplicated and capped)
        for field in ("key_moments", "leverage_points"):
            existing = self.last_context.get(field, [])
            new_items = context.get(field, [])
            
            # Add new items if they aren't already in the list
            for item in new_items:
                if item not in existing:
                    existing.append(item)
            
            # FIX: Cap the list to the 5 most recent items so the context doesn't grow forever
            # and cause the AI to repeatedly react to old triggers
            self.last_context[field] = existing[-5:]

    def _has_context_changed(self, context: dict) -> bool:
        """Check if any meaningful context has changed since last sent to AI."""
        if not self._last_sent_context:
            return True  # First time, always send
        
        last_sent = self._last_sent_context
        
        # Compare key fields that matter for the AI
        if context.get("item") != last_sent.get("item"):
            return True
        if context.get("seller_price") != last_sent.get("seller_price"):
            return True
        if context.get("user_offer") != last_sent.get("user_offer"):
            return True
        if context.get("user_target_price") != last_sent.get("user_target_price"):
            return True
        if context.get("user_max_price") != last_sent.get("user_max_price"):
            return True
        if context.get("counterparty_sentiment") != last_sent.get("counterparty_sentiment"):
            return True
        
        # Compare lists (key_moments, leverage_points)
        new_moments = self._normalize_text_list(context.get("key_moments", []))
        old_moments = self._normalize_text_list(last_sent.get("key_moments", []))
        if set(new_moments) != set(old_moments):
            return True
        
        new_leverage = self._normalize_text_list(context.get("leverage_points", []))
        old_leverage = self._normalize_text_list(last_sent.get("leverage_points", []))
        if set(new_leverage) != set(old_leverage):
            return True
        
        # Compare transcript snippet
        new_snippet = context.get("transcript_snippet", "")
        old_snippet = last_sent.get("transcript_snippet", "")
        if new_snippet != old_snippet:
            return True
        
        return False

    def _update_last_sent_context(self, context: dict) -> None:
        """Update the last sent context after successfully sending to AI."""
        self._last_sent_context = {
            "item": context.get("item"),
            "negotiation_type": context.get("negotiation_type"),
            "seller_price": context.get("seller_price"),
            "user_offer": context.get("user_offer"),
            "user_target_price": context.get("user_target_price"),
            "user_max_price": context.get("user_max_price"),
            "counterparty_sentiment": context.get("counterparty_sentiment"),
            "counterparty_goal": context.get("counterparty_goal"),
            "key_moments": context.get("key_moments", []),
            "leverage_points": context.get("leverage_points", []),
            "transcript_snippet": context.get("transcript_snippet", ""),
        }

    async def _send_context_update(self, context: dict) -> None:
        """Send CONTEXT_UPDATE to the frontend WebSocket."""
        try:
            # Resolve counterparty price: prefer counterparty_price, fall back to seller_asking_price
            counterparty_price = (
                self.last_context.get("counterparty_price")
                or self.last_context.get("seller_asking_price")
            )
            # Resolve user price: prefer user_price, fall back to buyer_offer
            user_price = (
                self.last_context.get("user_price")
                or self.last_context.get("buyer_offer")
            )

            payload = {
                "type": "CONTEXT_UPDATE",
                "payload": {
                    "item": self.last_context.get("item"),
                    "negotiation_type": self.last_context.get("negotiation_type"),
                    "seller_price": counterparty_price,
                    "user_offer": user_price,
                    "user_target_price": self.last_context.get("user_target_price"),
                    "user_max_price": self.last_context.get("user_walk_away_price"),
                    "sentiment": self.last_context.get("counterparty_sentiment", "unknown"),
                    "counterparty_goal": self.last_context.get("counterparty_goal"),
                    "key_moments": self.last_context.get("key_moments", []),
                    "leverage_points": self.last_context.get("leverage_points", []),
                    "transcript_snippet": context.get("transcript_snippet", ""),
                    "market_data": self.last_context.get("market_data"),
                    "cycle": self._cycle_count,
                },
            }
            sent = await self._safe_send_json(payload)
            if sent:
                logger.info(f"ðŸ“¤ CONTEXT_UPDATE sent (cycle {self._cycle_count})")
        except Exception as exc:
            logger.warning(
                f"[ListenerAgent] Failed to send CONTEXT_UPDATE: {exc}"
            )

    # ------------------------------------------------------------------
    # Public helpers (used by negotiation_engine)
    # ------------------------------------------------------------------

    def build_advisor_query(self, user_context: dict) -> str:
        """
        Build the ADVISOR_QUERY text injected by handle_ask_ai_button.
        Merges user-supplied context (from SetupDialog) with
        listener-accumulated context.
        """
        parts = ["ðŸ”” ADVISOR_QUERY"]

        # From user setup form
        if user_context.get("item"):
            parts.append(f"Item: {user_context['item']}")
        if user_context.get("target_price"):
            parts.append(f"User target: {user_context['target_price']}")
        if user_context.get("max_price"):
            parts.append(f"User maximum: {user_context['max_price']}")
        if user_context.get("extra_context"):
            parts.append(f"Notes: {user_context['extra_context']}")

        # From listener
        if self.last_context.get("item") and not user_context.get("item"):
            parts.append(f"Detected item: {self.last_context['item']}")
        counterparty_price = (
            self.last_context.get("counterparty_price")
            or self.last_context.get("seller_asking_price")
        )
        if counterparty_price:
            parts.append(f"Counterparty is asking/offering: {counterparty_price}")
        user_price = (
            self.last_context.get("user_price")
            or self.last_context.get("buyer_offer")
        )
        if user_price:
            parts.append(f"User has offered/stated: {user_price}")
        if self.last_context.get("leverage_points"):
            parts.append(
                "Leverage points: "
                + "; ".join(self.last_context["leverage_points"])
            )
        if self.last_context.get("market_data"):
            parts.append(f"Market Research: {self.last_context['market_data']}")

        # Recent transcript
        if self.accumulated_transcript:
            recent = self.accumulated_transcript[-600:]
            parts.append(f"Recent conversation: \"{recent}\"")

        return "\n".join(parts)

    def force_reextraction(self) -> None:
        """
        Force the next extraction cycle to run immediately, ignoring the
        MIN_NEW_AUDIO threshold. Used when manual speaker identification
        occurs to re-extract the last audio window with correct speaker context.
        """
        self._force_next_extraction = True
        logger.info(
            f"[ListenerAgent] Force re-extraction flag set - "
            f"next cycle will re-extract last {WINDOW_SECONDS}s with updated speaker"
        )

    def force_immediate_cycle(self) -> None:
        """
        Trigger an out-of-band extraction cycle right now, bypassing the poll interval
        and MIN_NEW_AUDIO gate. Call this when the user requests advice/command so they
        get fresh context immediately instead of waiting for the next scheduled cycle.
        """
        if self._running:
            self._force_next_extraction = True
            self._create_background_task(
                self._run_cycle(), name=f"listener-immediate-{self.session_id[:8]}"
            )
            logger.info(f"[ListenerAgent] Immediate extraction cycle triggered [{self.session_id}]")
