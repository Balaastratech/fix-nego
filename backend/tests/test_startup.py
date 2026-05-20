"""
Tests for application startup behavior with Google STT + SpeechBrain.
"""

import asyncio
from unittest.mock import patch


def test_startup_reports_full_capability_path_when_stt_and_speechbrain_probe_succeed():
    with patch("app.main.settings") as mock_settings, \
         patch("app.main.SpeechTranscriptionService") as mock_stt_service, \
         patch("app.main.speechbrain_service") as mock_speechbrain_service, \
         patch("app.main.capability_registry") as mock_registry:

        mock_settings.GEMINI_MODEL = "gemini-test"
        mock_settings.GOOGLE_STT_REGION = "us"
        mock_settings.GOOGLE_STT_MODEL = "chirp_3"
        mock_settings.SPEECHBRAIN_DEVICE = "cpu"
        mock_settings.SPEECHBRAIN_ENABLED = True
        mock_settings.SPEAKER_RECOGNITION_ENABLED = True
        mock_settings.RESEMBLYZER_ENABLED = False
        mock_settings.WESPEAKER_ENABLED = False
        mock_settings.GOOGLE_GENAI_USE_VERTEXAI = False
        mock_stt_service.return_value.probe_capability.return_value = (True, "ok")
        mock_speechbrain_service.probe_capability.return_value = (True, "ok")
        mock_registry.active_path.return_value = "full"

        from app.main import startup_event

        asyncio.run(startup_event())

        mock_registry.set_google_stt.assert_called_once()
        mock_registry.set_speechbrain.assert_called_once()
        mock_speechbrain_service.probe_capability.assert_called_once()


def test_startup_degrades_when_speechbrain_probe_fails():
    with patch("app.main.settings") as mock_settings, \
         patch("app.main.SpeechTranscriptionService") as mock_stt_service, \
         patch("app.main.speechbrain_service") as mock_speechbrain_service, \
         patch("app.main.capability_registry") as mock_registry, \
         patch("app.main.logger") as mock_logger:

        mock_settings.GEMINI_MODEL = "gemini-test"
        mock_settings.GOOGLE_STT_REGION = "us"
        mock_settings.GOOGLE_STT_MODEL = "chirp_3"
        mock_settings.SPEECHBRAIN_DEVICE = "cpu"
        mock_settings.SPEECHBRAIN_ENABLED = True
        mock_settings.SPEAKER_RECOGNITION_ENABLED = True
        mock_settings.RESEMBLYZER_ENABLED = False
        mock_settings.WESPEAKER_ENABLED = False
        mock_settings.GOOGLE_GENAI_USE_VERTEXAI = False
        mock_stt_service.return_value.probe_capability.return_value = (True, "ok")
        mock_speechbrain_service.probe_capability.return_value = (False, "speechbrain_disabled")
        mock_registry.active_path.return_value = "degraded"

        from app.main import startup_event

        asyncio.run(startup_event())

        warning_messages = [call.args[0] for call in mock_logger.warning.call_args_list]
        assert any("SpeechBrain probe failed" in message for message in warning_messages)


def test_startup_degrades_when_stt_probe_fails():
    with patch("app.main.settings") as mock_settings, \
         patch("app.main.SpeechTranscriptionService") as mock_stt_service, \
         patch("app.main.speechbrain_service") as mock_speechbrain_service, \
         patch("app.main.capability_registry") as mock_registry, \
         patch("app.main.logger") as mock_logger:

        mock_settings.GEMINI_MODEL = "gemini-test"
        mock_settings.GOOGLE_STT_REGION = "us"
        mock_settings.GOOGLE_STT_MODEL = "chirp_3"
        mock_settings.SPEECHBRAIN_DEVICE = "cpu"
        mock_settings.SPEECHBRAIN_ENABLED = True
        mock_settings.SPEAKER_RECOGNITION_ENABLED = True
        mock_settings.RESEMBLYZER_ENABLED = False
        mock_settings.WESPEAKER_ENABLED = False
        mock_settings.GOOGLE_GENAI_USE_VERTEXAI = False
        mock_stt_service.return_value.probe_capability.return_value = (False, "region_not_supported")
        mock_speechbrain_service.probe_capability.return_value = (True, "ok")
        mock_registry.active_path.return_value = "degraded"

        from app.main import startup_event

        asyncio.run(startup_event())

        error_messages = [call.args[0] for call in mock_logger.error.call_args_list]
        assert any("Google STT diarization probe failed" in message for message in error_messages)


def test_startup_logs_provider_configuration():
    with patch("app.main.settings") as mock_settings, \
         patch("app.main.SpeechTranscriptionService") as mock_stt_service, \
         patch("app.main.speechbrain_service") as mock_speechbrain_service, \
         patch("app.main.capability_registry") as mock_registry, \
         patch("app.main.logger") as mock_logger:

        mock_settings.GEMINI_MODEL = "gemini-test"
        mock_settings.GOOGLE_STT_REGION = "us"
        mock_settings.GOOGLE_STT_MODEL = "chirp_3"
        mock_settings.SPEECHBRAIN_DEVICE = "cpu"
        mock_settings.SPEECHBRAIN_ENABLED = False
        mock_settings.SPEAKER_RECOGNITION_ENABLED = False
        mock_settings.RESEMBLYZER_ENABLED = False
        mock_settings.WESPEAKER_ENABLED = False
        mock_settings.GOOGLE_GENAI_USE_VERTEXAI = False
        mock_stt_service.return_value.probe_capability.return_value = (True, "ok")
        mock_speechbrain_service.probe_capability.return_value = (False, "speechbrain_disabled")
        mock_registry.active_path.return_value = "degraded"

        from app.main import startup_event

        asyncio.run(startup_event())

        info_messages = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any("Speaker recognition providers configured" in message for message in info_messages)
