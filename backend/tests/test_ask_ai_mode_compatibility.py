"""
Test Ask AI mode compatibility with PerfectListenerSystem.

Verifies that when user_addressing_ai is true:
- PerfectListenerSystem skips automatic processing
- Audio accumulates in question_capture_bytes
- Audio is NOT pushed to audio_buffer
- Audio is NOT included in accumulated_transcript

Requirements: 10.1, 10.2, 10.3, 10.4
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.services.perfect_listener import PerfectListenerSystem
from app.models.negotiation import NegotiationSession


@pytest.mark.asyncio
async def test_ask_ai_mode_skips_automatic_processing():
    """
    Test that PerfectListenerSystem skips processing when user_addressing_ai is true.
    
    Requirement 10.1: When user_addressing_ai is true, PerfectListenerSystem SHALL skip audio processing
    """
    # Create mock session with Ask AI mode active
    session = Mock(spec=NegotiationSession)
    session.session_id = "test-session"
    session.user_addressing_ai = True
    session.manual_override_until = 0
    
    # Create mock websocket and listener_agent
    websocket = AsyncMock()
    listener_agent = Mock()
    listener_agent.accumulated_transcript = ""
    
    # Create PerfectListenerSystem
    perfect_listener = PerfectListenerSystem(
        session=session,
        websocket=websocket,
        listener_agent=listener_agent
    )
    
    # Create test audio chunk (100ms at 16kHz, 16-bit mono = 3200 bytes)
    test_chunk = b'\x00' * 3200
    
    # Process audio chunk
    await perfect_listener.process_audio_chunk(test_chunk)
    
    # Verify that no processing occurred
    # frame_buffer should be empty (not accumulated)
    assert perfect_listener.frame_buffer == b"", "frame_buffer should be empty when Ask AI mode is active"
    
    # overlap_window should be empty (not accumulated)
    assert perfect_listener.overlap_window == b"", "overlap_window should be empty when Ask AI mode is active"
    
    # No transcripts should be sent
    websocket.send_json.assert_not_called()
    
    # accumulated_transcript should be unchanged
    assert listener_agent.accumulated_transcript == "", "accumulated_transcript should be unchanged when Ask AI mode is active"


@pytest.mark.asyncio
async def test_ask_ai_mode_audio_accumulation():
    """
    Test that audio accumulates in question_capture_bytes during Ask AI mode.
    
    This test verifies the NegotiationEngine behavior, not PerfectListenerSystem directly.
    
    Requirements: 10.2, 10.3, 10.4
    """
    from app.services.negotiation_engine import NegotiationEngine
    
    # Create mock session with Ask AI mode active
    session = Mock(spec=NegotiationSession)
    session.session_id = "test-session"
    session.live_session = True
    session.user_addressing_ai = True
    session.question_capture_bytes = b""
    session.audio_buffer = Mock()
    session.current_speaker = "user"
    
    # Create test audio chunk (100ms at 16kHz, 16-bit mono = 3200 bytes)
    test_chunk = b'\x00' * 3200
    
    # Process audio chunk through NegotiationEngine
    await NegotiationEngine.handle_audio_chunk(session, test_chunk)
    
    # Verify audio accumulated in question_capture_bytes (Requirement 10.2)
    assert session.question_capture_bytes == test_chunk, "Audio should accumulate in question_capture_bytes"
    
    # Verify audio NOT pushed to audio_buffer (Requirement 10.3)
    session.audio_buffer.push.assert_not_called()


@pytest.mark.asyncio
async def test_ask_ai_mode_resume_after_deactivation():
    """
    Test that automatic processing resumes after Ask AI mode is deactivated.
    
    Requirement 10.5: When user_addressing_ai becomes false, the system SHALL resume normal processing
    """
    # Create mock session with Ask AI mode initially active
    session = Mock(spec=NegotiationSession)
    session.session_id = "test-session"
    session.user_addressing_ai = True
    session.manual_override_until = 0
    
    # Create mock websocket and listener_agent
    websocket = AsyncMock()
    listener_agent = Mock()
    listener_agent.accumulated_transcript = ""
    
    # Create PerfectListenerSystem
    perfect_listener = PerfectListenerSystem(
        session=session,
        websocket=websocket,
        listener_agent=listener_agent
    )
    
    # Create test audio chunk (100ms at 16kHz, 16-bit mono = 3200 bytes)
    test_chunk = b'\x00' * 3200
    
    # Process audio chunk while Ask AI mode is active
    await perfect_listener.process_audio_chunk(test_chunk)
    
    # Verify no processing occurred
    assert perfect_listener.frame_buffer == b"", "frame_buffer should be empty during Ask AI mode"
    
    # Deactivate Ask AI mode
    session.user_addressing_ai = False
    
    # Process another audio chunk
    await perfect_listener.process_audio_chunk(test_chunk)
    
    # Verify processing resumed (frame_buffer should now have data)
    assert perfect_listener.frame_buffer == test_chunk, "frame_buffer should accumulate after Ask AI mode is deactivated"


@pytest.mark.asyncio
async def test_manual_and_ask_ai_mode_mutual_exclusion():
    """
    Test that both manual mode and Ask AI mode can coexist without conflicts.
    
    When both flags are set, both should skip automatic processing.
    """
    # Create mock session with both manual mode and Ask AI mode active
    session = Mock(spec=NegotiationSession)
    session.session_id = "test-session"
    session.user_addressing_ai = True
    session.manual_override_until = float('inf')  # Manual mode active
    
    # Create mock websocket and listener_agent
    websocket = AsyncMock()
    listener_agent = Mock()
    listener_agent.accumulated_transcript = ""
    
    # Create PerfectListenerSystem
    perfect_listener = PerfectListenerSystem(
        session=session,
        websocket=websocket,
        listener_agent=listener_agent
    )
    
    # Create test audio chunk (100ms at 16kHz, 16-bit mono = 3200 bytes)
    test_chunk = b'\x00' * 3200
    
    # Process audio chunk
    await perfect_listener.process_audio_chunk(test_chunk)
    
    # Verify that no processing occurred (manual mode check happens first)
    assert perfect_listener.frame_buffer == b"", "frame_buffer should be empty when both modes are active"
    assert perfect_listener.overlap_window == b"", "overlap_window should be empty when both modes are active"
    
    # No transcripts should be sent
    websocket.send_json.assert_not_called()
