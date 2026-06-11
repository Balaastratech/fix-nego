# backend/app/utils/ — logging, tracing & audit modules

Five separate, independently-toggleable logging/tracing streams exist in this codebase. They do NOT share state and can be enabled/disabled independently via settings flags. This file documents the ones not covered in `03_backend_speaker_infra.md`.

---

## backend/app/utils/session_logger.py (427 lines)

**Purpose**: Human-readable, per-session `.log` file. One `SessionLogger` per active negotiation session.

- `LOG_DIR = data/logs/sessions/` — writes `data/logs/sessions/{session_id}.log`.
- Registry functions `:26-43` — `get_session_logger(session_id)`, `create_session_logger(session_id)`, `close_session_logger(session_id)`.
- `_ts()` / `_elapsed()` `:62-71` — timestamp + elapsed-since-session-start helpers.

**Key log methods (each appends a formatted line):**
- `session_started` / `session_ended` `:104-127`
- `gemini_live_connected` / `gemini_live_reconnected` / `copilot_activated` `:129-136`
- `transcript` / `transcript_diarized_turn` `:140-162`
- `text_extraction_result` `:166-198`
- `audio_extraction_result` `:202-219`
- `context_extracted` `:223-244`
- `research_triggered` / `research_complete` / `person_research_complete` / `company_research_complete` `:248-299`
- `vision_analyzed` / `document_page_captured` `:303-350`
- `pre_query_brief_sent` / `intel_injected` `:354-383`
- `hold_activated` / `hold_released` / `ask_ai_question` / `ai_response` `:387-415`
- `error` / `note` `:419-426`

