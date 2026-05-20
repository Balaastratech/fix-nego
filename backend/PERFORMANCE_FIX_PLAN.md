# Performance Fix: Fast Automatic Transcription

## Current Problems

### 1. Tremendous Delay (9+ seconds)
```
21:02:52.906 - Speaker classified
21:03:02.128 - Transcript appears (9.2 second delay!)
```

**Bottlenecks:**
- Resemblyzer embedding: ~3-4s on CPU
- Gemini API transcription: ~5-6s
- Total: 9+ seconds per segment

### 2. Overlapping Speech Risk
If counterparty starts speaking within 1 second of user stopping, the audio segments might overlap or get misattributed because classification is still in progress.

## Root Cause

The system has TWO parallel speaker identification systems:

1. **SpeakerService** (slow, Resemblyzer-based)
   - Uses webrtcvad for VAD
   - Uses Resemblyzer for embeddings (SLOW on CPU)
   - Runs classification after each segment
   - Takes 3-4 seconds per segment

2. **PerfectListenerSystem** (fast, pyannote-based)
   - Uses pyannote VAD (faster, more accurate)
   - Uses WeSpeaker for embeddings (faster than Resemblyzer)
   - Already has full pipeline for diarization + transcription
   - Designed for real-time performance

**The problem**: Both systems are running, but SpeakerService is being used for transcription triggers, causing the delay.

## Solution Options

### Option A: Disable SpeakerService, Use Only PerfectListener (RECOMMENDED)

**Pros:**
- Single pipeline, no duplication
- Faster (pyannote + WeSpeaker)
- Already handles overlapping speech
- Designed for real-time use

**Cons:**
- Need to verify PerfectListener's speaker identification works with enrollment

**Implementation:**
1. Set `SPEAKER_RECOGNITION_ENABLED=false` in config
2. Ensure PerfectListener uses enrollment embedding for speaker ID
3. Test automatic mode with PerfectListener only

### Option B: Make SpeakerService Async & Non-Blocking

**Pros:**
- Keep existing architecture
- Gradual migration

**Cons:**
- Still slow (Resemblyzer is the bottleneck)
- Doesn't solve overlapping speech issue
- More complex code

### Option C: Hybrid - Fast VAD + Deferred Classification

**Pros:**
- Immediate transcription
- Classification happens in background

**Cons:**
- Transcripts might have wrong speaker labels initially
- Need to update labels retroactively
- Complex state management

## Recommended Implementation: Option A

### Step 1: Check PerfectListener Speaker ID

Verify that PerfectListener can use the enrollment embedding:

```python
# In perfect_listener.py
async def _identify_speaker(self, audio: bytes) -> str:
    """Use enrollment embedding if available, otherwise use WeSpeaker clustering."""
    if self.session.user_embedding is not None:
        # Use enrollment-based identification
        # Compare with user_embedding using cosine similarity
        pass
    else:
        # Fall back to WeSpeaker clustering
        pass
```

### Step 2: Disable SpeakerService in Auto Mode

```python
# In negotiation_engine.py handle_start()
# Remove or comment out SpeakerService initialization
# if settings.SPEAKER_RECOGNITION_ENABLED and session.speaker_mode == "auto":
#     # ... SpeakerService code ...
```

### Step 3: Ensure PerfectListener Transcribes on VAD Segments

PerfectListener should already do this, but verify the flow:
1. VAD detects speech → silence
2. Identify speaker (fast WeSpeaker or enrollment comparison)
3. Transcribe immediately
4. Send to frontend

### Step 4: Configuration

Add to `.env`:
```
# Disable slow SpeakerService in favor of PerfectListener
SPEAKER_RECOGNITION_ENABLED=false

# Ensure PerfectListener is active
PERFECT_LISTENER_ENABLED=true

# Fast VAD settings
PYANNOTE_MIN_DURATION_ON=0.25
PYANNOTE_MIN_DURATION_OFF=0.5

# Speaker identification threshold
WESPEAKER_THRESHOLD=0.70
```

## Expected Performance After Fix

- **Transcription delay**: 1-2 seconds (down from 9+ seconds)
- **Speaker identification**: <500ms (WeSpeaker on CPU)
- **Overlapping speech**: Handled by pyannote overlap detection
- **Accuracy**: Same or better (pyannote VAD is more accurate than webrtcvad)

## Testing Plan

1. Start negotiation in AUTO mode
2. User speaks: "Hello" → pause 1s → "I want $800" → pause 1s → "Is that fair?"
3. Verify all 3 segments transcribed within 1-2 seconds each
4. Counterparty speaks immediately after user stops
5. Verify no audio mixing or misattribution
6. Check speaker labels are correct

## Fallback Plan

If PerfectListener doesn't work well:
1. Keep SpeakerService for speaker ID only
2. Trigger transcription immediately on VAD stop (don't wait for classification)
3. Update speaker label retroactively when classification completes
4. This gives fast transcription with eventual correct labeling
