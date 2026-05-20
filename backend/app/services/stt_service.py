from __future__ import annotations

import asyncio
import logging
import os
import re
import struct
from urllib.parse import urlparse
from typing import Any

from app.config import settings
from app.services.capability_registry import capability_registry
from app.models.negotiation import NegotiationSession
from app.services.bounded_async import GlobalLimiter, run_with_retries
from app.services.utterance_types import FinalizedUtterance
from app.utils.speaker_debug import log_speaker_debug

logger = logging.getLogger(__name__)
_BROKEN_PROXY_ENV_SANITIZED = False


def _sanitize_broken_loopback_proxy_env() -> None:
    global _BROKEN_PROXY_ENV_SANITIZED
    if _BROKEN_PROXY_ENV_SANITIZED:
        return

    removed: list[str] = []
    proxy_keys = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ]

    for key in proxy_keys:
        raw = os.environ.get(key)
        if not raw:
            continue
        try:
            parsed = urlparse(raw)
        except Exception:
            continue

        host = (parsed.hostname or "").strip().lower()
        port = parsed.port
        if host in {"127.0.0.1", "localhost", "::1"} and port == 9:
            os.environ.pop(key, None)
            removed.append(key)

    if removed:
        os.environ["GRPC_ENABLE_HTTP_PROXY"] = "0"
        logger.warning(
            "[STT] Removed broken loopback proxy env for Google STT: %s",
            ", ".join(sorted(removed)),
        )

    _BROKEN_PROXY_ENV_SANITIZED = True


def _duration_to_seconds(value: Any) -> float:
    if value is None:
        return 0.0
    if hasattr(value, "total_seconds"):
        try:
            return float(value.total_seconds())
        except Exception:
            pass
    seconds = getattr(value, "seconds", 0) or 0
    nanos = getattr(value, "nanos", 0) or 0
    return float(seconds) + (float(nanos) / 1_000_000_000.0)


def _pcm_to_wav(pcm_data: bytes) -> bytes:
    sr, nc, sw = 16000, 1, 2
    br = sr * nc * sw
    ba = nc * sw
    ds = len(pcm_data)
    hdr = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + ds, b"WAVE", b"fmt ", 16, 1, nc,
        sr, br, ba, sw * 8, b"data", ds,
    )
    return hdr + pcm_data


