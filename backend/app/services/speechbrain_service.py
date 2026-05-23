from __future__ import annotations

import gc
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SpeechBrainVerificationResult:
    accepted: bool
    confidence: float | None
    reason: str
    provider: str = "speechbrain"
    ambiguous: bool = False
    strong_reject: bool = False


class SpeechBrainService:
    MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
    SAMPLE_RATE = 16000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._verifier: Any | None = None
        self._loaded_at: float | None = None

    @property
    def enabled(self) -> bool:
        return bool(settings.SPEECHBRAIN_ENABLED)

    def _device(self) -> str:
        return settings.SPEECHBRAIN_DEVICE or "cpu"

    def _ensure_loaded(self) -> Any:
        with self._lock:
            if self._verifier is None:
                from speechbrain.inference.speaker import SpeakerRecognition
                started = time.perf_counter()
                self._verifier = SpeakerRecognition.from_hparams(
                    source=self.MODEL_SOURCE,
                    savedir="pretrained_models/speechbrain-spkrec-ecapa-voxceleb",
                    run_opts={"device": self._device()},
                )
                self._loaded_at = time.time()
                logger.info(
                    "SpeechBrain verifier loaded",
                    extra={
                        "speechbrain_device": self._device(),
                        "model_source": self.MODEL_SOURCE,
                        "load_seconds": round(time.perf_counter() - started, 3),
                    },
                )
            return self._verifier

    def probe_capability(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "speechbrain_disabled"
        try:
            started = time.perf_counter()
            # Lightweight import check to verify system capability without loading model weights
            from speechbrain.inference.speaker import SpeakerRecognition
            return True, f"ok:{time.perf_counter() - started:.3f}s"
        except Exception as exc:
            return False, str(exc)

    def extract_embedding(self, pcm: bytes) -> Any:
        import torch
        verifier = self._ensure_loaded()
        waveform = self._pcm_to_waveform_tensor(pcm)
        if waveform.numel() == 0:
            raise ValueError("empty_audio")
        with torch.no_grad():
            embedding = verifier.encode_batch(waveform)
        return self._normalize_embedding(embedding)

    def verify_against_embedding(self, reference_embedding: Any, pcm: bytes) -> SpeechBrainVerificationResult:
        import torch
        if reference_embedding is None:
            return SpeechBrainVerificationResult(False, None, "missing_reference")

        waveform = self._pcm_to_waveform_tensor(pcm)
        if waveform.numel() == 0:
            return SpeechBrainVerificationResult(False, None, "empty_audio")

        with torch.no_grad():
            candidate_embedding = self._ensure_loaded().encode_batch(waveform)
        candidate_embedding = self._normalize_embedding(candidate_embedding)
        reference_embedding = self._normalize_embedding(reference_embedding)
        confidence = float(torch.nn.functional.cosine_similarity(reference_embedding, candidate_embedding, dim=0).item())
        confidence = max(0.0, min(1.0, confidence))

        ambiguous = settings.SPEECHBRAIN_AMBIGUOUS_LOW <= confidence <= settings.SPEECHBRAIN_AMBIGUOUS_HIGH
        strong_reject = confidence < settings.SPEECHBRAIN_AMBIGUOUS_LOW
        accepted = confidence >= settings.SPEECHBRAIN_ACCEPT_THRESHOLD

        if accepted:
            reason = "accepted"
        elif ambiguous:
            reason = "ambiguous"
        elif strong_reject:
            reason = "strong_reject"
        else:
            reason = "rejected"

        return SpeechBrainVerificationResult(
            accepted=accepted,
            confidence=confidence,
            reason=reason,
            ambiguous=ambiguous,
            strong_reject=strong_reject,
        )

    def cleanup_session_state(self, session: Any) -> None:
        import torch
        session.speechbrain_reference_embedding = None
        session.speechbrain_last_result = None
        session.user_embedding = None
        gc.collect()
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass

    def _pcm_to_waveform_tensor(self, pcm: bytes) -> Any:
        import torch
        samples = torch.frombuffer(bytearray(pcm), dtype=torch.int16)
        if samples.numel() == 0:
            return torch.zeros((1, 0), dtype=torch.float32)
        waveform = (samples.float() / 32768.0).unsqueeze(0)
        return waveform

    def load_audio_file(self, path: str) -> bytes:
        import torch
        import torchaudio
        waveform, sample_rate = torchaudio.load(path)
        if waveform.ndim > 1 and waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)
        if sample_rate != self.SAMPLE_RATE:
            waveform = torchaudio.functional.resample(waveform, sample_rate, self.SAMPLE_RATE)
        waveform = waveform.clamp(-1.0, 1.0)
        pcm = (waveform.squeeze(0) * 32767.0).to(torch.int16).contiguous()
        return pcm.numpy().tobytes()

    @staticmethod
    def _normalize_embedding(embedding: Any) -> Any:
        import torch
        if isinstance(embedding, torch.Tensor):
            tensor = embedding.detach().cpu().float().reshape(-1)
        else:
            tensor = torch.tensor(embedding, dtype=torch.float32).reshape(-1)
        norm = torch.linalg.norm(tensor)
        if float(norm.item()) == 0.0:
            return tensor
        return tensor / norm


speechbrain_service = SpeechBrainService()
