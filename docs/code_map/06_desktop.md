I'll start by reading the HANDOFF.md for context, then systematically analyze each file.

HANDOFF.md is too large. Let me grep for relevant mentions and check file sizes.

Now let me dispatch parallel agents to analyze each major file, since this is a large task. I'll handle the main.js and preload.js myself first since they're foundational, then delegate the renderer files.

Now let me get more detail on main.js sections and dispatch parallel agents for the renderer files (overlay.js, full.js, app.js, login.js, HTML/CSS).

Two agents completed. Now let me continue reading main.js for full coverage of its structure while waiting for the overlay.js agent.

Now let me read the remaining IPC handlers section (1260-1545) to complete the catalog.

I now have comprehensive coverage of main.js. Let me wait for the overlay.js agent to finish (it's running in background).

I have enough context for main.js now. Let me check on the overlay.js agent status.

Let me do some additional verification work myself while the overlay.js agent runs - checking the HTML/CSS files and overlay window functions section of main.js in more detail.

Now let me check the privacy section (325-765) briefly for completeness on the remaining major functions, and read the HTML files quickly.

I have a solid foundation now. Let me check on the overlay.js background agent.

I have everything needed for main.js, preload.js, package.json, app.js, login.js, and HTML/CSS files. Let me check on the overlay.js agent's status now - I'll check if there's a notification, but since I shouldn't poll, let me do other useful prep work: verify the privacy strategy / watchdog functions and overlayWatchdog section briefly.

I now have complete coverage of main.js. Let me check the overlay.js agent's completion status by checking the output file existence (without reading it).

The agent (ac9dc53dc43fd0487) for overlay.js is still running. Let me wait for it to complete by sending it a follow-up check, or just continue with my own analysis of remaining areas while waiting. Let me verify the CSS files briefly and prepare the final report skeleton.

Now I'll wait for the overlay.js agent to finish since it's the largest file (3431 lines) and most critical. I'll check via a short monitor.

I'll continue with other prep work while waiting. Let me look at the overlay.html structure briefly to understand its UI elements (helps cross-reference overlay.js).

Now let me check the scripts folder briefly while waiting.

Now let's wait for the monitor notification for overlay.js completion.

The overlay.js agent is done. Let me retrieve its final result by sending a message to continue/get the report.

That was a new agent, not the original. Let me send the message to the correct agent ID.

The SendMessage tool isn't routing to the original agent ID correctly - it's spawning new agents instead. Let me try the SendMessage tool directly with the exact agent ID format.

No SendMessage tool available directly. Since the original agent's full output is in the JSONL file, let me just re-run the overlay.js analysis as a fresh agent - it will be faster the second time since the task is well-defined, or I can extract directly from the transcript file using grep on the jsonl (it's large but I can search for the final text).

I can extract the full text. Let me get the complete content.

I now have all the data I need from all three agents (overlay.js, full.js, app.js/login.js/HTML/CSS) plus my own main.js/preload.js/package.json analysis. Let me verify a couple of line numbers in overlay.js that seemed slightly imprecise (the catalog noted some approximations), then compile the final comprehensive reference map.

I have all the precise data I need. Now let me compile the comprehensive reference map document and present it as the final response.

I have comprehensive data on all files. Here is the complete reference map.

---

# Desktop Companion App — Reference Map
`/home/user/fix-nego/desktop`

---

## main.js
`/home/user/fix-nego/desktop/src/main.js` (1683 lines) — Electron main process

### 1. Purpose
Electron main process. Resolves backend URL config (dev `.env` vs packaged prod), manages runtime/userData paths, hosts `companionState`/`privacyState`/`PROVIDER_CONFIG`/auth-token persistence, the OAuth loopback login flow, the driverless mic-privacy-isolation subsystem (PowerShell helper via STA COM), screen/window capture source resolution + `setDisplayMediaRequestHandler`, and creates/owns three windows: `overlayWindow` (orb, loads `overlay.html`), `fullWindow` (dashboard, loads `full.html`), `loginWindow` (loads `login.html`). It is the IPC server for `preload.js`'s `companionBridge`.

### 2. Top-level functions/sections
| Lines | Symbol | Description |
|---|---|---|
| `main.js:15` | `function resolveBackendConfig()` | Resolves `{ws, http, token}` from env/`.env` or `PROD_BACKEND_WS` default |
| `main.js:32-34` | `ipcMain.on("companion:getBackendConfig")` | Sync IPC returning resolved backend config |
| `main.js:36-49` | `application-loopback` require | Loads optional native module for process audio loopback |
| `main.js:51-69` | runtime paths/cache setup | `userData`/`sessionData`/cache dir, GPU/disk-cache/throttling command-line switches, WGC-disable feature flags |
| `main.js:72-119` | `const companionState = {...}` | Central mutable session/device/capture state (see §5) |
| `main.js:133-137` | privacy helper paths | `PRIVACY_HELPER_SCRIPT`, `PRIVACY_RECOVERY_FILE`, `PRIVACY_WATCHDOG_MS=30000` |
| `main.js:144-171` | `PROVIDER_CONFIG_FILE`, `readProviderConfig()`, `writeProviderConfig()` | Phase G BYOK provider config persisted to `user-data/provider-config.json` (0600) |
| `main.js:179-206` | `AUTH_TOKEN_FILE`, `readAuthTokens()`, `writeAuthTokens()`, `clearAuthTokens()` | Encrypted (safeStorage) Clerk/app JWT storage |
| `main.js:217-288` | `ipcMain.handle("companion:startLogin")` | Loopback OAuth: spawns local HTTP server, opens Clerk login page in system browser, exchanges `clerk_token` → app JWT |
| `main.js:290-323` | `ipcMain.handle("companion:logout")` | Revokes refresh token, clears local tokens, creates login window BEFORE destroying overlay/full (ordering matters — see gotcha) |
| `main.js:325-340` | `const privacyState = {...}` | Privacy-isolation strategy/runtime state |
| `main.js:344-352` | `function helperScriptExists()` | Checks `audio-isolator.ps1` presence (cached) |
| `main.js:355-417` | `function startPrivacyHelper()` | Spawns persistent `powershell.exe -Sta` helper, wires stdout JSON-line protocol |
| `main.js:419-429` | `function stopPrivacyHelper()` | Sends `{cmd:"exit"}`, force-kills after 1s |
| `main.js:432-454` | `function helperCmd(cmdObj, timeoutMs)` | Promise-based request/response queue to helper |
| `main.js:455-464` | `function waitForHelperReady(maxMs)` | Polls `privacyState.helperReady` |
| `main.js:467-474` | `function hotkeyForPlatform(platform)` | zoom→`alt+a`, teams→`ctrl+shift+m`, google_meet→`ctrl+d` |
| `main.js:482-559` | `async function resolvePrivacyStrategy(platform, listenerName)` | Resolves `hotkey` (default) vs `policyconfig` vs `vbcable` per `COMPANION_PRIVACY_MODE`/`COMPANION_VBCABLE` env |
| `main.js:562-574` | `writeRecoveryMarker()`, `clearRecoveryMarker()` | Persists redirect/disabled-spare info for crash recovery |
| `main.js:577-608` | `async function recoverStaleRedirect()` | On startup, repairs stale mic redirects from prior crash |
| `main.js:611-652` | `async function performPrivacyIsolate()` | On hold-press: policyconfig redirect or hotkey mute |
| `main.js:655-694` | `async function performPrivacyRestore()` | On hold-release: restore redirect/un-mute |
| `main.js:702-728` | `async function performHotkeyMute(combo, desired)` | Sends meeting-app mute hotkey via helper SendInput |
| `main.js:731-746` | `startWatchdog()`/`stopWatchdog()` | Auto-restores mic if hold not released within 30s |
| `main.js:749-761` | `async function resolveMeetingPid(hwnd)` | Resolves PID from HWND via helper |
| `main.js:766-769` | window/state globals | `overlayWindow`, `fullWindow`, `overlayPresentation="idle"`, `activeProcessCapturePid` |
| `main.js:771-777` | `function inferPlatform(title)` | zoom/google_meet/teams/generic detection |
| `main.js:779-794` | `function isNoiseWindowTitle(title)` | Filters out own app/system windows from picker |
| `main.js:796-820` | `setRemoteAudioMode()`, `stopRemoteProcessCapture()` | Manages `companionState.remoteAudioMode` ("none"/"display_loopback"/"process_loopback") |
| `main.js:822-836` | `parseWindowHandleFromSourceId()`, `normalizeHandle()` | HWND extraction/normalization from `window:<hwnd>:...` source ids |
| `main.js:838-912` | `function resolveDisplaySource(sources)` | Multi-strategy re-match of selected capture source (id → name+kind → handle → title → fuzzy-normalized title → platform priority) |
| `main.js:917-926` | `function normalizeTitleForMatch(title)` | Strips unread badges/timers/"N new messages" suffixes |
| `main.js:933-948` | `function pickScreenSource(sources)` | Fallback monitor selection (last display → primary → "Entire screen") |
| `main.js:952-964` | `function setCaptureFollowingScreen(following)` | Pushes `companion:captureFollowingScreen` to overlay when capture falls back to monitor |
| `main.js:966-978` | `function targetPriority(title)` | Scores window titles for meeting-likelihood |
| `main.js:980-1003` | `async function listMeetingTargets()` | Returns sorted/filtered window list for picker |
| `main.js:1005-1015` | `function overlayBounds()` | Initial 58x58 top-right overlay position |
| `main.js:1017-1063` | `function applyOverlayPresentation(mode)` | Resizes overlay window per mode (idle/menu/picker/panel/captions/compact/listening) |
| `main.js:1065-1100` | `function createOverlayWindow()` | Frameless/transparent/always-on-top BrowserWindow, loads `overlay.html` |
| `main.js:1102-1139` | `function createFullWindow()` | 1280x800 dashboard BrowserWindow, loads `full.html`; `close` → destroy overlay + `app.quit()` |
| `main.js:1149-1171` | `function createLoginWindow(opts)` | 480x640 BrowserWindow, loads `login.html` |
| `main.js:1183-1195` | `function openFullWindow()` | Restores/maximizes/focuses full window |

