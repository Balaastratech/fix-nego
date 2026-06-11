I'll analyze these three files systematically. Let me start by gathering structural information.

Now let me get more details: imports, top-level constants, settings.X references, gotchas, and message types for each file.

Now let me gather gotchas/comments and message type literals for each file.

Now let me get message types for gemini_client and companion_runtime, plus a few more specifics (class structure of NegotiationEngine - is it all static methods?).

Now I have enough to build the reference map. Let me check a couple more details: the companion_runtime dataclasses/module-level constants section (lines 30-180), and verify a few key handler line ranges and helper functions in negotiation_engine for the "who calls whom" relationships.

I have all the information I need. Let me produce the structured reference map.

## backend/app/services/negotiation_engine.py (3459 lines)

**Purpose**: Core WebSocket negotiation orchestration. `NegotiationEngine` (all `@staticmethod` methods) is the central message router (`route_message`) for the negotiation WebSocket — handles state-machine transitions (IDLE -> CONSENTED -> ACTIVE -> PAUSED -> ENDING), session lifecycle (start/pause/resume/end), audio/vision frame intake, speaker identification, "Ask AI" (USER_ADDRESSING_AI) flow, copilot mode, and context injection into the live Gemini session. It calls into `gemini_client.py` (imports `open_live_session`, `send_vision_frame`, `send_audio_chunk`, `receive_responses`, `keepalive_ping`, `handle_gemini_text`) to manage the Gemini Live connection, and into `companion_runtime.py` (`companion_runtime` singleton) to delegate desktop-companion-specific audio routing, hold-to-ask state, and meeting binding/capture-health updates. `gemini_client.py` calls back into `negotiation_engine.NegotiationEngine` (lazy imports) for trace/state-update helpers during live response streaming.

### Module-level constants/dicts
- `VALID_MESSAGES` — `backend/app/services/negotiation_engine.py:53` — dict of allowed msg types per `NegotiationState`.
- `ERROR_CODES` — `backend/app/services/negotiation_engine.py:97` — error code/message per state for invalid transitions.

### Classes/Functions

