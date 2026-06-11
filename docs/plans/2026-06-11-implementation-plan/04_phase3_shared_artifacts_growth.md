# Phase 3 — Shared Negotiation Artifacts + Growth Loop

These items are the durable product differentiator (vs. generic meeting-notetakers like Trellus/Winn.ai per the market research) and the growth loop ("desktop captures, web shares" — Granola/Loom precedent). They're shared across web (Phase 1) and desktop (Phase 2) — built once, surfaced on both.

**Depends on**: Phase 1.4 (prep wizard supplies BATNA/walkaway/target inputs), Phase 2.4 (debrief data shape established).

---

## 3.1 [NEW] Concession tracker

**What exists today**: `StrategyUpdate` (`messages.py:108`) already has `target_price/current_offer/recommended_response/key_points/approach_type/confidence/walkaway_threshold/web_search_used/search_sources` — a single "current state" snapshot, sent presumably on each strategy recompute. There is no *history* of how `current_offer` changed over time.

**What to build**:
1. **Backend**: append each `StrategyUpdate`'s `current_offer`/`target_price`/timestamp to a new `session.concession_history: list[dict]` field on `NegotiationSession` (`models/negotiation.py`, alongside `strategy_history` per `04_backend_api_models_providers.md:489`) — likely `strategy_history` already accumulates these and this item may be mostly a *surfacing* task rather than new data collection. **Verify first**: read `negotiation.py:282-310` and the code that appends to `strategy_history` before assuming new collection logic is needed.
2. **New message type** (or extend `STATE_UPDATE`): `CONCESSION_HISTORY_UPDATE` with the ordered list of `{offer, from: 'user'|'counterparty', timestamp}`.
3. **Frontend (both web + desktop `full.js`)**: a small "concession ladder" visualization — each party's offers over time, converging or diverging, with the gap to `target_price`/`walkaway_threshold` highlighted.

**Acceptance criteria**: during a live session with multiple back-and-forth offers, the tracker UI updates after each `StrategyUpdate` and shows the narrowing/widening gap.

**Skill**: start with a read-only audit (`Explore` or direct grep) of `strategy_history` population before deciding if backend changes are needed — this could be a frontend-only item if the data already exists.

---

## 3.2 [NEW] BATNA / walkaway memory