### 3. IPC channels (ipcMain.handle/on)
| Line | Channel | Purpose |
|---|---|---|
| `main.js:32` | `companion:getBackendConfig` (`.on`, sync) | Returns `{ws, http, token}` |
| `main.js:172` | `companion:getProviderConfig` | Read BYOK provider config |
| `main.js:173` | `companion:setProviderConfig` | Write BYOK provider config |
| `main.js:208` | `companion:getAuth` | Read encrypted auth tokens |
| `main.js:209` | `companion:setAuth` | Write encrypted auth tokens |
| `main.js:210` | `companion:clearAuth` | Delete auth token file |
| `main.js:217` | `companion:startLogin` | Loopback OAuth flow (also sends `companion:loginUrl` event) |
| `main.js:290` | `companion:logout` | Revoke + clear tokens, recreate login window |
| `main.js:1174` | `companion:loginSuccess` | Close login window, create overlay+full windows |
| `main.js:1197` | `companion:listMeetingTargets` | List candidate meeting windows |
| `main.js:1202` | `companion:getScreenSources` | Screens+windows w/ thumbnails for picker |
| `main.js:1234` | `companion:bindMeetingTarget` | Bind meeting window, resolve PID for privacy |
| `main.js:1260` | `companion:rebindMeetingTarget` | Re-bind/re-resolve PID |
| `main.js:1286` | `companion:listAudioDevices` | Stub, returns `{inputs:[],outputs:[]}` |
| `main.js:1288` | `companion:getWindowProcessIds` | Native `getActiveWindowProcessIds()` |
| `main.js:1300` | `companion:startProcessAudioCapture` | Starts native loopback capture, streams via `companion:processAudioChunk` |
| `main.js:1346` | `companion:stopProcessAudioCapture` | Stops loopback capture |
| `main.js:1352` | `companion:selectListeningOutput` | Sets `companionState.listeningOutput` |
| `main.js:1360` | `companion:selectMeetingRouteOutput` | Sets `companionState.meetingRouteOutput` + binding fields |
| `main.js:1370` | `companion:startCompanionSession` | Sets `sessionActive=true`, returns state snapshot |
| `main.js:1381` | `companion:setHoldToAsk` | Sets `companionState.holdState` |
| `main.js:1389` | `companion:setCaptureHealth` | Merges into `companionState.captureHealth` |
| `main.js:1397` | `companion:getCaptureHealth` | Returns capture health |
| `main.js:1399` | `companion:endCompanionSession` | Resets session/capture/privacy state |
| `main.js:1427` | `companion:resolvePrivacyStrategy` | Resolves hotkey/policyconfig/vbcable strategy |
| `main.js:1446` | `companion:privacyIsolate` | Mic isolate on hold-press |
| `main.js:1455` | `companion:privacyRestore` | Mic restore on hold-release |
| `main.js:1464` | `companion:openFullWindow` | Show/maximize/focus full window |
| `main.js:1469` | `companion:minimizeFullWindow` | Minimize full window |
| `main.js:1476` | `companion:moveOverlayWindow` | Repositions overlay |
| `main.js:1488` | `companion:setOverlayPresentation` | Resizes overlay per mode |
| `main.js:1490` | `companion:getOverlayContrast` | Samples screen luminance behind overlay → theme |

**Outbound events (`webContents.send`):**
- `companion:loginUrl` (`main.js:233`) → login window
- `companion:overlayPresentation` (`main.js:1061`) → overlay window
- `companion:processAudioChunk` (`main.js:1320`) → overlay window
- `companion:captureFollowingScreen` (`main.js:958`) → overlay window

### 4. Window creation / load mapping
- `overlayWindow.loadFile(...overlay.html)` — `main.js:1096`
- `fullWindow.loadFile(...full.html)` — `main.js:1119`
- `loginWindow.loadFile(...login.html)` — `main.js:1169`
- `index.html`/`app.js` — **never referenced** (legacy/dead path)
- App startup (`main.js:1553-1677`): if `readAuthTokens()` has `access_token` → `createOverlayWindow()` + `createFullWindow()`; else → `createLoginWindow()`. `app.on("activate")` recreates windows unless login window is open. `app.on("window-all-closed")` quits on non-darwin.

