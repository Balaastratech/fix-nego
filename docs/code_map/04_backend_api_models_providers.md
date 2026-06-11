I now have all the information needed. Here is the detailed reference map.

---

## backend/app/main.py (392 lines)

**Purpose**: FastAPI app entrypoint. Sets up monkeypatches for HF/pyannote compatibility, configures CORS, logging, correlation IDs; defines startup probes for STT/SpeechBrain capability detection and readiness; defines root Clerk-handshake redirect, health/readiness endpoints, session history REST endpoints, and frontend log relay; mounts the websocket, providers, and auth routers.

**Key items:**
- `main.py:27 _patched_hf_hub_download` - shim translating `use_auth_token` kwarg to `token` for huggingface_hub >=0.23 (pyannote compat)
- `main.py:60 _DESKTOP_ORIGINS` - list `["null", "file://", "app://.", "http://localhost:8000"]` added to CORS origins for Electron desktop renderer
- `main.py:71 _log_google_auth_context()` - logs Vertex config + resolved ADC identity at startup
- `main.py:106 _validate_runtime_configuration()` - raises RuntimeError if SpeechBrain enabled alongside conflicting speaker providers (Resemblyzer/WeSpeaker/Azure); warns on unsupported STT languages
- `main.py:138 async _run_capability_probes_in_background()` - probes STT (google_stt or deepgram) and SpeechBrain capability, populates `capability_registry`, calls `readiness.mark_ready()` and `connection_manager.broadcast_backend_ready()`
- `main.py:254 @app.on_event("startup") async def startup_event()` - initializes `session_store`, configures `auth_db` (must run AFTER session_store.initialize), schedules background capability probes
- `main.py:295 @app.get("/") async def clerk_root_handler(...)` - handles Clerk handshake (`__clerk_handshake`/`__clerk_db_jwt` query params), replays Set-Cookie headers, redirects to `/auth/login-page`
- `main.py:349 @app.get("/api/health") async def health_check()` - returns `{"status": "healthy"}`
- `main.py:353 @app.get("/health") async def health_check_root()` - same, root alias
- `main.py:357 @app.get("/api/ready") async def readiness_check()` - returns `readiness.snapshot()`
- `main.py:365 @app.get("/api/sessions", dependencies=[Depends(get_current_user)]) async def list_sessions(limit=20)` - lists persisted sessions
- `main.py:369 @app.get("/api/sessions/{session_id}", dependencies=[Depends(get_current_user)]) async def get_session_history(session_id)` - 404 if not found, else returns session bundle
- `main.py:378 @app.post("/api/log") async def log_frontend_message(request, payload=Body(...))` - relays frontend log messages into `frontend_logger`
- `main.py:386,389,392` - `app.include_router(websocket_router)`, `app.include_router(providers_router)`, `app.include_router(auth_router)`

**Gotchas:**
- The k2_fsa/speechbrain patch (`backend/app/utils/speechbrain_patch.patch_speechbrain_k2()`) is called FIRST, before any pyannote imports — ordering matters (main.py:14-15)
- `auth_db.configure()` must run AFTER `session_store.initialize()` (comment at main.py:270-271) since they share the SQLite DB file

---

## backend/app/config.py (568 lines)

**Purpose**: Single pydantic-settings `Config` class (`settings = Config()`) loading from `.env`, defining ALL runtime configuration: AI provider keys, auth, per-task-slot provider/model defaults, audio/STT/speaker-recognition tuning, multilanguage flags, ASK_AI native-audio flags, vision settings, eval/logging paths, and several `*_list` properties + `effective_*` model properties (Vertex `google/` prefix qualification via `app.ai_assets.qualify_model_name`). Ends with `validate_config()` which logs warnings for out-of-range values (called once at module import, `config.py:568`).

### Settings fields by category

**Core AI key (config.py:19)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| GEMINI_API_KEY | str | "" | Primary Google Gemini API key |

**Phase C shared-secret auth (config.py:26)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| COMPANION_SHARED_TOKEN | str | "" | When set, gates `/ws` (`?token=`) and sensitive REST via Bearer/X-Companion-Token; empty = auth disabled |

**Clerk identity (config.py:35-38)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| CLERK_PUBLISHABLE_KEY | str | "" | Clerk pk_live/pk_test key |
| CLERK_JWKS_URL | str | "" | Clerk JWKS endpoint for JWT verification |
| CLERK_ISSUER | str | "" | Clerk issuer URL (no trailing slash) |
| CLERK_AUTHORIZED_PARTY | str | "" | `azp` claim check; empty skips check (desktop PKCE) |

**App-session JWT (config.py:43-46)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| JWT_SECRET_KEY | str | "" | Secret for signing app-minted JWTs |
| JWT_ALGORITHM | str | "HS256" | JWT signing algorithm |
| JWT_ACCESS_TTL_MINUTES | int | 30 | Access token lifetime |
| JWT_REFRESH_TTL_DAYS | int | 30 | Refresh token lifetime |

**Auth kill-switch (config.py:52)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| AUTH_REQUIRED | bool | False | If False, /ws and REST accept any/no token (open dev mode) |

**Multi-provider API keys (config.py:59-65) — BYOK seeds**
| Field | Type | Default | Meaning |
|---|---|---|---|
| OPENAI_API_KEY | str | "" | OpenAI key |
| ANTHROPIC_API_KEY | str | "" | Anthropic key |
| GROQ_API_KEY | str | "" | Groq key |
| DEEPSEEK_API_KEY | str | "" | DeepSeek key |
| OPENROUTER_API_KEY | str | "" | OpenRouter key |
| ASSEMBLYAI_API_KEY | str | "" | AssemblyAI key |
| ELEVENLABS_API_KEY | str | "" | ElevenLabs key |

**Provider runtime overrides — feature flags (config.py:71, 80)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| PROVIDER_RUNTIME_OVERRIDE_ENABLED | bool | True | Master switch for `runtime_providers.json` overlay; False = pure .env behavior |
| PER_SESSION_PROVIDER_OVERRIDE_ENABLED | bool | True | Phase G — enables per-session BYOK via PROVIDER_CONFIG WS message |

**Per-task-slot provider/model defaults (config.py:85-96)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| LIVE_VOICE_PROVIDER | str | "google" | Provider for live voice slot (Google-only this release) |
| LIVE_VOICE_MODEL | str | DEFAULT_GEMINI_LIVE_MODEL | Live voice model id |
| REASONING_PROVIDER | str | "google" | Provider for reasoning slot |
| REASONING_MODEL | str | "gemini-2.5-pro" | Reasoning model id |
| FAST_TEXT_PROVIDER | str | "google" | Provider for fast-text slot |
| FAST_TEXT_MODEL | str | DEFAULT_GEMINI_FLASH_MODEL | Fast text model id |
| VISION_PROVIDER | str | "google" | Provider for vision slot |
| VISION_MODEL | str | "gemini-2.5-flash" | Vision model id |
| STT_PROVIDER | str | "" | STT provider override (falls back to TRANSCRIPTION_PROVIDER) |
| STT_MODEL | str | "" | STT model override |

**Gemini model defaults (config.py:98-110)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| GEMINI_MODEL | str | DEFAULT_GEMINI_LIVE_MODEL | Primary live model |
| GEMINI_MODEL_FALLBACK | str | DEFAULT_GEMINI_FALLBACK_MODEL | Fallback model |
| GEMINI_LIVE_MODEL_AISTUDIO | str | "gemini-2.5-flash-native-audio-preview-12-2025" | AI Studio Live model id (separate namespace from Vertex) |
| GEMINI_LIVE_FALLBACK_AISTUDIO | str | "gemini-3.1-flash-live-preview" | AI Studio Live fallback |
| GEMINI_LIVE_VOICE_NAME | str | "Aoede" | Live voice persona name |
| GEMINI_LIVE_LANGUAGE_CODE | str | "en-US" | Live language code |
| GEMINI_LIVE_ENABLE_AFFECTIVE_DIALOG | bool | False | Enable affective dialog on Live model |

**Vertex AI (config.py:113-115)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| GOOGLE_CLOUD_PROJECT | str | "" | GCP project id |
| GOOGLE_CLOUD_LOCATION | str | "us-central1" | GCP region |
| GOOGLE_GENAI_USE_VERTEXAI | bool | False | Env-level Vertex toggle (effective value resolved via runtime_config.google_use_vertex()) |

**Advanced capabilities (config.py:118)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| ENABLE_AFFECTIVE_DIALOG | bool | False | (legacy/general) affective dialog flag |

