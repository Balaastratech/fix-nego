# Full Engineering Audit

Date: 2026-05-21
Repo: `D:\Balaastra\hackothon\project code`

## 1. Audit method

This was audited as a production-readiness review, not just a style review.

Why this audit shape:

- Google SRE's Production Readiness Review treats reliability, instrumentation, emergency response, capacity, change management, and latency as one system, not separate checklists.
- OWASP's code review guidance is explicit that manual review still matters even when scanners exist.
- The Twelve-Factor App remains the right baseline for config separation, deploy/runtime parity, and log handling.

Applied audit lenses:

1. Architecture and runtime shape
2. Reliability and failure handling
3. Latency and responsiveness
4. Security and session safety
5. Observability and operability
6. Testability and change safety
7. Repo hygiene and deployment readiness

## 2. System inventory

Current codebase size inspected:

- `backend/app`: 40 files
- `backend/tests`: 26 files
- `frontend/app + components + hooks + lib`: 32 files
- `desktop/src`: 11 files

The project is now a 3-surface system:

1. FastAPI backend with WebSocket-first runtime
2. Next.js frontend web app
3. Electron desktop companion

That architecture is legitimate for the product you are building, but it raises the bar for runtime discipline. Right now the architecture is ahead of the operational maturity.

## 3. What is verified working

This section is intentionally strict. I am only listing items that I could verify locally in this checkout.

### 3.1 Backend modules compile

These key backend files compile successfully with `py_compile`:

- `backend/app/main.py`
- `backend/app/api/websocket.py`
- `backend/app/services/stt_service.py`
- `backend/app/services/session_store.py`
- `backend/app/services/negotiation_engine.py`
- `backend/app/services/gemini_client.py`
- `backend/app/ai_assets.py`

This does not prove correctness, but it does prove the current edited backend is at least syntactically intact.

### 3.2 Targeted backend tests pass

Verified passing:

- `backend/tests/test_live_ask_turn_packaging.py`
- `backend/tests/test_copilot_eval_harness.py`
- `backend/tests/test_companion_runtime.py`

Result: `28 passed`.

Interpretation:

- Live ask-turn packaging has regression coverage
- Companion runtime has at least some direct behavior coverage
- Copilot evaluation harness is runnable

### 3.3 Frontend production build passes

`npm run build` in `frontend/` passes on Next.js 15.5.12.

Interpretation:

- The app is buildable
- The current TypeScript/Next runtime graph is internally consistent enough for a production bundle

### 3.4 Desktop JavaScript parses

Both of these pass `node --check`:

- `desktop/src/main.js`
- `desktop/src/renderer/overlay.js`

Interpretation:

- The Electron companion code is not syntactically broken

### 3.5 Session persistence layer is one of the strongest parts of the repo

The SQLite session store uses WAL mode and persists sessions through explicit tables and bundle loading.

Evidence:

- `backend/app/services/session_store.py:33`
- `backend/app/services/session_store.py:36`
- `backend/app/services/session_store.py:115`
- `backend/app/services/session_store.py:266`

Interpretation:

- Persisted transcript/session state is a real subsystem, not a stub
- Resume/history functionality has a credible persistence base

## 4. What is clearly not production-ready

These are not cosmetic issues. These are structural gaps.

### 4.1 Full backend test suite is not runnable as a stable baseline

`backend\venv\Scripts\python.exe -m pytest backend\tests -q` fails during collection with:

- `ModuleNotFoundError: No module named 'k2'`
- `ImportError: Please install k2 to use k2`
- then Hypothesis/pytest internal collection failure through SpeechBrain lazy import

This is one of the most important audit findings.

Why it matters:

- You do not currently have a trustworthy full-backend regression gate
- Dependency fragility is leaking into test collection itself
- Reliability work is being done without a clean test envelope

Related code smell:

- import-time patching in `backend/app/main.py:9-30`
- heavyweight and brittle audio/ML dependency stack in `backend/requirements.txt`

### 4.2 Frontend test suite is not green

`npm test` fails.

Observed failure:

- `frontend/components/enrollment/EnrollmentModal.test.tsx` has 11 failing tests
- immediate cause is `ReferenceError: React is not defined`

The file imports Vitest and Testing Library, but no React import exists at the top of the test file:

- `frontend/components/enrollment/EnrollmentModal.test.tsx:1-3`

Why it matters:

- Build green is not the same as behavior green
- Frontend confidence is currently partial, not comprehensive

### 4.3 Documentation is stale relative to the actual system

The README still documents a previous product shape:

- deployed Cloud Run URLs are hardcoded in `README.md:13-17`
- manual response modes are still documented in `README.md:199`
- browser/manual speaker flow is still described as the main path in later sections

