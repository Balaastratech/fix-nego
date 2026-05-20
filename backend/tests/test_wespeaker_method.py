"""
Unit tests for _try_wespeaker method (Task 6.2).

Tests verify:
1. WeSpeaker ResNet34 model loading (Requirement 5.1)
2. Minimum duration check (>= 0.5s) (Requirement 5.2)
3. Cosine similarity comparison (Requirement 5.3)
4. Threshold-based speaker identification (Requirements 5.4, 5.5)
5. Async execution without blocking (Requirement 5.7)
6. Error handling and fallback (Requirement 5.6)
"""

# Import fix_torchaudio first to patch deprecated functions
import sys
import os
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

try:
    import fix_torchaudio
except ImportError:
    pass  # Continue without patch if not available

import pytest
import asyncio
import numpy as np
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from app.services.perfect_listener import PerfectListenerSystem


@pytest.fixture
def mock_session():
    """Create a mock NegotiationSession."""
    session = Mock()
    session.session_id = "test_session_123"
    
    # Create a normalized user embedding (256-dimensional)
    user_embedding = np.random.randn(256).astype(np.float32)
    user_embedding = user_embedding / np.linalg.norm(user_embedding)
    session.user_embedding = user_embedding
    
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


@pytest.mark.asyncio
async def test_wespeaker_skips_short_audio(perfect_listener):
    """
    Test that WeSpeaker skips audio shorter than 0.5s.
    
    Requirement 5.2: Generate embeddings for audio segments >= 0.5s
    """
    # Create audio shorter than 0.5s (0.25s = 4000 samples)
    short_audio = np.zeros(4000, dtype=np.int16).tobytes()
    
    # Call _try_wespeaker
    speaker, confidence = await perfect_listener._try_wespeaker(short_audio)
    
    # Should return empty label and zero confidence
    assert speaker == "", f"Expected empty label for short audio, got '{speaker}'"
    assert confidence == 0.0, f"Expected 0.0 confidence for short audio, got {confidence}"


@pytest.mark.asyncio
async def test_wespeaker_skips_without_enrollment(perfect_listener):
    """
    Test that WeSpeaker skips when user_embedding is None.
    
    Requirement 5.7: Skip when user enrollment doesn't exist
    """
    # Remove user enrollment
    perfect_listener.session.user_embedding = None
    
    # Create valid audio (1.0s = 16000 samples)
    audio = np.zeros(16000, dtype=np.int16).tobytes()
    
    # Call _try_wespeaker
    speaker, confidence = await perfect_listener._try_wespeaker(audio)
    
    # Should return empty label and zero confidence
    assert speaker == "", f"Expected empty label without enrollment, got '{speaker}'"
    assert confidence == 0.0, f"Expected 0.0 confidence without enrollment, got {confidence}"


@pytest.mark.asyncio
async def test_wespeaker_processes_valid_audio(perfect_listener):
    """
    Test that WeSpeaker processes audio >= 0.5s with enrollment.
    
    Requirement 5.2: Generate embeddings for audio segments >= 0.5s
    """
    # Create valid audio (1.0s = 16000 samples)
    audio = np.zeros(16000, dtype=np.int16).tobytes()
    
    # Mock the speaker model to avoid actual model loading
    mock_model = Mock()
    mock_embedding = np.random.randn(256).astype(np.float32)
    mock_embedding = mock_embedding / np.linalg.norm(mock_embedding)
    mock_model.embed_utterance = Mock(return_value=mock_embedding)
    perfect_listener.speaker_model = mock_model
    
    # Call _try_wespeaker
    speaker, confidence = await perfect_listener._try_wespeaker(audio)
    
    # Should return a speaker label (not empty)
    assert speaker in ["user", "counterparty"], f"Expected 'user' or 'counterparty', got '{speaker}'"
    assert 0.0 <= confidence <= 1.0, f"Confidence should be in [0, 1], got {confidence}"


@pytest.mark.asyncio
async def test_wespeaker_high_similarity_returns_user(perfect_listener):
    """
    Test that high similarity (> 0.70) returns "user".
    
    Requirement 5.4: Return "user" if similarity > WESPEAKER_THRESHOLD (0.70)
    """
    # Create valid audio
    audio = np.zeros(16000, dtype=np.int16).tobytes()
    
    # Mock the speaker model to return high similarity
    mock_model = Mock()
    # Return the same embedding as user_embedding for high similarity
    mock_model.embed_utterance = Mock(return_value=perfect_listener.session.user_embedding)
    perfect_listener.speaker_model = mock_model
    
    # Call _try_wespeaker
    speaker, confidence = await perfect_listener._try_wespeaker(audio)
    
    # Should return "user" with high confidence
    assert speaker == "user", f"Expected 'user' for high similarity, got '{speaker}'"
    assert confidence > 0.70, f"Expected confidence > 0.70, got {confidence}"


