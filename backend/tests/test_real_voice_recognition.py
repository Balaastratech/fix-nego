"""
Real Voice Recognition Tests (pyttsx3 / Windows SAPI5)

Tests the full enrollment → classification pipeline with Windows TTS voices
that produce distinguishable SpeechBrain ECAPA-TDNN embeddings:
  - David (male)  → enrolled as the user
  - Zira  (female) → must NOT be classified as "user"

Skip conditions:
  - pyttsx3 not installed
  - SPEECHBRAIN_ENABLED=False in settings
  - SpeechBrain model fails to load

Accuracy target:
  - user turns recognised as "user" ≥ 80 % of the time
  - NO Zira turn is ever labelled "user" (safety-critical: 0 false-user claims)
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf
import torch

from app.config import settings
from app.models.negotiation import NegotiationSession, NegotiationState
from app.services.speaker_service import SpeakerService
from app.services.speaker_enrollment import ENROLLMENT_SCRIPT


# ---------------------------------------------------------------------------
# Availability guards
# ---------------------------------------------------------------------------

def _pyttsx3_available() -> bool:
    try:
        import pyttsx3  # noqa: F401
        return True
    except ImportError:
        return False


def _speechbrain_ready() -> bool:
    if not settings.SPEECHBRAIN_ENABLED:
        return False
    try:
        from app.services.speechbrain_service import speechbrain_service
        ok, _ = speechbrain_service.probe_capability()
        return ok
    except Exception:
        return False


pytestmark = [
    pytest.mark.skipif(not _pyttsx3_available(), reason="pyttsx3 not installed (pip install pyttsx3)"),
    pytest.mark.skipif(not _speechbrain_ready(), reason="SpeechBrain disabled or model unavailable"),
]

SAMPLE_RATE = 16000


# ---------------------------------------------------------------------------
# TTS helper
# ---------------------------------------------------------------------------

def _find_voice_id(engine: Any, name_fragment: str) -> str | None:
    for voice in engine.getProperty("voices"):
        if name_fragment.lower() in voice.name.lower():
            return voice.id
    return None


def synth_pcm(text: str, sapi_name: str, rate_delta: int = 0) -> bytes:
    """Synthesise *text* with the named SAPI5 voice; return 16 kHz mono PCM bytes."""
    import pyttsx3
    import torchaudio

    engine = pyttsx3.init()
    voice_id = _find_voice_id(engine, sapi_name)
    if voice_id is None:
        available = [v.name for v in engine.getProperty("voices")]
        pytest.skip(f"SAPI5 voice '{sapi_name}' not found. Available: {available}")

    engine.setProperty("voice", voice_id)
    base_rate = int(engine.getProperty("rate"))
    engine.setProperty("rate", max(50, base_rate + rate_delta))

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        engine.save_to_file(text, str(tmp_path))
        engine.runAndWait()

        waveform, sr = torchaudio.load(str(tmp_path))
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)
        if sr != SAMPLE_RATE:
            waveform = torchaudio.functional.resample(waveform, sr, SAMPLE_RATE)
        waveform = waveform.clamp(-1.0, 1.0)
        return (waveform.squeeze(0) * 32767.0).to(torch.int16).numpy().tobytes()
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Enrollment helper
# ---------------------------------------------------------------------------

# Use the production enrollment script (3 sentences, ~10s) so the embedding
# is stable enough for ECAPA-TDNN to achieve high cosine similarity.
ENROLLMENT_TEXT = ENROLLMENT_SCRIPT

TEST_PHRASES = [
    "I can do eighty two with net sixty and no auto renewal.",
    "That price is too high for fifty units.",
    "Can we agree on delivery terms today?",
    "Let me check my budget before accepting.",
    "I need a firm commitment on the warranty.",
]

COUNTERPARTY_PHRASES = [
    "At eighty four we keep delivery included.",
    "That is the best I can do right now.",
    "Warranty is standard — no changes.",
    "We can review sixty one if terms stay.",
    "I need approval from my manager first.",
]


def _active_rv_session(session_id: str) -> NegotiationSession:
    session = NegotiationSession(session_id=session_id)
    session.state = NegotiationState.ACTIVE
    return session


def _enroll_session(session: NegotiationSession, sapi_name: str) -> None:
    from app.services.speechbrain_service import speechbrain_service

    audio = synth_pcm(ENROLLMENT_TEXT, sapi_name)
    session.user_embedding = speechbrain_service.extract_embedding(audio)
    session.speaker_recognition_enabled = True
    session.speaker_mode = "auto"
    session.state = NegotiationState.ACTIVE


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRealVoiceRecognition:
    """End-to-end voice recognition tests with Windows SAPI5 voices."""

    @pytest.mark.asyncio
    async def test_user_voice_recognised(self):
        """David (enrolled) must be classified as 'user'."""
        session = _active_rv_session("rv-user-recognised")
        _enroll_session(session, "David")
        service = SpeakerService(session)

        audio = synth_pcm(TEST_PHRASES[0], "David")
        label = await service._classify_segment(audio)

        assert label == "user", (
            f"Enrolled David voice should be classified as 'user', got '{label}'. "
            f"Check USER_VERIFY_THRESHOLD ({settings.USER_VERIFY_THRESHOLD}) — "
            f"last confidence: {service.get_confidence_score():.3f}"
        )

    @pytest.mark.asyncio
    async def test_counterparty_not_labelled_user(self):
        """Zira must NEVER be classified as 'user' when David is enrolled."""
        session = _active_rv_session("rv-cp-not-user")
        _enroll_session(session, "David")
        service = SpeakerService(session)

        audio = synth_pcm(COUNTERPARTY_PHRASES[0], "Zira")
        label = await service._classify_segment(audio)

        assert label != "user", (
            f"Zira must not be classified as 'user' (false-user claim). Got '{label}'. "
            f"Confidence={service.get_confidence_score():.3f}"
        )

    @pytest.mark.asyncio
    async def test_silence_is_unknown(self):
        """Pure silence must return 'unknown' (too short or no speech)."""
        session = _active_rv_session("rv-silence")
        _enroll_session(session, "David")
        service = SpeakerService(session)

        silence = np.zeros(int(0.4 * SAMPLE_RATE), dtype=np.int16).tobytes()
        label = await service._classify_segment(silence)

        assert label == "unknown", f"Silence should be 'unknown', got '{label}'"

    @pytest.mark.asyncio
    async def test_no_enrollment_returns_unknown(self):
        """Without enrollment, every segment is 'unknown'."""
        session = _active_rv_session("rv-no-enroll")
        service = SpeakerService(session)

        audio = synth_pcm(TEST_PHRASES[0], "David")
        label = await service._classify_segment(audio)
        assert label == "unknown"

    @pytest.mark.asyncio
    async def test_accuracy_over_multiple_turns(self):
        """
        Enroll David; alternate David/Zira turns.

        Requirements:
          - David turns recognised as 'user' ≥ 80 % (realistic TTS target)
          - Zira turns NEVER classified as 'user' (zero false-user claims)
        """
        session = _active_rv_session("rv-accuracy")
        _enroll_session(session, "David")
        service = SpeakerService(session)

        user_correct = 0
        user_total = len(TEST_PHRASES)
        false_user_claims = 0
        counterparty_total = len(COUNTERPARTY_PHRASES)

        for phrase in TEST_PHRASES:
            audio = synth_pcm(phrase, "David")
            label = await service._classify_segment(audio)
            if label == "user":
                user_correct += 1

        for phrase in COUNTERPARTY_PHRASES:
            audio = synth_pcm(phrase, "Zira")
            label = await service._classify_segment(audio)
            if label == "user":
                false_user_claims += 1

        user_accuracy = user_correct / user_total
        print(
            f"\n[RealVoiceRecognition] "
            f"User accuracy: {user_accuracy:.0%} ({user_correct}/{user_total}), "
            f"False-user claims: {false_user_claims}/{counterparty_total}"
        )

        # Zero false-user claims is a hard requirement
        assert false_user_claims == 0, (
            f"{false_user_claims} Zira turn(s) were incorrectly labelled 'user'. "
            f"Check USER_VERIFY_THRESHOLD={settings.USER_VERIFY_THRESHOLD}"
        )

        # User accuracy ≥ 80 % is a soft quality gate
        assert user_accuracy >= 0.80, (
            f"User recognition accuracy {user_accuracy:.0%} < 80 %. "
            f"Consider lowering USER_VERIFY_THRESHOLD (currently {settings.USER_VERIFY_THRESHOLD}) "
            f"or using longer enrollment audio."
        )

    @pytest.mark.asyncio
    async def test_speaker_label_reported_in_session_history(self):
        """Every non-unknown classification is recorded in speaker_confidence_history."""
        session = _active_rv_session("rv-history")
        _enroll_session(session, "David")
        service = SpeakerService(session)

        for phrase in TEST_PHRASES[:3]:
            audio = synth_pcm(phrase, "David")
            await service._classify_segment(audio)

        assert len(session.speaker_confidence_history) >= 1
        for entry in session.speaker_confidence_history:
            assert entry["speaker"] in {"user", "counterparty", "unknown"}
            assert "confidence" in entry
            assert "timestamp" in entry

    @pytest.mark.asyncio
    async def test_counterparty_eventually_labelled(self):
        """
        After several Zira turns the system should label at least one as
        'counterparty' (not just 'unknown').  This validates the counterparty
        cluster promotion logic.
        """
        session = _active_rv_session("rv-cp-label")
        _enroll_session(session, "David")
        # Seed the session with a confirmed 'user' classification so
        # _promote_or_match_counterparty's guard passes.
        session.speaker_confidence_history.append({
            "speaker": "user",
            "timestamp": 0.0,
            "confidence": 0.92,
            "duration_ms": 2000,
        })
        service = SpeakerService(session)

        labels = []
        for phrase in COUNTERPARTY_PHRASES:
            audio = synth_pcm(phrase, "Zira")
            label = await service.classify_utterance(
                audio,
                duration_ms=int(len(audio) / 2 / 16000 * 1000),
                transcription_confidence=0.95,
                utterance_id=f"test-{phrase[:10]}",
            )
            labels.append(label[0])

        assert "counterparty" in labels, (
            f"Expected at least one Zira turn to be labelled 'counterparty'. "
            f"Got labels: {labels}. "
            f"COUNTERPARTY_REJECT_THRESHOLD={settings.COUNTERPARTY_REJECT_THRESHOLD}"
        )
