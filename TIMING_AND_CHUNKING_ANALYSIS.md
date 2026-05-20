# Timing & Chunking Problem - Deep Dive

## 🎯 YOUR SCENARIO (The Problem)

```
Timeline:
0s ────► You speak for 5 seconds
5s ────► 1 second silence
6s ────► You speak again for 2 seconds
8s ────► Counterparty speaks for 10 seconds
18s ───► End
```

## ❌ WHAT'S HAPPENING NOW (Why It Fails)

### Current System Flow:

```
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND: Sends audio in 100ms chunks continuously          │
│ ├─ Chunk 1 (0-0.1s)                                         │
│ ├─ Chunk 2 (0.1-0.2s)                                       │
│ ├─ Chunk 3 (0.2-0.3s)                                       │
│ └─ ... (streaming forever)                                  │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ BACKEND: AudioBuffer accumulates ALL chunks                 │
│ ├─ Rolling 90-second buffer                                 │
│ └─ No concept of "turns" or "sentences"                     │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ LISTENER AGENT: Polls every 3 seconds                       │
│                                                              │
│ Cycle 1 (at 3s):                                            │
│   ├─ Grabs last 10 seconds of audio (0-3s available)       │
│   ├─ Sends to Flash: "You speak for 3 seconds"             │
│   └─ Flash returns: "User: [partial sentence]"             │
│                                                              │
│ Cycle 2 (at 6s):                                            │
│   ├─ Grabs last 10 seconds (0-6s available)                │
│   ├─ Sends to Flash: SAME 3s + new 3s                      │
│   └─ Flash returns: "User: [same partial + more]"          │
│   └─ ❌ DEDUP FILTER: "Already sent this, skip!"           │
│                                                              │
│ Cycle 3 (at 9s):                                            │
│   ├─ Grabs last 10 seconds (0-9s available)                │
│   ├─ Sends to Flash: Overlapping audio AGAIN               │
│   └─ Flash confused: "Who said what? It's all mixed!"      │
└─────────────────────────────────────────────────────────────┘
```

## 🔴 THE 5 CRITICAL PROBLEMS

### Problem 1: **No Turn Boundaries**
```python
# listener_agent.py line 700
audio_bytes = self.audio_buffer.get_window(WINDOW_SECONDS)
```

**Issue:** You grab a **fixed 10-second window** regardless of who's speaking or when they started/stopped.

**Example:**
- At 9s, you grab audio from -1s to 9s
- This includes: Your voice (0-5s) + silence (5-6s) + your voice (6-8s) + counterparty (8-9s)
- Flash sees this as ONE BLOB and can't tell where turns begin/end

### Problem 2: **Overlapping Windows Create Duplicates**
```python
# Cycle 1 at 3s: Processes audio [0-3s]
# Cycle 2 at 6s: Processes audio [0-6s]  ← Contains [0-3s] AGAIN
# Cycle 3 at 9s: Processes audio [0-9s]  ← Contains [0-6s] AGAIN
```

**Result:** Flash transcribes the same audio 2-3 times, then your dedup filter blocks it.

### Problem 3: **MIN_NEW_AUDIO Waits Too Long**
```python
# listener_agent.py line 40
MIN_NEW_AUDIO = 4.0  # Must wait 4 seconds of NEW audio
```

**Your scenario:**
- 0-5s: You speak (5s new audio) ✅ Processes
- 5-6s: Silence (1s new audio) ❌ Waits
- 6-8s: You speak (2s new audio) ❌ Still waiting (only 3s total)
- 8-12s: Counterparty speaks (4s new audio) ✅ Finally processes

**Result:** Your second utterance (6-8s) gets bundled with counterparty's speech, confusing Flash.

### Problem 4: **No Sentence Boundary Detection**
```python
# There is NO mechanism to detect:
# - End of sentence (punctuation, intonation)
# - Natural pauses (>500ms silence)
# - Speaker turn completion
```

**Result:** Flash receives audio mid-sentence and produces partial transcripts.

### Problem 5: **Speaker Timeline is Retroactive**
```python
# listener_agent.py line 1030
self.session.speaker_timeline.append({
    "speaker": our_speaker,
    "timestamp": current_time - WINDOW_SECONDS + start_time,
})
```

**Issue:** Timeline is built AFTER transcription, not BEFORE. So Flash doesn't know who's speaking when it processes the audio.

---

## ✅ WHAT MECHANISMS EXIST (Partial Solutions)

