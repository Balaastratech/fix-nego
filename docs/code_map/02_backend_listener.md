I'll analyze each file systematically using grep to get accurate line numbers and structure.

Now let's get the other files' structure and read key sections in parallel.

Now market_research.py and a few more details for listener_agent (class attrs, key methods detail) and stt_service result dict shape.

Now let's check key methods more closely - the extraction cycle, context update, market research trigger, and PerfectListener integration points, plus stt_service result dict and FinalizedUtterance usage.

Now let me check the stt_service `_recognize_sync` result dict structure, `transcribe`/`transcribe_audio` signatures, and FinalizedUtterance usage, plus check process_diarized_utterance and ingest_simulated_turn more closely.

Now let's check perfect_listener's transcription/output flow and how it connects to listener_agent's accumulated_transcript, plus check the `_call_flash` and market research trigger sections, and `_send_live_transcript_turn`/`_safe_send_json`.

Now check the rest of `_transcribe_turn` for the TRANSCRIPT_UPDATE message format and accumulated_transcript append, and check `process_audio_chunk` flow briefly.

Now I have enough detail. Let me check a couple remaining items: `_call_flash` in listener_agent (audio fallback path), `_run_market_research` trigger logic, and `_find_market_research` settings, plus `next_move_cache` settings list, and `_recognize_sync` returns dict shape briefly.

I have sufficient detail for all five files. Let me do one final check on `market_research.py`'s relation to `gemini_client`/`negotiation_engine` (it appears unused/placeholder—important to flag) and confirm `next_move_cache` settings constants list with line numbers.

Confirmed `market_research.py`'s `search_market_data`/`search_marketplaces`/`search_forums`/`calculate_price_range` functions are **dead code / placeholders** — only `build_market_research_prompt` (in ai_assets.py, used by listener_agent's `_run_market_research`, the actual Gemini+Search-grounded path) is wired up.

Now I have everything needed. Here's the reference map.

## backend/app/services/listener_agent.py

