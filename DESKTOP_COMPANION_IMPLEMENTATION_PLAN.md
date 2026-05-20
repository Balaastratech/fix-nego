# Windows Desktop Companion App Plan for AI Negotiation Copilot

## Summary
Build a **Windows-first desktop companion app** that runs beside Zoom, Google Meet, and Microsoft Teams while preserving the current **in-person meeting mode**.

The product will ship as **one backend + two client modes**:
- `in_person_web`: current browser-based local mic/camera workflow
- `virtual_companion_desktop`: new Windows desktop sidecar app for browser-based and native meeting apps

v1 decisions locked:
- Windows first
- Companion-only for Zoom/Meet/Teams in v1, no official platform integrations in v1
- Sidecar desktop window, not overlay-first
- Persist transcript, research, state, and metadata only; do not store raw audio/video by default
- Optimize for `1 user + 1 counterparty`
- Support both browser-based and native desktop meeting apps
- Allow an optional Windows capture helper/fallback path when built-in capture is not reliable enough
- Fastest MVP distribution: internal unsigned installer/dev build first, signed enterprise packaging later

This plan keeps the current in-person capability intact and adds a second, production-grade virtual meeting mode without forking the backend intelligence stack.

## Architecture
### Product shape
The system becomes a **multi-source conversation intelligence platform**:
- `frontend web client`: in-person mode
- `desktop shell client`: virtual companion mode
- `backend intelligence service`: shared across both modes
- `sqlite session store`: shared across both modes

### Source model
Add a formal source-mode abstraction:
- `source_mode = in_person_web | virtual_companion_desktop`

Add formal audio-source tagging:
- `audio_source = mic | system | captions | imported`

Add participant-origin tagging:
- `participant_origin = local_user | remote_counterparty | remote_unknown | ai`

### Companion-mode operating model
The desktop app privately advises the local user while they attend a Zoom/Meet/Teams meeting normally.
It does not join the meeting as a platform bot in v1.

Companion mode ingests:
- local microphone audio
- Windows system audio
- optional selected-window frames
- optional meeting captions when available later
- meeting app/window metadata

The backend then:
- transcribes with Google STT
- labels the local user and remote party
- triggers research
- generates tactical guidance with Gemini
- persists transcript and artifacts
- resumes the session after reconnects

## Implementation Changes
### 1. Desktop shell
Build a new Windows desktop app around the existing frontend.

Chosen stack:
- `Electron`
- `Electron Builder`
- `Next.js frontend loaded inside Electron`
- `preload bridge` for secure desktop APIs

Desktop app processes:
- `main process`
- `preload process`
- `renderer process`

Main process responsibilities:
- app lifecycle
- window creation
- permissions and device checks
- source selection dialogs
- capture orchestration
- local config storage
- crash reporting hooks
- update hooks placeholder
- native-helper process management if needed

Preload responsibilities:
- expose safe IPC methods to renderer
- expose meeting/window enumeration
- expose start/stop capture APIs
- expose local settings/status APIs
- no direct Node access from renderer

Renderer responsibilities:
- existing dashboard UI
- mode selection
- device status UI
- companion controls
- transcript/research/advice rendering
- privacy indicators
- history/resume UI

### 2. Preserve in-person mode
Do not replace the current browser workflow.

In-person mode remains:
- browser mic capture
- browser camera capture
- current web entrypoint
- current SpeechBrain enrollment flow
- current manual mode fallback
- current resume/persistence behavior

Needed changes:
- formalize in-person mode as one explicit source mode
- ensure desktop-specific logic does not leak into in-person web mode
- keep backend routing source-aware rather than frontend-specific

### 3. Add virtual companion mode
Add a new desktop-only source mode:
- `virtual_companion_desktop`

Companion session flow:
1. User opens desktop app
2. User selects `Virtual Meeting`
3. App checks:
   - backend reachable
   - mic permissions
   - system audio availability
   - optional capture helper availability
4. User selects active meeting source
   - browser tab/window or native app window
5. App starts:
   - mic capture
   - system audio capture
   - optional frame capture
6. Companion starts backend session with `source_mode=virtual_companion_desktop`
7. UI shows live advice, transcript, research, and status
8. Session remains active until user explicitly ends it

### 4. Audio capture architecture
Companion mode needs separate capture paths:
- `MicCaptureAdapter`
- `SystemAudioCaptureAdapter`
- `WindowFrameCaptureAdapter`
- optional `CaptureHelperAdapter`

#### Mic capture
Use standard desktop audio input capture.
Requirements:
- selectable input device
- live level meter
- mute/unmute handling
- device disconnect recovery
- AEC/noise-suppression options where available
- low-latency PCM output normalized to backend expectations

#### System audio capture
Primary goal:
- capture remote meeting audio from Zoom/Meet/Teams

