# Voice Recognition System - Complete Flow Documentation

## System Overview

This document explains the complete flow of the voice recognition and transcription system, from when a user speaks to when transcripts appear in the UI.

---

## Architecture Components

### Frontend Components
1. **AudioWorkletManager** (`frontend/lib/audio-worklet-manager.ts`)
   - Captures microphone audio using Web Audio API
   - Processes audio through AudioWorklet (pcm-processor.js)
   - Converts to 16kHz PCM format
   - Sends chunks to backend via WebSocket

2. **WebSocket Client** (`frontend/lib/websocket.ts`)
   - Manages WebSocket connection to backend
   - Sends binary audio chunks
   - Receives transcript updates and context updates

3. **useNegotiation Hook** (`frontend/hooks/useNegotiation.ts`)
   - Manages negotiation state
   - Starts/stops audio capture
   - Handles enrollment flow

### Backend Components
1. **WebSocket Handler** (`backend/app/api/websocket.py`)
   - Receives audio chunks from frontend
   - Routes to appropriate handlers based on session state

2. **NegotiationEngine** (`backend/app/services/negotiation_engine.py`)
   - Manages session state machine
   - Routes audio to AudioBuffer
   - Handles speaker identification

3. **AudioBuffer** (`backend/app/services/audio_buffer.py`)
   - Thread-safe rolling buffer
   - Stores last 90 seconds of audio
   - Provides windowed access for processing

4. **ListenerAgent** (`backend/app/services/listener_agent.py`)
   - Background polling loop (every 3 seconds)
   - Extracts audio windows
   - Sends to Flash API for transcription + diarization
   - Processes speaker labels
   - Sends transcripts to frontend

5. **SpeakerEnrollmentService** (`backend/app/services/speaker_enrollment.py`)
   - Captures 10 seconds of enrollment audio
   - Validates audio quality
   - Stores enrollment audio in session

---

## Complete Flow: From Speech to Transcript

### Phase 1: Audio Capture (Frontend)

```
User Speaks
    ↓
Microphone captures audio
    ↓
AudioContext (16kHz sample rate)
    ↓
createMediaStreamSource(micStream)
    ↓
AudioWorkletNode (pcm-capture-processor)
    ↓
Converts to Int16 PCM chunks (every ~100ms)
    ↓
onChunk callback fires
    ↓
wsRef.current.sendAudioChunk(chunk)
    ↓
WebSocket.send(binary data)
```

**Timing**: Audio chunks sent every ~100ms (1600 bytes = 0.1s at 16kHz)

---

### Phase 2: Audio Reception (Backend)

```
WebSocket receives binary message
    ↓
websocket.py: message.get("bytes")
    ↓
Check session.state == ACTIVE
    ↓
NegotiationEngine.handle_audio_chunk(session, bytes)
    ↓
session.audio_buffer.push(raw_bytes)
    ↓
Audio stored in rolling buffer (max 90s)
```

**Timing**: Immediate (< 1ms per chunk)

---

### Phase 3: Enrollment (If First Time)

```
Frontend sends ENROLLMENT_START message
    ↓
Backend creates SpeakerEnrollmentService
    ↓
User speaks for 10 seconds
    ↓
Audio chunks accumulate in enrollment_service.audio_buffer
    ↓
After 10s: finalize_enrollment()
    ↓
Validate audio quality (volume check)
    ↓
session.enrollment_audio = audio_buffer (saved for diarization)
    ↓
session.speaker_mode = "auto"
    ↓
Send ENROLLMENT_COMPLETE to frontend
```

**Timing**: 10 seconds capture + ~500ms validation

---

### Phase 4: Background Polling Loop (ListenerAgent)