| Name | Location | Description |
|---|---|---|
| `NegotiationEngine` | `backend/app/services/negotiation_engine.py:101` | Container class; all methods are `@staticmethod`. |
| `start_live_preconnect` | `backend/app/services/negotiation_engine.py:103` | Kicks off background task to pre-open Gemini Live session before START_NEGOTIATION; reads `settings.GOOGLE_GENAI_USE_VERTEXAI`, `settings.MULTILANG_ENABLED`. |
| `_preconnect` (nested) | `backend/app/services/negotiation_engine.py:114` | Inner async fn that actually opens the live session and stores it on `session.live_session`/`session.live_session_cm`. |
| `_inject_start_context` | `backend/app/services/negotiation_engine.py:176` | Sends initial negotiation context into a preconnected live session; reads `settings.MULTILANG_ENABLED`; records to session trace. |
| `validate_message` | `backend/app/services/negotiation_engine.py:219` | Checks `msg_type` against `VALID_MESSAGES[session.state]`; sends `ERROR` payload via `ERROR_CODES` if invalid. |
| `transition_state` | `backend/app/services/negotiation_engine.py:248` | Mutates `session.state`, broadcasts `NEGOTIATION_STATE_CHANGED`. |
| `handle_consent` | `backend/app/services/negotiation_engine.py:272` | Handles PRIVACY_CONSENT_GRANTED; sets consent_mode, checks `settings.EVAL_MODE_ENABLED`/roleplay; sends `CONSENT_ACKNOWLEDGED`. |
| `handle_enrollment_start` | `backend/app/services/negotiation_engine.py:293` | Begins voice-enrollment flow (speaker recognition setup); reads `settings.GEMINI_API_KEY`. |
| `handle_provider_config` | `backend/app/services/negotiation_engine.py:317` | Handles PROVIDER_CONFIG; sends `PROVIDER_CONFIG_ACK`. |
| `handle_start` | `backend/app/services/negotiation_engine.py:414` | **Major handler** — START_NEGOTIATION: opens/attaches live Gemini session, starts STT, speaker recognition, sends `AI_CONNECTING`/`SESSION_STARTED`/`PERSISTENCE_STATUS`/`LANGUAGE_UPDATE`/`ERROR`; reads `settings.GEMINI_PRECONNECT_WAIT_SECONDS`, `SPEECHBRAIN_ENABLED`, `TRANSCRIPTION_PROVIDER`, `SPEAKER_RECOGNITION_ENABLED`, `RESEMBLYZER_ENABLED`, `GEMINI_MODEL`, `VISION_ENABLED`, `MULTILANG_ENABLED`. ~270 lines, the biggest setup routine. |
| `handle_vision_frame` | `backend/app/services/negotiation_engine.py:685` | Handles VISION_FRAME; buffers frames, gated by `settings.VISION_PRO_ENABLED`, `VISION_PRO_MAX_FRAMES`, `VISION_PRO_LIVE_COOLDOWN_SECONDS`/`VISION_PRO_COOLDOWN_SECONDS`, `VISION_PRO_MIN_FRAMES`, `VISION_OBS_MAX_HISTORY`, `RESEARCH_HISTORY_LIMIT`; sends `VISION_INTEL`. |
| `_run_vision_analysis` (nested in handle_vision_frame) | `backend/app/services/negotiation_engine.py:797` | Inner async task that calls `gemini_client.analyze_vision_frames` and emits `VISION_INTEL`. |
| `_drain_live_vision_frames` | `backend/app/services/negotiation_engine.py:856` | Drains buffered vision frames to live session at interval; reads `settings.VISION_LIVE_SEND_INTERVAL_SECONDS`. |
| `handle_audio_chunk` | `backend/app/services/negotiation_engine.py:890` | Handles AUDIO_CHUNK (legacy single-stream audio path); reads `settings.ASK_AI_NATIVE_AUDIO`. |
| `handle_companion_audio` | `backend/app/services/negotiation_engine.py:925` | Delegates LOCAL_MIC_PCM/REMOTE_APP_PCM/ASK_AI_PCM to `companion_runtime.handle_audio_payload`. |
| `handle_meeting_binding` | `backend/app/services/negotiation_engine.py:937` | Handles MEETING_BINDING; calls `companion_runtime.update_meeting_binding`; sends `MEETING_BINDING_UPDATE`. |
| `handle_capture_health` | `backend/app/services/negotiation_engine.py:951` | Handles CAPTURE_HEALTH; calls `companion_runtime.update_capture_health`; sends `CAPTURE_HEALTH_UPDATE`/`DEGRADED_MODE_UPDATE`. |
| `handle_screen_frame` | `backend/app/services/negotiation_engine.py:976` | Handles SCREEN_FRAME (companion screen capture passthrough). |
| `handle_pause` | `backend/app/services/negotiation_engine.py:986` | Handles PAUSE_NEGOTIATION; closes ASK_AI native audio activity if `settings.ASK_AI_NATIVE_AUDIO`; sends `SESSION_PAUSED`. |
| `handle_resume` | `backend/app/services/negotiation_engine.py:1021` | Handles RESUME_NEGOTIATION; sends `SESSION_RESUMED`. |
| `handle_end` | `backend/app/services/negotiation_engine.py:1046` | Handles END_NEGOTIATION; tears down live session, sends `OUTCOME_SUMMARY`; persists session. |
| `handle_state_update` | `backend/app/services/negotiation_engine.py:1191` | Handles STATE_UPDATE; sends `STATE_UPDATE` echo with merge-strategy hint. |
| `handle_speaker_identified` | `backend/app/services/negotiation_engine.py:1211` | Handles SPEAKER_IDENTIFIED (manual or automatic); processes audio segment, runs STT, sends `TRANSCRIPT_UPDATE`; gated by `settings.MIN_TRANSCRIBE_DURATION_MS`, `TRANSCRIPTION_PROVIDER`, `SPEAKER_RECOGNITION_ENABLED`, `SPEECHBRAIN_ENABLED`. Contains "BUG FIX" comment at line 1540 about `classify_utterance()` only running under certain speaker conditions. |
| `route_message` | `backend/app/services/negotiation_engine.py:1342` | **Central dispatcher** — big if/elif on `msg_type`, routes to all `handle_*` methods. |
| `handle_trace_client_event` | `backend/app/services/negotiation_engine.py:1423` | Handles TRACE_CLIENT_EVENT; records to session trace via `get_session_trace`. |
| `handle_speaker_stopped` | `backend/app/services/negotiation_engine.py:1447` | Handles SPEAKER_STOPPED. |
| `handle_simulated_negotiation_turn` | `backend/app/services/negotiation_engine.py:1462` | Handles SIMULATED_NEGOTIATION_TURN (eval/roleplay mode); gated by `settings.EVAL_MODE_ENABLED`; sends `SIMULATED_TURN_ACCEPTED`/`ERROR`. |
| `handle_utterance_end` | `backend/app/services/negotiation_engine.py:1503` | Handles UTTERANCE_END — finalizes a speaker segment, runs transcription, calls `classify_utterance`/speaker recognition; contains BUG FIX comment (line 1540). |
| `handle_user_addressing_ai` | `backend/app/services/negotiation_engine.py:1618` | **Largest handler (~670 lines)** — USER_ADDRESSING_AI / "Ask AI" hold-to-talk flow: manages audio gating, pre-query brief injection, mode-activation instructions, native vs batch transcription, sends `AI_THINKING`, `AI_RESPONSE`, `TRANSCRIPT_UPDATE`; heavily gated by `settings.ASK_AI_NATIVE_AUDIO`, `ASK_AI_LOCAL_MIC_SUPPRESS_GRACE_SECONDS`, `ASK_AI_BATCH_TRANSCRIBE_TIMEOUT_SECONDS`. |
| `_close_ask_window_if_orphaned` (nested) | `backend/app/services/negotiation_engine.py:2273` | Inner async task; closes ask window after 25s grace if orphaned (uses generation counter `my_gen` to detect staleness). |
| `handle_start_copilot` | `backend/app/services/negotiation_engine.py:2287` | Handles START_COPILOT; sends `COPILOT_STARTED`/`ERROR`. |
| `handle_set_response_mode` | `backend/app/services/negotiation_engine.py:2381` | Handles SET_RESPONSE_MODE; sends `RESPONSE_MODE_SET`; defaults to "command" on invalid mode. |
| `handle_set_response_language` | `backend/app/services/negotiation_engine.py:2409` | Handles SET_RESPONSE_LANGUAGE; sends `LANGUAGE_UPDATE`. |
| `handle_set_language_profile` | `backend/app/services/negotiation_engine.py:2422` | Handles SET_LANGUAGE_PROFILE; gated by `settings.MULTILANG_ENABLED` (no-op note at 2444 if disabled); resets Deepgram streams; references "English bug from session 006183c1" (line 2491) and a NOTE about not using `_inject_start_context()` (line 2513) because it short-circuits. |
| `handle_speaker_mode_change` | `backend/app/services/negotiation_engine.py:2557` | Handles SPEAKER_MODE_CHANGE; sends `SPEAKER_MODE_CHANGED`; defaults to "manual" on invalid mode. |
| `_inject_context_to_live_ai` | `backend/app/services/negotiation_engine.py:2602` | Injects accumulated context/intel into live Gemini session. |
| `_flush_latest_intel` | `backend/app/services/negotiation_engine.py:2751` | Flushes most-recent vision/listener intel to live session; catches and logs context-injection failures. |
| `_send_coalesced_intel` | `backend/app/services/negotiation_engine.py:2783` | Sends merged/coalesced intel block; reads `settings.VISION_INTEL_SEND_INTERVAL_SECONDS`. |
| `flush_pending_injections` (1st def) | `backend/app/services/negotiation_engine.py:2888` | Flushes queued context injections; comment about preventing race conditions with new injections during flush (line 2913). |
| `_reconnect_live_session` | `backend/app/services/negotiation_engine.py:2939` | Reconnects to Gemini Live after disconnect; sends `DEGRADED_MODE_UPDATE`/`AI_DEGRADED`; reads `settings.GEMINI_API_KEY`, `MULTILANG_ENABLED`, `SPEAKER_RECOGNITION_ENABLED`, `RESEMBLYZER_ENABLED`/`SPEECHBRAIN_ENABLED`. |
| `_build_compact_snapshot` | `backend/app/services/negotiation_engine.py:3088` | Builds compact session-state snapshot dict (non-async helper). |
| `_inject_single_context` | `backend/app/services/negotiation_engine.py:3114` | Injects a single context dict into live session. |
| `_inject_critical_events` | `backend/app/services/negotiation_engine.py:3161` | Injects critical event blocks; sends queued context, logs `[CopilotEngine] Failed to send queued context` on failure. |
| `flush_pending_injections` (2nd def — **duplicate name**) | `backend/app/services/negotiation_engine.py:3214` | Second definition with same name as line 2888 — shadows/overrides the earlier one (verify which is actually used). |
| `handle_ask_advice` | `backend/app/services/negotiation_engine.py:3249` | Handles ASK_ADVICE; sends `AI_THINKING` then `TRANSCRIPT_UPDATE` (pro_advice); gated by `settings.ADVICE_GENERATION_TIMEOUT_SECONDS`; sends `ERROR` on failure. |
| `_build_context_summary` (module-level fn) | `backend/app/services/negotiation_engine.py:3441` | Standalone module function (not in class) building a text context summary; note a same-named function also exists in `gemini_client.py:77`. |

