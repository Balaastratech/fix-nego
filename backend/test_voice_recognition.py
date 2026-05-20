"""
Real-world test for voice recognition pipeline.
Tests the complete flow from enrollment to speaker identification.

Run with: python -m backend.test_voice_recognition
"""

import asyncio
import base64
import json
import struct
import time
from pathlib import Path

from google import genai
from google.genai import types as genai_types

from app.config import settings


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000, num_channels: int = 1, sample_width: int = 2) -> bytes:
    """Convert PCM audio to WAV format."""
    byte_rate = sample_rate * num_channels * sample_width
    block_align = num_channels * sample_width
    data_size = len(pcm_data)
    chunk_size = 36 + data_size
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', chunk_size, b'WAVE', b'fmt ', 16, 1, num_channels,
        sample_rate, byte_rate, block_align, sample_width * 8, b'data', data_size
    )
    return header + pcm_data


def generate_test_audio(duration_seconds: float = 3.0, frequency: int = 440) -> bytes:
    """
    Generate test PCM audio (sine wave).
    This simulates audio data - in real test you'd use actual recorded audio.
    """
    import math
    sample_rate = 16000
    num_samples = int(sample_rate * duration_seconds)
    
    samples = []
    for i in range(num_samples):
        # Generate sine wave
        value = int(32767 * 0.3 * math.sin(2 * math.pi * frequency * i / sample_rate))
        # Convert to 16-bit PCM
        samples.append(struct.pack('<h', value))
    
    return b''.join(samples)


async def test_enrollment_storage():
    """Test 1: Check if enrollment audio is properly stored."""
    print("\n" + "="*80)
    print("TEST 1: Enrollment Audio Storage")
    print("="*80)
    
    # Simulate enrollment audio
    enrollment_audio = generate_test_audio(duration_seconds=3.0, frequency=440)
    print(f"✓ Generated enrollment audio: {len(enrollment_audio)} bytes ({len(enrollment_audio)/32000:.2f}s)")
    
    # Check if it can be converted to WAV
    wav_audio = pcm_to_wav(enrollment_audio)
    print(f"✓ Converted to WAV: {len(wav_audio)} bytes")
    
    # Check if it can be base64 encoded (for API)
    b64_audio = base64.b64encode(wav_audio).decode("utf-8")
    print(f"✓ Base64 encoded: {len(b64_audio)} characters")
    
    return enrollment_audio


