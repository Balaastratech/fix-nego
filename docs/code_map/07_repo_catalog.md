I'll catalog this repo systematically. Let me start by exploring the structure and then gathering info on each section in parallel.

I notice there's also a PROJECT_OVERVIEW.md not in the original list, plus HANDOFF.md and lo.md. Let me read the heads of all the root-level md files in parallel batches, plus check backend/evals subfolders and other directories.

Now let me get the docs/ files, deploy/ files, backend root files, and test file docstrings.

Now let me get the test file docstrings/class names and check the scripts folder briefly, plus check ENROLLMENT/architecture/PROJECT_OVERVIEW dates more.

I have enough to grab the second non-docstring lines for files where the first grep didn't return useful info. Let me do a quick second pass for those test files and scripts.

I have enough information now to compile the complete catalog.

# Repo Catalog / Index — AI Negotiation Copilot

## 1. Root-level *.md / analysis files

- `ACTUAL_PROBLEM_ANALYSIS.md` — empty file (0 bytes) [STATUS: empty/stale]
- `COMPLETE_SPEAKER_FLOW_ANALYSIS.md` — deep dive on the two parallel speaker-ID systems (SpeakerService VAD+Resemblyzer vs ListenerAgent periodic Flash+Resemblyzer) and how they synchronize [STATUS: stale/superseded — predates PerfectListener refactor]
- `COMPREHENSIVE_AUDIO_PIPELINE_IMPLEMENTATION_BLUEPRINT.md` — large (100KB) zero-code architectural blueprint for a Conv-TasNet + Pyannote + WeSpeaker audio pipeline rewrite, dated 2026-04-01 [STATUS: stale — early planning blueprint, superseded by later PerfectListener/TASK_* implementation]
- `CRITICAL_ISSUES_FOUND.md` — log-driven bug list, headline issue is Flash returning empty diarization data in cycles [STATUS: stale — historical bug report]
- `DESKTOP_COMPANION_IMPLEMENTATION_PLAN.md` — plan for a Windows-first desktop companion app (sidecar for Zoom/Meet/Teams) alongside existing in-person web mode [STATUS: likely current/active — referenced by docs/plans deploy work]
- `ENROLLMENT_ISSUE_ANALYSIS.md` — short analysis of a 91-second audio gap causing enrollment timeout (20s timeout too short) [STATUS: stale — historical bug]
- `IMPLEMENTATION_ROADMAP.md` — notes/transcript explaining how "manual mode" speaker segmentation works correctly, used as reference for fixing auto mode [STATUS: stale — exploratory notes]
- `LISTENER_PERFORMANCE_ANALYSIS.md` — root-cause analysis of listener issues: speaker ID failures (Resemblyzer timing bug), missing audio, slow pipeline [STATUS: stale — historical analysis]
- `LOD2.MD` — raw JSON log dump (384KB) from app.services.gemini_client, dated 2026-04-07 [STATUS: stale — raw log artifact]
- `LOG_ANALYSIS.md` — analysis of speaker enrollment/negotiation log issues, e.g. 500+ "ignoring audio" warnings post-enrollment [STATUS: stale — historical bug analysis]
- `PERFECT_ACCURACY_SOLUTIONS.md` — research-driven plan for "perfect accuracy" (overlapping speech via Conv-TasNet, instant turn switching, 99%+ Resemblyzer accuracy) [STATUS: stale — superseded by PerfectListener implementation in backend]
- `PROJECT_STORY.md` — hackathon-style narrative ("inspiration", what it does) for the Gemini Live Agent Challenge submission [STATUS: stale/marketing-snapshot, likely from earlier hackathon phase]
- `RECOVERED_PLAN.md` — reconstructed plan from an Antigravity transcript covering speed/accuracy/AI-correctness optimization across the audio pipeline [STATUS: stale — recovered planning doc, see also docs/ANTIGRAVITY_SOTA_... which is a similar recovery]
- `RUNNING_COSTS.md` — monthly operating cost estimate for 100 active users on Cloud Run + Gemini Live/Flash + STT + SpeechBrain, May 2026 pricing [STATUS: possibly current reference, but flags some vendors (DeepSeek/Supabase/etc.) as not actual runtime deps]
- `SPEAKER_FLOW_ANALYSIS.md` — short overview of manual vs auto speaker ID paths and a race-condition issue in websocket.py/listener_agent.py [STATUS: stale — early version of COMPLETE_SPEAKER_FLOW_ANALYSIS.md]
- `SPEAKER_RECOGNITION_FLOW_ANALYSIS.md` — fix-priority list for speaker recognition race conditions (single source of truth, timeline locks, etc.) [STATUS: stale — historical fix plan]
- `STEP_BY_STEP_FLOW_ANALYSIS.md` — empty file (0 bytes) [STATUS: empty/stale]
- `TIMING_AND_CHUNKING_ANALYSIS.md` — deep dive into audio timing/chunking problems with a concrete speaker-overlap timeline scenario [STATUS: stale — historical analysis]
- `VERTEX_AI_DEPLOYMENT.md` — guide for switching between Gemini API (dev) and Vertex AI (prod, IAM auth) for Cloud Run deployment [STATUS: possibly stale — repo has since moved toward Oracle/desktop deploy per docs/plans]
- `VOICE_RECOGNITION_SYSTEM_FLOW.md` — full end-to-end documentation of voice recognition/transcription flow from frontend AudioWorklet through backend [STATUS: stale — likely predates PerfectListener]
- `architecture-diagram.html` — standalone HTML/CSS architecture diagram visualization for the project [STATUS: unknown, possibly current visual reference]
- `d.md` — single curl command snippet for Google Speech-to-Text v2 (chirp_3 model) [STATUS: stale scratch note]
- `fronlo.md` — raw frontend browser console log dump (WebSocket/enrollment events) [STATUS: stale — debug log artifact]
- `l.md` — raw terminal session log (uvicorn startup on Windows venv), 436KB [STATUS: stale — debug log artifact]
- `lod.md` — raw terminal/uvicorn log with SpeechBrain patch notices, 279KB, dated 2026-04-07 [STATUS: stale — debug log artifact]
- `loged.md.txt` — raw structured JSON log of negotiation_engine message routing, dated 2026-04-03 [STATUS: stale — debug log artifact]
- `plan_entry2_raw.txt` — essentially empty (3 bytes, BOM only) [STATUS: empty/stale]
- `render.yaml` — Render Blueprint for deploying backend/ as a lean BYOK Python web service (no Docker/Caddy), all heavy speaker-recognition flags set False [STATUS: possibly current alt-deploy option, parallel to deploy/ Oracle setup]
- `README.md` — main project README: product description, live demo URLs (Cloud Run frontend/backend), built for Gemini Live Agent Challenge [STATUS: current but may reference older Cloud Run deploy vs newer desktop/Oracle direction]
- `PROJECT_OVERVIEW.md` — (not in original list but present) high-level project identity doc: working real-time negotiation assistant, current strength is live coaching w/ manual speaker control, next push is automatic speaker recognition hardening [STATUS: current — appears to be the up-to-date overview]