### 5. `companionState` (main.js:72-119) key fields
`meetingBinding`, `listeningOutput`, `meetingRouteOutput`, `captureHealth` (incl. `degraded_reasons`), `holdState`, `sessionActive`, `selectedDesktopSourceId/Name/Kind`, `captureFollowingScreen`, `captureMissCount`, `meetingDisplayId`, `remoteAudioMode` ("none"|"display_loopback"|"process_loopback"), `processAudioCapture {pid, hwnd}`.

`privacyState` (main.js:325-340): `strategy` ("policyconfig"|"hotkey"|"vbcable"|null), `method`, `targetDeviceId`, `needsDisable`, `listenerName`, `meetingPid`, `meetingPlatform`, `isMuted`, `disabledSpare`, `watchdogTimer`, `helperProc`, `helperReady`, `helperQueue`, `_pendingLine`.

### 6. Gotchas
- `main.js:308-312` — **logout ordering bug fix**: must create login window BEFORE destroying overlay/full, else `window-all-closed` fires `app.quit()` mid-logout ("logout closes the app" bug).
- `main.js:1602-1604` — selection is intentionally NOT cleared when capture source can't be found ("that was the bug that 'dropped' the window").
- `main.js:931-932` — Windows note: `desktopCapturer` screen sources often have empty `display_id` → degrade to primary/first screen.
- `main.js:360-363` — PowerShell helper MUST run with `-Sta` or COM audio APIs silently return nothing.

### 7. Backend URL config
`main.js:14-30`: `PROD_BACKEND_WS = "wss://api.balaastratech.com/ws"`. `resolveBackendConfig()` reads `process.env.COMPANION_BACKEND_WS` (else prod default), derives `http` from `ws`→`https`/`http` and strips `/ws` unless `COMPANION_BACKEND_HTTP` set, and `COMPANION_SHARED_TOKEN` for `token`. Loaded from `desktop/.env` via `dotenv` (`main.js:7`). Exposed synchronously to renderers via `companion:getBackendConfig`.

---

## preload.js
`/home/user/fix-nego/desktop/src/preload.js` (90 lines)

### 1. Purpose
contextBridge layer. Resolves `window.companionConfig` synchronously from main (`companion:getBackendConfig`), and exposes `window.companionBridge` — the full IPC surface used by overlay.js, full.js, login.js (and legacy app.js).

### 2. Sections
| Lines | Section |
|---|---|
| `preload.js:6-13` | `backendConfig` resolution + `contextBridge.exposeInMainWorld("companionConfig", backendConfig)` — fallback `{ws:"ws://localhost:8000/ws", http:"http://localhost:8000"}` |
| `preload.js:15-29` | `async function enumerateAudioDevices()` — wraps `navigator.mediaDevices.enumerateDevices()` |
| `preload.js:31-90` | `contextBridge.exposeInMainWorld("companionBridge", {...})` |

### 3. contextBridge exposures
- `companionConfig` — `preload.js:13`
- `companionBridge` methods (all `ipcRenderer.invoke` unless noted) — `preload.js:31-90`: `listMeetingTargets`(32), `getScreenSources`(33), `bindMeetingTarget`(34), `rebindMeetingTarget`(35), `getWindowProcessIds`(36), `startProcessAudioCapture`(37), `stopProcessAudioCapture`(38), `listAudioDevices`(39, local), `getProviderConfig`(41), `setProviderConfig`(42), `getAuth`(44), `setAuth`(45), `clearAuth`(46), `startLogin`(47), `onLoginUrl`(48-52, `.on` listener wrapper), `logout`(53), `loginSuccess`(54), `selectListeningOutput`(55), `selectMeetingRouteOutput`(56), `startCompanionSession`(57), `setHoldToAsk`(58), `setCaptureHealth`(59), `getCaptureHealth`(60), `endCompanionSession`(61), `openFullWindow`(62), `minimizeFullWindow`(63), `setOverlayPresentation`(64), `getOverlayContrast`(65), `moveOverlayWindow`(66), `onOverlayPresentation`(67-71, `.on` listener), `onProcessAudioChunk`(72-76, `.on` listener), `onCaptureFollowingScreen`(77-81, `.on` listener), `resolvePrivacyStrategy`(84-85), `privacyIsolate`(87), `privacyRestore`(89).

Note: `getWindowMode` is NOT exposed (relevant to app.js gotcha below).

---

## overlay.js
`/home/user/fix-nego/desktop/src/renderer/overlay.js` (3431 lines)

### 1. Purpose
Renderer for the floating orb (`overlayWindow`, frameless/always-on-top, loads `overlay.html` via `main.js:1096`). Owns the WebSocket to backend `/ws`, all audio capture (mic, ask-AI mic, VB-Cable/remote audio, process-loopback), AI voice playback (StereoPanner, ducking), screen/meeting capture, hold-to-ask privacy isolation, orb chat/caption rendering, and broadcasts state to `full.js` over `BroadcastChannel("negotiation_companion_ui")`. `full.js` has no WS of its own — overlay.js is the sole backend connection owner.

