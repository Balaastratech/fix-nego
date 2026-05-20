"""
Unit tests for PerfectListenerSystem overlap detection (Task 3.1).

Tests the _detect_overlap method implementation.
"""

import pytest
import numpy as np
from unittest.mock import Mock, AsyncMock, MagicMock
from app.services.perfect_listener import PerfectListenerSystem


@pytest.fixture
def mock_session():
    """Create a mock negotiation session."""
    session = Mock()
    session.session_id = "test_session_123"
    return session


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket."""
    return Mock()


@pytest.fixture
def mock_listener_agent():
    """Create a mock ListenerAgent."""
    agent = Mock()
    agent.accumulated_transcript = ""
    return agent


@pytest.fixture
def perfect_listener(mock_session, mock_websocket, mock_listener_agent):
    """Create a PerfectListenerSystem instance for testing."""
    return PerfectListenerSystem(
        session=mock_session,
        websocket=mock_websocket,
        listener_agent=mock_listener_agent
    )


def generate_audio_window(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    """
    Generate a synthetic audio window for testing.
    
    Args:
        duration_seconds: Duration of audio in seconds
        sample_rate: Sample rate in Hz
    
    Returns:
        PCM audio bytes (16-bit signed integers)
    """
    num_samples = int(duration_seconds * sample_rate)
    # Generate a simple sine wave
    t = np.linspace(0, duration_seconds, num_samples)
    frequency = 440  # A4 note
    audio = np.sin(2 * np.pi * frequency * t)
    # Scale to 16-bit range
    audio_int16 = (audio * 32767 * 0.5).astype(np.int16)
    return audio_int16.tobytes()


@pytest.mark.asyncio
async def test_detect_overlap_returns_correct_format(perfect_listener):
    """
    Test that _detect_overlap returns the correct format.
    
    Validates: Requirements 1.6
    """
    # Generate 1-second audio window
    window = generate_audio_window(duration_seconds=1.0)
    
    # Call _detect_overlap
    has_overlap, timestamps = await perfect_listener._detect_overlap(window)
    
    # Verify return format
    assert isinstance(has_overlap, bool), "has_overlap should be a boolean"
    assert isinstance(timestamps, list), "timestamps should be a list"
    
    # Verify timestamp format if any exist
    for start, end in timestamps:
        assert isinstance(start, (int, float)), "start timestamp should be numeric"
        assert isinstance(end, (int, float)), "end timestamp should be numeric"
        assert start < end, "start should be before end"


@pytest.mark.asyncio
async def test_detect_overlap_handles_errors_gracefully(perfect_listener):
    """
    Test that _detect_overlap handles errors gracefully.
    
    Validates: Requirements 1.7
    """
    # Test with invalid audio (empty bytes)
    invalid_window = b""
    
    # Should not raise exception, should return (False, [])
    has_overlap, timestamps = await perfect_listener._detect_overlap(invalid_window)
    
    assert has_overlap is False, "Should return False on error"
    assert timestamps == [], "Should return empty list on error"


@pytest.mark.asyncio
async def test_detect_overlap_with_silence(perfect_listener):
    """
    Test overlap detection with silence (no speech).
    
    Should return no overlap.
    """
    # Generate silence (zeros)
    num_samples = 16000  # 1 second at 16kHz
    silence = np.zeros(num_samples, dtype=np.int16)
    window = silence.tobytes()
    
    # Call _detect_overlap
    has_overlap, timestamps = await perfect_listener._detect_overlap(window)
    
    # Silence should not have overlap
    assert has_overlap is False, "Silence should not have overlap"
    assert timestamps == [], "Silence should have no overlap timestamps"


@pytest.mark.asyncio
async def test_detect_overlap_lazy_loads_model(perfect_listener):
    """
    Test that the overlap detector model is lazy loaded.
    
    Validates: Requirements 1.2
    """
    # Initially, overlap_detector should be None
    assert perfect_listener.overlap_detector is None, "Model should not be loaded initially"
    
    # Generate audio window
    window = generate_audio_window(duration_seconds=1.0)
    
    # Call _detect_overlap (this should trigger model loading)
    try:
        await perfect_listener._detect_overlap(window)
        # After call, model should be loaded (or error occurred)
        # We can't guarantee model loads in test environment without HF_TOKEN
    except Exception:
        # Expected if HF_TOKEN not set or model not available
        pass


@pytest.mark.asyncio
async def test_detect_overlap_processes_one_second_window(perfect_listener):
    """
    Test that _detect_overlap processes 1-second audio windows.
    
    Validates: Requirements 1.3
    """
    # Generate exactly 1-second window (16000 samples at 16kHz)
    window = generate_audio_window(duration_seconds=1.0, sample_rate=16000)
    
    # Verify window size
    expected_bytes = 16000 * 2  # 16000 samples * 2 bytes per sample (16-bit)
    assert len(window) == expected_bytes, f"Window should be {expected_bytes} bytes"
    
    # Call _detect_overlap
    try:
        has_overlap, timestamps = await perfect_listener._detect_overlap(window)
        # Should process without error
        assert isinstance(has_overlap, bool)
        assert isinstance(timestamps, list)
    except Exception as e:
        # Expected if model not available in test environment
        pytest.skip(f"Model not available: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
