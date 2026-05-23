# Recovered Implementation Plan
## AI Negotiation Copilot — Speed, Accuracy & AI Correctness Optimization

> **Source:** Reconstructed from Antigravity plan-mode session transcript (`transcript.jsonl`, lines 13–912).  
> **Type:** `source: MODEL`, `type: PLANNER_RESPONSE` entries only.  
> **Status:** Planning phase — no codebase files were modified during this session.

---

## Executive Summary

A thorough audit of the entire codebase was completed and aligned with 2026 State-of-the-Art (SOTA) real-time streaming media standards.  
This plan outlines every optimization required to:
1. **Eliminate lag** across the audio capture → transcription → AI response pipeline
2. **Maximize transcript accuracy** with correct Deepgram segment assembly
3. **Fix Gemini Live AI blindness** (vision frames never reaching the model)
4. **Eliminate WGC frame freezing** on Windows

> No project codebase files were modified during the planning phase.

---

## Part 1 — Speed & Latency Bottlenecks

### 1.1 Main Thread Audio Capture Lag

**Location:** `desktop/src/renderer/overlay.js`

**Problem:**  
`overlay.js` captures microphone and speaker audio using the legacy `ScriptProcessorNode`. This node runs on Electron's **main UI thread**. Any heavy UI operation — scrolling transcripts, redrawing panels, or DOM updates — stalls this thread, **dropping audio packets** and introducing severe processing lag before audio even reaches the WebSocket.

**SOTA Solution:**  
Migrate audio capture and resampling to a dedicated, low-latency background **`AudioWorkletProcessor`** loaded via an inline **Blob URL** inside `overlay.js`.

- `AudioWorkletProcessor` runs on a dedicated audio rendering thread, fully isolated from the UI thread.
- An inline Blob URL avoids the need for a separate `.js` file, making it deployable without server changes.
- The worklet handles both the `local_mic` and `remote_app` PCM lanes in a lock-free ring buffer architecture.
- Downsampling logic (currently `f32ToI16Buffer`) moves entirely into the worklet, removing main-thread math overhead.

**Files to modify:**
- `desktop/src/renderer/overlay.js` — replace `ScriptProcessorNode` with `AudioWorkletProcessor` loaded via Blob URL

---

### 1.2 Network Transit Buffering (Nagle's Algorithm)

**Location:** `backend/app/api/websocket.py`

**Problem:**  
FastAPI Starlette WebSockets operate with standard TCP buffers enabled. Nagle's algorithm consolidates small outgoing packets to reduce network round-trips — but for real-time PCM audio this adds **up to 40ms of packet transit latency per network hop**, defeating the purpose of streaming.

**SOTA Solution:**  
Access Starlette's underlying transport socket in `websocket.py` and immediately set `TCP_NODELAY` (disabling Nagle's algorithm) for direct, low-latency transit.

```python
# In websocket.py, after WebSocket accept():
import socket
ws_transport = websocket._transport
if hasattr(ws_transport, 'get_extra_info'):
    raw_sock = ws_transport.get_extra_info('socket')
    if raw_sock:
        raw_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
```

**Files to modify:**
- `backend/app/api/websocket.py` — add `TCP_NODELAY` socket option after connection accept

---

### 1.3 Ignored Barge-In Playback Bug

**Location:** `desktop/src/renderer/overlay.js` — `handleWsMessage`

**Problem:**  
The backend correctly broadcasts an `AUDIO_INTERRUPTED` message to the desktop client when the user starts talking (barge-in). However, `overlay.js`'s `handleWsMessage` function has **no handler for `AUDIO_INTERRUPTED`**. As a result, previously buffered AI speech `AudioBufferSourceNode` objects continue playing on the user's headset even after the user has started speaking — creating a disorienting double-audio experience.

**SOTA Solution:**  
Establish an **Active Playback Source Registry** in `overlay.js`:

1. Every `AudioBufferSourceNode` created during AI audio playback is added to a `Set<AudioBufferSourceNode>` registry.
2. Each node removes itself from the registry in its `onended` callback.
3. When `AUDIO_INTERRUPTED` is received in `handleWsMessage`, iterate the registry and call `.stop()` on every active source node immediately.

