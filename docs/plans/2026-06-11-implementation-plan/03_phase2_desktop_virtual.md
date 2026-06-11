# Phase 2 — Desktop App: Virtual Meeting Focus

Strategic frame (confirmed by user): the Electron desktop companion targets **virtual meetings** (Zoom/Teams/Google Meet) — system-audio capture, meeting-window binding, floating overlay orb. This is distinct from the web app (Phase 1), which targets in-person/face-to-face.

Current architecture: `desktop/main.js` (Electron main process — windows, privacy helper, capture-source resolution, `docs/code_map/06_desktop.md:64-99`), `overlay.js` (orb renderer — sole WS owner, all audio capture/playback, `:202-388`), `full.js` (dashboard renderer, no own WS, listens via `BroadcastChannel`, `:420-571`), `preload.js` (`companionBridge` IPC).

**Depends on**: Phase 0 (especially 0.1 for any shared frontend types reused in `full.js`, and 0.2 if desktop gates features by plan).

---

## 2.1 [NEW] macOS capture support

**Severity**: highest-leverage desktop item — halves the addressable market today (Windows-only).

**Where Windows-only today**:
- `audio-isolator.ps1` (717 lines, `:635`) — driverless per-process mic isolation via `IAudioPolicyConfig`/`IPolicyConfig` COM, spawned via `powershell.exe -Sta` (`main.js:355-417`, `:170` "MUST run with `-Sta`").
- `global-hold-listener.ps1` (`:636`) — `GetAsyncKeyState` global hotkey.
- `install-vbcable.ps1` (`:637`) — VB-CABLE driver installer (legacy strategy).
- `resolvePrivacyStrategy(platform, listenerName)` (`main.js:482-559`) — resolves `hotkey`/`policyconfig`/`vbcable` per `COMPANION_PRIVACY_MODE`/`COMPANION_VBCABLE`.
- `package.json` `build.win.icon`/`build.nsis` (`:642,650-655`) — packaging is Windows-targeted (NSIS installer); no `build.mac` config.
- Note: `docs/DRIVERLESS_MIC_ISOLATION_PLAN.md` is an **approved-but-unimplemented** plan for the Windows driverless approach (`docs/code_map/07_repo_catalog.md:56`) — read this before designing the macOS equivalent; the design principles (avoid VB-Cable-style virtual devices where possible, prefer OS-native per-process audio APIs) should carry over.

**What to build**:
1. **System-audio capture on macOS**: macOS 13+ has `ScreenCaptureKit` with system-audio capture support (no virtual audio device needed, similar spirit to the driverless Windows plan). For Electron, this likely means a small native helper (Swift/ObjC binary invoked similarly to how `audio-isolator.ps1` is spawned) or evaluating whether `desktopCapturer`/`getDisplayMedia` with `audio: true` now yields system audio on macOS in the Electron version pinned (`electron ^31.0.0`, `:655` — verify current support, this has changed across Electron versions).
2. **Mic isolation equivalent**: macOS doesn't have `IAudioPolicyConfig`; per-app mic routing typically requires either (a) a virtual audio device (BlackHole-style, mirrors the legacy VB-Cable path — `isVirtualRouteDevice` detection at `overlay.js:1792`/`full.js:122` may be reusable if generalized) or (b) accept that "ask AI" mic isolation is a Windows-only refinement initially and ship macOS with a simpler "mute system audio briefly" UX for hold-to-ask.
3. **Hotkey**: replace `global-hold-listener.ps1` with macOS equivalent (Electron's `globalShortcut` module is cross-platform — check whether the Windows path even needs the custom `.ps1` or if `globalShortcut` already suffices; if the `.ps1` exists for a reason `globalShortcut` can't satisfy, document why before porting).
4. **Platform detection**: `inferPlatform(title)` (`main.js:771-777`) and `hotkeyForPlatform(platform)` (`main.js:467-474`) are about *meeting-app* platform (zoom/teams/meet), not OS — don't conflate; add a separate `process.platform === 'darwin'` branch in `resolvePrivacyStrategy`/`startPrivacyHelper`.
5. **Packaging**: add `build.mac` to `package.json` (DMG target), `build/icon.icns`.

**Acceptance criteria**: on macOS, the overlay launches, binds to a Zoom/Meet window, captures system audio (counterparty speech) and mic (user speech) into the existing `LOCAL_MIC_PCM`/`REMOTE_APP_PCM` pipeline (`companion_runtime.py:303` `handle_audio_payload` is OS-agnostic on the backend — no backend changes expected), and hold-to-ask works (even if mic-isolation fidelity is initially lower than Windows).

