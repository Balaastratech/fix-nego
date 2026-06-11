# Code Map — AI Negotiation Copilot

**Purpose of this directory**: a structured reference map of the entire `fix-nego` codebase, written so a Claude Code session can jump straight to the relevant file/line instead of re-exploring the repo from scratch. Each file below covers a slice of the codebase with `path:line` references, class/function inventories, settings flags, message types, and known gotchas/dead code.

**Read this file first**, then open only the specific numbered file(s) relevant to your task.

---

## What this project is

"AI Negotiation Copilot" — a real-time negotiation coaching assistant:
- **Backend**: FastAPI (Python) WebSocket server (`backend/app/`). Single `/ws` endpoint drives the whole session. Uses Gemini Live (native audio) for the conversational AI, Deepgram/Google STT for transcription, SpeechBrain ECAPA-TDNN for speaker verification, and a multi-provider abstraction layer (BYOK: OpenAI/Anthropic/Groq/DeepSeek/OpenRouter/etc.) for swappable model providers.
- **Frontend**: Next.js/React/TypeScript (`frontend/`) — the in-browser dashboard UI.
- **Desktop**: Electron companion app (`desktop/` or similar) — floating overlay + dashboard, used for "virtual companion" mode (binds to a meeting window, captures system audio).
- **xr-application/**: separate side project (pitch-deck generator, marketing artifact — not part of the core product).

---

## Index of code map files

| File | Covers | Key paths |
|---|---|---|
| `01_backend_core.md` | The 3 largest/most central backend services | `services/negotiation_engine.py` (3459L), `services/gemini_client.py` (2357L), `services/companion_runtime.py` (1245L) |
| `02_backend_listener.md` | Dual-model listening/transcription pipeline | `services/listener_agent.py`, `services/perfect_listener.py`, `services/stt_service.py`, `services/next_move_cache.py`, `services/market_research.py` (dead) |
| `03_backend_speaker_infra.md` | Speaker recognition, session/connection infra, auth helpers, readiness | 23 files in `services/`: `speaker_service.py`, `speaker_mapping_service.py`, `speaker_enrollment.py`, `speechbrain_service.py`, `session_store.py`, `connection_manager.py`, `deepgram_stream.py`, `translation.py`, `ask_transcript_state.py`, `audio_buffer.py`, `bounded_async.py`, `capability_registry.py`, `app_tokens.py`, `auth_db.py`, `clerk_verify.py`, `response_validator.py`, `utterance_types.py`, `readiness.py`, + dead: `azure_speaker_service.py`, `voice_encoder.py`, `eagle_service.py`, `master_prompt.py`, `u.py` |
| `04_backend_api_models_providers.md` | Entrypoint, config, prompts, REST/WS API, data models, provider abstraction | `main.py`, `config.py`, `ai_assets.py`, `api/auth.py`, `api/auth_routes.py`, `api/providers.py`, `api/websocket.py`, `models/negotiation.py`, `models/messages.py`, `models/companion.py`, `providers/registry.py`, `providers/runtime_config.py`, `providers/model_catalog.py`, `providers/text_client.py` |
| `05_frontend.md` | Next.js frontend | `frontend/app/`, `frontend/components/`, `frontend/hooks/`, `frontend/lib/`, `frontend/utils/` |
| `06_desktop.md` | Electron desktop companion | `main.js`, `preload.js`, `overlay.js`, `full.js`, `app.js` (legacy/dead), `login.js`, `scripts/` (PowerShell helpers) |
| `07_repo_catalog.md` | Whole-repo doc/test/deploy inventory with stale/current flags | root `*.md` files, `docs/`, `deploy/`, `xr-application/`, `backend/tests/`, `backend/scripts/`, `backend/evals/` |
| `08_backend_utils_logging.md` | The 5 separate logging/tracing streams | `utils/session_logger.py`, `utils/logging_config.py`, `utils/session_trace.py`, `utils/trace_helpers.py`, `utils/conversation_audit.py`, `utils/speechbrain_patch.py`, `utils/speaker_debug.py` |

---

## Quick lookup: "I need to work on X"

| Task area | Start here |
|---|---|
| Gemini Live session lifecycle, reconnect, ask-AI native audio | `01_backend_core.md` → `gemini_client.py` |
| Negotiation state machine, message routing, hold-to-ask, vision injection | `01_backend_core.md` → `negotiation_engine.py` |
| Desktop/companion audio routing, dual-source capture | `01_backend_core.md` → `companion_runtime.py`, `06_desktop.md` |
| Transcription accuracy / STT provider behavior | `02_backend_listener.md` → `stt_service.py`, `03_backend_speaker_infra.md` → `deepgram_stream.py` |
| "What should I do now" cache / vague-ask routing | `02_backend_listener.md` → `next_move_cache.py` |
| Speaker ID / diarization / enrollment | `03_backend_speaker_infra.md` |
| Auth (Clerk, JWT, shared token, BYOK) | `04_backend_api_models_providers.md` → `api/auth.py`, `api/auth_routes.py`, `services/auth_db.py`, `services/clerk_verify.py`, `services/app_tokens.py` |
| Adding/changing a settings flag | `04_backend_api_models_providers.md` → `config.py` (full settings table) |
| Prompts / system instructions / what the AI is told | `04_backend_api_models_providers.md` → `ai_assets.py` |
| WebSocket message types (client↔server) | `04_backend_api_models_providers.md` → `models/messages.py` + `api/websocket.py` |
| Multi-provider / BYOK runtime config | `04_backend_api_models_providers.md` → `providers/*.py` |
| Frontend dashboard / hooks / WS client | `05_frontend.md` |
| Electron overlay/dashboard, IPC, privacy isolation | `06_desktop.md` |
| "Is this doc/test/script still relevant?" | `07_repo_catalog.md` |
| Logging/tracing a session for debugging | `08_backend_utils_logging.md` |
| Cross-agent history of recent fixes/decisions | `/home/user/fix-nego/HANDOFF.md` (NOT in this code map — see `AGENTS.md`/`CLAUDE.md` relay protocol) |

---

## Top cross-cutting gotchas (collected from all files — see source file for detail)

1. **`frontend/lib/types.ts` does not exist** but is imported by 6 files — build-breaking. See `05_frontend.md`.
2. **Phase G per-session BYOK**: `NegotiationSession.provider_overrides` flows through `runtime_config.set_session_overrides()` (called at `websocket.py:127` AND on every received message at `websocket.py:170`) into a `ContextVar` consulted by every provider/model/key resolver in `providers/runtime_config.py`. See `04_backend_api_models_providers.md`.
3. **Master revert switches**: `PROVIDER_RUNTIME_OVERRIDE_ENABLED` (ignore `runtime_providers.json`, pure `.env`) and `PER_SESSION_PROVIDER_OVERRIDE_ENABLED` (disable Phase G BYOK).
4. **ASK_AI native-audio flags** (`ASK_AI_NATIVE_AUDIO`, `ASK_AI_NATIVE_ONLY_TRANSCRIPTION`, `ASK_AI_SUPPRESS_NATIVE_TRANSCRIPTION`, `ASK_AI_ACTIVITY_END_DELAY_SECONDS`) control which model transcribes the user's private "ask" question and have a documented history of race conditions — see `HANDOFF.md` for the most recent fixes/reversals and `04_backend_api_models_providers.md`/`config.py` for current defaults.
5. **MULTILANG_ENABLED** (default True) gates Deepgram multi-language mode, per-source language profiles, Gemini auto-language, response-language prompts, and pro-advice translation.
6. **Google backend (Vertex vs AI Studio)** is resolved via `runtime_config.google_backend()`/`google_use_vertex()`, NOT the raw `GOOGLE_GENAI_USE_VERTEXAI` env. Live model IDs differ entirely between the two backends.
7. **SpeechBrain exclusivity**: if `SPEECHBRAIN_ENABLED=True`, `RESEMBLYZER_ENABLED`/`WESPEAKER_ENABLED`/`AZURE_SPEAKER_VERIFICATION_ENABLED` must all be False or startup raises `RuntimeError` (`main.py`).
8. **k2_fsa/pyannote patches must run first**: `patch_speechbrain_k2()` (`utils/speechbrain_patch.py`) and the `hf_hub_download` shim must execute before any pyannote import — done at the top of `main.py`.
9. **Auth layering**: `COMPANION_SHARED_TOKEN` empty = Phase C shared-token auth fully disabled; `AUTH_REQUIRED=False` = Clerk JWT auth also fully open (anonymous admin `AuthUser`). Both can coexist.
10. **`gemini_send_lock`** on `NegotiationSession` serializes ALL `send_realtime_input` calls to the Gemini Live session — any new code path that sends to Live must acquire this lock.
11. **Five separate logging/tracing streams** exist (`backend.jsonl`, per-session `.log`, per-session `trace.jsonl`+`report.md`, conversation audit JSONL, speaker debug log) — see `08_backend_utils_logging.md` for which to use when.
12. **Likely-dead modules**: `services/azure_speaker_service.py`, `services/eagle_service.py`, `services/voice_encoder.py`, `services/master_prompt.py`, `services/u.py` (empty), `services/market_research.py`, `desktop/app.js` (legacy renderer), `frontend/components/negotiation/VideoCapture.tsx`, `frontend/components/negotiation/StrategyPanel.tsx` — verified zero inbound references at time of writing. Confirm with a fresh grep before deleting.

---

## Maintenance note

If you make a significant architectural change (new service file, renamed module, removed dead code, new settings flag category), update the relevant numbered file in this directory rather than letting it go stale. Each file's "Gotchas" sections are the highest-value content for future sessions — keep them accurate.
