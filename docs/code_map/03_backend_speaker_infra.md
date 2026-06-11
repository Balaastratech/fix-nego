I'll analyze these files systematically. Let me start by exploring the directory structure and then dive into each file.

u.py is empty (0 bytes). Now let me read all the target files in parallel batches.

Now let's read the next batch of files.

Now let's read the next batch.

Now the final batch of files.

Now let me check imports/usages across the codebase for these files to determine "used by" relationships, and check for gotchas/NOTE/FIXME comments.

Let me check azure_speaker_service and eagle_service usage further (likely used dynamically), and check voice_encoder usage too, plus check NegotiationSession model for the dict shapes referenced.

Now I have everything I need. Let me also quickly check the ask_transcript_state.py and azure/eagle usage in negotiation_engine for context, and check the ask_transcript_state import list used by negotiation_engine/gemini_client/companion_runtime to capture key consumers.

I now have all the information needed. Azure and Eagle services appear unused/dead code (no imports anywhere). Let me produce the final reference map.

## Reference Map: backend/app/services/ (speaker, audio, session, auth subsystem)

## speaker_service.py

**Purpose**: Real-time speaker classification (user vs counterparty vs unknown) during a negotiation session. Runs WebRTC VAD over 30ms PCM frames to detect speech segment boundaries, generates SpeechBrain ECAPA-TDNN embeddings, and compares via cosine similarity to the enrolled user voiceprint. Two parallel paths exist: a legacy frame/VAD-driven path (`feed_audio`/`_classify_segment`) and a newer per-utterance path (`classify_utterance`) used with diarized STT output. Imported/used by `negotiation_engine.py` (3 call sites: `backend/app/services/negotiation_engine.py:587`, `:1552`, `:3037`).

- `class SpeakerService` — `backend/app/services/speaker_service.py:33`
  - Class constants: `SAMPLE_RATE=16000`, `BYTES_PER_SAMPLE=2`, `FRAME_DURATION_MS=30`, `FRAME_SIZE=960` bytes — `backend/app/services/speaker_service.py:54-57`
  - `MAX_EMBED_DURATION=2.0` (only embeds first 2s of audio — perf optimization) — `backend/app/services/speaker_service.py:58`
  - `USER_BOOTSTRAP_MARGIN=0.10`, `USER_STICKY_THRESHOLD=0.58`, `STICKY_SPEAKER_MAX_GAP_SECONDS=2.5`, `COUNTERPARTY_THRESHOLD=0.38` — `backend/app/services/speaker_service.py:59-62`
  - `__init__(session, on_segment_complete_callback=None)` — `backend/app/services/speaker_service.py:64` — sets up `webrtcvad.Vad` with `settings.SPEAKER_VAD_AGGRESSIVENESS` (default 2), frame buffer, segment state, transcription rate-limit (`min_transcription_gap=3.0s`)
  - `async feed_audio(chunk: bytes)` — `backend/app/services/speaker_service.py:94` — buffers PCM into 960-byte frames; only processes if `session.state.value in ["ACTIVE","CONSENTED"]`
  - `_process_frame(frame: bytes)` — `backend/app/services/speaker_service.py:118` — runs VAD, detects silence↔speech transitions, fires `asyncio.create_task(self._classify_segment(...))` on segment end
  - `async _classify_segment(audio: bytes) -> str` — `backend/app/services/speaker_service.py:163` — legacy VAD-segment classification path; checks `session.user_embedding`, `manual_override_until`/`current_speaker` manual override, trims to first 2s, extracts embedding via `speechbrain_service.extract_embedding` in executor, computes cosine similarity vs `settings.USER_VERIFY_THRESHOLD`; returns `"user"|"counterparty"|"unknown"`; appends to `session.speaker_confidence_history` and `session.speaker_timeline`; rate-limits transcription callback (`min_transcription_duration=1.5s`)
  - `get_current_speaker() -> str` — `backend/app/services/speaker_service.py:371`
  - `get_confidence_score() -> float` — `backend/app/services/speaker_service.py:380`
  - `async classify_utterance(audio, *, duration_ms, transcription_confidence, utterance_id, timestamp=None) -> tuple[str, float|None]` — `backend/app/services/speaker_service.py:392` — newer per-utterance classification (3-state). Returns early "unknown" if `session.user_embedding is None` or `duration_ms < settings.MIN_TRANSCRIBE_DURATION_MS`. Checks `settings.USER_VERIFY_THRESHOLD` (user), then continuation logic via `settings.USER_CONTINUATION_WINDOW_SECONDS`/`USER_CONTINUATION_THRESHOLD`, then counterparty candidacy via `settings.COUNTERPARTY_REJECT_THRESHOLD` + `COUNTERPARTY_STT_CONFIDENCE_MIN`
  - `_promote_or_match_counterparty(*, embedding, utterance_id, timestamp) -> bool` — `backend/app/services/speaker_service.py:522` — maintains `session.counterparty_candidates` (rolling 30s window, max 5), `session.counterparty_cluster_embedding` (running mean, normalized), `session.counterparty_cluster_promoted_at`; uses `settings.COUNTERPARTY_CLUSTER_THRESHOLD`; "user_confirmed_at_least_once" gate checks `session.user_embedding`, `speaker_confidence_history`, and `session.speaker_mapping`
  - `_record_label(label, similarity, duration_ms, timestamp)` — `backend/app/services/speaker_service.py:598` — appends to `session.speaker_confidence_history`; increments `session.session_metrics["speaker_user_count"|"speaker_counterparty_count"|"speaker_unknown_count"]`

**Data shapes produced**:
- `speaker_confidence_history` entries: `{"speaker": str, "timestamp": float, "confidence": float|None, "duration"|"duration_ms": float|int}`
- `speaker_timeline` entries: `{"speaker": str, "timestamp": float}`
- `counterparty_candidates` entries: `{"embedding": Tensor, "utterance_id": str, "timestamp": float}`

**Gotchas**: Comment at `speaker_service.py:216-220` documents a past design change (middle-slice → first-slice for embedding because middle slices broke acoustic context for short utterances). Two classification code paths (`_classify_segment` legacy vs `classify_utterance` newer) coexist — check which is actually wired up in `negotiation_engine.py` before editing either.

---

## speaker_mapping_service.py

**Purpose**: Maps Deepgram-diarized speaker IDs (`diarized_speaker_id`) to semantic roles (`"user"`, `"counterparty"`, `"unknown"`) using a state machine (`unmapped → calibrating → mapped → degraded`) backed by SpeechBrain verification against a reference embedding. Used by `negotiation_engine.py:44` and `listener_agent.py:50`.