```javascript
// In overlay.js:
const activePlaybackSources = new Set();

// When creating each AI audio chunk source:
const source = audioCtx.createBufferSource();
source.buffer = decodedBuffer;
activePlaybackSources.add(source);
source.onended = () => activePlaybackSources.delete(source);
source.connect(audioCtx.destination);
source.start();

// In handleWsMessage, add case for AUDIO_INTERRUPTED:
case 'AUDIO_INTERRUPTED':
  activePlaybackSources.forEach(src => { try { src.stop(); } catch(e) {} });
  activePlaybackSources.clear();
  break;
```

**Files to modify:**
- `desktop/src/renderer/overlay.js` — add `AUDIO_INTERRUPTED` handler and Active Playback Source Registry

---

## Part 2 — Accuracy & AI Correctness Bottlenecks

### 2.1 Deepgram Transcript Segment Discard Bug

**Location:** `backend/app/services/companion_runtime.py`

**Problem:**  
Deepgram's streaming transcription emits two types of finalized events:
- `is_final=True` — a finalized word segment (may be mid-sentence)
- `speech_final=True` — the entire utterance is complete (end of sentence/turn)

The current `companion_runtime.py` forwarding logic **only dispatches when `speech_final=True`** and discards all intermediate `is_final=True` segments. In multi-part sentences, the beginning and middle of what speakers say is **permanently thrown away**, depriving the strategic negotiation AI of critical context it needs to provide accurate advice.

**SOTA Solution:**  
Implement a session-level **Transcript Segment Assembler** in `companion_runtime.py`:

1. Buffer all `is_final=True` word segments for each active speaker lane (`local_mic`, `remote_app`) in a per-session list.
2. When `speech_final=True` is received, concatenate all buffered segments into a single complete utterance string.
3. Forward this complete sentence to the negotiation engine and clear the buffer.

```python
# In companion_runtime.py:
# Per session, per lane transcript buffer
transcript_buffer = {"local_mic": [], "remote_app": []}

def on_transcript(lane, result):
    if result.is_final:
        transcript_buffer[lane].append(result.channel.alternatives[0].transcript)
    if result.speech_final:
        full_sentence = " ".join(transcript_buffer[lane]).strip()
        transcript_buffer[lane] = []
        if full_sentence:
            negotiation_engine.on_transcript(lane, full_sentence)
```

**Files to modify:**
- `backend/app/services/companion_runtime.py` — implement Transcript Segment Assembler

---

### 2.2 Zero-Overhead Speaker Separation (Architecture Strength)

**Current design (preserve as-is):**  
The hardware loopback design physically separates audio at the OS level:
- `local_mic` lane → captures only the user's microphone input
- `remote_app` lane → captures only the Zoom/Meet counterparty via VB-CABLE virtual driver loopback

This guarantees **100% speaker separation accuracy** with **zero CPU-heavy local diarization model overhead** — no pyannote, no SpeakerNet, no VAD-based segmentation. Speaker identity is implicit from which PCM lane the audio arrived on.

**No changes needed.** This architecture is already at SOTA for hardware-separated dual-lane audio.

---

## Part 3 — Gemini Live Vision & WGC Freeze Fixes

### 3.1 Gemini Live Session Blindness (`is_live_mode` Always False)

**Location:** `backend/app/services/negotiation_engine.py`

**Problem:**  
In `negotiation_engine.py`, base64 screen frames received from the desktop app via `handle_vision_frame` are only forwarded to the Gemini Live session if `is_live_mode` evaluates to `True`. The code evaluates:

```python
is_live_mode = bool(payload.get("live_mode", False))
```

However, the desktop app's `overlay.js` sends `SCREEN_FRAME` payloads **without a `live_mode` key**. Because of this, `is_live_mode` is always `False`, the live frame buffer is never populated, and the Gemini Live AI is **completely blind** during hold-to-talk. The AI states it "cannot see the screen" because no frames are ever sent to the session.

**Fix:**  
Update line 641 in `negotiation_engine.py` to fall back to `True` when the session's source mode is `VIRTUAL_COMPANION_DESKTOP`:

```python
is_live_mode = bool(payload.get("live_mode", False)) or \
               (session.source_mode == SourceMode.VIRTUAL_COMPANION_DESKTOP.value)
```