**Speaker recognition core (config.py:121-150)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| SPEAKER_RECOGNITION_ENABLED | bool | True | Master speaker recognition toggle |
| RESEMBLYZER_ENABLED | bool | False | Resemblyzer embedding provider |
| WESPEAKER_ENABLED | bool | False | WeSpeaker embedding provider |
| SPEAKER_SIMILARITY_THRESHOLD | float | 0.60 | General similarity threshold [0,1] |
| SPEAKER_VAD_AGGRESSIVENESS | int | 1 | VAD aggressiveness level |
| SPEAKER_MIN_SEGMENT_DURATION | float | 1.0 | Min segment length (s) |
| SPEAKER_ENROLLMENT_OPTIONAL | bool | True | Whether enrollment can be skipped |
| AUTO_SPEAKER_MODE | str | "conservative" | Only valid value validated is "conservative" |
| ALLOW_UNKNOWN_SPEAKER | bool | True | Allow "unknown" speaker label |
| USER_VERIFY_THRESHOLD | float | 0.55 | Threshold to verify USER speaker |
| USER_CONTINUATION_THRESHOLD | float | 0.45 | Threshold to continue attributing to USER |
| USER_CONTINUATION_WINDOW_SECONDS | float | 30.0 | Window for continuation logic |
| COUNTERPARTY_REJECT_THRESHOLD | float | 0.30 | Reject as counterparty below this |
| COUNTERPARTY_CLUSTER_THRESHOLD | float | 0.65 | Cluster counterparty embeddings threshold |
| COUNTERPARTY_STT_CONFIDENCE_MIN | float | 0.65 | Min STT confidence for counterparty attribution |
| MIN_TRANSCRIBE_DURATION_MS | int | 800 | Min audio duration to transcribe |
| MIN_CONTEXT_DURATION_MS | int | 800 | Min audio duration for context capture |
| ENROLLMENT_MIN_DB | float | -35.0 | Min dB level during enrollment |
| ENROLLMENT_EMBED_WINDOW_SECONDS | float | 2.0 | Embedding window length |
| ENROLLMENT_EMBED_MAX_WINDOWS | int | 1 | Max embedding windows captured |
| ENROLLMENT_EMBED_TIMEOUT_SECONDS | float | 180.0 | Enrollment timeout |
| ENROLLMENT_SPEECH_FRAME_MS | float | 30.0 | Frame size for speech detection during enrollment |
| ENROLLMENT_SPEECH_FRAME_RMS_THRESHOLD | float | 0.004 | RMS threshold for speech frame |
| ENROLLMENT_SPEECH_HANGOVER_FRAMES | int | 6 | Hangover frames after speech ends |

**Transcription provider/STT (config.py:145-180)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| TRANSCRIPTION_PROVIDER | str | "google_stt" | "google_stt" or "deepgram" (validated) |
| BROWSER_VAD_PROVIDER | str | "webrtc_wasm" | Browser-side VAD provider (validated, only "webrtc_wasm") |
| GOOGLE_STT_REGION | str | "us" | Google Cloud STT region |
| GOOGLE_STT_DIARIZATION_ENABLED | bool | True | Enable speaker diarization |
| GOOGLE_STT_DIARIZATION_MIN_SPEAKERS | int | 1 | Min diarization speakers |
| GOOGLE_STT_DIARIZATION_MAX_SPEAKERS | int | 3 | Max diarization speakers |
| GOOGLE_STT_LOCATION | str | "us" | Google STT API location |
| GOOGLE_STT_RECOGNIZER | str | "_" | Recognizer resource id |
| GOOGLE_STT_MODEL | str | DEFAULT_GOOGLE_STT_MODEL ("chirp_3") | STT model |
| GOOGLE_STT_LANGUAGE_CODES | str | DEFAULT_GOOGLE_STT_LANGUAGE_CODES ("en-US,hi-IN,es-US") | Comma-separated STT languages |
| GOOGLE_STT_HINT_PHRASES | str | "" | Removed/no-op — no hardcoded hint keywords |
| GOOGLE_STT_HINT_BOOST | float | 0.0 (DEFAULT_GOOGLE_STT_HINT_BOOST) | Hint boost (disabled, kept for compat) |
| DEEPGRAM_API_KEY | str | "" | Deepgram key |
| DEEPGRAM_API_BASE_URL | str | "https://api.deepgram.com/v1/listen" | Deepgram REST/streaming base |
| DEEPGRAM_MODEL | str | "nova-3" | Deepgram STT model |
| DEEPGRAM_LANGUAGE_CODES | str | DEFAULT_GOOGLE_STT_LANGUAGE_CODES | Deepgram language list |
| DEEPGRAM_DIARIZATION_ENABLED | bool | False | Deepgram diarization |
| DEEPGRAM_UTTERANCE_SPLIT | float | 0.45 | Utterance split threshold (must be >0, validated) |
| DEEPGRAM_STREAM_ENDPOINTING_MS | int | 1000 | Silence ms before speech_final fires |
| DEEPGRAM_UTTERANCE_END_MS | int | 1000 | Word-gap ms for UtteranceEnd (Deepgram requires >=1000) |
| DEEPGRAM_STREAM_LANGUAGE | str | "en-US" | Default Deepgram stream language |
| DEEPGRAM_STREAM_KEEPALIVE_SECONDS | float | 3.0 | Keepalive interval |

**Multilanguage adaptation — feature flag (config.py:190-203)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| MULTILANG_ENABLED | bool | True | Master flag: Deepgram multi-lang, per-source language profiles, Gemini auto language, response-language prompts, pro-advice translation wrap |
| LANGUAGE_PROFILE_DEFAULT | str | "auto_multi" | Default profile when user hasn't picked one ("auto_multi" or "pinned:<bcp47>") |
| DEEPGRAM_MULTI_LANGUAGES | str | "en,es,fr,de,hi,it,ja,nl,ru,pt" | Languages covered by Deepgram Nova-3 multi mode |
| LANGUAGE_PROFILE_PINNED_CHOICES | str | "en-US,hi-IN,gu-IN,es-US,fr-FR,de-DE,ja-JP,zh-CN,ar" | UI-selectable pinned monolingual codes |
| TRANSLATION_MODEL | str | "gemini-2.5-flash" | Model for pro-advice translation calls |
| TRANSLATION_TIMEOUT_SECONDS | float | 2.5 | Translation call timeout |
| TRANSLATION_CACHE_MAX_ENTRIES | int | 500 | Max cached translations |

**ASK_AI native audio path — feature flags (config.py:214-261)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| ASK_AI_NATIVE_AUDIO | bool | True | Stream ASK_AI_PCM directly to Gemini Live via send_realtime_input alongside transcribe-then-text path |
| ASK_AI_NATIVE_ONLY_TRANSCRIPTION | bool | True | Native Live model is sole transcriber of private ask (skips Deepgram/Google STT for the YOU bubble) |
| ASK_AI_SUPPRESS_NATIVE_TRANSCRIPTION | bool | False | Suppress native transcript publish (off by default given native-only ownership) |
| ASK_AI_TRANSCRIPT_SETTLE_SECONDS | float | 0.0 | Settle delay before repairing transcript |
| ASK_AI_ACTIVITY_END_DELAY_SECONDS | float | 0.4 | Delay between orb-release and sending activity_end to Gemini Live |
| ASK_AI_LOCAL_MIC_SUPPRESS_GRACE_SECONDS | float | 1.25 | Grace period suppressing local mic after ask |
| AI_VOICE_LEAK_GRACE_SECONDS | float | 8.0 | Grace period for AI voice leak detection |
| AI_VOICE_LEAK_STRICT_POST_PLAYBACK_SECONDS | float | 2.0 | Strict post-playback leak window |
| AI_VOICE_LEAK_SHORT_WORD_LIMIT | int | 3 | Word count limit for short-word leak heuristic |
| ASK_AI_BATCH_TRANSCRIBE_TIMEOUT_SECONDS | float | 6.0 | Timeout for batch ask transcription |

**STT/research concurrency & timeouts (config.py:242-259)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| STT_GLOBAL_CONCURRENCY | int | 8 | Global concurrent STT calls |
| STT_MAX_RETRIES | int | 2 | STT retry count |
| STT_BASE_BACKOFF_MS | int | 300 | STT retry base backoff |
| STT_MAX_BACKOFF_MS | int | 4000 | STT retry max backoff |
| TEXT_EXTRACTION_TIMEOUT_SECONDS | float | 6.0 | Text-extraction call timeout |
| GEMINI_PRECONNECT_WAIT_SECONDS | float | 4.0 | Wait for Live preconnect |
| STT_PROBE_TIMEOUT_SECONDS | float | 8.0 | STT capability probe timeout |
| STT_RPC_TIMEOUT_SECONDS | float | 18.0 | Per-RPC STT timeout (handles gRPC cold start) |
| STT_END_TO_END_TIMEOUT_SECONDS | float | 28.0 | End-to-end STT timeout |
| STARTUP_PROBE_TIMEOUT_SECONDS | float | 12.0 | Startup capability probe timeout |
| RESEARCH_GLOBAL_CONCURRENCY | int | 2 | Concurrent research calls |
| RESEARCH_MAX_RETRIES | int | 3 | Research retry count |
| RESEARCH_BASE_BACKOFF_MS | int | 1000 | Research retry base backoff |
| RESEARCH_MAX_BACKOFF_MS | int | 12000 | Research retry max backoff |

**Azure speaker verification (config.py:262-271)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| AZURE_SPEAKER_VERIFICATION_ENABLED | bool | False | Enable Azure speaker verification |
| AZURE_SPEAKER_SUBSCRIPTION_KEY | str | "" | Azure subscription key |
| AZURE_SPEAKER_REGION | str | "eastus" | Azure region |
| AZURE_SPEAKER_API_VERSION | str | "2024-02-15-preview" | Azure API version |
| AZURE_SPEAKER_TIMEOUT_SECONDS | float | 20.0 | Azure call timeout |
| AZURE_SPEAKER_MIN_VERIFICATION_SECONDS | float | 3.0 | Min audio for verification |
| AZURE_ENROLLMENT_MIN_EFFECTIVE_SPEECH_SECONDS | float | 15.0 | Min effective speech for enrollment |
| USER_CONTRADICTION_THRESHOLD | float | 0.42 | Threshold flagging user-id contradiction |
| USER_REBIND_MARGIN | float | 0.10 | Margin for rebinding user identity |
| SPEAKER_RECHECK_WINDOW_SECONDS | float | 45.0 | Recheck window |

