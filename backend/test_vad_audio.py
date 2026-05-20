"""
Quick test to save audio and check VAD detection.
Run this to debug why VAD isn't detecting speech.
"""
import wave
import numpy as np

# Create a test WAV file with 1 second of silence
sample_rate = 16000
duration = 1.0
samples = int(sample_rate * duration)

# Generate silence
audio = np.zeros(samples, dtype=np.int16)

# Save as WAV
with wave.open('test_silence.wav', 'wb') as wav_file:
    wav_file.setnchannels(1)  # Mono
    wav_file.setsampwidth(2)  # 16-bit
    wav_file.setframerate(sample_rate)
    wav_file.writeframes(audio.tobytes())

print("Created test_silence.wav - 1 second of silence")
print("Now test with actual recorded audio to see if VAD detects it")
