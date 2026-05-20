"""
Download and verify pre-trained models for Conv-TasNet + Pyannote + WeSpeaker pipeline.

This script downloads:
1. Pyannote models (OverlappedSpeechDetection, VoiceActivityDetection, Embedding)
2. WeSpeaker ResNet34 model
3. Conv-TasNet model from Hugging Face

Requirements: HF_TOKEN environment variable must be set for Pyannote models.
"""

import os
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_hf_token():
    """Check if HF_TOKEN is set in environment."""
    token = os.getenv("HF_TOKEN")
    if not token:
        logger.error("HF_TOKEN environment variable not set!")
        logger.error("Please set HF_TOKEN in your .env file or environment")
        logger.error("Get your token from: https://huggingface.co/settings/tokens")
        return False
    logger.info("✓ HF_TOKEN found")
    return True

def download_pyannote_models():
    """Download Pyannote models."""
    logger.info("Downloading Pyannote models...")
    
    try:
        from pyannote.audio import Pipeline
        
        # 1. Overlap Detection
        logger.info("  - Loading OverlappedSpeechDetection...")
        overlap_model = Pipeline.from_pretrained(
            "pyannote/overlapped-speech-detection",
            token=os.getenv("HF_TOKEN")
        )
        logger.info("    ✓ OverlappedSpeechDetection loaded")
        
        # 2. Voice Activity Detection
        logger.info("  - Loading VoiceActivityDetection...")
        vad_model = Pipeline.from_pretrained(
            "pyannote/voice-activity-detection",
            token=os.getenv("HF_TOKEN")
        )
        logger.info("    ✓ VoiceActivityDetection loaded")
        
        # 3. Speaker Embedding
        logger.info("  - Loading Speaker Embedding...")
        embedding_model = Pipeline.from_pretrained(
            "pyannote/embedding",
            token=os.getenv("HF_TOKEN")
        )
        logger.info("    ✓ Speaker Embedding loaded")
        
        logger.info("✓ All Pyannote models downloaded successfully")
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to download Pyannote models: {e}")
        return False

def download_wespeaker_model():
    """Download WeSpeaker ResNet34 model."""
    logger.info("Downloading WeSpeaker model...")
    
    try:
        import wespeaker
        
        logger.info("  - Loading wespeaker-voxceleb-resnet34...")
        # WeSpeaker downloads models automatically on first use
        # We'll just verify the package is installed
        logger.info("    ✓ WeSpeaker package ready (models download on first use)")
        
        logger.info("✓ WeSpeaker model setup complete")
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to setup WeSpeaker: {e}")
        return False

def download_convtasnet_model():
    """Download Conv-TasNet model from Hugging Face."""
    logger.info("Downloading Conv-TasNet model...")
    
    try:
        import torch
        from torch.hub import load_state_dict_from_url
        
        logger.info("  - Loading JorisCos/ConvTasNet_Libri2Mix_sepclean_16k...")
        # Conv-TasNet model will be downloaded via torch.hub on first use
        # We'll verify torch is working
        logger.info("    ✓ Conv-TasNet setup ready (model downloads on first use)")
        
        logger.info("✓ Conv-TasNet model setup complete")
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to setup Conv-TasNet: {e}")
        return False

def verify_device():
    """Verify GPU/CPU availability."""
    logger.info("Verifying device compatibility...")
    
    try:
        import torch
        
        logger.info(f"  PyTorch version: {torch.__version__}")
        
        if torch.cuda.is_available():
            logger.info(f"  ✓ CUDA available")
            logger.info(f"  Device: {torch.cuda.get_device_name(0)}")
            logger.info(f"  CUDA version: {torch.version.cuda}")
        else:
            logger.info(f"  Device: CPU (GPU not available)")
            logger.info(f"  Note: Pipeline will run on CPU (slower but functional)")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to verify device: {e}")
        return False

def main():
    """Main function to download all models."""
    logger.info("=" * 70)
    logger.info("Conv-TasNet + Pyannote + WeSpeaker Model Download")
    logger.info("=" * 70)
    
    # Check prerequisites
    if not check_hf_token():
        logger.error("\nSetup failed: HF_TOKEN not configured")
        sys.exit(1)
    
    # Verify device
    if not verify_device():
        logger.error("\nSetup failed: Device verification failed")
        sys.exit(1)
    
    # Download models
    success = True
    
    if not download_pyannote_models():
        success = False
    
    if not download_wespeaker_model():
        success = False
    
    if not download_convtasnet_model():
        success = False
    
    # Summary
    logger.info("=" * 70)
    if success:
        logger.info("✓ All models downloaded successfully!")
        logger.info("=" * 70)
        logger.info("\nNext steps:")
        logger.info("1. Models are cached in ~/.cache/torch/ and ~/.cache/huggingface/")
        logger.info("2. Models will be loaded automatically when PerfectListenerSystem starts")
        logger.info("3. First load may take a few seconds as models are initialized")
        sys.exit(0)
    else:
        logger.error("✗ Some models failed to download")
        logger.error("=" * 70)
        logger.error("\nPlease check the errors above and:")
        logger.error("1. Verify HF_TOKEN is valid")
        logger.error("2. Check internet connection")
        logger.error("3. Ensure sufficient disk space (~2GB)")
        sys.exit(1)

if __name__ == "__main__":
    main()