This is now inaccurate because the repo has moved into:

- desktop companion mode
- newer Live ask/hold flow
- prompt/runtime behavior that has already been reworked

Why it matters:

- onboarding is harder
- debugging starts from bad assumptions
- future contributors will use the wrong runtime model

### 4.4 WebSocket session restoration is unauthenticated

The WebSocket accepts a `session_id` query parameter, tries to restore an existing or persisted session, and then accepts the socket:

- `backend/app/api/websocket.py:49-73`

What is missing:

- no auth
- no ownership check
- no signed resume token

Why it matters:

- session transcript leakage is possible if session IDs are exposed or guessed
- this is a real privacy/security issue for negotiation data

### 4.5 Desktop companion is still not a complete device-routing product

Two concrete problems remain in the desktop shell:

1. Audio device enumeration is stubbed:
   - `desktop/src/main.js:259`
   - `companion:listAudioDevices` returns `{ inputs: [], outputs: [] }`

2. Overlay still hardcodes backend WebSocket URL:
   - `desktop/src/renderer/overlay.js:6`
   - `ws://localhost:8000/ws`

Why it matters:

- Desktop mode is still partially demo-wired
- Device selection and route management are not fully productized
- This increases the chance of echo, sink mismatch, and environment-specific failures

### 4.6 Market research is placeholder code

The market research service is not implemented in any real sense.

Evidence:

- `backend/app/services/market_research.py:40`
- `backend/app/services/market_research.py:44`
- `backend/app/services/market_research.py:79`
- `backend/app/services/market_research.py:83`

Current behavior:

- marketplace search: TODO, returns empty list
- forum search: TODO, returns empty list

Why it matters:

- any product promise around pricing guidance or comparable listing advice is currently overstated
- the system can appear smart while returning no real market evidence

### 4.7 Repo hygiene is weak

The working tree currently contains:

- runtime DB files
- WAL/SHM files
- JSONL logs
- generated build info
- many modified app files across backend/frontend/desktop

Examples from `git status --short`:

- `backend/data/negotiation_sessions.db`
- `backend/data/negotiation_sessions.db-shm`
- `backend/data/negotiation_sessions.db-wal`
- `backend/data/logs/backend.jsonl`
- `frontend/tsconfig.tsbuildinfo`

Why it matters:

- signal-to-noise is poor
- reviews become harder
- accidental commits of runtime artifacts become more likely

## 5. Latency and Live-AI audit findings

This is the highest-value technical section for your product.

### 5.1 The codebase is trying to be low-latency, but the architecture is still mixed

There are two latency stories in the repo:

1. Direct streaming behavior for hold-to-ask / Live replies
2. Batched transcription and context extraction for ambient conversation

That is fine in principle, but the seams are still rough.

### 5.2 ListenerAgent still contains batch/debounce gates that cap responsiveness

Evidence in `backend/app/services/listener_agent.py`:

- `POLL_INTERVAL = 1.5` at line 61
- `MIN_NEW_AUDIO = 1.5` at line 63
- `TEXT_EXTRACTION_DEBOUNCE_SECONDS = 1.5` at line 65
- `_batch_interval = 3.0` at line 116
- explicit note that short segments are buffered because they hallucinate at line 288

Interpretation:

- the code explicitly trades latency for stability
- some of that is correct
- but it means "instant" response is not yet architecturally true across the whole system

Net effect:

- Ask-AI can be fast if Gemini Live hears the user directly
- background transcript/context will still feel delayed

### 5.3 STT provider architecture improved, but default drift remains

Config supports both Google STT and Deepgram:

- `backend/app/config.py:56`
- `backend/app/config.py:70`
- validation logic later in the same file

But the default is still:

- `TRANSCRIPTION_PROVIDER = "google_stt"` at `backend/app/config.py:56`

Interpretation:

- the provider abstraction is now real
- operational defaults may still not reflect the current latency-first direction

### 5.4 There is still too much runtime complexity in the live path

Current live stack spans:

- WebSocket session lifecycle
- ask-turn packaging
- Gemini Live transport
- desktop audio routing
- dual-source desktop capture
- partial transcript emission
- STT provider fallback
- session persistence

That is too much moving state for the present test coverage.

Conclusion:

- the main long-term latency fix is not only "pick the fastest model"
- it is reducing state-machine complexity and making the Live path more deterministic

## 6. Security and privacy findings

### 6.1 Critical: unauthenticated session restore

Already covered above. This is the top security issue in the repo.

### 6.2 Secrets/config management is only partially disciplined