### WebSocket message types sent (search `"type": "..."`)
`ERROR`, `NEGOTIATION_STATE_CHANGED`, `CONSENT_ACKNOWLEDGED`, `PROVIDER_CONFIG_ACK`, `AI_CONNECTING`, `SESSION_STARTED`, `PERSISTENCE_STATUS`, `LANGUAGE_UPDATE`, `VISION_INTEL`, `MEETING_BINDING_UPDATE`, `CAPTURE_HEALTH_UPDATE`, `DEGRADED_MODE_UPDATE`, `SESSION_PAUSED`, `SESSION_RESUMED`, `OUTCOME_SUMMARY`, `STATE_UPDATE`, `TRANSCRIPT_UPDATE`, `SIMULATED_TURN_ACCEPTED`, `AI_THINKING`, `AI_RESPONSE`, `COPILOT_STARTED`, `RESPONSE_MODE_SET`, `SPEAKER_MODE_CHANGED`, `AI_DEGRADED`.

### Message types handled (in `route_message`, `backend/app/services/negotiation_engine.py:1342-1421`)
`PROVIDER_CONFIG`, `PRIVACY_CONSENT_GRANTED`, `START_NEGOTIATION`, `ENROLLMENT_START`, `VISION_FRAME`, `SCREEN_FRAME`, `LOCAL_MIC_PCM`, `REMOTE_APP_PCM`, `ASK_AI_PCM`, `TRACE_CLIENT_EVENT`, `MEETING_BINDING`, `CAPTURE_HEALTH`, `HOLD_TO_ASK_STATE`, `PAUSE_NEGOTIATION`, `RESUME_NEGOTIATION`, `END_NEGOTIATION`, `STATE_UPDATE`, `ASK_ADVICE`, `SPEAKER_IDENTIFIED`, `SPEAKER_STOPPED`, `USER_ADDRESSING_AI`, `START_COPILOT`, `SET_RESPONSE_MODE`, `SET_RESPONSE_LANGUAGE`, `SET_LANGUAGE_PROFILE`, `SPEAKER_MODE_CHANGE`, `UTTERANCE_END`, `SIMULATED_NEGOTIATION_TURN`, `AI_PLAYBACK_DONE`.

