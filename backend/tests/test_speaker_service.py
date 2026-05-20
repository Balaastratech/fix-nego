"""
Unit Tests for Speaker Service

Tests the SpeakerService classification logic.

Enrollment embeddings are created with SpeechBrain (the same model used in
production) when SPEECHBRAIN_ENABLED=True.  Tests that only exercise control
flow (override, VAD buffering) use synthetic torch tensors directly so they
run without loading the 100 MB SpeechBrain model.
"""

import pytest
import numpy as np
import asyncio
import time
import torch

from app.models.negotiation import NegotiationSession, NegotiationState
from app.services.speaker_service import SpeakerService
from app.config import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_pcm_audio(duration_s: float, frequency_hz: int = 440, volume: float = 0.5) -> bytes:
    sample_rate = 16000
    num_samples = int(duration_s * sample_rate)
    t = np.linspace(0, duration_s, num_samples)
    samples = (volume * np.sin(2 * np.pi * frequency_hz * t) * 32767).astype(np.int16)
    return samples.tobytes()


def generate_speech_audio(duration_s: float) -> bytes:
    return generate_pcm_audio(duration_s, frequency_hz=200, volume=0.7)


def generate_silence_audio(duration_s: float) -> bytes:
    return generate_pcm_audio(duration_s, frequency_hz=0, volume=0.0)


def _unit_tensor(dim: int = 192) -> torch.Tensor:
    """Return a random L2-normalised tensor of the SpeechBrain ECAPA-TDNN dimension."""
    v = torch.rand(dim)
    return v / v.norm()


def _active_session(session_id: str) -> NegotiationSession:
    """Create a NegotiationSession in ACTIVE state (required for classification to run)."""
    session = NegotiationSession(session_id=session_id)
    session.state = NegotiationState.ACTIVE
    return session


# ---------------------------------------------------------------------------
# Tests that need a real SpeechBrain embedding (skip when model unavailable)
# ---------------------------------------------------------------------------

def _speechbrain_available() -> bool:
    if not settings.SPEECHBRAIN_ENABLED:
        return False
    try:
        from app.services.speechbrain_service import speechbrain_service
        ok, _ = speechbrain_service.probe_capability()
        return ok
    except Exception:
        return False


@pytest.mark.asyncio
@pytest.mark.skipif(not _speechbrain_available(), reason="SpeechBrain not available")
async def test_classification_with_speechbrain_enrollment():
    """Classification returns a valid label when enrollment uses SpeechBrain."""
    from app.services.speechbrain_service import speechbrain_service

    session = _active_session("test-sb-enroll")
    enrollment_audio = generate_speech_audio(5.0)
    session.user_embedding = speechbrain_service.extract_embedding(enrollment_audio)

    service = SpeakerService(session)
    segment_audio = generate_speech_audio(1.0)
    label = await service._classify_segment(segment_audio)

    assert label in {"user", "counterparty", "unknown"}, f"Unexpected label: {label}"
    assert session.current_speaker == label
    assert session.speaker_last_updated > 0 or label == "unknown"
    assert len(session.speaker_confidence_history) > 0


# ---------------------------------------------------------------------------
# Tests that use synthetic tensors (no model load required)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_classification_without_enrollment():
    """When no enrollment exists, result must be 'unknown'."""
    session = _active_session("test-no-enroll")
    session.user_embedding = None

    service = SpeakerService(session)
    label = await service._classify_segment(generate_speech_audio(1.0))
    assert label == "unknown", f"Without enrollment expected 'unknown', got '{label}'"


@pytest.mark.asyncio
async def test_minimum_segment_duration_filter():
    """Segments below the minimum duration must be rejected as 'unknown'."""
    session = _active_session("test-min-dur")
    session.user_embedding = _unit_tensor()

    service = SpeakerService(session)
    short_audio = generate_speech_audio(0.3)  # < 0.5 s threshold
    label = await service._classify_segment(short_audio)
    assert label == "unknown", f"Short segment should be 'unknown', got '{label}'"