```
ListenerAgent starts on session creation
    ↓
_poll_loop() runs every POLL_INTERVAL (3 seconds)
    ↓
_run_cycle() called
    ↓
Check if user_addressing_ai == False (not asking AI)
    ↓
Check audio_buffer.duration_seconds
    ↓
Calculate new_audio_duration = current - last_processed
    ↓
If new_audio_duration < MIN_NEW_AUDIO (2.0s): SKIP CYCLE
    ↓
If enough audio: proceed to extraction
```

**Timing**: Cycle runs every 3 seconds, needs 2s of new audio

**Critical Conditions**:
- ✅ Cycle runs if: `new_audio_duration >= 2.0s`
- ❌ Cycle skips if: `new_audio_duration < 2.0s`
- ❌ Cycle skips if: `user_addressing_ai == True`
- ❌ Cycle skips if: `audio_bytes < 3200 bytes` (< 0.1s)

---

### Phase 5: Audio Extraction & Flash API Call

```
audio_buffer.get_window(WINDOW_SECONDS=10)
    ↓
Returns last 10 seconds of PCM audio
    ↓
Convert PCM to WAV format
    ↓
Base64 encode WAV
    ↓
Build Flash API request:
    - If enrollment_audio exists:
        1. Add separator: "=== REFERENCE VOICE SAMPLE ==="
        2. Add enrollment_audio (base64)
        3. Add separator: "=== END REFERENCE ==="
        4. Add separator: "=== CONVERSATION TO TRANSCRIBE ==="
        5. Add conversation_audio (base64)
    - If no enrollment:
        1. Add conversation_audio only
    ↓
Add diarization prompt:
    - With enrollment: "Label as USER or COUNTERPARTY"
    - Without enrollment: "Label as Speaker 1 or Speaker 2"
    ↓
Send to gemini-2.5-flash API
    ↓
Wait for response (2-5 seconds)
```

**Timing**: 2-5 seconds for Flash API response

**Flash API Response Format**:
```json
{
  "item": "iPhone 15 Pro Max",
  "negotiation_type": "selling_goods",
  "user_price": 800,
  "counterparty_price": null,
  "diarization": [
    {
      "speaker": "USER",
      "text": "I want to sell iPhone 15 Pro Max for 800",
      "start_time": 0.0
    }
  ]
}
```

---

### Phase 6: Diarization Processing

```
Flash returns parsed JSON
    ↓
Check if "diarization" field exists
    ↓
Check if manual_override_until has expired
    ↓
If diarization exists and not in manual mode:
    ↓
_process_diarization(diarization_data)
    ↓
For each turn in diarization:
    ↓
    Extract speaker label ("USER", "COUNTERPARTY", "Speaker 1", "Speaker 2")
    Extract text
    Extract start_time
    ↓
    Map speaker label to internal format:
        - "USER" → "user"
        - "COUNTERPARTY" → "counterparty"
        - "Speaker 1/2" → wait for manual mapping (SKIP for now)
    ↓
    Update session.current_speaker
    Update session.speaker_timeline
    ↓
    Send TRANSCRIPT_UPDATE to frontend:
        {
            "type": "TRANSCRIPT_UPDATE",
            "payload": {
                "speaker": "user",
                "text": "I want to sell iPhone 15 Pro Max for 800",
                "timestamp": 1234567890.123
            }
        }
```

**Timing**: < 100ms per turn

**Critical Conditions**:
- ✅ Transcripts sent if: `diarization exists AND manual_override_until expired`
- ❌ Transcripts NOT sent if: `no diarization data`
- ❌ Transcripts NOT sent if: `manual_override_until > current_time`
- ❌ Transcripts NOT sent if: `speaker label is "Speaker 1/2" and no mapping exists`

---

### Phase 7: Frontend Display

```
WebSocket receives TRANSCRIPT_UPDATE message
    ↓
useNegotiation hook processes message
    ↓
Updates transcript state
    ↓
UI re-renders with new transcript
    ↓
Transcript appears in sidebar
```

**Timing**: < 50ms

---

## Complete Timeline Example