Plan:
- primary Windows built-in capture path
- fallback helper path if built-in capture is insufficient on some machines

The app must explicitly support:
- browser meeting tabs
- native Zoom desktop app
- native Teams desktop app
- Meet in Chrome/Edge
- PWA/native wrapper cases when they appear as windows

System audio responsibilities:
- enumerate capturable windows/sources
- allow user to select the active meeting source
- stream normalized PCM to backend
- detect silence / source failure
- rebind to a different meeting source when the user switches windows

#### Echo and bleed handling
The user explicitly wants support for both speakers and headphones.
v1 therefore must support both, but with clear quality tiers:

- `best quality`: headset mode
- `supported but lower certainty`: laptop speakers mode

Controls and mitigations:
- enable AEC where possible on mic capture
- add “headset mode” and “open-speaker mode” presets
- in open-speaker mode:
  - raise ambiguity thresholds
  - bias toward `remote_unknown` rather than false attribution
  - expose a visible warning that speaker certainty is reduced
- never silently pretend laptop-speaker mode is as accurate as headset mode

### 5. Meeting detection and source control
Add a `MeetingPresenceDetector` in desktop mode.

Responsibilities:
- detect candidate active meeting windows
- identify common apps:
  - Zoom
  - Google Meet in Chrome/Edge
  - Microsoft Teams
- expose source candidates to UI
- show current bound source
- detect source closure or change
- trigger degraded mode if source disappears

v1 detection strategy:
- window title matching
- executable/process heuristics
- browser tab title hints where available through capture surface labels
- manual override always available

### 6. Backend session model changes
Extend the session model with explicit companion-mode fields.

Add:
- `source_mode`
- `audio_sources_active`
- `capture_preset`
- `meeting_platform_hint`
- `meeting_window_title`
- `meeting_process_name`
- `local_user_identity_mode`
- `remote_party_identity_mode`
- `capture_helper_active`
- `companion_quality_mode`
- `device_status_snapshot`

State model additions:
- `advisor_reconnecting`
- `stt_reconnecting`
- `capture_degraded`
- `manual_only`
- `source_missing`

Companion-specific session invariants:
- the session remains alive until user ends it
- disconnect of frontend renderer must not destroy session immediately
- desktop reconnect must restore transcript, research, speaker state, and companion status
- meeting source loss enters degraded mode, not full session death

### 7. Speaker and participant logic by mode
Do not force the in-person speaker policy onto virtual meetings.

#### In-person mode
Keep:
- Google STT finalized turns
- SpeechBrain user binding
- second speaker -> counterparty
- ambiguity -> unknown
- manual override available

#### Companion mode
Use source-aware participant logic:

**Local mic turns**
- default identity = `user`
- no need to re-prove every turn with SpeechBrain
- SpeechBrain remains available for initial voice enrollment/verification if desired, but is not the primary classifier for every local turn in companion mode

**System audio turns**
- if one clear remote participant is present, label `counterparty`
- if mixed or uncertain remote speech, label `remote_unknown`
- do not falsely force remote turns into the enrolled `user` class
- if future platform caption/identity metadata exists, it can override generic `counterparty`

Companion-mode default:
- source-origin is stronger than SpeechBrain for local-vs-remote separation
- SpeechBrain remains a local-user verifier and fallback, not the main remote-party classifier

### 8. Enrollment policy
Keep enrollment capability but make it mode-aware.

In-person mode:
- keep current live quality-gated enrollment

Companion mode:
- enrollment is optional but supported
- user may enroll once on desktop device for local-user verification
- if companion mode runs without enrollment:
  - local mic still maps to `user` by source
  - remote system audio maps to `counterparty` or `remote_unknown`
- if enrollment exists:
  - use it for stronger user verification and conflict detection
  - never let remote system audio falsely rebind as user

### 9. Transcription and routing
Backend routing must become source-aware.

Each utterance must carry:
- `source_mode`
- `audio_source`
- `speaker`
- `language`
- `speaker_confidence`
- `transcription_confidence`
- `eligible_for_context`
- `eligible_for_research`
- `meeting_platform_hint`

Routing rules:
- `mic` audio contributes to user-side transcript
- `system` audio contributes to remote-side transcript
- `ask_ai` interactions remain separate from negotiation transcript
- AI response transcript remains in advisor channel

### 10. Multilingual behavior
Launch languages remain:
- `en-US`
- `hi-IN`
- `es-US`

Companion-mode language policy:
- detect dominant session language from turns
- default advisor response to dominant language
- allow manual response-language override from desktop UI
- persist language per turn and per session
- mixed-language turns are accepted
- Gujarati and Arabic remain out of v1 auto-speaker guarantees

### 11. Vision in companion mode
The desktop app must make vision real, not optional-only UI.

