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
        mock_settings.TRANSCRIPTION_PROVIDER = "google_stt"
        mock_settings.transcription_language_codes_list = ["en-US"]
        mock_settings.supported_auto_speaker_languages_list = ["en-US"]
        mock_settings.STARTUP_PROBE_TIMEOUT_SECONDS = 1.0
        mock_settings.VISION_ENABLED = True
        mock_settings.GOOGLE_STT_REGION = "us"
        mock_settings.GOOGLE_STT_LOCATION = "us"
        mock_settings.GOOGLE_STT_RECOGNIZER = "_"
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

        from app.main import _run_capability_probes_in_background

        asyncio.run(_run_capability_probes_in_background())

        mock_registry.set_stt.assert_called_once()
        mock_registry.set_speechbrain.assert_called_once()
        mock_speechbrain_service.probe_capability.assert_called_once()


def test_startup_degrades_when_speechbrain_probe_fails():
    with patch("app.main.settings") as mock_settings, \
         patch("app.main.SpeechTranscriptionService") as mock_stt_service, \
         patch("app.main.speechbrain_service") as mock_speechbrain_service, \
         patch("app.main.capability_registry") as mock_registry, \
         patch("app.main.logger") as mock_logger:

        mock_settings.GEMINI_MODEL = "gemini-test"
        mock_settings.TRANSCRIPTION_PROVIDER = "google_stt"
        mock_settings.transcription_language_codes_list = ["en-US"]
        mock_settings.supported_auto_speaker_languages_list = ["en-US"]
        mock_settings.STARTUP_PROBE_TIMEOUT_SECONDS = 1.0
        mock_settings.VISION_ENABLED = True
        mock_settings.GOOGLE_STT_REGION = "us"
        mock_settings.GOOGLE_STT_LOCATION = "us"
        mock_settings.GOOGLE_STT_RECOGNIZER = "_"
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

        from app.main import _run_capability_probes_in_background

        asyncio.run(_run_capability_probes_in_background())

        warning_messages = [call.args[0] for call in mock_logger.warning.call_args_list]
        assert any("SpeechBrain probe failed" in message for message in warning_messages)


def test_startup_degrades_when_stt_probe_fails():
    with patch("app.main.settings") as mock_settings, \
         patch("app.main.SpeechTranscriptionService") as mock_stt_service, \
         patch("app.main.speechbrain_service") as mock_speechbrain_service, \
         patch("app.main.capability_registry") as mock_registry, \
         patch("app.main.logger") as mock_logger:

        mock_settings.GEMINI_MODEL = "gemini-test"
        mock_settings.TRANSCRIPTION_PROVIDER = "google_stt"
        mock_settings.transcription_language_codes_list = ["en-US"]
        mock_settings.supported_auto_speaker_languages_list = ["en-US"]
        mock_settings.STARTUP_PROBE_TIMEOUT_SECONDS = 1.0
        mock_settings.VISION_ENABLED = True
        mock_settings.GOOGLE_STT_REGION = "us"
        mock_settings.GOOGLE_STT_LOCATION = "us"
        mock_settings.GOOGLE_STT_RECOGNIZER = "_"
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

        from app.main import _run_capability_probes_in_background

        asyncio.run(_run_capability_probes_in_background())

        error_messages = [call.args[0] for call in mock_logger.error.call_args_list]
        assert any("Google STT diarization probe failed" in message for message in error_messages)


def test_startup_logs_provider_configuration():
    def _capture_and_close_task(coro, name=None):
        coro.close()
        return None

    with patch("app.main.settings") as mock_settings, \
         patch("app.main.SpeechTranscriptionService") as mock_stt_service, \
         patch("app.main.speechbrain_service") as mock_speechbrain_service, \
         patch("app.main.capability_registry") as mock_registry, \
         patch("app.main.logger") as mock_logger, \
         patch("app.main.session_store") as mock_session_store, \
         patch("app.main.asyncio.create_task", side_effect=_capture_and_close_task) as mock_create_task:

        mock_settings.GEMINI_MODEL = "gemini-test"
        mock_settings.TRANSCRIPTION_PROVIDER = "google_stt"
        mock_settings.transcription_language_codes_list = ["en-US"]
        mock_settings.supported_auto_speaker_languages_list = ["en-US"]
        mock_settings.STARTUP_PROBE_TIMEOUT_SECONDS = 1.0
        mock_settings.VISION_ENABLED = True
        mock_settings.GOOGLE_STT_REGION = "us"
        mock_settings.GOOGLE_STT_LOCATION = "us"
        mock_settings.GOOGLE_STT_RECOGNIZER = "_"
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
        mock_session_store.initialize.assert_called_once()
        mock_create_task.assert_called_once()


def test_startup_uses_deepgram_provider_probe_path():
    with patch("app.main.settings") as mock_settings, \
         patch("app.main.SpeechTranscriptionService") as mock_stt_service, \
         patch("app.main.speechbrain_service") as mock_speechbrain_service, \
         patch("app.main.capability_registry") as mock_registry, \
         patch("app.main.logger") as mock_logger:

        mock_settings.GEMINI_MODEL = "gemini-test"
        mock_settings.TRANSCRIPTION_PROVIDER = "deepgram"
        mock_settings.transcription_language_codes_list = ["en-US", "hi-IN"]
        mock_settings.supported_auto_speaker_languages_list = ["en-US", "hi-IN"]
        mock_settings.STARTUP_PROBE_TIMEOUT_SECONDS = 1.0
        mock_settings.VISION_ENABLED = True
        mock_settings.DEEPGRAM_MODEL = "nova-3"
        mock_settings.DEEPGRAM_API_BASE_URL = "https://api.deepgram.com/v1/listen"
        mock_settings.GOOGLE_STT_REGION = "us"
        mock_settings.SPEECHBRAIN_DEVICE = "cpu"
        mock_settings.SPEECHBRAIN_ENABLED = False
        mock_settings.SPEAKER_RECOGNITION_ENABLED = False
        mock_settings.RESEMBLYZER_ENABLED = False
        mock_settings.WESPEAKER_ENABLED = False
        mock_settings.GOOGLE_GENAI_USE_VERTEXAI = False
        mock_stt_service.return_value.probe_capability.return_value = (True, "ok")
        mock_speechbrain_service.probe_capability.return_value = (False, "speechbrain_disabled")
        mock_registry.active_path.return_value = "degraded"

        from app.main import _run_capability_probes_in_background

        asyncio.run(_run_capability_probes_in_background())

        mock_registry.set_stt.assert_called_once()
        stt_status = mock_registry.set_stt.call_args.args[0]
        assert stt_status.provider == "deepgram"