```
T=0.0s:  User starts speaking "I want to sell iPhone 15 Pro Max for 800"
T=0.1s:  First audio chunk sent to backend (1600 bytes)
T=0.2s:  Second audio chunk sent
T=0.3s:  Third audio chunk sent
...
T=2.0s:  User finishes speaking (20 chunks sent, 32000 bytes total)
T=3.0s:  ListenerAgent cycle runs
         - new_audio_duration = 3.0s (>= 2.0s ✓)
         - Extracts last 10s window
         - Sends to Flash API
T=5.5s:  Flash API responds with diarization
         - speaker: "USER"
         - text: "I want to sell iPhone 15 Pro Max for 800"
T=5.6s:  _process_diarization() processes turn
         - Maps "USER" → "user"
         - Sends TRANSCRIPT_UPDATE to frontend
T=5.7s:  Frontend receives and displays transcript
```

**Total latency**: ~5.7 seconds from speech end to display

---

## Failure Modes & Debugging

### Issue 1: No Transcripts Appearing

**Possible Causes**:
1. **Cycles not running**
   - Check logs for: `🔄 Cycle X starting...`
   - If missing: Poll loop not started

2. **Cycles skipping due to insufficient audio**
   - Check logs for: `⏸️ Cycle X: Skipping - only X.Xs new audio (need 2.0s)`
   - Solution: Speak for at least 2 seconds

3. **Audio buffer empty**
   - Check logs for: `⏸️ Cycle X: Skipping - audio too short (X bytes)`
   - Solution: Verify audio capture is working

4. **Flash not returning diarization**
   - Check logs for: `⚠️ No diarization data returned from Flash`
   - Solution: Check Flash API response, verify enrollment audio

5. **Manual override blocking diarization**
   - Check logs for: `⏸️ Diarization paused (manual mode until X.Xs)`
   - Solution: Wait for manual_override_until to expire or set to None

6. **Speaker mapping missing**
   - Check logs for: `⏭️ Skipping speaker mapping wait for Speaker 1`
   - Solution: Provide manual speaker identification

### Issue 2: Wrong Speaker Labels

**Possible Causes**:
1. **Enrollment audio doesn't match user voice**
   - Flash compares conversation audio to enrollment audio
   - If voices don't match, labels as COUNTERPARTY
   - Solution: Re-enroll with correct voice

2. **Enrollment audio not saved**
   - Check: `session.enrollment_audio` should contain bytes
   - Check logs for: `📋 Enrollment audio size: X bytes`
   - Solution: Verify enrollment completed successfully

3. **Flash misidentifying voices**
   - Flash AI may make mistakes in voice matching
   - Check logs for: `🎯 Turn X: [COUNTERPARTY] ...` when should be USER
   - Solution: Improve enrollment audio quality, speak more clearly

### Issue 3: Transcription Stuck After One Iteration

**Possible Causes**:
1. **_last_processed_duration not updating**
   - After each cycle, `_last_processed_duration = current_duration`
   - If this doesn't update, next cycle sees 0 new audio
   - Check logs for: `🎤 Cycle X: Processing X.Xs new audio (buffer: X.Xs)`

2. **Audio buffer not receiving new chunks**
   - Check if audio capture is still running
   - Check WebSocket connection status
   - Check logs for: `🎤 Received binary audio frame: X bytes`

3. **Cycle interval too long**
   - POLL_INTERVAL = 3 seconds
   - MIN_NEW_AUDIO = 2.0 seconds
   - If user speaks < 2s between cycles, skipped
   - Solution: Reduce MIN_NEW_AUDIO or speak continuously

---

## Configuration Constants

```python
# listener_agent.py
POLL_INTERVAL = 3           # seconds between cycles
WINDOW_SECONDS = 10         # audio window sent to Flash
MIN_NEW_AUDIO = 2.0         # minimum new audio required

# speaker_enrollment.py
ENROLLMENT_DURATION = 10.0  # seconds of enrollment audio
MIN_DB_THRESHOLD = -40.0    # minimum audio volume

# audio_buffer.py
SAMPLE_RATE = 16000         # Hz
BYTES_PER_SAMPLE = 2        # 16-bit PCM
BYTES_PER_SECOND = 32000    # 16000 * 2
```