### Gotchas
- Line 1540: "BUG FIX: the old code only ran `classify_utterance()` when `current_speaker`..." — fixed condition in `handle_utterance_end`.
- Line 2491: comment referencing the "...English' bug from session 006183c1" — language-profile fix in `handle_set_language_profile`.
- Line 2513: NOTE — `_inject_start_context()` cannot be reused for language-profile changes because it short-circuits.
- Line 2913: comment about flush_pending_injections preventing race conditions with concurrent injections.
- **Two functions named `flush_pending_injections`** at lines 2888 and 3214 — second shadows first; potential dead code / bug risk.
- Lines 2273-2281: `_close_ask_window_if_orphaned` uses a generation counter (`my_gen`) with a 25s grace sleep — check generation match before acting (stale-closure guard).

---

## backend/app/services/gemini_client.py (2357 lines)

**Purpose**: Wrapper around the Google GenAI ("Gemini Live") SDK. Provides the `GeminiClient` class (static methods, re-exported as module-level aliases at the bottom: `open_live_session`, `send_vision_frame`, `send_audio_chunk`, `receive_responses`, `monitor_session_lifetime`, `keepalive_ping`) plus standalone helper functions for vision analysis, tactical "pro advice" generation, function-calling (web search), and Gemini text-message handling. `negotiation_engine.py` imports and drives these directly (opens sessions, sends frames/audio, runs `receive_responses` as a long-lived task). `receive_responses` (the core read-loop) lazily imports `NegotiationEngine` from `negotiation_engine.py` at several points (lines 1615, 2145, 2165, 2227, 2320) to call back into engine-level helpers (e.g., context injection, trace handling) — i.e., a circular but lazy dependency.

### Module-level constants
- `GEMINI_MODEL_PRIMARY = settings.effective_model` — `backend/app/services/gemini_client.py:41`
- `GEMINI_MODEL_FALLBACK = settings.effective_fallback_model` — `backend/app/services/gemini_client.py:42`
- `GEMINI_MODEL_TEXT_ONLY = settings.effective_flash_model` — `backend/app/services/gemini_client.py:43`
- `SESSION_HARD_LIMIT_SECONDS = 600` — `backend/app/services/gemini_client.py:45`
- `SESSION_HANDOFF_TRIGGER = 540` — `backend/app/services/gemini_client.py:46`

### Classes/Functions

