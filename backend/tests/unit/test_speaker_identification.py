"""
Unit tests for speaker identification (Stage 4 of the pipeline).

Tests the _identify_speaker method and its fallback chain:
1. WeSpeaker (primary)
2. Pyannote embedding (fallback)
3. Clustering (positional fallback)
4. Unknown label (last resort)
"""

import pytest
import numpy as np
from unittest.mock import Mock, AsyncMock, patch
from app.services.perfect_listener import PerfectListenerSystem


@pytest.fixture
def mock_session():
    """Create a mock negotiation session."""
    session = Mock()
    session.session_id = "test_session_123"
    session.user_embedding = None
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


class TestIdentifySpeaker:
    """Tests for _identify_speaker method."""
    
    @pytest.mark.asyncio
    async def test_identify_speaker_wespeaker_success(self, perfect_listener):
        """Test successful identification using WeSpeaker (Level 1)."""
        # Create test audio (1 second of silence)
        audio = np.zeros(16000, dtype=np.int16).tobytes()
        
        # Mock WeSpeaker to return high confidence
        with patch.object(perfect_listener, '_try_wespeaker', new_callable=AsyncMock) as mock_wespeaker:
            mock_wespeaker.return_value = ("user", 0.85)
            
            speaker, confidence = await perfect_listener._identify_speaker(audio)
            
            assert speaker == "user"
            assert confidence == 0.85
            mock_wespeaker.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_identify_speaker_pyannote_fallback(self, perfect_listener):
        """Test fallback to Pyannote embedding (Level 2) when WeSpeaker confidence is low."""
        audio = np.zeros(16000, dtype=np.int16).tobytes()
        
        # Mock WeSpeaker to return low confidence
        # Mock Pyannote to return high confidence
        with patch.object(perfect_listener, '_try_wespeaker', new_callable=AsyncMock) as mock_wespeaker, \
             patch.object(perfect_listener, '_try_pyannote_embedding', new_callable=AsyncMock) as mock_pyannote:
            
            mock_wespeaker.return_value = ("", 0.50)  # Below threshold
            mock_pyannote.return_value = ("counterparty", 0.75)
            
            speaker, confidence = await perfect_listener._identify_speaker(audio)
            
            assert speaker == "counterparty"
            assert confidence == 0.75
            mock_wespeaker.assert_called_once()
            mock_pyannote.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_identify_speaker_clustering_fallback(self, perfect_listener):
        """Test fallback to clustering (Level 3) when both WeSpeaker and Pyannote fail."""
        audio = np.zeros(16000, dtype=np.int16).tobytes()
        
        # Mock WeSpeaker and Pyannote to return low confidence
        # Mock clustering to return label
        with patch.object(perfect_listener, '_try_wespeaker', new_callable=AsyncMock) as mock_wespeaker, \
             patch.object(perfect_listener, '_try_pyannote_embedding', new_callable=AsyncMock) as mock_pyannote, \
             patch.object(perfect_listener, '_try_clustering', new_callable=AsyncMock) as mock_clustering:
            
            mock_wespeaker.return_value = ("", 0.50)
            mock_pyannote.return_value = ("", 0.60)
            mock_clustering.return_value = "user"
            
            speaker, confidence = await perfect_listener._identify_speaker(audio)
            
            assert speaker == "user"
            assert confidence == 0.60  # Fixed confidence for clustering
            mock_wespeaker.assert_called_once()
            mock_pyannote.assert_called_once()
            mock_clustering.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_identify_speaker_unknown_fallback(self, perfect_listener):
        """Test fallback to 'unknown' label (Level 4) when all methods fail."""
        audio = np.zeros(16000, dtype=np.int16).tobytes()
        
        # Mock all methods to fail
        with patch.object(perfect_listener, '_try_wespeaker', new_callable=AsyncMock) as mock_wespeaker, \
             patch.object(perfect_listener, '_try_pyannote_embedding', new_callable=AsyncMock) as mock_pyannote, \
             patch.object(perfect_listener, '_try_clustering', new_callable=AsyncMock) as mock_clustering:
            
            mock_wespeaker.return_value = ("", 0.50)
            mock_pyannote.return_value = ("", 0.60)
            mock_clustering.return_value = "unknown"
            
            speaker, confidence = await perfect_listener._identify_speaker(audio)
            
            assert speaker == "unknown"
            assert confidence == 0.0
            mock_wespeaker.assert_called_once()
            mock_pyannote.assert_called_once()
            mock_clustering.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_identify_speaker_clustering_disabled(self, perfect_listener):
        """Test that clustering is skipped when disabled."""
        audio = np.zeros(16000, dtype=np.int16).tobytes()
        perfect_listener.clustering_enabled = False
        
        # Mock WeSpeaker and Pyannote to fail
        with patch.object(perfect_listener, '_try_wespeaker', new_callable=AsyncMock) as mock_wespeaker, \
             patch.object(perfect_listener, '_try_pyannote_embedding', new_callable=AsyncMock) as mock_pyannote, \
             patch.object(perfect_listener, '_try_clustering', new_callable=AsyncMock) as mock_clustering:
            
            mock_wespeaker.return_value = ("", 0.50)
            mock_pyannote.return_value = ("", 0.60)
            
            speaker, confidence = await perfect_listener._identify_speaker(audio)
            
            assert speaker == "unknown"
            assert confidence == 0.0
            mock_wespeaker.assert_called_once()
            mock_pyannote.assert_called_once()
            mock_clustering.assert_not_called()  # Should be skipped
    
    @pytest.mark.asyncio
    async def test_identify_speaker_exception_handling(self, perfect_listener):
        """Test that exceptions are handled gracefully and return 'unknown'."""
        audio = np.zeros(16000, dtype=np.int16).tobytes()
        
        # Mock WeSpeaker to raise exception
        with patch.object(perfect_listener, '_try_wespeaker', new_callable=AsyncMock) as mock_wespeaker:
            mock_wespeaker.side_effect = Exception("Model inference failed")
            
            speaker, confidence = await perfect_listener._identify_speaker(audio)
            
            assert speaker == "unknown"
            assert confidence == 0.0
    
    @pytest.mark.asyncio
    async def test_identify_speaker_normalizes_audio(self, perfect_listener):
        """Test that audio is normalized before identification."""
        # Create test audio with high volume
        audio = (np.ones(16000, dtype=np.int16) * 30000).tobytes()
        
        with patch.object(perfect_listener, '_normalize_audio') as mock_normalize, \
             patch.object(perfect_listener, '_try_wespeaker', new_callable=AsyncMock) as mock_wespeaker:
            
            mock_normalize.return_value = audio
            mock_wespeaker.return_value = ("user", 0.85)
            
            await perfect_listener._identify_speaker(audio)
            
            # Verify normalization was called
            mock_normalize.assert_called_once_with(audio)


