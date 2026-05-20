# 6-Second Pipeline Implementation Plan

**Goal:** Reduce total pipeline time from 8-10 seconds to under 6 seconds  
**Date:** 2026-04-07  
**Status:** Implementation Ready

---

## EXECUTIVE SUMMARY

You can achieve a 6-second pipeline (user starts speaking → context injected) by implementing streaming STT with parallel speaker identification. Your current system is 80% ready - you just need to add streaming capabilities and optimize the injection timing.

**Current Performance:** 8-10 seconds (from user STOPS speaking)  
**Target Performance:** 4-5 seconds (from user STARTS speaking)  
**Improvement:** 50-60% faster

---

## WHY THIS WORKS

### The Physics Problem
- Biometric speaker ID requires 2-3 seconds of audio (minimum)
- No AI can identify a speaker from <2 seconds with high accuracy
- This is a physics limitation, not a software problem

### The Solution
Instead of waiting for everything sequentially, we process in parallel:

**Current (Sequential):**
```
User speaks (2s) → STT batch (6s) → Speaker ID (0s, included) → Context (2s) = 10s total
```

**Target (Parallel):**
```
User speaks (2s) → STT streaming (1s first result)
                 → Speaker buffer (2.5s) → Speaker ID (1s)
                 → Intent detection (0.2s)
                 → Inject (0.5s)
                 = 5s total from START speaking
```

### Why Your System Is Ready
1. You already have SpeechBrain (fast, accurate, local)
2. You already have Google STT integration (just need streaming mode)
3. You already have Gemini Live API (just need earlier injection)
4. You already have audio buffering (just need parallel processing)

---

## WHAT YOU'RE BUILDING

### Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ AUDIO INPUT (from frontend)                                  │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────────────┐
│ AUDIO ROUTER (negotiation_engine.handle_audio_chunk)        │
│ - Receives 100ms chunks                                      │
│ - Routes to multiple processors                              │
└────┬────────────────┬────────────────┬─────────────────────┘
     │                │                │
     ↓                ↓                ↓
┌─────────┐    ┌──────────┐    ┌─────────────┐
│ Gemini  │    │ Streaming│    │   Speaker   │
│  Live   │    │   STT    │    │   Buffer    │
│  API    │    │ Service  │    │  Manager    │
└─────────┘    └────┬─────┘    └──────┬──────┘
                    │                  │
                    ↓                  ↓
              ┌──────────┐      ┌──────────┐
              │ Partial  │      │ 2.5s     │
              │Transcript│      │ Audio    │
              │ (0.5s)   │      │ Buffer   │
              └────┬─────┘      └────┬─────┘
                   │                 │
                   ↓                 ↓
              ┌──────────┐      ┌──────────┐
              │  Intent  │      │SpeechBrain│
              │Classifier│      │ Speaker  │
              │(Flash-8B)│      │   ID     │
              └────┬─────┘      └────┬─────┘
                   │                 │
                   └────────┬────────┘
                            ↓
                   ┌─────────────────┐
                   │ Context Builder │
                   │ - Transcript    │
                   │ - Speaker       │
                   │ - Intent        │
                   └────────┬────────┘
                            ↓
                   ┌─────────────────┐
                   │ Context Injector│
                   │ → Gemini Live   │
                   └─────────────────┘