- `class SpeakerMappingService` — `backend/app/services/speaker_mapping_service.py:17`
  - `__init__(session)` — `backend/app/services/speaker_mapping_service.py:18`
  - `begin_calibration()` — `backend/app/services/speaker_mapping_service.py:21` — transitions `unmapped → calibrating`
  - `_transition(state)` — `backend/app/services/speaker_mapping_service.py:25` — records to `session.mapping_state_transitions` and `session_store.record_speaker_mapping_event`
  - `async label_diarized_turns(turns, utterance_audio) -> list[dict]` — `backend/app/services/speaker_mapping_service.py:33` — main entry point; calls `_attach_turn_audio`, `_mark_third_speakers`, then per-turn dispatches to `_handle_degraded_mapping` or `_label_non_degraded_turn`; logs via `log_speaker_debug("MAPPING_START"/"MAPPING_DECISION", ...)`
  - `async _label_non_degraded_turn(diarized_id, turn, *, is_ephemeral) -> str` — `backend/app/services/speaker_mapping_service.py:85` — core routing logic: ephemeral→`_classify_ephemeral_turn`; mapped "user"→`_recheck_user_mapping`; mapped "counterparty"→"counterparty"; else attempts user binding if `turn_duration >= settings.SPEECHBRAIN_MIN_BIND_SECONDS`, or stable-counterparty promotion via `_is_stable_counterparty_candidate`
  - `async _handle_degraded_mapping(diarized_id, turn, *, is_ephemeral) -> str` — `backend/app/services/speaker_mapping_service.py:111` — in "degraded" state, only re-verifies existing "user" mapping via `settings.SPEECHBRAIN_RECHECK_THRESHOLD`
  - `async _attempt_user_binding(diarized_id, turn) -> str` — `backend/app/services/speaker_mapping_service.py:126` — verifies against `settings.SPEECHBRAIN_ACCEPT_THRESHOLD`; on accept, evicts any prior `"user"` mapping, sets `session.speaker_mapping[diarized_id]="user"`, `speaker_mapping_confidence`, `speaker_mapping_locked_at`, `speaker_mapping_last_validated_at`, transitions to `"mapped"`; on reject transitions to `"calibrating"`
  - `async _classify_ephemeral_turn(turn) -> str` — `backend/app/services/speaker_mapping_service.py:143` — threshold depends on whether a "user" is already mapped (`SPEECHBRAIN_ACCEPT_THRESHOLD` vs `SPEECHBRAIN_RECHECK_THRESHOLD`); returns "user"/"counterparty"(strong_reject)/"unknown"(ambiguous or default)
  - `async _recheck_user_mapping(diarized_id, turn) -> str` — `backend/app/services/speaker_mapping_service.py:158` — short turns (< `SPEECHBRAIN_MIN_BIND_SECONDS`) auto-pass as "user"; otherwise re-verify, calling `record_contradiction` on `strong_reject`
  - `async _verify_user_candidate(turn, *, threshold) -> dict` — `backend/app/services/speaker_mapping_service.py:180` — calls `speechbrain_service.verify_against_embedding(session.speechbrain_reference_embedding, turn_audio)`; requires `capability_registry.speechbrain().available`, `session.speechbrain_reference_embedding is not None`, `turn_duration >= SPEECHBRAIN_MIN_BIND_SECONDS`, non-empty audio — else returns `{"accepted": False, "provider": "none", ...}` and logs `"SPEECHBRAIN_VERIFY_SKIPPED"`. Increments `session.speechbrain_verification_attempts`, `session_metrics["speechbrain_verification_calls"]`, `speechbrain_verification_successes/failures`, and updates `session.speechbrain_last_result`
  - `_attach_turn_audio(turns, utterance_audio) -> list[dict]` — `backend/app/services/speaker_mapping_service.py:263` — slices `utterance_audio` per turn using `start_time`/`end_time` at `16000*2` bytes/sec, adds `"turn_audio"` key
  - `_mark_third_speakers(turns)` — `backend/app/services/speaker_mapping_service.py:278` — caps distinct speakers to 2; extras added to `session.permanent_unknown_speaker_ids`
  - `_remember_turn(diarized_id, turn_duration)` — `backend/app/services/speaker_mapping_service.py:294` — updates `session.speaker_embedding_cache[diarized_id] = {"seen", "total_duration", "last_seen_at"}`
  - `_is_stable_counterparty_candidate(diarized_id) -> bool` — `backend/app/services/speaker_mapping_service.py:303` — true if `total_duration >= SPEECHBRAIN_MIN_BIND_SECONDS` or `seen >= 2`
  - `_mapped_id(role) -> str|None` — `backend/app/services/speaker_mapping_service.py:313`
  - `@staticmethod _is_ephemeral_diarized_id(diarized_id) -> bool` — `backend/app/services/speaker_mapping_service.py:319` — true for `{"", "unknown", "user", "counterparty", "none", "null"}` (case/whitespace-insensitive)
  - `_turn_duration(turn) -> float` — `backend/app/services/speaker_mapping_service.py:324`
  - `record_contradiction(diarized_id, evidence)` — `backend/app/services/speaker_mapping_service.py:327` — appends to `session.mapping_contradictions[diarized_id]`, prunes entries older than `settings.SPEAKER_RECHECK_WINDOW_SECONDS`; **2+ contradictions within window → transitions session to `"degraded"`**

**Key data structures**:
- `turns`: list of dicts with `diarized_speaker_id`, `start_time`, `end_time`, `text`, plus added `turn_audio` (bytes) and `speaker` (output)
- `session.speaker_mapping`: `dict[diarized_id -> "user"|"counterparty"]`
- `session.mapping_contradictions`: `dict[diarized_id -> list[{"timestamp": float, "evidence": float}]]`
- `session.speaker_embedding_cache`: `dict[diarized_id -> {"seen": int, "total_duration": float, "last_seen_at": float}]`
- `session.speechbrain_last_result`: `{"accepted","confidence","reason","provider","ambiguous","strong_reject","timestamp"}`

**Gotchas**: State machine has 4 states (`unmapped`, `calibrating`, `mapped`, `degraded`) only `degraded` and the others appear in code — `_transition` is the only mutator. SpeechBrain verification is silently skipped (returns `accepted=False, provider="none"`) if capability not available — this is logged via `log_speaker_debug` not raised.

---

## speaker_enrollment.py

**Purpose**: Live, quality-gated voice enrollment flow for SpeechBrain ECAPA-TDNN — captures audio while user reads a fixed script, evaluates volume/speech-duration/embedding-stability every second, and on success populates `session.user_embedding` / `session.speechbrain_reference_embedding`. Used by `negotiation_engine.py:305` (lazy import).

- `ENROLLMENT_SCRIPT` constant (the spoken passage) — `backend/app/services/speaker_enrollment.py:23-28`
- `class EnrollmentState(str, Enum)` — `backend/app/services/speaker_enrollment.py:31` — values: `IDLE`, `CAPTURING`, `COMPLETE`, `FAILED`
- `class SpeakerEnrollmentService` — `backend/app/services/speaker_enrollment.py:38`
  - Constants: `SAMPLE_RATE=16000`, `BYTES_PER_SAMPLE=2`, `MIN_DB_THRESHOLD=settings.ENROLLMENT_MIN_DB`, `EVALUATION_INTERVAL_SECONDS=1.0` — `backend/app/services/speaker_enrollment.py:39-42`
  - `__init__(session)` — `backend/app/services/speaker_enrollment.py:44`
  - `async start_enrollment() -> dict` — `backend/app/services/speaker_enrollment.py:52` — calls `self.cleanup()`, sets `session.speechbrain_profile_state="collecting"`→`"enrolling"`, `session.speaker_mode="auto"`. Returns `ENROLLMENT_FAILED` (error=`"provider_disabled"`) if `not settings.SPEECHBRAIN_ENABLED`; returns `ENROLLMENT_FAILED` (error=`"provider_init_failed"`) if `speechbrain_service.probe_capability()` fails; else returns `ENROLLMENT_STARTED` with `script=ENROLLMENT_SCRIPT`
  - `async process_audio(chunk: bytes) -> Optional[dict]` — `backend/app/services/speaker_enrollment.py:110` — accumulates `audio_buffer`; no-op unless state==`CAPTURING`; times out via `settings.SPEECHBRAIN_ENROLLMENT_TIMEOUT_SECONDS` → `_fail("timeout", ...)`; throttled to once per `EVALUATION_INTERVAL_SECONDS`; checks `db_level >= MIN_DB_THRESHOLD`, `effective_speech >= settings.SPEECHBRAIN_ENROLLMENT_MIN_EFFECTIVE_SPEECH_SECONDS`, then extracts embedding and checks `stability >= settings.SPEECHBRAIN_ENROLLMENT_STABILITY_THRESHOLD`; on success sets `session.speechbrain_reference_embedding`, `session.user_embedding`, `session.enrollment_audio`, `session.speechbrain_profile_state="ready"`, `session.speaker_recognition_enabled=True`, `session.speaker_mode="auto"`, `state=COMPLETE`
  - `cleanup()` — `backend/app/services/speaker_enrollment.py:194` — calls `speechbrain_service.cleanup_session_state(session)`, resets `state=IDLE`, `speechbrain_profile_state="none"`
  - `_progress(message, db_level, stability=None, effective_speech=None) -> dict` — `backend/app/services/speaker_enrollment.py:199` — builds `ENROLLMENT_PROGRESS` message
  - `_fail(error, message) -> dict` — `backend/app/services/speaker_enrollment.py:218` — builds `ENROLLMENT_FAILED`, calls `speechbrain_service.cleanup_session_state`
  - `_safe_db_level() -> float` — `backend/app/services/speaker_enrollment.py:245`
  - `_calculate_db_level(audio: bytes) -> float` — `backend/app/services/speaker_enrollment.py:253` — RMS-based dBFS via torch
  - `_calculate_effective_speech_duration(audio: bytes) -> float` — `backend/app/services/speaker_enrollment.py:264` — frame-based VAD using `settings.ENROLLMENT_SPEECH_FRAME_MS`, `ENROLLMENT_SPEECH_FRAME_RMS_THRESHOLD`, `ENROLLMENT_SPEECH_HANGOVER_FRAMES`
  - `_embedding_stability(reference_embedding) -> float` — `backend/app/services/speaker_enrollment.py:286` — cosine similarity between full-buffer embedding and tail-slice embedding (tail = `max(SPEECHBRAIN_MIN_BIND_SECONDS, 3.0)` seconds)