### 2. Top-level functions/sections
| Line | Symbol | Description |
|---|---|---|
| 3 | `const bridge = window.companionBridge` | IPC bridge alias |
| 4 | `const channel = new BroadcastChannel("negotiation_companion_ui")` | Cross-window UI channel |
| 5 | `const STORAGE_KEY` | localStorage prefs key |
| 6 | `const BACKEND_WS_URL` | `companionConfig.ws` or `ws://localhost:8000/ws` |
| 8 | `const BACKEND_SHARED_TOKEN` | legacy static token fallback |
| 12 | `let _authTokens` | cached Clerk/app tokens |
| 14 | `async function _loadAuthTokens()` | `companionBridge.getAuth()` |
| 22 | `async function _getActiveToken()` | returns valid access token, refreshes if needed |
| 28 | `async function _refreshAuthTokens()` | `fetch(BACKEND_HTTP + "/auth/refresh")` |
| 32 | `const BACKEND_HTTP` | `companionConfig.http` or `http://localhost:8000` |
| 46 | `async function backendWsUrl()` | appends `?token=`/`&token=<active token>` |
| 52-55 | process-audio constants | resampling/flush/silence thresholds |
| 58 | `const state = {...}` | global state object (§5) |
| 151 | `const $ = (id) => document.getElementById(id)` | DOM getter |
| 152-160 | cached DOM refs | orb, ring, conn-dot, chat-feed, mix strip, etc. |
| 163 | `function loadPrefs()` | localStorage load |
| 169 | `function savePrefs()` | localStorage save |
| 174 | `function setOrbState(s)` | sets visual orb state |
| 201 | `function updateConnectionIndicator()` | conn-dot color/tooltip |
| 225 | `function updateMicMuteState()` | mutes mic-forward based on hold/orb state |
| 256 | `function updateRootClasses()` | root container CSS classes |
| 266 | `function desiredOverlayPresentation()` | computes layout mode |
| 280 | `function syncOverlayPresentation()` | applies + IPC notify (`setOverlayPresentation`) |
| 289 | `async function refreshContrast()` | `getOverlayContrast` IPC |
| 310 | `function getChatIterations()` | groups privateEntries into Q&A blocks |
| 334 | `function formatChatTimestamp(ts)` | timestamp formatting |
| 341 | `function renderChat()` | renders orb chat/caption feed |
| 405 | `function entryFromPayload(payload, fallbackSpeaker)` | normalizes WS payload → entry |
| 417 | `function normalizeTranscriptText(text)` | text cleanup |
| 425 | `function shouldCollapseHumanEntries(previous, next)` | dedup logic |
| 444 | `function shouldAppendHumanContinuation(previous, next)` | continuation detection |
| 467 | `function mergeHumanEntryText(previousText, nextText)` | merges continuation |
| 480 | `function upsertEntry(list, entry, limit)` | insert/update/cap entry list |
| 524 | `function broadcast(type, payload)` | `channel.postMessage` to full.js |
| 527 | `function broadcastSnapshot()` | full state snapshot (`STATE_SNAPSHOT`) |
| 551 | `function broadcastSnapshotThrottled()` | 300ms-throttled snapshot |
| 557 | `function f32ToI16Buffer(f32)` | Float32→Int16 PCM |
| 565 | `function toBase64(buf)` | ArrayBuffer→base64 |
| 573 | `function wsSend(type, payload)` | `state.ws.send(JSON.stringify({type,payload}))` |
| 584 | `async function sendProviderConfig()` | sends `PROVIDER_CONFIG` (Phase G BYOK) on connect |
| 603 | `function stopActivePlayback(sendDone)` | stops AI audio sources |
| 621 | `function traceClientEvent(eventName, summary, detail)` | sends `TRACE_CLIENT_EVENT` |
| 630 | `function resolvePreferredCaptureSourceId(sourceId)` | resolves preferred capture source |
| 634 | `function selectedSourceKindFromId(sourceId)` | screen vs window |
| 640 | `function setSelectedCaptureSource(source)` | stores selection |
| 652 | `function selectedSourceMatches(source)` | compares to current selection |
| 662 | `async function refreshScreenSources()` | `getScreenSources` IPC |
| 671 | `function resolveSourceForTarget(target, sources)` | maps meeting target→source |
| 684 | `function resolveCurrentSelectedSource(sources, preferredSourceId)` | resolves source object |
| 701 | `function parseWindowHandleFromSourceId(sourceId)` | HWND from source id |
| 707 | `function normalizeHandle(value)` | normalizes handle |
| 717 | `function resolveMeetingWindowHandle()` | HWND of selected target |
| 724 | `function toUint8Array(chunk)` | coerce chunk |
| 735 | `function mergeArrayBuffers(buffers)` | concat buffers |
| 746 | `async function syncDesktopCaptureSelection(sourceId)` | syncs main process selection |
| 757 | `async function connectBackend()` | opens WS via `backendWsUrl()` |
| 812 | `function handleWsMessage(ev)` | main WS dispatcher (§4) |
| 1080 | `async function ensurePlayback()` | inits AudioContext/gain/panner |
| 1144 | `function playPcm(buffer)` | schedules PCM playback |
| 1202 | `function applyAiGain(rampSeconds)` | volume+duck gain ramp |
| 1211 | `function duckPlayback(speaking)` | ducks AI volume |
| 1239 | `function setUserAiVolume(value01)` | sets baseline AI volume |
| 1243 | `function setAutoDuckEnabled(enabled)` | toggles auto-duck |
| 1260 | `const PCM_WORKLET_CODE` | inline AudioWorklet (`PcmCaptureProcessor`) |
| 1298 | `const FRAME_ENCODER_CODE` | inline OffscreenCanvas worker for JPEG frame encode |
| 1315 | `async function createPcmCapture(stream, msgType, options)` | mic→16kHz PCM→WS pipeline |
| 1529 | `function inferProcessAudioFormat(uint8Chunk)` | detects process-audio PCM format |
| 1558 | `function convertProcessAudioChunk(uint8Chunk)` | converts/resamples |
| 1619 | `function resetProcessAudioSegment()` | resets utterance state |
| 1625 | `function stopProcessAudioCapture()` | stops loopback capture |
| 1645 | `function flushProcessAudioBuffer(forceFinal)` | flushes buffered audio to backend |
| 1689 | `function findProcessAudioMatch(windows)` | matches target window |
| 1715 | `async function startProcessAudioCapture()` | starts loopback via IPC |
| 1787 | `function _isBadMic(label)` | filters bad mic labels |
| 1792 | `function isVirtualRouteDevice(label)` | detects VB-Cable devices |
| 1796 | `function hasUnsafeDeviceLoopback()` | checks unsafe mic/output loopback |
| 1809 | `async function autoSelectDevices()` | auto-selects mic/output |
| 1876 | `async function setupMicForward(stream)` | forwards mic to VB-Cable `<audio>` |
| 1928 | `async function showScreenPicker()` | screen/window picker modal |
| 2039 | `async function stopMeetingCapture()` | stops capture |
| 2052 | `async function teardownLocalSession({resetSelection, closeSocket})` | full local cleanup |
| 2103 | `async function startMeetingCapture(sourceId)` | starts display/audio capture |
| 2396 | `function reportCaptureHealth(overrides)` | sends capture health |
| 2437 | `function sendStartNegotiation()` | sends `START_NEGOTIATION` |
| 2464 | `async function startSession()` | orchestrates session start |
| 2685 | `function pauseSession()` | pauses |
| 2710 | `function resumeSession()` | resumes |
| 2723 | `function endSession()` | ends/tears down |
| 2736 | `async function selectTarget(target, {autoStart})` | selects meeting target |
| 2765 | `function closeMenu()` | closes meeting menu |
| 2775 | `function renderMenu()` | renders target menu |
| 2829 | `async function openMenu()` | opens target menu |
| 2846 | `async function openScreenSelectionFromOverlay()` | opens screen picker |
| 2881 | `function toggleMenu()` | toggles menu |
| 2887 | `async function setHold(active, source)` | activates/deactivates hold-to-ask |
| 2944 | `function startRingFill()` / 2951 `stopRingFill()` | orb hold-progress ring animation |
| 3137-3165 | `(function setupScreenPickerChip())` IIFE | screen-chip wiring |
| 3186-3230 | `(function setupAudioMixUI())` IIFE | AI volume slider/duck UI |
| 3171 | `function syncOverlayMixUI()` | syncs mix UI controls |
| 3236-3431 | `(function setupLanguageUI())` IIFE | language menu, monkey-patches `state.ws.onmessage` for `LANGUAGE_UPDATE` |

### 3. IPC channel usage
| Line | Channel/Method | Usage |
|---|---|---|
| 3 | `window.companionBridge` | aliased `bridge` |
| 6 | `window.companionConfig.ws` | base WS URL |
| 8 | `window.companionConfig.token` | shared token fallback |
| 16 | `companionBridge.getAuth()` | load cached tokens |
| 32 | `window.companionConfig.http` | base HTTP URL |
| 41 | `companionBridge.setAuth()` | persist refreshed tokens |
| 586-587 | `companionBridge.getProviderConfig()` | BYOK config before WS send |

Also used throughout (per preload surface): `listMeetingTargets`, `getScreenSources`, `bindMeetingTarget`, `rebindMeetingTarget`, `getWindowProcessIds`, `startProcessAudioCapture`/`stopProcessAudioCapture`, `listAudioDevices`, `selectListeningOutput`, `selectMeetingRouteOutput`, `startCompanionSession`/`endCompanionSession`, `setHoldToAsk`, `setCaptureHealth`/`getCaptureHealth`, `openFullWindow`, `setOverlayPresentation`, `getOverlayContrast`, `moveOverlayWindow`, `onOverlayPresentation`, `onProcessAudioChunk`, `onCaptureFollowingScreen`, `resolvePrivacyStrategy`, `privacyIsolate`/`privacyRestore`.

