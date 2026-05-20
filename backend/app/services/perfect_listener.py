"""
PerfectListenerSystem: Real-time speaker diarization and transcription system.

Implements a 5-stage pipeline:
1. Overlap Detection (Pyannote)
2. Speech Separation (Conv-TasNet, conditional)
3. Turn Segmentation (Pyannote VAD)
4. Speaker Identification (WeSpeaker + multi-level fallback)
5. Transcription (Gemini Flash)

Requirements: 20.1, 20.2, 20.3
"""

import asyncio
import logging
from typing import Optional, Any
from fastapi import WebSocket

from app.ai_assets import build_perfect_listener_transcription_prompt
from app.models.negotiation import NegotiationSession
from app.config import settings

logger = logging.getLogger(__name__)


class PerfectListenerSystem:
    """
    Real-time speaker diarization and transcription system.
    
    Implements 5-stage pipeline:
    1. Overlap Detection (Pyannote)
    2. Speech Separation (Conv-TasNet, conditional)
    3. Turn Segmentation (Pyannote VAD)
    4. Speaker Identification (WeSpeaker + fallback)
    5. Transcription (Gemini Flash)
    """
    
    def __init__(
        self,
        session: NegotiationSession,
        websocket: WebSocket,
        listener_agent: Any
    ):
        """
        Initialize PerfectListenerSystem.
        
        Args:
            session: Negotiation session containing state and configuration
            websocket: WebSocket connection for sending transcripts
            listener_agent: Reference to ListenerAgent for accumulated_transcript
        
        Raises:
            RuntimeError: If model loading fails and PERFECT_LISTENER_FALLBACK is False
        """
        import torch
        
        # Session and communication
        self.session = session
        self.websocket = websocket
        self.listener_agent = listener_agent
        
        # Task 20.1: GPU detection and automatic device selection (Requirement 17.6)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.device_type = "GPU (CUDA)" if torch.cuda.is_available() else "CPU"
        
        # Log device information at startup (Requirement 17.6)
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)  # GB
            logger.info(
                f"GPU detected: {gpu_name}, {gpu_memory:.2f} GB memory "
                f"[session={session.session_id}]"
            )
        else:
            logger.info(f"No GPU detected, using CPU [session={session.session_id}]")
        
        # Model references (loaded once, reused across sessions)
        # These will be initialized lazily on first use
        self.overlap_detector: Optional[Any] = None  # Pyannote OverlappedSpeechDetection
        self.separator: Optional[Any] = None  # Conv-TasNet model
        self.vad_pipeline: Optional[Any] = None  # Pyannote VoiceActivityDetection
        self.speaker_model: Optional[Any] = None  # WeSpeaker ResNet34
        self.pyannote_embedding_model: Optional[Any] = None  # Pyannote speaker embedding model
        self.flash_client: Optional[Any] = None  # Gemini Flash client
        
        # Buffers (Task 20.3: Optimize buffer operations - use bytearray for efficient concatenation)
        self.frame_buffer: bytearray = bytearray()  # Accumulates to 30ms VAD frames
        self.turn_buffer: bytearray = bytearray()  # Accumulates current turn audio
        self.overlap_window: bytearray = bytearray()  # Last 2 seconds for overlap detection
        
        # State tracking
        self.current_speaker: str = ""  # Last identified speaker
        self.transcribed_turn_ids: set[str] = set()  # Prevent duplicate transcriptions
        self.speaker_clusters: dict = {}  # For clustering fallback
        
        # Error tracking (Requirement 17.5)
        self.model_load_errors: dict = {}  # Track which models failed to load
        
        # Configuration attributes
        self.min_duration_on: float = getattr(settings, 'PYANNOTE_MIN_DURATION_ON', 0.25)
        self.min_duration_off: float = getattr(settings, 'PYANNOTE_MIN_DURATION_OFF', 0.5)
        self.wespeaker_threshold: float = getattr(settings, 'WESPEAKER_THRESHOLD', 0.70)
        self.convtasnet_enabled: bool = getattr(settings, 'CONVTASNET_ENABLED', True)
        self.clustering_enabled: bool = getattr(settings, 'CLUSTERING_ENABLED', True)
        
        # Heavy ML component flags (disable for 2-speaker scenarios)
        self.overlap_detection_enabled: bool = getattr(settings, 'ENABLE_OVERLAP_DETECTION', False)
        self.speech_separation_enabled: bool = getattr(settings, 'ENABLE_SPEECH_SEPARATION', False)
        
        # Track availability of heavy components
        self._overlap_available: bool = False
        self._separation_available: bool = False
        self._vad_load_attempted: bool = False  # Track if we've tried loading VAD
        
        logger.info(
            f"PerfectListenerSystem initialized [session={session.session_id}] "
            f"device={self.device_type}, "
            f"min_duration_on={self.min_duration_on}s, "
            f"min_duration_off={self.min_duration_off}s, "
            f"wespeaker_threshold={self.wespeaker_threshold}, "
            f"convtasnet_enabled={self.convtasnet_enabled}, "
            f"clustering_enabled={self.clustering_enabled}, "
            f"overlap_detection={self.overlap_detection_enabled}, "
            f"speech_separation={self.speech_separation_enabled}"
        )
    
    async def process_audio_chunk(self, chunk: bytes) -> None:
        """
        Main entry point for audio processing.
        
        Called from NegotiationEngine.handle_audio_chunk() in automatic mode.
        Processes 100ms audio chunks through the 5-stage pipeline.
        
        Args:
            chunk: PCM audio bytes (16kHz, 16-bit, mono)
        
        Requirements: 1.1, 1.5, 14.1, 14.2, 14.3, 9.1, 9.2
        """
        try:
            # Check manual mode mutual exclusion (Requirement 9.1, 9.2)
            import time
            import math
            manual_until = getattr(self.session, 'manual_override_until', 0) or 0
            
            # Manual mode only affects speaker identification, NOT VAD processing
            # VAD should always run to detect turn boundaries and transcribe
            # Only log if in manual mode for debugging
            if math.isinf(manual_until) or time.time() < manual_until:
                logger.debug(
                    f"Manual speaker mode active, but VAD processing continues "
                    f"[session={self.session.session_id}]"
                )
            
            # Check Ask AI mode mutual exclusion (Requirement 10.1)
            # When user_addressing_ai is true, audio should accumulate in question_capture_bytes
            # and NOT be processed by PerfectListenerSystem
            if getattr(self.session, 'user_addressing_ai', False):
                logger.debug(
                    f"Ask AI mode active (user_addressing_ai=true), skipping automatic processing "
                    f"[session={self.session.session_id}]"
                )
                return
            # ═══════════════════════════════════════════════════════════════════
            # Buffer Management (Requirements 13.2, 13.4)
            # Task 20.3: Optimized buffer operations using bytearray.extend()
            # ═══════════════════════════════════════════════════════════════════
            
            # 15.2: Accumulate chunk into frame_buffer until 30ms VAD frame complete
            # 30ms at 16kHz, 16-bit mono = 30 * 16 * 2 = 960 bytes
            # Clear after processing (done at end of method)
            self.frame_buffer.extend(chunk)
            
            # 15.4: Maintain last 2 seconds in overlap_window for overlap detection
            # 2 seconds at 16kHz, 16-bit mono = 2 * 16000 * 2 = 64000 bytes
            # Update on each chunk
            self.overlap_window.extend(chunk)
            if len(self.overlap_window) > 64000:
                # Evict old audio when exceeds 2 seconds (Task 20.3: efficient slicing)
                del self.overlap_window[:len(self.overlap_window) - 64000]
            
            # Check if we have enough data for overlap detection (0.5-second window for faster response)
            # 0.5 seconds at 16kHz, 16-bit mono = 0.5 * 16000 * 2 = 16000 bytes
            if len(self.overlap_window) < 16000:
                # Not enough data yet, wait for more chunks
                logger.debug(
                    f"⏳ Waiting for more audio: overlap_window={len(self.overlap_window)}/16000 bytes "
                    f"[session={self.session.session_id}]"
                )
                return
            
            logger.debug(
                f"🎤 Processing audio: chunk={len(chunk)} bytes, buffer={len(self.overlap_window)} bytes "
                f"[session={self.session.session_id}]"
            )
            
            # Stage 1: Detect overlap on 0.5-second windows (faster response)
            # Skip if overlap detection is disabled (2-speaker optimization)
            if self.overlap_detection_enabled:
                # Use the most recent 0.5 seconds from overlap_window for faster processing
                window_size = min(16000, len(self.overlap_window))
                window = bytes(self.overlap_window[-window_size:])
                has_overlap, overlap_timestamps = await self._detect_overlap(window)
            else:
                # Overlap detection disabled, assume no overlap
                has_overlap = False
                overlap_timestamps = []
            
            # Stage 2: Conditionally separate speakers if overlap detected (Requirement 1.5)
            # Skip if speech separation is disabled OR no overlap detected
            if has_overlap and self.speech_separation_enabled and self.convtasnet_enabled:
                logger.info(
                    f"Overlap detected, running Conv-TasNet separation "
                    f"[session={self.session.session_id}]"
                )
                # Separate the overlapping audio
                # Use the full overlap_window for better context (Task 20.3: convert to bytes)
                streams = await self._separate_speakers(bytes(self.overlap_window))
            else:
                # No overlap, separation disabled, or Conv-TasNet disabled - process as single stream
                if has_overlap and not self.speech_separation_enabled:
                    logger.debug(
                        f"Overlap detected but speech separation disabled, processing as single stream "
                        f"[session={self.session.session_id}]"
                    )
                elif has_overlap and not self.convtasnet_enabled:
                    logger.debug(
                        f"Overlap detected but Conv-TasNet disabled, processing as single stream "
                        f"[session={self.session.session_id}]"
                    )
                streams = [bytes(self.overlap_window)]
            
            # Stage 3: Segment turns on audio streams
            turns = await self._segment_turns(streams)
            
            logger.info(
                f"🔍 Segmentation result: {len(turns)} complete turn(s) found "
                f"[session={self.session.session_id}]"
            )
            
            if not turns:
                # No complete turns detected yet
                logger.debug(
                    f"No complete turns detected yet (waiting for silence) [session={self.session.session_id}]"
                )
                return
            
            logger.info(
                f"Detected {len(turns)} complete turn(s) [session={self.session.session_id}]"
            )
            
            # Stage 4 & 5: For each complete turn, identify speaker and transcribe
            for turn in turns:
                # 15.3: Accumulate audio in turn_buffer until turn completion
                # turn_buffer accumulates current turn audio and is cleared after transcription
                # Task 20.3: Use extend() for efficient concatenation
                self.turn_buffer.extend(turn["audio"])
                
                # Generate turn ID for deduplication (Requirement 14.1, 14.2)
                turn_id = self._generate_turn_id(turn["start_time"])
                
                # Check if already transcribed (prevent duplicates, Requirement 14.2)
                if turn_id in self.transcribed_turn_ids:
                    logger.debug(
                        f"Turn {turn_id} already transcribed, skipping "
                        f"[session={self.session.session_id}]"
                    )
                    continue
                
                # Stage 4: Identify speaker
                speaker_label, confidence = await self._identify_speaker(turn["audio"])
                
                logger.info(
                    f"Speaker identified: turn_id={turn_id}, speaker={speaker_label}, "
                    f"confidence={confidence:.3f} [session={self.session.session_id}]"
                )
                
                # Stage 5: Transcribe turn (Requirement 14.3)
                # This will also mark turn as transcribed and update accumulated_transcript
                await self._transcribe_turn(
                    audio=turn["audio"],
                    speaker=speaker_label,
                    start_time=turn["start_time"],
                    end_time=turn["end_time"]
                )
                
                # 15.3: Clear turn_buffer after transcription (Task 20.3: use clear())
                self.turn_buffer.clear()
            
            # 15.2: Clear frame_buffer after processing (accumulate until 30ms VAD frame complete)
            # Keep overlap_window for next iteration (maintained for overlap detection)
            # Task 20.3: Use clear() for efficient buffer reset
            self.frame_buffer.clear()
            
            logger.debug(
                f"Audio chunk processing complete [session={self.session.session_id}]"
            )
        
        except Exception as e:
            # Handle unexpected errors gracefully
            self._log_error(
                error_type="process_audio_chunk_error",
                message="Error in process_audio_chunk",
                exception=e,
                chunk_size=len(chunk)
            )
            # Don't re-raise, just log and continue processing next chunk
    
    async def _detect_overlap(self, window: bytes) -> tuple[bool, list[tuple[float, float]]]:
        """
        Detect overlapping speech in audio window.
        
        Stage 1 of the 5-stage pipeline. Uses Pyannote OverlappedSpeechDetection
        to identify when multiple speakers talk simultaneously.
        
        Args:
            window: 1-second audio window (16000 samples, PCM 16-bit mono)
        
        Returns:
            (has_overlap, overlap_timestamps)
            - has_overlap: True if overlap detected in the window
            - overlap_timestamps: List of (start, end) timestamps in seconds
        
        Performance: ~30ms per 1s window (CPU), ~10ms (GPU)
        
        Requirements: 1.1, 1.2, 1.3, 1.6, 1.7, 22.1
        """
        import numpy as np
        import torch
        import time
        
        # Skip overlap detection if disabled (2-speaker optimization)
        if not self.overlap_detection_enabled:
            return False, []
        
        # Start timing for overlap detection (Requirement 22.1)
        start_time = time.perf_counter()
        
        try:
            # Lazy load Pyannote OverlappedSpeechDetection model with error handling
            if self.overlap_detector is None:
                # Skip loading if overlap detection is disabled
                if not self.overlap_detection_enabled:
                    logger.info(
                        f"Overlap detection disabled, skipping model load "
                        f"[session={self.session.session_id}]"
                    )
                    self._overlap_available = False
                    return False, []
                
                def _load_overlap_detector():
                    try:
                        from pyannote.audio import Pipeline
                        
                        # Load the overlap detection pipeline
                        # Requires HF_TOKEN environment variable
                        detector = Pipeline.from_pretrained(
                            "pyannote/overlapped-speech-detection",
                            use_auth_token=settings.HF_TOKEN
                        )
                        
                        # Move to GPU if available (Task 20.1)
                        detector.to(self.device)
                        logger.info(f"OverlappedSpeechDetection model loaded on {self.device_type}")
                        
                        return detector
                    except Exception as e:
                        # Model not available - this is expected, overlap detection is optional
                        logger.warning(f"OverlappedSpeechDetection not available: {e}")
                        return None
                
                # Use safe model loading (Requirement 17.1)
                success = self._load_model_safe(
                    model_name="Pyannote OverlappedSpeechDetection",
                    loader_func=_load_overlap_detector,
                    model_attr="overlap_detector"
                )
                
                if not success:
                    # Model loading failed, return no overlap (fail-safe)
                    self._overlap_available = False
                    logger.warning(
                        f"Overlap detection unavailable due to model loading failure, "
                        f"assuming no overlap [session={self.session.session_id}]"
                    )
                    return False, []
                else:
                    self._overlap_available = True
            
            # Additional check: verify model is actually loaded (not None)
            if self.overlap_detector is None:
                logger.warning(
                    f"Overlap detector is None after loading attempt, "
                    f"assuming no overlap [session={self.session.session_id}]"
                )
                return False, []
            
            # Convert PCM bytes to numpy array
            # PCM format: 16-bit signed integers, mono, 16kHz
            audio_array = np.frombuffer(window, dtype=np.int16)
            
            # Normalize to [-1, 1] range (float32)
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Pyannote expects shape (num_samples,) or (1, num_samples)
            # and sample rate of 16000 Hz
            waveform = torch.from_numpy(audio_float).unsqueeze(0)  # Shape: (1, num_samples)
            
            # Create a dictionary with the expected format for Pyannote
            # Pyannote expects: {"waveform": tensor, "sample_rate": int}
            audio_dict = {
                "waveform": waveform,
                "sample_rate": 16000
            }
            
            # Task 20.2: Run overlap detection in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            
            def _run_overlap_detection():
                # Run overlap detection
                # Returns an Annotation object with overlap segments
                return self.overlap_detector(audio_dict)
            
            overlap_annotation = await loop.run_in_executor(None, _run_overlap_detection)
            
            # Extract overlap timestamps
            overlap_timestamps = []
            has_overlap = False
            
            # Iterate through detected overlap segments
            for segment in overlap_annotation.itersegments():
                has_overlap = True
                # segment.start and segment.end are in seconds
                overlap_timestamps.append((segment.start, segment.end))
            
            # Log timing for overlap detection (Requirement 22.1)
            elapsed_time = time.perf_counter() - start_time
            logger.debug(
                f"Overlap detection completed: has_overlap={has_overlap}, "
                f"segments={len(overlap_timestamps)}, time={elapsed_time*1000:.1f}ms "
                f"[session={self.session.session_id}]"
            )
            
            return has_overlap, overlap_timestamps
        
        except Exception as e:
            # Handle model inference errors gracefully (Requirement 1.7, 17.3)
            audio_duration = len(window) / (2 * 16000)  # bytes / (bytes_per_sample * sample_rate)
            
            self._log_error(
                error_type="overlap_detection_failure",
                message="Overlap detection failed",
                exception=e,
                audio_duration=audio_duration
            )
            
            # Return no overlap on error (fail-safe: process as single stream)
            return False, []
    
    async def _separate_speakers(self, audio: bytes) -> list[bytes]:
        """
        Separate overlapping speech into individual streams.
        
        Stage 2 of the 5-stage pipeline. Uses Conv-TasNet to separate mixed audio
        containing overlapping speech into clean individual streams.
        
        Args:
            audio: Mixed audio containing overlapping speech (PCM 16-bit mono, 16kHz)
        
        Returns:
            List of separated audio streams (typically 2)
            - Each stream is PCM bytes (16-bit mono, 16kHz)
            - Normalized to [-1, 1] range
            - Returns [audio] (single stream) on failure
        
        Performance: ~200ms per 1s audio (CPU), ~50ms (GPU)
        
        Requirements: 2.1, 2.2, 2.5, 2.6, 16.3, 17.3, 22.1
        """
        import numpy as np
        import torch
        import time
        
        # Skip speech separation if disabled (2-speaker optimization)
        if not self.speech_separation_enabled:
            return [audio]
        
        # Start timing for separation (Requirement 22.1)
        start_time = time.perf_counter()
        
        try:
            # Lazy load Conv-TasNet model with error handling
            if self.separator is None:
                # Skip loading if speech separation is disabled
                if not self.speech_separation_enabled:
                    logger.info(
                        f"Speech separation disabled, skipping model load "
                        f"[session={self.session.session_id}]"
                    )
                    self._separation_available = False
                    return [audio]
                
                def _load_convtasnet():
                    from asteroid.models import ConvTasNet
                    
                    # Load pre-trained Conv-TasNet model from Hugging Face
                    separator = ConvTasNet.from_pretrained(
                        "JorisCos/ConvTasNet_Libri2Mix_sepclean_16k"
                    )
                    
                    # Set to evaluation mode (disable dropout, batch norm training)
                    separator.eval()
                    
                    # Move to GPU if available (Task 20.1)
                    separator.to(self.device)
                    logger.info(f"Conv-TasNet model loaded on {self.device_type}")
                    
                    return separator
                
                # Use safe model loading (Requirement 17.1)
                success = self._load_model_safe(
                    model_name="Conv-TasNet",
                    loader_func=_load_convtasnet,
                    model_attr="separator"
                )
                
                if not success:
                    # Model loading failed, return mixed audio (Requirement 17.3)
                    self._separation_available = False
                    logger.warning(
                        f"Conv-TasNet unavailable due to model loading failure, "
                        f"processing mixed audio [session={self.session.session_id}]"
                    )
                    return [audio]
                else:
                    self._separation_available = True
            
            # Convert PCM bytes to numpy array
            # PCM format: 16-bit signed integers, mono, 16kHz
            audio_array = np.frombuffer(audio, dtype=np.int16)
            
            # Normalize to [-1, 1] range (float32)
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Conv-TasNet expects shape (batch, samples)
            waveform = torch.from_numpy(audio_float).unsqueeze(0)  # Shape: (1, num_samples)
            
            # Move to same device as model (Task 20.1)
            waveform = waveform.to(self.device)
            
            # Run separation in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            
            def _run_separation():
                with torch.no_grad():
                    # Run Conv-TasNet separation
                    # Output shape: (batch, num_sources, num_samples)
                    # num_sources is typically 2 for this model
                    separated = self.separator(waveform)
                    return separated
            
            separated = await loop.run_in_executor(None, _run_separation)
            
            # Extract individual streams
            # separated shape: (1, num_sources, num_samples)
            num_sources = separated.shape[1]
            
            logger.debug(
                f"Conv-TasNet separated audio into {num_sources} streams "
                f"[session={self.session.session_id}]"
            )
            
            # Convert each stream back to PCM bytes
            separated_streams = []
            
            for i in range(num_sources):
                # Extract stream: shape (num_samples,)
                stream = separated[0, i, :].cpu().numpy()
                
                # Normalize to [-1, 1] range
                # Find max absolute value
                max_val = np.abs(stream).max()
                
                if max_val > 0:
                    # Normalize and scale to 95% to avoid clipping
                    stream = (stream / max_val) * 0.95
                
                # Convert back to 16-bit PCM
                # Clip to [-1, 1] range to be safe
                stream = np.clip(stream, -1.0, 1.0)
                
                # Scale to int16 range
                stream_int16 = (stream * 32767).astype(np.int16)
                
                # Convert to bytes
                stream_bytes = stream_int16.tobytes()
                
                separated_streams.append(stream_bytes)
            
            # Log timing for separation (Requirement 22.1)
            elapsed_time = time.perf_counter() - start_time
            logger.debug(
                f"Speech separation completed: streams={len(separated_streams)}, "
                f"time={elapsed_time*1000:.1f}ms [session={self.session.session_id}]"
            )
            
            logger.info(
                f"Successfully separated audio into {len(separated_streams)} clean streams "
                f"[session={self.session.session_id}]"
            )
            
            return separated_streams
        
        except Exception as e:
            # Handle separation failures gracefully (Requirement 16.3, 17.3)
            audio_duration = len(audio) / (2 * 16000)  # bytes / (bytes_per_sample * sample_rate)
            
            self._log_error(
                error_type="separation_failure",
                message="Conv-TasNet separation failed, processing mixed audio",
                exception=e,
                audio_duration=audio_duration
            )
            
            # Fall back to processing mixed audio (no separation)
            # Return original audio as single stream
            logger.warning(
                f"Falling back to mixed audio processing (no separation) "
                f"[session={self.session.session_id}]"
            )
            
            return [audio]
    
    async def _segment_turns(self, streams: list[bytes]) -> list[dict]:
        """
        Segment audio streams into complete turns.
        
        Stage 3 of the 5-stage pipeline. Uses Pyannote VoiceActivityDetection
        to detect turn boundaries, merging short pauses and splitting on longer
        pauses or speaker changes.
        
        Args:
            streams: List of audio streams (1 if no overlap, 2 if separated)
                    Each stream is PCM bytes (16-bit mono, 16kHz)
        
        Returns:
            List of turn dictionaries:
            {
                "audio": bytes,           # Turn audio (PCM 16-bit mono, 16kHz)
                "start_time": float,      # Absolute timestamp (seconds since epoch)
                "end_time": float,        # Absolute timestamp (seconds since epoch)
                "stream_index": int       # 0 for non-overlapping, 0/1 for separated
            }
        
        Performance: ~50ms per 1s audio (CPU), ~20ms (GPU)
        
        Requirements: 3.1, 3.2, 3.3, 3.5, 3.6, 22.1, 22.3
        """
        import numpy as np
        import torch
        import time
        
        # Start timing for turn segmentation (Requirement 22.1)
        start_time = time.perf_counter()
        
        try:
            # Lazy load Pyannote VoiceActivityDetection model with error handling
            if self.vad_pipeline is None:
                def _load_vad():
                    try:
                        from pyannote.audio import Model
                        from pyannote.audio.pipelines.utils import PipelineModel
                        import torch
                        
                        # Load the segmentation model directly (avoids SpeechBrain/k2 dependency)
                        model = Model.from_pretrained(
                            "pyannote/segmentation-3.0",
                            use_auth_token=settings.HF_TOKEN
                        )
                        
                        # Move to device
                        model.to(self.device)
                        
                        # Create a simple VAD wrapper
                        class SimpleVAD:
                            def __init__(self, model, device, min_duration_on, min_duration_off):
                                self.model = model
                                self.device = device
                                self.min_duration_on = min_duration_on
                                self.min_duration_off = min_duration_off
                            
                            def __call__(self, audio_dict):
                                """Simple VAD using segmentation model."""
                                from pyannote.core import Annotation, Segment
                                import numpy as np
                                
                                waveform = audio_dict["waveform"]
                                sample_rate = audio_dict["sample_rate"]
                                
                                # Move to device
                                if not isinstance(waveform, torch.Tensor):
                                    waveform = torch.from_numpy(waveform)
                                waveform = waveform.to(self.device)
                                
                                # Run model inference
                                with torch.no_grad():
                                    output = self.model(waveform.unsqueeze(0) if waveform.dim() == 1 else waveform)
                                
                                # Extract speech segments (simple thresholding)
                                # output shape: (batch, frames, classes)
                                # Take the speech class (usually index 1)
                                speech_probs = output[0, :, 1].cpu().numpy() if output.shape[-1] > 1 else output[0, :, 0].cpu().numpy()
                                
                                # Log speech probability statistics for debugging
                                max_prob = speech_probs.max()
                                mean_prob = speech_probs.mean()
                                logger.debug(
                                    f"VAD speech probabilities: max={max_prob:.3f}, mean={mean_prob:.3f}, "
                                    f"frames={len(speech_probs)}"
                                )
                                
                                # Convert frame indices to timestamps
                                duration = waveform.shape[-1] / sample_rate
                                frame_duration = duration / len(speech_probs)
                                
                                # Threshold and create segments
                                annotation = Annotation()
                                in_speech = False
                                speech_start = 0
                                
                                for i, prob in enumerate(speech_probs):
                                    timestamp = i * frame_duration
                                    
                                    # Very low threshold (0.2) for better speech detection with low audio levels
                                    if prob > 0.2 and not in_speech:
                                        # Speech starts
                                        speech_start = timestamp
                                        in_speech = True
                                    elif prob <= 0.2 and in_speech:
                                        # Speech ends
                                        segment_duration = timestamp - speech_start
                                        if segment_duration >= self.min_duration_on:
                                            annotation[Segment(speech_start, timestamp)] = "speech"
                                        in_speech = False
                                
                                # Handle case where speech continues to end
                                if in_speech:
                                    segment_duration = duration - speech_start
                                    if segment_duration >= self.min_duration_on:
                                        annotation[Segment(speech_start, duration)] = "speech"
                                
                                return annotation
                        
                        vad = SimpleVAD(model, self.device, self.min_duration_on, self.min_duration_off)
                        
                        logger.info(
                            f"VoiceActivityDetection model loaded (direct segmentation, no k2 required) "
                            f"[min_duration_on={self.min_duration_on}s, "
                            f"min_duration_off={self.min_duration_off}s]"
                        )
                        
                        return vad
                    except ModuleNotFoundError as e:
                        # Handle missing dependencies
                        logger.error(
                            f"VAD loading failed due to missing dependency: {e}. "
                            f"Install required packages."
                        )
                        return None
                    except Exception as e:
                        logger.error(f"VAD loading failed: {e}")
                        return None
                
                # Use safe model loading (Requirement 17.1)
                success = self._load_model_safe(
                    model_name="Pyannote VoiceActivityDetection",
                    loader_func=_load_vad,
                    model_attr="vad_pipeline"
                )
                
                self._vad_load_attempted = True
                
                if not success:
                    # Model loading failed, return empty turns (fail-safe)
                    # Only log once to avoid spam
                    logger.warning(
                        f"Turn segmentation unavailable due to model loading failure, "
                        f"returning no turns [session={self.session.session_id}]"
                    )
                    return []
            
            # Additional check: verify VAD pipeline is actually loaded (not None)
            if self.vad_pipeline is None:
                # Only log if this is the first time we're checking after load attempt
                if not self._vad_load_attempted:
                    logger.warning(
                        f"VAD pipeline is None after loading attempt, "
                        f"returning no turns [session={self.session.session_id}]"
                    )
                    self._vad_load_attempted = True
                return []
            
            all_turns = []
            current_time = time.time()
            
            # Process each stream separately
            for stream_idx, stream_bytes in enumerate(streams):
                # Convert PCM bytes to numpy array
                # PCM format: 16-bit signed integers, mono, 16kHz
                audio_array = np.frombuffer(stream_bytes, dtype=np.int16)
                
                # Normalize to [-1, 1] range (float32)
                audio_float = audio_array.astype(np.float32) / 32768.0
                
                # Pyannote expects shape (1, num_samples) and sample rate
                waveform = torch.from_numpy(audio_float).unsqueeze(0)  # Shape: (1, num_samples)
                
                # Create audio dictionary for Pyannote
                audio_dict = {
                    "waveform": waveform,
                    "sample_rate": 16000
                }
                
                # Run VAD in executor to avoid blocking event loop
                loop = asyncio.get_event_loop()
                
                def _run_vad():
                    # Run VAD pipeline
                    # Returns an Annotation object with speech segments
                    return self.vad_pipeline(audio_dict)
                
                vad_result = await loop.run_in_executor(None, _run_vad)
                
                # Only log VAD result if segments are found (reduce log spam)
                timeline = vad_result.get_timeline()
                if len(timeline) > 0:
                    logger.info(
                        f"VAD detected speech: stream={stream_idx}, "
                        f"audio_duration={len(audio_array)/16000:.2f}s, "
                        f"segments_found={len(timeline)} "
                        f"[session={self.session.session_id}]"
                    )
                
                # Extract turns from VAD timeline
                # VAD automatically merges gaps < min_duration_off
                # and filters out segments < min_duration_on
                for segment in timeline:
                    # Calculate sample indices
                    start_sample = int(segment.start * 16000)
                    end_sample = int(segment.end * 16000)
                    
                    # Extract turn audio
                    turn_audio = audio_array[start_sample:end_sample]
                    
                    # Convert back to bytes
                    turn_bytes = turn_audio.tobytes()
                    
                    # Calculate absolute timestamps
                    # segment.start and segment.end are relative to the audio stream
                    # We need to convert to absolute timestamps
                    start_time = current_time + segment.start
                    end_time = current_time + segment.end
                    
                    # Create turn dictionary
                    turn = {
                        "audio": turn_bytes,
                        "start_time": start_time,
                        "end_time": end_time,
                        "stream_index": stream_idx
                    }
                    
                    all_turns.append(turn)
                    
                    # Log turn boundary (Requirement 22.3)
                    turn_duration = segment.end - segment.start
                    logger.debug(
                        f"Turn detected: stream={stream_idx}, "
                        f"start={segment.start:.2f}s, end={segment.end:.2f}s, "
                        f"duration={turn_duration:.2f}s "
                        f"[session={self.session.session_id}]"
                    )
            
            # Sort turns by start time (important for multi-stream processing)
            all_turns.sort(key=lambda t: t["start_time"])
            
            # Log timing for turn segmentation (Requirement 22.1)
            elapsed_time = time.perf_counter() - start_time
            logger.debug(
                f"Turn segmentation completed: streams={len(streams)}, "
                f"turns={len(all_turns)}, time={elapsed_time*1000:.1f}ms "
                f"[session={self.session.session_id}]"
            )
            
            # Only log when turns are actually detected to reduce noise
            if len(all_turns) > 0:
                logger.info(
                    f"Segmented {len(streams)} stream(s) into {len(all_turns)} turn(s) "
                    f"[session={self.session.session_id}]"
                )
            else:
                logger.debug(
                    f"Segmented {len(streams)} stream(s) into {len(all_turns)} turn(s) "
                    f"[session={self.session.session_id}]"
                )
            
            return all_turns
        
        except Exception as e:
            # Handle VAD failures gracefully
            audio_duration = sum(len(s) for s in streams) / (2 * 16000)
            
            self._log_error(
                error_type="turn_segmentation_failure",
                message="Turn segmentation failed",
                exception=e,
                audio_duration=audio_duration,
                num_streams=len(streams)
            )
            
            # Return empty list on error (fail-safe: no turns detected)
            return []
    
    async def _identify_speaker(self, audio: bytes) -> tuple[str, float]:
        """
        Identify speaker using multi-level fallback chain.
        
        Stage 4 of the 5-stage pipeline. Implements a robust fallback chain:
        1. Manual mode: Use session.current_speaker if manual mode is active
        2. WeSpeaker (primary, 99%+ accuracy with enrollment)
        3. Pyannote embedding (fallback, 95%+ accuracy)
        4. Clustering (positional fallback, 80%+ accuracy, no enrollment needed)
        5. Unknown label (last resort)
        
        Args:
            audio: Turn audio (PCM 16-bit mono, 16kHz)
                  Recommended >= 0.5s for reliable identification
        
        Returns:
            (speaker_label, confidence)
            - speaker_label: "user", "counterparty", or "unknown"
            - confidence: 0.0 to 1.0 (identification confidence)
        
        Performance: ~200ms per turn (CPU), ~50ms (GPU)
        
        Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 16.4, 17.4, 22.1, 22.2
        """
        import time
        import math
        
        # Start timing for speaker identification (Requirement 22.1)
        start_time = time.perf_counter()
        
        try:
            # Check if manual mode is active (Requirement 9.1, 9.2)
            manual_until = getattr(self.session, 'manual_override_until', 0) or 0
            if math.isinf(manual_until) or time.time() < manual_until:
                # Manual mode: Use manually selected speaker
                manual_speaker = getattr(self.session, 'current_speaker', 'unknown')
                logger.debug(
                    f"Manual mode active, using manual speaker: {manual_speaker} "
                    f"[session={self.session.session_id}]"
                )
                return manual_speaker, 1.0  # High confidence for manual selection
            
            # Normalize audio before embedding generation (Requirement 4.5)
            normalized_audio = self._normalize_audio(audio)
            
            # Level 1: Try WeSpeaker identification (primary method)
            # Requirements: 4.1, 5.1-5.7
            logger.debug(
                f"Attempting WeSpeaker identification [session={self.session.session_id}]"
            )
            
            speaker_label, confidence = await self._try_wespeaker(normalized_audio)
            
            if confidence >= self.wespeaker_threshold:
                # Log timing and confidence (Requirements 22.1, 22.2)
                elapsed_time = time.perf_counter() - start_time
                logger.debug(
                    f"Speaker identification completed: method=WeSpeaker, "
                    f"speaker={speaker_label}, confidence={confidence:.3f}, "
                    f"time={elapsed_time*1000:.1f}ms [session={self.session.session_id}]"
                )
                logger.info(
                    f"WeSpeaker identification successful: speaker={speaker_label}, "
                    f"confidence={confidence:.3f} [session={self.session.session_id}]"
                )
                return speaker_label, confidence
            
            # Log WeSpeaker confidence (Requirement 22.2)
            logger.debug(
                f"WeSpeaker confidence too low: confidence={confidence:.3f}, "
                f"threshold={self.wespeaker_threshold}, trying Pyannote fallback "
                f"[session={self.session.session_id}]"
            )
            
            # Level 2: Try Pyannote embedding fallback (Requirement 4.2)
            # Requirements: 6.1-6.6
            speaker_label, confidence = await self._try_pyannote_embedding(normalized_audio)
            
            pyannote_threshold = getattr(settings, 'PYANNOTE_EMBEDDING_THRESHOLD', 0.70)
            
            if confidence >= pyannote_threshold:
                # Log timing and confidence (Requirements 22.1, 22.2)
                elapsed_time = time.perf_counter() - start_time
                logger.debug(
                    f"Speaker identification completed: method=Pyannote, "
                    f"speaker={speaker_label}, confidence={confidence:.3f}, "
                    f"time={elapsed_time*1000:.1f}ms [session={self.session.session_id}]"
                )
                logger.info(
                    f"Pyannote embedding identification successful: speaker={speaker_label}, "
                    f"confidence={confidence:.3f} [session={self.session.session_id}]"
                )
                return speaker_label, confidence
            
            # Log Pyannote confidence (Requirement 22.2)
            logger.debug(
                f"Pyannote confidence too low: confidence={confidence:.3f}, "
                f"threshold={pyannote_threshold}, trying clustering fallback "
                f"[session={self.session.session_id}]"
            )
            
            # Level 3: Try clustering fallback (Requirement 4.3)
            # Requirements: 7.1-7.7
            if self.clustering_enabled:
                speaker_label = await self._try_clustering(normalized_audio)
                
                if speaker_label != "unknown":
                    # Log timing and fallback level (Requirements 22.1, 22.2)
                    elapsed_time = time.perf_counter() - start_time
                    logger.debug(
                        f"Speaker identification completed: method=Clustering, "
                        f"speaker={speaker_label}, confidence=0.60 (fixed), "
                        f"time={elapsed_time*1000:.1f}ms [session={self.session.session_id}]"
                    )
                    logger.info(
                        f"Clustering identification successful: speaker={speaker_label} "
                        f"[session={self.session.session_id}]"
                    )
                    # Clustering doesn't provide confidence, use fixed value
                    return speaker_label, 0.60
                
                # Log clustering failure (Requirement 22.2)
                logger.debug(
                    f"Clustering failed, using unknown label [session={self.session.session_id}]"
                )
            else:
                # Log clustering disabled (Requirement 22.2)
                logger.debug(
                    f"Clustering disabled, skipping to unknown label [session={self.session.session_id}]"
                )
            
            # Level 4: Unknown label (last resort, Requirement 4.4, 16.4, 17.4)
            # Log timing and fallback level (Requirements 22.1, 22.2)
            elapsed_time = time.perf_counter() - start_time
            logger.debug(
                f"Speaker identification completed: method=Unknown, "
                f"speaker=unknown, confidence=0.0, time={elapsed_time*1000:.1f}ms "
                f"[session={self.session.session_id}]"
            )
            logger.warning(
                f"All identification methods failed, using 'unknown' label "
                f"[session={self.session.session_id}]"
            )
            return "unknown", 0.0
        
        except Exception as e:
            # Handle identification failures gracefully (Requirement 4.4, 16.4, 17.4)
            audio_duration = len(audio) / (2 * 16000)
            
            self._log_error(
                error_type="identification_failure",
                message="Speaker identification failed with exception, using 'unknown' label",
                exception=e,
                audio_duration=audio_duration
            )
            
            # Return unknown label on error (fail-safe)
            return "unknown", 0.0
    
    async def _try_wespeaker(self, audio: bytes) -> tuple[str, float]:
        """
        Level 1: WeSpeaker identification.
        
        Uses WeSpeaker ResNet34 model for speaker identification.
        Compares audio embedding with user_embedding using cosine similarity.
        
        Args:
            audio: Normalized audio (PCM 16-bit mono, 16kHz, [-1, 1] range)
        
        Returns:
            (speaker_label, confidence)
            - speaker_label: "user", "counterparty", or "" (if failed)
            - confidence: Cosine similarity score (0.0 to 1.0)
        
        Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
        """
        import numpy as np
        
        try:
            # Check if user enrollment exists (Requirement 5.7)
            if not hasattr(self.session, 'user_embedding') or self.session.user_embedding is None:
                logger.debug(
                    f"No user enrollment, skipping WeSpeaker [session={self.session.session_id}]"
                )
                return "", 0.0
            
            # Check minimum duration (Requirement 5.2)
            # PCM format: 16-bit (2 bytes per sample), 16kHz
            duration = len(audio) / (2 * 16000)  # bytes / (bytes_per_sample * sample_rate)
            
            if duration < 0.5:
                logger.debug(
                    f"Audio too short for WeSpeaker ({duration:.2f}s < 0.5s), "
                    f"skipping [session={self.session.session_id}]"
                )
                return "", 0.0
            
            # Lazy load WeSpeaker model with error handling (Requirement 5.1, 17.1)
            if self.speaker_model is None:
                def _load_wespeaker():
                    # Import fix_torchaudio first to patch deprecated functions
                    try:
                        import sys
                        import os
                        # Add backend directory to path if not already there
                        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                        if backend_dir not in sys.path:
                            sys.path.insert(0, backend_dir)
                        import fix_torchaudio
                    except ImportError:
                        logger.warning("fix_torchaudio not found, continuing without patch")
                    
                    from wespeaker.cli.speaker import load_model
                    
                    # Load WeSpeaker ResNet34 model from downloaded cache
                    # Model: wespeaker-voxceleb-resnet34
                    model_path = os.path.expanduser("~/.cache/wespeaker/wespeaker-voxceleb-resnet34")
                    model = load_model(model_path)
                    
                    logger.info("WeSpeaker ResNet34 model loaded successfully")
                    return model
                
                # Use safe model loading (Requirement 17.1)
                success = self._load_model_safe(
                    model_name="WeSpeaker ResNet34",
                    loader_func=_load_wespeaker,
                    model_attr="speaker_model"
                )
                
                if not success:
                    # Model loading failed, trigger fallback
                    logger.warning(
                        f"WeSpeaker unavailable due to model loading failure, "
                        f"triggering fallback [session={self.session.session_id}]"
                    )
                    return "", 0.0
            
            # Convert PCM bytes to numpy array
            # PCM format: 16-bit signed integers, mono, 16kHz
            audio_array = np.frombuffer(audio, dtype=np.int16)
            
            # Convert to float32 in [-1, 1] range (already normalized by caller)
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Generate embedding asynchronously (Requirement 5.7)
            # Run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            
            def _generate_embedding():
                # WeSpeaker expects numpy array of float32 samples
                # Use extract_embedding method (correct API)
                return self.speaker_model.extract_embedding(audio_float)
            
            turn_embedding = await loop.run_in_executor(None, _generate_embedding)
            
            # Compare with user enrollment using cosine similarity (Requirement 5.3)
            # Cosine similarity = dot product of normalized vectors
            # Both embeddings should already be normalized by WeSpeaker
            similarity = float(np.dot(turn_embedding, self.session.user_embedding))
            
            # Clamp similarity to [0, 1] range (cosine similarity can be [-1, 1])
            # but for speaker verification we only care about positive similarity
            similarity = max(0.0, min(1.0, similarity))
            
            # Determine speaker label based on threshold (Requirements 5.4, 5.5)
            if similarity > self.wespeaker_threshold:
                # High similarity = user
                speaker_label = "user"
                logger.debug(
                    f"WeSpeaker: HIGH similarity ({similarity:.3f} > {self.wespeaker_threshold}), "
                    f"identified as USER [session={self.session.session_id}]"
                )
            else:
                # Low similarity = counterparty or trigger fallback
                speaker_label = "counterparty"
                logger.debug(
                    f"WeSpeaker: LOW similarity ({similarity:.3f} <= {self.wespeaker_threshold}), "
                    f"identified as COUNTERPARTY [session={self.session.session_id}]"
                )
            
            return speaker_label, similarity
        
        except Exception as e:
            # Handle WeSpeaker failures gracefully
            audio_duration = len(audio) / (2 * 16000)
            
            self._log_error(
                error_type="wespeaker_failure",
                message="WeSpeaker identification failed, triggering fallback",
                exception=e,
                audio_duration=audio_duration
            )
            
            # Return empty label and zero confidence to trigger fallback
            return "", 0.0
    
    async def _try_pyannote_embedding(self, audio: bytes) -> tuple[str, float]:
        """
        Level 2: Pyannote embedding fallback.
        
        Uses Pyannote speaker embedding model for identification.
        Compares audio embedding with user_embedding using cosine similarity.
        
        Args:
            audio: Normalized audio (PCM 16-bit mono, 16kHz, [-1, 1] range)
        
        Returns:
            (speaker_label, confidence)
            - speaker_label: "user", "counterparty", or "" (if failed)
            - confidence: Cosine similarity score (0.0 to 1.0)
        
        Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
        """
        import numpy as np
        import torch
        
        try:
            # Check if user enrollment exists (Requirement 6.1)
            if not hasattr(self.session, 'user_embedding') or self.session.user_embedding is None:
                logger.debug(
                    f"No user enrollment, skipping Pyannote embedding [session={self.session.session_id}]"
                )
                return "", 0.0
            
            # Lazy load Pyannote embedding model with error handling (Requirement 6.1, 17.1)
            if not hasattr(self, 'pyannote_embedding_model') or self.pyannote_embedding_model is None:
                def _load_pyannote_embedding():
                    from pyannote.audio import Inference
                    
                    # Load the speaker embedding model
                    # Uses pyannote/embedding for speaker verification
                    embedding_model = Inference(
                        "pyannote/embedding",
                        use_auth_token=settings.HF_TOKEN
                    )

                    # Move to GPU if available (Task 20.1)
                    embedding_model.to(self.device)
                    logger.info(f"Pyannote embedding model loaded on {self.device_type}")

                    return embedding_model

                # Use safe model loading (Requirement 17.1)
                success = self._load_model_safe(
                    model_name="Pyannote Embedding",
                    loader_func=_load_pyannote_embedding,
                    model_attr="pyannote_embedding_model"
                )
                
                if not success:
                    # Model loading failed, trigger fallback
                    logger.warning(
                        f"Pyannote embedding unavailable due to model loading failure, "
                        f"triggering fallback [session={self.session.session_id}]"
                    )
                    return "", 0.0
            
            # Convert PCM bytes to numpy array
            # PCM format: 16-bit signed integers, mono, 16kHz
            audio_array = np.frombuffer(audio, dtype=np.int16)
            
            # Convert to float32 in [-1, 1] range (already normalized by caller)
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Pyannote expects shape (1, num_samples) and sample rate
            waveform = torch.from_numpy(audio_float).unsqueeze(0)  # Shape: (1, num_samples)
            
            # Create audio dictionary for Pyannote
            audio_dict = {
                "waveform": waveform,
                "sample_rate": 16000
            }
            
            # Generate embedding asynchronously (Requirement 6.6)
            # Run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            
            def _generate_embedding():
                # Pyannote Inference returns a numpy array embedding
                return self.pyannote_embedding_model(audio_dict)
            
            turn_embedding = await loop.run_in_executor(None, _generate_embedding)
            
            # Ensure embedding is a numpy array
            if isinstance(turn_embedding, torch.Tensor):
                turn_embedding = turn_embedding.cpu().numpy()
            
            # Flatten embedding if needed (should be 1D)
            if turn_embedding.ndim > 1:
                turn_embedding = turn_embedding.flatten()
            
            # Normalize embeddings for cosine similarity
            # Cosine similarity = dot product of normalized vectors
            turn_embedding_norm = turn_embedding / (np.linalg.norm(turn_embedding) + 1e-8)
            user_embedding_norm = self.session.user_embedding / (np.linalg.norm(self.session.user_embedding) + 1e-8)
            
            # Compare with user enrollment using cosine similarity (Requirement 6.2)
            similarity = float(np.dot(turn_embedding_norm, user_embedding_norm))
            
            # Clamp similarity to [0, 1] range (cosine similarity can be [-1, 1])
            # but for speaker verification we only care about positive similarity
            similarity = max(0.0, min(1.0, similarity))
            
            # Get threshold from settings
            pyannote_threshold = getattr(settings, 'PYANNOTE_EMBEDDING_THRESHOLD', 0.70)
            
            # Determine speaker label based on threshold (Requirements 6.3, 6.4)
            if similarity > pyannote_threshold:
                # High similarity = user
                speaker_label = "user"
                logger.debug(
                    f"Pyannote embedding: HIGH similarity ({similarity:.3f} > {pyannote_threshold}), "
                    f"identified as USER [session={self.session.session_id}]"
                )
            else:
                # Low similarity = trigger clustering fallback (return empty to signal fallback)
                speaker_label = ""
                logger.debug(
                    f"Pyannote embedding: LOW similarity ({similarity:.3f} <= {pyannote_threshold}), "
                    f"triggering clustering fallback [session={self.session.session_id}]"
                )
            
            return speaker_label, similarity
        
        except Exception as e:
            # Handle Pyannote embedding failures gracefully
            audio_duration = len(audio) / (2 * 16000)
            
            self._log_error(
                error_type="pyannote_embedding_failure",
                message="Pyannote embedding identification failed, triggering fallback",
                exception=e,
                audio_duration=audio_duration
            )
            
            # Return empty label and zero confidence to trigger fallback
            return "", 0.0
    
    async def _try_clustering(self, audio: bytes) -> str:
        """
        Level 3: Clustering-based identification.
        
        Assigns speaker labels based on clustering without enrollment.
        First speaker is labeled "user", second speaker is "counterparty".
        Maintains speaker clusters across turns for consistency.
        
        Args:
            audio: Normalized audio (PCM 16-bit mono, 16kHz, [-1, 1] range)
        
        Returns:
            speaker_label: "user", "counterparty", or "unknown" (if failed)
        
        Requirements: 7.1, 7.2, 7.3, 7.4, 7.6
        """
        import numpy as np
        import torch
        
        try:
            # Check if clustering is enabled (Requirement 7.5)
            if not self.clustering_enabled:
                logger.debug(
                    f"Clustering disabled, skipping to unknown label [session={self.session.session_id}]"
                )
                return "unknown"
            
            # Lazy load Pyannote embedding model for clustering with error handling
            # We use Pyannote embeddings for clustering since it's already available
            if not hasattr(self, 'pyannote_embedding_model') or self.pyannote_embedding_model is None:
                def _load_pyannote_embedding():
                    from pyannote.audio import Inference
                    
                    # Load the speaker embedding model
                    embedding_model = Inference(
                        "pyannote/embedding",
                        use_auth_token=settings.HF_TOKEN
                    )

                    # Move to GPU if available (Task 20.1)
                    embedding_model.to(self.device)
                    logger.info(f"Pyannote embedding model loaded on {self.device_type} for clustering")
                    
                    return embedding_model
                
                # Use safe model loading (Requirement 17.1)
                success = self._load_model_safe(
                    model_name="Pyannote Embedding (for clustering)",
                    loader_func=_load_pyannote_embedding,
                    model_attr="pyannote_embedding_model"
                )
                
                if not success:
                    # Model loading failed, return unknown
                    logger.warning(
                        f"Clustering unavailable due to model loading failure, "
                        f"using 'unknown' label [session={self.session.session_id}]"
                    )
                    return "unknown"
            
            # Convert PCM bytes to numpy array
            # PCM format: 16-bit signed integers, mono, 16kHz
            audio_array = np.frombuffer(audio, dtype=np.int16)
            
            # Convert to float32 in [-1, 1] range (already normalized by caller)
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Pyannote expects shape (1, num_samples) and sample rate
            waveform = torch.from_numpy(audio_float).unsqueeze(0)  # Shape: (1, num_samples)
            
            # Create audio dictionary for Pyannote
            audio_dict = {
                "waveform": waveform,
                "sample_rate": 16000
            }
            
            # Generate embedding asynchronously
            # Run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            
            def _generate_embedding():
                # Pyannote Inference returns a numpy array embedding
                return self.pyannote_embedding_model(audio_dict)
            
            turn_embedding = await loop.run_in_executor(None, _generate_embedding)
            
            # Ensure embedding is a numpy array
            if isinstance(turn_embedding, torch.Tensor):
                turn_embedding = turn_embedding.cpu().numpy()
            
            # Flatten embedding if needed (should be 1D)
            if turn_embedding.ndim > 1:
                turn_embedding = turn_embedding.flatten()
            
            # Normalize embedding for cosine similarity
            turn_embedding_norm = turn_embedding / (np.linalg.norm(turn_embedding) + 1e-8)
            
            # Initialize speaker_clusters if not exists (Requirement 7.4)
            if not hasattr(self, 'speaker_clusters') or not self.speaker_clusters:
                self.speaker_clusters = {}
            
            # Find closest cluster using cosine similarity
            # Requirement 7.1: Assign labels based on speaker clusters
            best_cluster_id = None
            best_similarity = -1.0
            similarity_threshold = 0.60  # Lower threshold for clustering (more lenient)
            
            for cluster_id, cluster_data in self.speaker_clusters.items():
                # Calculate centroid of cluster
                cluster_embeddings = cluster_data['embeddings']
                cluster_centroid = np.mean(cluster_embeddings, axis=0)
                
                # Normalize centroid
                cluster_centroid_norm = cluster_centroid / (np.linalg.norm(cluster_centroid) + 1e-8)
                
                # Calculate cosine similarity
                similarity = float(np.dot(turn_embedding_norm, cluster_centroid_norm))
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_cluster_id = cluster_id
            
            # Assign to cluster or create new cluster
            if best_cluster_id is not None and best_similarity >= similarity_threshold:
                # Assign to existing cluster (Requirement 7.4: maintain clusters across turns)
                self.speaker_clusters[best_cluster_id]['embeddings'].append(turn_embedding)
                self.speaker_clusters[best_cluster_id]['turn_count'] += 1
                speaker_label = self.speaker_clusters[best_cluster_id]['label']
                
                logger.debug(
                    f"Clustering: Assigned to existing cluster {best_cluster_id} "
                    f"(similarity={best_similarity:.3f}), label={speaker_label} "
                    f"[session={self.session.session_id}]"
                )
            else:
                # Create new cluster
                # Requirement 7.2: Label first speaker as "user"
                # Requirement 7.3: Label second speaker as "counterparty"
                cluster_id = len(self.speaker_clusters)
                
                if cluster_id == 0:
                    speaker_label = "user"  # First speaker
                elif cluster_id == 1:
                    speaker_label = "counterparty"  # Second speaker
                else:
                    # More than 2 speakers detected (edge case)
                    # Label as "unknown" for 3+ speakers
                    speaker_label = "unknown"
                    logger.warning(
                        f"Clustering: More than 2 speakers detected (cluster_id={cluster_id}), "
                        f"labeling as 'unknown' [session={self.session.session_id}]"
                    )
                
                # Create new cluster
                self.speaker_clusters[cluster_id] = {
                    'label': speaker_label,
                    'embeddings': [turn_embedding],
                    'turn_count': 1
                }
                
                logger.info(
                    f"Clustering: Created new cluster {cluster_id}, label={speaker_label} "
                    f"[session={self.session.session_id}]"
                )
            
            # Requirement 7.6: Works without user enrollment
            logger.debug(
                f"Clustering identification successful: speaker={speaker_label}, "
                f"total_clusters={len(self.speaker_clusters)} [session={self.session.session_id}]"
            )
            
            return speaker_label
        
        except Exception as e:
            # Handle clustering failures gracefully
            audio_duration = len(audio) / (2 * 16000)
            
            self._log_error(
                error_type="clustering_failure",
                message="Clustering identification failed, using 'unknown' label",
                exception=e,
                audio_duration=audio_duration
            )
            
            # Return unknown label on error (fail-safe)
            return "unknown"
    
    async def _transcribe_turn(
        self,
        audio: bytes,
        speaker: str,
        start_time: float,
        end_time: float
    ) -> None:
        """
        Transcribe turn and send to frontend.
        
        Stage 5 of the 5-stage pipeline. Converts PCM audio to WAV format,
        sends to Gemini Flash API with speaker label, implements timeout and
        retry logic, and sends TRANSCRIPT_UPDATE to frontend.
        
        Args:
            audio: Turn audio (PCM 16-bit mono, 16kHz)
            speaker: Speaker label from identification ("user", "counterparty", "unknown")
            start_time: Turn start timestamp (seconds since epoch)
            end_time: Turn end timestamp (seconds since epoch)
        
        Side effects:
            - Sends TRANSCRIPT_UPDATE to frontend
            - Appends to listener_agent.accumulated_transcript
            - Updates session.speaker_timeline
        
        Performance: ~500-1000ms (API latency)
        
        Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 16.2, 17.2, 22.1, 22.4
        """
        import base64
        import time
        from google import genai
        from google.genai import types as genai_types
        
        # Start timing for transcription (Requirement 22.1)
        transcription_start_time = time.perf_counter()
        
        # Calculate audio duration for logging
        audio_duration = end_time - start_time
        
        try:
            # Generate unique turn ID for deduplication (Requirement 14.1)
            turn_id = self._generate_turn_id(start_time)
            
            # Check if already transcribed (prevent duplicates)
            if turn_id in self.transcribed_turn_ids:
                logger.debug(
                    f"Turn {turn_id} already transcribed, skipping "
                    f"[session={self.session.session_id}]"
                )
                return
            
            # Mark as transcribed immediately to prevent race conditions
            self.transcribed_turn_ids.add(turn_id)
            
            # Convert PCM to WAV format (Requirement 8.1)
            wav_bytes = self._pcm_to_wav(audio)
            audio_b64 = base64.b64encode(wav_bytes).decode()
            
            # Lazy load Gemini Flash client (Requirement 8.2)
            if self.flash_client is None:
                logger.info("Initializing Gemini Flash client...")
                
                if settings.GOOGLE_GENAI_USE_VERTEXAI:
                    import os
                    # Set environment variable for Vertex AI
                    if settings.GOOGLE_CLOUD_PROJECT:
                        os.environ["GOOGLE_CLOUD_PROJECT"] = settings.GOOGLE_CLOUD_PROJECT
                    
                    self.flash_client = genai.Client(
                        vertexai=True,
                        project=settings.GOOGLE_CLOUD_PROJECT,
                        location=settings.GOOGLE_CLOUD_LOCATION
                    )
                    logger.info(
                        f"Gemini Flash client initialized with Vertex AI "
                        f"[project={settings.GOOGLE_CLOUD_PROJECT}, "
                        f"location={settings.GOOGLE_CLOUD_LOCATION}]"
                    )
                else:
                    self.flash_client = genai.Client(api_key=settings.GEMINI_API_KEY)
                    logger.info("Gemini Flash client initialized with API key")
            
            # Get Flash model name
            flash_model = settings.effective_flash_model
            
            # Prepare transcription prompt with speaker label (Requirement 8.3)
            transcription_prompt = build_perfect_listener_transcription_prompt(speaker)
            
            # Implement retry logic with exponential backoff (Requirement 8.6)
            # 3 retries with backoff: 1s, 2s, 4s
            max_retries = 3
            retry_delays = [1.0, 2.0, 4.0]
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    # Log retry attempt (Requirement 17.2, 22.4)
                    if attempt > 0:
                        logger.info(
                            f"Transcription retry attempt {attempt}/{max_retries} for turn {turn_id} "
                            f"[session={self.session.session_id}]"
                        )
                    
                    # Start timing for API call (Requirement 22.4)
                    api_call_start = time.perf_counter()
                    
                    # Run transcription in executor to avoid blocking event loop
                    loop = asyncio.get_event_loop()
                    
                    def _call_flash():
                        # Call Gemini Flash API
                        response = self.flash_client.models.generate_content(
                            model=flash_model,
                            contents=[
                                genai_types.Content(
                                    role="user",
                                    parts=[
                                        genai_types.Part(
                                            inline_data=genai_types.Blob(
                                                data=audio_b64,
                                                mime_type="audio/wav",
                                            )
                                        ),
                                        genai_types.Part(text=transcription_prompt),
                                    ]
                                )
                            ],
                            config=genai_types.GenerateContentConfig(temperature=0.0),
                        )
                        return (response.text or "").strip()
                    
                    # Implement 10-second timeout (Requirement 8.5)
                    transcript_text = await asyncio.wait_for(
                        loop.run_in_executor(None, _call_flash),
                        timeout=10.0
                    )
                    
                    # Log API call latency (Requirement 22.4)
                    api_latency = time.perf_counter() - api_call_start
                    logger.debug(
                        f"Gemini Flash API call completed: latency={api_latency*1000:.1f}ms, "
                        f"attempt={attempt + 1} [session={self.session.session_id}]"
                    )
                    
                    # Success! Break out of retry loop
                    if transcript_text:
                        logger.info(
                            f"Transcription successful on attempt {attempt + 1}: "
                            f"speaker={speaker}, text_length={len(transcript_text)}, "
                            f"turn_id={turn_id} [session={self.session.session_id}]"
                        )
                        break
                    else:
                        # Empty transcript, treat as failure
                        raise ValueError("Empty transcript returned from API")
                
                except asyncio.TimeoutError as e:
                    last_exception = e
                    
                    # Log API latency for timeout (Requirement 22.4)
                    api_latency = time.perf_counter() - api_call_start
                    
                    # Log timeout with structured logging (Requirement 17.2, 17.5, 22.4)
                    self._log_error(
                        error_type="api_timeout",
                        message=f"Transcription timeout on attempt {attempt + 1}/{max_retries + 1}",
                        exception=e,
                        turn_id=turn_id,
                        audio_duration=audio_duration,
                        retry_attempt=attempt + 1,
                        max_retries=max_retries + 1,
                        api_latency_ms=api_latency * 1000
                    )
                    
                    # Retry with exponential backoff if not last attempt (Requirement 16.2, 17.2, 22.4)
                    if attempt < max_retries:
                        delay = retry_delays[attempt]
                        logger.info(
                            f"Retrying transcription in {delay}s (retry {attempt + 1}/{max_retries})... "
                            f"[session={self.session.session_id}]"
                        )
                        await asyncio.sleep(delay)
                    else:
                        # Last attempt failed, skip turn (Requirement 16.5, 17.2)
                        logger.error(
                            f"Transcription failed after {max_retries + 1} attempts (timeout), "
                            f"skipping turn {turn_id} [session={self.session.session_id}]"
                        )
                        return
                
                except Exception as e:
                    last_exception = e
                    
                    # Log API latency for error (Requirement 22.4)
                    api_latency = time.perf_counter() - api_call_start
                    
                    # Log error with structured logging (Requirement 17.2, 17.5, 22.4)
                    self._log_error(
                        error_type="api_error",
                        message=f"Transcription error on attempt {attempt + 1}/{max_retries + 1}",
                        exception=e,
                        turn_id=turn_id,
                        audio_duration=audio_duration,
                        retry_attempt=attempt + 1,
                        max_retries=max_retries + 1,
                        api_latency_ms=api_latency * 1000
                    )
                    
                    # Retry with exponential backoff if not last attempt (Requirement 16.2, 17.2, 22.4)
                    if attempt < max_retries:
                        delay = retry_delays[attempt]
                        logger.info(
                            f"Retrying transcription in {delay}s (retry {attempt + 1}/{max_retries})... "
                            f"[session={self.session.session_id}]"
                        )
                        await asyncio.sleep(delay)
                    else:
                        # Last attempt failed, skip turn (Requirement 16.5, 17.2)
                        self._log_error(
                            error_type="api_error_final",
                            message=f"Transcription failed after {max_retries + 1} attempts, skipping turn",
                            exception=last_exception,
                            turn_id=turn_id,
                            audio_duration=audio_duration
                        )
                        return
            
            # Verify we got a transcript
            if not transcript_text:
                logger.error(
                    f"No transcript text after retry loop, skipping turn {turn_id} "
                    f"[session={self.session.session_id}]"
                )
                return
            
            # Send TRANSCRIPT_UPDATE to frontend (Requirement 8.7)
            try:
                await self.websocket.send_json({
                    "type": "TRANSCRIPT_UPDATE",
                    "payload": {
                        "id": turn_id,
                        "speaker": speaker,
                        "text": transcript_text,
                        "timestamp": int(start_time * 1000),
                        "start_time": start_time,
                        "end_time": end_time,
                    },
                })
                
                logger.debug(
                    f"TRANSCRIPT_UPDATE sent to frontend: turn_id={turn_id}, "
                    f"speaker={speaker} [session={self.session.session_id}]"
                )
            except Exception as e:
                # Log WebSocket error with structured logging (Requirement 17.5)
                self._log_error(
                    error_type="websocket_error",
                    message="Failed to send TRANSCRIPT_UPDATE to frontend",
                    exception=e,
                    turn_id=turn_id,
                    audio_duration=audio_duration
                )
                # Continue processing even if WebSocket send fails
            
            # Append labeled transcript to accumulated_transcript (Requirement 8.8, 12.1)
            # Format: "[SPEAKER] transcript text\n"
            labeled_transcript = f"[{speaker.upper()}] {transcript_text}\n"
            self.listener_agent.accumulated_transcript += labeled_transcript
            
            # Keep transcript bounded to prevent unbounded growth (Requirement 12.1)
            # Keep last 6000 chars when exceeds 8000 chars (same as ListenerAgent)
            if len(self.listener_agent.accumulated_transcript) > 8000:
                self.listener_agent.accumulated_transcript = self.listener_agent.accumulated_transcript[-6000:]
                logger.debug(
                    f"Bounded accumulated_transcript to last 6000 chars "
                    f"[session={self.session.session_id}]"
                )
            
            logger.debug(
                f"Appended to accumulated_transcript: {len(labeled_transcript)} chars, "
                f"total={len(self.listener_agent.accumulated_transcript)} chars "
                f"[session={self.session.session_id}]"
            )
            
            # Update session.speaker_timeline (Requirement 12.2)
            self.session.speaker_timeline.append({
                "speaker": speaker,
                "timestamp": start_time,
            })
            
            # Keep timeline bounded to prevent unbounded growth (Requirement 12.2)
            # Keep last 5 minutes of entries (cap at 300 entries at ~1/s)
            if len(self.session.speaker_timeline) > 300:
                self.session.speaker_timeline = self.session.speaker_timeline[-300:]
                logger.debug(
                    f"Bounded speaker_timeline to last 300 entries "
                    f"[session={self.session.session_id}]"
                )
            
            logger.info(
                f"Turn transcription complete: turn_id={turn_id}, speaker={speaker}, "
                f"duration={end_time - start_time:.2f}s, text_length={len(transcript_text)} "
                f"[session={self.session.session_id}]"
            )
            
            # Log total transcription time (Requirement 22.1)
            total_time = time.perf_counter() - transcription_start_time
            logger.debug(
                f"Transcription stage completed: time={total_time*1000:.1f}ms "
                f"[session={self.session.session_id}]"
            )
        
        except Exception as e:
            # Handle unexpected errors gracefully (Requirement 16.5, 17.5)
            audio_duration = end_time - start_time
            turn_id = self._generate_turn_id(start_time)
            
            self._log_error(
                error_type="transcription_unexpected_error",
                message="Unexpected error in _transcribe_turn",
                exception=e,
                turn_id=turn_id,
                audio_duration=audio_duration
            )
            # Don't re-raise, just log and skip turn
    
    def _pcm_to_wav(self, pcm_data: bytes) -> bytes:
        """
        Convert PCM bytes to WAV format for API calls.
        
        Adds WAV header with correct parameters (16kHz, 16-bit, mono).
        
        Args:
            pcm_data: PCM audio bytes (16-bit signed integers, mono, 16kHz)
        
        Returns:
            WAV format bytes with header
        
        Requirements: 8.1
        """
        import struct
        
        # WAV format parameters
        sample_rate = 16000  # 16kHz
        num_channels = 1     # Mono
        sample_width = 2     # 16-bit (2 bytes per sample)
        byte_rate = sample_rate * num_channels * sample_width
        block_align = num_channels * sample_width
        data_size = len(pcm_data)
        
        # Create WAV header
        # Format: RIFF header + fmt chunk + data chunk
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",                    # ChunkID
            36 + data_size,             # ChunkSize (file size - 8)
            b"WAVE",                    # Format
            b"fmt ",                    # Subchunk1ID
            16,                         # Subchunk1Size (PCM = 16)
            1,                          # AudioFormat (PCM = 1)
            num_channels,               # NumChannels
            sample_rate,                # SampleRate
            byte_rate,                  # ByteRate
            block_align,                # BlockAlign
            sample_width * 8,           # BitsPerSample
            b"data",                    # Subchunk2ID
            data_size,                  # Subchunk2Size
        )
        
        return header + pcm_data
    
    def _generate_turn_id(self, start_time: float) -> str:
        """
        Generate unique turn ID from timestamp.
        
        Format: turn_{timestamp_ms}
        
        Args:
            start_time: Turn start timestamp (seconds since epoch)
        
        Returns:
            Unique turn ID string
        
        Requirements: 14.1
        """
        timestamp_ms = int(start_time * 1000)
        return f"turn_{timestamp_ms}"
    
    def _normalize_audio(self, audio: bytes) -> bytes:
        """
        Normalize audio to [-1, 1] range, scale to 95% to avoid clipping.
        
        Ensures consistent speaker identification regardless of volume.
        Applied to both enrollment and runtime audio.
        
        Args:
            audio: PCM audio bytes (16-bit signed integers, mono, 16kHz)
        
        Returns:
            Normalized audio bytes (PCM 16-bit mono, 16kHz, scaled to 95%)
        
        Requirements: 15.1, 15.2, 15.3, 15.4, 15.5
        """
        import numpy as np
        
        try:
            # Convert PCM bytes to numpy array
            # PCM format: 16-bit signed integers, mono, 16kHz
            audio_array = np.frombuffer(audio, dtype=np.int16)
            
            # Convert to float32 in [-1, 1] range
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Find max absolute value
            max_val = np.abs(audio_float).max()
            
            if max_val > 0:
                # Normalize to [-1, 1] range
                audio_normalized = audio_float / max_val
                
                # Scale to 95% to avoid clipping (Requirement 15.2)
                audio_normalized = audio_normalized * 0.95
            else:
                # Silence or near-silence, no normalization needed
                audio_normalized = audio_float
            
            # Convert back to 16-bit PCM
            # Clip to [-1, 1] range to be safe
            audio_normalized = np.clip(audio_normalized, -1.0, 1.0)
            
            # Scale to int16 range
            audio_int16 = (audio_normalized * 32767).astype(np.int16)
            
            # Convert to bytes
            return audio_int16.tobytes()
        
        except Exception as e:
            # Handle normalization errors gracefully
            logger.error(
                f"Audio normalization failed: {e} [session={self.session.session_id}]",
                exc_info=True
            )
            
            # Return original audio on error (fail-safe)
            return audio
    
    def _log_error(
        self,
        error_type: str,
        message: str,
        exception: Optional[Exception] = None,
        turn_id: Optional[str] = None,
        audio_duration: Optional[float] = None,
        **extra_context
    ) -> None:
        """
        Log errors with structured context for debugging.
        
        Implements graceful error logging with session_id, turn_id, audio_duration,
        error type, message, and stack trace.
        
        Args:
            error_type: Type of error (e.g., "model_loading", "api_timeout", "separation_failure")
            message: Human-readable error message
            exception: Optional exception object for stack trace
            turn_id: Optional turn ID for turn-specific errors
            audio_duration: Optional audio duration in seconds
            **extra_context: Additional context fields (e.g., model_name, retry_attempt)
        
        Requirements: 22.5, 22.6, 17.5
        """
        import json
        import traceback
        
        # Build structured log context
        log_context = {
            "error_type": error_type,
            "session_id": self.session.session_id,
            "message": message,
        }
        
        # Add optional fields
        if turn_id:
            log_context["turn_id"] = turn_id
        
        if audio_duration is not None:
            log_context["audio_duration"] = audio_duration
        
        # Add exception details
        if exception:
            log_context["exception_type"] = type(exception).__name__
            log_context["exception_message"] = str(exception)
            log_context["stack_trace"] = traceback.format_exc()
        
        # Add extra context
        log_context.update(extra_context)
        
        # Log as JSON for structured logging (Requirement 22.7)
        try:
            log_json = json.dumps(log_context, indent=2)
            logger.error(f"Structured error log:\n{log_json}")
        except Exception as json_error:
            # Fallback to simple logging if JSON serialization fails
            logger.error(
                f"Error logging failed (JSON serialization error): {json_error}",
                exc_info=True
            )
            logger.error(f"Original error: {message}", exc_info=exception is not None)
    
    def _load_model_safe(
        self,
        model_name: str,
        loader_func: callable,
        model_attr: str
    ) -> bool:
        """
        Safely load a model with error handling and fallback.
        
        Wraps model loading in try-except blocks, logs errors with model name
        and exception details, and handles fallback based on PERFECT_LISTENER_FALLBACK.
        
        Args:
            model_name: Human-readable model name (e.g., "Pyannote OverlappedSpeechDetection")
            loader_func: Function that loads and returns the model
            model_attr: Attribute name to store the loaded model (e.g., "overlap_detector")
        
        Returns:
            True if model loaded successfully, False otherwise
        
        Raises:
            RuntimeError: If loading fails and PERFECT_LISTENER_FALLBACK is False
        
        Requirements: 16.1, 17.1, 22.6
        """
        import time
        import torch
        
        try:
            # Check if model already loaded
            if getattr(self, model_attr, None) is not None:
                return True
            
            # Check if this model previously failed to load
            if model_name in self.model_load_errors:
                logger.debug(
                    f"Model {model_name} previously failed to load, skipping "
                    f"[session={self.session.session_id}]"
                )
                return False
            
            # Log model loading start (Requirement 22.6)
            device = "GPU (CUDA)" if torch.cuda.is_available() else "CPU"
            logger.info(
                f"Loading {model_name} on {device}... [session={self.session.session_id}]"
            )
            
            # Start timing for model loading
            load_start = time.perf_counter()
            
            # Load the model
            model = loader_func()

            # If loader returned None it failed silently — treat as failure
            # so we don't retry on every subsequent call
            if model is None:
                self.model_load_errors[model_name] = "loader returned None"
                logger.warning(
                    f"{model_name} loader returned None, marking as failed to prevent retry "
                    f"[session={self.session.session_id}]"
                )
                return False

            # Store the model
            setattr(self, model_attr, model)

            # Log model loading completion (Requirement 22.6)
            load_time = time.perf_counter() - load_start
            logger.info(
                f"{model_name} loaded successfully: device={device}, "
                f"time={load_time:.2f}s [session={self.session.session_id}]"
            )
            return True
        
        except Exception as e:
            # Log error with structured logging (Requirement 17.1)
            self._log_error(
                error_type="model_loading",
                message=f"Failed to load {model_name}",
                exception=e,
                model_name=model_name,
                model_attr=model_attr
            )
            
            # Track failed model
            self.model_load_errors[model_name] = str(e)
            
            # Handle fallback based on configuration (Requirement 16.1)
            if settings.PERFECT_LISTENER_FALLBACK:
                logger.warning(
                    f"Model loading failed for {model_name}, continuing with degraded functionality "
                    f"(PERFECT_LISTENER_FALLBACK=true) [session={self.session.session_id}]"
                )
                return False
            else:
                # Raise exception if fallback is disabled
                logger.error(
                    f"Model loading failed for {model_name}, raising exception "
                    f"(PERFECT_LISTENER_FALLBACK=false) [session={self.session.session_id}]"
                )
                raise RuntimeError(
                    f"Failed to load {model_name}: {e}. "
                    f"Set PERFECT_LISTENER_FALLBACK=true to enable fallback to old system."
                ) from e
    
    async def stop(self) -> None:
        """
        Stop processing and cleanup resources.
        
        Called from NegotiationEngine.handle_end().
        Clears buffers and releases model references.
        
        Requirements: 20.4, 20.5, 20.6, 13.6 (15.6)
        """
        # 15.6: Clear all buffers on session end (Requirement 13.6)
        # Task 20.3: Use clear() for efficient buffer reset
        self.frame_buffer.clear()
        self.turn_buffer.clear()
        self.overlap_window.clear()
        
        # Clear state
        self.current_speaker = ""
        self.transcribed_turn_ids.clear()
        self.speaker_clusters.clear()
        
        # Release model references (Requirement 20.6)
        # Note: Models are shared across sessions, so we only clear references
        # The actual model objects will be garbage collected when no sessions reference them
        self.overlap_detector = None
        self.separator = None
        self.vad_pipeline = None
        self.speaker_model = None
        self.pyannote_embedding_model = None
        self.flash_client = None
        
        # Log cleanup completion
        logger.info(
            f"PerfectListenerSystem stopped and cleaned up "
            f"[session={self.session.session_id}] "
            f"(buffers cleared, model references released)"
        )