Positive:

- `.env` files are ignored by git

Risk:

- a very large number of provider keys and runtime toggles are mixed into one config surface
- operational behavior depends on environment discipline more than explicit deployment policy

Relevant config surface:

- `backend/app/config.py`
- `backend/.env.example`

### 6.3 Negotiation data has real privacy sensitivity, but security posture is still local-dev grade

This repo stores:

- transcripts
- advisor outputs
- research events
- vision events
- session metadata

The persistence is strong enough to be useful, but access control is not yet strong enough for a privacy-sensitive product.

## 7. Observability and operability findings

### 7.1 Logging exists, but the system is not yet observability-mature

Positive:

- backend emits structured runtime logs
- session summaries are persisted
- there is explicit capability probing at startup

Evidence:

- `backend/app/main.py:125-243`

Gaps:

- no clearly standardized tracing layer
- no clear metrics contract across backend/frontend/desktop
- no explicit SLOs or error-budget style thresholds
- no stable operational dashboard surface in repo

Interpretation:

- this is debuggable by log spelunking
- it is not yet operable by standard service health signals

### 7.2 Startup is fragile because production capability probing and dependency patching are entangled

`backend/app/main.py` does all of these at startup:

- SpeechBrain patching
- Hugging Face compatibility patching
- capability probes
- background readiness tasks

Why it matters:

- startup time and startup failure modes are harder to reason about
- environment-specific breakage is more likely

## 8. Highest-priority gaps to fix next

This is the order I would use if the goal is to make the project materially better, not just cleaner.

### Priority 0: establish a trustworthy regression baseline

1. Make the full backend test suite collect and run without `k2` import explosions
2. Fix the failing frontend enrollment tests
3. Add one desktop smoke test layer, even if it is narrow

Reason:

Without this, every Live/STT/runtime fix remains high-risk.

### Priority 1: harden session and privacy boundaries

1. Replace raw session restore by `session_id` with signed resume tokens
2. Add session ownership checks
3. Define retention policy for transcript/advisor/vision records

Reason:

This is a negotiation product. Privacy is not optional.

### Priority 2: simplify the Live ask path

1. Keep one answer policy
2. Keep prompt protocol plain-language only
3. Reduce control-message contamination between system/context/user turns
4. Separate "ambient context injection" from "direct user question" more aggressively

Reason:

You already saw the failure mode: Live transport can work while the answer logic is still corrupted.

### Priority 3: finish the desktop companion as a real product surface

1. Implement actual audio device enumeration in Electron
2. Remove hardcoded local backend URL
3. Formalize meeting-route vs listening-route handling
4. Add explicit diagnostics UI for route health and loopback safety

Reason:

Right now the desktop shell is functionally important but still partly scaffolded.

### Priority 4: decide the real STT strategy

You need to choose one of these as the primary design:

1. Live-direct voice for ask-AI, batch STT for background context
2. Full streaming STT for both ambient and ask flows

Right now the codebase is halfway between them.

Recommendation:

- keep Gemini Live direct-audio for ask-AI
- move ambient conversation to a clean streaming STT pipeline
- minimize fallback branches

### Priority 5: remove placeholders and stale product promises

1. Either implement market research or downgrade the feature claim
2. Rewrite README to match the actual current architecture
3. Clean runtime artifacts from the repo workflow

## 9. What I would not claim yet

I would not honestly call any of these "100% working perfectly" yet:

- full backend reliability
- frontend behavior coverage
- desktop device-routing correctness
- market research functionality
- secure multi-session resume
- end-to-end low-latency production behavior

That does not mean the project is bad. It means the project is real, ambitious, and still in a heavy integration/debugging phase.

## 10. Bottom line

### Strongest parts

- overall product architecture direction
- session persistence model
- targeted backend regression tests
- frontend buildability
- active movement toward low-latency audio paths

### Weakest parts

- full-suite test stability
- session security
- desktop productization
- stale docs
- placeholder market-research layer
- runtime complexity in the Live path

### Overall audit verdict

This repo is beyond prototype in architecture, but not yet production-ready in discipline.

The right next step is not another broad feature push.
The right next step is hardening:

1. regression baseline
2. session security
3. deterministic Live path
4. desktop routing completeness
5. documentation and hygiene cleanup

## 11. Source frame used for the audit

Web references used to shape the audit method:

- Google SRE PRR: https://sre.google/sre-book/evolving-sre-engagement-model/
- OWASP Code Review Guide: https://owasp.org/www-project-code-review-guide/
- Twelve-Factor App: https://www.12factor.net/
- OpenTelemetry status/reference surface: https://opentelemetry.io/status/