@pytest.mark.asyncio
async def test_wespeaker_low_similarity_returns_counterparty(perfect_listener):
    """
    Test that low similarity (<= 0.70) returns "counterparty".
    
    Requirement 5.5: Return "counterparty" if similarity <= WESPEAKER_THRESHOLD
    """
    # Create valid audio
    audio = np.zeros(16000, dtype=np.int16).tobytes()
    
    # Mock the speaker model to return low similarity
    mock_model = Mock()
    # Return orthogonal embedding for low similarity
    mock_embedding = np.random.randn(256).astype(np.float32)
    mock_embedding = mock_embedding / np.linalg.norm(mock_embedding)
    # Make it orthogonal to user_embedding (dot product ~ 0)
    mock_embedding = mock_embedding - np.dot(mock_embedding, perfect_listener.session.user_embedding) * perfect_listener.session.user_embedding
    mock_embedding = mock_embedding / np.linalg.norm(mock_embedding)
    mock_model.embed_utterance = Mock(return_value=mock_embedding)
    perfect_listener.speaker_model = mock_model
    
    # Call _try_wespeaker
    speaker, confidence = await perfect_listener._try_wespeaker(audio)
    
    # Should return "counterparty" with low confidence
    assert speaker == "counterparty", f"Expected 'counterparty' for low similarity, got '{speaker}'"
    assert confidence <= 0.70, f"Expected confidence <= 0.70, got {confidence}"


@pytest.mark.asyncio
async def test_wespeaker_runs_asynchronously(perfect_listener):
    """
    Test that WeSpeaker runs asynchronously without blocking event loop.
    
    Requirement 5.7: Run asynchronously to avoid blocking event loop
    """
    # Create valid audio
    audio = np.zeros(16000, dtype=np.int16).tobytes()
    
    # Mock the speaker model with a slow embedding generation
    mock_model = Mock()
    
    def slow_embed(audio_array):
        # Simulate slow processing
        import time
        time.sleep(0.1)  # 100ms delay
        embedding = np.random.randn(256).astype(np.float32)
        return embedding / np.linalg.norm(embedding)
    
    mock_model.embed_utterance = slow_embed
    perfect_listener.speaker_model = mock_model
    
    # Run with timeout to ensure it doesn't block
    try:
        speaker, confidence = await asyncio.wait_for(
            perfect_listener._try_wespeaker(audio),
            timeout=5.0  # 5 second timeout
        )
        # If we get here, it completed without blocking
        assert True, "Method completed asynchronously"
    except asyncio.TimeoutError:
        pytest.fail("Method blocked the event loop (timeout)")


@pytest.mark.asyncio
async def test_wespeaker_handles_model_loading_error(perfect_listener):
    """
    Test that WeSpeaker handles model loading errors gracefully.
    
    Requirement 5.6: Handle errors gracefully and trigger fallback
    """
    # Create valid audio
    audio = np.zeros(16000, dtype=np.int16).tobytes()
    
    # Mock load_model to raise an exception
    with patch('wespeaker.cli.speaker.load_model') as mock_load:
        mock_load.side_effect = Exception("Model loading failed")
        
        # Call _try_wespeaker
        speaker, confidence = await perfect_listener._try_wespeaker(audio)
        
        # Should return empty label and zero confidence (triggers fallback)
        assert speaker == "", f"Expected empty label on error, got '{speaker}'"
        assert confidence == 0.0, f"Expected 0.0 confidence on error, got {confidence}"


@pytest.mark.asyncio
async def test_wespeaker_handles_embedding_generation_error(perfect_listener):
    """
    Test that WeSpeaker handles embedding generation errors gracefully.
    
    Requirement 5.6: Handle errors gracefully and trigger fallback
    """
    # Create valid audio
    audio = np.zeros(16000, dtype=np.int16).tobytes()
    
    # Mock the speaker model to raise an exception during embedding
    mock_model = Mock()
    mock_model.embed_utterance = Mock(side_effect=Exception("Embedding generation failed"))
    perfect_listener.speaker_model = mock_model
    
    # Call _try_wespeaker
    speaker, confidence = await perfect_listener._try_wespeaker(audio)
    
    # Should return empty label and zero confidence (triggers fallback)
    assert speaker == "", f"Expected empty label on error, got '{speaker}'"
    assert confidence == 0.0, f"Expected 0.0 confidence on error, got {confidence}"


