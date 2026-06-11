# Phase 0 — Foundations (blocking, do first)

Everything in this phase either (a) currently breaks the build/product, (b) blocks monetization, or (c) blocks legal launch. Phase 1/2/3 work should not start in earnest until 0.1, 0.3, and ideally 0.2 land (0.4/0.5/0.6 can be picked up opportunistically by whoever is in those files).

---

## 0.1 [FIX] Restore `frontend/lib/types.ts` (build-breaking)

**Severity**: P0 — frontend will not typecheck/build without this.

**Where**: `frontend/lib/types.ts` (does not exist). Imported by `useNegotiation.ts:4-12`, `useNegotiation.test.ts`, `NegotiationDashboard.tsx`, `NegotiationStateCard.tsx`, `TranscriptPanel.tsx`, `StrategyPanel.tsx` (`docs/code_map/05_frontend.md:33,543`).

**What to do**:
- Reconstruct the file with the exports the code map already inferred from usage (`docs/code_map/05_frontend.md:41`):
  - `NegotiationState` — fields: `isConnected, consentGiven, isNegotiating, sessionId, transcript, strategy, outcome, error, aiDegraded, aiState, copilotActive, responseMode, aiLiveTranscription, language, responseLanguage, persistenceReady, degradedMode, enrollmentState, enrollmentCountdown, enrollmentError, enrollmentProgress, enrollmentFeedback, speakerMode, visionIntel, isAudioActive, isVisionActive` (cross-check against the reducer in `useNegotiation.ts:70-176`).
  - `INITIAL_NEGOTIATION_STATE` — default values for all of the above.
  - `TranscriptEntry` — lowercase `speaker: 'user'|'counterparty'|'ai'|'unknown'`, plus `isPartial/confidence/source/context` (per `useNegotiation.ts:307-319`). **Do not confuse with** the differently-shaped `TranscriptEntry` in `hooks/useNegotiationState.ts:28-33` (uppercase speaker, no extra fields) — both names exist by design in different contexts; do not merge them.
  - `Strategy` — fields per `StrategyPanel.tsx:21-29`.
  - `OutcomeSummary`, `ServerMessageType`, `WebSocketMessage` (`{ type: string, payload: unknown }` minimum).
- Note `StrategyPanel.tsx` is also flagged as a likely-dead component (`00_INDEX.md:70`) — verify with a fresh import-grep before deciding whether to (a) keep it and restore its `Strategy` type usage, or (b) remove it and drop its type from `types.ts` if genuinely unused. Don't let Phase 4 cleanup and this fix conflict — resolve `StrategyPanel.tsx`'s status here since you're already touching its dependency.

**Acceptance criteria**: `cd frontend && npm run build` (or `tsc --noEmit`) passes with zero `lib/types` errors. `useNegotiation.test.ts` passes.

**Skill**: `verify` after the fix; `code-review` optional (low risk, additive types file).

---

## 0.2 [NEW] Billing / metering / entitlements infrastructure

**Severity**: Blocks all revenue — "the largest single lack" per the gap analysis. Currently `session_metrics` (per `docs/code_map/04_backend_api_models_providers.md:489`, `negotiation.py:282-310`) tracks counters (stt/speaker/research/ask/vision_pro_call_count etc.) but nothing reads them for limits or billing.

**Decision needed before coding** (flag via `AskUserQuestion`): payment processor (Stripe is the default assumption — confirm), and initial tier shape. Use the pricing tiers validated in `docs/plans/2026-06-11-market-research-monetization.md` as the starting point: Free / Pro ($29-39/mo) / Team ($59-79/seat) / Event Pass ($49-149 one-time).

**What to build**:
1. **Data model**: new tables/columns alongside `sessions` table (`backend/app/services/session_store.py:36-122`) — `accounts`/`users` (if not present — check `services/auth_db.py` per `docs/code_map/03_backend_speaker_infra.md`), `subscriptions` (plan, status, period), `usage_ledger` (session_id, account_id, minutes_used, asks_used, timestamp) seeded from existing `session_metrics`.
2. **Entitlement resolver**: a service (new `backend/app/services/entitlements.py`) that, given an authenticated `AuthUser` (from `services/auth_db.py`/`api/auth.py`), returns the active plan + remaining quota. Call this at session start (`handle_start`, `negotiation_engine.py:414`) and reject/soft-cap (`ERROR` message) if quota exhausted.
3. **Stripe integration**: webhook endpoint (new route in `api/`) for subscription lifecycle events (created/updated/canceled, checkout completed for Event Pass), checkout-session creation endpoint for the frontend pricing page.
4. **Usage metering hook**: at `_finalize_session_cleanup` (`connection_manager.py:98`) — after `session_store.persist_session`, write a `usage_ledger` row from `session.session_metrics`.
5. **Frontend**: pricing/upgrade page, plan badge in dashboard, "quota low/exhausted" banner wired to the new `ERROR`/a new `QUOTA_UPDATE` message type (extend `models/messages.py` per `docs/code_map/04_backend_api_models_providers.md:500-516` pattern).
6. **Settings flags**: `BILLING_ENABLED` (default False until verified end-to-end on a staging Stripe account), `BILLING_ENFORCEMENT_ENABLED` (separately gate hard quota cutoffs from soft warnings) — follow the existing `*_ENABLED` flag convention in `config.py`.