### Mechanism 1: **Deduplication Filter**
```python
# listener_agent.py line 1001-1020
text_key = f"{our_speaker}:{text_normalized}"
if text_key in self._recent_transcript_hashes:
    logger.debug("Skipping exact duplicate")
    continue
```

**Purpose:** Prevent sending the same transcript twice.

**Problem:** Too aggressive - blocks legitimate repeated phrases.

### Mechanism 2: **Speaker Timeline**
```python
# negotiation_engine.py line 450
session.speaker_timeline.append({
    "speaker": speaker,
    "timestamp": timestamp,
})
```

**Purpose:** Track who spoke when for Resemblyzer.

**Problem:** Only updated on manual button clicks, not automatic detection.

### Mechanism 3: **Segment Audio Accumulation**
```python
# negotiation_engine.py line 280
session.current_segment_audio += raw_bytes
```

**Purpose:** Accumulate audio for the current speaker's turn.

**Problem:** Only works in manual mode (button clicks), not auto mode.

### Mechanism 4: **VAD in SpeakerService**
```python
# speaker_service.py line 90
is_speech = self.vad.is_speech(frame, self.SAMPLE_RATE)
```

**Purpose:** Detect speech vs silence.

**Problem:** Only used for speaker classification, NOT for turn segmentation.

---

## 🎯 WHAT'S MISSING (The Real Solution)

### Missing 1: **Turn-Based Segmentation**

You need a system that:
1. Detects when someone STARTS speaking (silence → speech)
2. Accumulates audio for that turn
3. Detects when they STOP speaking (speech → silence for >500ms)
4. Sends ONLY that complete turn to Flash

**Pseudocode:**
```python
class TurnSegmenter:
    def __init__(self):
        self.current_turn_audio = b""
        self.current_speaker = None
        self.silence_frames = 0
        self.SILENCE_THRESHOLD = 15  # 15 frames = 450ms
    
    def process_frame(self, frame, is_speech):
        if is_speech:
            self.current_turn_audio += frame
            self.silence_frames = 0
        else:
            self.silence_frames += 1
            
            # End of turn detected
            if self.silence_frames >= self.SILENCE_THRESHOLD:
                if len(self.current_turn_audio) > 0:
                    self.finalize_turn()
                    self.current_turn_audio = b""
    
    def finalize_turn(self):
        # Send complete turn to Flash for transcription
        asyncio.create_task(self.transcribe_turn(self.current_turn_audio))
```

### Missing 2: **Non-Overlapping Windows**

Instead of grabbing "last 10 seconds" every 3 seconds, you should:
1. Track what audio you've already processed
2. Only send NEW audio since last cycle
3. Never re-process the same audio twice

**Current (Wrong):**
```python
# Cycle 1: Process [0-10s]
# Cycle 2: Process [3-13s]  ← Overlaps with [3-10s] from Cycle 1
```

**Correct:**
```python
# Cycle 1: Process [0-10s], mark as processed
# Cycle 2: Process [10-20s], mark as processed
# No overlap!
```

### Missing 3: **Sentence Completion Detection**

Flash should indicate when a sentence is complete:
```json
{
  "diarization": [
    {
      "speaker": "Speaker 1",
      "text": "I want to buy this phone",
      "start_time": 0.0,
      "end_time": 2.5,
      "is_complete": true  ← NEW FIELD
    }
  ]
}
```

### Missing 4: **Buffering Incomplete Sentences**

If Flash returns an incomplete sentence, buffer it until the next cycle:
```python
self.incomplete_sentences = {}

def process_diarization(self, turns):
    for turn in turns:
        speaker = turn["speaker"]
        text = turn["text"]
        is_complete = turn.get("is_complete", True)
        
        # Append to previous incomplete sentence
        if speaker in self.incomplete_sentences:
            text = self.incomplete_sentences[speaker] + " " + text
            del self.incomplete_sentences[speaker]
        
        if is_complete:
            # Send complete sentence
            self.send_transcript(speaker, text)
        else:
            # Buffer for next cycle
            self.incomplete_sentences[speaker] = text
```

---

## 🔧 RECOMMENDED ARCHITECTURE CHANGE

### Option A: **Event-Driven Turn Segmentation** (Best)

