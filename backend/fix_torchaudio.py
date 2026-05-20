"""
Compatibility patch for torchaudio 2.x with older packages.

This module patches the deprecated set_audio_backend function that was removed
in torchaudio 2.0 but is still used by some packages like s3prl (wespeaker dependency).

Import this BEFORE importing wespeaker or any package that uses s3prl.
"""

import sys
import torchaudio

# Monkey patch for torchaudio 2.x compatibility
if not hasattr(torchaudio, 'set_audio_backend'):
    def _dummy_set_audio_backend(backend):
        """Dummy function for backward compatibility. Does nothing."""
        pass
    
    torchaudio.set_audio_backend = _dummy_set_audio_backend
    print(f"[Compatibility] Patched torchaudio.set_audio_backend for torchaudio {torchaudio.__version__}")

# Patch sox_effects module (removed in torchaudio 2.1+)
if not hasattr(torchaudio, 'sox_effects'):
    from types import ModuleType
    
    # Create dummy sox_effects module
    sox_effects = ModuleType('sox_effects')
    
    def apply_effects_tensor(waveform, sample_rate, effects):
        """Dummy function - returns waveform unchanged."""
        return waveform, sample_rate
    
    sox_effects.apply_effects_tensor = apply_effects_tensor
    torchaudio.sox_effects = sox_effects
    sys.modules['torchaudio.sox_effects'] = sox_effects
    print(f"[Compatibility] Patched torchaudio.sox_effects module")
