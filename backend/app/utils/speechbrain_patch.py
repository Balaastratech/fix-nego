"""
Patch SpeechBrain to suppress ALL lazy import errors.

SpeechBrain tries to lazy-import optional integrations (k2_fsa, nlp, etc.)
but import failures crash Pyannote model loading. Since we don't use these
integrations (we use Gemini for transcription), we can safely suppress them.
"""

import sys
import warnings


def patch_speechbrain_k2():
    """
    Monkey-patch SpeechBrain to suppress all lazy import errors.
    
    This prevents lazy import failures from breaking Pyannote model loading.
    
    Call this BEFORE importing pyannote.audio.
    """
    try:
        # Suppress ALL lazy import warnings from SpeechBrain
        warnings.filterwarnings(
            'ignore',
            message='.*Lazy import.*failed.*',
            category=UserWarning
        )
        
        # Create a dummy module that returns None for any attribute
        class DummyModule:
            """Dummy module that returns None for any attribute access."""
            def __getattr__(self, name):
                return None
            def __call__(self, *args, **kwargs):
                return None
        
        # Inject dummy modules for ALL known SpeechBrain optional integrations
        dummy = DummyModule()
        optional_modules = [
            'speechbrain.integrations.k2_fsa',
            'speechbrain.integrations.nlp',
            'speechbrain.integrations.kenlm',
            'speechbrain.k2_integration',
            'k2',
            'k2_fsa',
            'kenlm',
        ]
        
        for module_name in optional_modules:
            sys.modules[module_name] = dummy
        
        print(f"[PATCH] SpeechBrain patch applied - {len(optional_modules)} optional modules stubbed")
        return True
        
    except Exception as e:
        print(f"[PATCH] Failed to patch SpeechBrain: {e}")
        return False