| Name | Location | Description |
|---|---|---|
| `GeminiUnavailableError` | `backend/app/services/gemini_client.py:48` | Exception raised when all Gemini Live models are unavailable (primary + fallback exhausted). |
| `_accumulate_live_usage` | `backend/app/services/gemini_client.py:53` | Accumulates token usage metadata from a live response onto `session`; tolerant of unexpected metadata shape (debug log at 74). |
| `_build_context_summary` | `backend/app/services/gemini_client.py:77` | Builds text context summary from session (separate from same-named fn in negotiation_engine.py:3441). |
| `_extract_recent_line` | `backend/app/services/gemini_client.py:99` | Gets the most recent transcript line for a given speaker. |
| `_extract_live_terms` | `backend/app/services/gemini_client.py:108` | Extracts key negotiation terms/numbers from transcript text. |
| `_build_live_deal_brief` | `backend/app/services/gemini_client.py:143` | Builds short "deal brief" text from transcript + user query. |
| `build_advisor_query` | `backend/app/services/gemini_client.py:159` | Builds the prompt/query sent to the advisor model from session state + transcript. |
| `_normalize_text_list` (nested in build_advisor_query) | `backend/app/services/gemini_client.py:218` | Inner helper normalizing list-of-text fields. |
| `_safe_parse_vision_json` | `backend/app/services/gemini_client.py:271` | Safely parses JSON from vision-model output; logs warning + "[Vision] Complete JSON extraction failed" on failure (line 318). |
| `analyze_vision_frames` | `backend/app/services/gemini_client.py:322` | **Vision Pro analysis** — sends buffered frames to vision model; gated by `settings.VISION_PRO_ENABLED` (335), uses `settings.effective_vision_model` (338), `settings.GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION` (344-345), timeout `settings.VISION_PRO_COOLDOWN_SECONDS + 12.0` (445); writes trace artifacts (vision_prompt, vision_result, vision_frame_N). |
| `generate_tactical_advice` | `backend/app/services/gemini_client.py:612` | **"Ask Advice"/Pro advice generation** — gated by `settings.ADVICE_GENERATION_ENABLED` (627); honors `settings.MULTILANG_ENABLED` (691, 718) for translation; uses `settings.effective_advice_model` (744), `ADVICE_GENERATION_TEMPERATURE`/`MAX_TOKENS`/`TIMEOUT_SECONDS` (770-822); pre/post-translation with fallback to English on failure (line 960 comment). |
| `trigger_advice_response` | `backend/app/services/gemini_client.py:995` | Triggers an advice response on the live session (wraps `generate_tactical_advice`). |
| `perform_web_search` | `backend/app/services/gemini_client.py:1029` | Performs a web search (function-calling tool backend); sends `RESEARCH_STARTED`/`RESEARCH_COMPLETE`. |
| `handle_function_call` | `backend/app/services/gemini_client.py:1055` | Dispatches Gemini function-call requests (e.g., to `perform_web_search`). |
| `_sanitize_ai_response_fragment` | `backend/app/services/gemini_client.py:1126` | Cleans a streamed text fragment from the AI response. |
| `_append_ai_response_text` | `backend/app/services/gemini_client.py:1137` | Appends text fragment to `session.current_ai_response`/buffer. |
| `_consume_completed_ai_response` | `backend/app/services/gemini_client.py:1150` | Pops/returns the completed AI response text and resets buffer. |
| `_current_ask_entry_id` | `backend/app/services/gemini_client.py:1164` | Returns current "Ask AI" transcript entry id from session. |
| `_current_ask_response_entry_id` | `backend/app/services/gemini_client.py:1179` | Returns current "Ask AI" response entry id from session. |
| `handle_gemini_text` | `backend/app/services/gemini_client.py:1185` | Handles a raw text payload from Gemini (e.g., strategy/state JSON); sends `STRATEGY_UPDATE`/`STATE_UPDATE`; logs warnings on JSON parse failure (1203, 1216). |
| `extract_state_from_transcript` | `backend/app/services/gemini_client.py:1233` | Extracts negotiation state JSON from transcript via model call; sends `STATE_UPDATE` (1324) with `_merge_strategy: "smart"`. |
| `GeminiClient` | `backend/app/services/gemini_client.py:1331` | Container class; methods are `@staticmethod` (some also `@asynccontextmanager`). |
| `open_live_session` | `backend/app/services/gemini_client.py:1334` | **Async context manager** opening a Gemini Live session; sets `GOOGLE_APPLICATION_CREDENTIALS`/`GOOGLE_CLOUD_PROJECT` env vars (1341-1344) from settings; uses `settings.GOOGLE_CLOUD_LOCATION` (1357), resolves response language via `settings.MULTILANG_ENABLED`/`GEMINI_LIVE_LANGUAGE_CODE` (1369-1430) — comment about "I set English but it transcribed Hindi" bug (1373); sets voice via `settings.GEMINI_LIVE_VOICE_NAME` (1413); affective dialog via `settings.GEMINI_LIVE_ENABLE_AFFECTIVE_DIALOG`/`ENABLE_AFFECTIVE_DIALOG` (1459); falls back from primary to fallback model on failure (1482, 1493). |
| `send_vision_frame` | `backend/app/services/gemini_client.py:1498` | Sends a JPEG frame to the live session; logs warning on send failure (1504). |
| `send_audio_chunk` | `backend/app/services/gemini_client.py:1507` | Sends raw PCM audio chunk to live session; warns on empty chunk (1519). |
| `receive_responses` | `backend/app/services/gemini_client.py:1548` | **The core long-running read loop (~700 lines)** — receives Gemini Live responses, handles audio interruption (`AUDIO_INTERRUPTED`), speaking/listening state (`AI_SPEAKING`/`AI_LISTENING`), transcript partials/updates (`TRANSCRIPT_PARTIAL`/`TRANSCRIPT_UPDATE`), AI responses (`AI_RESPONSE`), degraded mode (`AI_DEGRADED`); reads `settings.ASK_AI_NATIVE_AUDIO`/`ASK_AI_SUPPRESS_NATIVE_TRANSCRIPTION` (1722, 1837-1838), `settings.RESEARCH_HISTORY_LIMIT` (2080); contains comments re: "and different from what I hear the AI say" bug (1644) and "double-response bug" (2093, listener cycle 10s); lazy-imports `NegotiationEngine` from negotiation_engine at 1615, 2145, 2165, 2227, 2320. |
| `keepalive_ping` | `backend/app/services/gemini_client.py:2254` | Sends periodic keepalive ping on the live session; logs "Keepalive ping failed" on close (2284). |
| `monitor_session_lifetime` | `backend/app/services/gemini_client.py:2288` | Monitors session against `SESSION_HARD_LIMIT_SECONDS`/`SESSION_HANDOFF_TRIGGER`, triggers reconnect/handoff via `settings.GEMINI_API_KEY`-based reconnection (uses `settings.MULTILANG_ENABLED` at 2310). |

