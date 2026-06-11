# Phase 1 — Web App: In-Person / Face-to-Face Focus

Strategic frame (confirmed by user): the web app's primary use case is a **live, in-person, face-to-face negotiation** — phone/laptop on the table or in a pocket, capturing room audio via a single device mic, with the user glancing at (or feeling) discreet cues. This is distinct from the desktop app (Phase 2), which targets virtual/video meetings with system-audio capture.

Current entrypoint: `frontend/app/page.tsx` (top-level client page, wires `useNegotiation()` + `useEnrollment()`, renders `EnrollmentModal` + `NegotiationDashboard`, `docs/code_map/05_frontend.md:97-110`). `NegotiationDashboard.tsx` (`:335-376`) is the main UI; `useNegotiation.ts:178-647` owns the WS connection and `AudioManager`.

**Depends on**: Phase 0.1 (`types.ts` must exist for any of this to compile) and Phase 0.3 (consent model extended for jurisdiction).

---

## 1.1 [NEW] Mobile PWA (biggest gap — dashboard currently unusable "in-pocket")

**Where**: `frontend/app/layout.tsx` (19 lines, `docs/code_map/05_frontend.md:110`), `frontend/app/page.tsx`. No `manifest.json` or service worker currently exists in `frontend/` (confirmed absent).

**What to build**:
1. **Web app manifest** (`frontend/public/manifest.json` + `<link rel="manifest">` in `layout.tsx`): name, icons, `display: "standalone"`, theme colors — enables "Add to Home Screen" on iOS/Android.
2. **Wake Lock API**: acquire `navigator.wakeLock` when a session is `ACTIVE` (hook into the same lifecycle as `handleStartNegotiation`/`handleEndNegotiation` in `page.tsx:210-235`) so the screen doesn't sleep mid-negotiation when the phone is face-down or in a pocket — release on `endNegotiation`/`SESSION_PAUSED`.
3. **Background audio handling**: investigate `AudioContext` suspension on mobile Safari/Chrome when backgrounded — `AudioManager` (`docs/code_map/05_frontend.md:181-188`, `resumeAudioContexts()`) already has a resume path used for AI playback after interruption; extend/reuse this for app-backgrounded → foregrounded transitions (mic capture must keep streaming or gracefully pause+resume without dropping the WS connection).
4. **Responsive layout pass on `NegotiationDashboard.tsx`** (376 lines, `:36-376`) — current component tree (`docs/code_map/05_frontend.md:45-62`) was built dashboard-first; needs a single-column, large-touch-target mobile layout. This is also the natural place to introduce the cue-card format from 1.2 (don't build two separate layouts).
5. Service worker: minimal (cache shell for offline-tolerant reconnect UX), not full offline-first — the product is inherently real-time/online.

**Acceptance criteria**: Lighthouse PWA installability check passes; a session started on a mobile device, screen-locked then unlocked mid-session, does not drop the WS connection or stop transcription; "Add to Home Screen" produces a standalone app icon.

**Skill**: `Plan` subagent (multi-file, cross-cutting layout change). `run` skill to serve frontend on LAN IP for real mobile-device testing (not just desktop browser devtools emulation — wake lock/background audio behave differently on real devices).

---

## 1.2 [NEW] Discreet delivery / glanceable cue-card format

**Severity**: high — this is a verified UX differentiator (research: short directives beat paragraphs; "Cluely failed/Granola won" on transparent-not-stealth positioning, but delivery still needs to be glanceable, not a wall of text).

**Where**: AI advice currently renders via `AI_RESPONSE`/`AI_THINKING` messages (`negotiation_engine.py` sends these; frontend reducer actions `SET_AI_STATE`, etc., `docs/code_map/05_frontend.md:225`) into `NegotiationStateCard.tsx` (269 lines, `:365-`) and/or `TranscriptPanel.tsx`. Today this renders full spoken/streamed text.

**What to build**:
1. **Backend**: a structured "cue" format alongside the conversational `AI_RESPONSE` — e.g., extend `AI_RESPONSE` payload (or add a new `CUE_CARD` message type in `models/messages.py`, following the `ConsentAcknowledgedPayload`-style pattern at `messages.py:148`) with `{ headline: string (<=8 words), detail: string (1 sentence), tone: 'suggestion'|'warning'|'opportunity' }`. The system instruction in `ai_assets.py` (`docs/code_map/04_backend_api_models_providers.md`) needs a prompt addition asking the model to emit this structured summary alongside (or instead of, in copilot/glance mode) full prose.
2. **Frontend**: a new compact "cue card" component — large headline text, color-coded by `tone`, auto-dismiss/replace on next cue, designed to be readable in <1 second at arm's length or in-pocket-glance. This becomes the primary mobile view (ties into 1.1's responsive layout).
3. **Vibration alerts**: `navigator.vibrate()` on new high-priority cues (e.g., `tone: 'warning'`) — useful when the phone is face-down/pocketed. Gate behind a user setting (some users will find this annoying in a meeting).
4. **Settings flag**: `CUE_CARD_FORMAT_ENABLED` (default False until prompt-tuning is validated) — this changes model output shape and needs A/B-style validation before becoming default.

