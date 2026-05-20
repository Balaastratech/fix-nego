"""
Verify that all dependencies and models are correctly installed for the
Conv-TasNet + Pyannote + WeSpeaker pipeline.
"""

import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def check_package(package_name, import_name=None):
    """Check if a package is installed."""
    if import_name is None:
        import_name = package_name
    
    try:
        # Special handling for pyannote.audio due to torchaudio compatibility
        if import_name == "pyannote.audio":
            # Temporarily patch torchaudio to avoid the deprecated set_audio_backend call
            import torchaudio
            if not hasattr(torchaudio, 'set_audio_backend'):
                # Monkey patch for compatibility
                torchaudio.set_audio_backend = lambda x: None
        
        # Special handling for wespeaker - check if module exists
        if import_name == "wespeaker":
            import importlib.util
            spec = importlib.util.find_spec("wespeaker")
            if spec is not None:
                logger.info(f"✓ {package_name} installed")
                return True
            else:
                logger.error(f"✗ {package_name} NOT installed")
                return False
        
        __import__(import_name)
        logger.info(f"✓ {package_name} installed")
        return True
    except ImportError as e:
        logger.error(f"✗ {package_name} NOT installed: {e}")
        return False

def main():
    logger.info("=" * 70)
    logger.info("Dependency Verification for Conv-TasNet + Pyannote + WeSpeaker Pipeline")
    logger.info("=" * 70)
    
    all_ok = True
    
    # Core dependencies
    logger.info("\nCore Dependencies:")
    all_ok &= check_package("torch")
    all_ok &= check_package("torchaudio")
    all_ok &= check_package("numpy")
    all_ok &= check_package("scipy")
    
    # Pipeline-specific dependencies
    logger.info("\nPipeline Dependencies:")
    all_ok &= check_package("pyannote.audio", "pyannote.audio")
    all_ok &= check_package("wespeaker")
    all_ok &= check_package("asteroid-filterbanks", "asteroid_filterbanks")
    
    # Check PyTorch version
    logger.info("\nPyTorch Configuration:")
    try:
        import torch
        version = torch.__version__
        logger.info(f"  PyTorch version: {version}")
        
        major, minor = map(int, version.split('.')[:2])
        if major >= 2:
            logger.info(f"  ✓ PyTorch version >= 2.0")
        else:
            logger.error(f"  ✗ PyTorch version < 2.0 (found {version})")
            all_ok = False
        
        if torch.cuda.is_available():
            logger.info(f"  ✓ CUDA available: {torch.cuda.get_device_name(0)}")
        else:
            logger.info(f"  ℹ CUDA not available (will use CPU)")
    except Exception as e:
        logger.error(f"  ✗ Failed to check PyTorch: {e}")
        all_ok = False
    
    # Check HF_TOKEN
    logger.info("\nEnvironment Configuration:")
    import os
    if os.getenv("HF_TOKEN"):
        logger.info("  ✓ HF_TOKEN is set")
    else:
        logger.error("  ✗ HF_TOKEN not set (required for Pyannote models)")
        logger.error("    Set HF_TOKEN in .env file or environment")
        all_ok = False
    
    # Summary
    logger.info("\n" + "=" * 70)
    if all_ok:
        logger.info("✓ All dependencies verified successfully!")
        logger.info("=" * 70)
        logger.info("\nYou can now run: python download_models.py")
        return 0
    else:
        logger.error("✗ Some dependencies are missing or misconfigured")
        logger.error("=" * 70)
        logger.error("\nPlease install missing packages:")
        logger.error("  pip install -r requirements.txt")
        return 1

if __name__ == "__main__":
    sys.exit(main())