### 4. WebSocket message types
**Outgoing** (via `wsSend`, overlay.js:573):
| Line | Type | Purpose |
|---|---|---|
| 593 | `PROVIDER_CONFIG` | BYOK keys/slots/settings on connect |
| 617, 1191 | `AI_PLAYBACK_DONE` | AI audio finished |
| 622 | `TRACE_CLIENT_EVENT` | telemetry |
| 882 | `MEETING_BINDING` | binds meeting window post-session-start |
| 952 | `START_COPILOT` | triggers copilot on first non-AI transcript |
| 1397 | `LOCAL_MIC_PCM` / `ASK_AI_PCM` | 16kHz PCM mic streams (param-driven) |
| 1675 | `REMOTE_APP_PCM` | VB-Cable/counterparty audio |
| 2208 | `SCREEN_FRAME` | base64 JPEG frame + ts |
| 2335, 2368, 2433 | `CAPTURE_HEALTH` | capture health report |
| 2445 | `START_NEGOTIATION` | start session |
| 2667 | `PRIVACY_CONSENT_GRANTED` | consent before start |
| 2701 | `PAUSE_NEGOTIATION` | pause |
| 2715 | `RESUME_NEGOTIATION` | resume |
| 2725 | `END_NEGOTIATION` | end |
| 2932 | `HOLD_TO_ASK_STATE` | hold press/release |
| 3090, 3386 | `SET_LANGUAGE_PROFILE` | language profile change |

**Incoming** (`handleWsMessage`, overlay.js:812-1074; binary `ArrayBuffer` → `playPcm`):
| Line | Type | Handling |
|---|---|---|
| 824 | `CONNECTION_ESTABLISHED` | sets sessionId/backendReady, sends provider config, broadcasts snapshot |
| 853 | `BACKEND_READY` | marks ready to start |
| 860 | `CONSENT_ACKNOWLEDGED` | proceeds to `sendStartNegotiation()` |
| 868 | `SESSION_STARTED` | session live, sends `MEETING_BINDING` + capture health |
| 898 | `COPILOT_STARTED` | confirms copilot |
| 908 | `SESSION_PAUSED` | pause + stop playback |
| 921 | `SESSION_RESUMED` | resume |
| 931 | `TRANSCRIPT_PARTIAL`/`TRANSCRIPT_UPDATE` | updates entries/orb/chat |
| 992 | `TRANSCRIPT_DELETE` | removes entry by id |
| 998 | `AI_RESPONSE` | adds to `privateEntries`, renders chat |
| 1013 | `AI_THINKING` | orb → "processing" |
| 1018 | `AUDIO_INTERRUPTED` | stops playback, resets timeline |
| 1034 | `AI_LISTENING` | orb → "active" if not holding |
| 1038 | `RESEARCH_STARTED` | relayed to full.js |
| 1041 | `RESEARCH_COMPLETE` | relayed |
| 1044 | `RESEARCH_FAILED` | relayed |
| 1047 | `OUTCOME_SUMMARY` | tears down session |
| 1050 | `DEGRADED_MODE_UPDATE` | orb → "degraded", broadcasts |
| 1055 | `ERROR` (`CONNECTION_TIMEOUT`) | resets session, marks degraded |
| 3409 | `LANGUAGE_UPDATE` | handled via `setupLanguageUI()` onmessage tap |

**HTTP**: overlay.js:33 — `fetch(BACKEND_HTTP + "/auth/refresh")`.

**Outgoing BroadcastChannel** (to full.js): `STATE_SNAPSHOT`, `CONVERSATION_ENTRY`, `PRIVATE_ENTRY`, `RESEARCH_STARTED/COMPLETE/FAILED`, `DEGRADED`, `START_BLOCKED`, `PRIVACY_SETUP_NOTE`, `AUDIO_MIX_STATE`, `LANGUAGE_ACK`.
**Incoming BroadcastChannel** (from full.js): `COMMAND_START/PAUSE/RESUME/END_SESSION`, `REQUEST_STATE`, `COMMAND_SET_AUDIO_MIX`, `COMMAND_SET_LANGUAGE`.

### 5. Global `state` object (overlay.js:58-148)
| Lines | Group | Properties |
|---|---|---|
| 59-69 | Connection/session | `ws`, `wsConnecting`, `sessionId`, `backendState`, `_pendingStart`, `backendReady`, `backendStatusMessage`, `wsConnected`, `sessionLive`, `sessionStarting`, `sessionPaused` |
| 72-74 | Hold-to-ask | `holdActive`, `holdSource`, `awaitingPrivateReply` |
| 77-105 | Audio | `playbackCtx`, `playbackDest`, `playbackEl`, `playbackNextAt`, `_playbackDoneTimer`, `playbackGain`, `playbackPanner`, `activePlaybackSources`, `ignoreIncomingAiUntil`, `isDucked`, `duckTimer`, `userAiVolume`(1.0), `autoDuckEnabled`(true), `duckMultiplier`(0.8), `micStream`, `selectedMicDeviceId/Label`, `micCapture`, `askCapture`, `micForwardEl`, `meetingCapture`, `copilotStarted`, `vbCableDeviceId/Label`, `privacyStrategy`, `listeningDeviceId/Label` |
| 108-123 | Meeting/capture | `meetingTargets`, `screenSources`, `selectedTarget`, `selectedSourceId/Name/Kind`, `processAudioActive`, `processAudioUnsubscribe`, `processAudioFlushTimer`, `processAudioPendingChunks`, `processAudioUtteranceId`, `processAudioStartedAt/LastChunkAt`, `processAudioProbeLogged`, `processAudioInputFormat`, `processAudioMatchStrategy` |
| 126-127 | Transcript | `conversationEntries` (cap 80), `privateEntries` (cap 40) |
| 130-137 | UI | `orbState`, `menuOpen`, `langMenuOpen`, `dragging`, `dragPointerId`, `dragOffX/Y`, `dragMoved` |
| 140-141 | Ring animation | `ringTimer`, `ringStarted` |
| 143-147 | `prefs` (persisted) | `lastMeetingTitle`, `listeningDeviceId`, `vbCableDeviceId` |

### 6. Gotchas
- `overlay.js:2485` — starting before capability probes finish "races the probes and can fail" — `startSession()` refuses with clear message.
- `overlay.js:2542-2560` — one-time `PRIVACY_SETUP_NOTE` guidance per active privacy method (hotkey/redirect-cable).
- `overlay.js:2964` — "Following screen" note + Re-pick button when capture falls back to monitor.
- `overlay.js:3398-3406` — `setupLanguageUI()` monkey-patches `state.ws.onmessage` (chained via `prev`) since there's no clean event bus; retries `installTap()` every 250ms up to 30s.
- HANDOFF.md:599 — VB-Cable mute is a no-op if `state.micForwardEl` is null (VB-Cable not installed).
- HANDOFF.md:2584 — older raw `new WebSocket("ws://localhost:8000/ws")` with no auth, superseded by `backendWsUrl()` token-based connect.