**SpeechBrain speaker verification (config.py:274-283)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| SPEECHBRAIN_ENABLED | bool | False | Enable SpeechBrain as sole biometric provider (conflicts validated against Resemblyzer/WeSpeaker/Azure) |
| SPEECHBRAIN_DEVICE | str | "cpu" | Inference device |
| SPEECHBRAIN_MIN_BIND_SECONDS | float | 1.5 | Min audio to bind speaker |
| SPEECHBRAIN_ACCEPT_THRESHOLD | float | 0.55 | Accept threshold [0,1] |
| SPEECHBRAIN_RECHECK_THRESHOLD | float | 0.25 | Recheck threshold [0,1] |
| SPEECHBRAIN_AMBIGUOUS_LOW | float | 0.10 | Ambiguity band low [0,1] |
| SPEECHBRAIN_AMBIGUOUS_HIGH | float | 0.53 | Ambiguity band high [0,1], must be >= LOW |
| SPEECHBRAIN_ENROLLMENT_TIMEOUT_SECONDS | float | 90.0 | Enrollment timeout |
| SPEECHBRAIN_ENROLLMENT_MIN_EFFECTIVE_SPEECH_SECONDS | float | 6.0 | Min effective enrollment speech |
| SPEECHBRAIN_ENROLLMENT_STABILITY_THRESHOLD | float | 0.65 | Enrollment stability threshold [0,1] |

**Session/persistence/logging (config.py:284-337)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| SESSION_RESUME_GRACE_SECONDS | int | 300 | Grace window to resume disconnected sessions |
| SESSION_DB_PATH | str | "data/negotiation_sessions.db" | SQLite DB path |
| TRANSCRIPT_HISTORY_LIMIT | int | 200 | Max transcript turns retained |
| RESEARCH_HISTORY_LIMIT | int | 100 | Max research events retained |
| VISION_FRAME_INTERVAL_SECONDS | float | 2.0 | Vision frame capture interval |
| VISION_FRAME_MAX_WIDTH | int | 960 | Max vision frame width |
| VISION_ENABLED | bool | True | Master vision toggle |
| CORS_ORIGINS | str | "http://localhost:3000" | Comma-separated CORS origins |
| LOG_LEVEL | str | "INFO" | Logging level |
| SESSION_TTL_SECONDS | int | 3600 | Session TTL |
| SPEAKER_DEBUG_LOG_ENABLED | bool | True | Enable speaker debug log |
| SPEAKER_DEBUG_LOG_PATH | str | "data/logs/speaker_debug.log" | Speaker debug log path |
| CONVERSATION_AUDIT_LOG_ENABLED | bool | True | Enable conversation audit log |
| CONVERSATION_AUDIT_LOG_PATH | str | "data/logs/copilot_conversation_audit.jsonl" | Audit log path |
| EVAL_MODE_ENABLED | bool | False | Enable eval mode |
| EVAL_REPORT_DIR | str | "data/eval_reports" | Eval report dir |
| AUDIO_EVAL_FIXTURE_DIR | str | "evals/audio_fixtures" | Audio eval fixtures dir |
| AUDIO_EVAL_REPORT_DIR | str | "data/audio_eval_reports" | Audio eval report dir |
| EVAL_JUDGE_MODEL | str | DEFAULT_GEMINI_FLASH_MODEL | Model used as eval judge |

**Continuous Pro Vision Analysis (config.py:294-306)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| VISION_LIVE_FPS | float | 1.0 | Frontend capture rate reference |
| VISION_PRO_ENABLED | bool | True | Enable scene analysis |
| VISION_ANALYSIS_MODEL | str | "gemini-2.5-flash" | Model for vision frame analysis |
| VISION_PRO_COOLDOWN_SECONDS | float | 3.0 | Min seconds between Pro vision calls |
| VISION_PRO_MIN_FRAMES | int | 2 | Min buffered frames before Pro call |
| VISION_PRO_MAX_FRAMES | int | 4 | Max frames sent per Pro call |
| VISION_FRAME_DIFF_THRESHOLD | float | 0.15 | Scene-change threshold (0-1) |
| VISION_OBS_MAX_HISTORY | int | 20 | Max vision observations kept |
| VISION_OBS_STALENESS_SECONDS | float | 30.0 | Max age of usable vision observation (lowered from 60s) |
| VISION_PRO_LIVE_COOLDOWN_SECONDS | float | 3.0 | Live-mode Pro cooldown (lowered from 8s) |
| VISION_LIVE_SEND_INTERVAL_SECONDS | float | 0.75 | Interval for sending live vision frames |
| VISION_INTEL_SEND_INTERVAL_SECONDS | float | 2.0 | Interval for sending vision intel |
| SUPPORTED_AUTO_SPEAKER_LANGUAGES | str | DEFAULT_SUPPORTED_AUTO_SPEAKER_LANGUAGES ("en-US,hi-IN,gu-IN,es-US") | Languages allowed for auto-speaker mode |

**PerfectListener Configuration (config.py:309-321)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| PERFECT_LISTENER_ENABLED | bool | False | Enable PerfectListener pipeline (requires HF_TOKEN, validated) |
| PERFECT_LISTENER_FALLBACK | bool | True | Fall back gracefully if PerfectListener unavailable |
| PYANNOTE_MIN_DURATION_ON | float | 0.25 | Pyannote min "on" segment duration (must be >0) |
| PYANNOTE_MIN_DURATION_OFF | float | 0.5 | Pyannote min "off" gap duration (must be >0) |
| CONVTASNET_ENABLED | bool | True | Enable ConvTasNet speech separation |
| WESPEAKER_THRESHOLD | float | 0.70 | WeSpeaker threshold [0,1] |
| PYANNOTE_EMBEDDING_THRESHOLD | float | 0.70 | Pyannote embedding threshold [0,1] |
| CLUSTERING_ENABLED | bool | True | Enable speaker clustering |
| HF_TOKEN | str | "" | HuggingFace token (required if PERFECT_LISTENER_ENABLED) |

**Heavy ML toggles (config.py:320-321)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| ENABLE_OVERLAP_DETECTION | bool | False | Enable overlap detection (disable for 2-speaker scenarios) |
| ENABLE_SPEECH_SEPARATION | bool | False | Enable speech separation |

**Credentials (config.py:324)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| GOOGLE_APPLICATION_CREDENTIALS | str | "" | Path to GCP service account JSON |

**Pro-tier advice generation (config.py:342-346)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| ADVICE_GENERATION_MODEL | str | "gemini-2.5-pro" | Model for handle_ask_advice/handle_user_addressing_ai pre-compute |
| ADVICE_GENERATION_TEMPERATURE | float | 0.15 | Advice generation temperature |
| ADVICE_GENERATION_MAX_TOKENS | int | 4096 | Advice generation token cap |
| ADVICE_GENERATION_ENABLED | bool | True | Master toggle for Pro pre-compute |
| ADVICE_GENERATION_TIMEOUT_SECONDS | float | 3.0 | Advice generation timeout |

**Next-move cache — feature flag (config.py:354-366)**
| Field | Type | Default | Meaning |
|---|---|---|---|
| NEXT_MOVE_CACHE_ENABLED | bool | True | Background-precompute "what should I do now" cache |
| NEXT_MOVE_FAST_MODEL | str | "gemini-2.5-flash" | Fast model for cache refresh |
| NEXT_MOVE_PRO_UPGRADE_ENABLED | bool | True | Allow upgrading cache to Pro reasoning |
| NEXT_MOVE_MAX_AGE_SECONDS | float | 20.0 | Max cache age to be considered fresh |
| NEXT_MOVE_BACKGROUND_DEBOUNCE_MS | int | 500 | Debounce for background refresh |
| NEXT_MOVE_FAST_TIMEOUT_SECONDS | float | 4.0 | Fast model timeout |
| NEXT_MOVE_PRO_TIMEOUT_SECONDS | float | 8.0 | Pro model timeout |
| NEXT_MOVE_VAGUE_TOKENS | str | "what now,say what,trap,accept,..." | Comma-separated tokens for `classify_ask()` to route vague asks to cache |

**Properties / methods (not Settings fields):**
- `cors_origins_list` (config.py:369), `google_stt_language_codes_list` (373), `google_stt_hint_phrases_list` (377, always returns []), `deepgram_language_codes_list` (382), `transcription_language_codes_list` (386), `supported_auto_speaker_languages_list` (392), `next_move_vague_tokens_list` (396), `deepgram_multi_languages_list` (400), `language_profile_pinned_choices_list` (404)
- `resolve_deepgram_language(profile, per_source=None)` (config.py:407) - maps language profile → Deepgram `?language=` param, honors MULTILANG_ENABLED
- `_effective_use_vertex()` (config.py:427) - lazy-imports `runtime_config.google_use_vertex()`, falls back to `GOOGLE_GENAI_USE_VERTEXAI`
- `effective_model` / `effective_fallback_model` / `effective_flash_model` / `effective_advice_model` / `effective_vision_model` (config.py:440-467) - all apply `qualify_model_name(..., use_vertex)` to add `google/` prefix for Vertex
- `validate_config()` (config.py:472) - startup validation, logs warnings only (never raises except via `main._validate_runtime_configuration`)

---

## backend/app/ai_assets.py (1084 lines)

**Purpose**: Central repository of all AI prompts, system instructions, and live-model tunables. Imported by `config.py` for default model names. Contains the negotiation advisor's core system prompt (`ADVISOR_SYSTEM_PROMPT` / `UNIFIED_ADVISOR_SYSTEM_PROMPT`), prompt-builder functions for vision/audio extraction, market/person/company research, pre-query briefs, and intel blocks injected into the live Gemini session.