Note: also present but not listed in the task — `HANDOFF.md` (341KB, the live agent relay/history file per AGENTS.md) and `backend/lo.md` / `backend/error_output.txt` / `backend/out2.txt` / `backend/device_verification_log.txt` / `backend/test_models.txt` (all raw debug/log scratch files, mostly UTF-16 garbled text, model-availability error logs) [STATUS: stale debug artifacts].

## 2. docs/ folder

- `docs/AI_NEGOTIATION_COPILOT_FULL_SYSTEM_SPEC.md` — full end-to-end product/system spec defining the negotiation copilot for AI/engineer/designer consumption [STATUS: likely current — canonical spec]
- `docs/AI_NEGOTIATION_COPILOT_FULL_SYSTEM_SPEC.json` — same spec as structured JSON (meta/product fields) for machine consumption [STATUS: likely current, companion to the .md spec]
- `docs/FULL_ENGINEERING_AUDIT_2026-05-21.md` — production-readiness style engineering audit (SRE/OWASP-informed) of the whole repo, dated 2026-05-21 [STATUS: current-ish reference, recent date]
- `docs/ANTIGRAVITY_SOTA_SPEED_ACCURACY_PLAN_RECOVERED.md` — recovered (2026-05-23) Antigravity SOTA speed/accuracy architectural plan from a transcript, with explicit gaps marked [STATUS: stale/recovered planning doc — overlaps RECOVERED_PLAN.md]
- `docs/DRIVERLESS_MIC_ISOLATION_PLAN.md` — approved (not yet implemented) plan to replace VB-Cable with driverless per-process mic isolation for the desktop companion (Windows only), owned by Claude Code [STATUS: current/active — approved but pending implementation]
- `docs/AI Negotiation Copilot — Complete P.txt` — long-form complete product description (multimodal real-time negotiation assistant for Live Agent category) [STATUS: likely older marketing/product doc, overlaps README/PROJECT_STORY]

