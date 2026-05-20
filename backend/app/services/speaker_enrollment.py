"""
Speaker Enrollment Service

Quality-gated live enrollment for SpeechBrain ECAPA-TDNN.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

import torch

from app.config import settings
from app.models.negotiation import NegotiationSession
from app.services.speechbrain_service import speechbrain_service
from app.utils.speaker_debug import log_speaker_debug

logger = logging.getLogger(__name__)

ENROLLMENT_SCRIPT = (
    "Hello, I am preparing for an important negotiation today. "
    "I want to speak clearly, stay calm under pressure, and explain my position with confidence. "
    "My goal is to reach a fair deal, protect my budget, and respond thoughtfully to every offer "
    "while keeping the conversation respectful and productive."
)


class EnrollmentState(str, Enum):
    IDLE = "IDLE"
    CAPTURING = "CAPTURING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class SpeakerEnrollmentService:
    SAMPLE_RATE = 16000
    BYTES_PER_SAMPLE = 2
    MIN_DB_THRESHOLD = settings.ENROLLMENT_MIN_DB
    EVALUATION_INTERVAL_SECONDS = 1.0

    def __init__(self, session: NegotiationSession):
        self.session = session
        self.state = EnrollmentState.IDLE
        self.audio_buffer: bytes = b""
        self.start_time: Optional[float] = None
        self._last_feedback: str = "LISTENING"
        self._last_evaluation_at: float = 0.0

    async def start_enrollment(self) -> dict:
        logger.info("Starting SpeechBrain voice enrollment [session=%s]", self.session.session_id)
        log_speaker_debug(
            "ENROLLMENT_START",
            session_id=self.session.session_id,
            speechbrain_enabled=settings.SPEECHBRAIN_ENABLED,
            speaker_mode=self.session.speaker_mode,
        )
        self.state = EnrollmentState.CAPTURING
        self.audio_buffer = b""
        self.start_time = time.time()
        self._last_feedback = "LISTENING"
        self._last_evaluation_at = 0.0

        self.cleanup()
        self.state = EnrollmentState.CAPTURING
        self.session.speechbrain_profile_state = "collecting"
        self.session.speechbrain_last_result = None
        self.session.speaker_mode = "auto"

        if not settings.SPEECHBRAIN_ENABLED:
            self.state = EnrollmentState.FAILED
            return {
                "type": "ENROLLMENT_FAILED",
                "payload": {
                    "success": False,
                    "error": "provider_disabled",
                    "message": "SpeechBrain is disabled. Use manual mode or enable SpeechBrain in the backend env.",
                    "can_retry": False,
                },
            }

        ok, reason = speechbrain_service.probe_capability()
        if not ok:
            self.state = EnrollmentState.FAILED
            self.session.speechbrain_profile_state = "failed"
            return {
                "type": "ENROLLMENT_FAILED",
                "payload": {
                    "success": False,
                    "error": "provider_init_failed",
                    "message": f"Failed to initialize SpeechBrain: {reason}",
                    "can_retry": True,
                },
            }

        self.session.speechbrain_profile_state = "enrolling"
        return {
            "type": "ENROLLMENT_STARTED",
            "payload": {
                "duration_seconds": None,
                "sample_rate": self.SAMPLE_RATE,
                "message": "Keep speaking until the system confirms your voice sample is ready.",
                "script": ENROLLMENT_SCRIPT,
                "progress": None,
            },
        }

    async def process_audio(self, chunk: bytes) -> Optional[dict]:
        if self.state != EnrollmentState.CAPTURING:
            return None

        self.audio_buffer += chunk

        if self.start_time and (time.time() - self.start_time) >= settings.SPEECHBRAIN_ENROLLMENT_TIMEOUT_SECONDS:
            return self._fail(
                "timeout",
                "Enrollment timed out before a stable voice sample was captured. Please retry in a quieter setting and keep speaking continuously.",
            )

        now = time.time()
        if now - self._last_evaluation_at < self.EVALUATION_INTERVAL_SECONDS:
            return None
        self._last_evaluation_at = now

        effective_speech = self._calculate_effective_speech_duration(self.audio_buffer)
        db_level = self._safe_db_level()

        if db_level < self.MIN_DB_THRESHOLD:
            self._last_feedback = "LOW_VOLUME"
            return self._progress("Move closer to the microphone and speak a little louder.", db_level)

        if effective_speech < settings.SPEECHBRAIN_ENROLLMENT_MIN_EFFECTIVE_SPEECH_SECONDS:
            self._last_feedback = "MORE_SPEECH"
            return self._progress("Keep speaking until the system has enough clean speech to build your voice sample.", db_level)

        try:
            reference_embedding = speechbrain_service.extract_embedding(self.audio_buffer)
            stability = self._embedding_stability(reference_embedding)
        except Exception as exc:
            return self._fail("provider_error", f"SpeechBrain enrollment failed: {exc}")

        if stability < settings.SPEECHBRAIN_ENROLLMENT_STABILITY_THRESHOLD:
            self._last_feedback = "UNSTABLE_SAMPLE"
            return self._progress(
                "Keep speaking naturally for a few more seconds so the voice sample becomes more stable.",
                db_level,
                stability,
                effective_speech,
            )

        self.session.speechbrain_reference_embedding = reference_embedding
        self.session.user_embedding = reference_embedding
        self.session.enrollment_audio = self.audio_buffer
        self.session.speechbrain_profile_state = "ready"
        self.session.speaker_recognition_enabled = True
        self.session.speaker_mode = "auto"
        self.state = EnrollmentState.COMPLETE

        logger.info(
            "SpeechBrain enrollment complete [session=%s effective_speech=%.2fs db=%.2f stability=%.3f]",
            self.session.session_id,
            effective_speech,
            db_level,
            stability,
        )
        log_speaker_debug(
            "ENROLLMENT_COMPLETE",
            session_id=self.session.session_id,
            effective_speech_seconds=round(effective_speech, 3),
            db_level=round(db_level, 3),
            stability=round(stability, 3),
            speaker_mode=self.session.speaker_mode,
            speechbrain_profile_state=self.session.speechbrain_profile_state,
        )

        return {
            "type": "ENROLLMENT_COMPLETE",
            "payload": {
                "success": True,
                "message": "Voice sample ready.",
                "speaker_mode": "auto",
                "speechbrain_profile_state": self.session.speechbrain_profile_state,
                "progress": None,
                "feedback": "READY",
                "feedback_message": "SpeechBrain confirmed a stable voice sample.",
                "db_level": db_level,
                "effective_speech_duration": effective_speech,
                "stability": stability,
            },
        }

    def cleanup(self) -> None:
        speechbrain_service.cleanup_session_state(self.session)
        self.state = EnrollmentState.IDLE
        self.session.speechbrain_profile_state = "none"

    def _progress(
        self,
        message: str,
        db_level: float,
        stability: float | None = None,
        effective_speech: float | None = None,
    ) -> dict:
        return {
            "type": "ENROLLMENT_PROGRESS",
            "payload": {
                "progress": None,
                "feedback": self._last_feedback,
                "feedback_message": message,
                "db_level": db_level,
                "stability": stability,
                "effective_speech_duration": effective_speech,
            },
        }

    def _fail(self, error: str, message: str) -> dict:
        logger.warning("SpeechBrain enrollment failed [%s]: %s", self.session.session_id, message)
        log_speaker_debug(
            "ENROLLMENT_FAILED",
            session_id=self.session.session_id,
            error=error,
            message=message,
            speaker_mode=self.session.speaker_mode,
            speechbrain_profile_state=self.session.speechbrain_profile_state,
        )
        self.state = EnrollmentState.FAILED
        self.session.speechbrain_profile_state = "failed"
        speechbrain_service.cleanup_session_state(self.session)
        return {
            "type": "ENROLLMENT_FAILED",
            "payload": {
                "success": False,
                "error": error,
                "message": message,
                "can_retry": True,
                "progress": None,
                "feedback": self._last_feedback,
                "feedback_message": message,
                "db_level": self._safe_db_level(),
            },
        }

    def _safe_db_level(self) -> float:
        if not self.audio_buffer:
            return float("-inf")
        try:
            return self._calculate_db_level(self.audio_buffer)
        except Exception:
            return float("-inf")

    def _calculate_db_level(self, audio: bytes) -> float:
        if not audio:
            raise ValueError("Audio cannot be empty")
        samples = torch.frombuffer(bytearray(audio), dtype=torch.int16)
        if samples.numel() == 0:
            raise ValueError("No audio samples found")
        samples_float = samples.float() / 32768.0
        rms = torch.sqrt(torch.mean(samples_float ** 2))
        epsilon = 1e-10
        return float(20 * torch.log10(rms + epsilon).item())

    def _calculate_effective_speech_duration(self, audio: bytes) -> float:
        frame_seconds = max(0.01, settings.ENROLLMENT_SPEECH_FRAME_MS / 1000.0)
        frame_size = int(frame_seconds * self.SAMPLE_RATE) * self.BYTES_PER_SAMPLE
        if frame_size <= 0 or len(audio) < frame_size:
            return 0.0

        speech_frames = 0
        hangover_remaining = 0
        rms_threshold = max(1e-4, settings.ENROLLMENT_SPEECH_FRAME_RMS_THRESHOLD)
        hangover_frames = max(0, settings.ENROLLMENT_SPEECH_HANGOVER_FRAMES)
        for offset in range(0, len(audio) - frame_size + 1, frame_size):
            frame = audio[offset:offset + frame_size]
            samples = torch.frombuffer(bytearray(frame), dtype=torch.int16).float() / 32768.0
            rms = torch.sqrt(torch.mean(samples ** 2)).item()
            if rms >= rms_threshold:
                speech_frames += 1
                hangover_remaining = hangover_frames
            elif hangover_remaining > 0:
                speech_frames += 1
                hangover_remaining -= 1
        return speech_frames * frame_seconds

    def _embedding_stability(self, reference_embedding: torch.Tensor) -> float:
        tail_seconds = max(settings.SPEECHBRAIN_MIN_BIND_SECONDS, 3.0)
        tail_bytes = int(tail_seconds * self.SAMPLE_RATE * self.BYTES_PER_SAMPLE)
        if len(self.audio_buffer) <= tail_bytes:
            return 1.0
        tail_audio = self.audio_buffer[-tail_bytes:]
        tail_embedding = speechbrain_service.extract_embedding(tail_audio)
        return float(torch.nn.functional.cosine_similarity(reference_embedding, tail_embedding, dim=0).item())
