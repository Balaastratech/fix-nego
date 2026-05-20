erService when manual mode activated (immediate)
2. Add timestamp-based staleness checks (high priority)
3. Add timeline write lock (medium priority)
4. Refactor to single source of truth (long-term)

1. Manual button handler (fastest, 11-51ms)
2. SpeakerService VAD+Resemblyzer (medium, 130-3330ms)
3. ListenerAgent diarization (slowest, 2000-8000ms)

**Critical flaw**: All three write to the same fields (`current_speaker`, `speaker_timeline`) without locks or timestamp validation.

**Impact**: Speaker labels can be incorrect, transcripts can be mislabeled, and timeline can be out of order.

**Severity**: HIGH - Affects core functionality (speaker identification)

**Recommended fix priority**:
1. Disable Speakheck (can update with 3-second-old data)

**When ListenerAgent processes diarization**:
1. ✅ Reads `speaker_confidence_history` from SpeakerService
2. ✅ Falls back to Resemblyzer if no recent history
3. ✅ Falls back to positional if no embedding
4. ❌ Updates `current_speaker` without checking manual override
5. ❌ Updates `speaker_timeline` without locking
6. ❌ Can conflict with both manual and auto modes

---

## CONCLUSION

The system has **3 concurrent writers** to speaker state with **no synchronization**:mmediately
3. ✅ Previous segment transcribed with correct label
4. ❌ SpeakerService continues running (wastes CPU)
5. ❌ In-flight classifications can still overwrite `current_speaker`
6. ❌ Timeline can have out-of-order entries

**When SpeakerService classifies**:
1. ✅ Checks `manual_override_until` before classification
2. ❌ Check happens at classification time, not segment start time
3. ✅ Updates `current_speaker` and `speaker_timeline`
4. ❌ No coordination with ListenerAgent's timeline writes
5. ❌ No staleness cr.info("SpeakerService disabled (manual mode activated)")
```

### 4. Add Classification Staleness Check
```python
# In _classify_segment()
classification_time = time.time()
if classification_time - segment_end_time > 1.0:
    logger.warning(f"Classification stale ({classification_time - segment_end_time:.1f}s old), discarding")
    return "unknown"
```

---

## CURRENT BEHAVIOR SUMMARY

**When user clicks button**:
1. ✅ `manual_override_until = float('inf')` set immediately
2. ✅ `current_speaker` updated iride
        return self.session.current_speaker
```

### 2. Add Timeline Write Lock
```python
# In NegotiationSession model
speaker_timeline_lock: asyncio.Lock = Field(default_factory=asyncio.Lock)

# In all writers
async with session.speaker_timeline_lock:
    session.speaker_timeline.append({"speaker": label, "timestamp": ts})
```

### 3. Disable SpeakerService in Manual Mode
```python
# In handle_speaker_identified()
if session.speaker_service:
    session.speaker_service = None  # Stop processing
    logge        is_fragment = True
        break
```

**Problem**: Uses speaker label in dedup key. If speaker label changes due to race condition, same text with different label passes through.

---

## RECOMMENDATIONS

### 1. Add Timestamp-Based Manual Override
```python
# In _classify_segment()
segment_start_time = self.segment_start_time  # Captured at speech start
if self.session.manual_override_until:
    if segment_start_time < self.session.manual_override_until:
        # This segment started AFTER manual over 750-780)

```python
# Dedup set reset every 8 cycles (24 seconds)
if self._cycle_count - self._recent_transcript_cycle > 8:
    self._recent_transcript_hashes.clear()
    self._recent_transcript_cycle = self._cycle_count

text_key = f"{our_speaker}:{text_normalized}"
if text_key in self._recent_transcript_hashes:
    logger.debug(f"Skipping exact duplicate: {text[:50]}")
    continue

# Fragment dedup
for sent_key in self._recent_transcript_hashes:
    if text_core in sent_core and len(text_core) < len(sent_core):
)
       ↓
      _classify_segment() → 100-300ms (embedding)
       ↓
      Session update → <1ms
```

**Total latency (AUTO MODE)**: 130-3330ms from speech end to label

### Manual Mode Latency
```
Button Click → WebSocket
  ↓ 10-50ms (network)
handle_speaker_identified()
  ↓ <1ms
Session update → <1ms
```

**Total latency (MANUAL MODE)**: 11-51ms

**Conclusion**: Manual mode is 10-300x faster than auto mode.

---

## DEDUPLICATION LOGIC

### ListenerAgent Transcript Dedup
**File**: `listener_agent.py` (linesad pool)
- Embedding completes at T=10.4s (300ms later)
- Session update at T=10.4s

**Problem**: By T=10.4s, the speaker may have already changed (manual button or new speech segment).

---

## TIMING ANALYSIS

### Audio Flow Latency
```
Microphone → WebSocket (20ms chunks)
  ↓ 0-20ms