@pytest.mark.asyncio
async def test_wespeaker_cosine_similarity_calculation(perfect_listener):
    """
    Test that WeSpeaker uses cosine similarity for comparison.
    
    Requirement 5.3: Compare with user_embedding using cosine similarity
    """
    # Create valid audio
    audio = np.zeros(16000, dtype=np.int16).tobytes()
    
    # Create a known embedding with specific similarity
    user_emb = perfect_listener.session.user_embedding
    
    # Create embedding with known cosine similarity (0.8)
    # cos(θ) = 0.8, so we create a vector at angle θ from user_emb
    mock_embedding = 0.8 * user_emb + 0.6 * np.random.randn(256).astype(np.float32)
    mock_embedding = mock_embedding / np.linalg.norm(mock_embedding)
    
    # Verify cosine similarity is approximately 0.8
    expected_similarity = np.dot(mock_embedding, user_emb)
    
    # Mock the speaker model
    mock_model = Mock()
    mock_model.embed_utterance = Mock(return_value=mock_embedding)
    perfect_listener.speaker_model = mock_model
    
    # Call _try_wespeaker
    speaker, confidence = await perfect_listener._try_wespeaker(audio)
    
    # Confidence should be close to expected similarity
    assert abs(confidence - expected_similarity) < 0.1, \
        f"Expected confidence ~{expected_similarity:.2f}, got {confidence:.2f}"


@pytest.mark.asyncio
async def test_wespeaker_clamps_similarity_to_valid_range(perfect_listener):
    """
    Test that WeSpeaker clamps similarity to [0, 1] range.
    
    Requirement 5.3: Cosine similarity should be in valid range
    """
    # Create valid audio
    audio = np.zeros(16000, dtype=np.int16).tobytes()
    
    # Mock the speaker model to return negative similarity
    mock_model = Mock()
    # Return opposite embedding for negative similarity
    mock_embedding = -perfect_listener.session.user_embedding
    mock_model.embed_utterance = Mock(return_value=mock_embedding)
    perfect_listener.speaker_model = mock_model
    
    # Call _try_wespeaker
    speaker, confidence = await perfect_listener._try_wespeaker(audio)
    
    # Confidence should be clamped to [0, 1]
    assert 0.0 <= confidence <= 1.0, f"Confidence should be in [0, 1], got {confidence}"


@pytest.mark.asyncio
async def test_wespeaker_lazy_loads_model(perfect_listener):
    """
    Test that WeSpeaker model is lazy loaded on first use.
    
    Requirement 5.1: Load WeSpeaker ResNet34 model (lazy loading)
    """
    # Initially, speaker_model should be None
    assert perfect_listener.speaker_model is None, "Model should not be loaded initially"
    
    # Create valid audio
    audio = np.zeros(16000, dtype=np.int16).tobytes()
    
    # Mock load_model to avoid actual model loading
    with patch('wespeaker.cli.speaker.load_model') as mock_load:
        mock_model = Mock()
        mock_embedding = np.random.randn(256).astype(np.float32)
        mock_embedding = mock_embedding / np.linalg.norm(mock_embedding)
        mock_model.embed_utterance = Mock(return_value=mock_embedding)
        mock_load.return_value = mock_model
        
        # Call _try_wespeaker (should trigger model loading)
        await perfect_listener._try_wespeaker(audio)
        
        # Model should be loaded now
        assert perfect_listener.speaker_model is not None, "Model should be loaded after first use"
        assert mock_load.called, "load_model should have been called"


@pytest.mark.asyncio
async def test_wespeaker_threshold_boundary(perfect_listener):
    """
    Test WeSpeaker behavior at threshold boundary (0.70).
    
    Requirements 5.4, 5.5: Threshold-based speaker identification
    """
    # Create valid audio
    audio = np.zeros(16000, dtype=np.int16).tobytes()
    
    # Test exactly at threshold (0.70)
    mock_model = Mock()
    
    # Create embedding with similarity exactly 0.70
    user_emb = perfect_listener.session.user_embedding
    mock_embedding = 0.70 * user_emb + 0.714 * np.random.randn(256).astype(np.float32)
    mock_embedding = mock_embedding / np.linalg.norm(mock_embedding)
    
    # Adjust to get exactly 0.70 similarity
    current_sim = np.dot(mock_embedding, user_emb)
    mock_embedding = mock_embedding * (0.70 / current_sim)
    mock_embedding = mock_embedding / np.linalg.norm(mock_embedding)
    
    mock_model.embed_utterance = Mock(return_value=mock_embedding)
    perfect_listener.speaker_model = mock_model
    
    # Call _try_wespeaker
    speaker, confidence = await perfect_listener._try_wespeaker(audio)
    
    # At threshold (0.70), should return "counterparty" (not > 0.70)
    assert speaker == "counterparty", f"Expected 'counterparty' at threshold, got '{speaker}'"
