"""Manual test script for VoiceEncoder."""

import numpy as np
from app.services.voice_encoder import VoiceEncoder


def test_empty_audio():
    """Test error handling for empty audio."""
    encoder = VoiceEncoder.get_instance()
    try:
        encoder.embed_utterance(b'')
        print('❌ ERROR: Should have raised ValueError')
        return False
    except ValueError as e:
        print(f'✅ Correctly raised ValueError: {e}')
        return True


def test_different_audio():
    """Test that different audio produces different embeddings."""
    encoder = VoiceEncoder.get_instance()
    
    sample_rate = 16000
    duration = 1.0
    t = np.linspace(0, duration, int(sample_rate * duration))
    
    # Audio 1: 440 Hz
    audio1 = (0.5 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16).tobytes()
    
    # Audio 2: 880 Hz
    audio2 = (0.5 * np.sin(2 * np.pi * 880 * t) * 32767).astype(np.int16).tobytes()
    
    emb1 = encoder.embed_utterance(audio1)
    emb2 = encoder.embed_utterance(audio2)
    
    similarity = np.dot(emb1, emb2)
    print(f'Cosine similarity between different audio: {similarity:.6f}')
    
    if similarity < 0.99:
        print(f'✅ Different audio produces different embeddings')
        return True
    else:
        print(f'❌ ERROR: Different audio should produce different embeddings')
        return False


def test_audio_preprocessing():
    """Test audio preprocessing (bytes to numpy conversion)."""
    encoder = VoiceEncoder.get_instance()
    
    # Create test audio with known values
    samples = np.array([0, 16384, -16384, 32767, -32768], dtype=np.int16)
    audio_bytes = samples.tobytes()
    
    audio_float = encoder._bytes_to_numpy(audio_bytes)
    
    print(f'Audio float dtype: {audio_float.dtype}')
    print(f'Audio float values: {audio_float}')
    
    # Check normalization
    if audio_float.dtype == np.float32 and -1.0 <= audio_float.min() <= 1.0 and -1.0 <= audio_float.max() <= 1.0:
        print('✅ Audio preprocessing works correctly')
        return True
    else:
        print('❌ ERROR: Audio preprocessing failed')
        return False


if __name__ == '__main__':
    print('Testing VoiceEncoder implementation...\n')
    
    results = []
    
    print('Test 1: Empty audio error handling')
    results.append(test_empty_audio())
    print()
    
    print('Test 2: Different audio produces different embeddings')
    results.append(test_different_audio())
    print()
    
    print('Test 3: Audio preprocessing')
    results.append(test_audio_preprocessing())
    print()
    
    if all(results):
        print('✅ All tests passed!')
    else:
        print('❌ Some tests failed')
