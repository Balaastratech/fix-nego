# Skills, Verification Strategy, and Phase 4 Cleanup

---

## Skill usage by phase (concrete mapping)

| Item | Recommended skill(s) | Why |
|---|---|---|
| 0.1 types.ts | `verify` | Mechanical, low risk — just confirm build passes |
| 0.2 Billing/metering | `Plan` → `security-review` + `code-review` → `verify` | Highest architectural complexity + payment data |
| 0.3 Consent (geo) | `AskUserQuestion` (jurisdiction list/copy) → `code-review`/`security-review` | Legal-sensitive, needs product decisions |
| 0.4 Latency instrumentation | direct implementation → `verify` | Additive logging, low risk |
| 0.5 Vision-dominance bug | `Plan` → `verify` + manual `run` smoke test | Cross-file, has prior failed attempts (check HANDOFF.md) |
| 0.6 Ask-transcription truncation | `Plan` → `verify` + repeated manual smoke test | Concurrency bug, needs careful analysis |
| 1.1 Mobile PWA | `Plan` → `run` (real device testing) | Multi-file layout change, needs physical-device verification |
| 1.2 Cue-card format | `Plan` (prompt change) → `negotiation-session-e2e` (new, see below) | Prompt changes need regression coverage |
| 1.3 Room-audio robustness | `Plan` → manual `run` with real device | VAD/audio tuning can't be unit-tested meaningfully |
| 1.4 Prep wizard | `Plan` (decide on `market_research.py` revival) → `code-review` if reviving dead code | Architectural decision point |
| 1.5 In-person consent | `AskUserQuestion` (disclosure UX) → `code-review`/`security-review` | Legal/compliance |
| 2.1 macOS capture | `Plan` (scope v1/v2) → `security-review` (native helper) | Substantial native integration |
| 2.2 Auto meeting detection | v1 direct + `verify`; v2 `Plan` (OAuth) | v1 is small; v2 is OAuth-scoped |
| 2.3 Cue-card overlay | `verify` + manual `run` (Electron) | Consumes 1.2's backend output |
| 2.4 Debrief surface | `verify` | Read-only productization |
| 3.1 Concession tracker | `Explore` (audit existing data first) → `verify` | May be frontend-only |
| 3.2 BATNA memory | `verify` | Coordinates with 1.4 |
| 3.3 Offer-history timeline | `verify` | Builds on 3.1 |
| 3.4 Terms panel | `Plan` (prompt-engineering risk) → `negotiation-session-e2e` | New structured model output |
| 3.5 Debrief/share page | `security-review` (share token) → `verify` | Public-facing endpoint |
| 3.6 HubSpot CRM sync | `Plan` → `security-review` (OAuth tokens) | External API + billing-gated |
| 4.1 Dead code removal | `Explore` (fresh grep per module) → `simplify` | Verify zero references before deleting |
| 4.2 Onboarding polish | `run` (manual UX pass) | UX judgment, not test-driven |
| 4.3 Stale flags cleanup | `Explore` → `simplify` | Same pattern as 4.1 |

General rule across all items: `code-review` and/or `security-review` for anything touching auth, payments, consent/legal copy, OAuth tokens, or external API integrations. `simplify` after any phase that accumulated incremental changes across multiple sessions.

---

## New skill proposal: `negotiation-session-e2e`

**Why**: several Phase 0/1/3 items (latency instrumentation, cue-card format, terms tracking) change the *shape* of model output or the *timing* of the pipeline. The repo already has an eval harness (`backend/evals/` — "Copilot Evaluation Harness," tests the Live AI advisor with scripted speaker-labeled turns over a real WebSocket, bypassing mic/STT/speaker recognition, gated by `EVAL_MODE_ENABLED=True`, per `docs/code_map/07_repo_catalog.md:174-176`, with `AUDIO_EVAL_FIXTURE_DIR` pointing at `evals/audio_fixtures/manifest.json`). This is the right foundation — the new skill should be a thin wrapper that makes this harness a fast, repeatable regression check.