**Message types produced** (all `{"type": ..., "payload": {...}}`):
- `ENROLLMENT_STARTED` — payload includes `script`, `sample_rate`, `message`
- `ENROLLMENT_PROGRESS` — payload includes `feedback` (one of `"LISTENING"|"LOW_VOLUME"|"MORE_SPEECH"|"UNSTABLE_SAMPLE"`), `feedback_message`, `db_level`, `stability`, `effective_speech_duration`
- `ENROLLMENT_COMPLETE` — payload includes `success=True`, `speaker_mode="auto"`, `speechbrain_profile_state`, `feedback="READY"`, `db_level`, `effective_speech_duration`, `stability`
- `ENROLLMENT_FAILED` — payload includes `success=False`, `error` (`"provider_disabled"|"provider_init_failed"|"timeout"|"provider_error"`), `can_retry` (bool), `message`

---

## azure_speaker_service.py

**Purpose**: Azure Cognitive Services "text-independent speaker verification" REST client (raw `urllib`-based, no SDK dependency). Defines `AzureSpeakerVerificationService` + `azure_speaker_verification_service` singleton. **Appears UNUSED / dead code** — no other file in `backend/app` imports `azure_speaker_service` or `AzureSpeakerVerificationService` (grep across `app/` returned zero hits besides its own definition). Likely a vestigial alternative-provider implementation alongside SpeechBrain/Eagle.

- `@dataclass AzureVerificationResult` — `backend/app/services/azure_speaker_service.py:18` — fields: `accepted: bool`, `confidence: float|None`, `profile_id: str|None`, `reason: str`, `provider="azure"`
- `class AzureSpeakerVerificationService` — `backend/app/services/azure_speaker_service.py:26`
  - `__init__()` — `backend/app/services/azure_speaker_service.py:27` — creates `ssl.create_default_context()`
  - `enabled` property — `backend/app/services/azure_speaker_service.py:30` — gated on `settings.AZURE_SPEAKER_VERIFICATION_ENABLED`, `AZURE_SPEAKER_SUBSCRIPTION_KEY`, `AZURE_SPEAKER_REGION`
  - `build_endpoint() -> str` — `backend/app/services/azure_speaker_service.py:38` — `https://{region}.api.cognitive.microsoft.com`
  - `_request(method, path, *, query=None, body=None, content_type="application/json")` — `backend/app/services/azure_speaker_service.py:41` — raw urllib request w/ `Ocp-Apim-Subscription-Key` header, timeout `settings.AZURE_SPEAKER_TIMEOUT_SECONDS`
  - `probe_capability() -> tuple[bool,str]` — `backend/app/services/azure_speaker_service.py:85` — GETs profile list endpoint
  - `create_profile() -> str` — `backend/app/services/azure_speaker_service.py:99` — POST to create a verification profile, returns `profileId`
  - `enroll_profile(profile_id, wav_audio, *, ignore_min_length=False) -> dict` — `backend/app/services/azure_speaker_service.py:113`
  - `verify_profile(profile_id, wav_audio) -> AzureVerificationResult` — `backend/app/services/azure_speaker_service.py:128`
  - Module singleton: `azure_speaker_verification_service = AzureSpeakerVerificationService()` — `backend/app/services/azure_speaker_service.py:160`

All endpoints use `query={"api-version": settings.AZURE_SPEAKER_API_VERSION}`.

---

## speechbrain_service.py

**Purpose**: Core ECAPA-TDNN (`speechbrain/spkrec-ecapa-voxceleb`) speaker-embedding/verification provider — lazy-loads the model singleton, extracts L2-normalized embeddings, and verifies candidate audio against a reference embedding with ambiguous/strong-reject zones. Used by `speaker_enrollment.py`, `speaker_mapping_service.py`, `speaker_service.py`, `negotiation_engine.py:45`, and `app/main.py:45`.

- `@dataclass SpeechBrainVerificationResult` — `backend/app/services/speechbrain_service.py:16` — fields: `accepted`, `confidence`, `reason`, `provider="speechbrain"`, `ambiguous=False`, `strong_reject=False`
- `class SpeechBrainService` — `backend/app/services/speechbrain_service.py:25`
  - `MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"`, `SAMPLE_RATE = 16000` — `backend/app/services/speechbrain_service.py:26-27`
  - `__init__()` — `backend/app/services/speechbrain_service.py:29` — `threading.Lock`, lazy `_verifier`, `_loaded_at`
  - `enabled` property — `backend/app/services/speechbrain_service.py:35` — `settings.SPEECHBRAIN_ENABLED`
  - `_device() -> str` — `backend/app/services/speechbrain_service.py:38` — `settings.SPEECHBRAIN_DEVICE or "cpu"`
  - `_ensure_loaded() -> Any` — `backend/app/services/speechbrain_service.py:41` — thread-locked lazy load of `SpeakerRecognition.from_hparams(...)` saved to `pretrained_models/speechbrain-spkrec-ecapa-voxceleb`
  - `probe_capability() -> tuple[bool,str]` — `backend/app/services/speechbrain_service.py:62` — lightweight import-only check (does not load weights); returns `(False, "speechbrain_disabled")` if disabled
  - `extract_embedding(pcm: bytes) -> Tensor` — `backend/app/services/speechbrain_service.py:73` — raises `ValueError("empty_audio")` if empty waveform
  - `verify_against_embedding(reference_embedding, pcm: bytes) -> SpeechBrainVerificationResult` — `backend/app/services/speechbrain_service.py:83` — computes cosine similarity clamped [0,1]; `ambiguous` = `settings.SPEECHBRAIN_AMBIGUOUS_LOW <= confidence <= SPEECHBRAIN_AMBIGUOUS_HIGH`; `strong_reject` = `confidence < SPEECHBRAIN_AMBIGUOUS_LOW`; `accepted` = `confidence >= settings.SPEECHBRAIN_ACCEPT_THRESHOLD`; returns `reason` in `{"accepted","ambiguous","strong_reject","rejected"}`
  - `cleanup_session_state(session: Any)` — `backend/app/services/speechbrain_service.py:120` — nulls `session.speechbrain_reference_embedding`, `speechbrain_last_result`, `user_embedding`; `gc.collect()` + `torch.cuda.empty_cache()` (best-effort)
  - `_pcm_to_waveform_tensor(pcm: bytes) -> Tensor` — `backend/app/services/speechbrain_service.py:131` — int16 → float32 [-1,1], shape `(1, N)`; returns `(1,0)` zeros tensor for empty input
  - `load_audio_file(path: str) -> bytes` — `backend/app/services/speechbrain_service.py:139` — torchaudio load, downmix to mono, resample to 16kHz, returns int16 PCM bytes
  - `@staticmethod _normalize_embedding(embedding) -> Tensor` — `backend/app/services/speechbrain_service.py:152` — flattens, L2-normalizes (returns unnormalized zero tensor if norm==0)
  - Module singleton: `speechbrain_service = SpeechBrainService()` — `backend/app/services/speechbrain_service.py:164`

**Settings referenced**: `SPEECHBRAIN_ENABLED`, `SPEECHBRAIN_DEVICE`, `SPEECHBRAIN_AMBIGUOUS_LOW`, `SPEECHBRAIN_AMBIGUOUS_HIGH`, `SPEECHBRAIN_ACCEPT_THRESHOLD`.

---

## voice_encoder.py

