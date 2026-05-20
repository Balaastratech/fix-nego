 What Manual Mode Does Perfectly
Let me check the manual mode implementation:

Searched workspace
Finding how manual mode handles turn segmentation
Read file(s)

negotiation_engine.py 350 - 481
Perfect! Now I can see exactly what manual mode does. Let me explain:

💡 What Manual Mode Does PERFECTLY
The Magic of Manual Mode:
# 1. User clicks button → "I'm speaking now"
session.current_speaker = "user"
session.speaker_segment_start = timestamp
session.current_segment_audio = b""  # Start fresh buffer

# 2. Audio chunks arrive → Accumulate in buffer
session.current_segment_audio += raw_bytes  # Keep adding

# 3. User clicks different button → "Counterparty speaking now"
# This triggers:
segment_audio = session.current_segment_audio  # Grab EXACT audio
asyncio.create_task(
    session.listener_agent.transcribe_segment(
        speaker=prev_speaker,  # Label it with PREVIOUS speaker
        audio=segment_audio,   # Send COMPLETE turn
        start_time=seg_start_ts,
        end_time=timestamp
    )
)
session.current_segment_audio = b""  # Reset for next turn
Why It Works Perfectly:
✅ No overlapping audio - Each turn is isolated
✅ No duplicates - Audio is cleared after transcription
✅ Complete turns - Button click = natural turn boundary
✅ Correct speaker - User explicitly labels who spoke
✅ No timing issues - Just accumulate bytes, no timestamps

🤔 Can We Replicate This in Automatic Mode?
YES! Absolutely! Here's how:

The Key Insight:
Manual mode uses button clicks as turn boundaries.
Automatic mode should use VAD silence detection as turn boundaries.

The Implementation:
class AutomaticTurnSegmenter:
    """
    Replicates manual mode's perfect turn segmentation,
    but uses VAD instead of button clicks.
    """
    
    def __init__(self, session):
        self.session = session
        self.vad = webrtcvad.Vad(1)  # Aggressiveness level 1
        
        # Same as manual mode
        self.current_turn_audio = b""
        self.current_speaker = None
        self.turn_start_time = None
        
        # VAD state tracking
        self.silence_frames = 0
        self.speech_frames = 0
        self.SILENCE_THRESHOLD = 15  # 450ms of silence = turn end
        self.SPEECH_THRESHOLD = 5    # 150ms of speech = turn start
        
    async def process_audio_chunk(self, chunk: bytes):
        """
        Process incoming audio chunk (same as handle_audio_chunk).
        This is called for every 100ms chunk from frontend.
        """
        # Split chunk into 30ms VAD frames
        frame_size = 960  # 30ms at 16kHz
        offset = 0
        
        while offset + frame_size <= len(chunk):
            frame = chunk[offset:offset + frame_size]
            await self._process_vad_frame(frame)
            offset += frame_size
    
    async def _process_vad_frame(self, frame: bytes):
        """
        Process single 30ms frame through VAD.
        This is the AUTOMATIC equivalent of button clicks.
        """
        try:
            is_speech = self.vad.is_speech(frame, 16000)
        except:
            return  # Skip invalid frames
        
        if is_speech:
            self.speech_frames += 1
            self.silence_frames = 0
            
            # TURN START (silence → speech)
            if self.speech_frames == self.SPEECH_THRESHOLD:
                await self._start_new_turn()
            
            # Accumulate audio (same as manual mode)
            if self.current_turn_audio is not None:
                self.current_turn_audio += frame
        
        else:  # Silence
            self.silence_frames += 1
            self.speech_frames = 0
            
            # TURN END (speech → silence for 450ms)
            if self.silence_frames == self.SILENCE_THRESHOLD:
                await self._end_current_turn()
    
    async def _start_new_turn(self):
        """
        Equivalent to: User clicks button to start speaking.
        """
        if self.current_turn_audio is None:
            self.current_turn_audio = b""
            self.turn_start_time = time.time()
            logger.info("🎤 Turn started (VAD detected speech)")
    
    async def _end_current_turn(self):
        """
        Equivalent to: User clicks different button (turn complete).
        """
        if self.current_turn_audio and len(self.current_turn_audio) >= 16000:
            # Classify speaker using Resemblyzer
            speaker = await self._classify_speaker(self.current_turn_audio)
            
            # Transcribe (same as manual mode)
            logger.info(f"📝 Turn ended: {speaker}, {len(self.current_turn_audio)/32000:.1f}s")
            asyncio.create_task(
                self.session.listener_agent.transcribe_segment(
                    speaker=speaker,
                    audio=self.current_turn_audio,
                    start_time=self.turn_start_time,
                    end_time=time.time()
                )
            )
            
            # Reset (same as manual mode)
            self.current_turn_audio = None
            self.turn_start_time = None
    
    async def _classify_speaker(self, audio: bytes) -> str:
        """
        Use Resemblyzer to identify speaker.
        This replaces the manual button click label.
        """
        if not self.session.user_embedding:
            return "unknown"
        
        # Run Resemblyzer in executor (don't block)
        from app.services.voice_encoder import VoiceEncoder
        encoder = VoiceEncoder.get_instance()
        
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(
            None, encoder.embed_utterance, audio
        )
        
        similarity = float(np.dot(embedding, self.session.user_embedding))
        threshold = 0.68
        
        return "user" if similarity > threshold else "counterparty"
