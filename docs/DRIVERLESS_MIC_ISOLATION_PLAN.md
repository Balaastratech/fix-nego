# Plan: Driverless Per-Process Mic Isolation (replace VB-Cable as default)

> Status: APPROVED (not yet implemented). Windows only for now.
> Owner at time of writing: [Agent: Claude Code]

## Context

Today the desktop companion achieves "counterparty can't hear me while I talk to the AI"
by forwarding the mic into a **VB-Cable** virtual device and muting that forward during
Hold-to-Ask. VB-Cable requires every user to install a kernel driver (admin + reboot +
manual Zoom mic config) and its license forbids silent redistribution — so the app can't
be a clean one-click download.

User research surfaced the **Windows `IAudioPolicyConfig`** approach: an undocumented but
stable COM interface (the backend of Settings → "App volume and device preferences") that
can redirect **one specific process's mic capture** to a silent endpoint, with zero install,
no driver, no admin, and no error dialogs in the meeting app. The AI keeps reading the real
mic via `getUserMedia`; only the meeting app gets silence.

**Goal:** make `IAudioPolicyConfig` the default privacy mechanism, fall back to **hotkey-mute**
when no silent endpoint exists, and keep **VB-Cable** as an env-toggleable path
(enable / auto / fully-off). Windows only for now.

### Why this is safe (verified during exploration)
- **Backend is 100% agnostic.** It enforces its own mute gate via `session.user_addressing_ai`
  in `backend/app/services/companion_runtime.py:340-346` (drops `LOCAL_MIC_PCM` during hold)
  and never reads *how* the client mutes. `muted_to_meeting` is stored but never acted on.
  **No backend changes required.**
- **Mic forward is trivial today** — `overlay.js:1272-1316` is just `<audio>.srcObject + setSinkId`,
  mute = `micForwardEl.muted = true` (`overlay.js:135-140`). No WebAudio graph to unwind.
- **The one gap:** the meeting app's **PID is not available** today. `process_name` is hardcoded
  `null` (`main.js:119`); `source.id` is `"window:HWND:0"`. We must add HWND→PID resolution.

---

## Architecture

```
Real Mic ─┬─> getUserMedia (Electron renderer) ──> AI lanes (always on)   [unchanged]
          └─> Meeting app reads REAL mic directly (default device)        [no cable]
                         │
                Hold-to-Ask pressed
                         ▼
   main.js resolves strategy at session start, then on hold:
     • policyconfig: helper.exe redirect <pid> <silentDeviceId>   (primary)
     • hotkey:       helper.exe send-keys <meeting mute combo>    (fallback)
     • vbcable:      renderer toggles micForwardEl.muted          (env-gated legacy)
                         ▼
                Hold released → restore
```

Strategy is decided **once per session in main.js** (it owns `child_process` + `process.env`)
and returned to the renderer. The renderer only knows which of the three to drive.

---

## New component: native helper `audio-isolator.exe`

Location: `desktop/native/audio-isolator/` (C++ console app, built separately, prebuilt
binary checked in + bundled via electron-builder `extraResources`). Single binary, commands:

| Command | Behavior |
|---|---|
| `enumerate-capture` | JSON of capture endpoints `{id, name, state}` (uses `IMMDeviceEnumerator` with `DEVICE_STATEMASK_ALL`) |
| `pid-from-hwnd <hwnd>` | `GetWindowThreadProcessId` → PID |
| `redirect <pid> <deviceId>` | `IAudioPolicyConfig::SetPersistedDefaultAudioEndpoint(pid, eCapture, role, deviceId)` for roles eConsole+eMultimedia+eCommunications |
| `restore <pid>` | same with empty/default device string to clear the override |
| `send-keys <combo>` | `SendInput` for hotkey fallback (e.g. `alt+a`) |

Implementation notes:
- Define `IAudioPolicyConfig` vtable manually; try Win11/21H2+ CLSID `{ab3d4648-e242-459f-b02f-541c70306324}`
  first, fall back to legacy `{2a59116d-6c4f-45e0-a74f-707e3fef9258}`. Report which worked on stdout.
- Silent-endpoint selection (in main.js, using `enumerate-capture` output): prefer a
  `DEVICE_STATE_DISABLED`/`UNPLUGGED` endpoint or one named `Line In`/`Stereo Mix`; else a
  non-default active input; if confidence low → signal "no silent endpoint" so main falls back to hotkey.
- Code-sign the `.exe` separately (OV cert) to reduce SmartScreen/AV friction. No injection,
  no remote threads — only COM + SendInput, low AV profile.

---

## CRITICAL SAFETY: persisted-override recovery

`SetPersistedDefaultAudioEndpoint` is **persistent** — it survives an app crash. If the
companion dies mid-hold, the meeting app stays redirected to the silent endpoint and the
user looks muted forever. The current VB-Cable mute auto-clears on close; this does not.

**Mandatory mitigations (must ship with the feature):**
1. On every successful `redirect`, write a recovery marker file (PID + original state) under
   the app's userData dir.
2. Restore on `app.on('before-quit')` and on `companion:endCompanionSession` (`main.js:371`).
3. On app startup, run a **sweep**: read any stale marker and `restore` it before starting.
4. Wrap hold in a watchdog: auto-restore after N seconds if no `release` arrives.

---

## File-by-file changes

### `desktop/src/main.js` (orchestration + native helper)
- Add `child_process.execFile` wrapper to call `audio-isolator.exe`; resolve path for dev vs
  packaged (`process.resourcesPath`).
- In `companion:bindMeetingTarget` (`:302`) and `:rebindMeetingTarget` (`:312`): parse HWND from
  `source.id` (`"window:<hwnd>:0"`), store on `companionState`; resolve PID via helper, with a
  title-based PID lookup as backstop.