class SpeechTranscriptionService:
    def __init__(self, session: NegotiationSession):
        self.session = session
        self._clients: dict[str, Any] = {}
        self._ensured_recognizers: set[tuple[str, str, str]] = set()
        self._global_limiter = GlobalLimiter.get("google_stt", settings.STT_GLOBAL_CONCURRENCY)

    def _get_client(self, location_override: str | None = None):
        _sanitize_broken_loopback_proxy_env()
        location = (location_override or settings.GOOGLE_STT_LOCATION or "").strip().lower()
        cache_key = location or "default"
        if cache_key not in self._clients:
            from google.api_core.client_options import ClientOptions
            from google.cloud.speech_v2 import SpeechClient

            client_options = None
            if location and location != "global":
                client_options = ClientOptions(
                    api_endpoint=f"{location}-speech.googleapis.com"
                )

            self._clients[cache_key] = SpeechClient(client_options=client_options)
        return self._clients[cache_key]

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        message = str(exc).lower()
        return any(
            marker in message
            for marker in ("429", "resource exhausted", "temporar", "deadline", "timeout", "503", "500")
        )

    @staticmethod
    def _candidate_locations(location: str, model_name: str) -> list[str]:
        normalized = (location or "").strip().lower()
        candidates: list[str] = []

        def add(value: str) -> None:
            if value and value not in candidates:
                candidates.append(value)

        add(normalized)
        if model_name == "chirp_3":
            # Per official Chirp 3 docs: ONLY available in `us` (multi-region)
            # and `eu` (multi-region) — both GA. NOT available in regional zones
            # like us-central1, asia-south1, etc. If user configured a regional
            # endpoint, map it to the correct multi-region.
            if normalized in {"", "global", "us-central1", "us-east1", "us-west1", "us-east4"}:
                candidates = ["us"]
            elif normalized in {"europe-west1", "europe-west2", "europe-west3", "europe-west4"}:
                candidates = ["eu"]
            # Keep "us", "eu", "asia-*" (asia for forward compat) as-is.

        return candidates or [settings.GOOGLE_STT_LOCATION]

    @staticmethod
    def _supports_named_recognizer_creation(recognizer_id: str) -> bool:
        return bool(recognizer_id and recognizer_id != "_")

    @staticmethod
    def _is_not_found_message(message: str) -> bool:
        normalized = (message or "").strip().lower()
        return (
            "requested entity was not found" in normalized
            or "unable to find recognizer" in normalized
            or ("recognizer" in normalized and "not found" in normalized)
        )

    async def transcribe(self, utterance: FinalizedUtterance) -> FinalizedUtterance:
        stt_started = asyncio.get_event_loop().time()
        async with self.session.stt_lock:
            async with self._global_limiter:
                self.session.session_metrics["stt_requests"] += 1
                self.session.session_metrics["google_stt_minutes"] += utterance.duration_ms / 60000.0

                async def _on_retry(attempt: int, exc: Exception) -> None:
                    self.session.session_metrics["stt_retry_count"] += 1
                    logger.warning(
                        "[STT] retrying utterance %s attempt=%s session=%s error=%s",
                        utterance.utterance_id,
                        attempt,
                        self.session.session_id,
                        exc,
                    )

                async def _call():
                    return await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: self._recognize_sync(
                                utterance.audio,
                                language_hint=self.session.language,
                                response_language_hint=self.session.response_language,
                            ),
                        ),
                        timeout=settings.STT_END_TO_END_TIMEOUT_SECONDS,
                    )

                response = await run_with_retries(
                    "google_stt_recognize",
                    _call,
                    max_retries=settings.STT_MAX_RETRIES,
                    base_backoff_ms=settings.STT_BASE_BACKOFF_MS,
                    max_backoff_ms=settings.STT_MAX_BACKOFF_MS,
                    is_retryable=self._is_retryable,
                    on_retry=_on_retry,
                )
        logger.info(
            "[STT] utterance complete id=%s duration_ms=%s stt_elapsed_ms=%.1f [session=%s]",
            utterance.utterance_id,
            utterance.duration_ms,
            (asyncio.get_event_loop().time() - stt_started) * 1000.0,
            self.session.session_id,
        )

        text = (response.get("text") or "").strip()
        confidence = response.get("confidence")
        utterance.transcript_text = text
        utterance.transcription_confidence = confidence
        utterance.metadata["stt_response"] = response
        utterance.metadata["diarized_turns"] = response.get("diarized_turns", [])

        if text:
            self.session.session_metrics["stt_successes"] += 1
        else:
            self.session.session_metrics["stt_empty_results"] += 1
            logger.info(
                "[STT] empty transcript result session=%s utterance=%s duration_ms=%s",
                self.session.session_id,
                utterance.utterance_id,
                utterance.duration_ms,
            )
        diarized_turns = response.get("diarized_turns", [])
        log_speaker_debug(
            "STT_RESULT",
            session_id=self.session.session_id,
            utterance_id=utterance.utterance_id,
            language_hint=self.session.language,
            response_language_hint=self.session.response_language,
            adaptation_phrases=response.get("adaptation_phrases", []),
            resolved_text=text,
            confidence=confidence,
            diarized_turn_count=len(diarized_turns),
            diarized_turns=[
                {
                    "speaker_id": turn.get("diarized_speaker_id"),
                    "start": turn.get("start_time"),
                    "end": turn.get("end_time"),
                    "text": turn.get("text"),
                }
                for turn in diarized_turns
            ],
        )

        return utterance

    def _resolve_language_codes(
        self,
        language_hint: str | None = None,
        response_language_hint: str | None = None,
    ) -> list[str]:
        configured = settings.google_stt_language_codes_list

        for hint in (language_hint, response_language_hint):
            if hint and hint in configured:
                return [hint]

        # Per official Chirp 3 docs (us/eu multi-region):
        #   - language_codes=["auto"] IS supported for automatic language detection
        #   - Multiple explicit codes are also supported
        # Just return whatever is configured. Empty → "auto" (language-agnostic).
        if not configured:
            return ["auto"]
        return configured

    def _resolve_adaptation_phrases(self) -> list[str]:
        phrases: list[str] = []
        seen: set[str] = set()

        def add_phrase(value: str | None) -> None:
            if not value:
                return
            cleaned = " ".join(str(value).strip().split())
            if not cleaned:
                return
            key = cleaned.casefold()
            if key in seen:
                return
            seen.add(key)
            phrases.append(cleaned)

        for phrase in settings.google_stt_hint_phrases_list:
            add_phrase(phrase)

        for key in ("item", "title", "product", "brand", "model", "variant"):
            value = self.session.user_context.get(key) if isinstance(self.session.user_context, dict) else None
            if isinstance(value, str):
                add_phrase(value)

        context_sources = [
            self.session.context,
            self.session.user_context.get("item") if isinstance(self.session.user_context, dict) else None,
        ]
        token_pattern = re.compile(
            r"\b(?:[A-Za-z]+(?:\s+[A-Za-z0-9]+){0,4}\s+(?:Pro(?:\s+Max)?|Max|Ultra|Plus)|[A-Za-z]+\s+\d{1,4}(?:\s+[A-Za-z0-9]+){0,3})\b"
        )
        for source in context_sources:
            if not source:
                continue
            for match in token_pattern.findall(str(source)):
                add_phrase(match)

        return phrases[:25]

    def _recognize_sync(
        self,
        audio: bytes,
        language_hint: str | None = None,
        response_language_hint: str | None = None,
    ) -> dict[str, Any]:
        from google.cloud.speech_v2.types import cloud_speech
        language_codes = self._resolve_language_codes(language_hint, response_language_hint)
        adaptation_phrases = self._resolve_adaptation_phrases()

        adaptation = None
        if adaptation_phrases:
            adaptation = cloud_speech.SpeechAdaptation(
                phrase_sets=[
                    cloud_speech.SpeechAdaptation.AdaptationPhraseSet(
                        inline_phrase_set=cloud_speech.PhraseSet(
                            boost=float(settings.GOOGLE_STT_HINT_BOOST),
                            phrases=[
                                cloud_speech.PhraseSet.Phrase(
                                    value=phrase,
                                    boost=float(settings.GOOGLE_STT_HINT_BOOST),
                                )
                                for phrase in adaptation_phrases
                            ],
                        )
                    )
                ]
            )

        def _build_diarization_config(model_name: str):
            """Chirp 3 only supports diarization in BatchRecognize per official docs:
                "Speaker Diarization | Available only in Speech.BatchRecognize"
            Sending diarizationConfig to Recognize() with chirp_3 returns a
            generic 404 NotFound. We use synchronous Recognize(), so we MUST
            omit diarizationConfig for chirp_3.

            Speaker classification is handled by SpeechBrain on our side anyway
            (via enrollment embedding), so we don't lose functionality.

            For other models (long, latest_long, chirp_2), diarization works
            in Recognize() with min/max speaker counts.
            """
            if not settings.GOOGLE_STT_DIARIZATION_ENABLED:
                return None
            if model_name == "chirp_3":
                # Diarization not supported in sync Recognize for chirp_3 — skip
                return None
            return cloud_speech.SpeakerDiarizationConfig(
                min_speaker_count=settings.GOOGLE_STT_DIARIZATION_MIN_SPEAKERS,
                max_speaker_count=settings.GOOGLE_STT_DIARIZATION_MAX_SPEAKERS,
            )

        def build_request(model_name: str, recognizer: str):
            return cloud_speech.RecognizeRequest(
                recognizer=recognizer,
                config=cloud_speech.RecognitionConfig(
                    auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
                    language_codes=language_codes,
                    model=model_name,
                    adaptation=adaptation,
                    features=cloud_speech.RecognitionFeatures(
                        enable_automatic_punctuation=True,
                        diarization_config=_build_diarization_config(model_name),
                    ),
                ),
                content=_pcm_to_wav(audio),
            )

        def build_default_recognition_config(model_name: str):
            return cloud_speech.RecognitionConfig(
                auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
                language_codes=language_codes,
                model=model_name,
                features=cloud_speech.RecognitionFeatures(
                    enable_automatic_punctuation=True,
                    diarization_config=_build_diarization_config(model_name),
                ),
            )

        def ensure_named_recognizer(location: str, model_name: str) -> None:
            recognizer_id = settings.GOOGLE_STT_RECOGNIZER
            if not self._supports_named_recognizer_creation(recognizer_id):
                return

            cache_key = (location, recognizer_id, model_name)
            if cache_key in self._ensured_recognizers:
                return

            client = self._get_client(location)
            recognizer_name = (
                f"projects/{settings.GOOGLE_CLOUD_PROJECT}/locations/{location}"
                f"/recognizers/{recognizer_id}"
            )

            try:
                client.get_recognizer(name=recognizer_name)
                self._ensured_recognizers.add(cache_key)
                logger.info(
                    "[STT] named recognizer %s already exists at %s [session=%s]",
                    recognizer_id,
                    location,
                    self.session.session_id,
                )
                return
            except Exception as exc:
                exc_msg = str(exc)
                if not self._is_not_found_message(exc_msg):
                    # Detailed log so we can see permission / API-disabled errors
                    logger.error(
                        "[STT] get_recognizer FAILED (non-404) for %s at %s: type=%s message=%s "
                        "details=%s grpc_status=%s [session=%s]",
                        recognizer_id,
                        location,
                        type(exc).__name__,
                        exc_msg,
                        getattr(exc, "details", lambda: None)() if callable(getattr(exc, "details", None)) else getattr(exc, "details", None),
                        getattr(exc, "code", lambda: None)() if callable(getattr(exc, "code", None)) else getattr(exc, "code", None),
                        self.session.session_id,
                    )
                    raise

            parent = f"projects/{settings.GOOGLE_CLOUD_PROJECT}/locations/{location}"
            logger.warning(
                "[STT] named recognizer %s not found, creating it at %s [session=%s]",
                recognizer_id,
                location,
                self.session.session_id,
            )
            try:
                operation = client.create_recognizer(
                    request=cloud_speech.CreateRecognizerRequest(
                        parent=parent,
                        recognizer_id=recognizer_id,
                        recognizer=cloud_speech.Recognizer(
                            default_recognition_config=build_default_recognition_config(model_name),
                        ),
                    )
                )
                operation.result()
                logger.info(
                    "[STT] recognizer %s CREATED successfully at %s with model=%s [session=%s]",
                    recognizer_id,
                    location,
                    model_name,
                    self.session.session_id,
                )
            except Exception as exc:
                exc_msg = str(exc)
                if "already exists" in exc_msg.lower():
                    logger.info(
                        "[STT] recognizer %s already exists at %s (race) [session=%s]",
                        recognizer_id,
                        location,
                        self.session.session_id,
                    )
                else:
                    # SURFACE THE EXACT GOOGLE ERROR — this is the diagnostic we need
                    error_details = None
                    try:
                        error_details = getattr(exc, "details", None)
                        if callable(error_details):
                            error_details = error_details()
                    except Exception:
                        error_details = None
                    error_code = None
                    try:
                        error_code = getattr(exc, "code", None)
                        if callable(error_code):
                            error_code = error_code()
                    except Exception:
                        error_code = None
                    logger.error(
                        "[STT] create_recognizer FAILED for %s at %s with model=%s\n"
                        "  exception_type: %s\n"
                        "  message: %s\n"
                        "  grpc_code: %s\n"
                        "  details: %s\n"
                        "  parent_path: %s\n"
                        "  language_codes: %s\n"
                        "  project: %s\n"
                        "  [session=%s]",
                        recognizer_id,
                        location,
                        model_name,
                        type(exc).__name__,
                        exc_msg,
                        error_code,
                        error_details,
                        parent,
                        language_codes,
                        settings.GOOGLE_CLOUD_PROJECT,
                        self.session.session_id,
                    )
                    raise
            self._ensured_recognizers.add(cache_key)

        def recognize_once(location: str, model_name: str):
            ensure_named_recognizer(location, model_name)
            recognizer = (
                f"projects/{settings.GOOGLE_CLOUD_PROJECT}/locations/{location}"
                f"/recognizers/{settings.GOOGLE_STT_RECOGNIZER}"
            )
            # DEBUG: prove exact bytes being sent — eliminates "missing underscore" doubt
            logger.info(
                "[STT] OUTGOING recognizer string: repr=%r len=%d last_char=%r raw_env_value=%r model=%r project=%r location=%r",
                recognizer,
                len(recognizer),
                recognizer[-1] if recognizer else None,
                settings.GOOGLE_STT_RECOGNIZER,
                model_name,
                settings.GOOGLE_CLOUD_PROJECT,
                location,
            )
            client = self._get_client(location)
            import time as _time
            started = _time.monotonic()
            try:
                return client.recognize(
                    request=build_request(model_name, recognizer),
                    timeout=settings.STT_RPC_TIMEOUT_SECONDS,
                )
            finally:
                elapsed_ms = (_time.monotonic() - started) * 1000.0
                logger.info(
                    "[STT] recognize() finished model=%s location=%s elapsed_ms=%.1f [session=%s]",
                    model_name,
                    location,
                    elapsed_ms,
                    self.session.session_id,
                )

        configured_location = settings.GOOGLE_STT_LOCATION
        recognizer_id = settings.GOOGLE_STT_RECOGNIZER
        model_name = settings.GOOGLE_STT_MODEL
        candidate_locations = self._candidate_locations(configured_location, model_name)
        last_exc: Exception | None = None
        response = None

        for attempt_location in candidate_locations:
            try:
                if attempt_location != configured_location:
                    logger.warning(
                        "[STT] retrying model %s at fallback location %s [session=%s]",
                        model_name,
                        attempt_location,
                        self.session.session_id,
                    )
                response = recognize_once(attempt_location, model_name)
                break
            except Exception as exc:
                last_exc = exc
                message = str(exc)
                normalized_message = message.lower()
                not_found = self._is_not_found_message(message)
                timed_out = "deadline" in normalized_message or "timeout" in normalized_message
                wrong_location = (
                    "does not exist in the location named" in normalized_message
                    or "unsupported for location" in normalized_message
                    or "expected resource location to be global" in normalized_message
                )
                diarization_unsupported = "does not support speaker diarization" in message.lower()

                # ENHANCED ERROR LOGGING — surface full Google error details
                error_details = None
                error_code = None
                try:
                    error_details = getattr(exc, "details", None)
                    if callable(error_details):
                        error_details = error_details()
                except Exception:
                    pass
                try:
                    error_code = getattr(exc, "code", None)
                    if callable(error_code):
                        error_code = error_code()
                except Exception:
                    pass

                if model_name == "chirp_3" and (not_found or wrong_location):
                    logger.error(
                        "[STT] chirp_3 recognize() FAILED at %s\n"
                        "  exception_type: %s\n"
                        "  message: %s\n"
                        "  grpc_code: %s\n"
                        "  details: %s\n"
                        "  recognizer_path: projects/%s/locations/%s/recognizers/%s\n"
                        "  model_in_request: %s\n"
                        "  language_codes: %s\n"
                        "  ==> The recognizer exists but Google rejects the model. This means:\n"
                        "      chirp_3 is NOT enabled for project '%s' in location '%s'.\n"
                        "      Auto-falling back to chirp_2 to verify if STT API itself works.\n"
                        "  [session=%s]",
                        attempt_location,
                        type(exc).__name__,
                        message,
                        error_code,
                        error_details,
                        settings.GOOGLE_CLOUD_PROJECT,
                        attempt_location,
                        settings.GOOGLE_STT_RECOGNIZER,
                        model_name,
                        language_codes,
                        settings.GOOGLE_CLOUD_PROJECT,
                        attempt_location,
                        self.session.session_id,
                    )
                    # AUTO-FALLBACK: try chirp_2 to prove API + permissions work
                    try:
                        logger.warning(
                            "[STT] FALLBACK: retrying with chirp_2 at %s [session=%s]",
                            attempt_location,
                            self.session.session_id,
                        )
                        response = recognize_once(attempt_location, "chirp_2")
                        logger.info(
                            "[STT] ✅ chirp_2 SUCCEEDED at %s — your STT works, but chirp_3 is not enrolled. "
                            "Either: (1) use chirp_2 permanently by setting GOOGLE_STT_MODEL=chirp_2, "
                            "or (2) request Chirp 3 access via Google Cloud Console. "
                            "[session=%s]",
                            attempt_location,
                            self.session.session_id,
                        )
                        break
                    except Exception as fallback_exc:
                        logger.error(
                            "[STT] chirp_2 ALSO failed at %s: %s — this means STT API itself is unreachable. "
                            "Check: 1) speech.googleapis.com enabled, 2) ADC has roles/speech.client, "
                            "3) quota_project matches GOOGLE_CLOUD_PROJECT. [session=%s]",
                            attempt_location,
                            str(fallback_exc),
                            self.session.session_id,
                        )
                        continue

                if model_name == "chirp_3" and timed_out:
                    logger.warning(
                        "[STT] chirp_3 timed out at %s after %.1fs; trying fallback models [session=%s]",
                        attempt_location,
                        settings.STT_RPC_TIMEOUT_SECONDS,
                        self.session.session_id,
                    )
                    for fallback_model in ("chirp_2", "latest_long"):
                        try:
                            response = recognize_once(attempt_location, fallback_model)
                            logger.warning(
                                "[STT] fallback model %s succeeded after chirp_3 timeout at %s [session=%s]",
                                fallback_model,
                                attempt_location,
                                self.session.session_id,
                            )
                            break
                        except Exception as fallback_exc:
                            logger.warning(
                                "[STT] fallback model %s failed after chirp_3 timeout at %s: %s [session=%s]",
                                fallback_model,
                                attempt_location,
                                fallback_exc,
                                self.session.session_id,
                            )
                    if response is not None:
                        break

                if model_name == "chirp_3" and diarization_unsupported:
                    raise

                if model_name not in {"long", "latest_long", "chirp_3"} and wrong_location:
                    logger.warning(
                        "[STT] model %s unsupported for location %s, falling back to latest_long [session=%s]",
                        model_name,
                        attempt_location,
                        self.session.session_id,
                    )
                    response = recognize_once(attempt_location, "latest_long")
                    break

                # Generic error path — log full details for any other failure
                logger.error(
                    "[STT] recognize() FAILED for model=%s at %s\n"
                    "  exception_type: %s\n"
                    "  message: %s\n"
                    "  grpc_code: %s\n"
                    "  details: %s\n"
                    "  [session=%s]",
                    model_name,
                    attempt_location,
                    type(exc).__name__,
                    message,
                    error_code,
                    error_details,
                    self.session.session_id,
                )
                raise

        if response is None:
            if last_exc is not None:
                raise last_exc
            raise RuntimeError("stt_recognition_failed_without_response")
        alternatives: list[Any] = []
        for result in getattr(response, "results", []) or []:
            alternatives.extend(getattr(result, "alternatives", []) or [])

        if not alternatives:
            return {"text": "", "confidence": None, "diarized_turns": []}

        best = max(alternatives, key=lambda alt: getattr(alt, "confidence", 0.0))
        words = list(getattr(best, "words", []) or [])
        diarized_turns: list[dict[str, Any]] = []
        current_turn: dict[str, Any] | None = None
        for word in words:
            speaker_tag = getattr(word, "speaker_label", None) or getattr(word, "speaker_tag", None)
            if speaker_tag is None:
                continue
            start_time = _duration_to_seconds(getattr(word, "start_offset", None))
            end_time = _duration_to_seconds(getattr(word, "end_offset", None))
            word_text = getattr(word, "word", "") or ""
            diarized_id = str(speaker_tag)
            if current_turn and current_turn["diarized_speaker_id"] == diarized_id:
                current_turn["text"] = f"{current_turn['text']} {word_text}".strip()
                current_turn["end_time"] = end_time
            else:
                if current_turn:
                    diarized_turns.append(current_turn)
                current_turn = {
                    "diarized_speaker_id": diarized_id,
                    "text": word_text,
                    "start_time": start_time,
                    "end_time": end_time,
                    "transcription_confidence": float(getattr(best, "confidence", 0.0) or 0.0),
                }
        if current_turn:
            diarized_turns.append(current_turn)
        return {
            "text": getattr(best, "transcript", "") or "",
            "confidence": float(getattr(best, "confidence", 0.0) or 0.0),
            "language_code": getattr(best, "language_code", None),
            "diarized_turns": diarized_turns,
            "adaptation_phrases": adaptation_phrases,
        }

    def probe_capability(self) -> tuple[bool, str]:
        try:
            # Pass an explicit en-US hint so the probe never exercises the
            # invalid `["auto"]` path for Chirp 3 at the `us` endpoint.
            self._recognize_sync(b"\x00" * 32000, language_hint="en-US")
            capability_registry.set_google_stt(
                capability_registry.google_stt().__class__(
                    available=True,
                    reason="ok",
                    provider="google_stt",
                    region=settings.GOOGLE_STT_REGION,
                )
            )
            return True, "ok"
        except Exception as exc:
            capability_registry.set_google_stt(
                capability_registry.google_stt().__class__(
                    available=False,
                    reason=str(exc),
                    provider="google_stt",
                    region=settings.GOOGLE_STT_REGION,
                )
            )
            return False, str(exc)