### docs/plans/
- `docs/plans/2026-05-29-desktop-hosted-backend-reference-plan.md` — reference snapshot of hosted-backend + desktop-client deployment direction (superseded but kept for reference) [STATUS: superseded, kept as reference]
- `docs/plans/2026-05-30-desktop-oracle-deploy-plan.md` — actionable, status-board-tracked plan for Desktop + Oracle-hosted backend deployment, supersedes the 05-29 plan [STATUS: current/active — has phase status board]

### docs/enterprise-saas-it-procurement-e2e/ (group)
A complete fictional E2E test scenario package for testing the copilot in an enterprise SaaS/IT procurement renewal negotiation (Cobalt Bank Group renewal). Contains 12 numbered docs covering: start-here guide, private user/seller brief, counterparty brief+script, AI timing/prompts, vendor order form, redline doc, expected vision-extraction results, pass/fail audit sheet, solo-counterparty AI prompt, web research basis, and exact dialogue transcripts (user + counterparty), plus a PDF redline summary and `assets/` folder. [STATUS: current — test fixture/scenario package]

### docs/real-user-e2e-test/ (group)
A second complete E2E test scenario package, framed as a "real business meeting" B2B vendor renewal (buyer/procurement lead, AI customer support platform renewal, ~$96k contract). Contains 13 numbered docs: start-here, user meeting brief, counterparty script, UI commands, AI prompts, observation/pass-fail sheet, web research basis, solo-run guide, exact test scripts (user + counterparty), live AI query/audit log, plus an "AEGIS sales proposal" doc and E2E eval script, and a PNG asset. [STATUS: current — test fixture/scenario package, appears to be a refined iteration of the procurement package]

## 3. deploy/ folder

