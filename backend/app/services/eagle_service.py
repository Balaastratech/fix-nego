from __future__ import annotations

import importlib
import logging
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class EagleVerificationResult:
    accepted: bool
    confidence: float | None
    profile_id: str | None
    reason: str
    provider: str = "eagle"
    ambiguous: bool = False
    strong_reject: bool = False


class PicovoiceEagleService:
    def __init__(self) -> None:
        self._module: Any | None = None

    @property
    def enabled(self) -> bool:
        return bool(settings.PICOVOICE_EAGLE_ENABLED and settings.PICOVOICE_ACCESS_KEY)

    def _load_module(self) -> Any:
        if self._module is None:
            self._module = importlib.import_module("pveagle")
        return self._module

    def _call_release(self, obj: Any | None) -> None:
        if obj is None:
            return
        for name in ("delete", "release"):
            method = getattr(obj, name, None)
            if callable(method):
                method()
                return

    def probe_capability(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "eagle_credentials_missing"
        try:
            profiler = self.create_profiler()
            self.release_profiler(profiler)
            return True, "ok"
        except Exception as exc:
            return False, str(exc)

    def create_profiler(self) -> Any:
        module = self._load_module()
        create = getattr(module, "create_profiler", None)
        if callable(create):
            return create(access_key=settings.PICOVOICE_ACCESS_KEY)
        profiler_cls = getattr(module, "EagleProfiler", None)
        if profiler_cls is not None:
            try:
                return profiler_cls(access_key=settings.PICOVOICE_ACCESS_KEY)
            except TypeError:
                return profiler_cls(settings.PICOVOICE_ACCESS_KEY)
        raise RuntimeError("Unsupported pveagle profiler API")

    def create_recognizer(self, speaker_profiles: list[bytes] | bytes) -> Any:
        module = self._load_module()
        create = getattr(module, "create_recognizer", None)
        if callable(create):
            return create(
                access_key=settings.PICOVOICE_ACCESS_KEY,
                speaker_profiles=speaker_profiles,
            )
        eagle_cls = getattr(module, "Eagle", None)
        if eagle_cls is not None:
            try:
                return eagle_cls(
                    access_key=settings.PICOVOICE_ACCESS_KEY,
                    speaker_profiles=speaker_profiles,
                )
            except TypeError:
                return eagle_cls(settings.PICOVOICE_ACCESS_KEY, speaker_profiles)
        raise RuntimeError("Unsupported pveagle recognizer API")

    def release_profiler(self, profiler: Any | None) -> None:
        self._call_release(profiler)

    def release_recognizer(self, recognizer: Any | None) -> None:
        self._call_release(recognizer)

    def sample_rate(self, obj: Any) -> int:
        for name in ("sample_rate", "sampleRate"):
            value = getattr(obj, name, None)
            if isinstance(value, int):
                return value
            if callable(value):
                result = value()
                if isinstance(result, int):
                    return result
        return 16000

    def frame_length(self, recognizer: Any) -> int:
        for name in ("frame_length", "frameLength"):
            value = getattr(recognizer, name, None)
            if isinstance(value, int):
                return value
            if callable(value):
                result = value()
                if isinstance(result, int):
                    return result
        return 512

    def min_enroll_samples(self, profiler: Any) -> int:
        for name in ("min_enroll_samples", "minEnrollSamples"):
            value = getattr(profiler, name, None)
            if isinstance(value, int):
                return value
            if callable(value):
                result = value()
                if isinstance(result, int):
                    return result
        return 16000

    def enroll(self, profiler: Any, pcm: bytes) -> dict[str, Any]:
        samples = np.frombuffer(pcm, dtype=np.int16)
        result = profiler.enroll(samples)
        percentage = getattr(result, "percentage", None)
        feedback = getattr(result, "feedback", None)
        if percentage is None and isinstance(result, dict):
            percentage = result.get("percentage")
            feedback = result.get("feedback")
        return {
            "percentage": float(percentage or 0.0),
            "feedback": str(feedback or "NONE"),
        }

    def export_profile(self, profiler: Any) -> bytes:
        exported = profiler.export()
        if isinstance(exported, bytes):
            return exported
        if isinstance(exported, bytearray):
            return bytes(exported)
        if hasattr(exported, "tobytes"):
            return exported.tobytes()
        return bytes(exported)

    def verify_profile(self, recognizer: Any, pcm: bytes) -> EagleVerificationResult:
        samples = np.frombuffer(pcm, dtype=np.int16)
        if len(samples) == 0:
            return EagleVerificationResult(
                accepted=False,
                confidence=None,
                profile_id=None,
                reason="empty_audio",
            )

        frame_length = max(1, self.frame_length(recognizer))
        scores: list[float] = []
        for offset in range(0, len(samples) - frame_length + 1, frame_length):
            frame = samples[offset:offset + frame_length]
            result = recognizer.process(frame)
            score = self._extract_score(result)
            if score is not None:
                scores.append(score)

        if not scores:
            return EagleVerificationResult(
                accepted=False,
                confidence=None,
                profile_id=None,
                reason="no_scores",
            )

        confidence = float(max(scores))
        ambiguous = (
            settings.PICOVOICE_EAGLE_AMBIGUOUS_LOW
            < confidence
            <= settings.PICOVOICE_EAGLE_AMBIGUOUS_HIGH
        )
        accepted = confidence >= settings.PICOVOICE_EAGLE_ACCEPT_THRESHOLD
        strong_reject = confidence <= settings.PICOVOICE_EAGLE_AMBIGUOUS_LOW

        if accepted:
            reason = "accepted"
        elif ambiguous:
            reason = "ambiguous"
        elif strong_reject:
            reason = "strong_reject"
        else:
            reason = "rejected"

        return EagleVerificationResult(
            accepted=accepted,
            confidence=confidence,
            profile_id="session-profile",
            reason=reason,
            ambiguous=ambiguous,
            strong_reject=strong_reject,
        )

    @staticmethod
    def _extract_score(result: Any) -> float | None:
        if result is None:
            return None
        if isinstance(result, (int, float)):
            return float(result)
        if isinstance(result, (list, tuple)):
            if not result:
                return None
            first = result[0]
            if isinstance(first, (int, float)):
                return float(first)
        if isinstance(result, dict):
            for key in ("scores", "score", "similarity", "similarities"):
                value = result.get(key)
                if isinstance(value, (int, float)):
                    return float(value)
                if isinstance(value, (list, tuple)) and value:
                    first = value[0]
                    if isinstance(first, (int, float)):
                        return float(first)
        for key in ("scores", "score", "similarity", "similarities"):
            value = getattr(result, key, None)
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, (list, tuple)) and value:
                first = value[0]
                if isinstance(first, (int, float)):
                    return float(first)
        return None


eagle_service = PicovoiceEagleService()