**What exists today**: `walkaway_threshold` is already a field on `StrategyUpdate` (`messages.py:108`) and `max_price`/`target_price` exist in the `useNegotiationState` shape (`useNegotiationState.ts:7-23`, `05_frontend.md:292`). Phase 1.4's prep wizard is the natural input point for the user's *own* BATNA/walkaway (as opposed to the AI's *inferred* `walkaway_threshold` for the counterparty).

**What to build**:
1. Distinguish (in both data model and UI) **user's own BATNA/walkaway** (entered in the prep wizard, 1.4 — never shown to counterparty, persisted on `NegotiationSession`) from the **AI-inferred counterparty walkaway** (`walkaway_threshold` in `StrategyUpdate`, dynamically estimated). These are conceptually different and conflating them in the UI would be confusing.
2. **Frontend**: a persistent (not auto-dismissing, unlike the cue cards from 1.2) small panel showing: "Your walkaway: $X | Your target: $Y | Current gap: $Z" — always visible during `ACTIVE` state, since this is the anchor the user should never lose sight of.
3. Ensure this data survives session restore (`SESSION_RESTORED`, `websocket.py:133-160`, `_restore_session_from_bundle`, `websocket.py:20`) — add the new fields to the persisted bundle.

**Acceptance criteria**: BATNA/target entered in the prep wizard appears in this panel for the duration of the session and survives a reconnect/restore.

**Skill**: `verify`. Coordinate field naming with 1.4 (same item, don't duplicate field definitions).

---

## 3.3 [NEW] Offer-history timeline

**Relationship to 3.1**: 3.1 (concession tracker) is the *live, in-session* visualization; 3.3 is the **persistent, post-session artifact** — part of the debrief (2.4/3.5). Likely the same underlying data (`concession_history`/`strategy_history`), different rendering context (live ladder vs. timeline in a report).

**What to build**:
1. Extend `_build_report_lines()` (`session_trace.py:182-211`) with an "Offer History" section — chronological list of offers/counters with timestamps, derived from the same history used in 3.1.
2. Web debrief page (3.5) and desktop debrief view (2.4) both render this timeline — shared component.

**Acceptance criteria**: `report.md` for a multi-offer session includes a chronological offer table; the debrief UI renders the same data.

**Skill**: `verify`. Builds directly on 3.1's data — sequence after it.

---

## 3.4 ["Terms agreed so far" panel]

**What exists today**: `OutcomeSummary` (`messages.py:121`) captures the *final* state (`deal_reached/initial_price/final_price/savings/savings_percentage/market_value/vs_market/negotiation_duration_seconds/key_moves/effectiveness_score/transcript_summary`) — but only at session end. There's no running "what's been agreed so far" during the conversation (e.g., price agreed but delivery terms still open).

**What to build**:
1. This requires the AI to track **multi-dimensional terms** (price, delivery, warranty, payment terms, etc.), not just price — likely needs a prompt addition (`ai_assets.py` — coordinate with `build_pre_query_brief`/`build_listener_intel_block`, `:812,895`) asking the model to emit a structured `terms_status: {term: 'price'|'delivery'|..., status: 'agreed'|'open'|'contested', value?: string}[]` alongside its existing analysis.
2. **New message type**: `TERMS_STATUS_UPDATE` with the structured list.
3. **Frontend**: a checklist-style panel — agreed terms checked off, open terms highlighted — visible on both web (full dashboard view, not the mobile cue-card view — too much detail for glanceable) and desktop `full.js`.

**Acceptance criteria**: in a multi-term negotiation (e.g., price + delivery date), the panel correctly shows price as "agreed" once both parties confirm it verbally, while delivery remains "open."

**Skill**: `Plan` subagent (prompt-engineering risk similar to 1.2 — new structured output alongside existing advice generation; validate it doesn't degrade `ADVICE_GENERATION_*` quality, `config.py` settings per `04_backend_api_models_providers.md:311`). Settings flag: `TERMS_TRACKING_ENABLED` (default False until validated).

---

## 3.5 [NEW] Debrief/share page (web) + shareable recap link

**Builds on**: 2.4 (desktop debrief — same data shape), 3.3 (offer history), `OutcomeSummary` (`messages.py:121`, already has `deal_reached/savings/savings_percentage/effectiveness_score/transcript_summary` — most of what a recap needs already exists).

**What to build**:
1. **Backend**: a shareable-link endpoint (new route in `api/`) that serves a read-only debrief view for a `session_id` — gate by a generated share token (not the raw session_id) for privacy; respects `consent_mode`/jurisdiction (don't make all-party-consent-flagged session content shareable without re-confirmation).
2. **Frontend**: `/debrief/[token]` page — renders `OutcomeSummary` fields, offer-history timeline (3.3), terms panel (3.4) snapshot, latency-budget compliance (0.4, optional/internal-only).
3. **Growth loop**: a "Share recap" button at session end (web `OUTCOME_SUMMARY` handler) generates the link; this is the "desktop captures, web shares" pattern — even desktop sessions' debriefs should be shareable via this web page (desktop `full.js` debrief view, 2.4, can deep-link here rather than building its own share UI).

**Acceptance criteria**: ending a session produces a shareable link; opening it in an incognito browser shows the recap without requiring login (read-only, token-gated).

**Skill**: `security-review` for the share-token scheme (must not be guessable/enumerable). `verify`.

---

## 3.6 [NEW] HubSpot CRM sync (Team tier)

**Severity**: P2, but verified as "the paid-conversion feature" — HubSpot marketplace listing also doubles as a distribution channel (`docs/plans/2026-06-11-market-research-monetization.md:86`).

**Depends on**: 0.2 (billing — this is Team-tier-gated, so entitlement checks must exist first) and 3.5 (the debrief data shape is what gets synced to CRM as a "meeting note").

**What to build**:
1. HubSpot OAuth app registration + connection flow (account settings page — new frontend surface, likely part of the billing/account area from 0.2).
2. On session end (`OUTCOME_SUMMARY`), if the account has HubSpot connected and is on Team tier (entitlement check via 0.2's resolver), push a note/engagement to the associated HubSpot contact/deal with the debrief summary (3.5's data) + a link to the shareable recap.
3. Settings/entitlement flag: gated entirely behind `BILLING_ENABLED` + Team-tier check from 0.2 — do not build this before 0.2's entitlement resolver exists, since "Team tier" has no enforceable meaning without it.

**Acceptance criteria**: a Team-tier test account with HubSpot connected gets a new engagement on the relevant contact after a session ends, containing the debrief summary and recap link.

**Skill**: `Plan` subagent (OAuth + external API integration). `security-review` (OAuth token storage). This item should be sequenced **last** in Phase 3 — it's the one most clearly blocked on 0.2 actually shipping.