**Purpose**: Background asyncio task (`ListenerAgent`) that polls accumulated transcript text (populated by `PerfectListenerSystem` or the legacy STT path), runs fast text→text Gemini Flash extraction cycles to pull negotiation intelligence (prices, sentiment, leverage, key moments), merges/dedupes it into `session` state, pushes `CONTEXT_UPDATE`/`TRANSCRIPT_UPDATE`/`RESEARCH_*` messages over the websocket, and triggers market research (via `market_research`-prompt builder, NOT `market_research.py`'s placeholder functions). It owns the Gemini Flash client (`self._client`, `self._flash_model` from `settings.effective_flash_model`) and feeds `next_move_cache.schedule_refresh` via `_on_context_ready`. `transcribe_utterance`/`process_diarized_utterance`/`transcribe_segment` use `stt_service.SpeechTranscriptionService` for the legacy (non-PerfectListener) STT path. `negotiation_engine.py` instantiates `ListenerAgent`, calls `start/pause/resume/stop`, `ingest_simulated_turn`, `build_advisor_query`, `force_reextraction`/`force_immediate_cycle`. `gemini_client.py` is referenced indirectly (its `build_advisor_query`/`generate_tactical_advice` are called from `next_move_cache.py`, and `ListenerAgent.build_advisor_query` is the per-session wrapper used by `negotiation_engine`).

### Classes / functions
- `ListenerAgent` — `backend/app/services/listener_agent.py:86` — main background agent class.
  - `__init__` — `backend/app/services/listener_agent.py:91` — sets up state, Flash client (Vertex or API key based on `_rc.google_use_vertex()`), research limiter.
  - `start` — `backend/app/services/listener_agent.py:197` — spawns `_poll_loop` task if not already running.
  - `pause` — `backend/app/services/listener_agent.py:208` — sets `_paused=True`, suspends cycles (used during Ask-AI hold).
  - `resume` — `backend/app/services/listener_agent.py:221` — clears `_paused`.
  - `stop` — `backend/app/services/listener_agent.py:233` — sets `_running=False`, cancels background tasks.
  - `_create_background_task` — `backend/app/services/listener_agent.py:246` — wraps `asyncio.create_task`, tracks in `_background_tasks` set for cleanup.
  - `_cancel_background_tasks` — `backend/app/services/listener_agent.py:266` — cancels/awaits all tracked tasks; logs failures as warnings.
  - `_safe_send_json` — `backend/app/services/listener_agent.py:279` — guarded `websocket.send_json`; swallows/logs send errors, returns bool success.
  - `transcribe_segment` — `backend/app/services/listener_agent.py:306` — manual-mode transcription entry point (legacy/manual speaker mode).
  - `_transcribe_batch` — `backend/app/services/listener_agent.py:354` — batches pending segments, calls `_fast_transcribe`/Flash; on failure logs `"[ListenerAgent] Fast transcription failed"`.
  - `_fast_transcribe` — `backend/app/services/listener_agent.py:422` — synchronous fast transcription helper (legacy path).
  - `_append_accumulated_transcript` — `backend/app/services/listener_agent.py:466` — appends `"[LABEL] text\n"` to `self.accumulated_transcript`, bounds it (mirrors PerfectListener's 8000/6000-char cap).
  - `_send_live_transcript_turn` — `backend/app/services/listener_agent.py:471` — pushes a transcript turn into the live Gemini session (if copilot active).
  - `ingest_simulated_turn` — `backend/app/services/listener_agent.py:498` — injects a synthetic text-only transcript turn (used by automated Live AI eval/scenarios); appends to `session.transcript`/`display_transcript_turns`/`eligible_transcript_turns`, sends `TRANSCRIPT_UPDATE`, schedules `_run_text_extraction_cycle`.
  - `transcribe_utterance` — `backend/app/services/listener_agent.py:572` — legacy STT path: calls `_speech_transcriber.transcribe`, sets eligibility flags (`MIN_CONTEXT_DURATION_MS`, confidence ≥0.70), sends `TRANSCRIPT_UPDATE`/`LANGUAGE_UPDATE`.
  - `process_diarized_utterance` — `backend/app/services/listener_agent.py:686` — like above but emits per-diarized-turn transcript entries with mapped speakers.
  - `_run_text_extraction_cycle` — `backend/app/services/listener_agent.py:850` — **core extraction**: debounced (`TEXT_EXTRACTION_DEBOUNCE_SECONDS`=3.0s), hash-deduped, text→text Flash call using `TEXT_EXTRACTION_PROMPT`/`SHORT_TEXT_EXTRACTION_PROMPT`, writes trace artifacts, calls `_post_process_context`. Skips if `session.user_addressing_ai` is true.
  - `_coerce_text_entry` (staticmethod) — `backend/app/services/listener_agent.py:1125` — normalizes a raw extraction value to string.
  - `_normalize_text_list` (classmethod) — `backend/app/services/listener_agent.py:1144` — normalizes list-of-mixed-types to list of strings.
  - `_post_process_context` — `backend/app/services/listener_agent.py:1153` — shared by audio + text extraction paths: detects critical events (`ANCHOR_DETECTED`, `SENTIMENT_NEGATIVE`, `URGENCY_DETECTED`, `PRESSURE_TACTIC`), calls `_merge_context`, `_send_context_update`, triggers research.
  - `_poll_loop` — `backend/app/services/listener_agent.py:1366` — main loop, sleeps `POLL_INTERVAL`=1.5s, calls `_run_cycle`, catches/logs exceptions per cycle.
  - `_run_cycle` — `backend/app/services/listener_agent.py:1395` — per-cycle entry: skips if `user_addressing_ai`, skips if `accumulated_transcript` < 30 chars, else calls `_run_text_extraction_cycle`. Docstring notes it's "Modified for PerfectListenerSystem integration" — no audio handling here anymore.
  - `_run_market_research` — `backend/app/services/listener_agent.py:1423` — async Gemini+Google-Search market research; sends `RESEARCH_STARTED`/`RESEARCH_COMPLETE`/`RESEARCH_FAILED`; uses `build_market_research_prompt` from `app.ai_assets`; retries via `RESEARCH_MAX_RETRIES`/`RESEARCH_BASE_BACKOFF_MS`/`RESEARCH_MAX_BACKOFF_MS`; appends to `session.research_history` (capped by `RESEARCH_HISTORY_LIMIT`).
  - `_run_person_research` — `backend/app/services/listener_agent.py:1690` — researches a named person, sends `RESEARCH_COMPLETE` with `payload.type="person"`.
  - `_run_company_research` — `backend/app/services/listener_agent.py:1720` — researches a company, sends `RESEARCH_COMPLETE` with `payload.type="company"`.
  - `_build_speaker_timeline_hint` — `backend/app/services/listener_agent.py:1750` — builds a text hint of speaker turn timeline for Flash prompts.
  - `_call_flash` — `backend/app/services/listener_agent.py:1816` — **legacy/manual-mode** synchronous Flash call combining transcription+extraction from raw audio (kept "for manual mode compatibility (transcribe_segment)"; PerfectListenerSystem normally handles transcription).
  - `_attach_vision_observation` — `backend/app/services/listener_agent.py:1977` — merges latest vision observation into context dict.
  - `_merge_context` — `backend/app/services/listener_agent.py:1997` — non-destructive merge of extracted fields into `self.last_context`; has "contamination guard" (logs warning if `buyer_offer == seller_asking_price`); has item-downgrade guard (won't replace a longer/specific item name with a shorter one); caps `key_moments`/`leverage_points` to last 5.
  - `_has_context_changed` — `backend/app/services/listener_agent.py:2051` — compares current vs `_last_sent_context` to decide whether to push update.
  - `_update_last_sent_context` — `backend/app/services/listener_agent.py:2091` — snapshots the just-sent context fields.
  - `_send_context_update` — `backend/app/services/listener_agent.py:2107` — sends `CONTEXT_UPDATE` payload (item, prices, sentiment, key_moments, leverage_points, market_data, cycle).
  - `build_advisor_query` — `backend/app/services/listener_agent.py:2155` — public helper used by `negotiation_engine` to build the advisor prompt from `user_context`.
  - `force_reextraction` — `backend/app/services/listener_agent.py:2203` — clears dedup hash so next cycle re-extracts.
  - `force_immediate_cycle` — `backend/app/services/listener_agent.py:2215` — forces an out-of-band `_run_cycle`/extraction (e.g. after manual speaker correction).

### Module-level constants (listener_agent.py:60-86)
- `POLL_INTERVAL = 1.5` — `backend/app/services/listener_agent.py:65`
- `WINDOW_SECONDS = 20` — `backend/app/services/listener_agent.py:66` (audio window, fallback path)
- `MIN_NEW_AUDIO = 1.5` — `backend/app/services/listener_agent.py:67`
- `VOICE_SIMILARITY_THRESHOLD = 0.75` — `backend/app/services/listener_agent.py:68`
- `TEXT_EXTRACTION_DEBOUNCE_SECONDS = 3.0` — `backend/app/services/listener_agent.py:69`
- `SHORT_TEXT_EXTRACTION_PROMPT` — `backend/app/services/listener_agent.py:70`
- `SPEAKER_SMOOTHING_WINDOW = 3` — `backend/app/services/listener_agent.py:79`
- `SPEAKER_SMOOTHING_THRESHOLD = 0.55` — `backend/app/services/listener_agent.py:80`

### Settings flags read
- `settings.RESEARCH_GLOBAL_CONCURRENCY` — `backend/app/services/listener_agent.py:107`
- `settings.MIN_TRANSCRIBE_DURATION_MS` — `backend/app/services/listener_agent.py:128`
- `settings.GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` — `backend/app/services/listener_agent.py:173-183`
- `settings.effective_flash_model` — `backend/app/services/listener_agent.py:189`
- `settings.TRANSCRIPT_HISTORY_LIMIT` — `backend/app/services/listener_agent.py:543, 812`
- `settings.google_stt_language_codes_list` — `backend/app/services/listener_agent.py:584`
- `settings.MIN_CONTEXT_DURATION_MS` — `backend/app/services/listener_agent.py:605, 762`
- `settings.TEXT_EXTRACTION_TIMEOUT_SECONDS` — `backend/app/services/listener_agent.py:913, 953, 976, 1090, 1097`
- `settings.RESEARCH_MAX_RETRIES`, `RESEARCH_BASE_BACKOFF_MS`, `RESEARCH_MAX_BACKOFF_MS` — `backend/app/services/listener_agent.py:1536-1538`
- `settings.RESEARCH_HISTORY_LIMIT` — `backend/app/services/listener_agent.py:1658`

### Gotchas / non-obvious behaviors
- File header comment (lines 4-15) explicitly states this file was **modified for PerfectListenerSystem integration**: it now reads `accumulated_transcript` populated externally and does **NO transcription or speaker identification itself**.
- `_call_flash` (line 1816) is legacy code retained "for manual mode compatibility" — comment at line 1844-1845 warns PerfectListenerSystem normally owns transcription.
- `_merge_context` (line 1997) has a deliberate "contamination guard" — logs a warning but does NOT reject data when `buyer_offer == seller_asking_price` (line 2010).
- `_merge_context` item-downgrade guard (lines 2018-2026): blocks overwriting a longer item name with a shorter/generic one, logs `"Blocking item downgrade"`.
- Comment at line 2029 (mojibake `â€”` = em-dash, encoding issue in source) reiterates `transcript_snippet` is intentionally NOT appended to `accumulated_transcript` to avoid corrupting per-speaker labels.
- `_run_cycle` skips entirely while `session.user_addressing_ai` is true (prevents the user's question to the AI from polluting negotiation context).

### Key WebSocket message types produced
- `TRANSCRIPT_UPDATE` — `backend/app/services/listener_agent.py:395, 562, 653, 823` (and via `ingest_simulated_turn`)
- `LANGUAGE_UPDATE` — `backend/app/services/listener_agent.py:592`
- `CONTEXT_UPDATE` — `backend/app/services/listener_agent.py:2122`
- `RESEARCH_STARTED` — `backend/app/services/listener_agent.py:1437`
- `RESEARCH_COMPLETE` — `backend/app/services/listener_agent.py:1669, 1713 (person), 1743 (company)`
- `RESEARCH_FAILED` — `backend/app/services/listener_agent.py:1684`
- Internal `event_type` keys (sent inside critical-event lists, not top-level WS types): `ANCHOR_DETECTED` (1173), `SENTIMENT_NEGATIVE` (1181), `URGENCY_DETECTED` (1192), `PRESSURE_TACTIC` (1227)

---

## backend/app/services/perfect_listener.py

**Purpose**: Experimental, feature-flagged (`settings.ENABLE_OVERLAP_DETECTION`, `ENABLE_SPEECH_SEPARATION`, `PERFECT_LISTENER_FALLBACK`) `PerfectListenerSystem` class implementing a 5-stage real-time diarization/transcription pipeline (overlap detection → optional speech separation → VAD turn segmentation → speaker ID via WeSpeaker/Pyannote/clustering → Gemini Flash transcription). Replaces the old audio-handling responsibilities of `ListenerAgent`: it directly appends `"[SPEAKER] text\n"` lines to `listener_agent.accumulated_transcript` (the shared buffer `ListenerAgent._run_text_extraction_cycle` polls) and writes to `session.speaker_timeline`. It is constructed with a reference to the live `ListenerAgent` instance and the websocket; `negotiation_engine.handle_audio_chunk` calls `process_audio_chunk` in "automatic mode", and `negotiation_engine.handle_end` calls `stop()`. Does not call `gemini_client.py`; uses its own lazily-constructed `genai.Client` (`self.flash_client`) for transcription only.

### Classes / functions
- `PerfectListenerSystem` — `backend/app/services/perfect_listener.py:26` — main pipeline class.
  - `__init__` — `backend/app/services/perfect_listener.py:38` — GPU/CPU device detection (`torch.cuda.is_available()`), initializes buffers (`frame_buffer`, `turn_buffer`, `overlap_window` as `bytearray`), reads feature flags (see below). Raises `RuntimeError` on model-load failure if `PERFECT_LISTENER_FALLBACK` is False.
  - `process_audio_chunk` — `backend/app/services/perfect_listener.py:127` — **main entry point**, called per ~100ms PCM chunk from `negotiation_engine.handle_audio_chunk`. Skips processing entirely if `session.user_addressing_ai` is true (Ask-AI mutual exclusion). Manages `frame_buffer`/`overlap_window` (2s cap = 64000 bytes), runs the 5-stage pipeline per detected turn.
  - `_detect_overlap` — `backend/app/services/perfect_listener.py:308` — Stage 1: Pyannote `OverlappedSpeechDetection`, lazy-loaded; only runs if `overlap_detection_enabled`.
  - `_separate_speakers` — `backend/app/services/perfect_listener.py:459` — Stage 2: Conv-TasNet speech separation; only runs if overlap detected AND `speech_separation_enabled` AND `convtasnet_enabled`.
  - `_segment_turns` — `backend/app/services/perfect_listener.py:633` — Stage 3: Pyannote VAD (`pyannote/segmentation-3.0`) turn segmentation; uses `min_duration_on`/`min_duration_off`.
  - `_identify_speaker` — `backend/app/services/perfect_listener.py:922` — Stage 4 dispatcher: tries WeSpeaker → Pyannote embedding → clustering fallback chain.
  - `_try_wespeaker` — `backend/app/services/perfect_listener.py:1081` — WeSpeaker ResNet34 speaker embedding + cosine similarity vs `wespeaker_threshold` (0.70 default).
  - `_try_pyannote_embedding` — `backend/app/services/perfect_listener.py:1218` — Pyannote embedding model fallback for speaker ID.
  - `_try_clustering` — `backend/app/services/perfect_listener.py:1360` — online clustering fallback (`speaker_clusters` dict); only if `clustering_enabled`.
  - `_transcribe_turn` — `backend/app/services/perfect_listener.py:1547` — Stage 5: PCM→WAV, lazy-inits `self.flash_client` (Vertex AI if `GOOGLE_GENAI_USE_VERTEXAI` else API key), calls Gemini Flash (`settings.effective_flash_model`) with `build_perfect_listener_transcription_prompt(speaker)`, **3 retries with 1s/2s/4s backoff and a 10s per-attempt timeout**, sends `TRANSCRIPT_UPDATE` to frontend, appends `"[SPEAKER] text\n"` to `listener_agent.accumulated_transcript` (bounded to 6000 chars once >8000), appends to `session.speaker_timeline` (capped at 300 entries).
  - `_pcm_to_wav` — `backend/app/services/perfect_listener.py:1874` — PCM16→WAV header helper.
  - `_generate_turn_id` — `backend/app/services/perfect_listener.py:1919` — deterministic turn ID from `start_time`, used for dedup via `transcribed_turn_ids` set.
  - `_normalize_audio` — `backend/app/services/perfect_listener.py:1936` — audio normalization helper.
  - `_log_error` — `backend/app/services/perfect_listener.py:1994` — structured JSON error logging (session_id, turn_id, audio_duration, exception, stack trace).
  - `_load_model_safe` — `backend/app/services/perfect_listener.py:2057` — generic lazy model loader; tracks `model_load_errors` dict to avoid repeat-loading failed models; raises `RuntimeError` if load fails and `settings.PERFECT_LISTENER_FALLBACK` is False, else returns `False` and degrades gracefully.
  - `stop` — `backend/app/services/perfect_listener.py:2162` — clears all buffers/state and releases model references (models are shared/GC'd, not explicitly unloaded).

### Settings flags read
- `settings.HF_TOKEN` (HuggingFace token for Pyannote models) — `backend/app/services/perfect_listener.py:358, 677, 1255, 1396`
- `settings.GOOGLE_GENAI_USE_VERTEXAI` — `backend/app/services/perfect_listener.py:1610`
- `settings.GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` — `backend/app/services/perfect_listener.py:1613-1624`
- `settings.GEMINI_API_KEY` — `backend/app/services/perfect_listener.py:1627`
- `settings.effective_flash_model` — `backend/app/services/perfect_listener.py:1631`
- `settings.PERFECT_LISTENER_FALLBACK` — `backend/app/services/perfect_listener.py:2145` (also checked inside `_load_model_safe`)
- `getattr(settings, 'PYANNOTE_MIN_DURATION_ON', 0.25)` — `backend/app/services/perfect_listener.py:100`
- `getattr(settings, 'PYANNOTE_MIN_DURATION_OFF', 0.5)` — `backend/app/services/perfect_listener.py:101`
- `getattr(settings, 'WESPEAKER_THRESHOLD', 0.70)` — `backend/app/services/perfect_listener.py:102`
- `getattr(settings, 'CONVTASNET_ENABLED', True)` — `backend/app/services/perfect_listener.py:103`
- `getattr(settings, 'CLUSTERING_ENABLED', True)` — `backend/app/services/perfect_listener.py:104`
- `getattr(settings, 'ENABLE_OVERLAP_DETECTION', False)` — `backend/app/services/perfect_listener.py:107`
- `getattr(settings, 'ENABLE_SPEECH_SEPARATION', False)` — `backend/app/services/perfect_listener.py:108`

### Gotchas / non-obvious behaviors
- Module docstring (lines 2-12) describes the 5-stage pipeline and references "Requirements: 20.1, 20.2, 20.3" (spec-driven dev artifacts — many methods cite Requirement numbers in docstrings, e.g. lines 53, 312, 637).
- "Heavy ML component flags (disable for 2-speaker scenarios)" comment at line 76 — `overlap_detection_enabled`/`speech_separation_enabled` default to `False`, meaning by default overlap/separation stages are bypassed (`has_overlap = False` always, line ~211).
- `_load_model_safe` (line 2057): if a model previously failed to load, it's permanently skipped for the session (`model_load_errors` dict) — no retry within a session.
- `_transcribe_turn` marks `turn_id` as transcribed **before** the API call succeeds ("Mark as transcribed immediately to prevent race conditions", line ~1599) — if transcription ultimately fails, the turn is silently dropped (never retried).
- `accumulated_transcript` bound: kept under 8000 chars, truncated to last 6000 — same scheme as `ListenerAgent._append_accumulated_transcript`.
- `process_audio_chunk` requires ≥16000 bytes (0.5s) in `overlap_window` before doing anything (line ~189).
- Manual-mode comment (lines 144-152): manual speaker override (`session.manual_override_until`) does NOT stop VAD/transcription — it only affects speaker identification elsewhere.

### Key message types / dict keys
- Sends `TRANSCRIPT_UPDATE` directly via `self.websocket.send_json` — `backend/app/services/perfect_listener.py:1786` — payload keys: `id` (turn_id), `speaker`, `text`, `timestamp`, `start_time`, `end_time`.
- Writes to `self.listener_agent.accumulated_transcript` (string, format `"[SPEAKER] text\n"`).
- Writes to `self.session.speaker_timeline` (list of `{"speaker": ..., "timestamp": ...}`).
- `turns` dicts produced by `_segment_turns` contain at least `audio`, `start_time`, `end_time`.

---

## backend/app/services/stt_service.py

**Purpose**: `SpeechTranscriptionService` — the legacy/manual-mode STT wrapper supporting multiple providers (Google Cloud Speech-to-Text v2, Deepgram, AssemblyAI, ElevenLabs, OpenAI-compatible) selected via `settings.TRANSCRIPTION_PROVIDER`. Used by `ListenerAgent.transcribe_utterance`/`process_diarized_utterance`/`transcribe_segment` (legacy path; PerfectListenerSystem bypasses this for automatic transcription). Operates on `FinalizedUtterance` objects (`app.services.utterance_types`). Not directly related to `gemini_client.py` or `negotiation_engine.py` other than being constructed by `ListenerAgent.__init__` (`session.speech_transcriber`).

### Classes / functions
- `_sanitize_broken_loopback_proxy_env` — `backend/app/services/stt_service.py:25` — module-load-time env cleanup; logs a warning (line 57) if it removes a broken loopback proxy var. Sets module global `_BROKEN_PROXY_ENV_SANITIZED`.
- `_duration_to_seconds` — `backend/app/services/stt_service.py:65` — normalizes various duration representations to float seconds.
- `_pcm_to_wav` — `backend/app/services/stt_service.py:78` — PCM16→WAV header helper (module-level, separate from per-class helpers in other files).
- `SpeechTranscriptionService` — `backend/app/services/stt_service.py:91` — main class.
  - `__init__` — `backend/app/services/stt_service.py:92` — sets up `self._global_limiter` via `GlobalLimiter` with `settings.STT_GLOBAL_CONCURRENCY`, resolves provider.
  - `_resolve_stt_selection` (staticmethod) — `backend/app/services/stt_service.py:103` — reads `settings.TRANSCRIPTION_PROVIDER` (default `"google_stt"`), normalizes to internal provider key.
  - `_get_client` — `backend/app/services/stt_service.py:126` — lazy client construction per provider/location.
  - `_is_retryable` (staticmethod) — `backend/app/services/stt_service.py:144` — determines if an exception should trigger retry (used with `run_with_retries`).
  - `_candidate_locations` (staticmethod) — `backend/app/services/stt_service.py:152` — builds list of fallback GCP locations for recognizer creation.
  - `_supports_named_recognizer_creation` (staticmethod) — `backend/app/services/stt_service.py:175` — checks if recognizer_id supports auto-creation.
  - `_is_not_found_message` (staticmethod) — `backend/app/services/stt_service.py:179` — string match helper for 404-like errors.
  - `_provider_minutes_metric_key` — `backend/app/services/stt_service.py:187` — returns session metric key name (e.g. `"google_stt_minutes"` / `"deepgram_minutes"`) for usage tracking.
  - `_provider_log_name` — `backend/app/services/stt_service.py:192` — human-readable provider name for logs.
  - `_normalize_deepgram_language_code` — `backend/app/services/stt_service.py:197` — normalizes language codes for Deepgram's expected format.
  - `_resolve_deepgram_language` — `backend/app/services/stt_service.py:234` — picks Deepgram language param, iterates `settings.deepgram_language_codes_list` (line 243).
  - `_resolve_deepgram_keyterms` — `backend/app/services/stt_service.py:260` — keyterm/boost phrase list for Deepgram.
  - `_build_deepgram_request_url` — `backend/app/services/stt_service.py:263` — builds Deepgram REST URL using `settings.DEEPGRAM_MODEL`, `DEEPGRAM_UTTERANCE_SPLIT`, `DEEPGRAM_DIARIZATION_ENABLED`, `DEEPGRAM_API_BASE_URL`.
  - `_parse_deepgram_words` — `backend/app/services/stt_service.py:284` — extracts word-level timing/speaker info from Deepgram response.
  - `_parse_deepgram_response` — `backend/app/services/stt_service.py:327` — builds normalized result dict (`provider: "deepgram"`, `diarized_turns`, etc.) from raw Deepgram JSON.
  - `transcribe` — `backend/app/services/stt_service.py:381` — **main async entry**: takes a `FinalizedUtterance`, calls `transcribe_audio`, populates `utterance.transcript_text`, `transcription_confidence`, `metadata["stt_response"]`, `metadata["diarized_turns"]`; increments `session.session_metrics["stt_successes"]`/`"stt_empty_results"`; uses `log_speaker_debug("STT_RESULT", ...)`.
  - `transcribe_audio` — `backend/app/services/stt_service.py:441` — wraps `_recognize_sync` in executor + `run_with_retries` (max_retries=`STT_MAX_RETRIES`, backoff=`STT_BASE_BACKOFF_MS`/`STT_MAX_BACKOFF_MS`), enforces `timeout_seconds` (default `STT_END_TO_END_TIMEOUT_SECONDS`); increments `session_metrics["stt_requests"]` and provider-minutes metric if `count_metrics=True`; on retry increments `session_metrics["stt_retry_count"]`.
  - `_resolve_language_codes` — `backend/app/services/stt_service.py:491` — picks language code list; special-cases `GOOGLE_STT_MODEL == "chirp_3"` with multiple configured languages → forces `["auto"]`.
  - `_resolve_adaptation_phrases` — `backend/app/services/stt_service.py:508` — builds Speech Adaptation phrase list from `settings.google_stt_hint_phrases_list`.
  - `_recognize_deepgram_sync` — `backend/app/services/stt_service.py:547` — synchronous Deepgram REST call; requires `settings.DEEPGRAM_API_KEY`; uses `urlopen` with `STT_RPC_TIMEOUT_SECONDS`.
  - `_recognize_openai_compatible_sync` — `backend/app/services/stt_service.py:616` — OpenAI-compatible STT endpoint via `httpx`.
  - `_recognize_assemblyai_sync` — `backend/app/services/stt_service.py:668` — AssemblyAI provider, API key via `_rc.api_key_for("assemblyai")`.
  - `_recognize_elevenlabs_sync` — `backend/app/services/stt_service.py:731` — ElevenLabs provider, API key via `_rc.api_key_for("elevenlabs")`.
  - `_recognize_sync` — `backend/app/services/stt_service.py:772` — **dispatcher**: routes to provider-specific recognize function based on `self._provider` (`deepgram` line 778, `assemblyai` line 791, `elevenlabs` line 797, else Google STT v2 inline). Handles Google STT recognizer auto-creation (lines 877-1016), diarization config (`GOOGLE_STT_DIARIZATION_ENABLED`, `MIN/MAX_SPEAKERS`), speech adaptation boost (`GOOGLE_STT_HINT_BOOST`).
  - `probe_capability` — `backend/app/services/stt_service.py:1236` — health-check/capability probe; logs `region=` using `GOOGLE_STT_REGION` or `DEEPGRAM_API_BASE_URL` depending on provider.

### Settings flags read (selected, with line numbers)
- `settings.STT_GLOBAL_CONCURRENCY` — `backend/app/services/stt_service.py:99`
- `settings.TRANSCRIPTION_PROVIDER` — `backend/app/services/stt_service.py:119`
- `settings.GOOGLE_STT_LOCATION` — `backend/app/services/stt_service.py:128, 172`
- `settings.deepgram_language_codes_list` — `backend/app/services/stt_service.py:243`
- `settings.DEEPGRAM_MODEL` — `backend/app/services/stt_service.py:270, 566, 599`
- `settings.DEEPGRAM_UTTERANCE_SPLIT` — `backend/app/services/stt_service.py:273`
- `settings.DEEPGRAM_DIARIZATION_ENABLED` — `backend/app/services/stt_service.py:276`
- `settings.DEEPGRAM_API_BASE_URL` — `backend/app/services/stt_service.py:282, 1246, 1256`
- `settings.STT_END_TO_END_TIMEOUT_SECONDS` — `backend/app/services/stt_service.py:389, 478, 684`
- `settings.STT_MAX_RETRIES`, `STT_BASE_BACKOFF_MS`, `STT_MAX_BACKOFF_MS` — `backend/app/services/stt_service.py:484-486`
- `settings.google_stt_language_codes_list` — `backend/app/services/stt_service.py:496`
- `settings.GOOGLE_STT_MODEL` — `backend/app/services/stt_service.py:504, 1030`
- `settings.google_stt_hint_phrases_list` — `backend/app/services/stt_service.py:524`
- `settings.DEEPGRAM_API_KEY` — `backend/app/services/stt_service.py:553, 577`
- `settings.STT_RPC_TIMEOUT_SECONDS` — `backend/app/services/stt_service.py:586, 646, 686, 751, 1016, 1135`
- `settings.GOOGLE_STT_HINT_BOOST` — `backend/app/services/stt_service.py:808, 813, 817`
- `settings.GOOGLE_STT_DIARIZATION_ENABLED` — `backend/app/services/stt_service.py:839`
- `settings.GOOGLE_STT_DIARIZATION_MIN_SPEAKERS`, `MAX_SPEAKERS` — `backend/app/services/stt_service.py:845-846`
- `settings.GOOGLE_STT_RECOGNIZER` — `backend/app/services/stt_service.py:877, 996-997, 1005, 1029`
- `settings.GOOGLE_CLOUD_PROJECT` — `backend/app/services/stt_service.py:887, 918, 987, 996, 1007, 1094, 1099`
- `settings.GOOGLE_STT_REGION` — `backend/app/services/stt_service.py:1246, 1256`

### Gotchas / non-obvious behaviors
- `_sanitize_broken_loopback_proxy_env` (line 25) runs at module load and logs a warning if it had to fix a broken proxy env var — `backend/app/services/stt_service.py:57`.
- Comment at line 947: `"[STT] recognizer %s already exists at %s (race) [session=%s]"` — explicit handling of a **race condition** when two sessions try to auto-create the same Google STT recognizer concurrently.
- `_resolve_language_codes` (line 491-507): special interaction — Chirp 3 model + multiple configured languages forces `"auto"` language detection mode (Google STT v2 limitation).
- Provider value internally normalized: comment at lines 119-123 notes external config value maps to internal `"google_stt"`.

### Key dict keys / message shapes
- `FinalizedUtterance` fields populated: `transcript_text`, `transcription_confidence`, `metadata["stt_response"]`, `metadata["diarized_turns"]`.
- `_recognize_sync`/provider functions return a dict with at least: `text`, `confidence`, `diarized_turns` (list of `{diarized_speaker_id, start_time, end_time, text}`), `language_code`, `provider`, `adaptation_phrases`.

---

## backend/app/services/next_move_cache.py

**Purpose**: Precomputes a "what should I do right now" recommendation in the background so vague hold-to-ask queries ("what now", "trap?", "accept?") get an instant cached answer instead of waiting on synchronous Pro reasoning. Triggered via `schedule_refresh` from `ListenerAgent._on_context_ready` (i.e., wired into `listener_agent.py`'s context-update flow). Pulls context from `listener_agent.last_context`/`accumulated_transcript` and `session.vision_observations`. Uses `app.ai_assets.build_pre_query_brief` and `app.services.gemini_client.build_advisor_query`/`generate_tactical_advice` directly — this is the main file that calls into `gemini_client.py`. Result (`session.next_move_cache`) is read by `format_for_brief` and injected into the pre-query brief that `negotiation_engine`/`gemini_client` build for Gemini Live; per the module docstring, "The cache only changes the INPUT to Gemini Live."

### Functions
- `classify_ask` — `backend/app/services/next_move_cache.py:43` — classifies a user query as `"vague"` or `"precise"`; uses `settings.next_move_vague_tokens_list` (line 62); length cap 60 chars; falls back to `"vague"` if ≤30 chars else `"precise"`.
- `_context_basis_hash` — `backend/app/services/next_move_cache.py:73` — MD5 hash of `(transcript_tail[-1200:], intel_keys, latest_vision)` — used to detect staleness; `intel_keys` = tuple of `counterparty_price`, `seller_asking_price`, `buyer_offer`, `counterparty_sentiment`, `counterparty_goal`, last-5 `key_moments`, last-5 `leverage_points`.
- `should_refresh_cache` — `backend/app/services/next_move_cache.py:105` — gate: returns False if `NEXT_MOVE_CACHE_ENABLED` is off, within debounce window (`NEXT_MOVE_BACKGROUND_DEBOUNCE_MS`), or basis hash unchanged from current cache.
- `format_for_brief` — `backend/app/services/next_move_cache.py:125` — renders `[RECOMMENDED NEXT MOVE — precomputed Xs ago, tier=fast|pro] ... [/RECOMMENDED NEXT MOVE]` block; returns `""` if cache empty/stale (`age > NEXT_MOVE_MAX_AGE_SECONDS`) or text empty.
- `_vague_user_query` — `backend/app/services/next_move_cache.py:153` — synthetic prompt used to drive Flash/Pro: "What is the single best next move for me RIGHT NOW?..."
- `_trace_event` — `backend/app/services/next_move_cache.py:166` — best-effort write to session trace (category `"ask_ai"`).
- `_generate_flash` — `backend/app/services/next_move_cache.py:181` — fast recommendation via `NEXT_MOVE_FAST_MODEL`; builds `intel` via `build_pre_query_brief`, `advisor_query` via `gemini_client.build_advisor_query`; **multi-provider routing**: if `runtime_config.is_google(SLOT_FAST_TEXT)` is False, routes through `app.providers.text_client.generate` (line ~250) instead of direct `genai.Client`; otherwise builds a `genai.Client` (Vertex or API key) and calls `client.models.generate_content` with `ThinkingConfig(thinking_budget=0)`.
- `_generate_pro` — `backend/app/services/next_move_cache.py:301` — Pro upgrade via `gemini_client.generate_tactical_advice(session, user_query=_vague_user_query(), response_mode="advice")`.
- `refresh_next_move` — `backend/app/services/next_move_cache.py:315` — **main background task**: checks `should_refresh_cache`, sets `session.next_move_last_refresh_at`, runs `_generate_flash` (timeout `NEXT_MOVE_FAST_TIMEOUT_SECONDS`) and writes `session.next_move_cache` (`is_pro=False`) only if no newer Pro result exists for the same basis; if `NEXT_MOVE_PRO_UPGRADE_ENABLED`, also runs `_generate_pro` (timeout `NEXT_MOVE_PRO_TIMEOUT_SECONDS`) and overwrites only if `context_basis_hash` still matches (else logs `next_move_pro_upgrade_dropped_stale`).
- `schedule_refresh` — `backend/app/services/next_move_cache.py:391` — fire-and-forget scheduler: cancels any in-flight `session.next_move_task`, creates new task via `loop.create_task(refresh_next_move(session))`. No-ops if `NEXT_MOVE_CACHE_ENABLED` is False or `should_refresh_cache` is False.

### Settings flags read
- `settings.next_move_vague_tokens_list` — `backend/app/services/next_move_cache.py:62`
- `settings.NEXT_MOVE_CACHE_ENABLED` — `backend/app/services/next_move_cache.py:111, 396`
- `settings.NEXT_MOVE_BACKGROUND_DEBOUNCE_MS` — `backend/app/services/next_move_cache.py:113`
- `settings.NEXT_MOVE_MAX_AGE_SECONDS` — `backend/app/services/next_move_cache.py:136`
- `settings.NEXT_MOVE_FAST_TIMEOUT_SECONDS` — `backend/app/services/next_move_cache.py:252, 254, 332`
- `settings.GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` — `backend/app/services/next_move_cache.py:266-267`
- `settings.NEXT_MOVE_FAST_MODEL` — `backend/app/services/next_move_cache.py:273, 345`
- `settings.NEXT_MOVE_PRO_UPGRADE_ENABLED` — `backend/app/services/next_move_cache.py:356`
- `settings.NEXT_MOVE_PRO_TIMEOUT_SECONDS` — `backend/app/services/next_move_cache.py:363`
- `settings.ADVICE_GENERATION_MODEL` — `backend/app/services/next_move_cache.py:377`

### Gotchas / non-obvious behaviors
- Module docstring (lines 1-21) is itself the best architectural reference — describes the full lifecycle and explicitly states it doesn't change `handle_ask_advice`'s Pro pre-flight path.
- `should_refresh_cache` comment (line 105-110): debounce AND basis-hash dedup both apply — a context update during the debounce window will not trigger refresh even if basis changed.
- Comment at lines 339-341 / `refresh_next_move`: Flash result is only written if `existing.get("context_basis_hash") != basis or not existing.get("is_pro")` — i.e., a fresh Flash result will NOT clobber an already-fresh Pro result for the same basis.
- Comment at lines 369-373: Pro result is only written if `current.get("context_basis_hash") == basis` — guards against a slow Pro call overwriting a newer refresh's result ("stale Pro answer").

### Key dict keys / cache shape
- `session.next_move_cache` = `{"text": str, "model": str, "generated_at": float (epoch), "context_basis_hash": str, "is_pro": bool}`
- `session.next_move_last_refresh_at`, `session.next_move_task` (asyncio.Task) — session attributes set by this module.
- Trace event names: `next_move_cache_started`, `next_move_cache_ready`, `next_move_pro_upgrade_ready`, `next_move_pro_upgrade_dropped_stale`.

---

## backend/app/services/market_research.py

**Purpose**: Standalone module providing `search_marketplaces`, `search_forums`, `calculate_price_range`, `search_market_data` — **but these are unused placeholder/TODO implementations** (`search_marketplaces`/`search_forums` always return `[]`; comments explicitly say "TODO: Implement actual marketplace/forum search"). The actual market-research feature used in production is implemented separately in `ListenerAgent._run_market_research` (`backend/app/services/listener_agent.py:1423`) using `app.ai_assets.build_market_research_prompt` + Gemini Flash + Google Search grounding — that path does NOT call into this file at all. This file has no relationship to `negotiation_engine.py`, `gemini_client.py`, or the other 4 files in this set beyond the shared domain concept ("market research").

### Functions
- `search_marketplaces` — `backend/app/services/market_research.py:17` — **placeholder, always returns `[]`** (see TODO comment ~line 38-41); intended to search OLX/Facebook Marketplace etc.
- `search_forums` — `backend/app/services/market_research.py:57` — **placeholder, always returns `[]`** (TODO comment ~line 78-81); intended to search Reddit/forums.
- `calculate_price_range` — `backend/app/services/market_research.py:96` — **fully implemented**, pure function: extracts prices from `marketplace_listings`/`forum_discussions`, returns `{"min", "max", "average", "median", "sample_size"}` using `statistics.mean`/`median`; returns all-`None`/`sample_size=0` if no prices found.
- `search_market_data` — `backend/app/services/market_research.py:157` — orchestrator: runs `search_marketplaces`+`search_forums` in parallel via `asyncio.gather(..., return_exceptions=True)`, handles exceptions per-branch into `search_errors` list, calls `calculate_price_range`, returns `{"marketplace_listings", "forum_discussions", "price_range", "search_errors"?}`. Since the two search functions are stubs, this currently always returns empty lists + `price_range` with `sample_size: 0`.

### Settings flags read
- None — this module reads no `settings.*` values.

### Gotchas / non-obvious behaviors
- TODO comments at `backend/app/services/market_research.py:38-41` and `:78-81` mark `search_marketplaces`/`search_forums` as unimplemented stubs returning empty results — "graceful degradation" by design, but effectively dead weight since the real research path bypasses this file entirely.
- No imports of/from this module were found anywhere else in `backend/app` (verified via grep) — confirm before assuming any caller depends on it; if doing cleanup work, this file is a candidate for removal or for actually implementing the TODOs if the feature is wanted.

### Key dict keys / shapes
- Marketplace listing dict: `source`, `title`, `price`, `condition`, `location`, `url`, `posted_date`.
- Forum discussion dict: `source`, `title`, `summary`, `price_mentioned`, `url`, `date`.
- `price_range` dict: `min`, `max`, `average`, `median`, `sample_size`.
- `search_market_data` return: `marketplace_listings`, `forum_discussions`, `price_range`, optional `search_errors` (list of strings).