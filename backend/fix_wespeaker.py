#!/usr/bin/env python3
"""
Fix WeSpeaker model download issue.
This script properly downloads the wespeaker-voxceleb-resnet34 model.
"""

import os
import sys

def fix_wespeaker():
    print("Fixing WeSpeaker model download...")
    
    try:
        from wespeaker.cli.speaker import load_model
        
        print("Attempting to download wespeaker-voxceleb-resnet34 model...")
        model = load_model("wespeaker-voxceleb-resnet34")
        print("✓ WeSpeaker model downloaded and loaded successfully!")
        
        # Test the model
        import numpy as np
        test_audio = np.random.randn(16000).astype(np.float32)  # 1 second of audio
        embedding = model.embed_utterance(test_audio)
        print(f"✓ Model test successful! Embedding shape: {embedding.shape}")
        
        return True
        
    except FileNotFoundError as e:
        print(f"✗ FileNotFoundError: {e}")
        print("\nThe model files are missing or corrupted.")
        print("\nTry these steps:")
        print("1. Delete the cached model directory:")
        print("   - Windows: %USERPROFILE%\\.cache\\wespeaker\\")
        print("   - Linux/Mac: ~/.cache/wespeaker/")
        print("2. Run this script again to re-download")
        return False
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = fix_wespeaker()
    sys.exit(0 if success else 1)
