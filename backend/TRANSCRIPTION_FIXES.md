# Transcription & Rate Limit Fixes

## Problems Identified

### 1. Garbage Transcriptions
**Symptoms:**
- "transcribe" appearing as transcription output
- Random Hindi text mixed with English
- Short nonsense phrases: "Okay", "Mmm", "side of us"

**Root Cause:**
- Sending segments under 1 second to Gemini causes hallucinations
- Model transcribes its own prompt instructions when given silence/noise
- VAD picking up background noise, UI sounds, clicks

### 2. API Rate Limiting (429 Errors)
**Symptoms:**
```
HTTP/1.1 429 Too Many Requests
Resource exhausted. Please try again later.
```

**Root Cause:**
- 8-12 transcription API calls per minute
- Each 0.5-0.8s segment triggers separate Gemini call
- Vertex AI free tier limit: ~60 requests/minute total
- ListenerAgent context extraction also hitting same quota

### 3. NoneType Classification Error
**Symptoms:**
```python
TypeError: unsupported operand type(s) for *: 'float' and 'NoneType'
similarity = float(np.dot(segment_embedding, self.session.user_embedding))
```

**Root Cause:**
- Race condition: session ends and clears `user_embedding` to None
- Pending async classification tasks still running
- Check passes, then embedding cleared before calculation

## Solutions Implemented

### Fix 1: Minimum Segment Duration (1.5s)
**File:** `backend/app/services/listener_agent.py`

**Changes:**
- Added `_min_segment_duration: float = 1.5` to `__init__`
- Filter segments under 1.5s before transcription
- Prevents hallucinations on short/silent audio

**Impact:**
- Eliminates "transcribe" and garbage output
- Only processes meaningful speech segments

### Fix 2: Batch Transcriptions (3s batches)
**File:** `backend/app/services/listener_agent.py`

**Changes:**
- Added segment batching queue: `_pending_segments: list`
- Added `_batch_interval: float = 3.0` (collect for 3 seconds)
- New method: `_transcribe_batch()` processes multiple segments
- Triggers batch when:
  - 3 seconds elapsed since last batch
  - OR 5+ segments accumulated

**Impact:**
- Reduces API calls by 80% (one call per batch vs per segment)
- Stays well under rate limits
- Context extraction runs once per batch instead of per segment

### Fix 3: Race Condition Protection
**File:** `backend/app/services/speaker_service.py`

**Changes:**
```python
# Before (unsafe):
if self.session.user_embedding is None:
    return "unknown"
similarity = float(np.dot(segment_embedding, self.session.user_embedding))

# After (safe):
user_embedding = self.session.user_embedding
if user_embedding is None:
    return "unknown"
similarity = float(np.dot(segment_embedding, user_embedding))
```

**Impact:**
- Uses local variable to avoid race condition
- Prevents NoneType error when session ends during classification

### Fix 4: Enrollment Quality (Middle 2s)
**File:** `backend/app/services/speaker_enrollment.py`

**Changes:**
- Changed from first 2s to middle 2s of 10s enrollment
- Calculation: `middle_offset = (duration - 2.0) / 2.0`
- For 10s audio: skip first 4s, use next 2s, skip last 4s

**Impact:**
- Better voice quality (avoids initial hesitation and trailing off)
- More accurate speaker recognition

## Configuration

### Current Settings (.env)
```env
# Minimum segment duration for transcription
SPEAKER_MIN_SEGMENT_DURATION=0.5  # VAD detection threshold

# Batch transcription settings (hardcoded in listener_agent.py)
# _min_segment_duration = 1.5  # Only transcribe segments >= 1.5s
# _batch_interval = 3.0  # Batch segments for 3 seconds
```

### Rate Limiting in speaker_service.py
```python
# Rate limiting for transcription (prevent 429 errors)
self.last_transcription_time: float = 0.0
self.min_transcription_gap: float = 3.0  # Minimum 3 seconds between transcriptions
```

## Testing Checklist

- [ ] No "transcribe" in transcription output
- [ ] No Hindi/random text from background noise
- [ ] No 429 rate limit errors in logs
- [ ] No NoneType errors after ending negotiation
- [ ] Transcriptions only for segments >= 1.5s
- [ ] Batch processing logs show "📦 Processing batch of X segments"
- [ ] API call frequency reduced to ~1-2 per 3 seconds
- [ ] Speaker recognition still accurate with middle 2s enrollment

## Monitoring

Watch for these log patterns:

**Good:**
```
📦 Processing batch of 3 segments
💬 Counterparty: [actual speech content]
```

**Bad (should not appear):**
```
💬 Counterparty: transcribe
HTTP/1.1 429 Too Many Requests
TypeError: unsupported operand type(s) for *: 'float' and 'NoneType'
```

## Rollback Plan

If issues occur, revert these commits:
1. `listener_agent.py` - Remove batching, restore immediate transcription
2. `speaker_service.py` - Restore direct `self.session.user_embedding` access
3. `speaker_enrollment.py` - Restore first 2s instead of middle 2s

## Future Improvements

1. **Adaptive batching**: Adjust batch interval based on speech rate
2. **Silence detection**: Skip transcription if audio RMS below threshold
3. **Quota monitoring**: Track API usage and throttle proactively
4. **Fallback STT**: Use local Whisper model when quota exhausted