**Purpose**: Singleton wrapper around the **Resemblyzer** `VoiceEncoder` (256-dim embeddings). **Appears UNUSED / dead code** — grep for `voice_encoder`/`VoiceEncoder` across `app/` found zero references outside this file. Likely superseded by `speechbrain_service.py` (ECAPA-TDNN) as the active embedding provider.

- `class VoiceEncoder` — `backend/app/services/voice_encoder.py:19`
  - `__new__(cls)` — `backend/app/services/voice_encoder.py:33` — singleton via `_instance`
  - `@classmethod get_instance() -> VoiceEncoder` — `backend/app/services/voice_encoder.py:40` — lazy-loads model on first call
  - `_load_model()` — `backend/app/services/voice_encoder.py:60` — `from resemblyzer import VoiceEncoder as ResemblyzerEncoder`
  - `embed_utterance(audio_pcm: bytes) -> np.ndarray` — `backend/app/services/voice_encoder.py:78` — returns L2-normalized 256-dim float32 array; raises `RuntimeError` if model not loaded
  - `_bytes_to_numpy(audio_bytes: bytes) -> np.ndarray` — `backend/app/services/voice_encoder.py:125` — int16 → float32 [-1,1] via `np.frombuffer`; raises `ValueError` on empty input

---

## session_store.py

**Purpose**: SQLite-backed (WAL mode) persistence for negotiation sessions, transcript turns, research/advisor/vision/speaker-mapping events, and Clerk/JWT auth tables (`users`, `refresh_tokens`). Single global instance `session_store = SessionStore(settings.SESSION_DB_PATH)` at `backend/app/services/session_store.py:388`. Used pervasively: `main.py`, `negotiation_engine.py`, `speaker_mapping_service.py`, `listener_agent.py`, `connection_manager.py`, `gemini_client.py`, `companion_runtime.py`, `api/websocket.py`.

- `_json_dumps(payload: Any) -> str` — `backend/app/services/session_store.py:17` — `json.dumps(..., ensure_ascii=True, default=str)`
- `class SessionStore` — `backend/app/services/session_store.py:21`
  - `__init__(db_path: str)` — `backend/app/services/session_store.py:22` — creates parent dir, `threading.Lock`, `_initialized=False`
  - `initialize()` — `backend/app/services/session_store.py:28` — idempotent (checked via lock + flag); creates tables `sessions`, `turns`, `research_events`, `advisor_events`, `speaker_mapping_events`, `vision_events`, `users`, `refresh_tokens`; runs additive `ALTER TABLE` migrations for `final_summary_json`, `language_profile`, `display_language`, `per_source_language_json` (comment notes these are reversible/inert if `MULTILANG_ENABLED` off — `backend/app/services/session_store.py:112-114`)
  - `persist_session(session, *, ended=False)` — `backend/app/services/session_store.py:148` — UPSERT into `sessions`; truncates `display_transcript_turns`/`research_history`/`advisor_history`/`vision_history` to `settings.TRANSCRIPT_HISTORY_LIMIT`/`RESEARCH_HISTORY_LIMIT`; builds `context_payload` dict (see below); sets `session.last_persisted_at = now`
  - `record_turn(session_id, turn: dict, *, language=None)` — `backend/app/services/session_store.py:231` — INSERT into `turns`; turn id falls back to `f"turn_{int(time.time()*1000)}"`
  - `record_research_event(session_id, query, status, payload)` — `backend/app/services/session_store.py:255`
  - `record_advisor_event(session_id, event_type, payload)` — `backend/app/services/session_store.py:273`
  - `record_speaker_mapping_event(session_id, payload)` — `backend/app/services/session_store.py:284` — called by `speaker_mapping_service._transition`
  - `record_vision_event(session_id, payload)` — `backend/app/services/session_store.py:295`
  - `load_session_bundle(session_id) -> dict|None` — `backend/app/services/session_store.py:306` — full session reconstruction: session row + last N turns/research/advisor/vision events
  - `list_sessions(limit=20) -> list[dict]` — `backend/app/services/session_store.py:364` — ordered by `updated_at DESC`; extracts `source_mode`/`meeting_binding` from `context_json`

**`sessions` table columns** (key ones): `session_id` (PK), `state`, `consent_version`, `consent_mode`, `started_at/updated_at/ended_at`, `language`, `response_language`, `context_json`, `final_summary_json`, `transcript_json`, `speaker_mapping_json`, `last_context_json`, `research_json`, `advisor_json`, `vision_json`, `metrics_json`, `language_profile`, `display_language`, `per_source_language_json` — `backend/app/services/session_store.py:36-122`

**`context_payload` dict shape** (stored in `context_json`) — `backend/app/services/session_store.py:155-172`: `user_context`, `last_context`, `degraded_mode`, `source_mode`, `meeting_binding`, `audio_sources_active`, `hold_state`, `capture_health`, `capture_preset`, `companion_quality_mode`, `selected_output_device: {device_id, label}`, `degraded_reasons`, `resume_token`.

**`turns` table columns**: `session_id`, `turn_id`, `speaker`, `language`, `text`, `timestamp_ms`, `source`, `diarized_speaker_id`, `transcription_confidence`, `metadata_json` (full turn dict) — `backend/app/services/session_store.py:57-69`.

---

## connection_manager.py

**Purpose**: Tracks active and "suspended" (grace-period reconnect) WebSocket sessions; owns session lifecycle cleanup (listener agent stop, Gemini live-session close, persistence, trace/log finalization). Singleton `connection_manager = ConnectionManager()` at `backend/app/services/connection_manager.py:195`. Used by `main.py` and `api/websocket.py`.

- `class ConnectionManager` — `backend/app/services/connection_manager.py:18`
  - `__init__()` — `backend/app/services/connection_manager.py:21` — `active_connections: dict[session_id -> {"websocket","session"}]`, `suspended_sessions: dict[session_id -> {"session","cleanup_task","suspended_at"}]`
  - `async register(websocket, session_id, session)` — `backend/app/services/connection_manager.py:25` — pops/cancels any suspended cleanup task for this session, registers active connection
  - `async broadcast_backend_ready()` — `backend/app/services/connection_manager.py:39` — sends `{"type": "BACKEND_READY", "payload": readiness.snapshot()}` to all active connections (lazy-imports `app.services.readiness`)
  - `async unregister(session_id, preserve_runtime=False)` — `backend/app/services/connection_manager.py:58` — always calls `session_store.persist_session(session, ended=False)`; if `preserve_runtime and session.state.value=="ACTIVE" and session.session_resumable`, moves session to `suspended_sessions` and schedules `_cleanup_after_grace`; else calls `_finalize_session_cleanup`
  - `async _cleanup_after_grace(session_id, session)` — `backend/app/services/connection_manager.py:88` — `asyncio.sleep(settings.SESSION_RESUME_GRACE_SECONDS)`, then finalizes (catches `CancelledError` for early resume)
  - `async _finalize_session_cleanup(session)` — `backend/app/services/connection_manager.py:98` — stops `session.listener_agent`; closes Gemini live session via `_close_gemini_session`; cancels tasks `live_session_receive_task`, `live_session_keepalive_task`, `live_session_monitor_task`, `live_reconnect_task`, `live_preconnect_task`; `session_store.persist_session(session, ended=session.state.value=="IDLE")`; copies `session.vision_pro_call_count` into `session_metrics["vision_pro_call_count"]`; records `session_finalized` trace event; calls `close_session_logger`/`close_session_trace`; sets `session.trace_report_path`
  - `async _close_gemini_session(session)` — `backend/app/services/connection_manager.py:152` — prefers `session.live_session_cm.__aexit__`, falls back to `.close()` or `.aio.close()`; always nulls `live_session`/`live_session_cm`
  - `get_session(session_id) -> Optional[NegotiationSession]` — `backend/app/services/connection_manager.py:169` — checks active then suspended
  - `get_websocket(session_id) -> Optional[WebSocket]` — `backend/app/services/connection_manager.py:178`
  - `get_all_sessions() -> dict[str, NegotiationSession]` — `backend/app/services/connection_manager.py:184` — merges active + suspended (active takes priority)
  - `active_session_count` property — `backend/app/services/connection_manager.py:190`

