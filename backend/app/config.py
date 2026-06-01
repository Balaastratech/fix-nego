from pydantic_settings import BaseSettings
import logging

from app.ai_assets import (
    DEFAULT_GEMINI_FALLBACK_MODEL,
    DEFAULT_GEMINI_FLASH_MODEL,
    DEFAULT_GOOGLE_STT_HINT_BOOST,
    DEFAULT_GEMINI_LIVE_MODEL,
    DEFAULT_GOOGLE_STT_LANGUAGE_CODES,
    DEFAULT_GOOGLE_STT_MODEL,
    DEFAULT_SUPPORTED_AUTO_SPEAKER_LANGUAGES,
    qualify_model_name,
)
# DEFAULT_GOOGLE_STT_HINT_PHRASES removed — hardcoded keywords caused STT hallucinations

logger = logging.getLogger(__name__)

class Config(BaseSettings):
    GEMINI_API_KEY: str = ""

    # ── Phase C — minimal shared-secret auth (hosted/public box) ──────────────
    # When EMPTY (default), auth is DISABLED → localhost dev and current behavior
    # are unchanged. When set (in the Oracle VM's backend/.env), the websocket
    # (?token=…) and the sensitive REST endpoints (Authorization: Bearer /
    # X-Companion-Token) require this token. See app/api/auth.py.
    COMPANION_SHARED_TOKEN: str = ""

    # ── Clerk identity (Phase auth) ───────────────────────────────────────────
    # Obtain these from https://dashboard.clerk.com → API Keys.
    # CLERK_PUBLISHABLE_KEY: pk_live_... or pk_test_...
    # CLERK_JWKS_URL: https://<frontend-api>.clerk.accounts.dev/.well-known/jwks.json
    # CLERK_ISSUER: https://<frontend-api>.clerk.accounts.dev (no trailing slash)
    # CLERK_AUTHORIZED_PARTY: leave empty to skip azp check (recommended for
    #   desktop PKCE flows where the 'azp' claim is not consistently set).
    CLERK_PUBLISHABLE_KEY: str = ""
    CLERK_JWKS_URL: str = ""
    CLERK_ISSUER: str = ""
    CLERK_AUTHORIZED_PARTY: str = ""

    # ── App-session JWT (minted by us after Clerk verification) ──────────────
    # JWT_SECRET_KEY: long random string — generate with:
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TTL_MINUTES: int = 30
    JWT_REFRESH_TTL_DAYS: int = 30

    # ── Auth kill-switch ──────────────────────────────────────────────────────
    # When False (default): /ws and REST accept ANY valid token OR no token at
    # all (preserves today's open behavior). Flip True in the VM .env after
    # verifying the full Clerk→desktop flow end-to-end.
    AUTH_REQUIRED: bool = False

    # ── Multi-provider API keys (additive; empty = provider unavailable) ──────
    # These seed the runtime provider config as DEFAULTS only. The in-app
    # Settings page writes to backend/data/runtime_providers.json which overrides
    # these at runtime without a restart. Leaving them empty keeps today's
    # Google-only behavior exactly.
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    ASSEMBLYAI_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""

    # Master revert switch for the multi-provider runtime layer. When False, the
    # in-app Settings JSON is ignored entirely and ALL provider/key/STT resolution
    # falls back to the .env values below — i.e. exact pre-multi-provider behavior.
    # Flip to false via env if anything misbehaves; no code change needed.
    PROVIDER_RUNTIME_OVERRIDE_ENABLED: bool = True

    # Phase G — per-session BYOK. When True, a desktop client may send a
    # PROVIDER_CONFIG message right after CONNECTION_ESTABLISHED carrying its own
    # keys + slot/model + google_backend choices. Those are scoped to that one
    # websocket session (via a ContextVar overlay in runtime_config) and never
    # written to the global runtime_providers.json — so concurrent testers with
    # DIFFERENT keys don't overwrite each other. When False, PROVIDER_CONFIG is
    # ignored and resolution is exactly the global-JSON/.env path (full revert).
    PER_SESSION_PROVIDER_OVERRIDE_ENABLED: bool = True

    # ── Per-task-slot provider/model defaults ────────────────────────────────
    # Default to the current Google values so an empty runtime config behaves
    # identically to before. Live Voice is Google-only this release.
    LIVE_VOICE_PROVIDER: str = "google"
    LIVE_VOICE_MODEL: str = DEFAULT_GEMINI_LIVE_MODEL
    REASONING_PROVIDER: str = "google"
    REASONING_MODEL: str = "gemini-2.5-pro"
    FAST_TEXT_PROVIDER: str = "google"
    FAST_TEXT_MODEL: str = DEFAULT_GEMINI_FLASH_MODEL
    VISION_PROVIDER: str = "google"
    VISION_MODEL: str = "gemini-2.5-flash"
    # STT provider default mirrors the existing TRANSCRIPTION_PROVIDER below.
    # runtime_config resolves stt provider from STT_PROVIDER → TRANSCRIPTION_PROVIDER.
    STT_PROVIDER: str = ""
    STT_MODEL: str = ""

    GEMINI_MODEL: str = DEFAULT_GEMINI_LIVE_MODEL
    GEMINI_MODEL_FALLBACK: str = DEFAULT_GEMINI_FALLBACK_MODEL

    # Live API model IDs differ between backends, so the AI Studio (Gemini API)
    # Live models are separate from the Vertex ones above. Verified May 2026 from
    # https://ai.google.dev/gemini-api/docs/models — native-audio preview + a
    # newer Gemini-3 Live model as fallback. Override via .env if Google renames
    # them (no code change needed).
    GEMINI_LIVE_MODEL_AISTUDIO: str = "gemini-2.5-flash-native-audio-preview-12-2025"
    GEMINI_LIVE_FALLBACK_AISTUDIO: str = "gemini-3.1-flash-live-preview"
    GEMINI_LIVE_VOICE_NAME: str = "Aoede"
    GEMINI_LIVE_LANGUAGE_CODE: str = "en-US"
    GEMINI_LIVE_ENABLE_AFFECTIVE_DIALOG: bool = False
    
    # Vertex AI specific settings
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    GOOGLE_GENAI_USE_VERTEXAI: bool = False
    
    # Advanced capabilities
    ENABLE_AFFECTIVE_DIALOG: bool = False
   
    # Speaker Recognition Configuration
    SPEAKER_RECOGNITION_ENABLED: bool = True
    RESEMBLYZER_ENABLED: bool = False
    WESPEAKER_ENABLED: bool = False
    SPEAKER_SIMILARITY_THRESHOLD: float = 0.60
    SPEAKER_VAD_AGGRESSIVENESS: int = 1
    SPEAKER_MIN_SEGMENT_DURATION: float = 1.0
    SPEAKER_ENROLLMENT_OPTIONAL: bool = True
    AUTO_SPEAKER_MODE: str = "conservative"
    ALLOW_UNKNOWN_SPEAKER: bool = True
    USER_VERIFY_THRESHOLD: float = 0.55
    USER_CONTINUATION_THRESHOLD: float = 0.45
    USER_CONTINUATION_WINDOW_SECONDS: float = 30.0
    COUNTERPARTY_REJECT_THRESHOLD: float = 0.30
    COUNTERPARTY_CLUSTER_THRESHOLD: float = 0.65
    COUNTERPARTY_STT_CONFIDENCE_MIN: float = 0.65
    MIN_TRANSCRIBE_DURATION_MS: int = 800
    MIN_CONTEXT_DURATION_MS: int = 800
    ENROLLMENT_MIN_DB: float = -35.0
    ENROLLMENT_EMBED_WINDOW_SECONDS: float = 2.0
    ENROLLMENT_EMBED_MAX_WINDOWS: int = 1
    ENROLLMENT_EMBED_TIMEOUT_SECONDS: float = 180.0
    ENROLLMENT_SPEECH_FRAME_MS: float = 30.0
    ENROLLMENT_SPEECH_FRAME_RMS_THRESHOLD: float = 0.004
    ENROLLMENT_SPEECH_HANGOVER_FRAMES: int = 6
    TRANSCRIPTION_PROVIDER: str = "google_stt"
    BROWSER_VAD_PROVIDER: str = "webrtc_wasm"
    GOOGLE_STT_REGION: str = "us"
    GOOGLE_STT_DIARIZATION_ENABLED: bool = True
    GOOGLE_STT_DIARIZATION_MIN_SPEAKERS: int = 1
    GOOGLE_STT_DIARIZATION_MAX_SPEAKERS: int = 3

    # Speech-to-Text configuration
    GOOGLE_STT_LOCATION: str = "us"
    GOOGLE_STT_RECOGNIZER: str = "_"
    GOOGLE_STT_MODEL: str = DEFAULT_GOOGLE_STT_MODEL
    GOOGLE_STT_LANGUAGE_CODES: str = DEFAULT_GOOGLE_STT_LANGUAGE_CODES
    GOOGLE_STT_HINT_PHRASES: str = ""   # removed — no hardcoded domain keywords
    GOOGLE_STT_HINT_BOOST: float = DEFAULT_GOOGLE_STT_HINT_BOOST  # stays 0.0 = disabled
    DEEPGRAM_API_KEY: str = ""
    DEEPGRAM_API_BASE_URL: str = "https://api.deepgram.com/v1/listen"
    DEEPGRAM_MODEL: str = "nova-3"
    DEEPGRAM_LANGUAGE_CODES: str = DEFAULT_GOOGLE_STT_LANGUAGE_CODES
    DEEPGRAM_DIARIZATION_ENABLED: bool = False
    DEEPGRAM_UTTERANCE_SPLIT: float = 0.45
    # Deepgram streaming endpointing: ms of AUDIO SILENCE before the stream fires
    # speech_final. This alone is unreliable with a noisy mic (headphone mic that
    # also plays the call → never truly silent), so we ALSO use utterance_end_ms
    # below (word-timing based, ignores non-speech noise) as the primary turn
    # boundary. Endpointing stays moderate so clean pauses still finalize quickly.
    # ~1s turn-end (user preference). Lines ALSO break immediately at sentence
    # boundaries (. ? !) in companion_runtime, so this 1000ms only governs when a
    # turn that did NOT end in punctuation finalizes — it won't over-merge.
    DEEPGRAM_STREAM_ENDPOINTING_MS: int = 1000
    # Word-gap (ms) after which Deepgram emits an UtteranceEnd message → we flush
    # the current turn. NOTE: Deepgram REQUIRES >= 1000 — any lower value is ignored
    # (the param isn't sent, disabling UtteranceEnd). Keep at 1000 to honor the ~1s
    # turn-end. Set 0 to fully disable. Requires interim_results=true (always sent).
    DEEPGRAM_UTTERANCE_END_MS: int = 1000
    DEEPGRAM_STREAM_LANGUAGE: str = "en-US"
    DEEPGRAM_STREAM_KEEPALIVE_SECONDS: float = 3.0

    # ── Multilanguage adaptation (reversible feature flag) ───────────────────
    # When False (default), all language code paths behave exactly as before.
    # Flip to True via env (MULTILANG_ENABLED=true) to enable:
    #   - Deepgram language=multi code-switching
    #   - Per-source / per-session pinned language profiles
    #   - Gemini Live native-audio auto language switching (omit language_code)
    #   - Response-language-driven prompt instructions
    #   - Pro advice translation wrap (non-English → English → answer → back)
    MULTILANG_ENABLED: bool = True
    # Profile applied when the flag is ON and the user hasn't picked one:
    #   "auto_multi" → language=multi (en,es,fr,de,hi,it,ja,nl,ru,pt)
    #   "pinned:<bcp47>" → monolingual stream (use for gu-IN, ta-IN, etc.)
    LANGUAGE_PROFILE_DEFAULT: str = "auto_multi"
    # Languages covered by Deepgram Nova-3 language=multi (per official docs)
    DEEPGRAM_MULTI_LANGUAGES: str = "en,es,fr,de,hi,it,ja,nl,ru,pt"
    # Pinned monolingual codes we explicitly surface in the UI (must include the
    # must-haves: English, Hindi, Gujarati). User can pick from a longer list.
    LANGUAGE_PROFILE_PINNED_CHOICES: str = "en-US,hi-IN,gu-IN,es-US,fr-FR,de-DE,ja-JP,zh-CN,ar"
    # Pro-advice translation: which lightweight model handles translate calls.
    TRANSLATION_MODEL: str = "gemini-2.5-flash"
    TRANSLATION_TIMEOUT_SECONDS: float = 2.5
    TRANSLATION_CACHE_MAX_ENTRIES: int = 500

    # ── ASK_AI native audio path (reversible feature flag) ──────────────────
    # When False (default), the existing transcribe-then-text flow is used:
    #   ASK_AI_PCM → buffered → Flash WAV transcription → text via send_client_content.
    # When True, in addition to the above, ASK_AI_PCM chunks are ALSO streamed
    # to Gemini Live via send_realtime_input(audio=) with activity_start/end
    # markers (we have automatic_activity_detection=disabled, so manual
    # markers are required). The Flash-transcribed text is still sent as the
    # final turn-completer — belt-and-suspenders so a failure on either lane
    # doesn't kill the ask. Easy revert: set ASK_AI_NATIVE_AUDIO=false.
    ASK_AI_NATIVE_AUDIO: bool = True
    ASK_AI_SUPPRESS_NATIVE_TRANSCRIPTION: bool = True
    ASK_AI_LOCAL_MIC_SUPPRESS_GRACE_SECONDS: float = 1.25
    AI_VOICE_LEAK_GRACE_SECONDS: float = 8.0
    AI_VOICE_LEAK_STRICT_POST_PLAYBACK_SECONDS: float = 2.0
    AI_VOICE_LEAK_SHORT_WORD_LIMIT: int = 3
    STT_GLOBAL_CONCURRENCY: int = 8
    STT_MAX_RETRIES: int = 2
    STT_BASE_BACKOFF_MS: int = 300
    STT_MAX_BACKOFF_MS: int = 4000
    ASK_AI_BATCH_TRANSCRIBE_TIMEOUT_SECONDS: float = 6.0
    TEXT_EXTRACTION_TIMEOUT_SECONDS: float = 6.0
    GEMINI_PRECONNECT_WAIT_SECONDS: float = 4.0
    STT_PROBE_TIMEOUT_SECONDS: float = 8.0
    # Increased to handle gRPC cold-start: first call after a new connection can
    # take 12-15 s while TLS + HTTP/2 establishment completes. Subsequent calls
    # on the warm connection are 2-4 s.
    STT_RPC_TIMEOUT_SECONDS: float = 18.0
    STT_END_TO_END_TIMEOUT_SECONDS: float = 28.0
    STARTUP_PROBE_TIMEOUT_SECONDS: float = 12.0
    RESEARCH_GLOBAL_CONCURRENCY: int = 2
    RESEARCH_MAX_RETRIES: int = 3
    RESEARCH_BASE_BACKOFF_MS: int = 1000
    RESEARCH_MAX_BACKOFF_MS: int = 12000

    # Azure speaker verification
    AZURE_SPEAKER_VERIFICATION_ENABLED: bool = False
    AZURE_SPEAKER_SUBSCRIPTION_KEY: str = ""
    AZURE_SPEAKER_REGION: str = "eastus"
    AZURE_SPEAKER_API_VERSION: str = "2024-02-15-preview"
    AZURE_SPEAKER_TIMEOUT_SECONDS: float = 20.0
    AZURE_SPEAKER_MIN_VERIFICATION_SECONDS: float = 3.0
    AZURE_ENROLLMENT_MIN_EFFECTIVE_SPEECH_SECONDS: float = 15.0
    USER_CONTRADICTION_THRESHOLD: float = 0.42
    USER_REBIND_MARGIN: float = 0.10
    SPEAKER_RECHECK_WINDOW_SECONDS: float = 45.0

    # SpeechBrain speaker verification
    SPEECHBRAIN_ENABLED: bool = False
    SPEECHBRAIN_DEVICE: str = "cpu"
    SPEECHBRAIN_MIN_BIND_SECONDS: float = 1.5
    SPEECHBRAIN_ACCEPT_THRESHOLD: float = 0.55
    SPEECHBRAIN_RECHECK_THRESHOLD: float = 0.25
    SPEECHBRAIN_AMBIGUOUS_LOW: float = 0.10
    SPEECHBRAIN_AMBIGUOUS_HIGH: float = 0.53
    SPEECHBRAIN_ENROLLMENT_TIMEOUT_SECONDS: float = 90.0
    SPEECHBRAIN_ENROLLMENT_MIN_EFFECTIVE_SPEECH_SECONDS: float = 6.0
    SPEECHBRAIN_ENROLLMENT_STABILITY_THRESHOLD: float = 0.65
    SESSION_RESUME_GRACE_SECONDS: int = 300
    SESSION_DB_PATH: str = "data/negotiation_sessions.db"
    TRANSCRIPT_HISTORY_LIMIT: int = 200
    RESEARCH_HISTORY_LIMIT: int = 100
    VISION_FRAME_INTERVAL_SECONDS: float = 2.0
    VISION_FRAME_MAX_WIDTH: int = 960
    VISION_ENABLED: bool = True

    # Continuous Pro Vision Analysis
    # Frontend captures at VISION_LIVE_FPS; backend filters by scene diff before calling Pro.
    VISION_LIVE_FPS: float = 1.0                  # target capture rate (frontend setting reference)
    VISION_PRO_ENABLED: bool = True               # enable scene analysis
    VISION_ANALYSIS_MODEL: str = "gemini-2.5-flash"  # model for vision frame analysis
    VISION_PRO_COOLDOWN_SECONDS: float = 3.0      # min seconds between Pro calls
    VISION_PRO_MIN_FRAMES: int = 2                # min frames to buffer before calling Pro
    VISION_PRO_MAX_FRAMES: int = 4                # max frames to send per Pro call
    VISION_FRAME_DIFF_THRESHOLD: float = 0.15     # scene-change threshold (0–1; 0.15 = 15%)
    VISION_OBS_MAX_HISTORY: int = 20              # max vision observations kept in session
    VISION_OBS_STALENESS_SECONDS: float = 30.0    # lowered from 60s — use only fresh observations
    VISION_PRO_LIVE_COOLDOWN_SECONDS: float = 3.0 # lowered from 8s — same rate as non-live so vision is always fresh when user holds orb
    VISION_LIVE_SEND_INTERVAL_SECONDS: float = 0.75
    VISION_INTEL_SEND_INTERVAL_SECONDS: float = 2.0
    SUPPORTED_AUTO_SPEAKER_LANGUAGES: str = DEFAULT_SUPPORTED_AUTO_SPEAKER_LANGUAGES

    # PerfectListener Configuration
    PERFECT_LISTENER_ENABLED: bool = False
    PERFECT_LISTENER_FALLBACK: bool = True
    PYANNOTE_MIN_DURATION_ON: float = 0.25
    PYANNOTE_MIN_DURATION_OFF: float = 0.5
    CONVTASNET_ENABLED: bool = True
    WESPEAKER_THRESHOLD: float = 0.70
    PYANNOTE_EMBEDDING_THRESHOLD: float = 0.70
    CLUSTERING_ENABLED: bool = True
    HF_TOKEN: str = ""
    
    # Heavy ML Components (disable for 2-speaker scenarios)
    ENABLE_OVERLAP_DETECTION: bool = False
    ENABLE_SPEECH_SEPARATION: bool = False
    
    # Credentials path
    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    
    CORS_ORIGINS: str = "http://localhost:3000"
    LOG_LEVEL: str = "INFO"
    SESSION_TTL_SECONDS: int = 3600
    SPEAKER_DEBUG_LOG_ENABLED: bool = True
    SPEAKER_DEBUG_LOG_PATH: str = "data/logs/speaker_debug.log"
    CONVERSATION_AUDIT_LOG_ENABLED: bool = True
    CONVERSATION_AUDIT_LOG_PATH: str = "data/logs/copilot_conversation_audit.jsonl"
    EVAL_MODE_ENABLED: bool = False
    EVAL_REPORT_DIR: str = "data/eval_reports"
    AUDIO_EVAL_FIXTURE_DIR: str = "evals/audio_fixtures"
    AUDIO_EVAL_REPORT_DIR: str = "data/audio_eval_reports"
    EVAL_JUDGE_MODEL: str = DEFAULT_GEMINI_FLASH_MODEL

    # Pro-tier advice generation: used by handle_ask_advice + handle_user_addressing_ai
    # to pre-compute the exact tactical answer before the live audio model speaks.
    # Pro is stronger at strategic reasoning, constraint following, and anti-hallucination.
    ADVICE_GENERATION_MODEL: str = "gemini-2.5-pro"
    ADVICE_GENERATION_TEMPERATURE: float = 0.15
    ADVICE_GENERATION_MAX_TOKENS: int = 4096
    ADVICE_GENERATION_ENABLED: bool = True
    ADVICE_GENERATION_TIMEOUT_SECONDS: float = 3.0

    # ── Next-move cache (reversible feature flag) ───────────────────────────
    # Background-precomputed "what should I do right now" recommendation so
    # vague private asks ("What now?", "Trap?", "Accept?") resolve from cache
    # without waiting for synchronous Pro reasoning. Cache is injected into
    # the pre-query brief during hold-to-ask; handle_ask_advice Pro pre-flight
    # is untouched (the cache only changes the *input* to Live, not the path).
    NEXT_MOVE_CACHE_ENABLED: bool = True
    NEXT_MOVE_FAST_MODEL: str = "gemini-2.5-flash"
    NEXT_MOVE_PRO_UPGRADE_ENABLED: bool = True
    NEXT_MOVE_MAX_AGE_SECONDS: float = 20.0
    NEXT_MOVE_BACKGROUND_DEBOUNCE_MS: int = 500
    NEXT_MOVE_FAST_TIMEOUT_SECONDS: float = 4.0
    NEXT_MOVE_PRO_TIMEOUT_SECONDS: float = 8.0
    # Comma-separated tokens (lowercased, substring-matched on whitespace-normalized
    # ask text) used by classify_ask() to route short asks to the cache.
    NEXT_MOVE_VAGUE_TOKENS: str = (
        "what now,say what,trap,accept,can i accept,trade what,protect what,"
        "read this,best counter,risk,summarize,what next,now what,next move"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def google_stt_language_codes_list(self) -> list[str]:
        return [code.strip() for code in self.GOOGLE_STT_LANGUAGE_CODES.split(",") if code.strip()]

    @property
    def google_stt_hint_phrases_list(self) -> list[str]:
        # Returns empty — hardcoded hint phrases removed; session-dynamic phrases still used
        return []

    @property
    def deepgram_language_codes_list(self) -> list[str]:
        return [code.strip() for code in self.DEEPGRAM_LANGUAGE_CODES.split(",") if code.strip()]

    @property
    def transcription_language_codes_list(self) -> list[str]:
        if self.TRANSCRIPTION_PROVIDER == "deepgram":
            return self.deepgram_language_codes_list
        return self.google_stt_language_codes_list

    @property
    def supported_auto_speaker_languages_list(self) -> list[str]:
        return [code.strip() for code in self.SUPPORTED_AUTO_SPEAKER_LANGUAGES.split(",") if code.strip()]

    @property
    def next_move_vague_tokens_list(self) -> list[str]:
        return [t.strip().lower() for t in self.NEXT_MOVE_VAGUE_TOKENS.split(",") if t.strip()]

    @property
    def deepgram_multi_languages_list(self) -> list[str]:
        return [code.strip().lower() for code in self.DEEPGRAM_MULTI_LANGUAGES.split(",") if code.strip()]

    @property
    def language_profile_pinned_choices_list(self) -> list[str]:
        return [code.strip() for code in self.LANGUAGE_PROFILE_PINNED_CHOICES.split(",") if code.strip()]

    def resolve_deepgram_language(self, profile: str | None, per_source: str | None = None) -> str:
        """Map a language profile (and optional per-source override) to a Deepgram language param.

        Returns a string suitable for Deepgram's ?language= query param. Falls back to
        DEEPGRAM_STREAM_LANGUAGE whenever the feature flag is off or input is malformed
        so legacy behavior is preserved.
        """
        if not self.MULTILANG_ENABLED:
            return self.DEEPGRAM_STREAM_LANGUAGE or "en-US"
        candidate = (per_source or profile or self.LANGUAGE_PROFILE_DEFAULT or "").strip()
        if not candidate:
            return self.DEEPGRAM_STREAM_LANGUAGE or "en-US"
        if candidate == "auto_multi":
            return "multi"
        if candidate.startswith("pinned:"):
            code = candidate.split(":", 1)[1].strip()
            return code or (self.DEEPGRAM_STREAM_LANGUAGE or "en-US")
        # Treat bare BCP-47 as a pinned monolingual stream.
        return candidate
    
    def _effective_use_vertex(self) -> bool:
        """The EFFECTIVE Google backend (Vertex vs AI Studio), honoring a runtime
        Settings toggle when present, else the env flag. Model qualification below
        must use THIS (not the raw env flag) so the `google/` prefix always matches
        the client's actual auth mode. Lazy import avoids a config↔providers cycle.
        """
        try:
            from app.providers import runtime_config
            return runtime_config.google_use_vertex()
        except Exception:
            return self.GOOGLE_GENAI_USE_VERTEXAI

    @property
    def effective_model(self) -> str:
        """Return model name with google/ prefix for Vertex AI."""
        return qualify_model_name(self.GEMINI_MODEL, self._effective_use_vertex())

    @property
    def effective_fallback_model(self) -> str:
        """Return fallback model name with google/ prefix for Vertex AI."""
        return qualify_model_name(self.GEMINI_MODEL_FALLBACK, self._effective_use_vertex())

    @property
    def effective_flash_model(self) -> str:
        """Return reasoning model name with google/ prefix for Vertex AI.

        Note: despite the historical 'flash' name, this property returns the
        background reasoning model (gemini-2.5-pro by default) used for
        extraction, research, and advice. Live audio still uses Flash.
        """
        return qualify_model_name(DEFAULT_GEMINI_FLASH_MODEL, self._effective_use_vertex())

    @property
    def effective_advice_model(self) -> str:
        """Return Pro advice generation model name with google/ prefix for Vertex AI."""
        return qualify_model_name(self.ADVICE_GENERATION_MODEL, self._effective_use_vertex())

    @property
    def effective_vision_model(self) -> str:
        """Return vision analysis model name with google/ prefix for Vertex AI."""
        return qualify_model_name(self.VISION_ANALYSIS_MODEL, self._effective_use_vertex())

    class Config:
        env_file = ".env"
    
    def validate_config(self) -> None:
        """
        Validate configuration parameters at startup.
        Logs warnings for invalid values.
        """
        # Validate thresholds are in [0.0, 1.0] range
        thresholds = {
            "SPEAKER_SIMILARITY_THRESHOLD": self.SPEAKER_SIMILARITY_THRESHOLD,
            "WESPEAKER_THRESHOLD": self.WESPEAKER_THRESHOLD,
            "PYANNOTE_EMBEDDING_THRESHOLD": self.PYANNOTE_EMBEDDING_THRESHOLD,
            "USER_VERIFY_THRESHOLD": self.USER_VERIFY_THRESHOLD,
            "USER_CONTINUATION_THRESHOLD": self.USER_CONTINUATION_THRESHOLD,
            "COUNTERPARTY_REJECT_THRESHOLD": self.COUNTERPARTY_REJECT_THRESHOLD,
            "COUNTERPARTY_CLUSTER_THRESHOLD": self.COUNTERPARTY_CLUSTER_THRESHOLD,
            "COUNTERPARTY_STT_CONFIDENCE_MIN": self.COUNTERPARTY_STT_CONFIDENCE_MIN,
        }
        
        for name, value in thresholds.items():
            if not (0.0 <= value <= 1.0):
                logger.warning(f"Invalid {name}={value}, must be in [0.0, 1.0]")
        
        # Validate durations are positive
        durations = {
            "PYANNOTE_MIN_DURATION_ON": self.PYANNOTE_MIN_DURATION_ON,
            "PYANNOTE_MIN_DURATION_OFF": self.PYANNOTE_MIN_DURATION_OFF,
            "SPEAKER_MIN_SEGMENT_DURATION": self.SPEAKER_MIN_SEGMENT_DURATION,
            "MIN_TRANSCRIBE_DURATION_MS": self.MIN_TRANSCRIBE_DURATION_MS,
            "MIN_CONTEXT_DURATION_MS": self.MIN_CONTEXT_DURATION_MS,
            "AZURE_SPEAKER_MIN_VERIFICATION_SECONDS": self.AZURE_SPEAKER_MIN_VERIFICATION_SECONDS,
            "AZURE_ENROLLMENT_MIN_EFFECTIVE_SPEECH_SECONDS": self.AZURE_ENROLLMENT_MIN_EFFECTIVE_SPEECH_SECONDS,
            "SPEAKER_RECHECK_WINDOW_SECONDS": self.SPEAKER_RECHECK_WINDOW_SECONDS,
            "SPEECHBRAIN_MIN_BIND_SECONDS": self.SPEECHBRAIN_MIN_BIND_SECONDS,
            "SPEECHBRAIN_ENROLLMENT_TIMEOUT_SECONDS": self.SPEECHBRAIN_ENROLLMENT_TIMEOUT_SECONDS,
            "SPEECHBRAIN_ENROLLMENT_MIN_EFFECTIVE_SPEECH_SECONDS": self.SPEECHBRAIN_ENROLLMENT_MIN_EFFECTIVE_SPEECH_SECONDS,
        }
        
        for name, value in durations.items():
            if value <= 0:
                logger.warning(f"Invalid {name}={value}, must be positive")

        if self.AUTO_SPEAKER_MODE not in {"conservative"}:
            logger.warning(f"Invalid AUTO_SPEAKER_MODE={self.AUTO_SPEAKER_MODE}, expected 'conservative'")

        if self.TRANSCRIPTION_PROVIDER not in {"google_stt", "deepgram"}:
            logger.warning(
                f"Invalid TRANSCRIPTION_PROVIDER={self.TRANSCRIPTION_PROVIDER}, expected 'google_stt' or 'deepgram'"
            )

        if self.BROWSER_VAD_PROVIDER not in {"webrtc_wasm"}:
            logger.warning(
                f"Invalid BROWSER_VAD_PROVIDER={self.BROWSER_VAD_PROVIDER}, expected 'webrtc_wasm'"
            )

        if self.TRANSCRIPTION_PROVIDER == "deepgram" and not self.DEEPGRAM_API_KEY:
            logger.warning(
                "TRANSCRIPTION_PROVIDER=deepgram but DEEPGRAM_API_KEY is not set. "
                "Deepgram STT requests will fail until the API key is configured."
            )

        if self.DEEPGRAM_UTTERANCE_SPLIT <= 0:
            logger.warning(
                "Invalid DEEPGRAM_UTTERANCE_SPLIT=%s, must be positive",
                self.DEEPGRAM_UTTERANCE_SPLIT,
            )

        if not (0.0 <= self.SPEECHBRAIN_ACCEPT_THRESHOLD <= 1.0):
            logger.warning("Invalid SPEECHBRAIN_ACCEPT_THRESHOLD=%s, must be in [0.0, 1.0]", self.SPEECHBRAIN_ACCEPT_THRESHOLD)
        if not (0.0 <= self.SPEECHBRAIN_RECHECK_THRESHOLD <= 1.0):
            logger.warning("Invalid SPEECHBRAIN_RECHECK_THRESHOLD=%s, must be in [0.0, 1.0]", self.SPEECHBRAIN_RECHECK_THRESHOLD)
        if not (0.0 <= self.SPEECHBRAIN_AMBIGUOUS_LOW <= 1.0):
            logger.warning("Invalid SPEECHBRAIN_AMBIGUOUS_LOW=%s, must be in [0.0, 1.0]", self.SPEECHBRAIN_AMBIGUOUS_LOW)
        if not (0.0 <= self.SPEECHBRAIN_AMBIGUOUS_HIGH <= 1.0):
            logger.warning("Invalid SPEECHBRAIN_AMBIGUOUS_HIGH=%s, must be in [0.0, 1.0]", self.SPEECHBRAIN_AMBIGUOUS_HIGH)
        if self.SPEECHBRAIN_AMBIGUOUS_LOW > self.SPEECHBRAIN_AMBIGUOUS_HIGH:
            logger.warning(
                "Invalid SpeechBrain ambiguity band: low=%s high=%s",
                self.SPEECHBRAIN_AMBIGUOUS_LOW,
                self.SPEECHBRAIN_AMBIGUOUS_HIGH,
            )
        if not (0.0 <= self.SPEECHBRAIN_ENROLLMENT_STABILITY_THRESHOLD <= 1.0):
            logger.warning(
                "Invalid SPEECHBRAIN_ENROLLMENT_STABILITY_THRESHOLD=%s, must be in [0.0, 1.0]",
                self.SPEECHBRAIN_ENROLLMENT_STABILITY_THRESHOLD,
            )
        
        # Validate HF_TOKEN is set if PERFECT_LISTENER_ENABLED is true
        if self.PERFECT_LISTENER_ENABLED and not self.HF_TOKEN:
            logger.warning(
                "PERFECT_LISTENER_ENABLED=true but HF_TOKEN is not set. "
                "Pyannote models require HuggingFace authentication. "
                "Set HF_TOKEN environment variable or disable PERFECT_LISTENER_ENABLED."
            )

settings = Config()

# Validate configuration at startup
settings.validate_config()