**Acceptance criteria**: in a live test session, a new piece of advice appears as a cue card within the latency budget from 0.4, headline is readable without scrolling on a phone screen, and (if enabled) a vibration fires for warning-tone cues.

**Skill**: `Plan` subagent for the prompt-format change (touches `ai_assets.py` system instructions — high blast radius if it regresses normal advice quality). `negotiation-session-e2e` (proposed in `05_skills_and_verification.md`) should be extended to assert cue-card payloads are well-formed when the flag is on.

---

## 1.3 [NEW] Room-audio robustness (single-mic, dual-speaker, in-person)

**Severity**: currently degrades silently — speaker-diarization confidence collapse in a noisy room produces no user-visible fallback.

**Where**: speaker recognition pipeline — `speaker_service.py` (`feed_audio`, `docs/code_map/03_backend_speaker_infra.md:30`), `speaker_mapping_service.py` (`_verify_user_candidate`, `:62`, gated by `SPEECHBRAIN_MIN_BIND_SECONDS`/`speechbrain_reference_embedding`), `_record_label` (`speaker_service.py:598`, increments `session_metrics["speaker_user_count"|"speaker_counterparty_count"|"speaker_unknown_count"]`). STT: `stt_service.py` (`transcribe`/`transcribe_audio`, `02_backend_listener.md:185-186`).

**What to build**:
1. **Confidence-collapse detection**: a new check (in `negotiation_engine.py` or `speaker_service.py`) that watches `session.speaker_confidence_history` (already populated by `_record_label`) — if the rolling `speaker_unknown_count` ratio exceeds a threshold over N seconds, emit a new `DEGRADED_MODE_UPDATE` reason (this message type already exists per `01_backend_core.md:73`) like `"speaker_confidence_low"`.
2. **Frontend fallback UI**: when `DEGRADED_MODE_UPDATE` fires with this reason, show a non-intrusive prompt: "Having trouble telling who's speaking — tap to confirm it's your turn" (manual speaker override already exists as `setManualSpeaker`/`SPEAKER_MODE_CHANGE`, `useNegotiation.ts:629-646` — wire the prompt to this existing control rather than building a new one).
3. **Far-field tuning**: investigate STT/VAD sensitivity settings (`AudioManagerConfig` — `silenceDebounceMs`, `vadOptions`, `docs/code_map/05_frontend.md:181`) for a "room mode" preset vs. the current (likely close-mic-tuned) defaults. This may be primarily a config/preset addition rather than new code — add a `captureMode: 'handheld'|'room'` toggle exposed in settings, mapped to different `vadOptions`/gain presets client-side.
4. **Noise suppression**: confirm whether `getUserMedia` constraints currently request `noiseSuppression`/`echoCancellation`/`autoGainControl` — if not, add and make tunable per `captureMode`.

