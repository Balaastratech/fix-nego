# Debug: Why PerfectListener Isn't Transcribing

## Problem
- Audio is being spoken
- `SPEAKER_STOPPED` events are firing
- But NO transcripts appear
- No PerfectListener logs about turns detected

## Possible Causes

### 1. Audio Not Reaching PerfectListener
Check if `process_audio_chunk` is being called:
- Add log at start of `process_audio_chunk`
- Check if `overlap_window` is accumulating

### 2. Minimum Buffer Not Reached
PerfectListener needs 1 second (32000 bytes) before processing:
```python
if len(self.overlap_window) < 32000:
    logger.debug("Waiting for more audio...")
    return  # ← Exits early!
```

**This is likely the issue!** If audio chunks are small and infrequent, the buffer might never reach 32000 bytes.

### 3. VAD Not Detecting Speech
Even if buffer is full, VAD might not detect speech if:
- Audio level too low
- Threshold too high (currently 0.2)
- Wrong audio format

### 4. No Complete Turns Detected
VAD detects speech but waiting for silence to mark turn as "complete":
```python
turns = await self._segment_turns(streams)
if not turns:
    logger.debug("No complete turns detected yet")
    return  # ← No transcription!
```

## Quick Fix: Lower Minimum Buffer Size

The 32000 byte (1 second) minimum is too high for real-time transcription.

**Change in perfect_listener.py:**
```python
# OLD:
if len(self.overlap_window) < 32000:  # 1 second
    return

# NEW:
if len(self.overlap_window) < 16000:  # 0.5 seconds
    return
```

## Better Fix: Process on Timer

Instead of waiting for buffer size, process every N chunks:
```python
self.chunk_count += 1
if self.chunk_count % 10 == 0:  # Every 10 chunks (1 second at 100ms chunks)
    # Process accumulated audio
    ...
```

## Best Fix: Streaming VAD

Use a streaming VAD that processes incrementally instead of batch processing the entire buffer each time.

## Immediate Action

Add debug logging to see what's happening:

```python
# At start of process_audio_chunk
logger.info(f"🎤 Processing chunk: {len(chunk)} bytes, buffer: {len(self.overlap_window)} bytes")

# After checking minimum
if len(self.overlap_window) < 32000:
    logger.info(f"⏳ Waiting for more audio: {len(self.overlap_window)}/32000 bytes")
    return

# After segmentation
logger.info(f"🔍 Segmentation found {len(turns)} turns")
```

This will show us exactly where the pipeline is stopping.