**Acceptance criteria**: a free-tier session over quota gets a graceful in-app upgrade prompt (not a hard crash); a Stripe test-mode checkout completes and flips the account's plan; `usage_ledger` rows are created per session.

**Skills**: `Plan` subagent first (this is the most architecturally complex item in the whole plan — get a sub-plan before coding). `security-review` + `code-review` mandatory (webhook signature verification, payment data handling). `verify` after.

---

## 0.3 [FIX] Consent flow — pre-session, geo-aware

**Severity**: P0, legal blocker. All-party-consent requirement applies in 11 US states + CT.

**Where it exists today**: `PRIVACY_CONSENT_GRANTED` → `handle_consent` (`negotiation_engine.py:272`) sets `consent_mode`, sends `CONSENT_ACKNOWLEDGED`; frontend `PrivacyConsent` component gates the dashboard (`docs/code_map/05_frontend.md:51`, `handleConsent` at `useNegotiation.ts`-driven dashboard `:154-163`); `ConsentPayload` (`messages.py:9` — `version`, `mode`: "live"|"roleplay"); `ConsentAcknowledgedPayload` (`messages.py:148` — mode/recording_active); `sessions` table stores `consent_version`/`consent_mode` (`session_store.py:36-122`).

**Gap**: the existing flow captures *that* consent was granted but is not geo-aware and (per the gap analysis) doesn't yet cover the **in-person** all-party-consent case where the AI is listening to a live room with a counterparty who hasn't seen any UI at all.

**What to do**:
1. Add a jurisdiction field to `ConsentPayload`/`ConsentAcknowledgedPayload` (e.g., `jurisdiction: string | null`, populated client-side via a coarse IP/timezone hint or explicit user-selected state — do not silently geolocate without disclosure).
2. Frontend `PrivacyConsent` component: when jurisdiction is in the all-party-consent list (CA, CT, FL, IL, MD, MA, MT, NV, NH, OR, PA, WA, DE per research — confirm exact list against `docs/plans/research-2026-06-11/6_verify_legal.md` before hardcoding), show explicit copy: "this app records and analyzes audio of everyone in the conversation; you must obtain the other party's consent before proceeding," with a checkbox acknowledgment stored as `consent_mode` metadata.
3. This item feeds directly into **1.5 (in-person verbal consent capture)** in Phase 1 — 0.3 is the data-model/legal-copy foundation; 1.5 is the in-person UX (e.g., a spoken consent disclosure the AI itself can play/prompt for at session start).

**Acceptance criteria**: a session started from a flagged jurisdiction cannot proceed past `IDLE`→`CONSENTED` without the explicit all-party acknowledgment; `consent_mode`/jurisdiction is persisted in `sessions` and visible in `session_trace`/`report.md`.

**Skills**: `code-review`/`security-review` (legal-sensitive copy + state persistence). Consider `AskUserQuestion` on exact jurisdiction list and copy wording — this is genuinely a product/legal decision, not purely technical.

---

## 0.4 [NEW] Latency instrumentation (per-stage timing vs <1.5s budget)

**Severity**: Needed to validate the "glanceable cue card" UX work in Phase 1/2 against the verified <1.5s perceived-latency threshold (Cresta benchmark, `docs/plans/2026-06-11-market-research-monetization.md`).

**Where**: the "Ask AI" pipeline is `handle_user_addressing_ai` (`negotiation_engine.py:1618`, ~670 lines) and `receive_responses` (`gemini_client.py:1548`, the core read loop). Five logging streams already exist (`docs/code_map/08_backend_utils_logging.md`) — `session_trace.py` (`trace.jsonl`+`report.md`) is the right place to add stage timestamps since it's already structured JSONL designed for "post-hoc debugging/analysis of a single session" (`08_backend_utils_logging.md:53`).

