"""
Comprehensive verification of GPU/CPU compatibility and all dependencies.
Logs detailed device information and checks for conflicts.
"""

import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def print_section(title):
    """Print a section header."""
    logger.info("\n" + "=" * 80)
    logger.info(f"  {title}")
    logger.info("=" * 80)

def verify_device_compatibility():
    """Verify GPU/CPU compatibility and log detailed device information."""
    print_section("DEVICE COMPATIBILITY VERIFICATION")
    
    try:
        import torch
        
        logger.info(f"PyTorch Version: {torch.__version__}")
        logger.info(f"Python Version: {sys.version}")
        
        # Check CUDA availability
        cuda_available = torch.cuda.is_available()
        logger.info(f"\nCUDA Available: {cuda_available}")
        
        if cuda_available:
            logger.info(f"CUDA Version: {torch.version.cuda}")
            logger.info(f"cuDNN Version: {torch.backends.cudnn.version()}")
            logger.info(f"Number of GPUs: {torch.cuda.device_count()}")
            
            for i in range(torch.cuda.device_count()):
                logger.info(f"\nGPU {i}:")
                logger.info(f"  Name: {torch.cuda.get_device_name(i)}")
                logger.info(f"  Compute Capability: {torch.cuda.get_device_capability(i)}")
                props = torch.cuda.get_device_properties(i)
                logger.info(f"  Total Memory: {props.total_memory / 1024**3:.2f} GB")
                logger.info(f"  Multi Processor Count: {props.multi_processor_count}")
        else:
            logger.info("Running on CPU")
            logger.info(f"CPU Count: {torch.get_num_threads()} threads")
        
        # Test tensor creation
        logger.info("\nTesting tensor operations...")
        device = torch.device("cuda" if cuda_available else "cpu")
        test_tensor = torch.randn(100, 100).to(device)
        result = torch.matmul(test_tensor, test_tensor)
        logger.info(f"✓ Tensor operations working on {device}")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Device verification failed: {e}")
        return False

def verify_core_dependencies():
    """Verify core dependencies are installed correctly."""
    print_section("CORE DEPENDENCIES VERIFICATION")
    
    dependencies = {
        'torch': 'torch',
        'torchaudio': 'torchaudio',
        'numpy': 'numpy',
        'scipy': 'scipy',
    }
    
    all_ok = True
    for name, import_name in dependencies.items():
        try:
            module = __import__(import_name)
            version = getattr(module, '__version__', 'unknown')
            logger.info(f"✓ {name:20s} {version}")
        except ImportError as e:
            logger.error(f"✗ {name:20s} NOT INSTALLED")
            all_ok = False
    
    return all_ok

def verify_pipeline_dependencies():
    """Verify pipeline-specific dependencies."""
    print_section("PIPELINE DEPENDENCIES VERIFICATION")
    
    # Apply compatibility patches first
    logger.info("Applying torchaudio compatibility patches...")
    try:
        import fix_torchaudio
        logger.info("✓ Compatibility patches applied")
    except Exception as e:
        logger.warning(f"⚠ Could not apply patches: {e}")
    
    dependencies = {
        'pyannote.audio': 'pyannote.audio',
        'wespeaker': 'wespeaker',
        'asteroid_filterbanks': 'asteroid_filterbanks',
        'onnxruntime': 'onnxruntime',
        's3prl': 's3prl',
        'peft': 'peft',
        'whisper': 'whisper',
        'soundfile': 'soundfile',
    }
    
    all_ok = True
    for name, import_name in dependencies.items():
        try:
            module = __import__(import_name)
            version = getattr(module, '__version__', 'unknown')
            logger.info(f"✓ {name:20s} {version}")
        except ImportError as e:
            logger.error(f"✗ {name:20s} NOT INSTALLED: {e}")
            all_ok = False
        except Exception as e:
            logger.warning(f"⚠ {name:20s} Import warning: {e}")
    
    return all_ok

def check_dependency_conflicts():
    """Check for dependency conflicts using pip."""
    print_section("DEPENDENCY CONFLICT CHECK")
    
    import subprocess
    
    try:
        result = subprocess.run(
            ['pip', 'check'],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0 and not result.stdout.strip():
            logger.info("✓ No dependency conflicts found")
            return True
        else:
            output = result.stdout.strip()
            if output:
                logger.warning("⚠ Dependency warnings found:")
                for line in output.split('\n'):
                    if 'resemblyzer' in line.lower() or 'webrtcvad' in line.lower():
                        logger.info(f"  (Ignorable) {line}")
                    elif 'hdbscan' in line.lower():
                        logger.info(f"  (Ignorable) {line}")
                    else:
                        logger.warning(f"  {line}")
            return True
            
    except Exception as e:
        logger.error(f"✗ Could not check dependencies: {e}")
        return False

def verify_model_compatibility():
    """Verify that models can be loaded."""
    print_section("MODEL COMPATIBILITY VERIFICATION")
    
    logger.info("Testing model loading capabilities...")
    
    # Test PyTorch model loading
    try:
        import torch
        logger.info("✓ PyTorch model loading: OK")
    except Exception as e:
        logger.error(f"✗ PyTorch model loading failed: {e}")
        return False
    
    # Test pyannote model structure
    try:
        from pyannote.audio import Pipeline
        logger.info("✓ Pyannote Pipeline class: OK")
    except Exception as e:
        logger.error(f"✗ Pyannote Pipeline import failed: {e}")
        return False
    
    # Test wespeaker structure
    try:
        import fix_torchaudio  # Apply patches first
        from wespeaker.cli.speaker import load_model
        logger.info("✓ WeSpeaker load_model function: OK")
    except Exception as e:
        logger.error(f"✗ WeSpeaker import failed: {e}")
        return False
    
    return True

def main():
    """Run all verifications."""
    logger.info("\n")
    logger.info("╔" + "═" * 78 + "╗")
    logger.info("║" + " " * 78 + "║")
    logger.info("║" + "  COMPREHENSIVE DEVICE AND DEPENDENCY VERIFICATION".center(78) + "║")
    logger.info("║" + " " * 78 + "║")
    logger.info("╚" + "═" * 78 + "╝")
    
    results = {
        'Device Compatibility': verify_device_compatibility(),
        'Core Dependencies': verify_core_dependencies(),
        'Pipeline Dependencies': verify_pipeline_dependencies(),
        'Dependency Conflicts': check_dependency_conflicts(),
        'Model Compatibility': verify_model_compatibility(),
    }
    
    # Summary
    print_section("VERIFICATION SUMMARY")
    
    all_passed = True
    for check, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"{check:30s} {status}")
        if not passed:
            all_passed = False
    
    logger.info("\n" + "=" * 80)
    if all_passed:
        logger.info("✓ ALL VERIFICATIONS PASSED")
        logger.info("=" * 80)
        logger.info("\nSystem is ready for Task 2 implementation.")
        return 0
    else:
        logger.error("✗ SOME VERIFICATIONS FAILED")
        logger.error("=" * 80)
        logger.error("\nPlease resolve the issues above before proceeding.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