**Proposed spec** (a Claude Code skill, e.g. `.claude/skills/negotiation-session-e2e/`):
1. Boots the backend (`uvicorn`) with `EVAL_MODE_ENABLED=True` and whatever feature flags the calling phase needs to test (e.g., `CUE_CARD_FORMAT_ENABLED=True`, `LATENCY_TRACE_ENABLED=True`).
2. Runs the existing `backend/evals/` harness against `audio_fixtures/manifest.json` (or `audio_fixtures_pyttsx3/` for synthetic-voice runs).
3. Asserts:
   - A `session_trace/{session_id}/report.md` is generated and contains expected sections (Conversation Summary, Event Counts, and — once 0.4 lands — Latency Summary).
   - Ask-latency (once 0.4 lands) stays under the configured budget (default 1.5s) for each scripted "ask" turn.
   - `backend.jsonl` contains no `ERROR`-level entries for the run.
   - (Phase-specific) if `CUE_CARD_FORMAT_ENABLED`, `AI_RESPONSE`/`CUE_CARD` payloads conform to the `{headline, detail, tone}` schema; if `TERMS_TRACKING_ENABLED`, `TERMS_STATUS_UPDATE` payloads conform to the `terms_status` schema.
4. Outputs a short pass/fail summary (not the full trace — respect the output-size constraint).

**Build this skill during Phase 0** (alongside 0.4) so it's available as a regression guard for every subsequent phase. It directly operationalizes the "actually working and high quality" requirement from the user's request — every phase's acceptance criteria can reference "passes `negotiation-session-e2e`."

---

## Phase 4 — Cleanup & polish (continuous, finalized last)

### 4.1 [FIX] Dead code removal

Per `docs/code_map/00_INDEX.md:70`, "verified zero inbound references at time of writing — confirm with a fresh grep before deleting":
- `backend/app/services/azure_speaker_service.py`
- `backend/app/services/eagle_service.py`
- `backend/app/services/voice_encoder.py`
- `backend/app/services/master_prompt.py`
- `backend/app/services/u.py` (empty)
- `backend/app/services/market_research.py` — **caution**: Phase 1.4 (prep wizard / auto-research) may want to revive logic from this file. Resolve 1.4's decision *before* deleting this in Phase 4 — don't let parallel work delete something another phase is about to reuse.
- `desktop/app.js` (legacy renderer)
- `frontend/components/negotiation/VideoCapture.tsx`
- `frontend/components/negotiation/StrategyPanel.tsx` — **caution**: Phase 0.1 (`types.ts` restoration) touches `Strategy` type which `StrategyPanel.tsx` imports. Resolve in 0.1, don't duplicate the decision here.
- Also flagged as orphaned in `05_frontend.md:62`: `ManualSpeakerSelector.tsx`, `StateDebugPanel.tsx` (not yet on the "likely-dead" list in 00_INDEX.md — verify and add to that list if confirmed dead).

**Process**: for each file, fresh `Grep` for imports/references across `backend/`, `frontend/`, `desktop/` immediately before deleting (code may have changed since the code map was written). Update `docs/code_map/0N_*.md` "likely-dead" lists after removal (maintenance note in `00_INDEX.md:74-76`).

### 4.2 [NEW] Onboarding polish (voice enrollment flow)

**Where**: `EnrollmentModal.tsx` (`components/enrollment/`), `useEnrollment()` hook (`:328`, returns `{startEnrollment, audioLevel}`), triggered via `ENROLLMENT_START` (`useNegotiation.ts:606`). Flow gating in `page.tsx`: `handleConsent` (`:154-163`) → enrollment modal vs. manual mode → `handleStartEnrollment`/`handleSkipEnrollment`/`handleEnrollmentComplete` (`:165-175`) → auto-close after 2s (`:178-184`).