**Files to modify:**
- `backend/app/services/negotiation_engine.py` — line 641, fix `is_live_mode` fallback logic

---

### 3.2 WGC Window Capturer Silent Frame Freezing

**Location:** `desktop/src/main.js`

**Problem:**  
The Electron desktop companion uses Chromium's screen capturer. Under the hood, Chromium attempts to use **Windows Graphics Capture (WGC)** for window capture. On Windows, WGC frequently fails with:

```
ProcessFrame failed, using existing frame: -2147467259
```

This happens when the target window is obscured, minimized, or composition state changes. When WGC fails, it **silently freezes on the last captured frame** without closing the media track — leaving the AI in a long-term frozen visual state.

The current Electron configuration disabled WGC for screen capture (`AllowWgcScreenCapturer`) but **did not disable it for window capture** (`AllowWgcWindowCapturer`). Since the companion captures the specific meeting window, WGC window capture was still active and failing.

**Fix:**  
Add `AllowWgcWindowCapturer` and `WebRtcAllowWgcWindowCapturer` to the `disable-features` switch in `main.js`. This forces Chromium to use the stable GDI/DXGI capture path instead:

```javascript
app.commandLine.appendSwitch(
  "disable-features",
  "CalculateNativeWinOcclusion,AllowWgcScreenCapturer,AllowWgcWindowCapturer,WebRtcAllowWgcScreenCapturer,WebRtcAllowWgcWindowCapturer"
);
```

**Files to modify:**
- `desktop/src/main.js` — update `disable-features` command-line switch

---

### 3.3 Freeze Detection Threshold Too Slow (24-Second Blind Spot)

**Location:** `desktop/src/renderer/overlay.js`

**Problem:**  
`overlay.js` has a pixel-level freeze detection that compares 5 sample coordinates across consecutive frames. However, the threshold is set to **30 consecutive identical frames** before triggering a hot-reload. At 800ms per frame, this means a **24-second delay** before the freeze is detected and resolved — leaving the AI visually blind for nearly half a minute.

**Fix:**  
Lower the threshold from `30` to `4` frames. A freeze will now be detected and hot-reloaded within **3.2 seconds** (4 frames × 800ms), with no false positives on legitimately static screens (which change at least every few seconds in a real meeting):

```javascript
// Before:
if (identicalFrameCount >= 30 && state.selectedSourceId) {

// After:
// If exactly identical for ~3.2 seconds (4 consecutive frames of 800ms)
if (identicalFrameCount >= 4 && state.selectedSourceId) {
  console.warn("[MeetingCapture] Pixel freeze detected (4 consecutive identical frames). Silently hot-reloading capture stream...");
```

**Files to modify:**
- `desktop/src/renderer/overlay.js` — change `identicalFrameCount >= 30` to `identicalFrameCount >= 4`

---

## Part 4 — Verification Plan

### 4.1 Automated Syntax Checks

Run after every file modification to catch regressions immediately:

```powershell
# Python syntax validation
python -c "import py_compile; py_compile.compile('backend/app/services/negotiation_engine.py', doraise=True)"
python -c "import py_compile; py_compile.compile('backend/app/services/companion_runtime.py', doraise=True)"

# Node/JavaScript syntax validation
node --check desktop/src/main.js
node --check desktop/src/renderer/overlay.js
```

### 4.2 Gemini Live Vision Test

1. Launch the FastAPI backend and Electron Companion app.
2. Start a session and hold the orb.
3. Ask the AI: *"What am I holding?"* or *"What is on my screen?"*
4. **Expected:** AI responds with accurate descriptions of the screen without stating it cannot see.
5. **Failure indicator:** AI says "I cannot see the screen" or gives a generic response.

### 4.3 WGC Freeze Elimination Test

1. Inspect the terminal log of the Electron companion app during a live meeting capture.
2. **Expected:** Zero `ProcessFrame failed, using existing frame: -2147467259` warnings.
3. **Failure indicator:** Continued WGC error logs after the Electron disable-features switch is applied.

### 4.4 Session Log Vision Routing Test

1. Check the session log at `backend/data/logs/sessions/{session_id}.log`.
2. **Expected:** Log entries showing live frames are processed and transmitted during hold-to-talk state.

### 4.5 Barge-In Playback Cancellation Test