### 7. Backend URL config
- `overlay.js:6` — `BACKEND_WS_URL = companionConfig.ws || "ws://localhost:8000/ws"`
- `overlay.js:8` — `BACKEND_SHARED_TOKEN = companionConfig.token || ""`
- `overlay.js:32` — `BACKEND_HTTP = companionConfig.http || "http://localhost:8000"`
- `overlay.js:46-50` — `backendWsUrl()` appends `?token=`/`&token=<active token>` from `_getActiveToken()`
- `overlay.js:766` — `new WebSocket(await backendWsUrl())` — actual connection point

---

## full.js
`/home/user/fix-nego/desktop/src/renderer/full.js` (1428 lines)

### 1. Purpose
Renderer for the maximized dashboard window (`fullWindow`, loads `full.html` via `main.js:1119`, created at startup, immediately maximize→show→minimize). Session controls, meeting picker, transcript/Private-AI-Asks/research panels, audio mix & language UI, user profile/auth, BYOK Settings tab. Has **no own WebSocket** — relies entirely on `BroadcastChannel("negotiation_companion_ui")` to/from overlay.js, plus direct `fetch()` to `BACKEND_HTTP` for auth refresh, `/api/ready` polling, and `/api/providers/*`.

### 2. Top-level functions/sections
| Line | Symbol | Description |
|---|---|---|
| full.js:3 | `const bridge = window.companionBridge` | IPC bridge alias |
| full.js:4 | `const channel = new BroadcastChannel("negotiation_companion_ui")` | cross-window channel |
| full.js:7-40 | `const $ = ...` + DOM ref consts | cached element lookups |
| full.js:43-66 | `const state = {...}` | global state (§5) |
| full.js:68 | `function upsertEntry(list, entry, limit)` | insert/update/cap entry |
| full.js:80 | `function renderSessionStatus()` | session pill/dots, button states |
| full.js:138 | `function renderCaptureNote()` | "Following your screen" banner |
| full.js:148 | `function renderConnectionBanner()` | backend connectivity banner |
| full.js:179 | `function renderMeetingStatus()` | selected meeting target label |
| full.js:192 | `const BANNER_LABELS = {...}` | orb/banner state→label map |
| full.js:199 | `function renderListenBanner()` | "listening/private talk" banner |
| full.js:225 | `function renderDevices()` | mic/VB-Cable/output device rows |
| full.js:256 | `function findSourceForTarget(t)` | matches target→screen source |
| full.js:269 | `function renderMeetingTargets()` | meeting picker w/ thumbnails |
| full.js:331 | `function _fmtTime(ts)` | timestamp formatting |
| full.js:337 | `function renderEntryList(container, entries, emptyText)` | generic transcript list render |
| full.js:372 | `function renderPairedAsks(container, entries, emptyText)` | Private AI Asks Q&A pairing |
| full.js:436 | `function renderResearchPanel()` | market research panel |
| full.js:520 | `function renderAll()` | master re-render |
| full.js:534-641 | `channel.onmessage = (ev) => {...}` | BroadcastChannel handler from overlay (§4) |
| full.js:643 | `function showPrivacyMicWarning(message)` | dismissable privacy banner |
| full.js:674-684 | Start/Pause/Resume/End handlers | post `COMMAND_*_SESSION` to channel |
| full.js:688 | `async function refreshTargets()` | fetches meeting targets + screen sources |
| ~725 | `(function setupAudioMixCard())` IIFE | AI volume slider/auto-duck card |
| ~882 | `function _initials(email)` / `_shortEmail(email)` | avatar/email formatting |
| full.js:897 | `async function setupUserProfile()` | loads auth, renders profile, wires logout |
| full.js:957 | `async function handleLogout()` | `companionBridge.logout()`, resets UI |
| full.js:988 | `let _fullAuthTokens = null` | cached JWT tokens |
| full.js:989 | `const FULL_SHARED_TOKEN` | `companionConfig.token` fallback |
| full.js:991 | `async function _ensureAuthLoaded()` | lazy-loads `_fullAuthTokens` |
| full.js:997 | `async function _getAuthHeader()` | builds Authorization/X-Companion-Token header |
| full.js:1006 | `async function _refreshAuth()` | `POST /auth/refresh` |
| full.js:1030 | `function startReadinessPolling()` | polls `/api/ready` (1s then 5s) — owns `backendReady`/`wsConnected` |
| ~1080-1110 | `(function setupOnboarding())` IIFE | onboarding modal w/ localStorage dismiss |
| ~1130-1428 | `(function setupSettingsPage())` IIFE | BYOK Settings tab (provider/model dropdowns, key fields, save/refresh) |

### 3. IPC channel usage
| Line | Call | Purpose |
|---|---|---|
| full.js:899 | `companionBridge.getAuth()` | retrieve stored JWT in `setupUserProfile` |
| full.js:967 | `companionBridge.logout()` | clear auth on logout |
| full.js:989 | `companionConfig.token` | fallback shared companion token |
| full.js:993 | `companionBridge.getAuth()` | lazy auth load |
| full.js:1018 | `companionBridge.setAuth(_fullAuthTokens)` | persist refreshed tokens |
| full.js:1395-1396 | `companionBridge.setProviderConfig(patch)` | persist BYOK provider config |
| (in `refreshTargets`, ~688+) | `bridge.listMeetingTargets()` / `bridge.getScreenSources()` | meeting picker data |

### 4. Message types / HTTP endpoints
**HTTP (fetch to `BACKEND_HTTP`)**:
| Line | Endpoint | Purpose |
|---|---|---|
| full.js:1010 | `POST /auth/refresh` | refresh JWT |
| full.js:1040 | `GET /api/ready` (no-store) | readiness poll — authoritative `backendReady`/`wsConnected` |
| full.js:1150 | `/api/providers/*` (generic `api()` helper) | Settings tab, 401→refresh→retry |

**BroadcastChannel outgoing (full→overlay)**:
| Line | Type |
|---|---|
| full.js:674 | `COMMAND_START_SESSION` |
| full.js:677 | `COMMAND_PAUSE_SESSION` |
| full.js:680 | `COMMAND_RESUME_SESSION` |
| full.js:683 | `COMMAND_END_SESSION` |
| full.js:703, 714 | `REQUEST_STATE` |
| full.js:754 | `COMMAND_SET_AUDIO_MIX` `{aiVolume, autoDuck}` |
| full.js:852 | `COMMAND_SET_LANGUAGE` |

**BroadcastChannel incoming (overlay→full)** in `channel.onmessage` (full.js:535-641):
| Line | Type | Purpose |
|---|---|---|
| full.js:538 | `STATE_SNAPSHOT` | bulk sync |
| full.js:577 | `CONVERSATION_ENTRY` | live transcript token (skips `speaker==="ai"`) |
| full.js:591 | `PRIVATE_ENTRY` | Private AI Ask Q&A |
| full.js:597 | `RESEARCH_STARTED` | market research started |
| full.js:603 | `RESEARCH_COMPLETE` | research result |
| full.js:618 | `RESEARCH_FAILED` | research error |
| full.js:624 | `DEGRADED` | capture/session degraded |
| full.js:629 | `START_BLOCKED` | overlay refused Start (`payload.reason`) |
| full.js:637 | `PRIVACY_SETUP_NOTE` | privacy method setup guidance |
| ~769-865 | `AUDIO_MIX_STATE`, `LANGUAGE_ACK` | mix/language sync (chained `prev` handler) |