**Constants/defaults (top of file):**
- `ai_assets.py:7-21` - `DEFAULT_GEMINI_LIVE_MODEL`, `DEFAULT_GEMINI_FALLBACK_MODEL`, `DEFAULT_GEMINI_FLASH_MODEL`, `DEFAULT_GOOGLE_STT_MODEL`, `DEFAULT_GOOGLE_STT_LANGUAGE_CODES`, `DEFAULT_GOOGLE_STT_HINT_BOOST` (=0.0, hint phrases removed — caused STT hallucinations), `DEFAULT_SUPPORTED_AUTO_SPEAKER_LANGUAGES` (includes gu-IN added so multilang flag can pin to it without tripping startup probe)
- `ai_assets.py:23-35` - `LIVE_RESPONSE_MODALITIES=["AUDIO"]`, `LIVE_VOICE_NAME="Aoede"`, `LIVE_GENERATION_TEMPERATURE=0.3`, `LIVE_GENERATION_MAX_OUTPUT_TOKENS=8192` (NOTE comment: raised from 1024 because audio-token budget was clipping spoken answers mid-sentence), `LIVE_GENERATION_CANDIDATE_COUNT=1`, `LIVE_GENERATION_TOP_P=0.8`, `LIVE_GENERATION_TOP_K=20`, `LIVE_CONTEXT_WINDOW_TRIGGER_TOKENS=100_000`
- `ai_assets.py:37-48` - `RESPONSE_VALIDATOR_ALLOWED_FIRST_WORDS` - list of allowed sentence-starters (Ask/Say/Tell/Counter/Offer/Walk/Stay/Push/$)
- `ai_assets.py:49-68` - `RESPONSE_VALIDATOR_FORBIDDEN_FIRST_WORDS` - list of forbidden hedge-y starters (Given/You/The/It/Well/Since/Maybe/If/I think/etc.)
- `ai_assets.py:70-72` - `TACTICAL_RESPONSE_LANGUAGE_RULE` - one-line rule: answer tactical request in the response language if specified

**Major prompts/builders:**
- `ai_assets.py:74 VISION_EXTRACTION_PROMPT` - template for analyzing camera frames; returns strict JSON (scene_type, item, condition, defects_visible, document_text, prices_visible, terms_visible, body_language, scene_summary, confidence, advice_hint). Format args: `{n_frames}`, `{session_context}`, `{transcript_hint}`
- `ai_assets.py:118 LISTENER_UTTERANCE_TRANSCRIPTION_PROMPT` - generic verbatim transcription instruction (no labels/timestamps)
- `ai_assets.py:125 TEXT_EXTRACTION_PROMPT` - extracts negotiation context JSON from a labeled transcript (item, negotiation_type, prices, leverage_points, research_query, etc.) with attribution rules
- `ai_assets.py:158 EXTRACTION_PROMPT` - combined transcribe+diarize+extract prompt for live audio (returns JSON with `diarization` array, item/prices/leverage/research fields, "TOO GENERIC" research_query guard at line 200)
- `ai_assets.py:203 ADVISOR_SYSTEM_PROMPT` - the large (~280 line) negotiation commander system prompt:
  - Mode selection (COMMAND MODE vs ADVICE MODE) - lines 206-236
  - Question-answering precedence rules - lines 237-273
  - RULE 1-7: grounding/anti-hallucination, numeric specificity, number format (digits not words), exact term naming, strategic trade hierarchy, query constraint extraction, soft-signal vs confirmed offer, preserve user target, visual evidence authority - lines 278-394
  - Structured briefing field definitions - lines 401-440
  - COMMAND MODE / ADVICE MODE detailed output rules - lines 444-474
  - 5 worked EXAMPLES with WHY explanations (good/bad pairs covering specificity, anti-hallucination, trade hierarchy, constraint extraction, soft-signal classification) - lines 479-545; includes the "ITEM SPECIFICS RULE" anti-hallucination guard about not inventing user item specs (storage/condition/etc.)
- `ai_assets.py:548 qualify_model_name(model_name, use_vertex_ai)` - prepends `"google/"` if Vertex and not already prefixed; used by config.py `effective_*` properties
- `ai_assets.py:554 UNIFIED_ADVISOR_SYSTEM_PROMPT` - newer/simpler unified copilot prompt (question-first behavior, answer-shape rules for "what should I do" / factual / evaluation questions, grounding rules, item-specifics rule, style rules) - appears to be a leaner alternative/successor to ADVISOR_SYSTEM_PROMPT
- `ai_assets.py:614 build_live_system_instruction(context, response_language=None)` - builds the actual Gemini Live system instruction: takes ADVISOR_SYSTEM_PROMPT, sanitizes "TWO MODES"/"COMMAND MODE"/"ADVICE MODE" labels (renamed to "RESPONSE SHAPES"/"DIRECTIVE SHAPE"/"ANALYSIS SHAPE" — comment says native-audio was echoing the labels aloud), appends voice-consistency rules + language rule (multilang-aware) + TACTICAL_RESPONSE_LANGUAGE_RULE + the negotiation context
- `ai_assets.py:650 build_audio_extraction_prompt(known_item=None)` - returns EXTRACTION_PROMPT, or if `known_item` provided, a customized version with item pre-filled and research_query keyed to that item
- `ai_assets.py:691 build_market_research_prompt(*, context_summary, research_query, research_gap, negotiation_type, trigger_reason)` - builds a web-search prompt returning JSON (price_range, key_facts, leverage, tactics, gap_answer); branches on `research_gap` vs `research_query`, and `trigger_reason` ("critical_pressure" / "ai_uncertainty")
- `ai_assets.py:736 build_vision_intel_block(observation)` - formats a VisionObservation dict into a `[VISION_INTEL]` text block (scene, item/condition/defects, document text, prices, terms, body language, tactical hint); includes ALL confidence levels (comment notes low-confidence used to be dropped)
- `ai_assets.py:812 build_pre_query_brief(*, context, market_info, transcript_text, vision_observation=None, next_move_block=None)` - the main per-query context brief injected before user questions; restates anti-hallucination reminders, item/price/sentiment/leverage fields, optional vision block and next-move block, full conversation transcript, and grounding instructions
- `ai_assets.py:856 build_mode_activation_instruction(response_mode)` - short instruction telling the model to answer directly without labeling mode (comment: avoid words "Command"/"Advice" since AI echoes them aloud)
- `ai_assets.py:869 build_copilot_priming_text(*, context, market_info, accumulated_transcript)` - "BACKGROUND INTEL (priming)" block with full price/context fields + transcript
- `ai_assets.py:895 build_listener_intel_block(*, context, negotiation_type, user_role, user_price_label, user_price_val, counterparty_price_label, counterparty_price_val, market_info, events_text, accumulated_transcript)` - richest intel block: base fields + role rule + auto-populated person intel (`counterparty_person_intel`), company intel (`counterparty_company_intel`), document intel (vision), price-conflict alert, full transcript
- `ai_assets.py:975 build_single_context_intel_text(*, context, market_info, transcript_text)` - simplified "BACKGROUND INTEL" block (single-context variant, accepts both `seller_asking_price`/`seller_price` and `buyer_offer`/`user_offer` aliases)
- `ai_assets.py:1001 build_critical_event_block(*, event_type, detail, transcript_text)` - "BACKGROUND INTEL (critical)" block for critical-event injections
- `ai_assets.py:1011 build_perfect_listener_transcription_prompt(speaker)` - per-speaker verbatim transcription prompt for PerfectListener pipeline
- `ai_assets.py:1019 build_person_research_prompt(*, person_name, company=None)` - auto-triggered web-search prompt for counterparty person intel (title, seniority, decision_maker, negotiation_style, pain_points, leverage, etc. as JSON)
- `ai_assets.py:1046 build_company_research_prompt(*, company_name, context=None)` - auto-triggered web-search prompt for counterparty company intel (industry, size, financial_health, procurement_style, urgency_signals, key_leverage_points, etc. as JSON)
- `ai_assets.py:1075 build_response_correction_prompt(violation_messages)` - "STOP. Rule violations: ..." correction prompt sent back to model when response validator fails
- `ai_assets.py:1083 _join_text(values, separator)` - private helper joining non-empty stringified list items

---

## backend/app/api/auth.py (194 lines)

**Purpose**: Two-layer auth module. Layer 1 ("Phase C"): a single shared-secret token (`COMPANION_SHARED_TOKEN`) gating WS/REST on a public box, no-op when empty. Layer 2 ("Phase auth"): Clerk + app-JWT based per-user identity via `AuthUser`. Both layers degrade to fully-open when unconfigured/`AUTH_REQUIRED=False`, preserving legacy dev behavior.

