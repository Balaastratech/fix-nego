"""
Manual Mode Compatibility Verification Tests

Verifies that manual mode transcription continues to work correctly
after PerfectListenerSystem integration.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
"""

import pytest
import asyncio
import math
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from app.services.perfect_listener import PerfectListenerSystem
from app.services.listener_agent import ListenerAgent


class TestManualModeCompatibility:
    """Test suite for manual mode compatibility with PerfectListenerSystem"""
    
    @pytest.mark.asyncio
    async def test_manual_mode_skips_automatic_processing(self):
        """
        Requirement 9.1, 9.2: When manual_override_until is infinity,
        PerfectListenerSystem SHALL skip automatic processing.
        """
        # Arrange
        session = Mock()
        session.session_id = "test-session"
        session.manual_override_until = float('inf')  # Manual mode active
        
        websocket = AsyncMock()
        listener_agent = Mock()
        
        perfect_listener = PerfectListenerSystem(
            session=session,
            websocket=websocket,
            listener_agent=listener_agent
        )
        
        # Mock the internal methods to verify they're NOT called
        perfect_listener._detect_overlap = AsyncMock()
        perfect_listener._separate_speakers = AsyncMock()
        perfect_listener._segment_turns = AsyncMock()
        perfect_listener._identify_speaker = AsyncMock()
        perfect_listener._transcribe_turn = AsyncMock()
        
        # Act
        chunk = b'\x00' * 3200  # 100ms of audio
        await perfect_listener.process_audio_chunk(chunk)
        
        # Assert
        # None of the pipeline stages should be called
        perfect_listener._detect_overlap.assert_not_called()
        perfect_listener._separate_speakers.assert_not_called()
        perfect_listener._segment_turns.assert_not_called()
        perfect_listener._identify_speaker.assert_not_called()
        perfect_listener._transcribe_turn.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_manual_mode_skips_when_override_in_future(self):
        """
        Requirement 9.2: When manual_override_until is in the future,
        PerfectListenerSystem SHALL skip automatic processing.
        """
        # Arrange
        import time
        session = Mock()
        session.session_id = "test-session"
        session.manual_override_until = time.time() + 10  # 10 seconds in future
        
        websocket = AsyncMock()
        listener_agent = Mock()
        
        perfect_listener = PerfectListenerSystem(
            session=session,
            websocket=websocket,
            listener_agent=listener_agent
        )
        
        # Mock the internal methods
        perfect_listener._detect_overlap = AsyncMock()
        
        # Act
        chunk = b'\x00' * 3200
        await perfect_listener.process_audio_chunk(chunk)
        
        # Assert
        perfect_listener._detect_overlap.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_current_segment_audio_accumulation_continues(self):
        """
        Requirement 9.3, 9.4: During manual mode, current_segment_audio
        accumulation SHALL continue in handle_audio_chunk.
        """
        # This test verifies the NegotiationEngine behavior
        # The actual implementation is in negotiation_engine.py handle_audio_chunk()
        
        # Arrange
        from app.services.negotiation_engine import NegotiationEngine
        
        session = Mock()
        session.session_id = "test-session"
        session.live_session = True
        session.user_addressing_ai = False
        session.current_speaker = "user"
        session.audio_buffer = Mock()
        session.audio_buffer.push = Mock()
        session.current_segment_audio = b""
        session.manual_override_until = float('inf')  # Manual mode
        session.perfect_listener = Mock()
        session.perfect_listener.process_audio_chunk = AsyncMock()
        
        # Act
        chunk = b'\x00' * 3200  # 100ms of audio
        await NegotiationEngine.handle_audio_chunk(session, chunk)
        
        # Assert
        # Audio should be accumulated in current_segment_audio
        assert len(session.current_segment_audio) == 3200
        
        # Audio should be pushed to audio_buffer
        session.audio_buffer.push.assert_called_once_with(chunk)
        
        # PerfectListenerSystem should NOT be called (manual mode)
        session.perfect_listener.process_audio_chunk.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_transcribe_segment_sends_transcript_update(self):
        """
        Requirement 9.5, 9.6: transcribe_segment SHALL send TRANSCRIPT_UPDATE
        messages correctly during manual mode.
        """
        # Arrange
        session = Mock()
        session.session_id = "test-session"
        
        websocket = AsyncMock()
        audio_buffer = Mock()
        gemini_send_lock = asyncio.Lock()
        
        listener_agent = ListenerAgent(
            session=session,
            audio_buffer=audio_buffer,
            gemini_send_lock=gemini_send_lock,
            websocket=websocket,
            on_context_ready=None
        )
        listener_agent._running = True
        listener_agent._batch_interval = 0.0
        
        # Mock the transcription method
        listener_agent._fast_transcribe = Mock(return_value="Hello, this is a test")
        
        # Act
        audio = b'\x00' * 32000  # 1 second of audio
        start_time = 1000.0
        end_time = 1001.0
        
        await listener_agent.transcribe_segment(
            speaker="user",
            audio=audio,
            start_time=start_time,
            end_time=end_time
        )
        if listener_agent._background_tasks:
            await asyncio.gather(*list(listener_agent._background_tasks), return_exceptions=True)
        
        # Assert
        # Verify TRANSCRIPT_UPDATE was sent
        websocket.send_json.assert_called_once()
        call_args = websocket.send_json.call_args[0][0]
        
        assert call_args["type"] == "TRANSCRIPT_UPDATE"
        assert call_args["payload"]["speaker"] == "user"
        assert call_args["payload"]["text"] == "Hello, this is a test"
        assert "id" in call_args["payload"]
        assert "timestamp" in call_args["payload"]
        
        # Verify accumulated_transcript was updated
        assert "User" in listener_agent.accumulated_transcript
        assert "Hello, this is a test" in listener_agent.accumulated_transcript
    
    @pytest.mark.asyncio
    async def test_automatic_mode_resumes_after_manual_override_expires(self):
        """
        Verify that automatic processing resumes when manual_override_until
        expires (not infinity).
        """
        # Arrange
        import time
        session = Mock()
        session.session_id = "test-session"
        session.manual_override_until = time.time() - 1  # Expired
        session.user_addressing_ai = False
        
        websocket = AsyncMock()
        listener_agent = Mock()
        
        perfect_listener = PerfectListenerSystem(
            session=session,
            websocket=websocket,
            listener_agent=listener_agent
        )
        perfect_listener.overlap_detection_enabled = True
        
        # Mock the internal methods
        perfect_listener._detect_overlap = AsyncMock(return_value=(False, []))
        perfect_listener._segment_turns = AsyncMock(return_value=[])
        
        # Act - send enough audio to trigger overlap detection (1 second = 32000 bytes)
        chunk = b'\x00' * 32000  # 1 second of audio
        await perfect_listener.process_audio_chunk(chunk)
        
        # Assert
        # Automatic processing resumes when manual override expires.
        perfect_listener._detect_overlap.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_manual_mode_mutual_exclusion(self):
        """
        Requirement 9.7: Audio SHALL be processed by exactly one mode
        (automatic or manual), never both.
        """
        # Arrange
        from app.services.negotiation_engine import NegotiationEngine
        
        session = Mock()
        session.session_id = "test-session"
        session.live_session = True
        session.user_addressing_ai = False
        session.current_speaker = "user"
        session.audio_buffer = Mock()
        session.audio_buffer.push = Mock()
        session.current_segment_audio = b""
        session.manual_override_until = float('inf')  # Manual mode
        
        # Create mock PerfectListenerSystem
        session.perfect_listener = Mock()
        session.perfect_listener.process_audio_chunk = AsyncMock()
        
        # Act
        chunk = b'\x00' * 3200
        await NegotiationEngine.handle_audio_chunk(session, chunk)
        
        # Assert
        # Audio accumulated for manual mode
        assert len(session.current_segment_audio) == 3200
        
        # PerfectListenerSystem NOT called (mutual exclusion)
        session.perfect_listener.process_audio_chunk.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