**What to do**: this is described as "currently rough" and "first-session success drives retention" — concretely:
1. Manual UX pass through the enrollment flow (use `run` to serve frontend, walk through as a fresh user) — identify specific friction points (unclear instructions, no progress feedback beyond `enrollmentProgress`/`enrollmentCountdown`, abrupt modal close).
2. Likely additions: clearer copy on *why* enrollment helps (speaker ID accuracy), visual audio-level feedback during capture (`audioLevel` is already returned by the hook — confirm it's rendered), a retry path on `enrollmentError` that doesn't require restarting the whole session.
3. This item is UX-judgment-driven, not spec-driven — treat the above as a starting checklist, not a fixed scope.

**Acceptance criteria**: a first-time user can complete enrollment without confusion in a manual walkthrough; errors during enrollment offer a clear retry without losing session state.

### 4.3 [FIX] Stale flags cleanup

**What to do**: cross-reference `config.py`'s full settings table (`docs/code_map/04_backend_api_models_providers.md`) against actual usage — flags introduced for now-resolved experiments (check HANDOFF.md history for flags mentioned as "temporary" or "for testing X, can remove after"). This is naturally discovered as a byproduct of Phase 0.5/0.6 (which both involve re-reading `ASK_AI_*`/`VISION_*` flag history) — fold findings into this item rather than a separate sweep.

---

## Acceptance criteria checklist (roll-up)

Before marking this plan "executed," each phase should satisfy:

- [ ] **Phase 0**: frontend builds clean (0.1); `negotiation-session-e2e` skill exists and passes on `main`/dev branch (built alongside 0.4); a Stripe test-mode checkout flips plan + enforces quota (0.2); flagged-jurisdiction sessions require explicit all-party consent (0.3); vision-vs-transcript conflict resolves toward spoken facts with a trace event (0.5); 10/10 manual hold-to-ask tests produce untruncated transcripts (0.6).
- [ ] **Phase 1**: PWA installable + survives screen lock (1.1); cue cards render within latency budget on mobile (1.2); room-audio fallback UI appears on confidence collapse (1.3); prep wizard data flows into first AI response (1.4); in-person disclosure is mandatory + traced in flagged jurisdictions (1.5).
- [ ] **Phase 2**: macOS overlay binds to a meeting and captures both audio sources (2.1); auto-detect prompt appears within ~5s of opening a meeting app (2.2); cue-card overlay mode works with flag on, unchanged with flag off (2.3); debrief view renders after `OUTCOME_SUMMARY` with a working report link (2.4).
- [ ] **Phase 3**: concession ladder updates live (3.1); BATNA/walkaway panel persists across reconnect (3.2); `report.md` includes offer-history timeline (3.3); terms panel correctly distinguishes agreed/open terms (3.4); shareable debrief link works unauthenticated with a non-enumerable token (3.5); Team-tier HubSpot sync creates a CRM engagement post-session (3.6).
- [ ] **Phase 4**: all listed dead-code files re-verified-zero-references and removed, with `docs/code_map/` updated (4.1); enrollment flow walkthrough completed with documented improvements (4.2); stale flags removed from `config.py` with HANDOFF.md note on what was removed and why (4.3).

---

## Execution note

This plan is intentionally detailed enough to execute from directly — each item names files, line numbers, message types, and settings-flag conventions already established in the codebase. Per the user's request ("use any skill needed or create new"), the `negotiation-session-e2e` skill should be built early (Phase 0) since it underwrites the "actually working and high quality" bar for every later phase.

**Recommended starting point for the next session**: Phase 0, items 0.1 (quick win, unblocks frontend) and 0.4 + the `negotiation-session-e2e` skill (establishes the regression-testing foundation before any behavior-changing work begins). 0.2 (billing) should get its `Plan` sub-plan started in parallel since it's the longest-lead-time item and the most likely to need user decisions (`AskUserQuestion` on Stripe vs. alternatives, tier shape).
