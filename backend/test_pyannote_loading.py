"""
Test script to verify Pyannote models load correctly with k2_fsa patch.
"""

import os
import sys

# Set up environment
os.environ.setdefault('HF_TOKEN', 'YOUR_HUGGINGFACE_TOKEN_HERE')

print("=" * 80)
print("Testing Pyannote Model Loading with k2_fsa Patch")
print("=" * 80)

# Step 0: Apply HuggingFace compatibility patch
print("\n[0/4] Applying HuggingFace API compatibility patch...")
import huggingface_hub
import huggingface_hub.file_download as _hf_file_download

_original_hf_hub_download = huggingface_hub.hf_hub_download

def _patched_hf_hub_download(*args, **kwargs):
    if 'use_auth_token' in kwargs:
        legacy_token = kwargs.pop('use_auth_token')
        if legacy_token is not None and 'token' not in kwargs:
            kwargs['token'] = legacy_token
    return _original_hf_hub_download(*args, **kwargs)

huggingface_hub.hf_hub_download = _patched_hf_hub_download
_hf_file_download.hf_hub_download = _patched_hf_hub_download
print("✓ HuggingFace API patch applied")

# Step 1: Apply k2_fsa patch
print("\n[1/4] Applying k2_fsa patch...")
from app.utils.speechbrain_patch import patch_speechbrain_k2
patch_result = patch_speechbrain_k2()
print(f"✓ Patch applied: {patch_result}")

# Step 2: Import Pyannote
print("\n[2/4] Importing pyannote.audio...")
from pyannote.audio import Pipeline, Model
print("✓ Pyannote imported successfully")

# Step 3: Test Overlap Detection model loading
print("\n[3/4] Loading OverlappedSpeechDetection model...")
try:
    overlap_detector = Pipeline.from_pretrained(
        "pyannote/overlapped-speech-detection",
        use_auth_token=os.environ['HF_TOKEN']
    )
    print("✓ OverlappedSpeechDetection loaded successfully")
    print(f"  Model type: {type(overlap_detector)}")
except Exception as e:
    print(f"✗ Failed to load OverlappedSpeechDetection: {e}")
    sys.exit(1)

# Step 4: Test VAD model loading
print("\n[4/4] Loading segmentation-3.0 model for VAD...")
try:
    vad_model = Model.from_pretrained(
        "pyannote/segmentation-3.0",
        use_auth_token=os.environ['HF_TOKEN']
    )
    print("✓ Segmentation model loaded successfully")
    print(f"  Model type: {type(vad_model)}")
except Exception as e:
    print(f"✗ Failed to load segmentation model: {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("SUCCESS: All Pyannote models loaded without k2_fsa errors!")
print("=" * 80)
print("\nYour PerfectListener pipeline should now work correctly.")
print("The k2_fsa dependency is NOT needed for your use case.")