```
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND: Sends audio chunks (100ms)                        │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ VAD SERVICE: Detects speech/silence boundaries              │
│ ├─ Silence → Speech: START new turn                         │
│ ├─ Speech → Silence (>500ms): END turn                      │
│ └─ Triggers: transcribe_turn(audio, speaker)                │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ TURN BUFFER: Accumulates audio per turn                     │
│ ├─ Turn 1: You (0-5s) → Complete                            │
│ ├─ Turn 2: You (6-8s) → Complete                            │
│ └─ Turn 3: Counterparty (8-18s) → Complete                  │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ TRANSCRIPTION: Process complete turns only                  │
│ ├─ Turn 1 → Flash → "I want to buy this phone"             │
│ ├─ Turn 2 → Flash → "for around $600"                      │
│ └─ Turn 3 → Flash → "The price is $800, final offer"       │
└─────────────────────────────────────────────────────────────┘
```

**Benefits:**
- ✅ No overlapping audio
- ✅ No duplicates
- ✅ Complete sentences
- ✅ Correct speaker attribution
- ✅ Faster (only process new turns)

### Option B: **Sliding Window with Checkpointing** (Simpler)

Keep current polling system but add:
1. Track last processed position
2. Only process NEW audio since checkpoint
3. Use longer windows (20s) to catch full sentences

```python
class ListenerAgent:
    def __init__(self):
        self._last_checkpoint = 0.0  # Seconds processed
    
    async def _run_cycle(self):
        current_duration = self.audio_buffer.duration_seconds
        new_audio_duration = current_duration - self._last_checkpoint
        
        if new_audio_duration < 2.0:
            return  # Wait for more audio
        
        # Grab audio from checkpoint to now
        audio = self.audio_buffer.get_segment(
            start_seconds_ago=current_duration - self._last_checkpoint,
            end_seconds_ago=0
        )
        
        # Process NEW audio only
        context = await self._call_flash(audio)
        
        # Update checkpoint
        self._last_checkpoint = current_duration
```

---

## 🚀 IMMEDIATE FIX (Quick & Dirty)

If you can't refactor the whole system, do this NOW:

### Fix 1: Increase Window Size
```python
# listener_agent.py line 39
WINDOW_SECONDS = 20  # Up from 10 - catches more complete sentences
```

### Fix 2: Reduce Polling Frequency
```python
# listener_agent.py line 38
POLL_INTERVAL = 6  # Up from 3 - reduces overlap
```

### Fix 3: Reduce MIN_NEW_AUDIO
```python
# listener_agent.py line 40
MIN_NEW_AUDIO = 2.0  # Down from 4.0 - faster response
```

### Fix 4: Disable Fragment Dedup
```python
# listener_agent.py line 1010
# Comment out this entire block:
# is_fragment = False
# for sent_key in self._recent_transcript_hashes:
#     ...
```

### Fix 5: Add Turn Boundary Hints to Flash
```python
# In _call_flash, add to prompt:
prompt += """
IMPORTANT: 
- If a sentence is cut off mid-word, mark is_complete=false
- If you hear a natural pause (>500ms), that's a turn boundary
- Don't transcribe the same audio twice - only NEW speech
"""
```

---

## 📊 TESTING YOUR SCENARIO

After fixes, your scenario should work like this:

```
Timeline:
0s ────► You speak for 5 seconds
         ├─ Cycle 1 (at 3s): Processes [0-3s] → "I want to buy..."
         └─ Cycle 2 (at 6s): Processes [3-6s] → "...this phone for"

6s ────► You speak again for 2 seconds
         └─ Cycle 3 (at 9s): Processes [6-9s] → "around $600"

8s ────► Counterparty speaks for 10 seconds
         ├─ Cycle 4 (at 12s): Processes [9-12s] → "The price is"
         └─ Cycle 5 (at 15s): Processes [12-15s] → "$800, final offer"
```

**Expected Results:**
- ✅ All speech captured
- ✅ No duplicates
- ✅ Correct speaker labels
- ✅ Complete sentences (or marked as incomplete)

---

## 🎬 NEXT STEPS

1. **Immediate**: Apply Quick Fixes 1-5 above
2. **Short-term**: Implement Option B (Sliding Window with Checkpointing)
3. **Long-term**: Implement Option A (Event-Driven Turn Segmentation)

The root cause is: **Your system processes overlapping time windows without tracking what's already been processed, causing confusion about turn boundaries and speaker attribution.**

The solution is: **Process audio in non-overlapping segments aligned with natural turn boundaries (detected by VAD silence detection).**