Companion-mode vision use cases:
- inspect the selected meeting window region
- read visible product/document/package text
- read visible listing details or pricing from shared screen
- support negotiation-relevant object/document context
- explicitly avoid people analytics as a product feature

Desktop frame capture plan:
- capture frames only when vision is enabled
- user chooses the target source/window
- send frames at controlled interval
- persist only derived observations and metadata, not raw continuous video

Persist:
- timestamp
- source window hint
- observation summary
- confidence/status
- no raw frame storage by default

### 12. Persistence
Use SQLite as the durable local session store.

Persist:
- sessions
- turns
- research events
- advisor events
- speaker-mapping events
- vision events
- state snapshots
- companion device/capture metadata

Do not persist raw media by default.

Session history must support:
- reconnect restore
- explicit past-session reopening
- transcript review
- research review
- AI advice timeline
- state/debug review

Companion-specific persisted fields:
- meeting platform hint
- selected source window metadata
- capture mode
- device mode
- language
- response language
- degraded-mode transitions

### 13. UI/UX
#### Mode selection
At startup:
- `In Person`
- `Virtual Meeting Companion`

#### Companion session UI
Add:
- meeting source selector
- mic device selector
- capture preset selector
- system audio status
- capture-helper status
- session language
- response language selector
- live privacy indicator
- persisted history panel
- degraded-mode banner
- reconnect status
- source-loss warning
- companion quality warning when using speakers

#### Sidecar layout
v1 uses:
- fixed sidecar window
- resizable
- minimizable
- always reopenable
- no overlay-first requirement

Recommended sections:
- session control
- capture status
- transcript
- advisor output
- research panel
- session history
- device/quality status

### 14. WebSocket and IPC interfaces
#### Backend WebSocket additions
Use and extend:
- `SESSION_RESUME`
- `SESSION_RESTORED`
- `PERSISTENCE_STATUS`
- `VISION_STATUS`
- `LANGUAGE_UPDATE`
- `DEGRADED_MODE_UPDATE`

Add companion-specific messages:
- `SOURCE_MODE_START`
- `CAPTURE_STATUS`
- `SOURCE_BOUND`
- `SOURCE_LOST`
- `DEVICE_STATUS`
- `QUALITY_MODE_UPDATE`
- `MEETING_PLATFORM_DETECTED`

#### Desktop preload IPC
Expose:
- `listAudioInputs()`
- `listCaptureSources()`
- `startMicCapture(config)`
- `stopMicCapture()`
- `startSystemCapture(config)`
- `stopSystemCapture()`
- `startFrameCapture(config)`
- `stopFrameCapture()`
- `getMeetingCandidates()`
- `setCompanionPreset(mode)`
- `getCaptureDiagnostics()`
- `startHelper()`
- `stopHelper()`

### 15. Desktop packaging and distribution
v1 packaging:
- Electron Builder
- Windows output:
  - dev unpacked build
  - internal NSIS installer
- code-signing deferred to post-MVP pilot stage

This is the fastest path and matches the user’s MVP preference.

Post-MVP plan:
- signed installer
- enterprise deployment options
- auto-update
- policy controls

### 16. Security and privacy
v1 privacy posture:
- visible capture indicator at all times
- explicit mode switch between in-person and companion
- transcript/research persistence only
- no raw media persistence by default
- explicit user-controlled session end
- clear source labels for captured streams
- minimal local metadata storage required for resume/history

Desktop security requirements:
- renderer isolation
- preload-only native access
- no direct Node APIs in renderer
- strict IPC validation
- local config separation from transcript DB
- helper binary integrity checks if helper is used

### 17. Reliability and degraded modes
Companion mode must degrade gracefully.

Degraded modes:
- `advisor_reconnecting`
- `stt_reconnecting`
- `capture_degraded`
- `source_missing`
- `manual_only`

Failure handling:
- backend disconnect -> reconnect and restore session
- renderer crash -> reopen and resume session
- meeting source disappears -> prompt rebind, keep session alive
- mic disconnect -> degraded mode with retry/reselect
- system audio capture fails -> prompt fallback helper or rebinding
- SpeechBrain unavailable -> continue with source-based user/remote attribution where possible
- vision failure -> disable vision only, not whole session

### 18. Observability
Add structured metrics for:
- first speech detection latency
- first partial transcript latency if available
- finalized-turn latency
- advisor response start latency
- reconnect count
- source rebinding count
- capture helper activation count
- local-vs-remote turn counts
- ambiguous turn counts
- language distribution
- meeting platform detection frequency

Add logs for:
- source bind/unbind
- device changes
- degraded-mode transitions
- resume/restore
- capture mode used
- headset vs speakers mode
- fallback-helper path use

### 19. Repository structure changes
Add a new desktop app workspace:
- `desktop/`
- `desktop/main/`
- `desktop/preload/`
- `desktop/helpers/` if helper is included
- `desktop/build/`