- `deploy/Caddyfile` — Caddy reverse-proxy config for automatic HTTPS/WSS (Let's Encrypt) for the Oracle-hosted backend, part of "Phase C2/D" [STATUS: current — active Oracle deploy artifact]
- `deploy/DEPLOY.md` — walkthrough for Oracle Cloud deployment (Always-Free Ampere A1 VM + Caddy, api.balaastratech.com), companion to the 2026-05-30 Oracle deploy plan [STATUS: current/active]
- `deploy/companion-backend.service` — systemd unit file for running the lean backend via uvicorn on the Oracle VM (Phase D) [STATUS: current — active Oracle deploy artifact]
- `deploy/keepalive.sh` — periodic health-ping script to prevent Oracle Always-Free idle-reclaim (Phase D5) [STATUS: current]
- `deploy/rsync-exclude.txt` — exclude list for rsyncing backend/ to the Oracle VM (excludes dev scripts, evals, venv, PII data) (Phase F3) [STATUS: current]
- `deploy/setup-oracle.sh` — one-shot idempotent provisioning script for the Oracle Ampere A1 VM (Python 3.11, venv, etc.) (Phase D) [STATUS: current]
- `deploy/.env.oracle.example` — example env file for the lean BYOK hosted profile (Phase B/C/D), all provider keys empty/per-session [STATUS: current — template for Oracle .env]

All deploy/ files form a coherent, currently-active Oracle VM deployment toolkit tied to `docs/plans/2026-05-30-desktop-oracle-deploy-plan.md`.

## 4. xr-application/ folder

A self-contained pitch-deck/presentation generator for "Balaastratech AI Negotiation Copilot — AndroidXR" pitch materials. Contains `build_brief.js`/`build_deck.js` (Node scripts to generate the deck), `package.json`, pre-built output files (`Balaastratech_AI_Negotiation_Copilot_AndroidXR.pdf/.pptx`, `Balaastratech_OnePager_AndroidXR.pdf/.pptx`), `assets/` (advisor.png, context.png, shot1/2.png — UI mockup images), and `qa/` + `qa_brief/` (slide screenshots Slide1-6.PNG for QA review of the generated deck). [STATUS: side-project/marketing artifact, not core backend — likely current as the latest pitch deck]

## 5. backend/ root-level *.md and misc files

- `backend/6_SECOND_PIPELINE_IMPLEMENTATION_PLAN.md` — plan to cut pipeline latency from 8-10s to under 6s, dated 2026-04-07, "Implementation Ready" [STATUS: stale — historical optimization plan]
- `backend/ADVANCED_OPTIMIZATIONS_SOLUTIONS.md` — research-backed solutions doc (e.g. streaming STT + speaker buffer hybrid approach), dated 2026-04-07 [STATUS: stale — historical research notes]
- `backend/BUSINESS_MODEL_AND_PRICING_STRATEGY.md` — comprehensive cost/pricing/competitive-positioning strategy doc, v1.0 dated 2026-04-07 [STATUS: stale-ish, overlaps root RUNNING_COSTS.md]
- `backend/DEBUG_PERFECT_LISTENER.md` — debugging checklist for why PerfectListener isn't producing transcripts (audio reaching pipeline, etc.) [STATUS: stale — debug notes]
- `backend/DEPENDENCY_ISSUES.md` — summary of resolved dependency issues (PyTorch, numpy, pyannote.audio versions, fallback strategy) [STATUS: stale — historical, marked RESOLVED]
- `backend/DEPENDENCY_RESOLUTION.md` — specific numpy 2.x upgrade resolution for pyannote-core/metrics version conflicts [STATUS: stale — historical, marked resolved]
- `backend/DEPLOYMENT_GUIDE.md` — FFmpeg + TorchCodec setup guide for pyannote.audio 4.x audio backend [STATUS: possibly stale if pyannote/PerfectListener path is disabled in current deploy profile]
- `backend/FIXES_APPLIED.md` — empty file (0 bytes) [STATUS: empty/stale]
- `backend/GOOGLE_BIOMETRIC_PIPELINE_ANALYSIS.md` — feasibility analysis for a Google-only biometric voice pipeline, dated 2026-04-07, marked FEASIBLE [STATUS: stale — feasibility study, unclear if implemented]
- `backend/LISTENER_SPEED_OPTIMIZATION.md` — performance timeline analysis of listener pipeline (e.g. 11s transcription delay) with optimization targets [STATUS: stale — historical perf analysis]
- `backend/OPTIMIZATION_APPLIED.md` — log of applied listener speed optimizations (e.g. POLL_INTERVAL 5→1.5), dated 2026-04-07, COMPLETED [STATUS: stale but documents an applied change — historical record]
- `backend/PERFORMANCE_FIX_PLAN.md` — plan to fix "fast automatic transcription" 9+ second delay (Resemblyzer + Gemini bottlenecks) [STATUS: stale — historical fix plan]
- `backend/SETUP_FINAL.md` — "Task 1 Complete" record of dependency/dev-environment setup (PyTorch, numpy, FFmpeg, etc.) [STATUS: stale — historical setup record]
- `backend/SPEAKERSERVICE_DISABLED.md` — explains disabling SpeakerService (`SPEAKER_RECOGNITION_ENABLED=False`) in favor of PerfectListener-only, due to 9+s delays [STATUS: possibly current decision — worth checking against current `.env`/render.yaml which also shows speaker recognition flags False]
- `backend/TRANSCRIPTION_FIXES.md` — fixes for garbage transcriptions (mixed-language output, sub-1s segments) and rate limits [STATUS: stale — historical fix notes]

### TASK_*_IMPLEMENTATION_SUMMARY.md (group)
A series of implementation-summary docs documenting the build-out of the **PerfectListenerSystem** (5-stage audio pipeline):
- `TASK_3.1` — `_detect_overlap` method (Stage 1, overlap detection)
- `TASK_6.1` — `_identify_speaker` method with fallback chain, dated 2024-01-15 (likely typo for 2026)
- `TASK_6.2` — `_try_wespeaker` method (speaker ID fallback level)
- `TASK_6.3` — `_try_pyannote_embedding` method (Level 2 fallback)
- `TASK_7.1` — `_transcribe_turn` (Stage 5, Gemini Flash transcription)
- `TASK_12` — Ask AI mode compatibility for PerfectListenerSystem
- `TASK_18` — Logging/monitoring (timing, confidence, turn logs) for PerfectListenerSystem
- `TASK_21` — Frontend integration (consistent WebSocket message formats) for PerfectListenerSystem

[STATUS: stale historical build records, but collectively document how PerfectListenerSystem was constructed — useful as implementation history/reference]

### Misc config/requirements files
- `backend/requirements.txt` — main Python deps (fastapi, uvicorn, websockets, google-genai, google-cloud-speech, ~44 lines) [STATUS: current]
- `backend/requirements-desktop.txt` — lean BYOK deploy profile requirements for the Oracle-hosted desktop-companion backend [STATUS: current — used by Oracle deploy]
- `backend/requirements-dev.txt` — dev/test deps (pytest, pytest-asyncio, hypothesis, httpx) [STATUS: current]
- `backend/constraints.txt` — single pip constraint pinning `webrtcvad==9999.0.0` (likely a stub/skip pin) [STATUS: current, odd pin worth noting]
- `backend/Dockerfile` — Python 3.11-slim Docker image, non-root appuser, curl for healthcheck [STATUS: current]
- `backend/pytest.ini` — pytest config (testpaths=tests, asyncio_mode=auto, hypothesis stats, coverage settings, markers: asyncio/property/integration/unit) [STATUS: current]
- `backend/lo.md`, `backend/error_output.txt`, `backend/out2.txt`, `backend/device_verification_log.txt`, `backend/test_models.txt` — raw debug/log scratch files (terminal sessions, Gemini model-availability errors, UTF-16 garbled text) [STATUS: stale debug artifacts]

## 6. backend/tests/ — test files

- `test_accuracy_validation.py` — accuracy validation tests (docstring present, content not deeply inspected)
- `test_ask_ai_mode_compatibility.py` — Ask AI mode compatibility tests
- `test_ask_transcript_state.py` — tests `best_candidate`/`should_replace_frontend_text` from `app.services.ask_transcript_state` (transcript text reconciliation between Gemini and Deepgram)
- `test_audio_eval_common.py` — tests for `scripts.audio_eval_common` helpers (EvaluatedTurn, aggregate_turns, detect_edge_drop)
- `test_companion_runtime.py` — async tests for companion runtime (desktop companion backend behavior)
- `test_copilot_eval_harness.py` — tests for the copilot eval harness against `app.config.settings`
- `test_deepgram_stream.py` — tests for Deepgram streaming STT integration
- `test_e2e_integration.py` — end-to-end integration tests
- `test_frontend_integration.py` — frontend integration tests (message formats etc.)
- `test_listener_extraction_latency.py` — tests around listener context-extraction latency
- `test_live_ask_turn_packaging.py` — tests for packaging "Ask AI" live turns
- `test_manual_mode_compatibility.py` — manual speaker mode compatibility tests
- `test_negotiation_session_speaker_fields.py` — tests for speaker-related fields on `NegotiationSession`
- `test_next_move_cache.py` — "Tests for next_move_cache: classifier, freshness, and brief formatting"
- `test_perfect_listener_overlap.py` — PerfectListener overlap-detection tests
- `test_perfect_listener_segmentation.py` — PerfectListener turn segmentation tests
- `test_perfect_listener_separation.py` — PerfectListener speaker separation tests
- `test_real_voice_recognition.py` — real voice recognition tests (likely uses real audio fixtures)
- `test_session_trace.py` — tests `SessionTrace` writes JSONL + report (from `app.utils.session_trace`)
- `test_speaker_enrollment.py` — speaker enrollment flow tests (numpy/torch mocks, `NegotiationSession`)
- `test_speaker_integration.py` — speaker subsystem integration tests
- `test_speaker_mapping_service.py` — tests for `SpeakerMappingService` (maps speaker IDs to roles)
- `test_speaker_service.py` — `SpeakerService` unit tests
- `test_speaker_service_properties.py` — property-based (Hypothesis) tests for `SpeakerService`
- `test_startup.py` — app startup tests
- `test_stt_service.py` — tests for `SpeechTranscriptionService` (`app.services.stt_service`)
- `test_trace_helpers_and_report.py` — "Smoke tests for the enriched trace pipeline and report renderer"
- `test_voice_encoder.py` — voice encoder (embedding) tests
- `test_wespeaker_method.py` — WeSpeaker speaker-ID fallback method tests
- `unit/test_speaker_identification.py` — unit-level speaker identification tests (separate `unit/` subfolder)

## 7. backend/scripts/ and backend/evals/

### backend/scripts/
- `_debug_eval_events.py` — small CLI debug tool: loads an eval JSON file (by path arg) and inspects events
- `_debug_eval_report.py` — small CLI debug tool: loads an eval report JSON and inspects it
- `_show_scenario.py` — CLI tool: prints a scenario by ID from `evals/copilot_scenarios.json`
- `_smoke_pro_advice.py` — "Quick smoke test that bypasses the full eval/websocket harness" for pro-advice generation
- `audio_eval_common.py` — shared helpers for audio eval scoring (EvaluatedTurn, aggregate_turns, edge-drop detection, etc.) — used by `test_audio_eval_common.py`
- `cost_report.py` — "Real per-session cost report from session_traces" — computes API cost per session
- `eagle_probe.py` — "Standalone Picovoice Eagle proof harness" for speaker verification (enrollment/genuine/impostor PCM files)
- `generate_audio_eval_corpus.py` — generates synthetic audio eval corpus (TTS-based, manifest+wav)
- `run_audio_backend_eval.py` — runs the audio backend eval against generated corpus
- `run_copilot_eval.py` — main copilot eval runner (scripted negotiation scenarios over real WebSocket, with optional LLM judge)
- `speechbrain_probe.py` — probes SpeechBrain models (timing/statistics) for speaker embedding feasibility

### backend/evals/
- `README.md` — "Copilot Evaluation Harness" docs: tests Live AI advisor with scripted speaker-labeled turns over real WebSocket, bypassing mic/STT/speaker recognition; requires `EVAL_MODE_ENABLED=True`
- `audio_fixtures/` — manifest.json + wav/ folder, real-recorded(?) audio fixtures for audio pipeline evals
- `audio_fixtures_pyttsx3/` — manifest.json + wav/ folder, pyttsx3-TTS-generated synthetic audio fixtures (parallel set to `audio_fixtures/`)
- `copilot_scenarios.json` — the scripted negotiation scenario definitions used by `run_copilot_eval.py`

[STATUS for section 7: all current — active eval/test tooling]