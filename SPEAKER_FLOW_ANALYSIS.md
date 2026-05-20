# Speaker Recognition System Flow Analysis

## System Overview

This system has TWO parallel speaker identification paths:
1. **Manual Mode** (button-based) - User clicks buttons to identify speakers
2. **Auto Mode** (voice recognition) - Resemblyzer AI identifies speakers automatically

## Critical Finding: Race Conditions & Timing Issues

### 🚨 MAJOR ISSUE #1: Dual Processing Paths Create Conflicts

**Location**: `websocket.py` lines 30-40 + `listener_agent.py` lines 200-250

**The Problem**:
```python
# In websocket.py - EVERY audio chunk goes to TWO places:
if session.state == NegotiationState.ACTIVE:
    await NegotiationEngine.handle_audio_chunk(session, message["bytes"])  # Path 1
    
    if session.speaker_service:  # Path 2 (runs in parallel!)
        await session.speaker_service.feed_audio(message["bytes"])
```

**Race Condition**:
- Audio chunk arrives at time T
- Path 1: Goes to AudioBuffer → ListenerAgent processes at T+3s (POLL_INTERVAL)
- Path 2: Goes to SpeakerService → Processes immediately at T+0.03s (30ms frames)
- Result: SpeakerService labels speaker BEFORE ListenerAgent extracts context
- But ListenerAgent uses its OWN diarization from Flash, ignoring SpeakerService!

### 🚨 MAJOR ISSUE #2: ListenerAgent Ignores SpeakerService

**Location**: `listener_agent.py` lines 550-650 (`_process_diarization`)