🎯 Comparison: Manual vs Automatic
Feature	Manual Mode	Automatic Mode (Proposed)
Turn boundary	Button click	VAD silence detection (450ms)
Audio accumulation	current_segment_audio += bytes	current_turn_audio += frame
Turn completion	Button switch	Silence threshold reached
Speaker label	User clicks button	Resemblyzer classification
Transcription	transcribe_segment()	Same transcribe_segment()
No overlaps	✅ Yes	✅ Yes
No duplicates	✅ Yes	✅ Yes
Complete turns	✅ Yes	✅ Yes
🚀 Implementation Plan
Step 1: Create the AutomaticTurnSegmenter
# backend/app/services/turn_segmenter.py
# (Full implementation above)
Step 2: Replace Current Flow
BEFORE (Current broken system):

# negotiation_engine.py
async def handle_audio_chunk(session, raw_bytes):
    session.audio_buffer.push(raw_bytes)  # Just dump into buffer
    # ListenerAgent polls every 3s and grabs overlapping windows
AFTER (New turn-based system):

# negotiation_engine.py
async def handle_audio_chunk(session, raw_bytes):
    # Still push to buffer (for context extraction)
    session.audio_buffer.push(raw_bytes)
    
    # NEW: Also process through turn segmenter
    if session.turn_segmenter:
        await session.turn_segmenter.process_audio_chunk(raw_bytes)
Step 3: Initialize in START_NEGOTIATION
# negotiation_engine.py
async def handle_start(session, payload, websocket, api_key):
    # ... existing code ...
    
    # Initialize turn segmenter (NEW)
    from app.services.turn_segmenter import AutomaticTurnSegmenter
    session.turn_segmenter = AutomaticTurnSegmenter(session)
    logger.info("Turn segmenter initialized")
Step 4: Disable Polling-Based Transcription
# listener_agent.py
async def _run_cycle(self):
    # Skip diarization processing - turn segmenter handles it now
    # Only do context extraction (prices, sentiment, etc.)
    
    audio_bytes = self.audio_buffer.get_window(WINDOW_SECONDS)
    context = await self._call_flash_context_only(audio_bytes)
    await self._post_process_context(context)
💬 Discussion Points
Q1: What about overlapping speech?
A: VAD will detect the LOUDER speaker. When they stop, it triggers turn end. If both speak simultaneously, VAD treats it as continuous speech until BOTH are silent for 450ms.

Solution: Add a "max turn duration" (e.g., 30 seconds) to force segmentation even without silence.

Q2: What if someone speaks in short bursts?
Example: "I want... um... to buy... this phone"

A: The 450ms silence threshold is tuned to allow natural pauses. If pauses are longer, they'll be treated as separate turns.

Solution: Make threshold configurable (300-600ms range).

Q3: What about background noise?
A: VAD level 1 is less aggressive, so it tolerates some noise. But loud noise can trigger false "speech" detection.

Solution: Add RMS amplitude check - only start turn if volume > -40dB.

Q4: How do we handle Resemblyzer failures?
A: If Resemblyzer can't classify (no enrollment, audio too short, etc.), label as "unknown" and let user correct it later.

Solution: Add a "relabel" feature in frontend to fix wrong labels.

🎬 What Do You Think?
This approach gives you:

✅ Same reliability as manual mode (turn-based, no overlaps)
✅ Automatic operation (no button clicks needed)
✅ Correct speaker labels (Resemblyzer classification)
✅ Complete sentences (VAD detects natural boundaries)
Questions for you:

Do you want to keep manual mode as a fallback option?
What silence threshold feels natural? (300ms, 450ms, 600ms?)
Should we add a "confidence score" to auto-labeled transcripts?
Do you want real-time feedback when turns are detected?
Let me know your thoughts and I can start implementing! 🚀