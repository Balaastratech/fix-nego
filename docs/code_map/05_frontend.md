I'll analyze the frontend codebase systematically. Let me start by exploring the structure and reading the key files.

Now let me read the core files in parallel.

Now let's read the hooks and lib files (the largest, most important ones).

Now let's read useAskAI, useEnrollment, websocket.ts, audio-worklet-manager.ts, and the lib/types file.

There's a `lib/types` import in useNegotiation.ts but no types.ts file found. Let me check.

The `lib/types` import doesn't exist as a separate file - let me check if it's actually missing or aliased somewhere (might be a build error / TODO).

Confirmed: `frontend/lib/types.ts` does NOT exist, but `useNegotiation.ts:4-12` imports `NegotiationState, INITIAL_NEGOTIATION_STATE, TranscriptEntry, Strategy, OutcomeSummary, ServerMessageType, WebSocketMessage` from `'../lib/types'`. This is a broken import / missing file - important gotcha to note. Let me verify by checking if the build actually fails or if there's a HANDOFF note about this.

Confirmed missing - this is a critical gotcha (likely build-breaking, or there's a `.gitignore`'d generated file). Now let's read the components in parallel - the dashboard, state card, and video capture first since they're large.

Note: `NegotiationDashboard` does NOT render `VideoCapture` - it's not imported. Now let's read the remaining smaller components in parallel batches.

Note: StrategyPanel.tsx is also imported from `lib/types` (Strategy type) - not used by NegotiationDashboard but may be a legacy/orphaned component. Let's check usages. Now read the rest of components.

Now let me check the public worklets/scripts and check for which components are unused (StrategyPanel, ManualSpeakerSelector, StateDebugPanel, VideoCapture).

Confirmed StrategyPanel, ManualSpeakerSelector, StateDebugPanel, and VideoCapture are all unused/orphaned (no imports found anywhere). Now I have everything needed. Let me do a final check on `.test.tsx`/`.example.tsx` files briefly and grep for ServerMessageType / WebSocketMessage usage to confirm types referenced.

`frontend/lib/types.ts` has never existed in git history — confirmed this is a genuinely missing file referenced by 4+ files. This is the most critical gotcha. Now I have all the information needed to produce the reference map.

---

# Frontend Reference Map: AI Negotiation Copilot (`/home/user/fix-nego/frontend`)

## CRITICAL GOTCHA (read first)

**`frontend/lib/types.ts` does NOT exist** (confirmed: not in filesystem, not in git history). It is imported by:
- `hooks/useNegotiation.ts:4-12` — imports `NegotiationState, INITIAL_NEGOTIATION_STATE, TranscriptEntry, Strategy, OutcomeSummary, ServerMessageType, WebSocketMessage`
- `hooks/useNegotiation.test.ts:4` — imports `TranscriptEntry`
- `components/negotiation/NegotiationDashboard.tsx:2,30` — imports `NegotiationState`, `TranscriptEntry`
- `components/negotiation/NegotiationStateCard.tsx:7` — imports `TranscriptEntry`
- `components/negotiation/TranscriptPanel.tsx:2` — imports `TranscriptEntry`
- `components/negotiation/StrategyPanel.tsx:2` — imports `Strategy`

This is a build-breaking missing module. Any session fixing TS build errors should start here — likely needs to be reconstructed (types: `NegotiationState` with fields `isConnected, consentGiven, isNegotiating, sessionId, transcript, strategy, outcome, error, aiDegraded, aiState, copilotActive, responseMode, aiLiveTranscription, language, responseLanguage, persistenceReady, degradedMode, enrollmentState, enrollmentCountdown, enrollmentError, enrollmentProgress, enrollmentFeedback, speakerMode, visionIntel, isAudioActive, isVisionActive` — inferred from reducer in `useNegotiation.ts:70-176` and dashboard usage; `TranscriptEntry` fields inferred from `useNegotiation.ts:307-319`; `Strategy` fields inferred from `StrategyPanel.tsx:21-29`; `OutcomeSummary` and `ServerMessageType`/`WebSocketMessage` are referenced but their shape only loosely constrained — `WebSocketMessage` needs `{ type: string, payload: unknown }`).

---

## Component tree (NegotiationDashboard composition)

```
app/page.tsx (Home)
├── EnrollmentModal                    (components/enrollment/EnrollmentModal.tsx)
└── NegotiationDashboard               (components/negotiation/NegotiationDashboard.tsx)
    ├── PrivacyConsent                 (early return if !consentGiven)
    ├── AIStateIndicator                (top floating pill)
    ├── ResearchIndicator               (top floating pill)
    ├── ValidationErrors                (conditional banner)
    ├── SpeakerModeToggle                (inline in speaker selector card)
    ├── TranscriptPanel  x2              ("Conversation" + "AI Advisor")
    ├── NegotiationStateCard
    ├── ControlBar                       (bottom bar)
    └── AskAIButton                      (bottom bar, right side)
```

**Orphaned/unused components** (exist but not imported anywhere): `StrategyPanel.tsx`, `ManualSpeakerSelector.tsx`, `StateDebugPanel.tsx`, `VideoCapture.tsx`. All four are dead code candidates — `VideoCapture` in particular looks like a removed feature (camera/vision capture) since `NegotiationDashboard` hardcodes `isVisionActive: false` (`page.tsx:237`) and there's a `sendFrame`/`VISION_FRAME` control message in `useNegotiation.ts:515-521` with no caller.

---

## Data flow sketch

```
app/page.tsx
  ├─ useNegotiation()          → state, connect, control senders, websocket, audioManager
  │     └─ lib/websocket.ts (NegotiationWebSocket)
  │           ├─ binary frames  → AudioWorkletManager.playChunk()  (AI audio playback)
  │           └─ text/JSON      → onMessage listeners → reducer dispatch + window CustomEvents
  │     └─ lib/audio-worklet-manager.ts (AudioWorkletManager)
  │           ├─ mic capture → VAD → onChunk → ws.sendAudioChunk() (binary PCM16 @16kHz)
  │           └─ playback worklet → speaker output (PCM16 @24kHz)
  │
  ├─ useNegotiationState()     → button-triggered state (item/prices/market/transcript)
  │     (fed by window 'negotiation-transcript', 'negotiation-state-update',
  │      'market-research-*', 'negotiation-context-update' events dispatched
  │      from useNegotiation's ws message handler)
  │
  ├─ useAskAI(negotiationState, websocket, setResearchState)
  │     → sends 'ASK_ADVICE' control message bundling negotiationState
  │
  ├─ useEnrollment({ audioManager, onStartEnrollment, onSendAudioChunk, ... })
  │     → triggers ENROLLMENT_START flow via useNegotiation
  │
  └─ NegotiationDashboard(state=dashboardState, negotiationState, validationErrors, ...)
        → renders all sub-components, passing slices of state down as props
```

Backend connection: `wss://<host>:8000/ws` (or `NEXT_PUBLIC_WS_URL`), session id persisted in `localStorage['negotiation_session_id']` (`useNegotiation.ts:14, 216-223, 238, 414`).