WebSocket Handler
  ↓ <1ms (fork)
  ├─→ AudioBuffer.push() → <1ms
  └─→ SpeakerService.feed_audio() → <1ms
       ↓
      VAD (30ms frames) → 30ms per frame
       ↓
      Speech→Silence detection → 0-3000ms (depends on pauselocking mechanism. List appends are atomic in CPython, but timestamp ordering can be violated.

**Example**:
```
Timeline: [
  {"speaker": "user", "timestamp": 100.0},      # Manual
  {"speaker": "counterparty", "timestamp": 99.5}, # SpeakerService (late)
  {"speaker": "user", "timestamp": 100.5}       # ListenerAgent
]
```

### Race 3: Embedding Generation Delay
**Location**: `speaker_service.py:_classify_segment()`

**Timing**:
- VAD detects silence at T=10.0s
- Embedding generation starts at T=10.1s (thret_speaker`

**Problem**: The check at T=0.2s passes because `manual_override_until` was just set, but the classification was triggered BEFORE the button click.

**Fix**: Check `manual_override_until` at segment START time, not classification time.

### Race 2: Concurrent Timeline Writes
**Location**: Multiple writers to `session.speaker_timeline`

**Writers**:
1. `handle_speaker_identified()` - Manual button
2. `_classify_segment()` - SpeakerService
3. `_process_diarization()` - ListenerAgent

**Problem**: No  "user" if "user" not in existing else "counterparty"
```

---

## RACE CONDITIONS IDENTIFIED

### Race 1: Manual Override Timing
**Location**: `speaker_service.py:_classify_segment()` vs `negotiation_engine.py:handle_speaker_identified()`

**Scenario**:
1. T=0.0s: User clicks button → `manual_override_until = float('inf')`
2. T=0.1s: SpeakerService VAD detects speech→silence from 0.5s ago
3. T=0.2s: `_classify_segment()` checks `manual_override_until`
4. T=0.3s: Classification completes, overwrites `currenass = recent[-1]
            return last_class.get("speaker", "unknown")
    
    # Priority 2: Try Resemblyzer with last 3 seconds
    audio_segment = self.audio_buffer.get_segment(3.0, 0.0)
    if len(audio_segment) >= 16000:
        embedding = encoder.embed_utterance(audio_segment)
        similarity = float(np.dot(embedding, user_embedding))
        avg_similarity = ...  # Smoothing logic
        return "user" if avg_similarity >= 0.55 else "counterparty"
    
    # Priority 3: Positional fallback
    returnt_time - WINDOW_SECONDS + start_time,
        })
```

### Speaker Label Resolution
**File**: `backend/app/services/listener_agent.py` (lines 650-700)

```python
def _resolve_speaker_label(self, label: str, turn: dict) -> str:
    # Priority 1: Check SpeakerService confidence history
    confidence_history = getattr(self.session, 'speaker_confidence_history', [])
    if confidence_history:
        recent = [e for e in confidence_history if now - e.get("timestamp", 0) < 8.0]
        if recent:
            last_cl   speaker_label = turn.get("speaker", "")  # "Speaker 1" or "Speaker 2"
        text = turn.get("text", "")
        
        # Resolve to "user" or "counterparty"
        our_speaker = self._resolve_speaker_label(speaker_label, turn)
        
        # Update session state (RACE CONDITION!)
        self.session.current_speaker = our_speaker
        self.session.speaker_last_updated = current_time
        self.session.speaker_timeline.append({
            "speaker": our_speaker,
            "timestamp": currenries = [e for e in speaker_timeline if e.get("timestamp", 0) >= window_start_ts]
    
    # Call Flash for transcription + context extraction
    context = await asyncio.get_event_loop().run_in_executor(
        None, self._call_flash, audio_bytes, segments
    )
```

**Timing**: Flash call takes 2-5 seconds

### Diarization Processing
**File**: `backend/app/services/listener_agent.py` (lines 700-800)

```python
async def _process_diarization(self, diarization: list) -> None:
    for turn in diarization:
     50)

```python
async def _run_cycle(self) -> None:
    # Check for new audio
    current_duration = self.audio_buffer.duration_seconds
    new_audio_duration = current_duration - self._last_processed_duration
    
    if new_audio_duration < MIN_NEW_AUDIO:  # 4.0 seconds
        return
    
    # Grab 10-second window
    audio_bytes = self.audio_buffer.get_window(WINDOW_SECONDS)  # 10s
    
    # Build speaker timeline hint
    speaker_timeline = getattr(self.session, 'speaker_timeline', [])
    window_enttener_agent.py` (lines 450-470)

```python
async def _poll_loop(self) -> None:
    await asyncio.sleep(POLL_INTERVAL)  # 3 seconds
    
    while self._running:
        cycle_start = time.monotonic()
        await self._run_cycle()
        
        elapsed = time.monotonic() - cycle_start
        sleep_time = max(0.0, POLL_INTERVAL - elapsed)
        await asyncio.sleep(sleep_time)
```

**Timing**: Runs every 3 seconds

### Audio Extraction Cycle
**File**: `backend/app/services/listener_agent.py` (lines 480-5= "user" if similarity > threshold else "counterparty"
    
    # UPDATE SESSION STATE (RACE CONDITION!)
    self.session.current_speaker = label
    self.session.speaker_last_updated = time.time()
    self.session.speaker_confidence_history.append({...})
    self.session.speaker_timeline.append({"speaker": label, "timestamp": time.time()})
```

**Timing**: Embedding generation takes 100-300ms in thread pool

---

## Path 3: ListenerAgent (Context Extraction)

### Polling Loop
**File**: `backend/app/services/lise_until:
        if time.time() < self.session.manual_override_until:
            return self.session.current_speaker  # Use manual label
    
    # Generate embedding (CPU-intensive, runs in thread pool)
    encoder = VoiceEncoder.get_instance()
    segment_embedding = await loop.run_in_executor(
        None, encoder.embed_utterance, audio
    )
    
    # Calculate similarity
    similarity = float(np.dot(segment_embedding, self.session.user_embedding))
    
    # Apply threshold
    threshold = 0.70
    label peech:
        self.is_speech = False
        segment_audio = self.current_segment
        self.current_segment = b""
        asyncio.create_task(self._classify_segment(segment_audio))
```

**Timing**: Classification triggered on speech→silence (typically 0.5-3s after speech ends)

### Step 3: Resemblyzer Classification
**File**: `backend/app/services/speaker_service.py` (lines 107-180)

```python
async def _classify_segment(self, audio: bytes) -> str:
    # Check manual override
    if self.session.manual_overrid30ms frames (53 frames/second)

### Step 2: VAD Detection
**File**: `backend/app/services/speaker_service.py` (lines 72-105)

```python
def _process_frame(self, frame: bytes) -> None:
    is_speech = self.vad.is_speech(frame, self.SAMPLE_RATE)
    
    # Silence → Speech transition
    if is_speech and not self.is_speech:
        self.is_speech = True
        self.segment_start_time = time.time()
        self.current_segment = frame
    
    # Speech → Silence transition
    elif not is_speech and self.is_s

---

## Path 2: AUTO MODE (Resemblyzer-Based)

### Step 1: SpeakerService.feed_audio()
**File**: `backend/app/services/speaker_service.py` (lines 60-70)

```python
async def feed_audio(self, chunk: bytes) -> None:
    self.frame_buffer += chunk
    
    while len(self.frame_buffer) >= self.FRAME_SIZE:  # 960 bytes = 30ms
        frame = self.frame_buffer[:self.FRAME_SIZE]
        self.frame_buffer = self.frame_buffer[self.FRAME_SIZE:]
        self._process_frame(frame)
```

**Timing**: Processes audio in ion PERMANENTLY
session.manual_override_until = float('inf')

# Updates session state
session.current_speaker = speaker
session.speaker_last_updated = timestamp
session.speaker_timeline.append({"speaker": speaker, "timestamp": timestamp})
```

**Key Actions**:
1. Sets `manual_override_until = float('inf')` → blocks SpeakerService forever
2. Updates `current_speaker` immediately
3. Appends to `speaker_timeline` (used by ListenerAgent)
4. Transcribes previous speaker's segment via `listener_agent.transcribe_segment()`fer → ListenerAgent
- `speaker_service.feed_audio()` → VAD → Classification

---

## Path 1: MANUAL MODE (Button-Based)

### Step 1: Frontend Button Click
Frontend sends: `{"type": "SPEAKER_IDENTIFIED", "payload": {"speaker": "user", "timestamp": 1234567890}}`

### Step 2: NegotiationEngine.handle_speaker_identified()
**File**: `backend/app/services/negotiation_engine.py` (lines 300-380)

```python
speaker = payload.get("speaker", "user")
timestamp = timestamp_ms / 1000.0

# CRITICAL: Disables auto-recognit8-35: Audio routing fork
if "bytes" in message and message["bytes"]:
    if session.state == NegotiationState.ACTIVE:
        await NegotiationEngine.handle_audio_chunk(session, message["bytes"])
        
        # Fork to SpeakerService (AUTO MODE)
        if session.speaker_service:
            if settings.SPEAKER_RECOGNITION_ENABLED:
                await session.speaker_service.feed_audio(message["bytes"])
```

**Flow**: Every audio chunk goes to TWO places simultaneously:
- `handle_audio_chunk()` → AudioBuf Recognition System - Complete Flow Analysis

## Executive Summary

This system has **TWO PARALLEL SPEAKER RECOGNITION PATHS** that can conflict:

1. **MANUAL MODE** (Button-based) - Frontend sends SPEAKER_IDENTIFIED
2. **AUTO MODE** (Resemblyzer-based) - SpeakerService classifies automatically

**CRITICAL ISSUE**: Both paths write to the same session fields, creating race conditions.

---

## System Architecture

### Entry Point: WebSocket Handler
**File**: `backend/app/api/websocket.py`

```python
# Line 2# Speaker