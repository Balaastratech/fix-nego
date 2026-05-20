"""
Unit tests for VoiceEncoder singleton service.

Tests verify:
- Singleton pattern (only one instance exists)
- Embedding generation produces 256-dimensional vectors
- L2 normalization (embeddings have norm ~1.0)
- Audio preprocessing (bytes → numpy conversion)
"""

import pytest
import numpy as np
from hypothesis import given, settings, strategies as st
from app.services.voice_encoder import VoiceEncoder


class TestVoiceEncoderSingleton:
    """Test singleton pattern implementation."""
    
    def test_singleton_returns_same_instance(self):
        """Verify get_instance() always returns the same object."""
        instance1 = VoiceEncoder.get_instance()
        instance2 = VoiceEncoder.get_instance()
        
        # Both should be the exact same object (same memory address)
        assert instance1 is instance2
        assert id(instance1) == id(instance2)
    
    def test_multiple_instantiation_returns_same_instance(self):
        """Verify direct instantiation also returns singleton."""
        instance1 = VoiceEncoder()
        instance2 = VoiceEncoder()
        instance3 = VoiceEncoder.get_instance()
        
        # All should be the same instance
        assert instance1 is instance2
        assert instance2 is instance3
    
    @settings(max_examples=100, deadline=5000)
    @given(num_calls=st.integers(min_value=1, max_value=50))
    def test_property_singleton_instance_uniqueness(self, num_calls):
        """
        **Validates: Requirements 7.2**
        
        Feature: speaker-recognition, Property 14: Singleton Instance Uniqueness
        
        For any number of calls to VoiceEncoder.get_instance(), all calls SHALL
        return the same object instance (verified by Python id() function).
        
        This property test verifies that regardless of how many times get_instance()
        is called, the singleton pattern ensures only one VoiceEncoder instance exists
        in memory throughout the application lifetime.
        """
        # Collect instance IDs from multiple calls
        instance_ids = set()
        instances = []
        
        for _ in range(num_calls):
            instance = VoiceEncoder.get_instance()
            instances.append(instance)
            instance_ids.add(id(instance))
        
        # All calls should return the same instance (only one unique ID)
        assert len(instance_ids) == 1, (
            f"Expected exactly 1 unique instance, but got {len(instance_ids)} "
            f"different instances across {num_calls} calls"
        )
        
        # Verify all instances are the same object
        first_instance = instances[0]
        for i, instance in enumerate(instances[1:], start=1):
            assert instance is first_instance, (
                f"Instance at index {i} is not the same object as the first instance"
            )
            assert id(instance) == id(first_instance), (
                f"Instance at index {i} has different id: {id(instance)} vs {id(first_instance)}"
            )