---

## `app/page.tsx` (277 lines)

**Purpose**: Top-level client page — wires up all hooks, manages local UI state (speaker selection, enrollment modal, session lifecycle), listens for backend custom events, renders `EnrollmentModal` + `NegotiationDashboard`.

- `export default function Home()` — `page.tsx:12-277` — main page component, "use client".
- Reads env `NEXT_PUBLIC_AUTO_SPEAKER_RECOGNITION_ENABLED` (`:13-14`) and `NEXT_PUBLIC_WS_URL` (`:75`).
- Local state: `currentSpeaker`, `showEnrollmentModal`, `isSessionActive`, `isAudioActive`, `sessionResearchHistory`, `sessionVisionHistory` (`:50-65`).
- Refs: `lastSpeakerRef`, `lastSessionIdRef` (`:67-68`).
- `useEffect` connect-on-mount (`:71-78`), clear-AI-loading-on-state (`:81-85`), TRANSCRIPT_UPDATE→negotiationState wiring via `negotiation-transcript` window event (`:88-105`), backend event listeners for `negotiation-state-update`, `market-research-started`, `market-research-complete`, `negotiation-session-restored`, `negotiation-vision-status`, `negotiation-context-update` (`:108-152`).
- Handlers: `handleConsent` (`:154-163`, gates enrollment modal vs manual mode), `handleStartEnrollment`/`handleSkipEnrollment`/`handleEnrollmentComplete` (`:165-175`), auto-close enrollment modal on success after 2s (`:178-184`), session-id-change effect that calls `resetState()` and clears all session-scoped local state (`:190-208`), `handleSpeakerModeChange`, `handleStartNegotiation`, `handleEndNegotiation`, `handleToggleAudio`, `handleSpeakerSelected` (`:210-235`).
- `dashboardState` (`:237`) — spreads `state` and overrides `isNegotiating`, adds `isAudioActive`, hardcodes `isVisionActive: false`.
- Renders `EnrollmentModal` (`:241-253`) and `NegotiationDashboard` (`:254-274`) inside `<main>`.

## `app/layout.tsx` (19 lines)

**Purpose**: Next.js root layout — sets `<html lang="en">`, imports `globals.css`, exports `metadata` (title "AI Negotiation Copilot").
- `export const metadata: Metadata` — `layout.tsx:4-7`
- `export default function RootLayout({ children })` — `layout.tsx:9-19`

## `app/api/log/route.ts` (17 lines)