async def test_flash_with_enrollment(enrollment_audio: bytes):
    """Test 2: Send enrollment + conversation audio to Flash and check speaker labels."""
    print("\n" + "="*80)
    print("TEST 2: Flash Speaker Identification with Enrollment")
    print("="*80)
    
    # Initialize Flash client
    if settings.GOOGLE_GENAI_USE_VERTEXAI:
        import os
        if settings.GOOGLE_APPLICATION_CREDENTIALS:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.GOOGLE_APPLICATION_CREDENTIALS
        if settings.GOOGLE_CLOUD_PROJECT:
            os.environ["GOOGLE_CLOUD_PROJECT"] = settings.GOOGLE_CLOUD_PROJECT
        
        client = genai.Client(
            vertexai=True,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION
        )
        print(f"✓ Using Vertex AI in {settings.GOOGLE_CLOUD_LOCATION}")
    else:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        print("✓ Using Gemini API")
    
    flash_model = settings.effective_flash_model
    print(f"✓ Using model: {flash_model}")
    
    # Generate conversation audio (different frequency to simulate different speaker)
    conversation_audio = generate_test_audio(duration_seconds=5.0, frequency=880)
    print(f"✓ Generated conversation audio: {len(conversation_audio)} bytes ({len(conversation_audio)/32000:.2f}s)")
    
    # Convert both to WAV
    enrollment_wav = pcm_to_wav(enrollment_audio)
    conversation_wav = pcm_to_wav(conversation_audio)
    
    enrollment_b64 = base64.b64encode(enrollment_wav).decode("utf-8")
    conversation_b64 = base64.b64encode(conversation_wav).decode("utf-8")
    
    # Build the exact same structure as listener_agent.py
    parts = []
    
    # Add enrollment audio with separators
    parts.append(genai_types.Part(
        text="=== REFERENCE VOICE SAMPLE (DO NOT TRANSCRIBE) ===\n"
    ))
    
    parts.append(genai_types.Part(
        inline_data=genai_types.Blob(
            mime_type="audio/wav",
            data=enrollment_b64,
        )
    ))
    
    parts.append(genai_types.Part(
        text="\n=== END REFERENCE (DO NOT TRANSCRIBE ABOVE AUDIO) ===\n\n=== CONVERSATION TO TRANSCRIBE (BELOW) ===\n"
    ))
    
    # Add conversation audio
    parts.append(genai_types.Part(
        inline_data=genai_types.Blob(
            mime_type="audio/wav",
            data=conversation_b64,
        )
    ))
    
    # Add diarization prompt
    diarization_prompt = """
TRANSCRIPTION INSTRUCTIONS:

1. REFERENCE AUDIO (marked with === REFERENCE ===):
   - This is a voice sample for speaker identification ONLY
   - DO NOT transcribe this audio
   - DO NOT include it in diarization output
   - ONLY use it to learn voice characteristics

2. CONVERSATION AUDIO (marked with === CONVERSATION ===):
   - This is the ONLY audio to transcribe
   - Compare voices to reference sample
   - Voice matching reference = "USER"
   - Other voice = "COUNTERPARTY"
   - Transcribe EXACTLY what is said - be very careful with product names, numbers, and technical terms

Return diarization ONLY for conversation audio:
"diarization": [
  {"speaker": "USER" or "COUNTERPARTY", "text": "exact words spoken - be precise", "start_time": 0.0}
]

CRITICAL: 
- Ignore all audio before "=== CONVERSATION TO TRANSCRIBE ===" marker
- Be extremely accurate with product names, model numbers, and prices

Also extract context in this JSON format:
{
  "item": "what is being negotiated",
  "negotiation_type": "buying_goods | selling_goods | other",
  "user_price": null,
  "counterparty_price": null,
  "diarization": [...]
}
"""
    
    parts.append(genai_types.Part(text=diarization_prompt))
    
    print("\n📤 Sending to Flash API...")
    print(f"   - Enrollment audio: {len(enrollment_b64)} chars")
    print(f"   - Conversation audio: {len(conversation_b64)} chars")
    print(f"   - Total parts: {len(parts)}")
    
    try:
        response = client.models.generate_content(
            model=flash_model,
            contents=[genai_types.Content(role="user", parts=parts)],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        
        raw = response.text
        if raw:
            raw = raw.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:]).rstrip("`").strip()
        
        if not raw:
            print("❌ ERROR: Empty response from Flash")
            return None
        
        parsed = json.loads(raw)
        
        print("\n✅ Flash Response:")
        print(json.dumps(parsed, indent=2))
        
        # Check diarization
        diarization = parsed.get("diarization", [])
        if not diarization:
            print("\n⚠️  WARNING: No diarization data returned!")
            print("   This means Flash did not identify any speakers.")
        else:
            print(f"\n✓ Diarization returned: {len(diarization)} turns")
            for i, turn in enumerate(diarization):
                speaker = turn.get("speaker", "UNKNOWN")
                text = turn.get("text", "")
                start_time = turn.get("start_time", 0.0)
                print(f"   Turn {i+1}: [{speaker}] at {start_time:.1f}s: {text[:80]}")
                
                # Check if speaker labels are correct
                if speaker not in ("USER", "COUNTERPARTY"):
                    print(f"   ⚠️  WARNING: Unexpected speaker label: {speaker}")
                    print(f"      Expected: USER or COUNTERPARTY")
        
        return parsed
        
    except Exception as exc:
        print(f"\n❌ ERROR calling Flash: {exc}")
        import traceback
        traceback.print_exc()
        return None