**Acceptance criteria**: in a test with background noise + two speakers on one device mic, when diarization confidence drops, the UI surfaces a manual-confirm prompt within a few seconds rather than silently misattributing speech.

**Skill**: `Plan` subagent (spans frontend audio config + backend speaker pipeline). Manual smoke test via `run` with a real device — VAD/noise-suppression tuning can't be meaningfully validated in a unit test.

---

## 1.4 [NEW] Pre-meeting prep wizard

**Severity**: ties directly to the Event Pass ($49-149 one-time) monetization tier from the market research — this is the feature that makes a one-time-purchase "prep for this specific negotiation" product make sense.

**Where**: new feature — closest existing analog is the research/context injection already present in `NegotiationSession` (`context`, `research_json`, `RESEARCH_HISTORY_LIMIT` per `04_backend_api_models_providers.md:467`, `01_backend_core.md` vision/research settings). The "auto-research" capability referenced in the gap analysis likely maps to existing market-research/context-gathering code paths — note `services/market_research.py` is currently flagged **dead** (`00_INDEX.md:70`/`02_backend_listener.md:24`); this phase may be the reason to either revive a trimmed version of it or confirm it's superseded by something else before deleting in Phase 4.

**What to build**:
1. **Frontend wizard** (pre-`START_NEGOTIATION`, after consent): a short form — item/topic, target price, walkaway/BATNA, counterparty info (if known), negotiation type. This data populates the same fields the engine already understands (`NegotiationState` fields like `item, negotiation_type, seller_price, user_offer, target_price, max_price, ...` per `useNegotiationState.ts:7-23`, `05_frontend.md:292`) — note the gotcha that this is a **different** `NegotiationState` than `lib/types.ts`'s session-state type (`05_frontend.md:544`); the wizard writes into the `useNegotiationState` shape, sent via `STATE_UPDATE` (already an existing client→server message type, `01_backend_core.md:76`).
2. **Auto-research** (optional, Event-Pass-tier gated once 0.2 lands): server-side lookup (price comparables, counterparty background) triggered from wizard submission, populating `research_json` before the session starts — investigate whether `services/market_research.py` (dead) contains reusable logic for this before writing new code.
3. **BATNA/walkaway storage**: persist target/walkaway values on `NegotiationSession` so Phase 3's "BATNA memory" panel (3.2) can read them — coordinate field names with that item now to avoid a rename later.

**Acceptance criteria**: a user can fill the wizard, start a session, and see the AI's first response already contextualized with their stated target/walkaway (verifiable via `report.md` showing the injected context).

**Skill**: `Plan` subagent (decide market_research.py revival vs. fresh build). `code-review` if reviving dead code (re-audit for stale API usage).

---

## 1.5 [FIX/NEW] In-person verbal consent capture

**Depends on**: 0.3 (jurisdiction-aware consent data model).

**What to build**:
1. At session start (after the wizard in 1.4, before `START_NEGOTIATION`), if jurisdiction requires all-party consent, the app should **play or display a spoken/visible disclosure** ("This conversation is being recorded and analyzed by an AI assistant for [user]'s benefit") — for in-person settings the counterparty can't see a screen the way a virtual-meeting participant might see a shared notification.
2. Two delivery options to evaluate (raise via `AskUserQuestion` if not obvious from user testing): (a) the device speaks the disclosure aloud via TTS before the session opens its mic for negotiation content, or (b) the user is prompted to verbally state a provided disclosure script themselves (captured in the transcript as proof of disclosure).
3. Record the disclosure event in `session_trace` (new event type `consent_disclosure_given`) so it's auditable in `report.md`.

**Acceptance criteria**: in a flagged-jurisdiction session, the disclosure step is mandatory and recorded in the trace before `ACTIVE` state is reached.

**Skill**: `code-review`/`security-review` (legal/compliance-adjacent). Likely needs `AskUserQuestion` on disclosure UX before building.
