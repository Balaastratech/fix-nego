# Enrollment Timeout Issue Analysis

## What Your Logs Show

```
17:22:13.740 - Audio chunk: 1600 bytes, buffer: 264000 bytes (8.25s)
17:22:13.825 - Audio chunk: 1600 bytes, buffer: 265600 bytes (8.30s)
17:23:44.649 - Audio chunk: 1600 bytes, buffer: 267200 bytes (8.35s)  ← 91 SECOND GAP
17:23:44.659 - Enrollment timeout after 20 seconds
```

## The Problem

**Audio stopped arriving for 91 seconds**, but enrollment only waits 20 seconds before timing out.

### Timeline

```
T=0s:    Enrollment starts (start_time = 17:22:03)
T=10s:   Audio reaches 8.25s (17:22:13.740)
T=10.1s: Audio reaches 8.30s (17:22:13.825)
T=20s:   Timeout check triggers (17:22:23) - but no audio chunk arrives to trigger it!
T=101s:  Audio finally arrives (17:23:44.649)
         Timeout check runs: (17:23:44 - 17:22:03) = 101s > 20s
         → TIMEOUT!
```

## Root Cause

The timeout check is INSIDE `process_audio()`:

```python
async def process_audio(self, chunk: bytes) -> Optional[dict]:
    # ... accumulate audio ...
    
    # Check for timeout (20 seconds max for 10-second enrollment)
    if self.start_time and (time.time() - self.start_time) > 20.0:
        logger.warning("Enrollment timeout after 20 seconds")
        return TIMEOUT_ERROR
```

**Problem**: The timeout check only runs when audio arrives!

If audio stops flowing (client paused, network issue, etc.), the timeout never triggers
until the next chunk arrives - which could be 91 seconds later.

## Why Audio Stopped

Possible causes:
1. **Frontend paused** - User stopped speaking or closed mic
2. **Network issue** - WebSocket connection stalled
3. **Browser tab backgrounded** - Chrome throttles audio capture
4. **Client-side error** - Audio capture crashed silently

## The "Race Condition" Question

**NO, the dual processing paths are NOT the issue here.**

Your original concern was:
> "ListenerAgent uses its OWN diarization from Flash, ignoring SpeakerService!"

This is **FALSE**. The code shows:
- ListenerAgent reads `speaker_confidence_history` from SpeakerService
- It PRIORITIZES SpeakerService labels over its own Resemblyzer
- The dual paths are synchronized, not conflicting

The enrollment timeout is a **separate issue** - audio stopped flowing from the client.

## Solutions

### Option 1: Background Timeout Task (Recommended)