### Module-level re-export aliases (bottom of file)
- `open_live_session = GeminiClient.open_live_session` — `backend/app/services/gemini_client.py:2331`
- `send_vision_frame = GeminiClient.send_vision_frame` — `:2332`
- `send_audio_chunk = GeminiClient.send_audio_chunk` — `:2333`
- `receive_responses = GeminiClient.receive_responses` — `:2334`
- `monitor_session_lifetime = GeminiClient.monitor_session_lifetime` — `:2335`
- `keepalive_ping = GeminiClient.keepalive_ping` — `:2336`

### WebSocket message types sent
`RESEARCH_STARTED`, `RESEARCH_COMPLETE`, `STRATEGY_UPDATE`, `STATE_UPDATE`, `AUDIO_INTERRUPTED`, `AI_SPEAKING`, `TRANSCRIPT_PARTIAL`, `TRANSCRIPT_UPDATE`, `AI_LISTENING`, `AI_RESPONSE`, `AI_DEGRADED`.

### Gotchas
- Line 1373: comment block re: language-resolution "I set English but it transcribed Hindi" bug — fixed by choosing language before session creation.
- Line 1644-1647: comment about transcript text "different from what I hear the AI say" — guards a skip condition for speaker classification.
- Line 1712: "Add 20ms grace period for speaker classification to complete (optimized)".
- Line 2093: comment about the "double-response bug" tied to the listener's 10s cycle — important if touching response-mode logic.
- Lines 1482/1493: primary->fallback model failover logging — silent fallback could mask primary model issues.
- `analyze_vision_frames` (322) and `generate_tactical_advice` (612) both write trace artifacts via `get_session_trace` — heavy I/O if tracing enabled.

---

## backend/app/services/companion_runtime.py (1245 lines)