- New IPC handlers:
  - `companion:resolvePrivacyStrategy` (session start): read env, `enumerate-capture`, pick silent
    endpoint, return chosen strategy + (if policyconfig) the silent deviceId.
  - `companion:privacyIsolate` (hold start): run `redirect` or `send-keys` per strategy; write recovery marker.
  - `companion:privacyRestore` (hold release): run `restore` or `send-keys`; clear marker.
- Recovery sweep on startup + `before-quit` restore + watchdog (see Safety section).
- Env resolution: `COMPANION_VBCABLE` = `auto|on|off`, `COMPANION_PRIVACY_MODE` = `auto|policyconfig|hotkey|vbcable`.

### `desktop/src/preload.js`
- Expose `bridge.resolvePrivacyStrategy()`, `bridge.privacyIsolate()`, `bridge.privacyRestore()`.

### `desktop/src/renderer/overlay.js` (the hold path)
- `startSession()` (`:1785-1786`): call `bridge.resolvePrivacyStrategy()`; store `state.privacyStrategy`.
  Only call `setupMicForward()` when strategy === `vbcable`.
- `updateMicMuteState()` (`:135-140`): dispatch by `state.privacyStrategy`:
  - `vbcable` → existing `micForwardEl.muted` toggle (unchanged).
  - `policyconfig`/`hotkey` → on enter-hold call `bridge.privacyIsolate()`, on exit call `bridge.privacyRestore()`.
  - Keep this idempotent; `setHold` (`:2016`/`:2053`) already the single call site.
- `autoSelectDevices()` (`:1217-1223`): keep VB-Cable detection but skip when `COMPANION_VBCABLE=off`.
- `reportCaptureHealth()` (`:1667-1686`): derive `helper_active` from the *active strategy*, not just `hasVb`;
  replace `vbcable_not_detected` reason with strategy-aware reason (e.g. `privacy_route_unavailable`).
- `sendStartNegotiation()` (`:1707-1708`): keep existing fields, add `privacy_strategy` (backend ignores it).

### `desktop/src/renderer/app.js` + `full.js` (status UI — cosmetic)
- `reportCaptureHealth()` (`app.js:657-673`) and `renderDevices()` (`full.js:144-153`): drive
  ready/not-ready from active strategy. "Virtual mic ready" → "Privacy route active (driverless)".
- Update VB-Cable copy to lead with driverless path; keep VB-Cable picker visible only when
  `COMPANION_VBCABLE != off`.

### UI copy (strings only)
- `index.html:51` ("Need VB-CABLE route"), `:73` ("Auto-selecting VB-CABLE"), `:77-79` (setup note);
  `full.html:55,65-67,204`; `app.js:622,672,964`; `full.js:104` → strategy-aware copy.

### Docs / scripts
- `desktop/README.md:13-51`: rewrite setup — driverless default, VB-Cable as opt-in (`COMPANION_VBCABLE=on`).
- `install-vbcable.ps1`: keep (only relevant when VB-Cable explicitly enabled).
- Add `desktop/native/audio-isolator/README.md` documenting build + signing.

### `desktop/package.json`
- electron-builder `extraResources`: bundle the prebuilt `audio-isolator.exe`. No node-gyp.

---

## What is explicitly NOT changing
- **Backend** — no edits. Verified agnostic (`companion_runtime.py:340-346`, `negotiation.py:270-271`).
- **AI TTS output privacy** — TTS still plays to the listening output (headphones); meeting app
  captures mic only, never system audio. No regression on the output side.
- **PCM capture lanes** — `micCapture`/`askCapture` gating (`overlay.js:1803/1817`) unchanged.

---

## Risks & mitigations
| Risk | Mitigation |
|---|---|
| Persisted override survives crash → user stuck muted | Recovery marker + startup sweep + before-quit restore + watchdog (Safety section) |
| HWND parse from `source.id` wrong on some Electron builds | Validate; title-based PID lookup backstop |
| No silent endpoint on machine | Fall back to hotkey-mute (chosen) |
| CLSID changes across Windows versions | Try both known CLSIDs; log which worked; telemetry |
| AV/SmartScreen flags helper exe | Code-sign; no injection so low profile |
| Hotkey path needs Zoom global shortcut enabled | One-time onboarding step; detect & warn if mic meter still moves |

---

## Verification (end-to-end)
1. **Helper unit checks:** `audio-isolator.exe enumerate-capture` prints endpoints; `pid-from-hwnd`
   returns a valid PID for a known window; `redirect`/`restore` round-trip on a test PID.
2. **Primary E2E (policyconfig):** Zoom set to the real default mic. Start companion → Hold-to-Ask →
   confirm Zoom's own mic level indicator goes silent AND the AI still transcribes the spoken question;
   release → Zoom mic returns. Confirm **no** Zoom "microphone disconnected" dialog appears.
2b. **Counterparty check:** second Zoom account confirms silence during hold, audio after release.
3. **Fallback E2E (hotkey):** force no-silent-endpoint (or `COMPANION_PRIVACY_MODE=hotkey`) → hold fires
   the mute combo; Zoom shows muted; release unmutes.
4. **VB-Cable toggle:** `COMPANION_VBCABLE=on` → legacy path still works; `=off` → VB-Cable UI/detection
   fully suppressed and never used.
5. **Crash recovery:** kill the app mid-hold → relaunch → startup sweep restores the meeting app's mic.
6. **Backend regression:** run the verified targeted pytest subset from HANDOFF.md (trace/companion/
   listener tests) → still green (should be untouched).