class TestVoiceEncoderEmbedding:
    """Test embedding generation functionality."""
    
    @pytest.fixture
    def encoder(self):
        """Get VoiceEncoder instance for tests."""
        return VoiceEncoder.get_instance()
    
    @pytest.fixture
    def sample_audio(self):
        """Generate 1 second of synthetic PCM audio (16kHz, 16-bit, mono)."""
        sample_rate = 16000
        duration = 1.0
        frequency = 440  # A4 note
        
        # Generate sine wave
        t = np.linspace(0, duration, int(sample_rate * duration))
        samples = (0.5 * np.sin(2 * np.pi * frequency * t) * 32767).astype(np.int16)
        
        return samples.tobytes()
    
    @settings(max_examples=100, deadline=5000)
    @given(
        duration=st.floats(min_value=0.5, max_value=5.0),
        frequency=st.integers(min_value=100, max_value=2000),
        volume=st.floats(min_value=0.1, max_value=0.9)
    )
    def test_property_embedding_generation_consistency(self, duration, frequency, volume):
        """
        **Validates: Requirements 1.2, 1.3, 2.2, 14.4**
        
        Feature: speaker-recognition, Property 1: Embedding Generation Consistency
        
        For any valid PCM audio sample (16kHz, 16-bit, mono, duration >= 0.5s),
        generating a voice fingerprint using Resemblyzer SHALL produce a
        256-dimensional normalized numpy array with L2 norm equal to 1.0 (±0.01).
        
        This property test verifies that:
        1. Embeddings always have exactly 256 dimensions
        2. Embeddings are L2-normalized (norm = 1.0 ± 0.01)
        3. The property holds across various audio characteristics (duration, frequency, volume)
        """
        # Generate synthetic PCM audio with given parameters
        sample_rate = 16000
        num_samples = int(sample_rate * duration)
        t = np.linspace(0, duration, num_samples)
        samples = (volume * np.sin(2 * np.pi * frequency * t) * 32767).astype(np.int16)
        audio_pcm = samples.tobytes()
        
        # Get encoder and generate embedding
        encoder = VoiceEncoder.get_instance()
        embedding = encoder.embed_utterance(audio_pcm)
        
        # Property 1: Embedding must be 256-dimensional
        assert embedding.shape == (256,), (
            f"Expected 256-dimensional embedding, but got shape {embedding.shape}. "
            f"Audio parameters: duration={duration:.2f}s, frequency={frequency}Hz, volume={volume:.2f}"
        )
        
        # Property 2: Embedding must be a numpy array
        assert isinstance(embedding, np.ndarray), (
            f"Expected numpy.ndarray, but got {type(embedding)}"
        )
        
        # Property 3: Embedding must be L2-normalized (norm = 1.0 ± 0.01)
        norm = np.linalg.norm(embedding)
        assert 0.99 <= norm <= 1.01, (
            f"Expected L2 norm between 0.99 and 1.01, but got {norm:.6f}. "
            f"Audio parameters: duration={duration:.2f}s, frequency={frequency}Hz, volume={volume:.2f}"
        )
        
        # Property 4: Embedding values should be finite (no NaN or Inf)
        assert np.all(np.isfinite(embedding)), (
            f"Embedding contains non-finite values (NaN or Inf). "
            f"Audio parameters: duration={duration:.2f}s, frequency={frequency}Hz, volume={volume:.2f}"
        )
    
    def test_embedding_has_correct_dimensions(self, encoder, sample_audio):
        """Verify embedding is 256-dimensional."""
        embedding = encoder.embed_utterance(sample_audio)
        
        assert embedding.shape == (256,), f"Expected 256-dim, got {embedding.shape}"
        assert isinstance(embedding, np.ndarray)
        assert embedding.dtype == np.float32 or embedding.dtype == np.float64
    
    def test_embedding_is_normalized(self, encoder, sample_audio):
        """Verify embedding has L2 norm approximately equal to 1.0."""
        embedding = encoder.embed_utterance(sample_audio)
        
        norm = np.linalg.norm(embedding)
        assert 0.99 <= norm <= 1.01, f"Expected L2 norm ~1.0, got {norm}"
    
    def test_embedding_generation_is_deterministic(self, encoder, sample_audio):
        """Verify same audio produces same embedding."""
        embedding1 = encoder.embed_utterance(sample_audio)
        embedding2 = encoder.embed_utterance(sample_audio)
        
        # Embeddings should be very similar (cosine similarity ~1.0)
        similarity = np.dot(embedding1, embedding2)
        assert similarity > 0.99, f"Expected similarity > 0.99, got {similarity}"
    
    def test_empty_audio_raises_error(self, encoder):
        """Verify empty audio bytes raise ValueError."""
        with pytest.raises(ValueError, match="Audio bytes cannot be empty"):
            encoder.embed_utterance(b"")
    
    def test_different_audio_produces_different_embeddings(self, encoder):
        """Verify different audio produces different embeddings."""
        # Generate two different audio samples
        sample_rate = 16000
        duration = 1.0
        
        # Audio 1: 440 Hz sine wave
        t = np.linspace(0, duration, int(sample_rate * duration))
        audio1 = (0.5 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16).tobytes()
        
        # Audio 2: 880 Hz sine wave (different frequency)
        audio2 = (0.5 * np.sin(2 * np.pi * 880 * t) * 32767).astype(np.int16).tobytes()
        
        embedding1 = encoder.embed_utterance(audio1)
        embedding2 = encoder.embed_utterance(audio2)
        
        # Embeddings should be different (cosine similarity < 1.0)
        similarity = np.dot(embedding1, embedding2)
        assert similarity < 0.99, f"Expected different embeddings, got similarity {similarity}"


class TestAudioPreprocessing:
    """Test audio preprocessing functionality."""
    
    @pytest.fixture
    def encoder(self):
        """Get VoiceEncoder instance for tests."""
        return VoiceEncoder.get_instance()
    
    def test_bytes_to_numpy_conversion(self, encoder):
        """Verify PCM bytes are correctly converted to numpy array."""
        # Create simple audio: [0, 16384, -16384, 32767, -32768]
        samples = np.array([0, 16384, -16384, 32767, -32768], dtype=np.int16)
        audio_bytes = samples.tobytes()
        
        # Convert using internal method
        audio_float = encoder._bytes_to_numpy(audio_bytes)
        
        # Check conversion
        assert audio_float.dtype == np.float32
        assert len(audio_float) == 5
        
        # Check normalization to [-1, 1]
        assert -1.0 <= audio_float.min() <= 1.0
        assert -1.0 <= audio_float.max() <= 1.0
        
        # Check specific values
        assert abs(audio_float[0] - 0.0) < 0.01  # 0 / 32768 = 0
        assert abs(audio_float[1] - 0.5) < 0.01  # 16384 / 32768 = 0.5
        assert abs(audio_float[2] - (-0.5)) < 0.01  # -16384 / 32768 = -0.5
        assert abs(audio_float[3] - 1.0) < 0.01  # 32767 / 32768 ≈ 1.0
        assert abs(audio_float[4] - (-1.0)) < 0.01  # -32768 / 32768 = -1.0
    
    def test_empty_bytes_raises_error(self, encoder):
        """Verify empty bytes raise ValueError."""
        with pytest.raises(ValueError, match="Audio bytes cannot be empty"):
            encoder._bytes_to_numpy(b"")
