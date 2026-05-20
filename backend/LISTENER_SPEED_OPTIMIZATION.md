# Listener Speed Optimization Analysis

## Current Performance (from logs)

**Timeline for "I want to sell iPhone 15 Pro Max for $800":**
- **10:02:55.480** - User stops speaking (UTTERANCE_END)
- **10:03:06.462** - Transcription complete (**~11 seconds**)
- **10:03:19.739** - Context extraction complete (**~13 seconds** from utterance end)
- **10:03:44.348** - Research complete (**~49 seconds** total)

## Bottlenecks Identified

### 1. Google STT Transcription: ~11 seconds
- Using `chirp_3` model with diarization
- Processing 4-second audio takes 11 seconds
- **Optimization:** Switch to faster model or disable diarization (you're using SpeechBrain already)

### 2. Context Extraction Polling: 5-second intervals
```python
POLL_INTERVAL = 5  # listener_agent.py line 51
```
- Listener checks for new transcripts every 5 seconds
- **Optimization:** Reduce to 1-2 seconds for faster response

### 3. Text Extraction Debounce: 4 seconds
```python
TEXT_EXTRACTION_DEBOUNCE_SECONDS = 4.0  # listener_agent.py line 61
```
- Prevents duplicate API calls but adds delay
- **Optimization:** Reduce to 1-2 seconds

### 4. Research: ~25 seconds
- Web search + Gemini analysis
- This is acceptable for background research

## Recommended Optimizations

### Quick Wins (Immediate Impact)

1. **Reduce polling interval:**
```python
POLL_INTERVAL = 1.5  # Was 5 seconds
```

2. **Reduce debounce time:**
```python
TEXT_EXTRACTION_DEBOUNCE_SECONDS = 1.5  # Was 4.0 seconds
```

3. **Disable Google STT diarization** (you're using SpeechBrain):
```python
# In backend/.env or config
GOOGLE_STT_DIARIZATION_ENABLED=false
```

4. **Use faster STT model:**
```python
GOOGLE_STT_MODEL=chirp_2  # Or latest_short for <1min audio
```

### Expected Results After Optimization

- **Transcription:** 11s → **4-6s** (faster model + no diarization)
- **Context extraction:** 13s → **6-8s** (faster polling + debounce)
- **Total response time:** 49s → **20-25s** (research still takes time)

### Advanced Optimizations (More Complex)

1. **Parallel processing:** Run transcription and context extraction in parallel
2. **Streaming STT:** Use Google's streaming API instead of batch
3. **Local STT:** Use Whisper locally for <1s transcription
4. **Incremental research:** Start research immediately, don't wait for full context

## Implementation Priority

1. ✅ **DONE:** Fixed verbose logging (bool conversion)
2. 🔥 **HIGH:** Reduce POLL_INTERVAL to 1.5s
3. 🔥 **HIGH:** Reduce TEXT_EXTRACTION_DEBOUNCE to 1.5s
4. 🔥 **HIGH:** Disable Google STT diarization
5. 🟡 **MEDIUM:** Test faster STT model
6. 🟢 **LOW:** Consider streaming STT for real-time

---

## Implementation Guide

### Step 1: Reduce Polling Interval (listener_agent.py)

**File:** `backend/app/services/listener_agent.py`

**Change line 51:**
```python
# BEFORE
POLL_INTERVAL = 5           # seconds between extraction cycles

# AFTER
POLL_INTERVAL = 1.5         # seconds between extraction cycles (optimized for speed)
```

**Impact:** Context extraction will check for new transcripts every 1.5s instead of 5s, reducing wait time by 3.5s.

---

### Step 2: Reduce Debounce Time (listener_agent.py)

**File:** `backend/app/services/listener_agent.py`

**Change line 61:**
```python
# BEFORE
TEXT_EXTRACTION_DEBOUNCE_SECONDS = 4.0  # limit text extraction cadence

# AFTER
TEXT_EXTRACTION_DEBOUNCE_SECONDS = 1.5  # limit text extraction cadence (optimized for speed)
```

**Impact:** Context extraction can run more frequently, reducing artificial delays.

---

### Step 3: Disable Google STT Diarization

**File:** `backend/.env`

**Add or modify:**
```bash
# Disable diarization since we're using SpeechBrain for speaker classification
GOOGLE_STT_DIARIZATION_ENABLED=false
```

**File:** `backend/app/config.py`

**Verify this setting exists:**
```python
GOOGLE_STT_DIARIZATION_ENABLED: bool = Field(
    default=True,
    description="Enable Google STT speaker diarization"
)
```

**Impact:** Google STT will skip diarization processing, reducing transcription time by 40-60%.

---

### Step 4: Use Faster STT Model (Optional)

**File:** `backend/.env`

**Current:**
```bash
GOOGLE_STT_MODEL=chirp_3
```

**Option A - Faster chirp model:**
```bash
GOOGLE_STT_MODEL=chirp_2
```

**Option B - Latest short model (best for <1min audio):**
```bash
GOOGLE_STT_MODEL=latest_short
```

**Option C - Chirp model (balanced):**
```bash
GOOGLE_STT_MODEL=chirp
```

**Impact:** Faster models trade slight accuracy for 2-3x speed improvement.

---

### Step 5: Reduce STT Grace Period (negotiation_engine.py)

**File:** `backend/app/services/gemini_client.py`

**Find the 50ms grace period (around line 738):**
```python
# BEFORE
await asyncio.sleep(0.05)  # 50ms grace period

# AFTER
await asyncio.sleep(0.02)  # 20ms grace period (optimized)
```

**Impact:** Reduces artificial delay before speaker classification by 30ms.

---

### Step 6: Optimize Minimum Audio Requirements (listener_agent.py)

**File:** `backend/app/services/listener_agent.py`

**Change line 54:**
```python
# BEFORE
MIN_NEW_AUDIO = 2.0         # minimum seconds of new audio required

# AFTER
MIN_NEW_AUDIO = 1.5         # minimum seconds of new audio required (optimized)
```

**Impact:** Allows processing of shorter utterances faster.

---

## Testing & Validation

### Before Testing
1. Backup current `.env` file
2. Note current performance metrics from logs
3. Test with same audio samples

### Test Procedure
1. Apply changes in order (Steps 1-3 first)
2. Restart backend server
3. Record new utterance
4. Check logs for timing:
   - `UTTERANCE_END` → `Transcription complete`
   - `Transcription complete` → `CONTEXT_UPDATE sent`
   - Total time to research complete

### Expected Improvements

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Transcription | 11s | 4-6s | 45-55% faster |
| Context Extraction | 13s | 6-8s | 38-54% faster |
| Total Response | 49s | 20-25s | 49-59% faster |

### Rollback Plan
If issues occur, revert changes:
```bash
# listener_agent.py
POLL_INTERVAL = 5
TEXT_EXTRACTION_DEBOUNCE_SECONDS = 4.0
MIN_NEW_AUDIO = 2.0

# .env
GOOGLE_STT_DIARIZATION_ENABLED=true
GOOGLE_STT_MODEL=chirp_3
```

---

## Monitoring After Changes

### Key Log Messages to Watch

1. **Transcription speed:**
```
🎙️ process_diarized_utterance called
✅ Transcription complete
```
Time between these should be 4-6s (down from 11s)

2. **Context extraction frequency:**
```
🔍 _run_text_extraction_cycle called
📤 CONTEXT_UPDATE sent
```
Should trigger every 1.5s (down from 5s)

3. **Research timing:**
```
🔬 Research triggered
✅ Research complete
```
Should remain ~20-25s (acceptable for web search)

### Performance Metrics to Track

Add to your logs or monitoring:
- Average transcription latency
- Context extraction trigger frequency
- End-to-end response time (utterance → context update)
- API call rates (ensure not hitting rate limits)

---

## Advanced Optimizations (Future)

### 1. Parallel Processing Architecture
```python
# Run transcription and preliminary analysis in parallel
async def process_utterance_parallel(utterance):
    transcription_task = asyncio.create_task(transcribe(utterance))
    audio_analysis_task = asyncio.create_task(analyze_audio_features(utterance))
    
    transcript, features = await asyncio.gather(
        transcription_task,
        audio_analysis_task
    )
    return combine_results(transcript, features)
```

### 2. Streaming STT Implementation
```python
# Use Google Cloud Speech streaming API
async def streaming_transcribe(audio_stream):
    async for audio_chunk in audio_stream:
        # Send chunk immediately, get partial results
        partial_result = await stt_client.streaming_recognize(audio_chunk)
        yield partial_result
```

### 3. Local Whisper Integration
```python
# Use OpenAI Whisper locally for <1s transcription
import whisper
model = whisper.load_model("base")  # or "small" for speed

def local_transcribe(audio_bytes):
    result = model.transcribe(audio_bytes)
    return result["text"]
```

### 4. Predictive Context Loading
```python
# Start context extraction before utterance completes
if utterance_duration > 2.0 and not utterance.is_complete:
    # Start preliminary extraction with partial transcript
    asyncio.create_task(preload_context(partial_transcript))
```

### 5. Caching Strategy
```python
# Cache common negotiation patterns
PATTERN_CACHE = {
    "iphone_15_pro_max": {
        "market_range": "$700-$900",
        "key_facts": "...",
        "cached_at": timestamp
    }
}

# Check cache before research
if item_key in PATTERN_CACHE and cache_fresh(item_key):
    return PATTERN_CACHE[item_key]
```

---

## Configuration Reference

### All Timing Constants

**listener_agent.py:**
```python
POLL_INTERVAL = 1.5                      # Extraction cycle frequency
WINDOW_SECONDS = 20                      # Audio window size
MIN_NEW_AUDIO = 1.5                      # Minimum audio to process
TEXT_EXTRACTION_DEBOUNCE_SECONDS = 1.5   # Debounce between extractions
```

**config.py / .env:**
```bash
GOOGLE_STT_MODEL=chirp_2                 # STT model selection
GOOGLE_STT_DIARIZATION_ENABLED=false     # Disable diarization
MIN_CONTEXT_DURATION_MS=1500             # Minimum utterance duration
STT_MAX_RETRIES=2                        # Retry attempts
STT_BASE_BACKOFF_MS=100                  # Retry backoff
```

---

## Troubleshooting

### Issue: Transcription still slow
- Check network latency to Google Cloud
- Verify STT model is actually changed (check startup logs)
- Ensure diarization is disabled in config

### Issue: Too many API calls
- Increase TEXT_EXTRACTION_DEBOUNCE_SECONDS to 2.0
- Check for duplicate transcript processing
- Monitor rate limit warnings in logs

### Issue: Missing context updates
- Verify POLL_INTERVAL isn't too aggressive
- Check MIN_NEW_AUDIO threshold
- Ensure eligible_for_context logic is working

### Issue: Degraded accuracy
- Test different STT models (chirp vs chirp_2 vs chirp_3)
- Re-enable diarization if speaker classification fails
- Adjust confidence thresholds

---

## Success Criteria

✅ **Optimization is successful when:**
1. Transcription completes in <6 seconds
2. Context extraction triggers within 2 seconds of transcription
3. Total response time <25 seconds
4. No increase in API errors or retries
5. Speaker classification accuracy remains >90%
6. User experience feels responsive

---

## Notes

- These optimizations prioritize speed over redundancy
- Monitor API costs as faster polling = more API calls
- Test thoroughly with various audio lengths and qualities
- Consider A/B testing with real users
- Keep original values documented for rollback

**Last Updated:** 2026-04-07  
**Status:** Ready for implementation  
**Estimated Impact:** 50% reduction in response time