**Purpose**: Implements desktop-companion-mode audio/transcription orchestration via the `CompanionRuntime` class (singleton `companion_runtime` at line 1245), instantiated and used by `negotiation_engine.py` (`handle_companion_audio`, `handle_meeting_binding`, `handle_capture_health`, `handle_user_addressing_ai` all delegate here). It owns: AI-voice-leak filtering (preventing the negotiation AI's own TTS audio from being mis-transcribed as user speech), local-mic/remote-app/ask-ai PCM stream routing to Deepgram (streaming) or batch STT, hold-to-ask state, meeting-binding/capture-health/degraded-mode bookkeeping, and partial/final transcript emission (`TRANSCRIPT_PARTIAL`/`TRANSCRIPT_UPDATE`). It does not import `gemini_client.py` or `negotiation_engine.py` directly (no circular import on this side) — only `negotiation_engine` imports `companion_runtime`.

### Module-level helper functions

| Name | Location | Description |
|---|---|---|
| `_resolved_stt_provider` | `backend/app/services/companion_runtime.py:30` | Resolves STT provider via `runtime_config.provider_for`, falling back to `settings.TRANSCRIPTION_PROVIDER`. |
| `_deepgram_api_key` | `backend/app/services/companion_runtime.py:44` | Resolves Deepgram API key via `runtime_config.api_key_for("deepgram")`, fallback `settings.DEEPGRAM_API_KEY`. |
| `_deepgram_streaming_enabled` | `backend/app/services/companion_runtime.py:52` | True only if provider is "deepgram" AND key present; comment notes streaming is Deepgram-only, all other providers use batch path via `SpeechTranscriptionService`. |
| `levenshtein_distance` | `backend/app/services/companion_runtime.py:59` | Standard edit-distance implementation (recursive base-case swap). |
| `filter_ai_voice_leak` | `backend/app/services/companion_runtime.py:76` | **Core anti-leak filter** — strips words from `text` that match recent AI TTS output; reads `settings.AI_VOICE_LEAK_GRACE_SECONDS` (79), `AI_VOICE_LEAK_STRICT_POST_PLAYBACK_SECONDS` (142, 168), `AI_VOICE_LEAK_SHORT_WORD_LIMIT` (143); includes hardcoded homophone map (e.g., "cloud"->"claude", "clawed"->"claude") and fuzzy levenshtein matching. |
| `get_words` (nested in filter_ai_voice_leak) | `backend/app/services/companion_runtime.py:91` | Tokenizes text into lowercase alnum words. |
| `expand_word_variants` (nested) | `backend/app/services/companion_runtime.py:95` | Expands word list with bigrams and stem variants (-ing/-ed) for fuzzy matching. |
| `is_ai_word` (nested) | `backend/app/services/companion_runtime.py:112` | Checks if a word matches AI-spoken vocabulary (direct, homophone, or fuzzy). |
| `is_ai_voice_leak` | `backend/app/services/companion_runtime.py:157` | Returns True if `filter_ai_voice_leak` would change the text (i.e., leak detected). |
| `_remote_ai_playback_window_active` | `backend/app/services/companion_runtime.py:162` | True if AI audio is currently playing or was within `settings.AI_VOICE_LEAK_STRICT_POST_PLAYBACK_SECONDS` (168). |
| `_classify_ask_shape` | `backend/app/services/companion_runtime.py:171` | Classifies an "ask" question text via `next_move_cache.classify_ask` ("vague"/"precise"/"unknown"). |
| `_should_upgrade_question_text` | `backend/app/services/companion_runtime.py:179` | Decides whether a new candidate question transcript should replace the existing one based on source/shape/length heuristics. |

### `CompanionRuntime` class (line 211)

| Name | Location | Description |
|---|---|---|
| `CompanionRuntime` | `backend/app/services/companion_runtime.py:211` | Class with constants `LOCAL_MIC_MESSAGE="LOCAL_MIC_PCM"`, `REMOTE_APP_MESSAGE="REMOTE_APP_PCM"`, `ASK_AI_MESSAGE="ASK_AI_PCM"` (lines 212-214). |
| `is_companion_mode` | `backend/app/services/companion_runtime.py:216` | Checks `session.source_mode == SourceMode.VIRTUAL_COMPANION_DESKTOP.value`. |
| `apply_start_payload` | `backend/app/services/companion_runtime.py:219` | Applies START_NEGOTIATION payload for companion mode: sets `source_mode`, disables `speaker_recognition_enabled`, forces `speaker_mode="auto"`, enables all audio sources, sets `capture_preset`/`companion_quality_mode`/output device. |
| `update_meeting_binding` | `backend/app/services/companion_runtime.py:241` | Validates/stores `MeetingBinding`; sets `bound_at` timestamp; toggles `audio_sources_active["remote_app"]`. |
| `update_hold_state` | `backend/app/services/companion_runtime.py:249` | Updates `CompanionHoldState` (hold-to-ask); sets `started_at`/`released_at` timestamps on transitions. |
| `update_capture_health` | `backend/app/services/companion_runtime.py:267` | Validates/stores `CaptureHealth`; computes `degraded_mode` (`source_ambiguous`/`source_missing`/`capture_degraded`) and `degraded_reasons` based on loopback/frame/audio flags. |
| `source_admissible` | `backend/app/services/companion_runtime.py:290` | Gatekeeper for REMOTE_APP_PCM — requires meeting binding bound, no unsafe loopback, remote audio OK. |
| `handle_audio_payload` | `backend/app/services/companion_runtime.py:303` | **Major entry point (~200 lines)** — routes LOCAL_MIC_PCM/REMOTE_APP_PCM/ASK_AI_PCM chunks; checks `is_companion_mode`/listener-init (debug logs 311, 318); decodes base64 PCM (warns on decode failure, 332); comment about "multi-writer race at hold-release (garbled/truncated question text)" (369); uses `_deepgram_streaming_enabled()` (375) gated also by `settings.ASK_AI_NATIVE_ONLY_TRANSCRIPTION`. |
| `_capture_private_ask_audio` | `backend/app/services/companion_runtime.py:502` | Captures audio for a private "Ask AI" question; checks `settings.ASK_AI_NATIVE_AUDIO` + `session.live_session`/`ask_audio_activity_open` (558); records trace event (531-533). |
| `_transcribe_snapshot_text` | `backend/app/services/companion_runtime.py:615` | Transcribes a snapshot of buffered audio to text; comment "Lock-protected so we don't race vision frames or text injections" (562, in surrounding context). |
| `_emit_partial_transcript` | `backend/app/services/companion_runtime.py:656` | Emits `TRANSCRIPT_PARTIAL` for general (non-ask) speech. |
| `_emit_partial_question_transcript` | `backend/app/services/companion_runtime.py:701` | Emits `TRANSCRIPT_PARTIAL` for the "Ask AI" question text specifically; records `last_question_event_id` to trace (768-783). |
| `_push_to_deepgram_stream` | `backend/app/services/companion_runtime.py:821` | Pushes audio chunks into a Deepgram streaming connection for general transcription; checks `settings.MULTILANG_ENABLED` (939), uses `settings.resolve_deepgram_language` (890); sends `LANGUAGE_UPDATE`/`TRANSCRIPT_PARTIAL`/`TRANSCRIPT_UPDATE` (948-994); sends `native_audio: settings.ASK_AI_NATIVE_AUDIO` debug field (780). |
| `_push_ask_to_deepgram_stream` | `backend/app/services/companion_runtime.py:1045` | Pushes audio for the "Ask AI" private channel into Deepgram streaming; uses `settings.resolve_deepgram_language` (1039) — comment notes it "returns settings.DEEPGRAM_STREAM_LANGUAGE — identical to old behavior" (1034); sends `TRANSCRIPT_PARTIAL`/`TRANSCRIPT_UPDATE` (1117, 1208); records `last_question_event_id` to trace (1188-1205); NOTE at 1214: "deliberately do NOT clear `acc` on speech_final/UtteranceEnd". |
| `_emit_degraded_update` | `backend/app/services/companion_runtime.py:1229` | Sends `DEGRADED_MODE_UPDATE` with `session.degraded_mode`/`degraded_reasons`; wraps send in try/except pass. |

### `companion_runtime` singleton
- `companion_runtime = CompanionRuntime()` — `backend/app/services/companion_runtime.py:1245` (module-level instance, imported by `negotiation_engine.py`).

### WebSocket message types sent
`TRANSCRIPT_PARTIAL`, `TRANSCRIPT_UPDATE`, `LANGUAGE_UPDATE`, `DEGRADED_MODE_UPDATE`.

### Gotchas
- Line 369: comment about "multi-writer race at hold-release (garbled/truncated question text)" in `handle_audio_payload` — known race condition area.
- Line 562: "Lock-protected so we don't race vision frames or text injections" — concurrency-sensitive section in `_capture_private_ask_audio`/`_transcribe_snapshot_text`.
- Line 1034: comment clarifying `settings.resolve_deepgram_language` behavior is "identical to old behavior" — refactor-safety note.
- Line 1214: NOTE — deliberately does NOT clear `acc` (accumulator) on `speech_final`/`UtteranceEnd` events in `_push_ask_to_deepgram_stream` — if "fixing" double-accumulation here, this is intentional.
- `filter_ai_voice_leak` (76) hardcodes a homophone dictionary keyed to the word "claude"/"analysis" — likely tuned for a specific AI voice/name and may need updates if the AI persona name changes.

---

## Settings flags referenced (cross-file summary)

Key `settings.X` flags spanning all three files (see `backend/app/config.py` for definitions): `GOOGLE_GENAI_USE_VERTEXAI`, `MULTILANG_ENABLED`, `EVAL_MODE_ENABLED`, `GEMINI_API_KEY`, `GEMINI_PRECONNECT_WAIT_SECONDS`, `SPEECHBRAIN_ENABLED`, `TRANSCRIPTION_PROVIDER`, `SPEAKER_RECOGNITION_ENABLED`, `RESEMBLYZER_ENABLED`, `GEMINI_MODEL`, `VISION_ENABLED`, `VISION_PRO_ENABLED`, `VISION_PRO_MAX_FRAMES`, `VISION_PRO_LIVE_COOLDOWN_SECONDS`, `VISION_PRO_COOLDOWN_SECONDS`, `VISION_PRO_MIN_FRAMES`, `VISION_OBS_MAX_HISTORY`, `RESEARCH_HISTORY_LIMIT`, `VISION_LIVE_SEND_INTERVAL_SECONDS`, `VISION_INTEL_SEND_INTERVAL_SECONDS`, `ASK_AI_NATIVE_AUDIO`, `ASK_AI_NATIVE_ONLY_TRANSCRIPTION`, `ASK_AI_SUPPRESS_NATIVE_TRANSCRIPTION`, `ASK_AI_LOCAL_MIC_SUPPRESS_GRACE_SECONDS`, `ASK_AI_BATCH_TRANSCRIBE_TIMEOUT_SECONDS`, `MIN_TRANSCRIBE_DURATION_MS`, `STT_END_TO_END_TIMEOUT_SECONDS`, `ADVICE_GENERATION_ENABLED`, `ADVICE_GENERATION_TEMPERATURE`, `ADVICE_GENERATION_MAX_TOKENS`, `ADVICE_GENERATION_TIMEOUT_SECONDS`, `effective_model`/`effective_fallback_model`/`effective_flash_model`/`effective_advice_model`/`effective_vision_model`, `GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION`/`GOOGLE_APPLICATION_CREDENTIALS`, `GEMINI_LIVE_LANGUAGE_CODE`, `GEMINI_LIVE_VOICE_NAME`, `GEMINI_LIVE_ENABLE_AFFECTIVE_DIALOG`/`ENABLE_AFFECTIVE_DIALOG`, `AI_VOICE_LEAK_GRACE_SECONDS`, `AI_VOICE_LEAK_STRICT_POST_PLAYBACK_SECONDS`, `AI_VOICE_LEAK_SHORT_WORD_LIMIT`, `resolve_deepgram_language()`, `DEEPGRAM_API_KEY`, `DEEPGRAM_STREAM_LANGUAGE`.

## Cross-file call graph summary
- `negotiation_engine.py` → imports from `gemini_client.py`: `open_live_session`, `send_vision_frame`, `send_audio_chunk`, `receive_responses`, `keepalive_ping`, `handle_gemini_text`, plus `analyze_vision_frames`/`generate_tactical_advice` (used inline within handlers).
- `negotiation_engine.py` → imports `companion_runtime` singleton from `companion_runtime.py` for all companion-mode audio/state delegation.
- `gemini_client.py` → lazily imports `NegotiationEngine` from `negotiation_engine.py` inside `receive_responses` (lines 1615, 2145, 2165, 2227, 2320) and `monitor_session_lifetime` — circular dependency resolved via deferred import.
- `companion_runtime.py` → standalone; no imports from the other two files (only imported BY `negotiation_engine.py`).