**Gotchas**: This is the "narrative" per-session log — distinct from `session_trace.py` (structured JSONL + report.md) and `conversation_audit.py` (flat dedup'd JSONL stream).

---

## backend/app/utils/logging_config.py (168 lines)

**Purpose**: Process-wide `dictConfig` logging setup, called once at startup via `setup_logging()`.

- `CorrelationIdFilter` `:14-17` — injects correlation ID into log records.
- `TerminalFormatter` `:21-92` — pretty-prints console output.
  - `_SKIP_PREFIXES` `:29-56` — tuple of noisy log-message prefixes dropped from the terminal entirely (but still written to the JSON file handler).
  - `_MODULE_SHORT` `:58-69` — maps long module paths to short tags for terminal readability: e.g. negotiation_engine→"engine", gemini_client→"gemini", stt_service→"stt", listener_agent→"listener", companion_runtime→"companion", deepgram_stream→"dgstream", websocket→"ws", session_store→"store".
  - `_LEVEL_COLORS` `:71-78` — ANSI color codes per log level.
- `_SkipEmptyFilter` `:95-102` — drops empty-message log records.
- `get_logging_config(log_level)` `:105-150` — returns the dictConfig dict:
  - File handler → JSON lines to `data/logs/backend.jsonl` (everything, unfiltered).
  - Console handler → `TerminalFormatter` (filtered via `_SKIP_PREFIXES`/`_SkipEmptyFilter`).
- `setup_logging(log_level)` `:153-168` — applies the dictConfig AND silences noisy third-party loggers (`httpx`, `google_genai.models`, `httpcore`, `urllib3`) to WARNING.

**Gotchas**: If you add a new noisy log line, either prefix-match it into `_SKIP_PREFIXES` (terminal only) or it will spam the console; the JSON file (`backend.jsonl`) always gets everything regardless.

---

## backend/app/utils/session_trace.py (368 lines)

**Purpose**: Structured per-session JSONL event trace + auto-generated markdown report (`report.md`) — the richest of the five logging streams, designed for post-hoc debugging/analysis of a single session.

- `TRACE_ROOT = backend/data/logs/session_traces/` — one directory per session: `session_traces/{session_id}/`.
- Registry functions `:18-36` — `create_session_trace(session_id)`, `get_session_trace(session_id)`, `close_session_trace(session_id)`.

**`SessionTrace` class `:39-368`:**
- `__init__` — sets up `session_dir`, `artifact_dir`, `trace_path` (`trace.jsonl`), `report_path` (`report.md`).
- `_bootstrap_from_disk()` `:58-70` — on init, replays any existing `trace.jsonl` into memory (supports session resume).
- `record(*, category, name, summary, data, artifacts, related_event_ids, include_in_report)` `:113-145` — appends an event dict to `trace.jsonl` AND in-memory list. This is the primary write API, called via `trace_helpers.safe_record()`.
- `finalize()` `:147-154` — writes `report.md` via `_build_report_lines()`.
- `_LONG_TEXT_KEYS` `:159-165` — set of keys (e.g. `question_text`, `response_text`, `advice_text`) that get rendered as fenced code blocks in the report.
- `_CATEGORY_LABELS` `:168-180` — maps event category → human-readable section label, e.g. `"ask_ai"` → `"Private ask flow (hold-to-ask)"`.
- `_build_report_lines()` `:182-211` — assembles report.md: header, Conversation Summary, Event Counts by Category, Event Timeline.
- `_build_conversation_summary()` `:223-313` — linear retelling of the user/AI exchange.
  - `ask_quality_score()` `:230-241` — scores candidate ask-text sources.
  - `source_rank` dict `:225-229` — `partial=1, batch_transcription=2, gemini_live_input=3` — used to pick the BEST ask text per `ask_entry_id` when multiple transcription sources raced (relevant to the Deepgram/native-audio ask-transcription history described in HANDOFF.md).
- `_render_event()` `:322-354`, `_render_value()` `:356-367` — low-level report formatting helpers.

**Gotchas**: `trace.jsonl` + `report.md` paths are surfaced to the frontend via `CONNECTION_ESTABLISHED` (`trace_jsonl_path`/`trace_report_path`, see `04_backend_api_models_providers.md` → websocket.py). The `source_rank` logic here is directly relevant to any future ask-transcription-race debugging.

---

## backend/app/utils/trace_helpers.py (248 lines)

**Purpose**: Helper layer on top of `session_trace.py` — provides `TraceTimer`, a context manager for timing+recording model calls, plus small formatting utilities. Used throughout `negotiation_engine.py`/`gemini_client.py` to record `*_started`/`*_completed`/`*_failed` trace events uniformly.

- `model_block(name, *, route, timeout_s, purpose, temperature, max_tokens)` `:26-50` — builds a uniform "attribution" dict describing a model call (which model/route/purpose/params) for inclusion in trace events.
- `model_route()` `:53-59` — returns `"vertex"` or `"api"` based on `settings.GOOGLE_GENAI_USE_VERTEXAI` (raw env flag, NOT the effective runtime_config-resolved value — note the asymmetry vs `config.py._effective_use_vertex()`).
- `safe_record(session_id, **kwargs)` `:62-72` — never-raising wrapper around `SessionTrace.record()`; safe to call from any code path without try/except.
- `text_preview(text, limit=400)` `:75-82` — truncates text for trace readability.
- `extract_token_usage(response)` `:85-104` — extracts prompt/candidates/thoughts/total/cached token counts from a Gemini `usage_metadata` object.
- `finish_reason(response)` `:107-114` — extracts the finish reason string from a Gemini response.
- `TraceTimer` class `:117-247` — context manager:
  - `__enter__` — records `*_started` event, starts timer.
  - `complete(summary, data, artifacts)` — records `*_completed` with latency.
  - `fail(reason, summary, data, artifacts)` — records `*_failed` with latency.
  - `__exit__` — auto-completes (if not already completed/failed) or auto-fails on exception; never suppresses the exception.

**Gotchas**: `TraceTimer.__exit__` never swallows exceptions — it just ensures a trace event is recorded either way. Any new model-call site should wrap with `TraceTimer` for trace-report visibility rather than ad-hoc logging.

---

## backend/app/utils/conversation_audit.py (91 lines)

**Purpose**: Append-only JSONL audit log of conversation events (transcripts, AI responses, ask-AI exchanges) — a lightweight, dedup'd flat event stream for offline analysis, separate from `session_trace.py`/`session_logger.py`.

**Module state:**
- `_write_lock`, `_recent_lock` `:14-15` — threading locks for file writes and dedup tracking.
- `_recent_events: dict[tuple[str,str,str,str], float]` `:16` — maps `(session_id, event, speaker, cleaned_text)` → last-seen timestamp.
- `_DEDUP_WINDOW_SECONDS = 3.0` `:17` — suppression window for duplicate events.

**Functions:**
- `log_conversation_event(*, session_id, event, speaker, text, timestamp_ms=None, context=None, response_mode=None, metadata=None)` `:20-67` — no-op if `CONVERSATION_AUDIT_LOG_ENABLED=False` or text empty; dedupes via `_is_duplicate`; writes a JSONL line (timestamp/session_id/event/speaker/text/context/response_mode/metadata) to `settings.CONVERSATION_AUDIT_LOG_PATH`.
- `_compact_text(value)` `:70-76` — collapses whitespace, truncates to 2000 chars.
- `_is_duplicate(key)` `:79-91` — `(session_id, event, speaker, text)` tuple dedup with a 3.0s window; prunes stale entries on each call.

**Gotchas**: Controlled by its own `CONVERSATION_AUDIT_LOG_ENABLED`/`CONVERSATION_AUDIT_LOG_PATH` settings — toggle independently of `session_trace`/`session_logger`. All failures swallowed silently (never breaks the runtime path).

---

## backend/app/utils/speechbrain_patch.py (57 lines)

**Purpose**: One-shot monkeypatch module that suppresses SpeechBrain's lazy-import failures so Pyannote model loading doesn't crash.

- `patch_speechbrain_k2()` `:13-57` — registers `warnings.filterwarnings` to ignore `.*Lazy import.*failed.*` UserWarnings, then injects a `DummyModule` instance (returns `None` for any attribute/call, defined inline `:30-35`) into `sys.modules` for: `speechbrain.integrations.k2_fsa`, `speechbrain.integrations.nlp`, `speechbrain.integrations.kenlm`, `speechbrain.k2_integration`, `k2`, `k2_fsa`, `kenlm` `:39-47`. Prints a `[PATCH]` confirmation and returns `True`/`False`.

**Gotchas**: MUST be called BEFORE importing `pyannote.audio` (per module docstring `:1-7`) — called from `main.py:14-15` at process startup, before any pyannote-dependent speaker-recognition modules are imported. We don't use the k2/nlp/kenlm SpeechBrain integrations (Gemini handles transcription), so stubbing them is safe.

---

## backend/app/utils/speaker_debug.py (50 lines)

**Purpose**: Lightweight, opt-in debug logger for speaker-recognition/diarization pipeline events — purely ad-hoc, separate from all other logging streams.

- `log_speaker_debug(event, **fields)` `:16-37` — no-op if `settings.SPEAKER_DEBUG_LOG_ENABLED=False`; formats each kwarg via `_format_value` and appends a pipe-delimited line (`timestamp | event | key=value | key=value | ...`) to `settings.SPEAKER_DEBUG_LOG_PATH`. Swallows all exceptions.
- `_format_value(value)` `:39-50` — strings >220 chars truncated+JSON-escaped; lists/dicts/tuples JSON-serialized (truncated if >400 chars); other types via `str()`.

**Gotchas**: Pipe-delimited (NOT JSON) format — distinct from `conversation_audit.py` (JSONL) and `session_trace.py` (JSONL). Gated by its own `SPEAKER_DEBUG_LOG_ENABLED` flag.

---

## Summary: the five logging/tracing streams

| Stream | Format | Path | Flag | Scope |
|---|---|---|---|---|
| `logging_config.py` | JSON lines (file) + colored text (console) | `data/logs/backend.jsonl` | always on | process-wide |
| `session_logger.py` | human-readable text | `data/logs/sessions/{session_id}.log` | always on (per session) | per-session narrative |
| `session_trace.py` | JSONL events + `report.md` | `data/logs/session_traces/{session_id}/` | always on (per session) | per-session structured trace + report |
| `conversation_audit.py` | JSONL (dedup'd) | `data/logs/copilot_conversation_audit.jsonl` | `CONVERSATION_AUDIT_LOG_ENABLED` | flat cross-session conversation stream |
| `speaker_debug.py` | pipe-delimited text | `data/logs/speaker_debug.log` | `SPEAKER_DEBUG_LOG_ENABLED` | speaker pipeline ad-hoc debug |