**What to do**:
1. Add trace events at each pipeline boundary for an "ask": `ask_audio_received` → `ask_transcription_complete` → `gemini_request_sent` → `gemini_first_token` → `ai_response_rendered_client`. Use `get_session_trace()` (already used by `analyze_vision_frames`/`generate_tactical_advice`, `08_backend_utils_logging.md` / `gemini_client.py:149`) to record these — it's already wired for artifact writes.
2. `_build_report_lines()` (`session_trace.py:182-211`) — add a "Latency Summary" section computing deltas between these events, surfaced in `report.md`.
3. Frontend: a small dev-mode latency badge (gated behind a debug flag) showing last-ask round-trip time — useful for manual verification during Phase 1/2 cue-card work.
4. New settings flag: `LATENCY_TRACE_ENABLED` (default True, low overhead — it's just timestamped trace events).

**Acceptance criteria**: `report.md` for a session contains a latency breakdown table; a manual ask in a dev session shows total round-trip and per-stage timings.

**Skill**: feeds the `negotiation-session-e2e` skill proposed in `05_skills_and_verification.md` — that skill should assert on these numbers once this instrumentation lands.

---

## 0.5 [FIX] Vision-dominance bug (AI answers from screen instead of spoken facts)

**Severity**: P1 — correctness bug, undermines trust in live advice.

**Where**: vision pipeline — `handle_vision_frame` (`negotiation_engine.py:685`, gated by `VISION_PRO_ENABLED`/`VISION_PRO_MAX_FRAMES`/etc.), `_run_vision_analysis` (`negotiation_engine.py:797`), `_drain_live_vision_frames` (`negotiation_engine.py:856`), `_flush_latest_intel`/`_send_coalesced_intel` (`negotiation_engine.py:2751,2783` — merge vision/listener intel into the live session context). `analyze_vision_frames` (`gemini_client.py:322`) is the vision-model call.

**What to do**:
1. Re-check `HANDOFF.md` for the most recent prior investigation/attempts at this bug (per `00_INDEX.md:62` this area "has a documented history") before re-diagnosing from scratch.
2. Likely fix shape: when both spoken-transcript context and vision-derived context are available for the same time window, the prompt assembly that feeds the live session (`_send_coalesced_intel`) should explicitly rank/label sources — e.g., prefix vision intel as "(visual observation, may be stale/ambiguous)" vs. transcript as "(what was just said)" — and the system instruction (`ai_assets.py`, per `docs/code_map/04_backend_api_models_providers.md`) should explicitly instruct the model to prioritize spoken facts over visual inference when they conflict.
3. Add a regression trace event (`vision_vs_transcript_conflict`) when both fire within the same coalescing window, to make future debugging easier.

**Acceptance criteria**: a manual test where the screen shows a different number than what's spoken (e.g., a stale price on screen vs. a new verbal offer) results in the AI advice reflecting the verbal offer, with a trace event recorded.

**Skill**: `Plan` subagent recommended given the cross-file complexity (3 files, lazy circular imports per `01_backend_core.md:90`). `verify` + manual smoke test via `run`.

---

## 0.6 [FIX] Ask-transcription truncation

**Severity**: P1 — garbled/cut-off "YOU" bubble text in the Ask AI flow.

**Where**: `handle_audio_payload` (`companion_runtime.py:303`) has an existing comment flagging "multi-writer race at hold-release (garbled/truncated question text)" (`companion_runtime.py:369`, noted at `01_backend_core.md:201`). Related: `_capture_private_ask_audio` (`companion_runtime.py:502`), `_transcribe_snapshot_text` (`companion_runtime.py:615`, lock-protected per comment at `:562`), `_push_to_deepgram_stream` (`companion_runtime.py:821`). Governing flags: `ASK_AI_NATIVE_AUDIO`, `ASK_AI_NATIVE_ONLY_TRANSCRIPTION`, `ASK_AI_LOCAL_MIC_SUPPRESS_GRACE_SECONDS`, `ASK_AI_ACTIVITY_END_DELAY_SECONDS` (`config.py:214-261`, `04_backend_api_models_providers.md:187-195`).

**What to do**:
1. Re-read `HANDOFF.md` for prior fixes/reversals on `ASK_AI_*` flags before changing defaults — this area has "a documented history of race conditions" (`00_INDEX.md:62`).
2. The race is at hold-release: audio buffer flush vs. transcription-snapshot read happen concurrently from different writers. Likely fix: ensure `_capture_private_ask_audio`'s buffer-close and `_transcribe_snapshot_text`'s snapshot-read are serialized through the same lock (the lock mentioned at `companion_runtime.py:562` may need to also guard the hold-release buffer-close path, not just vision-frame/text-injection races).
3. Consider whether `ASK_AI_ACTIVITY_END_DELAY_SECONDS` (currently 0.4s, `config.py`) needs tuning alongside the lock fix — but prefer fixing the race over masking it with a longer delay (delay-tuning works against the <1.5s latency budget in 0.4).

**Acceptance criteria**: 10 consecutive manual hold-to-ask tests produce complete, untruncated "YOU" transcript bubbles; trace shows no overlapping buffer-close/snapshot-read events.

**Skill**: `Plan` subagent for the concurrency analysis; `verify` + manual repeated smoke test.