**Gotchas**: `unregister` ALWAYS persists even when suspending (so a crash during grace period doesn't lose data). `register` cancels any in-flight suspension cleanup task — reconnect "rescues" a session before its grace timer fires.

---

## deepgram_stream.py

**Purpose**: Deepgram Nova-3 live streaming STT. Module-level registry `_SESSIONS: dict[session_id -> DeepgramStreamSession]` at `backend/app/services/deepgram_stream.py:21`. One `DeepgramLiveClient` websocket per `(session, source)` where `source` is `"local_mic"`/`"remote_app"` etc. Used heavily by `negotiation_engine.py` (lines ~1130, 1675, 2430) and `companion_runtime.py` (lines ~410, 524, 829, 1050).

- `class DeepgramStreamSession` — `backend/app/services/deepgram_stream.py:24`
  - `__init__(session_id, api_key)` — `backend/app/services/deepgram_stream.py:27` — `_clients: dict[source -> DeepgramLiveClient]`, `_active_language: dict[source->lang]`, `_callbacks`, `_utterance_end_callbacks`
  - `@classmethod get_or_create(session_id, api_key) -> DeepgramStreamSession` — `backend/app/services/deepgram_stream.py:42`
  - `@classmethod get(session_id) -> Optional[...]` — `backend/app/services/deepgram_stream.py:48`
  - `@classmethod async destroy(session_id)` — `backend/app/services/deepgram_stream.py:52` — pops from `_SESSIONS`, calls `stop_all()`
  - `register_callback(source, callback)` — `backend/app/services/deepgram_stream.py:59` — `callback(text, is_final, speech_final, confidence, detected_language=...)`
  - `register_utterance_end_callback(source, callback)` — `backend/app/services/deepgram_stream.py:63` — `callback()` for word-gap end-of-turn (UtteranceEnd events)
  - `async push(source, pcm_bytes, language="en-US")` — `backend/app/services/deepgram_stream.py:69` — core entry; if `_failed_{source}` flag set (set dynamically via `setattr`), drops silently; **tears down and rebuilds the client if the requested language differs from `_active_language[source]`** (atomic language switch); on client creation failure with HTTP 400/401/403 in the error string, sets `_failed_{source}=True` permanently (falls back to batch STT) — `backend/app/services/deepgram_stream.py:125-131`
  - `async reset_source(source)` — `backend/app/services/deepgram_stream.py:135` — used by `SET_LANGUAGE_PROFILE` handler to force reconnect
  - `async reset_all()` — `backend/app/services/deepgram_stream.py:149`
  - `async stop_all()` — `backend/app/services/deepgram_stream.py:156`
- `class DeepgramLiveClient` — `backend/app/services/deepgram_stream.py:163`
  - `WS_URL = "wss://api.deepgram.com/v1/listen"` — `backend/app/services/deepgram_stream.py:166`
  - `__init__(api_key, source, on_transcript, *, language="en-US", model="nova-3", sample_rate=16000, endpointing_ms=300, utterance_end_ms=0, on_utterance_end=None, keepalive_seconds=3.0)` — `backend/app/services/deepgram_stream.py:168` — `_send_queue: asyncio.Queue(maxsize=300)`
  - `_build_url() -> str` — `backend/app/services/deepgram_stream.py:200` — params: `model, encoding=linear16, sample_rate, channels=1, interim_results=true, endpointing, smart_format=true, language`; **comment notes `vad_events` previously caused HTTP 400 and is deliberately omitted** — `backend/app/services/deepgram_stream.py:201,215-216`; `utterance_end_ms` only added if `>= 1000`
  - `async start()` — `backend/app/services/deepgram_stream.py:221` — `websockets.connect(..., compression=None, open_timeout=10)` — **comment: `compression=None` required, Deepgram rejects permessage-deflate with HTTP 400** — `backend/app/services/deepgram_stream.py:230`; spawns `_recv_loop` and `_send_loop` tasks
  - `async stop()` — `backend/app/services/deepgram_stream.py:245` — sends `{"type":"CloseStream"}`, sleeps 50ms, closes ws, cancels tasks
  - `push_pcm(pcm_bytes)` — `backend/app/services/deepgram_stream.py:264` — thread-safe queue put; if `_ws is None` (dead), schedules `_reconnect()` via `ensure_future` and drops the chunk
  - `async _reconnect()` — `backend/app/services/deepgram_stream.py:286` — restarts the websocket after idle close; clears send queue first (avoids replaying stale audio)
  - `async _send_loop()` — `backend/app/services/deepgram_stream.py:309` — drains queue with 0.5s timeout; sends `KeepAlive` JSON if idle `>= keepalive_seconds`; marks `_ws=None` on send error (triggers reconnect)
  - `async _recv_loop()` — `backend/app/services/deepgram_stream.py:338` — 5s recv timeout loop; dispatches to `_handle_event`
  - `async _handle_event(event: dict)` — `backend/app/services/deepgram_stream.py:355` — handles `"Results"` (extracts `transcript`, `is_final`, `speech_final`, `confidence`, `detected_language` — falls back to `self.language` unless it's the `"multi"` sentinel, see comment `:368-372`), `"SpeechStarted"`, `"UtteranceEnd"` (invokes `on_utterance_end`), `"Error"`. Calls `on_transcript(..., detected_language=...)` with `TypeError` fallback to legacy positional-only signature — `backend/app/services/deepgram_stream.py:386-393`

**Gotchas**: `_failed_{source}` is a dynamically-set instance attribute (not declared in `__init__`) — search for `getattr(self, failed_key, ...)` / `setattr(self, failed_key, True)`. Permanent-failure detection is string-matching on exception text (`"400"`, `"401"`, `"403"`).

---

## eagle_service.py

**Purpose**: Picovoice Eagle speaker-recognition provider wrapper (`pveagle` module, lazy-imported). Defines `PicovoiceEagleService` + module singleton `eagle_service`. **Appears UNUSED / dead code** — grep across `app/` found zero references to `eagle_service`/`PicovoiceEagleService` outside this file. Likely another vestigial alternative provider (alongside `azure_speaker_service.py`/`voice_encoder.py`).

- `@dataclass EagleVerificationResult` — `backend/app/services/eagle_service.py:17` — fields: `accepted`, `confidence`, `profile_id`, `reason`, `provider="eagle"`, `ambiguous=False`, `strong_reject=False`
- `class PicovoiceEagleService` — `backend/app/services/eagle_service.py:27`
  - `enabled` property — `backend/app/services/eagle_service.py:31` — `settings.PICOVOICE_EAGLE_ENABLED and settings.PICOVOICE_ACCESS_KEY`
  - `_load_module()` — `backend/app/services/eagle_service.py:35` — `importlib.import_module("pveagle")`
  - `_call_release(obj)` — `backend/app/services/eagle_service.py:40` — calls `.delete()` or `.release()` if present
  - `probe_capability() -> tuple[bool,str]` — `backend/app/services/eagle_service.py:49`
  - `create_profiler() -> Any` — `backend/app/services/eagle_service.py:59` — handles both functional (`create_profiler`) and class (`EagleProfiler`) pveagle APIs
  - `create_recognizer(speaker_profiles) -> Any` — `backend/app/services/eagle_service.py:72` — same dual-API handling for `Eagle`
  - `release_profiler(profiler)` / `release_recognizer(recognizer)` — `backend/app/services/eagle_service.py:91`/`94`
  - `sample_rate(obj) -> int` — `backend/app/services/eagle_service.py:97` (default 16000)
  - `frame_length(recognizer) -> int` — `backend/app/services/eagle_service.py:108` (default 512)
  - `min_enroll_samples(profiler) -> int` — `backend/app/services/eagle_service.py:119` (default 16000)
  - `enroll(profiler, pcm) -> dict` — `backend/app/services/eagle_service.py:130` — returns `{"percentage": float, "feedback": str}`
  - `export_profile(profiler) -> bytes` — `backend/app/services/eagle_service.py:143`
  - `verify_profile(recognizer, pcm) -> EagleVerificationResult` — `backend/app/services/eagle_service.py:153` — frame-by-frame `recognizer.process(frame)`, takes `max(scores)` as confidence; thresholds: `PICOVOICE_EAGLE_AMBIGUOUS_LOW/HIGH`, `PICOVOICE_EAGLE_ACCEPT_THRESHOLD`
  - `@staticmethod _extract_score(result) -> float|None` — `backend/app/services/eagle_service.py:208` — defensive extraction across many possible pveagle return shapes (scalar, list/tuple, dict with `scores/score/similarity/similarities`, or object attrs)
  - Module singleton: `eagle_service = PicovoiceEagleService()` — `backend/app/services/eagle_service.py:239`

---

## translation.py

**Purpose**: Lightweight on-demand translation helper for the multilanguage adaptation feature — used on the "Pro tactical-advice" path to translate non-English transcript/query into English before calling `gemini-2.5-pro`, then translate the answer back. Gated entirely behind `settings.MULTILANG_ENABLED` at call sites (this module sits idle if off — per module docstring `backend/app/services/translation.py:9-11`). Used by `gemini_client.py:697` and `:957` (lazy imports).

- `_is_english(code: Optional[str]) -> bool` — `backend/app/services/translation.py:26` — `True` if code is falsy or root is `"en"`
- `_cache_key(text, src, dst) -> str` — `backend/app/services/translation.py:32` — `sha256(text)[:16] + "|" + src + "|" + dst`
- Module-level `_CACHE: OrderedDict[str,str]` — `backend/app/services/translation.py:39` — tiny LRU, capped at `max(50, settings.TRANSLATION_CACHE_MAX_ENTRIES)`
- `_cache_get(key)` / `_cache_put(key, value)` — `backend/app/services/translation.py:42`/`49`
- `clear_cache()` — `backend/app/services/translation.py:56` — test hook
- `async translate_text(text, source_lang, target_lang) -> str` — `backend/app/services/translation.py:61` — main entry. Returns original text unchanged on:
  - empty/whitespace text
  - `source_lang` in `{"multi","auto","unknown",""}` (case-insensitive) — comment explains these are Deepgram code-switch sentinels, not real BCP-47 codes — `backend/app/services/translation.py:74-80`
  - both source and target are English
  - source/target share the same root language code
  - any provider error/timeout (`settings.TRANSLATION_TIMEOUT_SECONDS`)
  
  **Provider routing**: if `not runtime_config.is_google(SLOT_FAST_TEXT)`, routes through `app.providers.text_client.generate(SLOT_FAST_TEXT, ...)` (provider-agnostic path) — `backend/app/services/translation.py:104-124`; otherwise uses `google.genai` directly with `settings.TRANSLATION_MODEL`, supporting both Vertex AI (`runtime_config.google_use_vertex()`) and direct API key paths — `backend/app/services/translation.py:126-178`. Successful translations are cached via `_cache_put`.

**Settings referenced**: `MULTILANG_ENABLED` (caller-side gate), `TRANSLATION_CACHE_MAX_ENTRIES`, `TRANSLATION_TIMEOUT_SECONDS`, `TRANSLATION_MODEL`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`.

---

## ask_transcript_state.py

**Purpose**: Pure-function state helpers for the "Ask AI" feature's transcript-candidate reconciliation — multiple STT sources (Deepgram, Gemini live input, snapshot/batch transcription) race to provide the text of the user's spoken question; this module ranks/dedupes/filters candidates and detects cross-contamination artifacts. Used by `negotiation_engine.py:33-38`, `gemini_client.py:28-33`, `companion_runtime.py:15-21`.

- `SOURCE_PRIORITY: dict[str,int]` — `backend/app/services/ask_transcript_state.py:8-16` — `{"partial":10, "snapshot_partial":15, "gemini_live_input":30, "snapshot_transcription":40, "desktop_ask_ai":40, "batch_transcription":45, "deepgram_ask":70}` (higher = preferred)
- `_SHORT_PARTIAL_FILLERS: set[str]` — `backend/app/services/ask_transcript_state.py:18-28` — `{"ah","eh","er","hm","hmm","uh","um","de","ex"}`
- `_words(text) -> list[str]` — `backend/app/services/ask_transcript_state.py:31` — lowercase alphanumeric word tokens
- `_latin_ratio(text) -> float` — `backend/app/services/ask_transcript_state.py:35` — fraction of alphabetic chars that are a-z
- `_same_start(left, right, *, words=3) -> bool` — `backend/app/services/ask_transcript_state.py:46` — compares first N word-tokens
- `_same_text_family(left, right) -> bool` — `backend/app/services/ask_transcript_state.py:55` — prefix match or `_same_start`
- `_current_reference_texts(capture) -> list[str]` — `backend/app/services/ask_transcript_state.py:67` — pulls non-short-partial texts from `transcript_candidates["gemini_live_input"|"snapshot_transcription"|"desktop_ask_ai"|"batch_transcription"]` plus legacy `gemini_input_text`/`ask_question_text`
- `looks_cross_ask_contaminated(capture, text, source) -> bool` — `backend/app/services/ask_transcript_state.py:83` — only applies when `source == "deepgram_ask"`; detects "Deepgram failure mode where an ask stream begins with an old tail" (docstring); requires Latin-script (`_latin_ratio >= 0.8`) on both incoming and reference texts
- `_deepgram_truncated_by_gemini(capture, text) -> bool` — `backend/app/services/ask_transcript_state.py:101` — true if a reference text is the same family but >18 chars longer (Deepgram truncated relative to Gemini)
- `compact_ask_text(text) -> str` — `backend/app/services/ask_transcript_state.py:113` — whitespace-collapse + strip
- `ask_entry_id(session, capture=None) -> str` — `backend/app/services/ask_transcript_state.py:117` — `f"ask_ai_{started_at_ms}"` from `current_ask_capture`, else `session.question_capture_id`, else `f"ask_ai_{int(time.time()*1000)}"`
- `is_short_private_partial(text) -> bool` — `backend/app/services/ask_transcript_state.py:128` — true if empty, or normalized text is a filler word, or `<=1 word and <=3 chars`
- `source_priority(source) -> int` — `backend/app/services/ask_transcript_state.py:139` — looks up `SOURCE_PRIORITY`, default 0
- `record_candidate(session, *, text, source, entry_id=None, is_final=False, confidence=None, timestamp_ms=None) -> dict` — `backend/app/services/ask_transcript_state.py:143` — mutates `session.current_ask_capture["transcript_candidates"][source] = {...}`; also updates `gemini_input_text` (if source is `gemini_live_input`) and `ask_question_text` (if `is_final`)
- `best_candidate(capture, *, allow_partial=False) -> dict|None` — `backend/app/services/ask_transcript_state.py:177` — picks best candidate by sorting on `(priority, is_final, len(text), updated_at_ms)` desc; filters out partials (unless `allow_partial`), short-private-partials (unless final), and cross-ask-contaminated text; demotes `deepgram_ask` priority by `-1` below `gemini_live_input` if `_deepgram_truncated_by_gemini`
- `should_replace_frontend_text(existing_source, new_source, existing_text, new_text) -> bool` — `backend/app/services/ask_transcript_state.py:227` — replacement heuristic: replace if new is non-empty and (existing empty, or different text with higher/equal priority + longer, or special-case `deepgram_ask → gemini_live_input` upgrade when both Latin-script and new is >18 chars longer same-family)

**Key data structure**: `session.current_ask_capture` dict — `{"entry_id", "transcript_candidates": {source -> {"text","source","entry_id","is_final","confidence","updated_at_ms","priority"}}, "gemini_input_text", "ask_question_text", "started_at_ms"}`.

---

## audio_buffer.py

**Purpose**: Thread-safe rolling PCM audio buffer (default 90s capacity at 16kHz/16-bit mono = 32,000 bytes/sec). `ListenerAgent` reads overlapping 15s windows every 10s (per docstring). Used by `negotiation_engine.py:32`.

- Constants: `SAMPLE_RATE=16_000`, `BYTES_PER_SAMPLE=2`, `BYTES_PER_SECOND=32_000` — `backend/app/services/audio_buffer.py:17-19`
- `class AudioBuffer` — `backend/app/services/audio_buffer.py:22`
  - `__init__(max_seconds: int = 90)` — `backend/app/services/audio_buffer.py:31` — `_buf: deque[bytes]`, `_total_bytes`, `threading.RLock`
  - `push(chunk: bytes)` — `backend/app/services/audio_buffer.py:46` — appends, evicts oldest chunks while `_total_bytes > _max_bytes` (comment references "Requirement 13.1" / 90s rolling window — `backend/app/services/audio_buffer.py:50-51`)
  - `get_window(seconds: float) -> bytes` — `backend/app/services/audio_buffer.py:69` — last N seconds as joined bytes; `b""` if empty or `seconds<=0`
  - `get_segment(start_seconds_ago, end_seconds_ago) -> bytes` — `backend/app/services/audio_buffer.py:85` — slice between two "seconds ago" offsets (e.g. `get_segment(10,5)` = audio from 10s ago to 5s ago); requires `start > end` else returns `b""`
  - `duration_seconds` property — `backend/app/services/audio_buffer.py:114`
  - `clear()` — `backend/app/services/audio_buffer.py:120`

---

## bounded_async.py

**Purpose**: Small async concurrency utilities — named semaphore registry + generic retry-with-backoff helper. Used by `listener_agent.py:49` and `stt_service.py:17`.

- `class GlobalLimiter` — `backend/app/services/bounded_async.py:12` — class-level `_semaphores: dict[str, asyncio.Semaphore]`
  - `@classmethod get(name, limit) -> asyncio.Semaphore` — `backend/app/services/bounded_async.py:18` — creates-or-returns a named semaphore with `max(1, limit)` slots (lazy singleton per name)
- `async run_with_retries(operation_name, func, *, max_retries, base_backoff_ms, max_backoff_ms, is_retryable, on_retry=None) -> T` — `backend/app/services/bounded_async.py:26` — calls `func()`, on exception checks `attempt > max_retries or not is_retryable(exc)` (re-raises if so); else calls optional `on_retry(attempt, exc)` (sync or async); backoff = `random.uniform(0, min(max_backoff_ms, base_backoff_ms * 2**(attempt-1)))` (full jitter exponential)

---

## capability_registry.py

**Purpose**: Tiny in-process status registry for STT and SpeechBrain provider availability, set during app startup probes (`main.py`) and read by `negotiation_engine.py`, `speaker_mapping_service.py`, `stt_service.py`. Singleton `capability_registry = CapabilityRegistry()` at `backend/app/services/capability_registry.py:53`.

- `@dataclass CapabilityStatus` — `backend/app/services/capability_registry.py:10` — fields: `available: bool`, `reason: str=""`, `provider: str=""`, `region: str=""`
- `class CapabilityRegistry` — `backend/app/services/capability_registry.py:17`
  - `__init__()` — `backend/app/services/capability_registry.py:18` — `threading.Lock`; initial `_stt = CapabilityStatus(False, "not_probed", settings.TRANSCRIPTION_PROVIDER)`, `_speechbrain = CapabilityStatus(False, "not_probed", "speechbrain")`
  - `set_stt(status)` / `stt() -> CapabilityStatus` — `backend/app/services/capability_registry.py:23`/`27` — returns a copy via `asdict`/`**`
  - `set_google_stt(status)` — `backend/app/services/capability_registry.py:31` — alias for `set_stt`
  - `set_speechbrain(status)` / `speechbrain() -> CapabilityStatus` — `backend/app/services/capability_registry.py:34`/`41`
  - `google_stt() -> CapabilityStatus` — `backend/app/services/capability_registry.py:38` — alias for `stt()`
  - `active_path() -> str` — `backend/app/services/capability_registry.py:45` — returns `"full"` if both `stt().available` and `speechbrain().available`, else `"degraded"`

---

## app_tokens.py

**Purpose**: Mints/verifies the app's own short-lived HS256 access tokens and long-lived refresh tokens (separate from Clerk's session tokens, which have a 60s TTL — per module docstring). Refresh token records persisted via `auth_db`. Used by `api/auth.py:146,181` and `api/auth_routes.py:26`.

- `class TokenPair(TypedDict)` — `backend/app/services/app_tokens.py:33` — `{access_token, refresh_token, token_type, expires_in}`
- `class TokenError(Exception)` — `backend/app/services/app_tokens.py:40`
- `_secret() -> str` — `backend/app/services/app_tokens.py:44` — reads `settings.JWT_SECRET_KEY`; raises `RuntimeError` with a `secrets.token_urlsafe(48)` generation hint if unset/blank
- `_now() -> datetime` — `backend/app/services/app_tokens.py:54` — UTC now
- `make_access_token(clerk_sub, email) -> str` — `backend/app/services/app_tokens.py:58` — payload `{sub, email, type:"access", iat, exp}`; TTL = `settings.JWT_ACCESS_TTL_MINUTES`
- `make_refresh_token(clerk_sub) -> tuple[str,str,datetime]` — `backend/app/services/app_tokens.py:72` — returns `(raw_token, jti, expires_at)`; payload `{sub, jti, type:"refresh", iat, exp}`; TTL = `settings.JWT_REFRESH_TTL_DAYS`
- `verify_access_token(raw_token) -> dict` — `backend/app/services/app_tokens.py:93` — raises `TokenError` if invalid or `type != "access"`
- `verify_refresh_token(raw_token) -> dict` — `backend/app/services/app_tokens.py:109` — raises `TokenError` if invalid or `type != "refresh"`
- `make_token_pair(clerk_sub, email) -> tuple[TokenPair, str, datetime]` — `backend/app/services/app_tokens.py:125` — convenience wrapper returning `(pair, refresh_jti, refresh_expires_at)`

**Settings referenced**: `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_TTL_MINUTES`, `JWT_REFRESH_TTL_DAYS`.

---

## auth_db.py

**Purpose**: Raw sqlite3 helpers for `users` and `refresh_tokens` tables (created by `session_store.initialize()`), reusing the same DB file/WAL mode — no separate connection pool or ORM (per module docstring). Module-level `_db_path`/`_lock`.

- `configure(db_path)` — `backend/app/services/auth_db.py:24` — sets module-global `_db_path`; called at app startup
- `_connect() -> sqlite3.Connection` — `backend/app/services/auth_db.py:30` — lazy-configures from `settings.SESSION_DB_PATH` if `configure()` wasn't called (e.g. tests); `row_factory = sqlite3.Row`, `PRAGMA journal_mode=WAL`
- `upsert_user(clerk_sub, email, email_verified)` — `backend/app/services/auth_db.py:46` — INSERT...ON CONFLICT updates `email`, `email_verified`, `last_login_at` on every call
- `get_user(clerk_sub) -> dict|None` — `backend/app/services/auth_db.py:63`
- `store_refresh_token(jti, clerk_sub, expires_at: datetime)` — `backend/app/services/auth_db.py:75` — `revoked=0` initially
- `is_refresh_token_valid(jti) -> bool` — `backend/app/services/auth_db.py:89` — `revoked==0 and expires_at > now`
- `revoke_refresh_token(jti)` — `backend/app/services/auth_db.py:102`
- `get_refresh_token_sub(jti) -> str|None` — `backend/app/services/auth_db.py:108` — only for valid (non-revoked, non-expired) tokens
- `purge_expired_tokens() -> int` — `backend/app/services/auth_db.py:119` — DELETE expired rows, returns rowcount

**`users` table**: `clerk_sub` (PK), `email`, `email_verified`, `created_at`, `last_login_at`. **`refresh_tokens` table**: `jti` (PK), `clerk_sub`, `expires_at`, `revoked`, `created_at` (defined in `session_store.py:135-141`).

---

## clerk_verify.py

**Purpose**: Stateless Clerk JWT (RS256) verification — fetches/caches Clerk's JWKS (5-minute TTL), verifies signature/issuer/azp. Intentionally has no DB or FastAPI coupling (unit-testable per docstring). Used by `api/auth_routes.py:25`.

- Module-level cache: `_jwks_cache: tuple[list[dict], float]|None`, `_JWKS_TTL = 300`, `_jwks_lock = asyncio.Lock()` — `backend/app/services/clerk_verify.py:34-36`
- `class ClerkTokenError(Exception)` — `backend/app/services/clerk_verify.py:39`
- `async _fetch_jwks() -> list[dict]` — `backend/app/services/clerk_verify.py:43` — GETs `settings.CLERK_JWKS_URL` via `httpx.AsyncClient(timeout=10.0)`; raises `ClerkTokenError` if URL unset, fetch fails, or no keys returned
- `_find_key(keys, kid) -> Any` — `backend/app/services/clerk_verify.py:73` — matches `kid`, falls back to first key (single-key tenancies); raises `ClerkTokenError` if `keys` empty
- `async verify_clerk_token(raw_token) -> dict` — `backend/app/services/clerk_verify.py:85` — peeks unverified header for `kid`; if `kid` not found in cached JWKS, force-refreshes cache (handles key rotation — `:109-114`); verifies RS256 signature, `exp`/`nbf`, optional `iss` (`settings.CLERK_ISSUER`) and `azp` (`settings.CLERK_AUTHORIZED_PARTY`). **Does NOT check `email_verified`** — docstring says callers must assert that themselves (`:94-95`)
- `invalidate_jwks_cache()` — `backend/app/services/clerk_verify.py:143` — test hook, nulls `_jwks_cache`

**Settings referenced**: `CLERK_JWKS_URL`, `CLERK_ISSUER`, `CLERK_AUTHORIZED_PARTY`.

---

## response_validator.py

**Purpose**: Validates Gemini AI negotiation-coach responses against "negotiation commander" formatting rules (must start with an action verb, no trailing question marks, no vague hedging language). Used by `gemini_client.py:34` (note: `gemini_client.py:1994` comment says **"ResponseValidator disabled in native audio mode"**).

- `class ResponseValidator` — `backend/app/services/response_validator.py:17`
  - `ALLOWED_FIRST_WORDS = RESPONSE_VALIDATOR_ALLOWED_FIRST_WORDS` (from `app.ai_assets`) — `backend/app/services/response_validator.py:21`
  - `FORBIDDEN_FIRST_WORDS = RESPONSE_VALIDATOR_FORBIDDEN_FIRST_WORDS` — `backend/app/services/response_validator.py:24`
  - `@staticmethod _strip_quoted_content(text) -> str` — `backend/app/services/response_validator.py:27` — regex-replaces quoted substrings with `""` so e.g. `Ask: "Could we move equity?"` is validated on the command frame, not the quoted question
  - `@staticmethod validate_response(text) -> dict` — `backend/app/services/response_validator.py:38` — returns `{"valid": bool, "violations": list[str], "correction_prompt": str|None}`. Checks (on `unquoted_text` unless noted):
    1. `ENDS_WITH_QUESTION` — text ends with `?`
    2. `FORBIDDEN_START:{word}` — first word or first-two-word phrase in `FORBIDDEN_FIRST_WORDS` (checked on raw `text`)
    3. `MISSING_ACTION_START` — doesn't start with allowed word AND no other violations yet
    4. `VAGUE_LANGUAGE` — regex match on `you could|you might|consider|maybe|perhaps|one option|a few options`
    5. `CONTAINS_QUESTIONS:{count}` — any `?` in unquoted text
  - `@staticmethod _generate_correction(violations, original_text) -> str` — `backend/app/services/response_validator.py:115` — maps violation codes to human messages, calls `build_response_correction_prompt(violation_messages)` from `app.ai_assets`
  - `@staticmethod should_send_correction(violations) -> bool` — `backend/app/services/response_validator.py:136` — `bool(violations)`; comment notes silent drops would create "hung turns" since the client waits forever (`:138-139`)

---

## master_prompt.py

**Purpose**: 3-line re-export shim — `from app.ai_assets import ADVISOR_SYSTEM_PROMPT; __all__ = ["ADVISOR_SYSTEM_PROMPT"]` (`backend/app/services/master_prompt.py:1-3`). The actual prompt text lives in `app/ai_assets.py:203` (`ADVISOR_SYSTEM_PROMPT`) and `app/ai_assets.py:554` (`UNIFIED_ADVISOR_SYSTEM_PROMPT`). **No other file imports `app.services.master_prompt`** (grep found zero references) — appears to be an unused/legacy re-export.

---

## utterance_types.py

**Purpose**: Shared dataclasses for finalized speech utterances and counterparty-embedding candidates, used across the STT/diarization pipeline. Used by `negotiation_engine.py:41` (and a local re-import alias `_FU` at `:547`), `listener_agent.py:53`, `companion_runtime.py:24`, `stt_service.py:18`.

- `@dataclass FinalizedUtterance` — `backend/app/services/utterance_types.py:8` — fields: `utterance_id: str`, `audio: bytes`, `started_at: float`, `ended_at: float`, `duration_ms: int`, `rms: float`, `source: str = "stt"`, `transcript_text: str = ""`, `transcription_confidence: float|None = None`, `speaker: str = "unknown"`, `speaker_confidence: float|None = None`, `eligible_for_display: bool = False`, `eligible_for_context: bool = False`, `eligible_for_research: bool = False`, `metadata: dict[str,Any] = field(default_factory=dict)`
- `@dataclass CounterpartyCandidate` — `backend/app/services/utterance_types.py:27` — fields: `embedding: Any`, `timestamp: float`, `utterance_id: str` (mirrors the dict shape used in `session.counterparty_candidates`, see `speaker_service.py:580-586`)

---

## u.py

**Purpose**: Empty file (0 bytes, `backend/app/services/u.py`). No content, no imports anywhere. Dead/stray file — likely an accidental `touch` or leftover from an aborted edit.

---

## readiness.py (72 lines)

**Purpose**: Single source of truth for "is the backend ready to start a session yet?" — bridges the gap between WS accepting connections immediately and the background STT/SpeechBrain capability probes (`main.py:_run_capability_probes_in_background`) which take a couple seconds at startup.

- `class BackendReadiness` `:27-72` — singleton instance `readiness` `:72`.
  - `_ready: bool`, `_event: Optional[asyncio.Event]` (lazily created, `:33-40`, to avoid "no running loop" at import time), `_detail: dict`.
  - `mark_ready(detail=None)` `:42-48` — flips ready=True, sets event, idempotent. Called once from `main.py` after capability probes complete.
  - `is_ready` property `:50-52`.
  - `status_message` property `:54-56` — returns `PENDING_MESSAGE` ("Connecting to AI services… please wait.") or `READY_MESSAGE` ("AI services ready — you can start a session.").
  - `snapshot()` `:58-63` — `{"ready": bool, "status_message": str, "detail": dict}` — sent in `CONNECTION_ESTABLISHED` (`websocket.py`) and via `GET /api/ready`.
  - `async wait()` `:65-69` — resolves immediately if ready, else awaits the event.

**Gotchas**: `connection_manager.broadcast_backend_ready()` is called right after `mark_ready()` to push readiness to already-connected clients (race: a client may connect before probes finish).

---

## Cross-cutting notes for future sessions

- **Likely-dead provider modules**: `azure_speaker_service.py`, `eagle_service.py`, `voice_encoder.py`, and `master_prompt.py` have zero inbound references from the rest of `backend/app` (verified via grep). The active speaker-verification stack is `speechbrain_service.py` + `speaker_enrollment.py` + `speaker_mapping_service.py` + `speaker_service.py`.
- **Two speaker-classification code paths** coexist in `speaker_service.py`: legacy VAD-segment (`feed_audio`/`_classify_segment`, lines 94-369) and newer per-utterance (`classify_utterance`, lines 392-520). Check `negotiation_engine.py` call sites (lines 587, 1552, 3037) to see which is live for any given code path.
- **Speaker mapping state machine** (`speaker_mapping_service.py`) states: `unmapped → calibrating → mapped → degraded`, with `degraded` reachable only via `record_contradiction` (2+ contradictions in `settings.SPEAKER_RECHECK_WINDOW_SECONDS`).
- **Deepgram language switching** (`deepgram_stream.py`) is per-source and tears down/rebuilds the websocket atomically; `_failed_{source}` is a dynamic attribute marking permanent per-source failure (HTTP 400/401/403).
- **`session_store.py`** is the central persistence point — almost every other service that needs to record session state imports `session_store` directly (singleton pattern, no DI).
- **Translation (`translation.py`) and ask-transcript-state (`ask_transcript_state.py`)** are both gated/consumed by `gemini_client.py` and `negotiation_engine.py`/`companion_runtime.py` for the multilingual "Ask AI" feature.