---

## Logging Guide

### Key Log Messages

**Cycle Execution**:
- `🔄 Cycle X starting...` - Cycle begins
- `🎤 Cycle X: Processing X.Xs new audio (buffer: X.Xs)` - Processing audio
- `⏸️ Cycle X: Skipping - only X.Xs new audio (need 2.0s)` - Insufficient audio
- `⏸️ Cycle X: Skipping - audio too short (X bytes)` - Buffer empty

**Flash API**:
- `🔍 Calling Flash: X.Xs audio, enrollment=✓` - Sending to Flash
- `📋 Enrollment audio size: X bytes (X.XXs)` - Enrollment audio details
- `📋 Conversation audio size: X bytes (X.XXs)` - Conversation audio details
- `✅ Flash returned: X turns, item=X` - Flash response received
- `🎯 Turn X: [USER/COUNTERPARTY] text...` - Each diarization turn

**Diarization**:
- `📝 Processing X diarization turns` - Starting diarization
- `⚠️ No diarization data returned from Flash` - No diarization
- `⏸️ Diarization paused (manual mode until X.Xs)` - Manual override active
- `💬 USER/COUNTERPARTY: text` - Transcript sent to frontend

**Context Updates**:
- `📤 CONTEXT_UPDATE sent (cycle X)` - Context forwarded to frontend

---

## Testing Checklist

### 1. Audio Capture Test
- [ ] Open browser console
- [ ] Check for: `🎤 Received binary audio frame: X bytes`
- [ ] Should appear every ~100ms while speaking
- [ ] If missing: Audio capture not working

### 2. Enrollment Test
- [ ] Start enrollment
- [ ] Speak for 10 seconds
- [ ] Check logs for: `Enrollment complete`
- [ ] Check logs for: `📋 Enrollment audio size: X bytes`
- [ ] Should be ~320000 bytes (10s * 32000 bytes/s)

### 3. Cycle Test
- [ ] Speak for 3+ seconds
- [ ] Wait 3 seconds
- [ ] Check logs for: `🔄 Cycle X starting...`
- [ ] Check logs for: `🎤 Cycle X: Processing X.Xs new audio`
- [ ] If skipping: Check skip reason in logs

### 4. Flash API Test
- [ ] After cycle runs
- [ ] Check logs for: `🔍 Calling Flash: X.Xs audio, enrollment=✓`
- [ ] Wait 2-5 seconds
- [ ] Check logs for: `✅ Flash returned: X turns`
- [ ] Check logs for: `🎯 Turn X: [USER/COUNTERPARTY] text...`

### 5. Diarization Test
- [ ] After Flash returns
- [ ] Check logs for: `📝 Processing X diarization turns`
- [ ] Check logs for: `💬 USER: text` or `💬 COUNTERPARTY: text`
- [ ] Check frontend UI for transcript

### 6. Speaker Label Test
- [ ] Enroll with your voice
- [ ] Speak: "I want to sell iPhone 15 Pro Max for 800"
- [ ] Check logs for: `🎯 Turn 1: [USER] I want to sell...`
- [ ] If shows COUNTERPARTY: Enrollment audio mismatch

---

## Common Issues & Solutions

### Issue: "Both speakers labeled as COUNTERPARTY"

**Root Cause**: Enrollment audio doesn't match user's actual speaking voice

**Debug Steps**:
1. Check enrollment audio was saved:
   ```
   📋 Enrollment audio size: 320000 bytes (10.00s)
   ```

2. Check Flash is receiving enrollment:
   ```
   🔍 Calling Flash: 10.0s audio, enrollment=✓
   ```