**Functions/classes:**
- `auth.py:40 _configured_token()` - returns stripped `settings.COMPANION_SHARED_TOKEN`
- `auth.py:44 auth_enabled()` - True only if shared token configured
- `auth.py:49 token_matches(candidate)` - constant-time compare via `hmac.compare_digest`; True if auth disabled
- `auth.py:63 async require_token(authorization=Header, x_companion_token=Header)` - FastAPI dependency for sensitive REST; raises 401 if mismatched (no-op if auth disabled)
- `auth.py:89 websocket_token_ok(websocket)` - validates `?token=` query param BEFORE accept(); True if auth disabled
- `auth.py:103 class AuthUser` (dataclass) - `clerk_sub: str`, `email: str`, `is_admin: bool=False`
- `auth.py:113 _ADMIN_SUB = "__shared_token_admin__"` - synthetic sub for shared-token bypass
- `auth.py:116 _extract_bearer(authorization, x_companion_token)` - extracts raw token string from either header
- `auth.py:128 async get_current_user(authorization=Header, x_companion_token=Header) -> AuthUser` - acceptance hierarchy: (1) valid app JWT → real AuthUser, (2) matching shared token → admin AuthUser, (3) `AUTH_REQUIRED=False` → anonymous admin AuthUser, else 401
- `auth.py:167 websocket_get_user(websocket) -> AuthUser | None` - same hierarchy as get_current_user but for WS `?token=`; never raises, returns None on failure (caller closes socket)

**Gotchas:** Comment at auth.py:5 explicitly states "v1 is BYOK + solo testing" — deliberately no OTP/multi-user.

---

## backend/app/api/auth_routes.py (368 lines)

**Purpose**: Clerk-based auth REST routes under `/auth` prefix (no `get_current_user` dependency at router level — `/me` applies it individually). Serves a hosted Clerk sign-in HTML page for desktop loopback OAuth flow, exchanges Clerk tokens for app JWT pairs, and handles refresh/logout/me.

**Routes:**
- `auth_routes.py:199 GET /auth/login-page` (HTMLResponse, `include_in_schema=False`) - `login_page(request, redirect="", signout="")` - serves `_LOGIN_PAGE_TEMPLATE` (Clerk JS sign-in widget); sets `_clerk_redirect`/`_clerk_signout` cookies; returns 503 HTML if `CLERK_PUBLISHABLE_KEY` unset
- `auth_routes.py:244 GET /auth/clear-signout` (`include_in_schema=False`) - `clear_signout(redirect="")` - deletes `_clerk_signout` cookie, redirects to clean login page (breaks sign-out infinite loop)
- `auth_routes.py:261 POST /auth/exchange` - `exchange_clerk_token(payload=Body(...))` - verifies Clerk token via `verify_clerk_token`, requires `email_verified`, upserts user, mints app token pair via `make_token_pair`, stores refresh token
- `auth_routes.py:307 POST /auth/refresh` - `refresh_tokens(payload=Body(...))` - verifies+revokes old refresh jti, mints new pair
- `auth_routes.py:336 POST /auth/logout` - `logout(payload=Body(...))` - revokes refresh token jti (best-effort, always returns `{"ok": True}`)
- `auth_routes.py:356 GET /auth/me` - `me(current_user=Depends(get_current_user))` - returns clerk_sub/email/is_admin/email_verified/last_login_at (or nulls for anonymous/admin)

**Helper:**
- `auth_routes.py:36 _clerk_fapi_url(publishable_key)` - decodes Clerk publishable key to derive Frontend API host for CDN script URLs

**Gotchas:** The login page polls `Clerk.session` every 500ms (no event dependency); `force_signout` flow exists specifically to fix a sign-out → re-sign-out infinite loop (auth_routes.py:154-163, 232-241).

---

## backend/app/api/providers.py (136 lines)

**Purpose**: REST API under `/api/providers` (gated by `get_current_user` dependency at router level, providers.py:29) for the in-app Settings page — read live model catalogs, read/write per-slot provider+model+key config (hot-applied via `runtime_config`), and test a provider+key with a minimal live ping. API key VALUES are never returned by any endpoint.

**Routes:**
- `providers.py:32 GET /api/providers/registry` - `get_registry()` - returns `model_catalog.full_registry(force=False)` (live classified model lists per slot)
- `providers.py:38 POST /api/providers/refresh` - `refresh_registry()` - `model_catalog.clear_cache()` then `full_registry(force=True)`
- `providers.py:45 GET /api/providers/config` - `get_config()` - `runtime_config.reload()` then `runtime_config.safe_config()`
- `providers.py:52 PUT /api/providers/config` - `put_config(patch=Body(...))` - `runtime_config.update(patch)`; on `runtime_config.ConfigError` returns 400 JSON `{"error": ...}`; clears model_catalog cache if keys changed; body shape `{"slots": {...}, "keys": {...}}`
- `providers.py:79 POST /api/providers/test` - `test_provider(payload=Body(...))` - validates provider+key via `_ping_provider`, returns `{"ok", "latency_ms"}` or error

**Helper:**
- `providers.py:108 async _ping_provider(provider, meta, key, model)` - cheapest liveness check per provider: list-endpoint GET for google/anthropic/deepgram/openai-compatible (200=ok); AssemblyAI probes `/v2/transcript` (401=bad key, else ok)

---

## backend/app/api/websocket.py (286 lines)

**Purpose**: The single `/ws` WebSocket endpoint — the heart of the real-time negotiation session. Handles auth gate, session creation/restoration (from `connection_manager` for live reconnects, or `session_store` for cold restores), Phase-G per-session provider override binding, the CONNECTION_ESTABLISHED/SESSION_RESTORED handshake, and the main receive loop dispatching binary audio chunks and JSON messages to `NegotiationEngine`.

**Functions/routes:**
- `websocket.py:20 _restore_session_from_bundle(session, bundle)` - rehydrates a `NegotiationSession` from a persisted bundle dict (state, consent, language/multilang fields, context, transcripts, research/advisor/vision history, speaker_mapping, metrics, final_summary)
- `websocket.py:56 @router.websocket("/ws") async def websocket_endpoint(websocket)` - main handler:
  - `websocket.py:61` - `websocket_get_user(websocket)`; closes with code 1008 if None
  - `websocket.py:67-89` - session resolution: if `?session_id=` matches an active `connection_manager` session → restore in-place; else try `session_store.load_session_bundle()` → restore; else new session
  - `websocket.py:91-122` - accept(), register with connection_manager, create session trace, send `CONNECTION_ESTABLISHED` (includes `resume_token`, `trace_jsonl_path`/`trace_report_path`, `readiness.snapshot()`)
  - `websocket.py:127` - `runtime_config.set_session_overrides(session.provider_overrides)` - Phase G binding (initial, before PROVIDER_CONFIG arrives)
  - `websocket.py:128-132` - `NegotiationEngine.start_live_preconnect(session, settings.GEMINI_API_KEY, context=...)` - kicks off Gemini Live preconnect
  - `websocket.py:133-160` - if restored, sends `SESSION_RESTORED` with transcript/research/advisor/vision/speaker_mapping/final_summary
  - `websocket.py:162-241` - main receive loop: re-binds `runtime_config.set_session_overrides()` on every message (line 170, so spawned tasks see latest overlay); handles `websocket.disconnect`, binary audio (`AUDIO_CHUNK` validated via `NegotiationEngine.validate_message`, routed to `handle_audio_chunk` if ACTIVE, enrollment audio if CONSENTED+enrolling, ignored if PAUSED, error if other state), and JSON text messages routed via `NegotiationEngine.route_message`
  - `websocket.py:227-241` - JSON decode error handling sends `ERROR`/`INVALID_JSON`
  - `websocket.py:243-286` - exception handling (`WebSocketDisconnect`, generic `Exception` → sends `ERROR`/`INTERNAL_ERROR`), `finally` block calls `connection_manager.unregister(session_id, preserve_runtime=...)` (preserves runtime state if session was ACTIVE and `session_resumable`)

**Gotchas:** `runtime_config.set_session_overrides()` is called twice — once at connect (websocket.py:127) and once per received message (websocket.py:170) — explicitly to keep spawned tasks bound to the latest PROVIDER_CONFIG overlay (Phase G / per-session BYOK).

---

## backend/app/models/negotiation.py (317 lines)

**Purpose**: Defines `NegotiationState` enum and the giant `NegotiationSession` pydantic model — the single source of truth for all per-session runtime state (consent, language/multilang, Gemini Live session handles, BYOK overrides, audio buffers, speaker recognition state across multiple providers, transcript buffers, vision analysis state, next-move cache, session metrics, and locks).