### 5. Global `state` (full.js:43-66)
`sessionLive`, `sessionStarting`, `sessionPaused`, `backendReady`, `wsConnected`, `backendStatusMessage`, `holdActive`, `meetingTitle`, `selectedTarget`, `selectedSourceId`, `meetingTargets`, `screenSources`, `conversationEntries`(cap 80), `privateEntries`(cap 40), `researchEntries`(cap 20), `researchActive`, `researchActiveQuery`, `listeningDeviceId`, `vbCableDeviceId`, `privacyStrategy`, `selectedMicLabel`, `orbState`. `captureFollowingScreen` is added dynamically (not in initial literal) via `STATE_SNAPSHOT` handler (full.js:552).

### 6. Gotchas
- full.js:542-544 — **NOTE**: `backendReady`/`wsConnected` deliberately NOT overwritten by `STATE_SNAPSHOT` — owned solely by `startReadinessPolling()` since relayed snapshots can be stale.
- full.js:880 — profile rendering silently no-ops if `getAuth()` returns falsy.
- full.js:637-639 — `PRIVACY_SETUP_NOTE` relies on overlay sending it once; full.js does no dedup beyond the warning banner.
- HANDOFF.md:496 — cross-file race: 8s ask-window orphan timer in `negotiation_engine` vs ~18s native-audio answer arrival → some advisor-tagged AI answers never populate `privateEntries`.
- HANDOFF.md:2427 — transcript/private lists do brute-force `innerHTML=""` rebuilds on every token (perf concern, not yet fixed).

### 7. Backend URL config
- full.js:989 — `FULL_SHARED_TOKEN = companionConfig.token || ""`
- full.js:1008, 1031, 1111 — `BACKEND_HTTP = companionConfig.http || "http://localhost:8000"` (re-derived per usage site)
- full.js never reads `companionConfig.ws` — no WS of its own.

---

## app.js (LEGACY)
`/home/user/fix-nego/desktop/src/renderer/app.js` (1017 lines)

### 1. Purpose / status
Renderer for the legacy single-window UI (`index.html`), predating the overlay+full split. **Confirmed NOT loaded by main.js** — `main.js` only `loadFile`s `overlay.html`(1096), `full.html`(1119), `login.html`(1169); `index.html`/`app.js` never appear (HANDOFF.md:339, 990, 2670 corroborate "intentionally left untouched"/"for future use"). Multiple agents have kept hardcoded-URL/perf fixes mirrored here "for future use," but it is drifting — `app.js:997` calls `bridge.getWindowMode()`, which **does not exist** in `preload.js`'s `companionBridge` (would throw if ever loaded).

### 2. Top-level functions/sections
| Line | Symbol | Description |
|---|---|---|
| 9 | `const state = {...}` | global state (session, prefs, ws, audio, UI entries) |
| 40 | `const elements = {...}` | cached DOM refs |
| 70 | `const BACKEND_WS_URL` | `companionConfig.ws` or localhost fallback |
| 72 | `const BACKEND_TOKEN` | `companionConfig.token` |
| 73 | `function backendWsUrl()` | appends `?token=`/`&token=` |
| 79 | `function loadPrefs()` | loads `negotiation_companion_prefs_v2` from localStorage |
| 93 | `function savePrefs()` | persists prefs |
| 101 | `function log(message, extra)` | console logging |
| 107 | `function setMiniStatus(text)` | compact-mode status |
| 111 | `function setExpandedStatus(element, text)` | expanded-mode status |
| 115 | `function describeMeetingTarget(target)` | label formatting |
| 122 | `function isVirtualRouteDevice(label)` | VB-Cable detection |
| 132 | `function arrayBufferToBase64(buffer)` | audio encoding |
| 141 | `function int16BufferFromFloat32(channelData)` | PCM conversion |
| 150 | `function closeMenus()` | closes dropdowns |
| 157 | `function setWindowMode(mode)` | compact/expanded switch |
| 166 | `function updateOverlayState()` | overlay shell CSS classes |
| 171 | `function updateTargetUi()` | selected target UI |
| 181 | `function renderPicker(...)` | generic dropdown renderer |
| 204 | `function renderMeetingPickers()` | meeting target picker |
| 238 | `function renderOutputPickers()` | audio output device pickers |
| 275 | `function renderMiniThread()` | compact conversation snippet |
| 294 | `function renderFullTranscript()` | full transcript |
| 327 | `function renderPrivateThread()` | private/AI thread |
| 362 | `function pushConversationEntry(entry)` | append to conversation log (cap 80) |
| 368 | `function pushPrivateEntry(entry)` | append to private log (cap 40) |
| 374 | `async function ensurePlayback()` | AudioContext setup for AI playback |
| 390 | `async function playPcmChunk(arrayBuffer)` | plays PCM chunk |
| 404 | `function safeSendControl(type, payload)` | WS send with readyState guard |
| 416 | `async function sendProviderConfig()` | sends BYOK config on connect |
| 435 | `function sendControl(type, payload)` | direct `state.ws.send(...)` |
| 441 | `function createPcmCapture(stream, messageType, opts)` | mic/system audio→PCM chunks |
| 493 | `async function connectBackend()` | opens WS, registers `onmessage` |
| 580 | `function handleTranscriptUpdate(payload)` | `TRANSCRIPT_UPDATE` handling |
| 610 | `async function loadMeetingTargets()` | fetches meeting windows via IPC |
| 632 | `async function loadAudioDevices()` | enumerates devices |
| 664 | `async function bindSelectedTarget()` | binds via IPC |
| 672 | `async function configureMicForward(stream)` | mic→virtual cable forward |
| 688 | `async function reportCaptureHealth(overrides)` | reports health to main |
| 720 | `async function stopMeetingCapture()` | stops capture |
| 731 | `async function startMeetingCapture()` | starts capture, calls `connectBackend()`(736) |
| 786 | `async function startSession()` | starts session, `connectBackend()`(799), `sendControl("START_NEGOTIATION",...)`(819) |
| 847 | `async function setHoldState(active, source)` | hold-to-ask push-to-talk |
| 878 | `async function endSession()` | ends session |
| 902 | `async function maybeAutoAttach()` | auto-attach last meeting target |
| 995-1017 | `window.addEventListener("load", ...)` | init sequence |

### 3. IPC usage
- app.js:70 — `companionConfig.ws` (BACKEND_WS_URL)
- app.js:72 — `companionConfig.token` (BACKEND_TOKEN)
- app.js:418-419 — `companionBridge.getProviderConfig()` existence check + call
- app.js:997 — `bridge.getWindowMode()` — **not present in preload.js** (drift/dead code if loaded)

### 4. WS message types
- app.js:408 — `state.ws.send(JSON.stringify({type, payload}))` (`sendControl`)
- app.js:533 — `JSON.parse(event.data)` incoming
- Incoming switch (~534-609): `CONNECTION_ESTABLISHED`(535), `SESSION_STARTED`(539), `MEETING_BINDING_UPDATE`(546), `CAPTURE_HEALTH_UPDATE`(549), `DEGRADED_MODE_UPDATE`(552), `TRANSCRIPT_UPDATE`(557→`handleTranscriptUpdate`), `AI_RESPONSE`(560), `OUTCOME_SUMMARY`(568)
- Outgoing: `START_NEGOTIATION`(819), `PROVIDER_CONFIG`(416-434)