3. Check Flash response labels:
   ```
   🎯 Turn 1: [COUNTERPARTY] I want to sell...
   ```
   Should be `[USER]` if enrollment matches

**Solutions**:
- Re-enroll with clearer voice
- Speak at same volume/tone as enrollment
- Check microphone is same device
- Verify enrollment audio quality (> -40dB)

### Issue: "Transcription stops after first time"

**Root Cause**: `_last_processed_duration` not updating correctly

**Debug Steps**:
1. Check first cycle:
   ```
   🎤 Cycle 1: Processing 3.0s new audio (buffer: 3.0s)
   ```

2. Check second cycle:
   ```
   ⏸️ Cycle 2: Skipping - only 0.0s new audio (need 2.0s)
   ```
   This indicates `_last_processed_duration` stuck at 3.0s

**Solutions**:
- Verify `_last_processed_duration = current_duration` executes
- Check for exceptions in `_run_cycle()`
- Verify audio buffer is still receiving chunks

### Issue: "No transcription at all"

**Root Cause**: Multiple possible causes

**Debug Steps**:
1. Check cycles running:
   ```
   🔄 Cycle X starting...
   ```
   If missing: Poll loop not started

2. Check audio buffer:
   ```
   🎤 Cycle X: Processing X.Xs new audio (buffer: X.Xs)
   ```
   If buffer=0.0s: Audio not reaching buffer

3. Check Flash API:
   ```
   🔍 Calling Flash: X.Xs audio, enrollment=✓
   ```
   If missing: Cycle skipping before Flash call

4. Check diarization:
   ```
   📝 Processing X diarization turns
   ```
   If missing: Flash not returning diarization

**Solutions**:
- Verify ListenerAgent.start() called
- Verify audio capture running
- Verify WebSocket connected
- Verify Flash API credentials
- Check Flash API response format

---

## Performance Metrics

### Expected Latencies
- Audio chunk capture: ~100ms
- Audio chunk send: < 10ms
- Audio buffer push: < 1ms
- Cycle trigger: 3 seconds (POLL_INTERVAL)
- Flash API call: 2-5 seconds
- Diarization processing: < 100ms
- Frontend display: < 50ms

**Total end-to-end**: ~5-8 seconds from speech end to transcript display

### Resource Usage
- Audio buffer memory: ~2.88 MB (90s * 32000 bytes/s)
- Enrollment audio: ~320 KB (10s * 32000 bytes/s)
- Flash API payload: ~1.3 MB (10s window base64 encoded)

---

## Next Steps for Debugging

1. **Enable debug logging**:
   - All cycle attempts logged
   - All skip reasons logged
   - All Flash API calls logged
   - All diarization turns logged

2. **Run test suite**:
   ```bash
   python -m backend.test_voice_recognition
   ```

3. **Check real-time logs**:
   - Watch backend terminal for emoji logs
   - Look for patterns in skip reasons
   - Verify Flash API responses

4. **Test with synthetic audio**:
   - Use test_voice_recognition.py
   - Verify Flash API integration
   - Verify diarization labels

5. **Test with real audio**:
   - Record enrollment audio
   - Record conversation audio
   - Verify voice matching works

---

## Summary

The voice recognition system works through a multi-stage pipeline:

1. **Frontend captures audio** → sends chunks every 100ms
2. **Backend buffers audio** → stores last 90 seconds
3. **ListenerAgent polls every 3s** → checks for 2s+ new audio
4. **Flash API processes audio** → returns transcription + speaker labels
5. **Diarization processor** → maps labels and sends to frontend
6. **Frontend displays** → shows transcripts in UI

**Critical success factors**:
- Audio capture must be running
- Enrollment audio must match user voice
- Cycles must run (not skip due to insufficient audio)
- Flash must return diarization data
- Manual override must be disabled for auto mode
- Speaker labels must map correctly

**Most common failure**: Enrollment audio doesn't match user's actual speaking voice, causing Flash to label user as COUNTERPARTY instead of USER.
