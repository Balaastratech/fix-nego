import pytest
import numpy as np
import torch
from unittest.mock import patch

from app.models.negotiation import NegotiationSession
from app.services.speaker_enrollment import SpeakerEnrollmentService, EnrollmentState


def generate_pcm_audio(duration_s: float, volume: float = 0.5) -> bytes:
    sample_rate = 16000
    num_samples = int(duration_s * sample_rate)
    t = np.linspace(0, duration_s, num_samples, endpoint=False)
    samples = (volume * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16)
    return samples.tobytes()


@pytest.mark.asyncio
async def test_speechbrain_enrollment_starts_when_enabled():
    session = NegotiationSession(session_id="test-session")
    service = SpeakerEnrollmentService(session)

    with patch("app.services.speaker_enrollment.settings.SPEECHBRAIN_ENABLED", True), \
         patch("app.services.speaker_enrollment.speechbrain_service.probe_capability", return_value=(True, "ok")):
        started = await service.start_enrollment()

    assert started["type"] == "ENROLLMENT_STARTED"
    assert service.state == EnrollmentState.CAPTURING
    assert session.speechbrain_profile_state == "enrolling"


@pytest.mark.asyncio
async def test_speechbrain_enrollment_fails_cleanly_when_disabled():
    session = NegotiationSession(session_id="test-session")
    service = SpeakerEnrollmentService(session)

    with patch("app.services.speaker_enrollment.settings.SPEECHBRAIN_ENABLED", False):
        result = await service.start_enrollment()

    assert result["type"] == "ENROLLMENT_FAILED"
    assert result["payload"]["error"] == "provider_disabled"


@pytest.mark.asyncio
async def test_speechbrain_enrollment_timeout_marks_failed():
    session = NegotiationSession(session_id="test-session")
    service = SpeakerEnrollmentService(session)

    with patch("app.services.speaker_enrollment.settings.SPEECHBRAIN_ENABLED", True), \
         patch("app.services.speaker_enrollment.settings.SPEECHBRAIN_ENROLLMENT_TIMEOUT_SECONDS", 0.0), \
         patch("app.services.speaker_enrollment.speechbrain_service.probe_capability", return_value=(True, "ok")), \
         patch("app.services.speaker_enrollment.speechbrain_service.cleanup_session_state") as mock_cleanup:
        await service.start_enrollment()
        result = await service.process_audio(generate_pcm_audio(1.0, volume=0.7))

    assert result["type"] == "ENROLLMENT_FAILED"
    assert session.speechbrain_profile_state == "failed"
    mock_cleanup.assert_called()


@pytest.mark.asyncio
async def test_speechbrain_enrollment_completes_after_stable_embedding():
    session = NegotiationSession(session_id="test-session")
    service = SpeakerEnrollmentService(session)
    embedding = torch.tensor([1.0, 0.0, 0.0], dtype=torch.float32)

    with patch("app.services.speaker_enrollment.settings.SPEECHBRAIN_ENABLED", True), \
         patch("app.services.speaker_enrollment.settings.SPEECHBRAIN_ENROLLMENT_MIN_EFFECTIVE_SPEECH_SECONDS", 1.0), \
         patch("app.services.speaker_enrollment.settings.SPEECHBRAIN_ENROLLMENT_STABILITY_THRESHOLD", 0.5), \
         patch("app.services.speaker_enrollment.speechbrain_service.probe_capability", return_value=(True, "ok")), \
         patch("app.services.speaker_enrollment.speechbrain_service.extract_embedding", return_value=embedding):
        await service.start_enrollment()
        result = await service.process_audio(generate_pcm_audio(2.5, volume=0.9))

    assert result["type"] == "ENROLLMENT_COMPLETE"
    assert session.speechbrain_profile_state == "ready"
    assert session.speechbrain_reference_embedding is embedding
    assert session.user_embedding is embedding


def test_enrollment_cleanup_releases_session_state():
    session = NegotiationSession(session_id="test-session")
    service = SpeakerEnrollmentService(session)
    session.speechbrain_reference_embedding = torch.tensor([1.0])
    session.user_embedding = torch.tensor([1.0])

    with patch("app.services.speaker_enrollment.speechbrain_service.cleanup_session_state") as mock_cleanup:
        service.cleanup()

    mock_cleanup.assert_called_once_with(session)
    assert session.speechbrain_profile_state == "none"
