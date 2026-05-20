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