**Skill**: `Plan` subagent — this is a substantial native-integration item; the sub-plan should explicitly scope a "v1" (system audio + basic hold-to-ask, accept lower mic-isolation fidelity) vs. "v2" (full per-process isolation parity). `security-review` for any new native helper binary (code signing/notarization considerations for distribution, though that's more ops than security per se — flag to user).

---

## 2.2 [NEW] Auto meeting detection (calendar integration)

**Severity**: addresses the "fully manual start/bind" gap — Granola-style habit loop is a verified retention driver.

**Where**: today, binding is manual — `MEETING_BINDING` (client→server, `01_backend_core.md:76`) is sent by the user explicitly; `update_meeting_binding` (`companion_runtime.py:241`) validates/stores it. `inferPlatform(title)` (`main.js:771-777`) already does window-title-based platform inference for an *already-selected* window — auto-detection extends this to proactively notice meeting windows without the user picking one.

**What to build**:
1. **Window-polling auto-detect (no calendar needed for v1)**: `main.js` already enumerates capture sources for `resolveDisplaySource` (`:838-912`) — add a lightweight periodic poll (e.g., every few seconds while idle) that checks open window titles for meeting-app patterns (the same patterns `inferPlatform` uses) and surfaces a non-intrusive overlay prompt: "Zoom meeting detected — start companion?" This alone delivers most of the habit-loop value without OAuth complexity.
2. **Calendar integration (v2)**: OAuth to Google/Outlook calendar (new auth flow alongside the existing OAuth loopback login in `main.js`), read upcoming events, pre-stage the prep wizard (shared component from Phase 1.4 — reuse, don't fork) before a detected meeting starts.
3. **Settings**: a toggle for auto-detect (privacy-sensitive — always-on window-title polling should be opt-in and clearly disclosed, consistent with the "transparent not stealth" positioning from the market research).

**Acceptance criteria**: opening a Zoom call with auto-detect enabled surfaces a "start companion?" prompt within ~5s; declining doesn't start any capture (privacy-safe default).

**Skill**: `Plan` subagent for v2 (OAuth scope). v1 (window-title polling) is small enough for direct implementation + `verify`.

---

## 2.3 [NEW] Glanceable cue-card overlay format

**Note**: this is the desktop counterpart of Phase 1.2 — **build the backend cue-card message type (1.2, item 1) once and consume it from both surfaces**, don't duplicate the backend change.

**Where**: `overlay.js` `renderChat()` (`:341`) renders the orb chat/caption feed today; `applyOverlayPresentation(mode)` (`main.js:1017-1063`) already resizes the overlay window per mode (`idle/menu/picker/panel/captions/compact/listening`) — a `cue-card` mode fits naturally into this existing mode system rather than as a bolted-on new window.

**What to build**:
1. Add a `cue-card` presentation mode to `applyOverlayPresentation` — compact, headline-first rendering of the `CUE_CARD`/structured `AI_RESPONSE` payload from 1.2.
2. `overlay.js` `renderChat()` — branch on payload shape: if structured cue fields are present (`headline`/`detail`/`tone`), render the compact card; otherwise fall back to existing prose rendering (graceful degradation when `CUE_CARD_FORMAT_ENABLED=False`).
3. `full.js` dashboard — same structured payload available via `BroadcastChannel`; render in the dashboard's advice panel alongside (not replacing) the transcript, since the full dashboard has more screen real estate for detail.

**Acceptance criteria**: with `CUE_CARD_FORMAT_ENABLED=True`, the overlay orb shows a compact cue card on new advice; with the flag off, behavior is unchanged from today.

**Skill**: `verify` + manual smoke test via `run` (Electron app launch).

---

## 2.4 [NEW] Post-call debrief surface

**Severity**: `session_trace` already writes `report.md` per session (`session_trace.py`, `08_backend_utils_logging.md:53,62,140`) but per the gap analysis it's **never surfaced to a UI** — pure productization of an existing artifact.

**Where**: `trace_report_path` is already surfaced to the frontend via `CONNECTION_ESTABLISHED` (`08_backend_utils_logging.md:71`, `04_backend_api_models_providers.md` websocket.py). `OUTCOME_SUMMARY` already triggers session teardown in `overlay.js` (`:1047,361`) and is handled in `full.js` (`:568`).

**What to build**:
1. **Backend**: on `OUTCOME_SUMMARY`, also send (or make fetchable via a small REST endpoint in `api/`) a structured summary derived from `_build_report_lines()` (`session_trace.py:182-211`) — Conversation Summary, Event Counts, and (once 0.4 lands) Latency Summary, plus session metrics (`session_metrics`).
2. **Desktop `full.js`**: a new "Debrief" view shown when `OUTCOME_SUMMARY` arrives — renders the structured summary, with a link/button to open the full `report.md` (local file, already on disk per `trace_report_path`).
3. **Web** (cross-reference Phase 3.5): the same structured summary becomes the basis for the shareable web debrief page — build the data shape once here, consumed by both.

**Acceptance criteria**: ending a desktop session shows a debrief view with conversation summary + key metrics, and a working link/button to the full report.

**Skill**: `verify`. Low risk — read-only productization of existing data.