async def test_without_enrollment():
    """Test 3: Send conversation audio WITHOUT enrollment to see generic labels."""
    print("\n" + "="*80)
    print("TEST 3: Flash Speaker Identification WITHOUT Enrollment")
    print("="*80)
    
    # Initialize Flash client
    if settings.GOOGLE_GENAI_USE_VERTEXAI:
        import os
        if settings.GOOGLE_APPLICATION_CREDENTIALS:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.GOOGLE_APPLICATION_CREDENTIALS
        if settings.GOOGLE_CLOUD_PROJECT:
            os.environ["GOOGLE_CLOUD_PROJECT"] = settings.GOOGLE_CLOUD_PROJECT
        
        client = genai.Client(
            vertexai=True,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION
        )
    else:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
    
    flash_model = settings.effective_flash_model
    
    # Generate conversation audio
    conversation_audio = generate_test_audio(duration_seconds=5.0, frequency=880)
    conversation_wav = pcm_to_wav(conversation_audio)
    conversation_b64 = base64.b64encode(conversation_wav).decode("utf-8")
    
    # Build parts WITHOUT enrollment
    parts = []
    
    parts.append(genai_types.Part(
        inline_data=genai_types.Blob(
            mime_type="audio/wav",
            data=conversation_b64,
        )
    ))
    
    diarization_prompt = """
SPEAKER IDENTIFICATION (No reference available):
Distinguish between two speakers based on voice characteristics.
Label them as "Speaker 1" and "Speaker 2" consistently.

TRANSCRIPTION ACCURACY:
- Transcribe EXACTLY what is said
- Be very careful with product names, numbers, and technical terms

Add a "diarization" field to your JSON response:
{
  "item": "what is being negotiated",
  "diarization": [
    {"speaker": "Speaker 1" or "Speaker 2", "text": "exact words spoken - be precise", "start_time": 0.0}
  ]
}
"""
    
    parts.append(genai_types.Part(text=diarization_prompt))
    
    print("\n📤 Sending to Flash API (no enrollment)...")
    
    try:
        response = client.models.generate_content(
            model=flash_model,
            contents=[genai_types.Content(role="user", parts=parts)],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        
        raw = response.text
        if raw:
            raw = raw.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:]).rstrip("`").strip()
        
        if not raw:
            print("❌ ERROR: Empty response from Flash")
            return None
        
        parsed = json.loads(raw)
        
        print("\n✅ Flash Response:")
        print(json.dumps(parsed, indent=2))
        
        # Check diarization
        diarization = parsed.get("diarization", [])
        if not diarization:
            print("\n⚠️  WARNING: No diarization data returned!")
        else:
            print(f"\n✓ Diarization returned: {len(diarization)} turns")
            for i, turn in enumerate(diarization):
                speaker = turn.get("speaker", "UNKNOWN")
                text = turn.get("text", "")
                start_time = turn.get("start_time", 0.0)
                print(f"   Turn {i+1}: [{speaker}] at {start_time:.1f}s: {text[:80]}")
                
                # Check if speaker labels are generic
                if speaker not in ("Speaker 1", "Speaker 2"):
                    print(f"   ⚠️  WARNING: Unexpected speaker label: {speaker}")
                    print(f"      Expected: Speaker 1 or Speaker 2")
        
        return parsed
        
    except Exception as exc:
        print(f"\n❌ ERROR calling Flash: {exc}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("VOICE RECOGNITION PIPELINE TEST")
    print("="*80)
    print("\nThis test validates the complete voice recognition flow:")
    print("1. Enrollment audio storage")
    print("2. Flash API speaker identification WITH enrollment")
    print("3. Flash API speaker identification WITHOUT enrollment")
    print("\nNOTE: This test uses synthetic audio (sine waves).")
    print("For real testing, replace with actual recorded voice samples.")
    print("="*80)
    
    # Test 1: Enrollment storage
    enrollment_audio = await test_enrollment_storage()
    
    # Test 2: Flash with enrollment
    result_with_enrollment = await test_flash_with_enrollment(enrollment_audio)
    
    # Test 3: Flash without enrollment
    result_without_enrollment = await test_without_enrollment()
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    print("\n✓ Test 1: Enrollment Storage - PASSED")
    
    if result_with_enrollment:
        diarization = result_with_enrollment.get("diarization", [])
        if diarization:
            has_user = any(t.get("speaker") == "USER" for t in diarization)
            has_counterparty = any(t.get("speaker") == "COUNTERPARTY" for t in diarization)
            if has_user or has_counterparty:
                print("✓ Test 2: Flash WITH Enrollment - PASSED")
                print(f"  - Found USER labels: {has_user}")
                print(f"  - Found COUNTERPARTY labels: {has_counterparty}")
            else:
                print("⚠️  Test 2: Flash WITH Enrollment - PARTIAL")
                print("  - Diarization returned but no USER/COUNTERPARTY labels")
        else:
            print("❌ Test 2: Flash WITH Enrollment - FAILED")
            print("  - No diarization data returned")
    else:
        print("❌ Test 2: Flash WITH Enrollment - FAILED")
        print("  - API call failed")
    
    if result_without_enrollment:
        diarization = result_without_enrollment.get("diarization", [])
        if diarization:
            has_speaker1 = any(t.get("speaker") == "Speaker 1" for t in diarization)
            has_speaker2 = any(t.get("speaker") == "Speaker 2" for t in diarization)
            if has_speaker1 or has_speaker2:
                print("✓ Test 3: Flash WITHOUT Enrollment - PASSED")
                print(f"  - Found Speaker 1 labels: {has_speaker1}")
                print(f"  - Found Speaker 2 labels: {has_speaker2}")
            else:
                print("⚠️  Test 3: Flash WITHOUT Enrollment - PARTIAL")
                print("  - Diarization returned but no Speaker 1/2 labels")
        else:
            print("❌ Test 3: Flash WITHOUT Enrollment - FAILED")
            print("  - No diarization data returned")
    else:
        print("❌ Test 3: Flash WITHOUT Enrollment - FAILED")
        print("  - API call failed")
    
    print("\n" + "="*80)
    print("NEXT STEPS:")
    print("="*80)
    print("1. If tests pass with synthetic audio, test with REAL voice recordings")
    print("2. Record yourself saying 'The quick brown fox...' for enrollment")
    print("3. Record a conversation for testing speaker identification")
    print("4. Replace generate_test_audio() calls with real audio file loading")
    print("5. Check if Flash correctly identifies YOUR voice vs OTHER voice")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