```

---

## IMPLEMENTATION PHASES

### PHASE 1: Intent Classification (1 week)
**Goal:** Reduce research trigger from 8-10s to 6-8s  
**Complexity:** LOW  
**Risk:** LOW  
**Cost Impact:** +4% ($0.10 per 1000 messages)

**What You're Adding:**
- Intent classifier using Gemini 1.5 Flash-8B
- Immediate research triggering after transcript (not after context)
- Parallel context extraction and research

**Why This First:**
- Easiest to implement
- Lowest risk
- Immediate 2-3s improvement
- Tests the Flash-8B integration
- No frontend changes needed

**Files to Create:**
- `backend/app/services/intent_classifier.py`

**Files to Modify:**
- `backend/app/services/listener_agent.py` (add intent trigger)
- `backend/app/config.py` (add intent settings)
- `backend/.env` (add intent config)

**Expected Result:**
- Research starts 2-3s earlier
- Total time: 6-8s (down from 8-10s)
- 90%+ accuracy on research triggers

---

### PHASE 2: Streaming STT + Speaker Buffer (2 weeks)
**Goal:** Reduce total time from 6-8s to 4-5s  
**Complexity:** MEDIUM  
**Risk:** MEDIUM  
**Cost Impact:** +20% ($0.50 per 1000 messages)

**What You're Adding:**
- Streaming STT service (Google Cloud Speech V2 streaming API)
- Speaker buffer manager (accumulates 2.5s for SpeechBrain)
- Parallel processing coordinator
- Retroactive speaker labeling

**Why This Second:**
- Requires Phase 1 foundation
- More complex (streaming connections)
- Bigger performance gain (4-5s improvement)
- Tests parallel processing architecture

**Files to Create:**
- `backend/app/services/streaming_stt_service.py`
- `backend/app/services/speaker_buffer_manager.py`
- `backend/app/services/parallel_processor.py`

**Files to Modify:**
- `backend/app/services/negotiation_engine.py` (route to streaming)
- `backend/app/services/listener_agent.py` (handle partial transcripts)
- `backend/app/config.py` (add streaming settings)
- `backend/.env` (add streaming config)

**Expected Result:**
- First transcript visible: 0.5-1s after user starts speaking
- Speaker ID appears: 3-4s after user starts speaking
- Context injected: 4-5s after user starts speaking
- Total time: 4-5s (down from 6-8s)

---

### PHASE 3: Frontend Updates (1 week)
**Goal:** Show real-time transcripts and handle retroactive speaker updates  
**Complexity:** MEDIUM  
**Risk:** MEDIUM  
**Cost Impact:** None (no additional API costs)

**What You're Adding:**
- Partial transcript display
- Retroactive speaker label updates
- Smooth UI transitions
- Loading states for speaker identification

**Why This Last:**
- Requires stable Phase 2 backend
- Frontend changes are risky
- User-facing changes need careful testing
- Can be A/B tested

**Files to Create:**
- `frontend/src/hooks/useStreamingTranscripts.ts`
- `frontend/src/components/PartialTranscript.tsx`

**Files to Modify:**
- `frontend/src/components/TranscriptDisplay.tsx`
- `frontend/src/contexts/WebSocketContext.tsx`
- `frontend/src/types/transcript.ts`

**Expected Result:**
- Users see text appear as they speak
- Speaker labels appear 2-3s later with smooth animation
- Real-time feel to the conversation
- No jarring UI updates

---

## TECHNICAL DECISIONS

### Decision 1: Keep SpeechBrain (Don't Use Google Speaker Recognition)

**Why SpeechBrain:**
- Already integrated and working
- Fast (local processing, no API calls)
- Free (no per-request costs)
- Accurate enough (90%+ with 2-3s audio)
- You control the model and thresholds

**Why NOT Google Speaker Recognition:**
- 2-3x more expensive ($0.72 vs $0.00 per 1000 messages)
- Same 2-3s audio requirement (no speed benefit)
- Requires user enrollment flow (UX friction)
- API dependency (network latency)
- No accuracy benefit for 2-speaker scenarios

**Verdict:** Keep SpeechBrain, save money and complexity

---

### Decision 2: Use Streaming STT (Not Batch)

**Why Streaming:**
- Partial results every 0.5-1s (feels real-time)
- Final results in 3-4s (vs 6-8s batch)
- Better user experience (see text as you speak)
- Enables parallel processing

**Why NOT Batch:**
- 6-8s latency (too slow for 6s target)
- No partial results (feels laggy)
- Sequential processing only

**Trade-offs:**
- Streaming costs 1.5x more ($0.36 vs $0.24 per 1000 messages)
- More complex (WebSocket management)
- Requires frontend changes

**Verdict:** Use streaming for speed, accept higher cost

---

### Decision 3: Use Flash-8B for Intent (Not Regex)

**Why Flash-8B:**
- Smart classification (understands context)
- Fast (<200ms latency)
- Cheap ($0.0375 per 1M tokens)
- Reduces false research triggers by 50%+

**Why NOT Regex:**
- Dumb pattern matching (many false positives)
- Can't understand context
- Brittle (breaks with variations)

**Trade-offs:**
- Flash-8B adds 200ms latency
- Adds API dependency
- Small cost increase

**Verdict:** Use Flash-8B for accuracy, 200ms is acceptable

---

### Decision 4: Inject Early (Don't Wait for Full Context)

**Why Inject Early:**
- Context available 4-5s after user starts speaking
- AI can start using info immediately
- Faster response to user

**Why NOT Wait:**
- Full context extraction takes 8-10s
- Research may arrive too late
- User experience suffers

**Trade-offs:**
- Context may be incomplete (missing some details)
- May need to inject updates later

**Verdict:** Inject early, update if needed

---

## BOTTLENECKS & SOLUTIONS

### Bottleneck 1: Speaker ID Requires 2-3s Audio
**Problem:** Physics limitation - can't identify speaker from <2s audio  
**Impact:** Speaker label always lags 2-3s behind transcript  
**Solution:** Show "unknown" speaker initially, update retroactively  
**Implementation:** Frontend handles retroactive updates with smooth animation

### Bottleneck 2: Streaming STT Complexity
**Problem:** More complex than batch (WebSocket, partial results, state management)  
**Impact:** More code, more bugs, harder to debug  
**Solution:** Extensive logging, feature flags, gradual rollout  
**Implementation:** Keep batch as fallback, add streaming as opt-in

### Bottleneck 3: Network Latency
**Problem:** Streaming requires constant connection to Google Cloud  
**Impact:** Network issues cause delays or failures  
**Solution:** Use regional endpoints, implement retry logic, fallback to batch  
**Implementation:** Monitor connection health, auto-switch to batch on failure

### Bottleneck 4: Cost Increase
**Problem:** Streaming STT is 1.5-2x more expensive  
**Impact:** Budget constraints, higher per-message cost  
**Solution:** Monitor usage, implement rate limiting, optimize for cost  
**Implementation:** Only stream user-facing transcripts, batch for background

### Bottleneck 5: Frontend State Complexity
**Problem:** Handling partial + final + retroactive updates is complex  
**Impact:** UI bugs, state inconsistencies, poor UX  
**Solution:** Clear state machine, extensive testing, phased rollout  
**Implementation:** Use TypeScript for type safety, add comprehensive tests

---

## RISK MITIGATION

### Risk 1: Streaming STT Fails
**Probability:** Medium  
**Impact:** High (no transcripts)  
**Mitigation:** Keep batch STT as fallback, auto-switch on failure  
**Detection:** Monitor streaming connection health, error rates  
**Recovery:** Graceful degradation to batch mode

### Risk 2: Speaker ID Accuracy Drops
**Probability:** Low  
**Impact:** Medium (wrong speaker labels)  
**Mitigation:** Keep SpeechBrain thresholds conservative, add confidence scores  
**Detection:** Monitor speaker classification confidence, user reports  
**Recovery:** Adjust thresholds, add manual override

### Risk 3: Cost Overruns
**Probability:** Medium  
**Impact:** Medium (budget issues)  
**Mitigation:** Set budget alerts, implement rate limiting, monitor usage  
**Detection:** Daily cost reports, usage dashboards  
**Recovery:** Reduce streaming usage, optimize batch processing

### Risk 4: Frontend Bugs
**Probability:** Medium  
**Impact:** Medium (poor UX)  
**Mitigation:** Extensive testing, phased rollout, A/B testing  
**Detection:** User reports, error monitoring, session recordings  
**Recovery:** Quick rollback, fix bugs, re-deploy

### Risk 5: API Rate Limits
**Probability:** Low  
**Impact:** High (service degradation)  
**Mitigation:** Request quota increases, implement backoff, queue requests  
**Detection:** Monitor API quota usage, rate limit errors  
**Recovery:** Implement exponential backoff, queue overflow handling

---

## SUCCESS METRICS

### Performance Metrics
- **First transcript visible:** <1s after user starts speaking
- **Speaker ID appears:** <4s after user starts speaking
- **Context injected:** <5s after user starts speaking
- **Total pipeline time:** <6s (target: 4-5s)

### Quality Metrics
- **Transcript accuracy:** >95% (same as batch)
- **Speaker ID accuracy:** >90% (same as current)
- **Intent classification accuracy:** >90% (new)
- **False research triggers:** <10% (down from 30%+)

### Reliability Metrics
- **Streaming uptime:** >99.5%
- **Fallback activation rate:** <1%
- **Error rate:** <1%
- **API timeout rate:** <0.5%

### Cost Metrics
- **Cost per 1000 messages:** <$3.50 (up from $2.74)
- **Cost increase:** <30%
- **ROI:** 50% faster response time for 30% cost increase

### User Experience Metrics
- **Perceived responsiveness:** User survey (target: 8/10)
- **Conversation flow:** Smoother, more natural
- **AI relevance:** Better context usage
- **User satisfaction:** Improved ratings

---

## IMPLEMENTATION TIMELINE

### Week 1: Phase 1 (Intent Classification)
**Days 1-2:** Create intent classifier service  
**Days 3-4:** Integrate into listener agent  
**Day 5:** Testing and deployment

**Deliverables:**
- Intent classifier service working
- Research triggers 2-3s faster
- Tests passing
- Deployed to staging

---

### Week 2-3: Phase 2 (Streaming STT)
**Days 1-3:** Create streaming STT service  
**Days 4-6:** Create speaker buffer manager  
**Days 7-9:** Integrate parallel processing  
**Day 10:** Testing and deployment

**Deliverables:**
- Streaming STT working
- Speaker buffer working
- Parallel processing working
- Tests passing
- Deployed to staging

---

### Week 4: Phase 3 (Frontend)
**Days 1-2:** Create streaming transcript hooks  
**Days 3-4:** Update UI components  
**Day 5:** Testing and deployment

**Deliverables:**
- Frontend handles partial transcripts
- Retroactive speaker updates working
- UI smooth and responsive
- Tests passing
- Deployed to production

---

## ROLLOUT STRATEGY

### Stage 1: Internal Testing (Week 1)
- Deploy Phase 1 to staging
- Test with internal team
- Measure performance improvements
- Fix bugs

### Stage 2: Beta Users (Week 2-3)
- Deploy Phase 2 to staging
- Invite 10-20 beta users
- Gather feedback
- Monitor metrics
- Fix issues

### Stage 3: Gradual Rollout (Week 4)
- Deploy Phase 3 to production
- Enable for 10% of users
- Monitor for 48 hours
- Increase to 50% if stable
- Full rollout if no issues

### Stage 4: Monitoring (Ongoing)
- Monitor performance metrics daily
- Track cost impact weekly
- Gather user feedback monthly
- Optimize based on data

---

## ROLLBACK PLAN

### If Phase 1 Fails:
1. Set `INTENT_CLASSIFICATION_ENABLED=false` in `.env`
2. Restart backend
3. System reverts to context-based research triggering
4. No data loss, no downtime

### If Phase 2 Fails:
1. Set `STREAMING_STT_ENABLED=false` in `.env`
2. Restart backend
3. System reverts to batch STT
4. Slight performance degradation but stable

### If Phase 3 Fails:
1. Revert frontend deployment
2. Backend continues working (backward compatible)
3. Users see batch transcripts (slower but stable)
4. No backend changes needed

---

## COST ANALYSIS

### Current System Costs (per 1000 messages)
- Google STT (batch): $0.24
- SpeechBrain (local): $0.00
- Gemini Live API: $2.00
- Market Research: $0.50
- **Total: $2.74**

### Phase 1 Costs (per 1000 messages)
- Google STT (batch): $0.24
- SpeechBrain (local): $0.00
- Gemini Live API: $2.00
- Market Research: $0.50
- Flash-8B (intent): $0.10
- **Total: $2.84 (+4%)**

### Phase 2 Costs (per 1000 messages)
- Google STT (streaming): $0.36
- SpeechBrain (local): $0.00
- Gemini Live API: $2.00
- Market Research: $0.50
- Flash-8B (intent): $0.10
- **Total: $2.96 (+8%)**

### Phase 3 Costs (per 1000 messages)
- No additional API costs
- **Total: $2.96 (same as Phase 2)**

### ROI Calculation
- **Cost increase:** $0.22 per 1000 messages (8%)
- **Performance improvement:** 50% faster (8-10s → 4-5s)
- **User experience:** Significantly better (real-time feel)
- **Competitive advantage:** Faster than competitors
- **Verdict:** Worth the investment

---

## DEPENDENCIES

### External Services
- Google Cloud Speech-to-Text V2 (streaming API)
- Google Gemini 1.5 Flash-8B (intent classification)
- Google Gemini Live API (context injection)
- Google Search API (market research)

### Internal Services
- SpeechBrain (speaker recognition)
- Audio buffer (rolling window)
- Listener agent (context extraction)
- Negotiation engine (audio routing)

### Infrastructure
- WebSocket connections (frontend ↔ backend)
- Streaming connections (backend ↔ Google)
- Thread-safe audio buffers
- Async task management

---

## TESTING STRATEGY

### Unit Tests
- Intent classifier accuracy (>90%)
- Streaming STT connection handling
- Speaker buffer accumulation
- Parallel processing coordination

### Integration Tests
- End-to-end pipeline timing
- Fallback mechanisms
- Error handling
- Retry logic

### Performance Tests
- Latency under load
- Concurrent user handling
- Memory usage
- CPU usage

### User Acceptance Tests
- Real conversations
- Edge cases (interruptions, overlaps)
- Network issues
- Long conversations

---

## MONITORING & ALERTING

### Key Metrics to Monitor
- Pipeline latency (p50, p95, p99)
- Streaming STT uptime
- Speaker ID accuracy
- Intent classification accuracy
- Error rates
- API costs
- User satisfaction

### Alerts to Configure
- Pipeline latency >10s (warning)
- Streaming STT failure rate >5% (critical)
- Speaker ID accuracy <80% (warning)
- API error rate >2% (critical)
- Daily cost >$500 (warning)

### Dashboards to Create
- Real-time performance dashboard
- Cost tracking dashboard
- Error rate dashboard
- User experience dashboard

---

## FINAL RECOMMENDATION

### Start with Phase 1 Only
**Why:**
- Low risk, low complexity
- Immediate 2-3s improvement
- Tests the architecture
- Minimal cost increase (+4%)
- No frontend changes

**Timeline:** 1 week  
**Cost:** +$0.10 per 1000 messages  
**Result:** 6-8s total (down from 8-10s)

### Evaluate Phase 2 After 2 Weeks
**Decision criteria:**
- Is 6-8s fast enough for users?
- Can budget handle 8% cost increase?
- Does team have bandwidth for complexity?
- Are Phase 1 metrics stable?

**If YES to all:** Proceed to Phase 2  
**If NO to any:** Stop at Phase 1

### Delay Phase 3 Until Phase 2 Stable
**Why:**
- Frontend changes are risky
- Need stable backend first
- Can A/B test carefully

**Timeline:** 2-4 weeks after Phase 2  
**Cost:** No additional API cost  
**Result:** Real-time UX

---

## CONCLUSION

You can achieve a 6-second pipeline by implementing streaming STT with parallel speaker identification. Your system is 80% ready - you just need to add streaming capabilities and optimize injection timing.

**Recommended path:**
1. Start with Phase 1 (intent classification) - 1 week, low risk
2. Measure results for 2 weeks
3. Decide on Phase 2 (streaming STT) based on data
4. Implement Phase 3 (frontend) only if Phase 2 is stable

**Expected outcome:**
- Phase 1 only: 6-8s (30% faster, easy)
- Phase 1+2: 4-5s (50% faster, medium complexity)
- Phase 1+2+3: 4-5s with real-time UX (best experience, high complexity)

**My recommendation:** Start Phase 1 this week, evaluate in 2 weeks, then decide.