1. Trigger an AI audio response (hold orb, ask question, release).
2. While AI audio is playing, immediately press orb again (barge-in).
3. **Expected:** AI audio stops instantly. No double-audio on headset.
4. **Failure indicator:** Old AI audio continues playing while the user's new question is being processed.

### 4.6 Transcript Segment Assembly Test

1. Speak a multi-clause sentence (e.g., "We can go to $50 per unit, but only if you commit to a two-year contract").
2. Verify the full sentence appears in the negotiation engine's context, not just the last clause.
3. **Failure indicator:** Only "two-year contract" or similar final fragment appears in the AI's context.

---

## Part 5 — Clarifying Questions

*(These were outstanding at the time of plan creation — answers determine exact resampling ratios and GCP network routing.)*

1. **Primary Microphone Native Sample Rate:**  
   What is the native sample rate of your primary microphone (e.g., 44.1kHz or 48kHz)?  
   *Knowing this verifies the exact AudioWorklet downsampling factor needed.*

2. **VB-CABLE Virtual Driver Configuration:**  
   Is your VB-CABLE virtual driver set to its default Windows configuration (44.1kHz), or have you manually adjusted it to 48kHz in the Windows Sound Control Panel?

3. **GCP Vertex AI Region & Physical Location:**  
   Which GCP region is your Vertex AI instance deployed in, and what is your general physical location?  
   *Aligning region with physical location can save up to 150ms of raw round-trip network latency.*

4. **Deepgram Turn-Detection Silence Threshold:**  
   Do you prefer aggressive end-of-turn detection (**150ms** silence endpointing for instant advice) or slightly more breathing space (**300ms**) to allow for mid-sentence pauses without premature cutoff?

---

## Change Summary Table

| # | File | Change | Impact |
|---|------|---------|--------|
| 1 | `desktop/src/renderer/overlay.js` | Replace `ScriptProcessorNode` with `AudioWorkletProcessor` via Blob URL | Eliminates main-thread audio drop lag |
| 2 | `backend/app/api/websocket.py` | Set `TCP_NODELAY` after WebSocket accept | Removes up to 40ms Nagle buffering |
| 3 | `desktop/src/renderer/overlay.js` | Add `AUDIO_INTERRUPTED` handler + Active Playback Source Registry | Fixes barge-in double-audio bug |
| 4 | `backend/app/services/companion_runtime.py` | Transcript Segment Assembler (`is_final` buffer, flush on `speech_final`) | Full sentences reach AI instead of fragments |
| 5 | `backend/app/services/negotiation_engine.py` | Fix `is_live_mode` fallback for `VIRTUAL_COMPANION_DESKTOP` | AI can see screen during hold-to-talk |
| 6 | `desktop/src/main.js` | Add `AllowWgcWindowCapturer` to disable-features | Eliminates ProcessFrame WGC errors |
| 7 | `desktop/src/renderer/overlay.js` | Lower freeze detection from 30 to 4 frames | Reduces visual blind spot from 24s to 3.2s |

---

## Files Analyzed During Planning

| File | Purpose |
|------|---------|
| `backend/app/services/companion_runtime.py` | Audio routing, Deepgram dispatch, PCM lane management |
| `backend/app/services/deepgram_stream.py` | Deepgram live WebSocket, keep-alive, reconnect logic |
| `backend/app/services/gemini_client.py` | Gemini Live bidirectional stream, audio response routing |
| `backend/app/services/negotiation_engine.py` | Turn-taking, context injection, hold-to-ask orchestration |
| `backend/app/services/listener_agent.py` | Single-mic / in-person speaker verification pipeline |
| `backend/app/config.py` | Model config, STT providers, timing thresholds, VAD settings |
| `desktop/src/renderer/overlay.js` | Client audio capture, WebSocket streaming, UI playback |
| `desktop/src/main.js` | Electron main process, Chromium command-line switches |
| `frontend/public/worklets/pcm-processor.js` | AudioWorklet downsampling and anti-aliasing |
| `backend/requirements.txt` | Python dependencies available in the environment |
| `desktop/package.json` | Node dependencies and Electron configuration |

---

*Reconstructed from `transcript.jsonl` — `source: MODEL`, `type: PLANNER_RESPONSE` — lines 13–912.*
