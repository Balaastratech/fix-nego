#!/usr/bin/env python3
"""
Download WeSpeaker model from ModelScope/HuggingFace.
"""

import os
import sys

def download_model():
    print("Downloading WeSpeaker model from HuggingFace...")
    
    try:
        from huggingface_hub import snapshot_download
        
        # Download the model
        model_path = snapshot_download(
            repo_id="Wespeaker/wespeaker-voxceleb-resnet34",
            cache_dir=os.path.expanduser("~/.cache/wespeaker"),
            local_dir=os.path.expanduser("~/.cache/wespeaker/wespeaker-voxceleb-resnet34"),
            local_dir_use_symlinks=False
        )
        
        print(f"✓ Model downloaded to: {model_path}")
        
        # Test loading
        from wespeaker.cli.speaker import load_model
        print("Testing model load...")
        model = load_model(model_path)
        print("✓ Model loaded successfully!")
        
        # Test inference
        import numpy as np
        test_audio = np.random.randn(16000).astype(np.float32)
        embedding = model.embed_utterance(test_audio)
        print(f"✓ Model test successful! Embedding shape: {embedding.shape}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = download_model()
    sys.exit(0 if success else 1)
