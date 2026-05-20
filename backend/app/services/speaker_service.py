"""
Speaker Service

This module handles real-time speaker classification during negotiations.
It uses Voice Activity Detection (VAD) to detect speech segments, generates
voice embeddings, and classifies speakers as "user" or "counterparty" based
on cosine similarity with the enrolled voice fingerprint.

The service processes audio in 30ms frames, detects segment boundaries,
and runs classification asynchronously to avoid blocking the event loop.

OPTIMIZATIONS:
- Only embeds first 2 seconds of audio (speaker identity established early)
- VAD aggressiveness level 2 (balanced for real-world environments)
- Min segment duration 0.5s (catches short responses like "no", "okay")
"""

import logging
import time
import asyncio
from typing import Optional
import numpy as np
import webrtcvad
import torch

from app.models.negotiation import NegotiationSession
from app.services.speechbrain_service import speechbrain_service
from app.config import settings

logger = logging.getLogger(__name__)


class SpeakerService:
    """
    Real-time speaker classification service.
    
    This service:
    1. Processes incoming PCM audio using Voice Activity Detection (VAD)
    2. Detects speech segment boundaries (silence → speech, speech → silence)
    3. Generates voice embeddings for complete segments (first 2s only)
    4. Classifies speakers using cosine similarity with user enrollment
    5. Updates session state with speaker labels and confidence scores
    
    Attributes:
        session: The negotiation session containing user enrollment
        vad: WebRTC VAD instance for speech detection
        frame_buffer: Accumulates bytes until complete 30ms frame
        is_speech: Current speech state (True = speech, False = silence)
        segment_start_time: Timestamp when current segment started
        current_segment: Accumulated audio bytes for current segment
    """
    
    # Constants
    SAMPLE_RATE = 16000  # Hz
    BYTES_PER_SAMPLE = 2  # 16-bit audio
    FRAME_DURATION_MS = 30  # milliseconds
    FRAME_SIZE = (SAMPLE_RATE * FRAME_DURATION_MS // 1000) * BYTES_PER_SAMPLE  # 960 bytes
    MAX_EMBED_DURATION = 2.0  # seconds
    USER_BOOTSTRAP_MARGIN = 0.10  # first post-enrollment segment can be slightly below the main threshold
    USER_STICKY_THRESHOLD = 0.58  # only keep the same speaker when similarity is still reasonably strong
    STICKY_SPEAKER_MAX_GAP_SECONDS = 2.5  # sticky logic only applies to immediately consecutive speech
    COUNTERPARTY_THRESHOLD = 0.38  # low similarity means "not the enrolled user" in a 2-party conversation
    
    def __init__(self, session: NegotiationSession, on_segment_complete_callback=None):
        """
        Initialize speaker service for a session.
        
        Args:
            session: The negotiation session with user enrollment
            on_segment_complete_callback: Optional async callback(speaker, audio, timestamp, speaker_changed) 
                                         called when a speech segment completes (VAD detects silence)
        """
        self.session = session
        self.on_segment_complete_callback = on_segment_complete_callback
        
        # Initialize VAD with aggressiveness from config
        aggressiveness = getattr(settings, 'SPEAKER_VAD_AGGRESSIVENESS', 2)
        self.vad = webrtcvad.Vad(aggressiveness)
        
        # Frame buffering
        self.frame_buffer: bytes = b""
        
        # Segment tracking
        self.is_speech: bool = False
        self.segment_start_time: Optional[float] = None
        self.current_segment: bytes = b""
        
        # Rate limiting for transcription (prevent 429 errors)
        self.last_transcription_time: float = 0.0
        self.min_transcription_gap: float = 3.0  # Minimum 3 seconds between transcriptions
        
        logger.info(f"SpeakerService initialized [session={session.session_id}, vad_aggressiveness={aggressiveness}]")
    
    async def feed_audio(self, chunk: bytes) -> None:
        """
        Process incoming PCM audio for speaker classification.
        
        This method buffers audio until complete 30ms frames are available,
        then processes each frame through VAD to detect speech segments.
        
        Args:
            chunk: PCM audio chunk (any size, will be buffered)
        """
        # Check if session is still active (negotiation not ended)
        if self.session.state.value not in ["ACTIVE", "CONSENTED"]:
            logger.debug(f"Ignoring audio - session state is {self.session.state.value}")
            return
        
        # Accumulate audio into frame buffer
        self.frame_buffer += chunk
        
        # Process complete frames
        while len(self.frame_buffer) >= self.FRAME_SIZE:
            frame = self.frame_buffer[:self.FRAME_SIZE]
            self.frame_buffer = self.frame_buffer[self.FRAME_SIZE:]
            self._process_frame(frame)
    
    def _process_frame(self, frame: bytes) -> None:
        """
        Run VAD on a single 30ms frame.
        
        This method:
        1. Checks if frame contains speech using webrtcvad
        2. Detects segment boundaries (silence → speech, speech → silence)
        3. Accumulates frames into current segment
        4. Triggers classification when segment ends
        
        Args:
            frame: Exactly 960 bytes (30ms at 16kHz, 16-bit mono)
        """
        try:
            # Run VAD on frame
            is_speech = self.vad.is_speech(frame, self.SAMPLE_RATE)
            
            # Detect silence → speech transition (segment start)
            if is_speech and not self.is_speech:
                self.is_speech = True
                self.segment_start_time = time.time()
                self.current_segment = frame
                logger.debug("Speech segment started")
            
            # Continue accumulating speech
            elif is_speech and self.is_speech:
                self.current_segment += frame
            
            # Detect speech → silence transition (segment end)
            elif not is_speech and self.is_speech:
                self.is_speech = False
                
                # Calculate segment duration
                duration = len(self.current_segment) / (self.SAMPLE_RATE * self.BYTES_PER_SAMPLE)
                logger.debug(f"Speech segment ended: {duration:.2f}s")
                
                # Classify segment asynchronously
                segment_audio = self.current_segment
                self.current_segment = b""
                asyncio.create_task(self._classify_segment(segment_audio))
        
        except Exception as e:
            logger.error(f"VAD frame processing error: {e}", exc_info=True)
            # Graceful degradation: continue processing next frames
    
    async def _classify_segment(self, audio: bytes) -> str:
        """
        Classify a speech segment as user or counterparty.
        
        OPTIMIZED: Only embeds first 2 seconds of audio for speed.
        Speaker identity is established in the first utterance.
        
        This method:
        1. Checks minimum segment duration
        2. Checks if user enrollment exists
        3. Checks manual override status
        4. Truncates audio to first 2 seconds (SPEED OPTIMIZATION)
        5. Generates segment embedding
        6. Calculates cosine similarity with user embedding
        7. Applies threshold to determine speaker label
        8. Updates session state
        
        Args:
            audio: PCM audio of complete speech segment
            
        Returns:
            Speaker label: "user", "counterparty", or "unknown"
        """
        try:
            # Check if session is still active (negotiation not ended)
            if self.session.state.value not in ["ACTIVE", "CONSENTED"]:
                logger.debug(f"Skipping classification - session state is {self.session.state.value}")
                return "unknown"
            
            # Calculate segment duration
            duration = len(audio) / (self.SAMPLE_RATE * self.BYTES_PER_SAMPLE)
            
            # Check minimum segment duration
            min_duration = getattr(settings, 'SPEAKER_MIN_SEGMENT_DURATION', 0.5)
            if duration < min_duration:
                logger.debug(f"Segment too short ({duration:.2f}s < {min_duration}s), skipping classification")
                return "unknown"
            
            # Check if enrollment exists (CRITICAL: Check before processing)
            if self.session.user_embedding is None:
                logger.debug("No user enrollment found, skipping classification")
                return "unknown"
            
            # Check manual override
            if self.session.manual_override_until:
                if isinstance(self.session.manual_override_until, float):
                    if time.time() < self.session.manual_override_until:
                        logger.debug("Manual override active, using manual label")
                        return self.session.current_speaker
                elif self.session.manual_override_until == float('inf'):
                    logger.debug("Manual mode active, using manual label")
                    return self.session.current_speaker
            
            # Take the first MAX_EMBED_DURATION seconds of the segment.
            # VAD ensures the audio starts with speech (no leading silence), so the
            # beginning of the utterance is the most representative for identification.
            # Previously used a middle slice, but that degrades quality for short
            # utterances because the acoustic context is broken at both boundaries.
            max_bytes = int(self.MAX_EMBED_DURATION * self.SAMPLE_RATE * self.BYTES_PER_SAMPLE)
            if len(audio) > max_bytes:
                audio_for_embedding = audio[:max_bytes]
                logger.debug(
                    f"Trimmed {duration:.2f}s segment to first {self.MAX_EMBED_DURATION:.2f}s for embedding"
                )
            else:
                audio_for_embedding = audio
            
            # Generate segment embedding (CPU-intensive, run in thread pool)
            loop = asyncio.get_event_loop()
            
            # Convert PCM bytes to tensor for SpeechBrain
            def extract_embedding_sync():
                return speechbrain_service.extract_embedding(audio_for_embedding)
            
            segment_embedding = await loop.run_in_executor(
                None,
                extract_embedding_sync
            )
            
            # CRITICAL: Check again if enrollment still exists (might have been cleared during embedding)
            # This prevents the NoneType error when session ends during classification
            user_embedding = self.session.user_embedding
            if user_embedding is None:
                logger.debug("User enrollment was cleared during processing, skipping classification")
                return "unknown"
            
            # Calculate cosine similarity and clamp to [0, 1] for easier reasoning.
            # Use local variable to avoid race condition if embedding is cleared between check and calculation.
            # SpeechBrain embeddings are torch tensors, so use torch operations
            segment_embedding_tensor = segment_embedding if isinstance(segment_embedding, torch.Tensor) else torch.tensor(segment_embedding)
            user_embedding_tensor = user_embedding if isinstance(user_embedding, torch.Tensor) else torch.tensor(user_embedding)
            
            similarity = float(torch.nn.functional.cosine_similarity(
                segment_embedding_tensor.unsqueeze(0), 
                user_embedding_tensor.unsqueeze(0), 
                dim=1
            ).item())
            similarity = max(0.0, min(1.0, similarity))

            # Three-way decision:
            # - confidently user
            # - confidently not the enrolled user => counterparty
            # - otherwise unknown
            threshold = settings.USER_VERIFY_THRESHOLD
            user_bootstrap_threshold = max(0.0, threshold - self.USER_BOOTSTRAP_MARGIN)
            current_speaker = self.session.current_speaker
            current_time = time.time()
            time_since_last_label = current_time - (self.session.speaker_last_updated or 0.0)
            is_first_auto_classification = self.session.speaker_last_updated == 0

            if similarity >= threshold:
                label = "user"
            elif (
                is_first_auto_classification
                and similarity >= user_bootstrap_threshold
            ):
                label = "user"
            elif (
                current_speaker == "user"
                and time_since_last_label <= self.STICKY_SPEAKER_MAX_GAP_SECONDS
                and similarity >= self.USER_STICKY_THRESHOLD
            ):
                # Only keep the current user turn sticky across short pauses when
                # the similarity remains reasonably strong.
                label = "user"
            elif similarity <= self.COUNTERPARTY_THRESHOLD:
                label = "counterparty"
            else:
                label = "unknown"
            
            # Detect speaker change
            speaker_changed = self.session.current_speaker != label
            
            # Update session state
            if label != "unknown":
                self.session.current_speaker = label
                self.session.speaker_last_updated = current_time
            
            # Append to confidence history
            self.session.speaker_confidence_history.append({
                "speaker": label,
                "timestamp": current_time,
                "confidence": similarity,
                "duration": duration
            })
            
            # Append to speaker timeline (used by ListenerAgent)
            if label != "unknown":
                self.session.speaker_timeline.append({
                    "speaker": label,
                    "timestamp": current_time
                })
            
            logger.info(
                f"Speaker classified: {label} (confidence={similarity:.3f}, duration={duration:.2f}s, "
                f"user_threshold={threshold:.3f}, counterparty_threshold={self.COUNTERPARTY_THRESHOLD:.3f}, "
                f"user_bootstrap_threshold={user_bootstrap_threshold:.3f}, "
                f"user_sticky_threshold={self.USER_STICKY_THRESHOLD:.3f}, "
                f"time_since_last_label={time_since_last_label:.2f}) "
                f"[session={self.session.session_id}]"
            )
            
            # Rate-limited transcription to prevent 429 errors and garbage output
            # Only transcribe if:
            # 1. Enough time has passed since last transcription (min_transcription_gap)
            # 2. OR speaker changed (important transition)
            time_since_last = current_time - self.last_transcription_time
            should_transcribe = (
                speaker_changed or 
                time_since_last >= self.min_transcription_gap
            )
            
            min_transcription_duration = 1.5
            if (
                self.on_segment_complete_callback
                and should_transcribe
                and label in {"user", "counterparty"}
                and duration >= min_transcription_duration
            ):
                self.last_transcription_time = current_time
                reason = "speaker_changed" if speaker_changed else "time_gap"
                logger.info(f"🎤 Segment complete: {label} spoke for {duration:.2f}s, triggering transcription ({reason})")
                asyncio.create_task(self.on_segment_complete_callback(
                    speaker=label,
                    audio=audio,
                    timestamp=current_time,
                    speaker_changed=speaker_changed
                ))
            elif self.on_segment_complete_callback and label == "unknown":
                logger.info(
                    f"Skipping transcription for ambiguous speaker segment "
                    f"(confidence={similarity:.3f}, duration={duration:.2f}s)"
                )
            elif self.on_segment_complete_callback and duration < min_transcription_duration:
                logger.info(
                    f"Skipping transcription for short segment "
                    f"(speaker={label}, confidence={similarity:.3f}, duration={duration:.2f}s)"
                )
            elif self.on_segment_complete_callback:
                logger.debug(f"⏭️ Skipping transcription: {label} spoke for {duration:.2f}s (rate limited, {time_since_last:.1f}s since last)")
            
            return label
        
        except Exception as e:
            logger.error(f"Classification failed: {e}", exc_info=True)
            # Graceful degradation: return unknown and continue
            return "unknown"
    
    def get_current_speaker(self) -> str:
        """
        Get the most recent speaker label.
        
        Returns:
            Speaker label: "user", "counterparty", or "unknown"
        """
        return self.session.current_speaker
    
    def get_confidence_score(self) -> float:
        """
        Get the cosine similarity score of the last classification.
        
        Returns:
            Confidence score (0.0 to 1.0), or 0.0 if no classifications yet
        """
        if not self.session.speaker_confidence_history:
            return 0.0
        
        return self.session.speaker_confidence_history[-1].get("confidence", 0.0)

    async def classify_utterance(
        self,
        audio: bytes,
        *,
        duration_ms: int,
        transcription_confidence: float | None,
        utterance_id: str,
        timestamp: float | None = None,
    ) -> tuple[str, float | None]:
        """Classify a completed utterance with conservative three-state logic."""
        if self.session.user_embedding is None:
            self._record_label("unknown", None, duration_ms, timestamp or time.time())
            return "unknown", None

        if duration_ms < settings.MIN_TRANSCRIBE_DURATION_MS:
            self._record_label("unknown", None, duration_ms, timestamp or time.time())
            return "unknown", None

        max_bytes = int(self.MAX_EMBED_DURATION * self.SAMPLE_RATE * self.BYTES_PER_SAMPLE)
        if len(audio) > max_bytes:
            audio_for_embedding = audio[:max_bytes]
        else:
            audio_for_embedding = audio

        loop = asyncio.get_event_loop()

        def extract_embedding_sync():
            return speechbrain_service.extract_embedding(audio_for_embedding)
        
        embedding = await loop.run_in_executor(None, extract_embedding_sync)
        user_embedding = self.session.user_embedding
        if user_embedding is None:
            self._record_label("unknown", None, duration_ms, timestamp or time.time())
            return "unknown", None

        # SpeechBrain embeddings are torch tensors
        embedding_tensor = embedding if isinstance(embedding, torch.Tensor) else torch.tensor(embedding)
        user_embedding_tensor = user_embedding if isinstance(user_embedding, torch.Tensor) else torch.tensor(user_embedding)
        
        similarity = float(torch.nn.functional.cosine_similarity(
            embedding_tensor.unsqueeze(0),
            user_embedding_tensor.unsqueeze(0),
            dim=1
        ).item())
        similarity = max(0.0, min(1.0, similarity))
        event_time = timestamp or time.time()
        time_since_last_label = event_time - (self.session.speaker_last_updated or 0.0)

        if similarity >= settings.USER_VERIFY_THRESHOLD:
            self.session.current_speaker = "user"
            self.session.speaker_last_updated = event_time
            self._record_label("user", similarity, duration_ms, event_time)
            logger.info(
                "Utterance speaker classified: user (similarity=%.3f, duration_ms=%s, utterance_id=%s, "
                "user_threshold=%.3f, counterparty_threshold=%.3f, stt_confidence=%s) [session=%s]",
                similarity,
                duration_ms,
                utterance_id,
                settings.USER_VERIFY_THRESHOLD,
                settings.COUNTERPARTY_REJECT_THRESHOLD,
                transcription_confidence,
                self.session.session_id,
            )
            return "user", similarity
        elif (
            self.session.current_speaker == "user"
            and time_since_last_label <= settings.USER_CONTINUATION_WINDOW_SECONDS
            and similarity >= settings.USER_CONTINUATION_THRESHOLD
        ):
            self.session.current_speaker = "user"
            self.session.speaker_last_updated = event_time
            self._record_label("user", similarity, duration_ms, event_time)
            logger.info(
                "Utterance speaker classified: user (continuation, similarity=%.3f, duration_ms=%s, utterance_id=%s, "
                "user_threshold=%.3f, continuation_threshold=%.3f, continuation_window=%.1fs, stt_confidence=%s) [session=%s]",
                similarity,
                duration_ms,
                utterance_id,
                settings.USER_VERIFY_THRESHOLD,
                settings.USER_CONTINUATION_THRESHOLD,
                settings.USER_CONTINUATION_WINDOW_SECONDS,
                transcription_confidence,
                self.session.session_id,
            )
            return "user", similarity

        candidate_ok = (
            similarity <= settings.COUNTERPARTY_REJECT_THRESHOLD
            and (transcription_confidence is None or transcription_confidence >= settings.COUNTERPARTY_STT_CONFIDENCE_MIN)
        )
        if candidate_ok:
            promoted = self._promote_or_match_counterparty(
                embedding=embedding,
                utterance_id=utterance_id,
                timestamp=event_time,
            )
            if promoted:
                self.session.current_speaker = "counterparty"
                self.session.speaker_last_updated = event_time
                self._record_label("counterparty", similarity, duration_ms, event_time)
                logger.info(
                    "Utterance speaker classified: counterparty (similarity=%.3f, duration_ms=%s, utterance_id=%s, "
                    "user_threshold=%.3f, counterparty_threshold=%.3f, stt_confidence=%s) [session=%s]",
                    similarity,
                    duration_ms,
                    utterance_id,
                    settings.USER_VERIFY_THRESHOLD,
                    settings.COUNTERPARTY_REJECT_THRESHOLD,
                    transcription_confidence,
                    self.session.session_id,
                )
                return "counterparty", similarity

        self._record_label("unknown", similarity, duration_ms, event_time)
        logger.info(
            "Utterance speaker classified: unknown (similarity=%.3f, duration_ms=%s, utterance_id=%s, "
            "user_threshold=%.3f, continuation_threshold=%.3f, counterparty_threshold=%.3f, "
            "stt_confidence=%s, candidate_ok=%s) [session=%s]",
            similarity,
            duration_ms,
            utterance_id,
            settings.USER_VERIFY_THRESHOLD,
            settings.USER_CONTINUATION_THRESHOLD,
            settings.COUNTERPARTY_REJECT_THRESHOLD,
            transcription_confidence,
            candidate_ok,
            self.session.session_id,
        )
        return "unknown", similarity

    def _promote_or_match_counterparty(
        self,
        *,
        embedding: torch.Tensor,
        utterance_id: str,
        timestamp: float,
    ) -> bool:
        window_start = timestamp - 30.0
        candidates = [
            candidate
            for candidate in self.session.counterparty_candidates
            if candidate.get("timestamp", 0.0) >= window_start
        ]
        self.session.counterparty_candidates = candidates

        cluster_embedding = self.session.counterparty_cluster_embedding
        if cluster_embedding is not None:
            # Convert to tensors for SpeechBrain
            embedding_tensor = embedding if isinstance(embedding, torch.Tensor) else torch.tensor(embedding)
            cluster_tensor = cluster_embedding if isinstance(cluster_embedding, torch.Tensor) else torch.tensor(cluster_embedding)
            
            cluster_similarity = float(torch.nn.functional.cosine_similarity(
                embedding_tensor.unsqueeze(0),
                cluster_tensor.unsqueeze(0),
                dim=1
            ).item())
            return cluster_similarity >= settings.COUNTERPARTY_CLUSTER_THRESHOLD

        if candidates:
            first_embedding = candidates[0]["embedding"]
            
            # Convert to tensors for SpeechBrain
            embedding_tensor = embedding if isinstance(embedding, torch.Tensor) else torch.tensor(embedding)
            first_tensor = first_embedding if isinstance(first_embedding, torch.Tensor) else torch.tensor(first_embedding)
            
            cluster_similarity = float(torch.nn.functional.cosine_similarity(
                embedding_tensor.unsqueeze(0),
                first_tensor.unsqueeze(0),
                dim=1
            ).item())
            
            if cluster_similarity >= settings.COUNTERPARTY_CLUSTER_THRESHOLD:
                # Average the embeddings for cluster
                if isinstance(first_embedding, torch.Tensor) and isinstance(embedding, torch.Tensor):
                    cluster_mean = torch.mean(torch.stack([first_embedding, embedding], dim=0), dim=0)
                else:
                    cluster_mean = torch.mean(torch.stack([first_tensor, embedding_tensor], dim=0), dim=0)
                
                # Normalize
                norm = torch.linalg.norm(cluster_mean)
                if norm > 0:
                    self.session.counterparty_cluster_embedding = cluster_mean / norm
                else:
                    self.session.counterparty_cluster_embedding = cluster_mean
                    
                self.session.counterparty_cluster_promoted_at = timestamp
                return True

        self.session.counterparty_candidates.append(
            {
                "embedding": embedding,
                "utterance_id": utterance_id,
                "timestamp": timestamp,
            }
        )
        self.session.counterparty_candidates = self.session.counterparty_candidates[-5:]
        # Enrollment completion counts as "user confirmed": the enrolled voice IS the user,
        # so any voice that clearly doesn't match it is the counterparty — we don't need
        # to wait for the user to speak first.
        user_confirmed_at_least_once = (
            self.session.user_embedding is not None
            or any(entry.get("speaker") == "user" for entry in self.session.speaker_confidence_history)
            or any(role == "user" for role in self.session.speaker_mapping.values())
        )
        return user_confirmed_at_least_once

    def _record_label(
        self,
        label: str,
        similarity: float | None,
        duration_ms: int,
        timestamp: float,
    ) -> None:
        self.session.speaker_confidence_history.append(
            {
                "speaker": label,
                "timestamp": timestamp,
                "confidence": similarity,
                "duration_ms": duration_ms,
            }
        )
        metric_key = {
            "user": "speaker_user_count",
            "counterparty": "speaker_counterparty_count",
            "unknown": "speaker_unknown_count",
        }[label]
        self.session.session_metrics[metric_key] += 1