Keep:
- `frontend/` as shared renderer app
- `backend/` as shared intelligence service

Introduce a shared protocol/types layer if needed:
- `shared/` for desktop/frontend/backend protocol contracts

### 20. Execution phases
#### Phase 1: foundation
- introduce `source_mode`
- make backend source-aware
- finalize protocol types
- keep in-person mode stable

#### Phase 2: desktop shell
- Electron app
- preload bridge
- sidecar window
- local app lifecycle
- source selection UI

#### Phase 3: capture stack
- mic capture
- system audio capture
- frame capture
- source binding
- quality presets

#### Phase 4: companion backend behavior
- mode-aware routing
- mode-aware speaker logic
- persistence extensions
- degraded-mode transitions
- reconnect/resume hardening

#### Phase 5: enterprise MVP hardening
- installer build
- privacy indicators
- diagnostics
- session history polish
- pilot readiness

## Important Public Interfaces and Types
### Session model
Add or formalize:
- `source_mode`
- `audio_sources_active`
- `meeting_platform_hint`
- `companion_quality_mode`
- `capture_helper_active`
- `language`
- `response_language`
- `degraded_mode`

### Transcript turn model
Each persisted/displayed turn must include:
- `id`
- `speaker`
- `text`
- `timestamp`
- `language`
- `source_mode`
- `audio_source`
- `speaker_confidence`
- `transcription_confidence`
- `source`
- `eligible_for_context`
- `eligible_for_research`

### Desktop renderer API
Expose typed capture and diagnostics APIs through preload only.

### WebSocket protocol
Add companion-mode control and status events listed above, while preserving current in-person protocol.

## Test Plan
### Unit tests
- source-mode routing
- local-vs-remote turn classification
- degraded-mode transitions
- session restore logic
- persistence schema and history retrieval
- response-language routing
- source bind/unbind behavior

### Desktop integration tests
- mic capture start/stop
- system audio capture start/stop
- source selection and rebinding
- frame capture enable/disable
- sidecar reopen/resume
- helper fallback activation path

### Backend integration tests
- in-person mode unchanged
- companion mode source-aware transcript routing
- SpeechBrain optional verification in companion mode
- resume after disconnect
- persistence/history replay
- language updates
- research persistence

### End-to-end scenarios
- Zoom in browser with headset
- Zoom desktop app with headset
- Meet in Chrome with headset
- Teams desktop app with headset
- browser and native meeting apps with laptop speakers
- source loss and rebind during active session
- backend reconnect during active session
- renderer restart during active session
- vision on/off during meeting
- response language switched mid-session

### Acceptance criteria
- in-person mode still works with current web flow
- virtual companion mode works on Windows for browser and native meeting apps
- transcript/research/advice persist and restore after reconnect
- companion session remains active until user ends it
- headset mode is production-ready
- speaker mode with laptop speakers is supported but clearly lower-certainty
- no raw media is stored by default
- system degrades visibly instead of silently failing or mislabeling speakers

## Assumptions and Defaults
- Windows is the only supported OS in v1
- v1 is companion-only for Zoom/Meet/Teams; official platform integrations are explicitly deferred
- v1 distributes as an internal MVP installer/dev build before signed enterprise packaging
- transcript/research/state persistence is enabled by default; raw media persistence is disabled by default
- companion mode is optimized for 1 user + 1 counterparty
- browser-based and native desktop meeting apps must both work in v1
- capture helper fallback is allowed if built-in Windows capture is insufficient on some machines
- headset mode is the preferred accuracy path; speaker mode is supported with lower-certainty safeguards

## External constraint references used for this plan
- Electron desktop capture and audio caveats: [Electron desktopCapturer](https://www.electronjs.org/docs/latest/api/desktop-capturer)
- Browser display/audio capture limitations: [MDN getDisplayMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia)
- Google Meet add-ons: [Meet add-ons quickstart](https://developers.google.com/workspace/meet/add-ons/guides/quickstart)
- Google Meet Media API preview restrictions: [Meet Media API get started](https://developers.google.com/workspace/meet/media-api/guides/get-started)
- Zoom Meeting SDK external-meeting authorization constraints: [Zoom Meeting SDK for Windows](https://developers.zoom.us/docs/meeting-sdk/windows/get-started/download/)
- Zoom meeting-content controls and automated tools visibility: [Zoom Meetings API](https://developers.zoom.us/docs/api/meetings/), [Zoom automated tools controls](https://library.zoom.com/zoom-workplace/zoom-meetings/securing-zoom-meetings-explainer/manage-automated-tools-and-participants-in-your-zoom-meetings)
- Teams meeting/calling bot and real-time media constraints: [Teams calls and meetings bots overview](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/calls-and-meetings/calls-meetings-bots-overview), [Teams real-time media concepts](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/calls-and-meetings/real-time-media-concepts)