**Purpose**: Next.js API route — receives frontend pino logs (via `utils/logger.ts`'s `fetch('/api/log', ...)`) and `console.log`s them server-side. Currently a no-op sink (TODO: wire to real logging backend).
- `export async function POST(request: NextRequest)` — `route.ts:4-16`

---

## `utils/api.ts` (55 lines)

**Purpose**: Fetch wrapper that adds `X-Correlation-ID` header and logs request/response via `logger`.
- `export const instrumentedFetch = async (input, init) => Promise<Response>` — `api.ts:3-54`
  - Generates `correlationId` via `crypto.randomUUID()`, logs "API Request"/"API Response"/"API Request Failed".
  - Note: clones response and calls `.json()` unconditionally (`:29-30`) — will throw/break for non-JSON responses (gotcha).
  - Not currently imported/used anywhere observed besides itself — verify before removing.

## `utils/logger.ts` (29 lines)

**Purpose**: Browser-side `pino` logger configured to POST every log entry to `/api/log` via `fetch(..., { keepalive: true })`.
- `export default logger` — `logger.ts:3-26,28`
- `level` = `'info'` in production, `'debug'` otherwise (`:25`).
- Every single `logger.debug/info/error` call across the app triggers a network POST — potential performance/log-volume concern (gotcha), especially since `lib/websocket.ts` logs every message.

---

## `lib/websocket.ts` (189 lines)

**Purpose**: `NegotiationWebSocket` class — bridges browser WebSocket to `AudioWorkletManager`, separates binary PCM frames (audio) from JSON text frames (control/state messages).

- `export class NegotiationWebSocket` — `websocket.ts:12-189`
  - `constructor(url, audioManager)` — `:22-32` — wires `onPlaybackStopped` callback to send `AI_PLAYBACK_DONE`.
  - `get isConnected` / `get isConnecting` — `:34-40`
  - `connect(): Promise<void>` — `:42-110` — opens WS, sets `binaryType='arraybuffer'`, routes `onmessage`: binary→`audioManager.playChunk()`, text→`JSON.parse` → `messageListeners`.
  - `disconnect(): void` — `:112-121`
  - `sendAudioChunk(buffer: ArrayBuffer): void` — `:126-134` — sends raw 16kHz Int16 PCM binary frame.
  - `sendControl(type: string, payload: any): void` — `:139-154` — sends `{type, payload}` JSON. Has verbose `console.log` for every non-`VISION_FRAME` message (gotcha: noisy).
  - `sendUtteranceEnd(payload)` — `:156-164` — wraps `sendControl('UTTERANCE_END', payload)`.
  - `onMessage/onClose/onError(listener)` — `:166-179` — return unsubscribe functions.
  - `resumeAudioContexts(): Promise<void>` — `:184-188` — calls `audioManager.resumeContexts()`.

### Outbound message types sent via `sendControl`/`sendAudioChunk` (grep across hooks/lib)
- `AI_PLAYBACK_DONE` (websocket.ts:28)
- `PRIVACY_CONSENT_GRANTED` (useNegotiation.ts:475)
- `START_NEGOTIATION` (useNegotiation.ts:500)
- `END_NEGOTIATION` (useNegotiation.ts:507)
- `VISION_FRAME` (useNegotiation.ts:516, unused caller — `sendFrame` not invoked from page.tsx)
- `SPEAKER_IDENTIFIED` (useNegotiation.ts:546)
- `START_COPILOT` (useNegotiation.ts:554)
- `USER_ADDRESSING_AI` (useNegotiation.ts:562)
- `ENROLLMENT_START` (useNegotiation.ts:606)
- `SPEAKER_MODE_CHANGE` (useNegotiation.ts:621)
- `SET_RESPONSE_LANGUAGE` (useNegotiation.ts:626)
- `UTTERANCE_END` (websocket.ts:163, called from useNegotiation.ts:490)
- `ASK_ADVICE` (useAskAI.ts:64) — bundles `state: { item, seller_price, target_price, max_price, market_data, transcript }`
- Binary: raw PCM16 audio chunks via `sendAudioChunk` (mic capture + enrollment audio)

---

## `lib/audio-worklet-manager.ts` (528 lines)

**Purpose**: `AudioWorkletManager` — manages microphone capture (with browser VAD via `@ricky0123/vad-web`/Silero ONNX), PCM16 resampling to 16kHz, and audio playback at 24kHz via AudioWorklets. Handles utterance segmentation, pre-speech buffering, VAD bypass mode (for enrollment / push-to-talk).

Exported types/classes:
- `export type Speaker = 'USER' | 'COUNTERPARTY'` — `:3`
- `export type CaptureState = 'idle'|'starting'|'capturing'|'stopping'|'error'` — `:5`
- `export type PlaybackState = 'idle'|'initializing'|'ready'|'error'` — `:6`
- `export interface AudioManagerConfig` — `:8-13` (silenceDebounceMs, captureSampleRate=16000, playbackSampleRate=24000, vadOptions)
- `export interface CaptureCallbacks` — `:15-29` (onChunk, onSilence, onSpeech, onUtteranceStart, onUtteranceEnd, onStateChange, onError)
- `export interface PlaybackCallbacks` — `:31-34` (onPlaybackStarted, onPlaybackStopped)
- `export class AudioManagerError extends Error` — `:36-45`
- `export enum AudioErrorCode` — `:47-55` (CONTEXT_CREATION_FAILED, WORKLET_LOAD_FAILED, MIC_ACCESS_DENIED, CAPTURE_NOT_STARTED, PLAYBACK_NOT_INITIALIZED, INVALID_STATE, CONTEXT_SUSPENDED)
- `export class AudioWorkletManager` — `:57-520`

Key methods (all on `AudioWorkletManager`):
- `setPlaybackCallbacks(callbacks)` — `:93-95`
- `async startCapture(callbacks: CaptureCallbacks): Promise<void>` — `:97-133` — creates AudioContext @16kHz, loads `/worklets/pcm-processor.js`, requests mic, creates browser VAD (Silero, unless `_bypassVAD`), wires capture node.
- `stopCapture(): void` — `:135-143`
- `async startRecording(durationMs): Promise<ArrayBuffer|null>` — `:145-184` — one-shot recording helper (records into chunks, returns combined buffer).
- `async initPlayback(): Promise<void>` — `:186-211` — creates AudioContext @24kHz, loads `/worklets/pcm-playback-processor.js`.
- `playChunk(chunk: ArrayBuffer): void` — `:213-223` — posts PCM chunk to playback worklet.
- `clearQueue(): void` — `:225-230` — sends `{type:'clear'}` to playback worklet (used on `AUDIO_INTERRUPTED`).
- `async resumeContexts(): Promise<void>` — `:232-237` — resumes suspended capture/playback AudioContexts.
- `async cleanup(): Promise<void>` — `:239-243`
- Getters: `isCapturing`, `isPlaybackReady`, `currentCaptureState`, `currentPlaybackState` — `:245-275`
- `setBypassVAD(bypass: boolean): void` — `:249-263` — used during enrollment (force-send all audio) and push-to-talk (`USER_ADDRESSING_AI`).
- Private handlers: `handleCaptureMessage` (`:277-310`, drops all-zero buffers, computes RMS, manages pre-speech ring buffer), `handlePlaybackMessage` (`:312-326`), `handleVadSpeechStart`/`handleVadSpeechEnd` (`:328-385`, emit `onUtteranceStart`/`onUtteranceEnd` with `utteranceId`/timing/RMS).
- `createBrowserVad(stream)` — `:387-413` — Silero VAD via `MicVAD.new()`, assets at `/vad/`, ONNX wasm at `/onnx/`. Thresholds: `positiveSpeechThreshold=0.55`, `negativeSpeechThreshold=0.35`, `redemptionFrames=6`, `preSpeechPadFrames=12`, `minSpeechFrames=3`. Allows test override via `window.__audioEvalVadOptions`.
- `calculateRms`, `createAudioContext`, `loadWorklet`, `requestMicrophone`, `cleanupCaptureResources`, `teardownPlayback`, `setCaptureState`, `wrapError` — private helpers (`:415-519`).
- `function int16ToFloat32(int16): Float32Array` — `:522-528` — **dead code, not called anywhere in this file** (gotcha — verify no external import either).

Comments/gotchas:
- Detailed resampler comment in `public/worklets/pcm-processor.js:1-16` explains why integer Bresenham-style phase accumulation is used (float drift caused Gemini 1007 errors after ~3 min).
- `PRE_SPEECH_FRAMES = 16` (~480ms) ring buffer prevents first-word clipping (`:69-72, 299-304, 339-343`).
- `setBypassVAD(true)` immediately sets `isSpeaking=true` so all subsequent chunks are forwarded (`:249-258`).

---

## `hooks/useNegotiation.ts` (647 lines)

**Purpose**: Core hook — owns the WebSocket connection, the `AudioWorkletManager` instance, a `useReducer`-based `NegotiationState`, and exposes all control-message senders.

### State management
- `negotiationReducer(state, action)` — `:70-176` — reducer for `NegotiationState`. Action union type `Action` defined `:43-68`.
- `export function useNegotiation()` — `:178-647` — main hook, returns `{ state, connect, grantConsent, startNegotiation, endNegotiation, sendFrame, setManualSpeaker, startCopilot, setUserAddressingAI, startEnrollment, sendEnrollmentAudio, setSpeakerMode, setResponseLanguage, websocket, aiLiveTranscription, audioManager }` (`:629-646`).

### Helper functions (exported, top-level)
- `export function shouldCollapseHumanTranscriptEntries(previous, next): boolean` — `:24-41` — dedup/collapse logic for repeated/corrected human transcript entries (normalizes text, checks speaker/source/context match, 5s timestamp window, substring containment for short fragments).
- `function normalizeTranscriptText(text): string` — `:16-22` — lowercases, strips non-word/non-`$` chars, collapses whitespace.

### Reducer action types (`Action` union, `:43-68`)
`RESET_SESSION, SET_CONNECTED, SET_CONSENTED, SET_NEGOTIATING, SET_SESSION_ID, UPSERT_TRANSCRIPT, SET_STRATEGY, SET_OUTCOME, SET_ERROR, SET_DEGRADED, SET_AI_STATE, SET_COPILOT_ACTIVE, SET_RESPONSE_MODE, SET_AI_LIVE_TRANSCRIPTION, SET_LANGUAGE, SET_RESPONSE_LANGUAGE, SET_PERSISTENCE_READY, SET_DEGRADED_MODE, SET_ENROLLMENT_STATE, SET_ENROLLMENT_COUNTDOWN, SET_ENROLLMENT_ERROR, SET_ENROLLMENT_PROGRESS, SET_ENROLLMENT_FEEDBACK, SET_SPEAKER_MODE, SET_VISION_INTEL`

### Inbound WebSocket message types handled (`switch (msg.type)`, `:228-455`)
| Type | Line | Effect |
|---|---|---|
| `CONNECTION_ESTABLISHED` | 229 | sets connected, stores `session_id` to localStorage |
| `CONSENT_ACKNOWLEDGED` | 242 | `SET_CONSENTED=true` |
| `ENROLLMENT_STARTED` | 245 | enrollment state→capturing |
| `ENROLLMENT_PROGRESS` | 251 | updates progress/feedback |
| `ENROLLMENT_COMPLETE` | 256 | success, switches `speakerMode→auto`, unbypasses VAD |
| `ENROLLMENT_FAILED` | 265 | error state, unbypasses VAD |
| `SPEAKER_MODE_CHANGED` | 274 | `SET_SPEAKER_MODE` |
| `SESSION_STARTED` | 278 | negotiating=true, aiState→connected then listening (2s delay) |
| `AI_CONNECTING` | 285 | aiState→connecting |
| `AI_LISTENING` | 288 | aiState→listening, clears live transcription |
| `AI_THINKING` | 293 | aiState→thinking |
| `AI_SPEAKING` | 296 | aiState→speaking |
| `SESSION_RESTORED` | 299 | dispatches `negotiation-session-restored` window event |
| `TRANSCRIPT_PARTIAL` / `TRANSCRIPT_UPDATE` | 304 | normalizes payload→`TranscriptEntry`, `UPSERT_TRANSCRIPT`, dispatches `negotiation-transcript` if not partial |
| `STRATEGY_UPDATE` | 327 | `SET_STRATEGY` |
| `AI_RESPONSE` | 330 | upserts AI transcript entry |
| `NEGOTIATION_STATE_CHANGED` | 342 | maps backend `current_state` (ACTIVE/IDLE) to local negotiating/aiState/copilot flags; preserves consent on IDLE (see comment `:349-356`) |
| `STATE_UPDATE` | 359 | dispatches `negotiation-state-update` window event |
| `RESEARCH_STARTED` | 367 | dispatches `market-research-started` |
| `RESEARCH_COMPLETE` | 373 | dispatches `market-research-complete` |
| `CONTEXT_UPDATE` | 380 | dispatches `negotiation-context-update` (ListenerAgent dual-model context) |
| `LANGUAGE_UPDATE` | 387 | `SET_LANGUAGE`, `SET_RESPONSE_LANGUAGE` |
| `PERSISTENCE_STATUS` | 392 | `SET_PERSISTENCE_READY` |
| `VISION_STATUS` | 395 | dispatches `negotiation-vision-status` |
| `VISION_INTEL` | 400 | `SET_VISION_INTEL` + dispatches `negotiation-vision-intel` |
| `DEGRADED_MODE_UPDATE` | 408 | `SET_DEGRADED`, `SET_DEGRADED_MODE` |
| `OUTCOME_SUMMARY` | 412 | clears localStorage session id, sets outcome, resets negotiating/consent/aiState/degraded/error/copilot/enrollment |
| `AUDIO_INTERRUPTED` | 426 | clears playback queue, aiState→listening |
| `COPILOT_STARTED` | 432 | `SET_COPILOT_ACTIVE=true` |
| `RESPONSE_MODE_SET` | 436 | `SET_RESPONSE_MODE` |
| `AI_TRANSCRIPTION_DISPLAY` | 441 | **disabled** (no-op, comment says "disabled") |
| `SESSION_RECONNECTING` | 444 | sets error="Reconnecting to AI..." |
| `AI_DEGRADED` | 447 | degraded=true, mode from payload or 'manual_only' |
| `ERROR` | 451 | `SET_ERROR` |

### Connection lifecycle gotchas (important comments)
- `:230-232` — explicit comment: do NOT reset session on session_id change after reconnect (was sending users back to privacy screen mid-negotiation).
- `:349-356` — backend IDLE transition does NOT un-consent the user or reset transcript — explicit design decision documented in comments.
- `:458-465` — `onClose` handler: NO auto-reconnect by design (would create new session_id → RESET_SESSION → privacy screen). User must refresh manually.
- `:204-209` — cleanup effect only disconnects on true unmount, with comment about "not inside strict effect reload".

### Exported control functions
- `connect(wsUrl: string)` — `:212-472` — async, resolves session id from localStorage, instantiates `NegotiationWebSocket`, registers all message/close/error handlers, calls `.connect()`.
- `grantConsent(version, mode)` — `:474-476` — sends `PRIVACY_CONSENT_GRANTED`.
- `startNegotiation(contextStr, userContext?)` — `:478-504` — unbypasses VAD, inits playback, starts capture (wires `onChunk`→`sendAudioChunk`, `onUtteranceEnd`→`sendUtteranceEnd`), sends `START_NEGOTIATION`.
- `endNegotiation(finalPrice, initialPrice)` — `:506-513` — sends `END_NEGOTIATION`, stops capture, clears reconnect timer.
- `sendFrame(base64Image, isLiveMode=false)` — `:515-521` — sends `VISION_FRAME` (no caller found in page.tsx — likely dead/future feature).
- `setManualSpeaker(speaker)` — `:524-550` — sends `SPEAKER_IDENTIFIED`; has very verbose decorative `console.log` block (`:528-543`, gotcha — noise/cleanup candidate).
- `startCopilot()` — `:552-555` — sends `START_COPILOT`.
- `setUserAddressingAI(active)` — `:557-563` — toggles VAD bypass + sends `USER_ADDRESSING_AI`.
- `startEnrollment()` — `:565-613` — async; guards re-entrancy via `isEnrollmentStartingRef`; stops any existing capture, force-bypasses VAD, starts capture, waits 500ms, sends `ENROLLMENT_START`.
- `sendEnrollmentAudio(audioChunk)` — `:615-617` — sends raw audio chunk via `sendAudioChunk`.
- `setSpeakerMode(mode)` — `:619-622` — sends `SPEAKER_MODE_CHANGE`.
- `setResponseLanguage(language)` — `:624-627` — local dispatch + sends `SET_RESPONSE_LANGUAGE`.

---

## `hooks/useNegotiationState.ts` (341 lines)

**Purpose**: Separate "button-triggered advice system" state — tracks negotiation item/prices/sentiment/transcript snippet/market data, independent of the realtime `useNegotiation` reducer. Drives `NegotiationStateCard` and `useAskAI`.

Exported types:
- `export interface NegotiationState` — `:7-23` — fields: `item, negotiation_type, seller_price, user_offer, target_price, max_price, counterparty_sentiment, counterparty_goal, key_moments, leverage_points, transcript_snippet, market_data, transcript, isResearching, researchProgress`. **Note: this is a DIFFERENT type from `lib/types.ts`'s `NegotiationState`** — same name, different shape, used in different contexts (gotcha: name collision between hook-local state and websocket-driven state).
- `export interface TranscriptEntry` — `:28-33` — `{id, speaker: 'USER'|'COUNTERPARTY', text, timestamp}` (also distinct from `lib/types.ts` TranscriptEntry which uses lowercase speaker incl. 'ai'/'unknown').
- `export interface ValidationError` — `:38-41` — `{field: keyof NegotiationState, message}`.
- `const INITIAL_STATE: NegotiationState` — `:43-59`.

Main hook:
- `export function useNegotiationState()` — `:73-291` — returns `{state, validationErrors, addTranscriptEntry, updateStateFromAI, updateMarketData, setResearchState, resetState, validateState}`.
  - `validateState(stateToValidate): ValidationError[]` — `:84-96` — checks `target_price <= max_price`.
  - `addTranscriptEntry(speaker, text)` — `:105-136` — appends entry, keeps 90s rolling window (`cutoffTime = Date.now()-90000`), extracts price from counterparty speech via `extractPriceFromText`.
  - `updateStateFromAI(updates: Partial<NegotiationState>)` — `:151-244` — smart-merge logic: prefers longer item names, only updates prices if changed/non-null, accepts backend aliases `user_target_price`→`target_price`, `user_max_price`→`max_price`, `sentiment`→`counterparty_sentiment`; merges `key_moments`/`leverage_points` (deduped, capped at last 5 via `normalizeListEntries`); runs `validateState` and updates `validationErrors`.
  - `updateMarketData(data: string)` — `:251-258` — sets `market_data`, clears researching flags.
  - `setResearchState(isResearching, progress=null)` — `:266-272`.
  - `resetState()` — `:277-279` — resets to `INITIAL_STATE`.

Module-private helpers:
- `function extractPriceFromText(text): number | null` — `:300-321` — regex patterns for ₹/$/rupees/dollars/bucks/rs/inr/usd.
- `function normalizeListEntries(values): string[]` — `:323-341` — normalizes array of strings or objects (extracts `moment|text|detail|summary|message|value` keys) to trimmed string array.

---

## `hooks/useAskAI.ts` (117 lines)

**Purpose**: One-shot "Ask AI" request — bundles `useNegotiationState` state and sends `ASK_ADVICE` over the websocket.

- `export function useAskAI(state, websocket, setResearchState)` — `:22-103` — returns `{askAI, isLoading, clearLoading}`.
  - `askAI()` — `:32-88` — async callback. Guards: websocket connected, not already loading. Sets `isLoading=true`, `setResearchState(true, 'Analyzing conversation...')`. Formats transcript via `formatTranscript`. **Important**: calls `websocket.resumeAudioContexts()` before sending, with comment "Button clicks can suspend [AudioContext], causing corrupted audio frames" (`:55-61`), plus 50ms stabilization delay. Sends `ASK_ADVICE` with `{state: {item, seller_price, target_price, max_price, market_data, transcript: formattedTranscript}}`. After 1.5s, updates progress message to "Researching market prices...". Loading is cleared externally by parent when `AI_SPEAKING`/`AI_THINKING` arrives (see `page.tsx:81-85`).
  - `clearLoading()` — `:94-96`.
- `function formatTranscript(entries: TranscriptEntry[]): string` — `:113-117` — `"[SPEAKER] text\n..."` format.

---

## `hooks/useEnrollment.ts` (84 lines)

**Purpose**: Thin wrapper around enrollment UI concerns — triggers enrollment start (delegating actual capture to `useNegotiation.startEnrollment`), simulates an audio level meter for visual feedback.

- `export type EnrollmentState = 'idle'|'capturing'|'processing'|'success'|'error'` — `:4`
- `export function useEnrollment({audioManager, onStartEnrollment, onSendAudioChunk, enrollmentState, enrollmentCountdown})` — `:14-84` — returns `{startEnrollment, audioLevel}`.
  - `startEnrollment()` — `:26-43` — calls `onStartEnrollment()` (audio capture already started by `useNegotiation.startEnrollment`).
  - Effect `:46-56` — stops audio capture when `enrollmentState` becomes `'success'`/`'error'`.
  - Effect `:59-78` — while `capturing`, simulates `audioLevel` via `setInterval` (random 40-100%) for the volume meter UI; note this is **simulated**, not real mic level (gotcha — `onSendAudioChunk` param is unused in this file, real audio chunk sending happens in `useNegotiation.startEnrollment`).

---

## `components/negotiation/NegotiationDashboard.tsx` (376 lines)

**Purpose**: Main dashboard layout — composes all negotiation UI. Renders `PrivacyConsent` gate, then a 2-column layout (left: audio status + speaker selector + dual transcript panels; right: `NegotiationStateCard` + session research history) plus a bottom `ControlBar`/`AskAIButton` and floating overlays.

- `interface NegotiationDashboardProps` — `:14-34` — props: `state: NegotiationState (lib/types)`, `negotiationState: ButtonTriggeredState (useNegotiationState)`, `validationErrors`, `onConsent`, `onToggleAudio`, `onStartNegotiation`, `onEndNegotiation`, `onStartCopilot`, `onUserAddressingAI`, `isAILoading`, `onSpeakerSelected?`, `currentSpeaker?`, `responseLanguage?`, `onResponseLanguageChange?`, `aiLiveTranscription?`, `liveTranscript?: TranscriptEntry[]`, `speakerMode?`, `onSpeakerModeChange?`, `sessionResearchHistory?`.
- `export function NegotiationDashboard(props)` — `:36-376`.
  - Local state: `isAddressingAI` (`:47`), `longPressTimerRef` (`:48`).
  - `handlePointerDown`/`handlePointerEnd` — `:50-62` — implements 600ms long-press to trigger "addressing AI" mode (calls `navigator.vibrate(30)` if available, calls `onUserAddressingAI(true/false)`). Only active if `state.copilotActive`.
  - Early return: `if (!state.consentGiven) return <PrivacyConsent onAccept={onConsent} />` — `:64`.
  - Layout sections:
    - Ambient blurred background blobs (`:76-85`, decorative).
    - `<AIStateIndicator state={state.aiState}/>` — `:87`
    - `<ResearchIndicator isResearching=... progress=.../>` — `:88`
    - `<ValidationErrors errors=.../>` if errors present — `:90-92`
    - **Left column** (`:98-244`, 55% width):
      - "Browser Audio Copilot" status card (capture/speaker mode/transcript/recovery info) — `:101-142`
      - Speaker selector card with `SpeakerModeToggle`, response-language `<select>` (en-US/hi-IN/es-US), and Me/Counterparty buttons (manual mode) or "Voice recognition active" message (auto mode) — `:144-225`
      - Two `TranscriptPanel`s side by side: "Conversation" (filters out `speaker==='ai'` and `context==='ask_ai'`) and "AI Advisor" (only `speaker==='ai'` or `context==='ask_ai'`) — `:227-244`
    - **Right column** (`:246-299`):
      - `<NegotiationStateCard state={negotiationState} isDualModelActive={state.isNegotiating} liveTranscript={liveTranscript} isAddressingAI={isAddressingAI}/>` — `:249-254`
      - "Session History" card showing last 5 `sessionResearchHistory` events (reversed) — `:255-297`
    - **Bottom bar**: `<ControlBar>` + `<AskAIButton>` (absolute positioned right) — `:303-327`
    - **AI live transcription overlay** (only when `aiLiveTranscription && state.aiState==='speaking'`) — `:330-343`
    - **"Listening to you..." overlay** (when `isAddressingAI`) — `:346-361`
    - **Degraded mode banner** (when `state.aiDegraded`) — `:364-373`

Dependencies: `PrivacyConsent`, `TranscriptPanel`, `ControlBar`, `AIStateIndicator`, `ValidationErrors`, `NegotiationStateCard`, `ResearchIndicator`, `AskAIButton`, `SpeakerModeToggle`. Does NOT use `VideoCapture`, `StrategyPanel`, `ManualSpeakerSelector`, `StateDebugPanel`.

---

## `components/negotiation/NegotiationStateCard.tsx` (269 lines)

**Purpose**: Right-column "Negotiation Context" card — shows item, role/type badge, prices (counterparty/user/target/walk-away), sentiment badge, counterparty goal, key moments, leverage points, market research summary, last transcript snippet, and a live mini-transcript feed.

- `interface NegotiationStateCardProps` — `:9-14` — `{state: NegotiationState (useNegotiationState), isDualModelActive?, liveTranscript?: TranscriptEntry[] (lib/types), isAddressingAI?}`.
- Style constants `GLASS, BLUR, BORDER, SHADOW, G, GL, GF, GG, TM, TB` — `:16-25` (shared "frosted glass + gold accent" theme, duplicated across multiple components — refactor candidate).
- `function StateField({label, value, icon, isUpdated, valueColor})` — `:27-44` — generic glass row, highlights gold when `isUpdated`.
- `function SentimentBadge({sentiment})` — `:46-60` — maps `positive/neutral/negative` to emoji+color badges.
- `function NegotiationTypeBadge({type})` — `:62-74` — maps `buying_goods|selling_goods|renting|salary|service|contract|other` to emoji labels.
- `function SectionLabel({children})` — `:76-84` — gold uppercase divider label.
- `export function NegotiationStateCard({state, isDualModelActive=false, liveTranscript=[], isAddressingAI=false})` — `:86-269`.
  - `recentlyUpdated` state + `prevStateRef` — `:87-88` — effect (`:90-108`) diffs current vs previous state across 10 fields (`item, seller_price, user_offer, target_price, max_price, counterparty_sentiment, counterparty_goal, key_moments.length, leverage_points.length, market_data`); sets `recentlyUpdated` to the first changed field for 2s (triggers gold highlight via `StateField`'s `isUpdated`).
  - Renders: Item field, Role badge (`negotiation_type`), Prices section (`seller_price`, `user_offer`, `target_price`, `max_price`), Counterparty section (sentiment badge, goal), conditional "Key Moments" (last 3), "Leverage Points" (last 3, purple theme), "Market Research" (handles both string and object `market_data` with `price_range`/`key_facts`/`leverage`/`summary`), "Last Snippet" (`transcript_snippet`), and live transcript feed (last 6 entries from `liveTranscript`, color-coded by speaker user/ai/counterparty) — `:110-268`.

---

## `components/negotiation/VideoCapture.tsx` (180 lines) — **UNUSED/ORPHANED**

**Purpose**: Camera capture component — requests webcam, periodically captures JPEG frames (deduped via signature hash) and calls `onFrameCapture(base64, isLiveMode)`. Not imported by `NegotiationDashboard` or anywhere else.

- `interface VideoCaptureProps` — `:4-15` — `{isActive, onToggle, onFrameCapture?, frameIntervalMs=1000, isLiveActive?}`.
- `export function VideoCapture(props)` — `:17-180`.
  - Effect `:30-78` — manages `getUserMedia({video:{1280x720, facingMode:'user'}})`, sets `videoRef.srcObject`, cleans up tracks on unmount/deactivation.
  - Effect `:81-83` — keeps `isLiveActiveRef` in sync.
  - Effect `:85-125` — `setInterval` at `frameIntervalMs` (default 1000ms/1fps): draws video frame to canvas (max width 640px), exports JPEG quality 0.6, dedupes via `frameSignature` (length + first/last 96 chars of base64) to avoid re-sending identical frames, calls `onFrameCapture`.
  - Renders `<video>` element, "Camera Inactive" placeholder, "Live Vision"/"AI Observing" badge, hover overlay with toggle button (Camera/CameraOff icons).
  - Comment `:9-11`: "Scene-change filter in the backend means Pro only fires when content actually changes" — backend-side dedup also exists.
  - This component pairs conceptually with `useNegotiation.sendFrame` (`useNegotiation.ts:515-521`, also unused) and `VISION_FRAME`/`VISION_STATUS`/`VISION_INTEL` message types — likely a disabled/removed vision feature, reactivatable by wiring both back into `page.tsx`/`NegotiationDashboard`.

---

## `components/negotiation/StrategyPanel.tsx` (117 lines) — **UNUSED/ORPHANED**

**Purpose**: Displays AI-recommended negotiation strategy (recommended response, current offer vs target price, key leverage points, walkaway threshold, confidence meter). Depends on `Strategy` type from missing `lib/types`.

- `interface StrategyPanelProps` — `:5-7` — `{strategy: Strategy | null}`.
- `export function StrategyPanel({strategy})` — `:9-116`.
  - If `!strategy`: shows "Listening to negotiation to formulate strategy..." placeholder (`:10-19`).
  - Otherwise destructures `{target_price, current_offer, recommended_response, key_points, approach_type, confidence, walkaway_threshold}` from `Strategy` (`:21-29`) — this is the inferred shape of the missing `Strategy` type.
  - Renders header with `approach_type` badge (collaborative/aggressive/other → blue/orange/red) and confidence bar (`:37-52`), "What to Say" quote box (`:55-65`), 2-col price grid "They Want" vs "Target" (`:68-86`), "Key Leverage Points" list (`:89-103`), walkaway threshold notice (`:105-112`).
  - Corresponds to `STRATEGY_UPDATE` message handled in `useNegotiation.ts:327-329` (`SET_STRATEGY` → `state.strategy`), but `state.strategy` is never read/passed to this component anywhere — fully disconnected.

---

## `components/negotiation/StrategyPanel.tsx`'s siblings — small components

### `components/negotiation/SpeakerModeToggle.tsx` (117 lines)
**Purpose**: Pill toggle button switching between `'auto'` (SpeechBrain voice ID) and `'manual'` speaker labeling, with hover tooltip explaining each mode.
- `export type SpeakerMode = 'auto' | 'manual'` — `:12`
- `interface SpeakerModeToggleProps` — `:14-18` — `{mode, onModeChange, disabled?}`.
- `export function SpeakerModeToggle({mode, onModeChange, disabled=false})` — `:20-116`.
  - `showTooltip` state (`:21`), `handleToggle` flips mode if not disabled (`:23-27`).
  - Renders gold gradient button when `mode==='auto'`, glass button when `'manual'`; status dot (green=auto/amber=manual); tooltip on hover with mode-specific explanation.
  - Used by `NegotiationDashboard.tsx:158-163`.

### `components/negotiation/TranscriptPanel.tsx` (115 lines)
**Purpose**: Scrollable chat-bubble transcript display, auto-scrolls to bottom on new entries, color-codes by speaker (user=gold, counterparty=white/glass, ai=blue italic, unknown=gray).
- `interface TranscriptPanelProps` — `:5-8` — `{entries: TranscriptEntry[] (lib/types), title?='Transcript'}`.
- `export function TranscriptPanel({entries, title='Transcript'})` — `:19-114`.
  - `scrollRef` + effect (`:20-24`) — auto-scrolls `scrollTop = scrollHeight` on `entries` change.
  - Empty state: "AI responses will appear here..." (if title==='AI Advisor') or "Waiting for conversation to start..." (`:33-45`).
  - Per-entry rendering (`:57-110`): avatar icon (User/MessageSquare/Cpu by speaker), bubble style/color by speaker (user/counterparty/ai/unknown), speaker label, timestamp (`toLocaleTimeString`), optional confidence % badge (`entry.confidence`).
  - Used twice in `NegotiationDashboard.tsx:231-241` (Conversation + AI Advisor).

### `components/negotiation/ValidationErrors.tsx` (85 lines)
**Purpose**: Displays friendly, actionable validation error banners (yellow alert boxes) for `useNegotiationState` validation issues.
- `interface ValidationErrorsProps` — `:8-10` — `{errors: ValidationError[] (useNegotiationState)}`.
- `const ERROR_DETAILS: Record<string, {title, message, icon}>` — `:15-41` — predefined messages for `missing_item`, `missing_seller_price`, `missing_target_price`, `target_price`, `max_price`. Note: `missing_item`/`missing_seller_price`/`missing_target_price` keys are defined but `validateState` in `useNegotiationState.ts:84-96` currently only ever produces `'target_price'` errors — the other three are dead/future-proofing (gotcha).
- `export function ValidationErrors({errors})` — `:49-84` — returns `null` if empty; otherwise maps errors to alert boxes with `role="alert" aria-live="polite"`.
- Used by `NegotiationDashboard.tsx:91`.
- Companion files: `ValidationErrors.test.tsx`, `ValidationErrors.example.tsx` (demo/integration example, not used in app).

### `components/negotiation/AskAIButton.tsx` (58 lines)
**Purpose**: Bottom-right "Start Copilot" button; once active, shows "Copilot Active" status + "Then press and hold to talk" hint (referring to `NegotiationDashboard`'s long-press-to-address-AI gesture).
- `interface AskAIButtonProps` — `:4-9` — `{onStartCopilot, isLoading, isDisabled, copilotActive}`.
- `export function AskAIButton(props)` — `:11-57`.
  - If `!copilotActive`: gold "Start Copilot" button (Sparkles icon), shows "Starting..." + spinner when `isLoading` — `:27-39`.
  - If `copilotActive`: "Copilot Active" pulsing mic indicator + hint text — `:41-54`.
  - Used by `NegotiationDashboard.tsx:319-324`.

### `components/negotiation/AIStateIndicator.tsx` (36 lines)
**Purpose**: Top-center floating pill showing AI connection/processing state with icon+color per state.
- `interface AIStateIndicatorProps` — `:4-6` — `{state: 'idle'|'connecting'|'connected'|'listening'|'thinking'|'speaking'}`.
- `export function AIStateIndicator({state})` — `:8-35`.
  - Returns `null` if `state==='idle'` (`:9`).
  - `cfg` map (`:11-17`): connecting=Loader2/orange/spin, connected=CheckCircle2/green, listening=Mic/blue, thinking=Brain/purple, speaking=Volume2/green.
  - Used by `NegotiationDashboard.tsx:87`.

### `components/negotiation/ControlBar.tsx` (61 lines)
**Purpose**: Bottom-bar primary controls — mic mute toggle + Start/End Session button.
- `interface ControlBarProps` — `:4-10` — `{isAudioActive, isNegotiating, onToggleAudio, onStartNegotiation, onEndNegotiation}`.
- `export function ControlBar(props)` — `:12-60`.
  - Mic toggle button (Mic/MicOff icons), disabled when `!isNegotiating` — `:19-29`.
  - If `isNegotiating`: red "End Session" button (PhoneOff icon) → `onEndNegotiation` — `:31-43`.
  - Else: gold "Start Session" button (Phone icon) → `onStartNegotiation` — `:45-56`.
  - Used by `NegotiationDashboard.tsx:311-317`.

### `components/negotiation/ManualSpeakerSelector.tsx` (32 lines) — **UNUSED/ORPHANED**
**Purpose**: Simple "Me (User)" / "Counterparty" toggle buttons with basic Tailwind blue/gray styling (older, non-glass design). Superseded by the inline speaker-selector UI in `NegotiationDashboard.tsx:144-224` which uses the same callback signature (`onSpeakerSelected`, `currentSpeaker`).
- `interface ManualSpeakerSelectorProps` — `:4-7` — `{onSpeakerSelected, currentSpeaker}`.
- `export function ManualSpeakerSelector(props)` — `:9-31`.

### `components/negotiation/PrivacyConsent.tsx` (38 lines)
**Purpose**: Full-screen modal gate shown when `!state.consentGiven` — explains mic/camera data usage, single "I Understand and Consent" button.
- `interface PrivacyConsentProps` — `:4-6` — `{onAccept: () => void}`.
- `export function PrivacyConsent({onAccept})` — `:8-37`.
  - Note: copy mentions "camera" access (`:20-21`) but no camera/video is actually requested in the active flow (`VideoCapture` is unused) — stale copy (gotcha).
  - Used by `NegotiationDashboard.tsx:64` (early return).

### `components/negotiation/ResearchIndicator.tsx` (26 lines)
**Purpose**: Top floating pill shown while `negotiationState.isResearching` is true, displays `progress` message or default "Analyzing conversation...".
- `interface ResearchIndicatorProps` — `:4-7` — `{isResearching, progress}`.
- `export function ResearchIndicator({isResearching, progress})` — `:9-25` — returns `null` if `!isResearching`.
- Used by `NegotiationDashboard.tsx:88`.

### `components/negotiation/StateDebugPanel.tsx` (74 lines) — **UNUSED/ORPHANED**
**Purpose**: Plain debug table of `useNegotiationState` fields (item, prices, market data, last 5 transcript entries) for dev/testing. Not rendered anywhere in the active app.
- `interface StateDebugPanelProps` — `:8-10` — `{state: NegotiationState (useNegotiationState)}`.
- `export function StateDebugPanel({state})` — `:12-73`.

---

## `components/enrollment/EnrollmentModal.tsx` (259 lines)

**Purpose**: Full-screen modal driving the voice-enrollment flow (idle → capturing → success/error), shows the enrollment script to read aloud, progress bar / volume meter, and action buttons (Start/Skip/Retry/Continue).

- `export const ENROLLMENT_SCRIPT: string` — `:3-4` — the fixed passage the user reads aloud during enrollment.
- `export type EnrollmentState = 'idle'|'capturing'|'processing'|'success'|'error'` — `:16` (duplicate of `useEnrollment.ts:4` — same literal union defined twice, refactor candidate).
- `interface EnrollmentModalProps` — `:18-30` — `{isOpen, onComplete, onSkip, onStartEnrollment, enrollmentState, countdown, progress?, feedbackMessage?, errorMessage?, audioLevel?=0, allowSkip?=true}`.
- `export function EnrollmentModal(props)` — `:32-258`.
  - Returns `null` if `!isOpen` — `:45`.
  - `getStatusMessage()` — `:47-62` — per-state status text.
  - `getInstructions()` — `:64-96` — idle: instructions to read the script; capturing: shows `ENROLLMENT_SCRIPT` + `feedbackMessage`.
  - `getStatusIcon()` — `:98-122` — Mic/Loader2/CheckCircle/XCircle icons per state, shows `progress%` overlay during capturing.
  - Renders icon, title "Voice Enrollment", status message, progress/volume bar (`width: progress ?? audioLevel`%) during capturing (`:152-168`), instructions, error box (error state), and action buttons: idle→Start Enrollment + (optional) Skip; success→Continue; error→Retry + (optional) Skip (`:181-254`).
  - Used by `page.tsx:241-253`.
- Companion: `EnrollmentModal.test.tsx` (test file).

---

## Public assets

### `frontend/public/worklets/`
- `pcm-processor.js` (87 lines) — `PCMCaptureProcessor extends AudioWorkletProcessor` — converts Float32 mic input → Int16 PCM @16kHz using integer Bresenham-style resampling (drift-free; comment explains float accumulator caused Gemini error 1007 after ~3min). Buffer size 800 samples (50ms). Loaded by `audio-worklet-manager.ts:110`.
- `pcm-playback-processor.js` (101 lines) — `PCMPlaybackProcessor extends AudioWorkletProcessor` — queues Int16 PCM @24kHz chunks, max 60s buffer (`24000*2*60` bytes), min buffer 1200 samples (50ms) before starting playback, drops oldest chunks on overflow, posts `playback_started`/`playback_stopped` messages, supports `{type:'clear'}` to flush queue. Loaded by `audio-worklet-manager.ts:201`.

### `frontend/public/vad/`
- `silero_vad_legacy.onnx`, `silero_vad_v5.onnx` — Silero VAD ONNX models (binary, not inspected).
- `vad.worklet.bundle.min.js` — bundled VAD worklet (binary/minified, 0 lines reported by `wc -l` — likely no trailing newline; not inspected). Referenced via `baseAssetPath: '/vad/'` in `audio-worklet-manager.ts:396`.

### `frontend/public/onnx/`
- `ort-wasm.wasm`, `ort-wasm-simd.wasm`, `ort-wasm-simd-threaded.wasm`, `ort-wasm-threaded.wasm`, `ort-wasm-threaded.worker.js` — ONNX Runtime WASM binaries for browser inference, referenced via `onnxWASMBasePath: '/onnx/'` in `audio-worklet-manager.ts:397`. Not inspected (binary/generated).

---

## `frontend/scripts/`

### `run_audio_browser_eval.mjs`
**Purpose**: Node/Playwright eval harness — launches headless Edge/Chromium, loads the frontend at `http://localhost:3000` (or `AUDIO_EVAL_FRONTEND_URL`), drives audio fixture scenarios from `backend/evals/audio_fixtures/manifest.json`, and writes reports to `backend/data/audio_eval_reports/browser/<runId>/`.
- Resolves `manifestPath`, `frontendUrl`, `outRoot`, `transcriptTimeoutMs` (default 30000) from CLI args/env (`:12-22`).
- Filters scenarios by `--scenarioId` and `--limit` (`:26-32`).
- Requires Microsoft Edge executable (`resolveEdgeExecutable()`, referenced `:38`); fails if not found.
- Uses `page.addInitScript(initAudioEvalScript)` (`:60`) — likely injects `window.__audioEvalVadOptions` (referenced in `audio-worklet-manager.ts:390-391`) to control VAD behavior during automated tests. (Did not read full file beyond line 60 — rest contains per-scenario run loop and report writing logic.)

---

## Test files (not deep-dived per instructions, noted for completeness)
- `components/enrollment/EnrollmentModal.test.tsx`
- `components/negotiation/SpeakerModeToggle.test.tsx`
- `components/negotiation/TranscriptPanel.test.tsx`
- `components/negotiation/ValidationErrors.test.tsx` / `ValidationErrors.example.tsx`
- `hooks/useNegotiation.test.ts` (imports the missing `lib/types` — likely currently failing/broken)
- `tests/example.test.ts`, `tests/setup.ts`, `vitest.config.ts`

---

## Summary of key gotchas for future sessions

1. **`frontend/lib/types.ts` is missing** — referenced by 6 files (`useNegotiation.ts`, `useNegotiation.test.ts`, `NegotiationDashboard.tsx`, `NegotiationStateCard.tsx`, `TranscriptPanel.tsx`, `StrategyPanel.tsx`). Must be reconstructed/restored for the project to typecheck/build. Inferred exports needed: `NegotiationState`, `INITIAL_NEGOTIATION_STATE`, `TranscriptEntry`, `Strategy`, `OutcomeSummary`, `ServerMessageType`, `WebSocketMessage`.
2. **Two different `NegotiationState` types** with the same name exist: `lib/types.ts` (websocket/session state, missing) vs `hooks/useNegotiationState.ts:7-23` (button-triggered advice state). Easy to confuse in imports.
3. **Two different `TranscriptEntry` types**: `lib/types.ts` (lowercase speaker `user|counterparty|ai|unknown`, has `isPartial/confidence/source/context`) vs `hooks/useNegotiationState.ts:28-33` (uppercase `USER|COUNTERPARTY`, minimal fields).
4. **Orphaned components** (not imported anywhere): `VideoCapture.tsx`, `StrategyPanel.tsx`, `ManualSpeakerSelector.tsx`, `StateDebugPanel.tsx`. Related dead code: `useNegotiation.sendFrame` (`:515-521`), `state.strategy`/`SET_STRATEGY` (set but never displayed), `int16ToFloat32` in `audio-worklet-manager.ts:522-528`.
5. **`PrivacyConsent.tsx`** copy mentions camera access but no camera capture is active in the current flow.
6. **No auto-reconnect** on WebSocket close (`useNegotiation.ts:458-465`) — by design, but means any disconnect requires a manual page refresh.
7. **Verbose console logging**: `lib/websocket.ts:142,147` and `useNegotiation.ts:528-543` (`setManualSpeaker`) log extensively to console — candidates for cleanup/guarding behind a debug flag.
8. **`utils/api.ts`** (`instrumentedFetch`) unconditionally calls `.json()` on cloned responses (`:29-30`) — will throw on non-JSON responses; check if/where it's actually used before relying on it.
9. **`useEnrollment.ts`** audio level meter is simulated random data (`:59-78`), not real mic RMS, despite `onSendAudioChunk` prop being passed in.
10. Shared "frosted glass + gold" theme constants (`G, GL, GF, GG, TM, TB, GLASS, BLUR, BORDER, SHADOW`) are duplicated across `NegotiationStateCard.tsx`, `TranscriptPanel.tsx`, `SpeakerModeToggle.tsx`, `EnrollmentModal.tsx` — candidate for extraction to a shared theme module.