**Classes:**
- `negotiation.py:11 class NegotiationState(str, Enum)` - `IDLE | CONSENTED | ACTIVE | PAUSED | ENDING`
- `negotiation.py:20 class NegotiationSession(BaseModel)` - huge state model. Notable field groups:
  - Session/consent: `session_id`, `state`, `consent_version`, `consent_mode`, `started_at`, `context`
  - Multilanguage (negotiation.py:32-45): `language`, `response_language`, `language_profile`, `display_language`, `per_source_language` (dict keyed by LOCAL_MIC_PCM/REMOTE_APP_PCM/ASK_AI_PCM), `voice_fallback_text_only`
  - Resumability: `session_resumable`, `session_restored`, `resume_token`, `last_persisted_at`, `degraded_mode`, `degraded_reasons`
  - Source/meeting (uses `app.models.companion`): `source_mode`, `meeting_binding`, `audio_sources_active`, `hold_state`, `capture_health`, `capture_preset`, `companion_quality_mode`, `selected_output_device_id/label`, `capture_helper_active`
  - Gemini Live handles (runtime-only): `live_session`, `live_session_cm`, `api_key`, `live_session_receive_task`, `live_session_keepalive_task`, `live_session_monitor_task`, `live_reconnect_task`, `live_preconnect_task`, `live_preconnected_context`, `live_preconnect_error`, `live_preconnected_at`
  - Phase G BYOK (negotiation.py:69-73): `provider_overrides: Optional[dict]` - shape `{"slots":{}, "keys":{}, "settings":{}}`, scoped to this WS session via runtime_config ContextVar, never persisted globally
  - Dual-model audio: `audio_buffer`, `listener_agent`, `speech_transcriber`
  - Hold-to-ask / ASK_AI flags: `user_addressing_ai`, `ask_audio_activity_open`, `ask_window_active`, `ask_cycle_gen`, `copilot_active`
  - AI speaking state: `ai_is_speaking`, `ai_audio_playing`, `pending_injections`, `pending_live_snapshot`, `pending_intel_context`, `pending_intel_critical_events`, `intel_injection_task`, `last_intel_injected_at`
  - Response tracking: `last_user_transcript`, `direct_query_in_flight`, `current_ai_response`, `recent_ai_responses`, `last_ai_audio_played_at`, `last_ask_response_at`, `response_mode="auto"`
  - User context: `user_context` (item/target_price/max_price/extra_context from SetupDialog)
  - `gemini_send_lock: asyncio.Lock` - serializes ALL `send_realtime_input` calls (negotiation.py:145)
  - Speaker recognition (negotiation.py:148-189): `current_speaker`, `manual_override_until`, `speaker_timeline`, `speaker_mapping`, `speaker_mapping_state/confidence/locked_at/last_validated_at`, `speaker_embedding_cache`, `speaker_cluster_centroids`, `mapping_contradiction_count`, `mapping_state_transitions`, `mapping_contradictions`, `permanent_unknown_speaker_ids`, `user_embedding`, `enrollment_audio`, `speaker_mode`, `speaker_recognition_enabled`, `speaker_confidence_history`, `counterparty_candidates`, `counterparty_cluster_embedding/promoted_at`, plus full SpeechBrain (`speechbrain_*`) and Azure (`azure_*`) verification state fields
  - Runtime services (not serialized): `speaker_service`, `enrollment_service`, `perfect_listener`
  - Transcript buffering: `pending_transcripts`, `display_transcript_turns`, `eligible_transcript_turns`, `pending_utterance_audio/id/started_at/rms`, `partial_transcript_*` fields
  - Speaker segment tracking: `speaker_segment_start/speaker`, `current_segment_audio`
  - ASK_AI capture: `question_capture_bytes/id/started_at/chunk_count/last_chunk_at`, `ignore_local_mic_until`, `current_ask_capture`, `companion_audio_buffers/started_at/last_chunk_at/last_transcript_at/partial_*` (per-source dicts)
  - Outcome: `initial_price`, `final_price`, `final_summary`, `transcript`, `research_history`, `advisor_history`, `vision_history`, `trace_jsonl_path/report_path`, `trace_refs`
  - Vision analysis: `vision_observations`, `vision_frame_buffer`, `vision_last_hash`, `vision_needs_analysis`, `vision_last_pro_call_at`, `vision_pro_call_count`, `vision_analysis_task`
  - Next-move cache (negotiation.py:264-272): `next_move_cache`, `next_move_task`, `next_move_last_refresh_at` - populated by `app.services.next_move_cache.refresh_next_move()`, read by `handle_user_addressing_ai`
  - Hold timing: `last_hold_started_ms/released_ms`
  - Vision live send: `vision_live_send_task`, `vision_live_pending_frame_b64`, `vision_live_last_sent_at`, `vision_live_drop_count`
  - `strategy_history`, `session_metrics` (dict with stt/speaker/research/ask counters, negotiation.py:282-310)
  - Locks: `sidecar_lock`, `stt_lock`, `research_lock`
  - `model_config = ConfigDict(arbitrary_types_allowed=True)` (negotiation.py:315) - required for live_session handle and asyncio.Lock fields

---

## backend/app/models/messages.py (262 lines)

**Purpose**: Pydantic models for all WebSocket JSON message payloads, split into Client→Server and Server→Client sections.

**Client → Server payloads:**
- `messages.py:9 ConsentPayload` - `version`, `mode` ("live"|"roleplay") — for PRIVACY_CONSENT_GRANTED
- `messages.py:15 StartNegotiationPayload` - `context`, `source_mode`, `meeting_binding`, `capture_preset`, `companion_quality_mode`, `selected_output_device` — for START_NEGOTIATION
- `messages.py:25 VisionFramePayload` - `image` (base64 JPEG), `timestamp`, `source_mode`, `source` — for VISION_FRAME
- `messages.py:33 SetResponseLanguagePayload` - `language` — for SET_RESPONSE_LANGUAGE
- `messages.py:38 SetLanguageProfilePayload` - `profile`, `pinned_code`, `per_source`, `display_language`, `response_language` — for SET_LANGUAGE_PROFILE (multilang)
- `messages.py:55 MeetingBindingPayload` - target_id/window_title/process_name/platform_hint/output_device_id/label/is_bound — for MEETING_BINDING
- `messages.py:66 CaptureHealthPayload` - mic_forward_ok/remote_audio_ok/frame_capture_ok/reply_output_ok/helper_active/process_loopback_ok/unsafe_device_loopback/degraded_reasons — for CAPTURE_HEALTH
- `messages.py:78 HoldToAskStatePayload` - `active`, `muted_to_meeting` — for HOLD_TO_ASK_STATE / USER_ADDRESSING_AI
- `messages.py:84 CompanionAudioPayload` - `pcm_base64`, `timestamp_ms`, `is_final`, `utterance_id`, `started_at_ms`, `rms` — for LOCAL_MIC_PCM/REMOTE_APP_PCM/ASK_AI_PCM
- `messages.py:94 EndNegotiationPayload` - `final_price`, `initial_price` — for END_NEGOTIATION
- `messages.py:100 TranscriptEntry` - `id`, `speaker`, `text`, `timestamp` (used in TRANSCRIPT_UPDATE-related contexts)
- `messages.py:108 StrategyUpdate` - target_price/current_offer/recommended_response/key_points/approach_type/confidence/walkaway_threshold/web_search_used/search_sources
- `messages.py:121 OutcomeSummary` - deal_reached/initial_price/final_price/savings/savings_percentage/market_value/vs_market/negotiation_duration_seconds/key_moves/effectiveness_score/transcript_summary — for OUTCOME_SUMMARY

**Server → Client payloads:**
- `messages.py:140 ConnectionEstablishedPayload` - session_id/server_time/restored/resume_token — CONNECTION_ESTABLISHED
- `messages.py:148 ConsentAcknowledgedPayload` - mode/recording_active — CONSENT_ACKNOWLEDGED
- `messages.py:154 SessionStartedPayload` - session_id/model/features (audio/vision/web_search bools) — SESSION_STARTED
- `messages.py:161 SessionRestoredPayload` - session_id/language/response_language/transcript/research/advisor/vision/speaker_mapping — SESSION_RESTORED
- `messages.py:173 PersistenceStatusPayload` - ready/session_id — PERSISTENCE_STATUS
- `messages.py:179 VisionStatusPayload` - timestamp/event/size/observation — VISION_STATUS
- `messages.py:187 LanguageUpdatePayload` - language/response_language — LANGUAGE_UPDATE
- `messages.py:193 DegradedModeUpdatePayload` - active/mode/reasons — DEGRADED_MODE_UPDATE
- `messages.py:200 MeetingBindingUpdatePayload` - binding (dict) — MEETING_BINDING_UPDATE
- `messages.py:205 CaptureHealthUpdatePayload` - health (dict) — CAPTURE_HEALTH_UPDATE
- `messages.py:210 TranscriptUpdatePayload` - id/speaker/text/timestamp/is_partial/source/context — TRANSCRIPT_UPDATE
- `messages.py:221 StrategyUpdatePayload` - same shape as StrategyUpdate — STRATEGY_UPDATE
- `messages.py:234 AIResponsePayload` - text/response_type ("analysis"|"coaching"|"alert"|"summary")/timestamp — AI_RESPONSE
- `messages.py:241 AudioInterruptedPayload` - empty — AUDIO_INTERRUPTED
- `messages.py:246 SessionReconnectingPayload` - reason ("gemini_session_dropped"|"session_timeout"|"model_fallback")/attempt/max_attempts — SESSION_RECONNECTING
- `messages.py:253 AIDegradedPayload` - message/features_available — AI_DEGRADED
- `messages.py:259 ErrorPayload` - code/message — ERROR

---

## backend/app/models/companion.py (47 lines)

**Purpose**: Small companion-app shared models for source mode, participant origin, meeting binding (which window/app the companion is bound to), capture health diagnostics, and hold-to-ask state. Used as defaults inside `NegotiationSession`.

**Classes:**
- `companion.py:9 class SourceMode(str, Enum)` - `IN_PERSON_WEB = "in_person_web"`, `VIRTUAL_COMPANION_DESKTOP = "virtual_companion_desktop"`
- `companion.py:14 class ParticipantOrigin(str, Enum)` - `LOCAL_USER`, `REMOTE_COUNTERPARTY`, `AI`, `UNKNOWN`
- `companion.py:21 class MeetingBinding(BaseModel)` - target_id/window_title/process_name/platform_hint/output_device_id/output_device_label/is_bound/bound_at
- `companion.py:32 class CaptureHealth(BaseModel)` - mic_forward_ok/remote_audio_ok/frame_capture_ok/reply_output_ok/helper_active/process_loopback_ok/unsafe_device_loopback/degraded_reasons
- `companion.py:43 class CompanionHoldState(BaseModel)` - active/muted_to_meeting/started_at/released_at

---

## backend/app/providers/registry.py (345 lines)

**Purpose**: Pure-data provider/model registry — no network calls. Defines task SLOTS, per-provider metadata (PROVIDERS), curated FALLBACK_MODELS (verified May 2026), and classification functions mapping discovered model ids to slots.

