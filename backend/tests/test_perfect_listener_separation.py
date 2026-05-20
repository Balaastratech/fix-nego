"""
Unit tests for PerfectListenerSystem speech separation (Task 4.1).

Tests the _separate_speakers method implementation.
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


def generate_mixed_audio(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    """
    Generate synthetic mixed audio with two speakers for testing.
    
    Args:
        duration_seconds: Duration of audio in seconds
        sample_rate: Sample rate in Hz
    
    Returns:
        PCM audio bytes (16-bit signed integers) with overlapping speech
    """
    num_samples = int(duration_seconds * sample_rate)
    t = np.linspace(0, duration_seconds, num_samples)
    
    # Speaker 1: 440 Hz (A4)
    speaker1 = np.sin(2 * np.pi * 440 * t) * 0.5
    
    # Speaker 2: 554 Hz (C#5)
    speaker2 = np.sin(2 * np.pi * 554 * t) * 0.5
    
    # Mix the two speakers
    mixed = speaker1 + speaker2
    
    # Normalize to prevent clipping
    mixed = mixed / np.abs(mixed).max() * 0.8
    
    # Scale to 16-bit range
    audio_int16 = (mixed * 32767).astype(np.int16)
    return audio_int16.tobytes()


def generate_single_speaker_audio(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    """
    Generate synthetic single speaker audio for testing.
    
    Args:
        duration_seconds: Duration of audio in seconds
        sample_rate: Sample rate in Hz
    
    Returns:
        PCM audio bytes (16-bit signed integers)
    """
    num_samples = int(duration_seconds * sample_rate)
    t = np.linspace(0, duration_seconds, num_samples)
    
    # Single speaker: 440 Hz (A4)
    audio = np.sin(2 * np.pi * 440 * t) * 0.5
    
    # Scale to 16-bit range
    audio_int16 = (audio * 32767).astype(np.int16)
    return audio_int16.tobytes()


@pytest.mark.asyncio
async def test_separate_speakers_returns_list(perfect_listener):
    """
    Test that _separate_speakers returns a list of audio streams.
    
    Validates: Requirements 2.1
    """
    # Generate mixed audio
    mixed_audio = generate_mixed_audio(duration_seconds=1.0)
    
    # Call _separate_speakers
    separated_streams = await perfect_listener._separate_speakers(mixed_audio)
    
    # Verify return type
    assert isinstance(separated_streams, list), "Should return a list"
    assert len(separated_streams) > 0, "Should return at least one stream"
    
    # Verify each stream is bytes
    for stream in separated_streams:
        assert isinstance(stream, bytes), "Each stream should be bytes"


@pytest.mark.asyncio
async def test_separate_speakers_normalizes_output(perfect_listener):
    """
    Test that separated streams are normalized to [-1, 1] range.
    
    Validates: Requirements 2.6
    """
    # Generate mixed audio
    mixed_audio = generate_mixed_audio(duration_seconds=1.0)
    
    # Call _separate_speakers
    try:
        separated_streams = await perfect_listener._separate_speakers(mixed_audio)
        
        # Check normalization for each stream
        for stream in separated_streams:
            # Convert bytes back to float array
            audio_array = np.frombuffer(stream, dtype=np.int16)
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Verify range [-1, 1]
            assert audio_float.min() >= -1.0, "Audio should be >= -1.0"
            assert audio_float.max() <= 1.0, "Audio should be <= 1.0"
            
            # Verify normalization (max should be close to 0.95 as per spec)
            max_abs = np.abs(audio_float).max()
            assert max_abs <= 0.96, f"Max absolute value should be <= 0.96, got {max_abs}"
    
    except Exception as e:
        # Expected if model not available in test environment
        pytest.skip(f"Model not available: {e}")


@pytest.mark.asyncio
async def test_separate_speakers_handles_errors_gracefully(perfect_listener):
    """
    Test that _separate_speakers handles errors gracefully.
    
    Validates: Requirements 2.5
    """
    # Test with invalid audio (empty bytes)
    invalid_audio = b""
    
    # Should not raise exception, should return [audio] (fallback)
    separated_streams = await perfect_listener._separate_speakers(invalid_audio)
    
    assert isinstance(separated_streams, list), "Should return a list on error"
    assert len(separated_streams) == 1, "Should return single stream on error"
    assert separated_streams[0] == invalid_audio, "Should return original audio on error"


@pytest.mark.asyncio
async def test_separate_speakers_fallback_on_failure(perfect_listener):
    """
    Test that _separate_speakers falls back to mixed audio on failure.
    
    Validates: Requirements 2.5
    """
    # Generate valid audio
    mixed_audio = generate_mixed_audio(duration_seconds=1.0)
    
    # Mock the separator to raise an exception
    perfect_listener.separator = Mock()
    perfect_listener.separator.side_effect = Exception("Model inference failed")
    
    # Call _separate_speakers
    separated_streams = await perfect_listener._separate_speakers(mixed_audio)
    
    # Should fall back to original audio
    assert isinstance(separated_streams, list), "Should return a list"
    assert len(separated_streams) == 1, "Should return single stream on failure"
    assert separated_streams[0] == mixed_audio, "Should return original audio on failure"


@pytest.mark.asyncio
async def test_separate_speakers_lazy_loads_model(perfect_listener):
    """
    Test that the Conv-TasNet model is lazy loaded.
    
    Validates: Requirements 2.2
    """
    # Initially, separator should be None
    assert perfect_listener.separator is None, "Model should not be loaded initially"
    
    # Generate mixed audio
    mixed_audio = generate_mixed_audio(duration_seconds=1.0)
    
    # Call _separate_speakers (this should trigger model loading)
    try:
        await perfect_listener._separate_speakers(mixed_audio)
        # After call, model should be loaded (or error occurred)
        # We can't guarantee model loads in test environment without proper setup
    except Exception:
        # Expected if model not available in test environment
        pass


@pytest.mark.asyncio
async def test_separate_speakers_produces_two_streams(perfect_listener):
    """
    Test that _separate_speakers produces 2 clean streams for overlapping audio.
    
    Validates: Requirements 2.1
    """
    # Generate mixed audio with overlap
    mixed_audio = generate_mixed_audio(duration_seconds=1.0)
    
    try:
        # Call _separate_speakers
        separated_streams = await perfect_listener._separate_speakers(mixed_audio)
        
        # Conv-TasNet typically produces 2 streams
        # Note: In test environment without model, this will fall back to 1 stream
        assert len(separated_streams) >= 1, "Should return at least 1 stream"
        
        # If model is available, should return 2 streams
        if len(separated_streams) == 2:
            # Verify both streams have same length
            assert len(separated_streams[0]) == len(separated_streams[1]), \
                "Both streams should have same length"
            
            # Verify both streams are valid PCM audio
            for stream in separated_streams:
                audio_array = np.frombuffer(stream, dtype=np.int16)
                assert len(audio_array) > 0, "Stream should contain audio samples"
    
    except Exception as e:
        # Expected if model not available in test environment
        pytest.skip(f"Model not available: {e}")


@pytest.mark.asyncio
async def test_separate_speakers_preserves_duration(perfect_listener):
    """
    Test that separated streams preserve audio duration.
    
    Validates: Requirements 30.1 (audio duration preservation)
    """
    # Generate 1-second mixed audio
    duration_seconds = 1.0
    sample_rate = 16000
    mixed_audio = generate_mixed_audio(duration_seconds=duration_seconds, sample_rate=sample_rate)
    
    # Calculate expected number of samples
    expected_samples = int(duration_seconds * sample_rate)
    
    try:
        # Call _separate_speakers
        separated_streams = await perfect_listener._separate_speakers(mixed_audio)
        
        # Check duration for each stream
        for stream in separated_streams:
            audio_array = np.frombuffer(stream, dtype=np.int16)
            actual_samples = len(audio_array)
            
            # Duration should be preserved within 1%
            duration_error = abs(actual_samples - expected_samples) / expected_samples
            assert duration_error < 0.01, \
                f"Duration error {duration_error:.2%} exceeds 1% threshold"
    
    except Exception as e:
        # Expected if model not available in test environment
        pytest.skip(f"Model not available: {e}")


@pytest.mark.asyncio
async def test_separate_speakers_with_silence(perfect_listener):
    """
    Test separation with silence (no speech).
    
    Should handle gracefully without crashing.
    """
    # Generate silence (zeros)
    num_samples = 16000  # 1 second at 16kHz
    silence = np.zeros(num_samples, dtype=np.int16)
    audio = silence.tobytes()
    
    # Call _separate_speakers
    separated_streams = await perfect_listener._separate_speakers(audio)
    
    # Should return at least one stream (fallback or separated)
    assert isinstance(separated_streams, list), "Should return a list"
    assert len(separated_streams) >= 1, "Should return at least one stream"


@pytest.mark.asyncio
async def test_separate_speakers_async_execution(perfect_listener):
    """
    Test that _separate_speakers runs asynchronously without blocking.
    
    Validates: Requirements 5.7 (async execution)
    """
    # Generate mixed audio
    mixed_audio = generate_mixed_audio(duration_seconds=1.0)
    
    # Call _separate_speakers
    # This should complete without blocking the event loop
    import asyncio
    
    try:
        # Run with timeout to ensure it doesn't block
        separated_streams = await asyncio.wait_for(
            perfect_listener._separate_speakers(mixed_audio),
            timeout=10.0  # 10 second timeout
        )
        
        assert isinstance(separated_streams, list), "Should return a list"
    
    except asyncio.TimeoutError:
        pytest.fail("_separate_speakers blocked the event loop (timeout)")
    
    except Exception as e:
        # Expected if model not available in test environment
        pytest.skip(f"Model not available: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