### 5. Global state (app.js:9-39)
`prefs` (windowMode, lastMeetingWindowTitle, listeningOutputDeviceId, meetingRouteOutputDeviceId), `ws`, `sessionId`, `sessionLive`, `selectedMeetingTarget`, `meetingTargets`, `meetingBinding`, `audioOutputs`, `listeningOutput`, `meetingRouteOutput`, `conversationEntries`(cap 80), `privateEntries`(cap 40), `playbackContext`, `playbackDestination`, `playbackAudioEl`.

### 6. Gotchas
- No inline NOTE/FIXME/TODO/BUG markers.
- `app.js:997` `bridge.getWindowMode()` — non-existent bridge method (API drift vs preload.js).
- HANDOFF.md:339 — if ever wired back in, needs same `ready_to_start`/BACKEND_READY gating as overlay.js/full.js.

### 7. Backend URL config
- app.js:70 — `BACKEND_WS_URL = companionConfig.ws || "ws://localhost:8000/ws"`
- app.js:72 — `BACKEND_TOKEN = companionConfig.token || ""`
- app.js:73-77 — `backendWsUrl()` appends token query param

---

## login.js
`/home/user/fix-nego/desktop/src/renderer/login.js` (75 lines)

### 1. Purpose
Renderer for the login window (`login.html`, loaded via `main.js:1169`/`createLoginWindow`). Single "Sign in/Create account" button → loopback OAuth via Clerk-hosted page; shows fallback copy-paste login URL.

### 2. Functions/sections
| Line | Function | Description |
|---|---|---|
| 6-10 | `setStatus(msg, kind)` | updates `#status` |
| 12-18 | `setLoading(loading)` | toggles button disabled/label |
| 20 | `addEventListener("click", startLogin)` | wires button |
| 24-31 | `companionBridge.onLoginUrl(...)` | listens for pushed login URL |
| 33-55 | `copyLoginUrl()` | clipboard copy w/ `execCommand` fallback |
| 57-75 | `async function startLogin()` | `startLogin()` → `loginSuccess()`, error hint about backend |

### 3. IPC usage
- login.js:24 — `companionBridge.onLoginUrl(...)` ← `companion:loginUrl` push
- login.js:61 — `companionBridge.startLogin()` → `companion:startLogin`
- login.js:63 — `companionBridge.loginSuccess()` → `companion:loginSuccess`

### 4. Backend calls
None directly — delegated to main process via IPC.

---

## HTML / CSS files
`/home/user/fix-nego/desktop/src/renderer/`

| File | Lines | Pairs with | Loaded by main.js | Purpose |
|---|---|---|---|---|
| `index.html` | 132 | `app.js` (script tag line 130), `styles.css` (line 7) | No (legacy) | Legacy single-window UI ("Negotiation Companion") |
| `overlay.html` | 143 | `overlay.js` (line 141), `overlay.css` (line 7) | Yes — `main.js:1096` | Floating orb overlay UI ("Companion Overlay"); orb, conn-dot, capture preview, meeting menu, audio mix strip, language menu, screen picker modal |
| `full.html` | 502 | `full.js` (line 500), `full.css` (line 7) | Yes — `main.js:1119` | Dashboard UI ("Negotiation Companion"); session controls, transcript/research/settings cards, onboarding modal |
| `login.html` | 169 | `login.js` (line 167), inline styles (no `<link>`) | Yes — `main.js:1169` | Sign-in window ("Sign in — Balaastra Companion") |
| `overlay.css` | 1055 | `overlay.html`/`overlay.js` | — | Overlay styling |
| `full.css` | 1828 | `full.html`/`full.js` | — | Dashboard styling |
| `styles.css` | 484 | `index.html`/`app.js` | — | Legacy UI styling |

---

## scripts/
`/home/user/fix-nego/desktop/scripts/`

| File | Lines | Purpose |
|---|---|---|
| `audio-isolator.ps1` | 717 | Persistent stdin/stdout JSON-line server (`-Sta`) implementing driverless per-process mic isolation via `IAudioPolicyConfig`/`IPolicyConfig` COM. Commands: `init`, `enumerate`, `pid-from-hwnd`, `probe`, `redirect`, `restore`, `set-visibility`, `send-keys`, `exit`. Invoked by `main.js` via `helperCmd()`/`startPrivacyHelper()`. |
| `global-hold-listener.ps1` | 62 | Add-Type C# `GetAsyncKeyState` wrapper for global hold-key detection |
| `install-vbcable.ps1` | 36 | Downloads/installs VB-CABLE driver pack (legacy vbcable strategy) |

Packaged as `extraResources` in `package.json` (`scripts/audio-isolator.ps1` → `scripts/audio-isolator.ps1`); resolved at `main.js:133-135` (`process.resourcesPath` when packaged, `__dirname/../scripts` in dev).

## build/
`/home/user/fix-nego/desktop/build/` — `icon.ico`, `icon.png` (Windows NSIS installer/app icons, referenced in `package.json` `build.win.icon` and `build.nsis`).

---

## package.json
`/home/user/fix-nego/desktop/package.json`

- `name`: `ai-negotiation-copilot-desktop`, `main`: `src/main.js`
- Scripts: `start`/`dev` = `electron .`; `pack` = `electron-builder --dir`; `dist` = `electron-builder`
- `build.appId`: `com.balaastra.negotiationcompanion`, `productName`: "Negotiation Companion"
- `build.files`: `src/**/*`, `package.json`
- `build.extraResources`: `scripts/audio-isolator.ps1` → `scripts/audio-isolator.ps1`
- `build.win.target`: `nsis`, icon `build/icon.ico`
- devDependencies: `electron ^31.0.0`, `electron-builder ^24.13.3`
- dependencies: `application-loopback ^1.2.6` (native process-loopback audio capture, optional — wrapped in try/catch in main.js), `dotenv ^16.6.1` (loads `desktop/.env` for backend config in dev)

---

## Cross-File Architecture Summary
- **Window→renderer**: `overlay.html`↔`overlay.js` (orb, owns WS), `full.html`↔`full.js` (dashboard, no WS), `login.html`↔`login.js` (auth), `index.html`↔`app.js` (legacy, unused).
- **IPC**: `preload.js` is the sole bridge — `companionConfig` (sync, backend URLs/token) + `companionBridge` (~30 methods covering capture, audio devices, BYOK provider config, auth/login, session lifecycle, hold-to-ask privacy, overlay window control).
- **Renderer↔renderer**: overlay.js and full.js communicate exclusively via `BroadcastChannel("negotiation_companion_ui")` — overlay relays backend WS events; full sends UI commands back.
- **Backend connection**: only overlay.js opens the `/ws` WebSocket (`backendWsUrl()` = `companionConfig.ws` + `?token=<JWT or shared token>`); full.js and app.js use direct HTTP `fetch` to `companionConfig.http` for auth/readiness/settings.
- **Privacy isolation**: main.js + `audio-isolator.ps1` (STA PowerShell COM helper) implement hotkey (default) / policyconfig / vbcable strategies for muting the meeting app's mic during Hold-to-Ask, driven by `companionBridge.resolvePrivacyStrategy/privacyIsolate/privacyRestore`.