**Constants:**
- `registry.py:30-42` - `SLOT_LIVE_VOICE`, `SLOT_REASONING`, `SLOT_FAST_TEXT`, `SLOT_VISION`, `SLOT_STT`, `SLOTS` list
- `registry.py:44-50` - `SLOT_LABELS` dict (display labels per slot)
- `registry.py:55-142` - `PROVIDERS` dict: `google` (Gemini, all 5 slots, ListModels endpoint), `openai` (reasoning/fast_text/vision/stt; live_voice is phase2), `anthropic` (reasoning/fast_text/vision), `groq` (reasoning/fast_text/vision/stt), `deepseek` (reasoning/fast_text), `openrouter` (reasoning/fast_text/vision), `deepgram` (stt), `assemblyai` (stt, no list_endpoint), `elevenlabs` (stt, no list_endpoint). Each entry: display_name, key_field, openai_compatible, base_url, list_endpoint, supports_custom_model, slots
- `registry.py:146-148` - `LIVE_VOICE_PHASE2 = {"openai": ["gpt-realtime", "gpt-realtime-2"]}` - documented but hidden in UI
- `registry.py:151` - `GOOGLE_STT_PROVIDER_VALUE = "google_stt"` - internal id used by stt_service for Google Cloud STT
- `registry.py:156-199` - `FALLBACK_MODELS` dict - curated per-provider per-slot model lists (e.g. google live_voice → `["gemini-live-2.5-flash-native-audio"]`, anthropic reasoning → `["claude-opus-4-8", "claude-sonnet-4-6"]`)
- `registry.py:207-210` - `_NON_CHAT_MARKERS` tuple - substrings marking non-chat models (embed/embedding/rerank/moderation/tts/image/dall-e/guard/whisper/transcribe/realtime/audio/search-)