@pytest.mark.asyncio
async def test_manual_override_precedence():
    """Manual override must take precedence over automatic classification."""
    session = _active_session("test-override")
    session.user_embedding = _unit_tensor()
    session.current_speaker = "counterparty"
    session.manual_override_until = time.time() + 3600

    service = SpeakerService(session)
    label = await service._classify_segment(generate_speech_audio(1.0))
    assert label == "counterparty", f"Manual override should yield 'counterparty', got '{label}'"


@pytest.mark.asyncio
async def test_manual_mode_infinite_override():
    """Infinite manual mode must honour the current label."""
    session = _active_session("test-manual-mode")
    session.user_embedding = _unit_tensor()
    session.current_speaker = "user"
    session.manual_override_until = float("inf")

    service = SpeakerService(session)
    label = await service._classify_segment(generate_speech_audio(1.0))
    assert label == "user", f"Manual mode should yield 'user', got '{label}'"


@pytest.mark.asyncio
async def test_vad_frame_buffering():
    """Audio is buffered until complete 30 ms frames are available."""
    session = _active_session("test-buffering")
    service = SpeakerService(session)

    audio_chunk = generate_speech_audio(0.05)  # ~1 600 bytes
    await service.feed_audio(audio_chunk)

    expected_remainder = len(audio_chunk) % 960
    assert len(service.frame_buffer) == expected_remainder, (
        f"Expected {expected_remainder} bytes in frame buffer, got {len(service.frame_buffer)}"
    )


@pytest.mark.asyncio
async def test_speech_segment_detection():
    """Service processes silence→speech→silence without crashing."""
    session = _active_session("test-segment-detect")
    session.user_embedding = _unit_tensor()

    service = SpeakerService(session)
    await service.feed_audio(generate_silence_audio(0.2))
    await service.feed_audio(generate_speech_audio(1.0))
    await service.feed_audio(generate_silence_audio(0.2))
    await asyncio.sleep(0.3)

    if session.speaker_confidence_history:
        assert session.speaker_confidence_history[0]["speaker"] in {"user", "counterparty", "unknown"}


@pytest.mark.asyncio
async def test_get_current_speaker():
    session = _active_session("test-get-speaker")
    session.current_speaker = "user"
    assert SpeakerService(session).get_current_speaker() == "user"


@pytest.mark.asyncio
async def test_get_confidence_score_initial():
    session = _active_session("test-get-conf")
    assert SpeakerService(session).get_confidence_score() == 0.0


@pytest.mark.asyncio
async def test_error_handling_graceful_degradation():
    """Corrupt embedding must not raise — return 'unknown' instead."""
    session = _active_session("test-error")
    session.user_embedding = "not-a-tensor"  # deliberately invalid

    service = SpeakerService(session)
    label = await service._classify_segment(generate_speech_audio(1.0))
    assert label == "unknown", f"On error expected 'unknown', got '{label}'"


@pytest.mark.asyncio
async def test_vad_aggressiveness_configuration():
    session = _active_session("test-vad-config")
    service = SpeakerService(session)
    assert service.vad is not None
    assert service.FRAME_SIZE == 960


@pytest.mark.asyncio
async def test_session_state_updates_with_synthetic_embedding():
    """Session state is updated correctly after a classification round."""
    session = _active_session("test-state-update")
    # Give the session a known user embedding (unit vector)
    session.user_embedding = _unit_tensor()

    service = SpeakerService(session)
    segment_audio = generate_speech_audio(1.0)
    label = await service._classify_segment(segment_audio)

    # State update only happens for non-unknown labels
    if label != "unknown":
        assert session.current_speaker == label
        assert session.speaker_last_updated > 0
        assert len(session.speaker_timeline) >= 1

    assert len(session.speaker_confidence_history) >= 1
    entry = session.speaker_confidence_history[0]
    assert entry["speaker"] in {"user", "counterparty", "unknown"}
    assert "confidence" in entry
    assert "timestamp" in entry
