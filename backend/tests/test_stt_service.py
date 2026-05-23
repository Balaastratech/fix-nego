from unittest.mock import patch

from app.models.negotiation import NegotiationSession
from app.services.stt_service import SpeechTranscriptionService


def test_resolve_language_codes_falls_back_to_auto_for_large_chirp3_locale_sets():
    service = SpeechTranscriptionService(NegotiationSession(session_id="stt-test"))

    with patch("app.services.stt_service.settings") as mock_settings:
        mock_settings.GOOGLE_STT_MODEL = "chirp_3"
        mock_settings.google_stt_language_codes_list = ["en-US", "hi-IN", "es-US"]

        assert service._resolve_language_codes(None) == ["auto"]


def test_resolve_language_codes_prefers_session_language_hint_when_supported():
    service = SpeechTranscriptionService(NegotiationSession(session_id="stt-test"))

    with patch("app.services.stt_service.settings") as mock_settings:
        mock_settings.GOOGLE_STT_MODEL = "chirp_3"
        mock_settings.google_stt_language_codes_list = ["en-US", "hi-IN", "es-US"]

        assert service._resolve_language_codes("hi-IN") == ["hi-IN"]


def test_resolve_language_codes_prefers_response_language_hint_before_auto_fallback():
    service = SpeechTranscriptionService(NegotiationSession(session_id="stt-test"))

    with patch("app.services.stt_service.settings") as mock_settings:
        mock_settings.GOOGLE_STT_MODEL = "chirp_3"
        mock_settings.google_stt_language_codes_list = ["en-US", "hi-IN", "es-US"]

        assert service._resolve_language_codes(None, "en-US") == ["en-US"]


def test_resolve_adaptation_phrases_includes_session_item_and_deduplicates():
    session = NegotiationSession(
        session_id="stt-test",
        context="User wants to sell iPhone 15 Pro Max for 800 dollars.",
        user_context={"item": "iPhone 15 Pro Max"},
    )
    service = SpeechTranscriptionService(session)

    with patch("app.services.stt_service.settings") as mock_settings:
        mock_settings.google_stt_hint_phrases_list = ["iphone", "sell", "offer"]

        phrases = service._resolve_adaptation_phrases()

    assert "iPhone 15 Pro Max" in phrases
    assert "iphone" in phrases
    assert phrases.count("iPhone 15 Pro Max") == 1


def test_resolve_deepgram_language_prefers_supported_hint_and_normalizes_codes():
    service = SpeechTranscriptionService(NegotiationSession(session_id="stt-test"))

    with patch("app.services.stt_service.settings") as mock_settings:
        mock_settings.TRANSCRIPTION_PROVIDER = "deepgram"
        mock_settings.deepgram_language_codes_list = ["en-US", "hi-IN", "es-US"]

        assert service._resolve_deepgram_language("hi-IN") == "hi"
        assert service._resolve_deepgram_language(None, "es-US") == "es"


def test_resolve_deepgram_language_falls_back_to_multi_for_multiple_configured_languages():
    service = SpeechTranscriptionService(NegotiationSession(session_id="stt-test"))

    with patch("app.services.stt_service.settings") as mock_settings:
        mock_settings.TRANSCRIPTION_PROVIDER = "deepgram"
        mock_settings.deepgram_language_codes_list = ["en-US", "hi-IN", "es-US"]

        assert service._resolve_deepgram_language() == "multi"


def test_parse_deepgram_response_groups_words_by_speaker():
    service = SpeechTranscriptionService(NegotiationSession(session_id="stt-test"))

    payload = {
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "hello there general kenobi",
                            "confidence": 0.91,
                            "language": "en-US",
                            "words": [
                                {"word": "hello", "start": 0.0, "end": 0.2, "confidence": 0.95, "speaker": 0},
                                {"word": "there", "start": 0.2, "end": 0.4, "confidence": 0.93, "speaker": 0},
                                {"word": "general", "start": 0.5, "end": 0.8, "confidence": 0.9, "speaker": 1},
                                {"word": "kenobi", "start": 0.8, "end": 1.1, "confidence": 0.89, "speaker": 1},
                            ],
                        }
                    ]
                }
            ]
        }
    }

    parsed = service._parse_deepgram_response(payload, adaptation_phrases=["kenobi"])

    assert parsed["text"] == "hello there general kenobi"
    assert parsed["confidence"] == 0.91
    assert parsed["language_code"] == "en-US"
    assert parsed["provider"] == "deepgram"
    assert parsed["diarized_turns"] == [
        {
            "diarized_speaker_id": "0",
            "text": "hello there",
            "start_time": 0.0,
            "end_time": 0.4,
            "transcription_confidence": 0.95,
        },
        {
            "diarized_speaker_id": "1",
            "text": "general kenobi",
            "start_time": 0.5,
            "end_time": 1.1,
            "transcription_confidence": 0.9,
        },
    ]