**Functions:**
- `registry.py:213 _is_chat_like(model_id)` - True if no `_NON_CHAT_MARKERS` substring present
- `registry.py:218 classify_openai_like(model_id)` - classifies OpenAI/Groq/DeepSeek-style ids: STT (transcribe/whisper), live_voice (realtime), or reasoning+fast_text (+vision for gpt-5/gpt-4o/llama-4/scout/maverick families) based on `reasoning_markers`/`vision_markers`
- `registry.py:251 classify_anthropic(model_id)` - any "claude" id → `{REASONING, FAST_TEXT, VISION}`
- `registry.py:259 classify_google(model_id, supported_methods=None)` - uses `supportedGenerationMethods` if available (`bidiGenerateContent`→live_voice, `generateContent`→reasoning+fast_text+vision); else infers from id substrings ("live"/"native-audio"→live_voice, "gemini"→all three text slots); excludes embed/aqa/imagen
- `registry.py:281 classify_openrouter(model)` - uses OpenRouter `architecture.input_modalities`/`output_modalities`/`supported_parameters`; requires text output; text input→reasoning+fast_text, image input→vision
- `registry.py:305 _google_cloud_stt_available()` - cached check via `importlib.util.find_spec("google.cloud.speech_v2")` - gates whether "google" appears in STT slot (lean hosted profile doesn't install this SDK)
- `registry.py:329 slot_providers(slot, *, include_phase2=False)` - providers that CAN serve a slot (ignores key presence); live_voice forced to `["google"]` (+phase2 if requested); STT excludes "google" if Cloud STT SDK unavailable
- `registry.py:344 provider_meta(provider)` - `PROVIDERS.get(provider)`

**Gotchas:** registry.py:309-315 explains why "google" STT requires the `google.cloud.speech_v2` SDK (ADC-based, not BYOK-portable) unlike the 5 HTTP/BYOK STT providers.

---

## backend/app/providers/runtime_config.py (388 lines)

**Purpose**: The hot-apply provider config overlay. Resolution order for every value: **session ContextVar overlay (Phase G BYOK) → `runtime_providers.json` → `.env` (settings) → registry fallback**. Persists to `backend/data/runtime_providers.json` (path overridable via `RUNTIME_PROVIDERS_PATH` env). API keys never returned by read APIs — only `present`/`missing` status.

**Module state:**
- `runtime_config.py:35-36` - `_DEFAULT_PATH` = `backend/data/runtime_providers.json`, `_CONFIG_PATH` (env-overridable)
- `runtime_config.py:38-39` - `_lock` (RLock), `_cache` (in-memory dict)
- `runtime_config.py:49-51` - `_session_overrides: ContextVar[dict|None]` - Phase G per-session overlay, shape `{"slots":{}, "keys":{}, "settings":{}}`

**Functions:**
- `runtime_config.py:54 _per_session_enabled()` - reads `settings.PER_SESSION_PROVIDER_OVERRIDE_ENABLED`
- `runtime_config.py:58 set_session_overrides(overrides)` - sets ContextVar, returns reset token; no-op (None) if feature flag off
- `runtime_config.py:68 reset_session_overrides(token)` - resets ContextVar (best-effort)
- `runtime_config.py:75 current_session_overrides()` - returns ContextVar value (None if flag off)
- `runtime_config.py:81 _sess_slot(slot)`, `runtime_config.py:88 _sess_key(provider)`, `runtime_config.py:95 _sess_setting(name)` - read sub-dicts from session overlay
- `runtime_config.py:103-109` - `_SLOT_ENV_FIELDS` dict - maps each SLOT to `(PROVIDER_env_field, MODEL_env_field)` on settings
- `runtime_config.py:112 _empty()` - returns `{"slots":{},"keys":{},"settings":{}}`
- `runtime_config.py:116 _override_enabled()` - reads `settings.PROVIDER_RUNTIME_OVERRIDE_ENABLED` (master revert switch)
- `runtime_config.py:123 _load_unlocked()` - loads/caches `runtime_providers.json`; returns `_empty()` if override disabled or file unreadable
- `runtime_config.py:145 reload()` - drops cache, re-reads file
- `runtime_config.py:153 _write_unlocked(data)` - atomic write via tempfile + `os.replace`
- `runtime_config.py:172 provider_for(slot)` - resolves provider: session overlay → JSON → env field → (STT special-case: legacy `TRANSCRIPTION_PROVIDER`, mapping `"google_stt"`→`"google"`) → default `"google"`
- `runtime_config.py:194 model_for(slot)` - resolves model: session overlay → JSON → env field → first `FALLBACK_MODELS` entry for resolved provider
- `runtime_config.py:215 api_key_for(provider)` - resolves key: session overlay → (legacy `google_stt` shares google's session key) → JSON → env `key_field`; legacy `google_stt` with no meta falls back to `GEMINI_API_KEY`
- `runtime_config.py:239 key_status(provider)` - `"present"`/`"missing"` based on `api_key_for`
- `runtime_config.py:244 has_runtime_key(provider)` - True only if key was explicitly saved via Settings UI (session or JSON), NOT from `.env`
- `runtime_config.py:256 google_api_key()` - alias for `api_key_for("google")`
- `runtime_config.py:261 google_backend()` - resolves `"vertex"|"ai_studio"`: session setting → JSON setting → `GOOGLE_GENAI_USE_VERTEXAI` env
- `runtime_config.py:280 google_use_vertex()` - `google_backend() == "vertex"`
- `runtime_config.py:285 google_live_models()` - returns `(primary, fallback)` Live model IDs; Vertex uses `effective_model`/`effective_fallback_model` (google/-prefixed), AI Studio uses `GEMINI_LIVE_MODEL_AISTUDIO`/`GEMINI_LIVE_FALLBACK_AISTUDIO` (different bare ids, not just missing prefix)
- `runtime_config.py:300 is_google(slot)` - True if `provider_for(slot)` is `"google"` or `"google_stt"`
- `runtime_config.py:307 class ConfigError(ValueError)` - raised by `_validate_patch`
- `runtime_config.py:311 _validate_patch(patch)` - validates slot names, provider eligibility per slot (STT also accepts legacy `"google_stt"`), key provider names, `google_backend` value
- `runtime_config.py:337 update(patch)` - merges+persists `{"slots":{...}, "keys":{...}, "settings":{...}}`; empty string key value removes stored key (falls back to env); returns `safe_config()`
- `runtime_config.py:377 safe_config()` - returns `{"slots": {slot: {provider, model}}, "key_status": {...}, "settings": {"google_backend": ...}, "path": str(_CONFIG_PATH)}`

**Gotchas:** This module is the central Phase-G/BYOK mechanism — `provider_overrides` on `NegotiationSession` flows through `set_session_overrides()` (called in websocket.py:127 and websocket.py:170) into every `_sess_*` lookup here.

---

## backend/app/providers/model_catalog.py (240 lines)

**Purpose**: Live model discovery — fetches each provider's own model-list API, classifies models into slots via `registry.classify_*`, caches per-provider (TTL 3600s, keyed by key-hash so a key change invalidates cache), and falls back to `registry.FALLBACK_MODELS` on any failure (marked `source="fallback"`). Powers `/api/providers/registry`.

**Constants:** `model_catalog.py:30 _CACHE_TTL_SECONDS = 3600.0`, `model_catalog.py:31 _FETCH_TIMEOUT = 8.0`, `model_catalog.py:34 _cache` dict, `model_catalog.py:35 _locks` dict (per-provider asyncio.Lock)

**Functions:**
- `model_catalog.py:38 _key_hash(key)` - sha256 hex (first 16 chars) of API key, used to detect key changes
- `model_catalog.py:42 _lock_for(provider)` - lazily creates per-provider asyncio.Lock
- `model_catalog.py:52 async _fetch_models(provider, client)` - per-provider fetch+classify dispatch:
  - `google` (model_catalog.py:62-73) - GET ListModels with `?key=`, classify via `registry.classify_google`
  - `anthropic` (75-87) - GET with `x-api-key`/`anthropic-version` headers, classify via `classify_anthropic`
  - `openrouter` (89-101) - GET with Bearer, classify via `classify_openrouter`
  - `deepgram` (103-133) - GET with `Token` auth; handles categorized response shapes, excludes TTS/aura* voices, all results → `{SLOT_STT}`
  - openai-compatible (135-148: openai/groq/deepseek) - GET with Bearer, classify via `classify_openai_like`
- `model_catalog.py:153 async _get_provider_models(provider, *, force)` - returns `({model_id: slots}, source)`; checks key presence, cache TTL+key_hash, double-checked locking, falls back to `({}, "fallback")` on any exception
- `model_catalog.py:194 async list_for_slot(slot, *, force=False)` - for every provider serving `slot`, returns `{models, source, key_status, supports_custom_model}`; falls back to `registry.FALLBACK_MODELS` if live list empty
- `model_catalog.py:221 async full_registry(*, force=False)` - builds `{slots: {slot: {label, providers: {...}}}, providers: {pid: {display_name, supports_custom_model}}}`
- `model_catalog.py:239 clear_cache()` - `_cache.clear()`

---

## backend/app/providers/text_client.py (191 lines)

**Purpose**: Provider-agnostic async text/vision generation. `generate()` resolves slot→provider/model/key via `runtime_config` and dispatches to the correct SDK (Anthropic, OpenAI-compatible, or Google), returning plain text. Design rule (text_client.py:8-10): the existing Google/Gemini call sites remain untouched; this module is only used when the resolved provider for a slot is NOT Google (though it does implement a Google branch for completeness/testing).

**Functions/classes:**
- `text_client.py:30 class ProviderNotConfigured(RuntimeError)` - raised when no model/key resolved or provider unsupported
- `text_client.py:34 _images_to_data_urls(images, mime)` - converts raw image bytes → `data:<mime>;base64,...` URLs
- `text_client.py:42 async generate(slot, *, user_text, system=None, images=None, image_mime="image/jpeg", json_mode=False, temperature=0.2, max_output_tokens=2048, timeout=8.0) -> str` - main entrypoint; resolves provider/model/key, raises `ProviderNotConfigured` if model missing or (non-google) key missing, dispatches to one of:
  - `text_client.py:90 async _generate_anthropic(...)` - uses `anthropic.AsyncAnthropic`, builds image+text content blocks, appends "Respond with ONLY valid JSON..." instruction if `json_mode`
  - `text_client.py:125 async _generate_openai_compatible(...)` - uses `openai.AsyncOpenAI` with `base_url`, builds messages (plain string if no images, else content array with `image_url` data URLs), sets `response_format={"type":"json_object"}` if `json_mode`
  - `text_client.py:157 async _generate_google(...)` - uses `google.genai`; `genai.Client(api_key=...)` if key present else ADC/Vertex `genai.Client()`; builds `Content`/`Part` with inline image blobs, `system_instruction`, `response_mime_type="application/json"` if json_mode

---

## API ROUTES SUMMARY (all FastAPI routes)

| Method | Path | Function | File:Line |
|---|---|---|---|
| GET | `/` | `clerk_root_handler` | main.py:295 |
| GET | `/api/health` | `health_check` | main.py:349 |
| GET | `/health` | `health_check_root` | main.py:353 |
| GET | `/api/ready` | `readiness_check` | main.py:357 |
| GET | `/api/sessions` | `list_sessions` | main.py:365 |
| GET | `/api/sessions/{session_id}` | `get_session_history` | main.py:369 |
| POST | `/api/log` | `log_frontend_message` | main.py:378 |
| WS | `/ws` | `websocket_endpoint` | websocket.py:56 |
| GET | `/api/providers/registry` | `get_registry` | providers.py:32 |
| POST | `/api/providers/refresh` | `refresh_registry` | providers.py:38 |
| GET | `/api/providers/config` | `get_config` | providers.py:45 |
| PUT | `/api/providers/config` | `put_config` | providers.py:52 |
| POST | `/api/providers/test` | `test_provider` | providers.py:79 |
| GET | `/auth/login-page` | `login_page` | auth_routes.py:199 |
| GET | `/auth/clear-signout` | `clear_signout` | auth_routes.py:244 |
| POST | `/auth/exchange` | `exchange_clerk_token` | auth_routes.py:261 |
| POST | `/auth/refresh` | `refresh_tokens` | auth_routes.py:307 |
| POST | `/auth/logout` | `logout` | auth_routes.py:336 |
| GET | `/auth/me` | `me` | auth_routes.py:356 |

---

## CROSS-CUTTING GOTCHAS / FEATURE FLAGS / RECENT CHANGES

1. **Phase G per-session BYOK** (`PER_SESSION_PROVIDER_OVERRIDE_ENABLED`, default True): `NegotiationSession.provider_overrides` (negotiation.py:73) flows through `runtime_config.set_session_overrides()` (websocket.py:127, 170) into a ContextVar consulted by every `_sess_*` resolver in runtime_config.py — never persisted to disk, scoped per-asyncio-task.
2. **Master revert switches**: `PROVIDER_RUNTIME_OVERRIDE_ENABLED` (config.py:71) — set False to ignore `runtime_providers.json` entirely (pure `.env` behavior). `PER_SESSION_PROVIDER_OVERRIDE_ENABLED` (config.py:80) — set False to disable Phase G BYOK entirely.
3. **ASK_AI native audio flags** (config.py:214-237): `ASK_AI_NATIVE_AUDIO`, `ASK_AI_NATIVE_ONLY_TRANSCRIPTION`, `ASK_AI_SUPPRESS_NATIVE_TRANSCRIPTION`, `ASK_AI_ACTIVITY_END_DELAY_SECONDS` — all have detailed inline comments about race conditions and "easy revert" instructions.
4. **MULTILANG_ENABLED** (config.py:190, default True): gates Deepgram `language=multi`, per-source language profiles, Gemini Live auto-language, response-language prompt instructions, and pro-advice translation wrap. When False, all paths behave as pre-multilang.
5. **NEXT_MOVE_CACHE_ENABLED** (config.py:354, default True): background-precomputed "what now" recommendation injected into pre-query brief via `next_move_block` param of `build_pre_query_brief` (ai_assets.py:812).
6. **Google backend (Vertex vs AI Studio)** is resolved EFFECTIVELY via `runtime_config.google_backend()`/`google_use_vertex()` (runtime_config.py:261-282), NOT the raw `GOOGLE_GENAI_USE_VERTEXAI` env — `config.py._effective_use_vertex()` lazy-imports runtime_config to avoid a circular import (config.py:427-437). Live model IDs differ entirely between backends (`google_live_models()`, runtime_config.py:285).
7. **STT hint phrases removed** (ai_assets.py:12-15, config.py:14, config.py:157-158, config.py:377-379): `GOOGLE_STT_HINT_PHRASES`/`google_stt_hint_phrases_list` are vestigial no-ops — hardcoded keywords caused STT hallucinations; always returns `[]`.
8. **LIVE_GENERATION_MAX_OUTPUT_TOKENS=8192** (ai_assets.py:26-31): raised from 1024 because the audio-token budget was clipping spoken Live answers mid-sentence.
9. **build_live_system_instruction** (ai_assets.py:614) sanitizes "TWO MODES"/"COMMAND MODE"/"ADVICE MODE" → "TWO RESPONSE SHAPES"/"DIRECTIVE SHAPE"/"ANALYSIS SHAPE" because the native-audio Gemini model was speaking the literal mode-label text aloud; same reasoning behind `build_mode_activation_instruction` (ai_assets.py:856) avoiding the words "Command"/"Advice".
10. **ITEM SPECIFICS RULE** (ai_assets.py in both ADVISOR_SYSTEM_PROMPT ~line 540 and UNIFIED_ADVISOR_SYSTEM_PROMPT ~line 588-602, also reiterated in `build_pre_query_brief` ai_assets.py:828-830): hard rule never to invent specifics about the user's item (storage/condition/etc.) unless the user stated them — "overrides all other rules".
11. **SpeechBrain exclusivity** (main.py:113-125): if `SPEECHBRAIN_ENABLED=True`, `RESEMBLYZER_ENABLED`/`WESPEAKER_ENABLED`/`AZURE_SPEAKER_VERIFICATION_ENABLED` must all be False or startup raises `RuntimeError`.
12. **Google Cloud STT availability gate** (registry.py:305-326): "google" only appears as an STT provider option if `google.cloud.speech_v2` SDK is importable (full local/Vertex install vs lean hosted profile).
13. **k2_fsa/pyannote patches must run first** (main.py:13-36) — `patch_speechbrain_k2()` and the `hf_hub_download` use_auth_token→token shim must execute before any pyannote import.
14. **Auth layering** (auth.py): `COMPANION_SHARED_TOKEN` empty = Phase C auth fully disabled (no-op); `AUTH_REQUIRED=False` = Phase-auth (Clerk JWT) also fully open, returns anonymous admin `AuthUser`. Both can be on simultaneously (shared-token path is checked before AUTH_REQUIRED fallback).
15. **DEEPGRAM_UTTERANCE_END_MS** (config.py:174-178): Deepgram silently ignores values <1000ms — must stay >=1000 or UtteranceEnd is disabled entirely.