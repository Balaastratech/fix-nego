# Implementation Plan — Overview & Index

**Date**: 2026-06-11
**Author**: `[Agent: Claude Code]`
**Inputs**: `docs/plans/2026-06-11-market-research-monetization.md` (market evidence + P0-P3 fix list), `docs/code_map/00_INDEX.md` (where things live), strategic decision: **web = live in-person/face-to-face negotiations**, **desktop = virtual meetings** (matches existing `SourceMode.IN_PERSON_WEB` vs `SourceMode.VIRTUAL_COMPANION_DESKTOP` in `backend/app/models/companion.py`).

## How to use this plan

This plan is split into files so each can be read independently and stays under output-size limits:

| File | Covers |
|---|---|
| `00_overview.md` (this file) | Phasing, dependency graph, cross-cutting rules, skill strategy |
| `01_phase0_foundations.md` | Blocking fixes + shared infrastructure (build-breaking bug, billing/metering, consent, latency instrumentation, vision-dominance bug, ask-transcription truncation) |
| `02_phase1_web_inperson.md` | Web app — in-person/face-to-face focus (mobile PWA, discreet delivery, room-audio robustness, prep wizard, in-person consent) |
| `03_phase2_desktop_virtual.md` | Desktop app — virtual-meeting focus (macOS capture, auto meeting detection, cue-card overlay, debrief surface) |
| `04_phase3_shared_artifacts_growth.md` | Negotiation-specific artifacts (concession tracker, BATNA memory, offer timeline, terms panel) + debrief/share + CRM sync |
| `05_skills_and_verification.md` | Skill usage per phase, new skill proposal, verification/testing strategy, acceptance criteria checklist |

Every work item below is tagged `[FIX]` (already-broken/regressed behavior, from the P0-P3 list) or `[NEW]` (net-new capability from the gap analysis), with a `path:line` pointer into `docs/code_map/` where the touchpoint lives.

## Phasing & dependency graph

```
Phase 0 (Foundations — BLOCKING, do first)
  0.1 [FIX] frontend/lib/types.ts missing — build-breaking, blocks ALL frontend work
  0.2 [NEW] Billing/metering infrastructure — blocks ALL monetization-facing work (pricing tiers,
       Event Pass, Team CRM tier, usage caps)
  0.3 [FIX] Consent flow (pre-session, geo-aware) — legal blocker for shipping to new users
  0.4 [NEW] Latency instrumentation (per-stage timing vs <1.5s budget) — needed to validate
       Phase 1/2 UX work and as a regression guard
  0.5 [FIX] Vision-dominance bug (AI answers from screen instead of spoken facts)
  0.6 [FIX] Ask-transcription truncation

        |
        v
Phase 1 (Web, in-person focus)        Phase 2 (Desktop, virtual focus)     <- can run in parallel
  1.1 [NEW] Mobile PWA                  2.1 [NEW] macOS capture support       once Phase 0 lands
  1.2 [NEW] Discreet delivery/cue-card  2.2 [NEW] Auto meeting detection
  1.3 [NEW] Room-audio robustness       2.3 [NEW] Cue-card overlay format
  1.4 [NEW] Pre-meeting prep wizard     2.4 [NEW] Post-call debrief surface
  1.5 [FIX/NEW] In-person consent UI

        |                                       |
        v                                       v
Phase 3 (Shared negotiation artifacts + growth loop)
  3.1 [NEW] Concession tracker
  3.2 [NEW] BATNA / walkaway memory
  3.3 [NEW] Offer-history timeline
  3.4 [NEW] "Terms agreed so far" panel
  3.5 [NEW] Debrief/share page (web) + shareable recap link
  3.6 [NEW] HubSpot CRM sync (Team tier — depends on 0.2 billing for tier-gating)

        |
        v
Phase 4 (Cleanup & polish — runs continuously, finalized last)
  4.1 [FIX] Dead code removal (per code_map "likely-dead modules" list)
  4.2 [NEW] Onboarding polish (voice enrollment flow)
  4.3 [FIX] Stale flags cleanup
```

**Critical path reasoning**:
- Nothing that touches money (Event Pass, Team tier CRM sync, usage caps) can ship before 0.2 (billing/metering). Build it once, early, even though its UI surface is small — it gates pricing decisions for everything downstream.
- 0.1 (`types.ts`) is a 30-minute fix but is currently **build-breaking** for the frontend — must land before any frontend Phase 1/3 work can even compile.
- 0.3 (consent) is a legal gate for onboarding new pilot users in all-party-consent states — should land before any broader user-facing rollout, not after.
- Phase 1 and Phase 2 are independent surfaces (web vs desktop) and can be worked in parallel by different sessions/agents once Phase 0 is merged.
- Phase 3 (negotiation artifacts) is the durable product differentiator but depends on UI patterns established in Phase 1/2 (cue-card format, debrief surface) so it's sequenced after.
- Phase 4 is not "do last" in the sense of waiting — dead-code removal items can be picked off opportunistically whenever a touched file overlaps, but the plan defers a dedicated cleanup pass to the end so it doesn't compete with feature work for review bandwidth.

## Cross-cutting rules for execution

1. **Always re-check `docs/code_map/00_INDEX.md` and the relevant numbered file before touching a service** — code map may have drifted; if so, fix the code map too (per its own maintenance note).
2. **Every phase ends with a HANDOFF.md append** (timestamped, `[Agent: Claude Code]`, per AGENTS.md/CLAUDE.md) — never rewrite prior entries.
3. **Every item that changes runtime behavior needs a settings flag** if it could regress existing sessions (consistent with existing pattern of `*_ENABLED` flags in `config.py` — see `docs/code_map/04_backend_api_models_providers.md`). Default new flags to **off** until verified, then flip default once stable, mirroring how `MULTILANG_ENABLED`/`SPEECHBRAIN_ENABLED` etc. are documented.
4. **No single response/turn should regenerate large files** — use Edit for incremental changes, Write only for new files, and split large generated docs across multiple Write calls (lesson from the 32k-output-token error).
5. **Billing/entitlements (0.2) and consent (0.3) are the two items most likely to need explicit user sign-off on vendor choice** (e.g., Stripe vs. alternative; consent copy/jurisdiction list) — flag these for `AskUserQuestion` before implementation, don't assume.
6. **Verification before "done"**: each phase's acceptance criteria (in `05_skills_and_verification.md`) must be checked — type-check/build, relevant test suite, and where applicable a manual smoke test via `run` skill — before marking an item complete in HANDOFF.md.

## Skill strategy (summary — detail in `05_skills_and_verification.md`)

- `Plan` subagent: used per-item for any item marked "complex" below (mobile PWA, billing infra, macOS capture) to produce a sub-plan before coding.
- `verify`: run after every implementation batch (build/typecheck/tests).
- `code-review` / `security-review`: mandatory for 0.2 (billing/Stripe webhooks), 0.3 (consent/legal), 1.5 (in-person consent), and any auth-adjacent change.
- `simplify`: run after each phase before final commit.
- `run`: used to boot backend/frontend/desktop for manual smoke tests.
- **New skill proposed**: `negotiation-session-e2e` — a project-specific skill that boots the backend WS server, replays a fixture audio session, and asserts (a) `session_trace/report.md` is generated, (b) ask-latency stays under the configured budget, (c) no unhandled exceptions in `backend.jsonl`. See `05_skills_and_verification.md` for spec.
