import pytest
from unittest.mock import AsyncMock, patch

from app.models.negotiation import NegotiationSession
from app.services.speaker_mapping_service import SpeakerMappingService


def _turn(speaker_id: str, start: float, end: float, text: str = "test") -> dict:
    return {
        "diarized_speaker_id": speaker_id,
        "start_time": start,
        "end_time": end,
        "text": text,
        "transcription_confidence": 0.95,
    }


@pytest.mark.asyncio
async def test_calibration_only_binds_user_when_speechbrain_accepts():
    session = NegotiationSession(session_id="mapping-test")
    service = SpeakerMappingService(session)
    service.begin_calibration()

    with patch.object(
        service,
        "_verify_user_candidate",
        AsyncMock(return_value={"accepted": True, "confidence": 0.88, "provider": "speechbrain"}),
    ):
        turns = await service.label_diarized_turns([_turn("spk_1", 0.0, 3.2)], b"\x00" * 120000)

    assert turns[0]["speaker"] == "user"
    assert session.speaker_mapping["spk_1"] == "user"
    assert session.speaker_mapping_state == "mapped"


@pytest.mark.asyncio
async def test_counterparty_is_promoted_only_after_user_is_mapped_and_stable():
    session = NegotiationSession(session_id="mapping-test")
    session.speaker_mapping = {"spk_1": "user"}
    session.speaker_mapping_state = "mapped"
    service = SpeakerMappingService(session)

    first = await service.label_diarized_turns([_turn("spk_2", 0.0, 1.0)], b"\x00" * 32000)
    second = await service.label_diarized_turns([_turn("spk_2", 0.0, 2.2)], b"\x00" * 70400)

    assert first[0]["speaker"] == "unknown"
    assert second[0]["speaker"] == "counterparty"
    assert session.speaker_mapping["spk_2"] == "counterparty"


@pytest.mark.asyncio
async def test_third_speaker_is_permanently_unknown():
    session = NegotiationSession(session_id="mapping-test")
    session.speaker_mapping = {"spk_1": "user", "spk_2": "counterparty"}
    session.speaker_mapping_state = "mapped"
    service = SpeakerMappingService(session)

    turns = await service.label_diarized_turns([_turn("spk_3", 0.0, 3.5)], b"\x00" * 112000)

    assert turns[0]["speaker"] == "unknown"
    assert "spk_3" in session.permanent_unknown_speaker_ids


@pytest.mark.asyncio
async def test_ambiguous_speechbrain_score_maps_to_unknown_without_degrading():
    session = NegotiationSession(session_id="mapping-test")
    session.speaker_mapping = {"spk_1": "user"}
    session.speaker_mapping_state = "mapped"
    service = SpeakerMappingService(session)

    with patch.object(
        service,
        "_verify_user_candidate",
        AsyncMock(return_value={"accepted": False, "confidence": 0.24, "provider": "speechbrain", "ambiguous": True, "strong_reject": False}),
    ):
        turns = await service.label_diarized_turns([_turn("spk_1", 0.0, 3.2)], b"\x00" * 120000)

    assert turns[0]["speaker"] == "unknown"
    assert session.speaker_mapping_state == "mapped"
    assert session.mapping_contradiction_count == 0


@pytest.mark.asyncio
async def test_ephemeral_unknown_turn_binds_user_without_persisting_unknown_mapping():
    session = NegotiationSession(session_id="mapping-test")
    service = SpeakerMappingService(session)

    with patch.object(
        service,
        "_verify_user_candidate",
        AsyncMock(return_value={"accepted": True, "confidence": 0.88, "provider": "speechbrain", "ambiguous": False, "strong_reject": False}),
    ):
        turns = await service.label_diarized_turns([_turn("unknown", 0.0, 3.2)], b"\x00" * 120000)

    assert turns[0]["speaker"] == "user"
    assert "unknown" not in session.speaker_mapping


@pytest.mark.asyncio
async def test_ephemeral_unknown_turn_strong_reject_maps_to_counterparty():
    session = NegotiationSession(session_id="mapping-test")
    session.speaker_mapping = {"spk_1": "user"}
    session.speaker_mapping_state = "mapped"
    service = SpeakerMappingService(session)

    with patch.object(
        service,
        "_verify_user_candidate",
        AsyncMock(return_value={"accepted": False, "confidence": 0.05, "provider": "speechbrain", "ambiguous": False, "strong_reject": True}),
    ):
        turns = await service.label_diarized_turns([_turn("unknown", 0.0, 3.2)], b"\x00" * 120000)

    assert turns[0]["speaker"] == "counterparty"
    assert "unknown" not in session.speaker_mapping


@pytest.mark.asyncio
async def test_two_strong_contradictions_within_window_degrade_mapping():
    session = NegotiationSession(session_id="mapping-test")
    session.speaker_mapping = {"spk_1": "user"}
    session.speaker_mapping_state = "mapped"
    service = SpeakerMappingService(session)

    with patch.object(
        service,
        "_verify_user_candidate",
        AsyncMock(return_value={"accepted": False, "confidence": 0.05, "provider": "speechbrain", "ambiguous": False, "strong_reject": True}),
    ):
        first = await service.label_diarized_turns([_turn("spk_1", 0.0, 3.2)], b"\x00" * 120000)
        second = await service.label_diarized_turns([_turn("spk_1", 0.0, 3.4)], b"\x00" * 120000)

    assert first[0]["speaker"] == "unknown"
    assert second[0]["speaker"] == "unknown"
    assert session.speaker_mapping_state == "degraded"


@pytest.mark.asyncio
async def test_degraded_mapping_requires_successful_revalidation():
    session = NegotiationSession(session_id="mapping-test")
    session.speaker_mapping = {"spk_1": "user"}
    session.speaker_mapping_state = "degraded"
    service = SpeakerMappingService(session)

    with patch.object(
        service,
        "_verify_user_candidate",
        AsyncMock(return_value={"accepted": True, "confidence": 0.92, "provider": "speechbrain"}),
    ):
        turns = await service.label_diarized_turns([_turn("spk_1", 0.0, 3.1)], b"\x00" * 120000)

    assert turns[0]["speaker"] == "user"
    assert session.speaker_mapping_state == "mapped"