class TestNormalizeAudio:
    """Tests for _normalize_audio method."""
    
    def test_normalize_audio_basic(self, perfect_listener):
        """Test basic audio normalization."""
        # Create audio with max value of 10000 (should be normalized to 32767 * 0.95)
        audio_array = np.array([10000, -10000, 5000, -5000], dtype=np.int16)
        audio = audio_array.tobytes()
        
        normalized = perfect_listener._normalize_audio(audio)
        normalized_array = np.frombuffer(normalized, dtype=np.int16)
        
        # Check that max absolute value is approximately 32767 * 0.95 = 31128
        max_val = np.abs(normalized_array).max()
        assert 30000 <= max_val <= 32000  # Allow some tolerance
    
    def test_normalize_audio_silence(self, perfect_listener):
        """Test normalization of silence (all zeros)."""
        audio = np.zeros(16000, dtype=np.int16).tobytes()
        
        normalized = perfect_listener._normalize_audio(audio)
        normalized_array = np.frombuffer(normalized, dtype=np.int16)
        
        # Silence should remain silence
        assert np.all(normalized_array == 0)
    
    def test_normalize_audio_already_normalized(self, perfect_listener):
        """Test normalization of already normalized audio."""
        # Create audio at 95% of max range
        audio_array = np.array([31128, -31128, 15564, -15564], dtype=np.int16)
        audio = audio_array.tobytes()
        
        normalized = perfect_listener._normalize_audio(audio)
        normalized_array = np.frombuffer(normalized, dtype=np.int16)
        
        # Should remain approximately the same
        max_val = np.abs(normalized_array).max()
        assert 30000 <= max_val <= 32000
    
    def test_normalize_audio_preserves_duration(self, perfect_listener):
        """Test that normalization preserves audio duration."""
        # Create 1 second of audio (16000 samples)
        audio = np.random.randint(-10000, 10000, 16000, dtype=np.int16).tobytes()
        
        normalized = perfect_listener._normalize_audio(audio)
        
        # Duration should be preserved
        assert len(normalized) == len(audio)
    
    def test_normalize_audio_error_handling(self, perfect_listener):
        """Test that normalization errors are handled gracefully."""
        # Create invalid audio (odd number of bytes)
        audio = b"invalid"
        
        normalized = perfect_listener._normalize_audio(audio)
        
        # Should return original audio on error
        assert normalized == audio


class TestFallbackMethods:
    """Tests for fallback method stubs."""
    
    @pytest.mark.asyncio
    async def test_try_wespeaker_stub(self, perfect_listener):
        """Test that _try_wespeaker stub returns empty label and zero confidence."""
        audio = np.zeros(16000, dtype=np.int16).tobytes()
        
        speaker, confidence = await perfect_listener._try_wespeaker(audio)
        
        assert speaker == ""
        assert confidence == 0.0
    
    @pytest.mark.asyncio
    async def test_try_pyannote_embedding_stub(self, perfect_listener):
        """Test that _try_pyannote_embedding stub returns empty label and zero confidence."""
        audio = np.zeros(16000, dtype=np.int16).tobytes()
        
        speaker, confidence = await perfect_listener._try_pyannote_embedding(audio)
        
        assert speaker == ""
        assert confidence == 0.0
    
    @pytest.mark.asyncio
    async def test_try_clustering_stub(self, perfect_listener):
        """Test that _try_clustering stub returns 'unknown' label."""
        audio = np.zeros(16000, dtype=np.int16).tobytes()
        
        speaker = await perfect_listener._try_clustering(audio)
        
        assert speaker == "unknown"
