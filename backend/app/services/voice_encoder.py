"""
VoiceEncoder Singleton Service

This module provides a singleton wrapper for the Resemblyzer VoiceEncoder model.
The singleton pattern ensures only one instance of the model is loaded in memory,
preventing redundant model loading and reducing memory usage.

The VoiceEncoder generates 256-dimensional voice embeddings from PCM audio,
which are used for speaker recognition via cosine similarity comparison.
"""

import logging
from typing import Optional, Any
import numpy as np

logger = logging.getLogger(__name__)


class VoiceEncoder:
    """
    Singleton wrapper for Resemblyzer VoiceEncoder model.
    
    This class ensures only one instance of the Resemblyzer model is loaded
    throughout the application lifetime, optimizing memory usage and startup time.
    
    The model generates 256-dimensional L2-normalized embeddings from PCM audio,
    suitable for speaker recognition via cosine similarity.
    """
    
    _instance: Optional['VoiceEncoder'] = None
    _model: Optional[Any] = None
    
    def __new__(cls):
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> 'VoiceEncoder':
        """
        Get or create the singleton VoiceEncoder instance.
        
        This method loads the Resemblyzer model on first call and returns
        the cached instance on subsequent calls.
        
        Returns:
            VoiceEncoder: The singleton instance with loaded model
            
        Raises:
            Exception: If Resemblyzer model fails to load
        """
        if cls._instance is None:
            logger.info("Initializing VoiceEncoder singleton...")
            instance = cls()
            instance._load_model()
            logger.info("VoiceEncoder singleton initialized successfully")
        return cls._instance
    
    def _load_model(self) -> None:
        """
        Load the Resemblyzer VoiceEncoder model.
        
        This method is called once during singleton initialization.
        The model is loaded into memory and cached for all future embeddings.
        
        Raises:
            Exception: If model loading fails
        """
        try:
            from resemblyzer import VoiceEncoder as ResemblyzerEncoder
            self._model = ResemblyzerEncoder()
            logger.info("Resemblyzer model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Resemblyzer model: {e}", exc_info=True)
            raise
    
    def embed_utterance(self, audio_pcm: bytes) -> np.ndarray:
        """
        Generate 256-dimensional voice embedding from PCM audio.
        
        This method converts raw PCM audio bytes into a normalized voice embedding
        suitable for speaker recognition. The embedding is L2-normalized for
        cosine similarity comparison.
        
        Audio preprocessing steps:
        1. Convert bytes to numpy int16 array
        2. Normalize to float32 in range [-1, 1]
        3. Generate embedding using Resemblyzer
        4. L2 normalize the embedding
        
        Args:
            audio_pcm: Raw PCM audio (16kHz, 16-bit, mono)
            
        Returns:
            Normalized 256-dimensional numpy array (L2 norm = 1.0)
            
        Raises:
            ValueError: If audio format is invalid
            Exception: If embedding generation fails
        """
        if self._model is None:
            raise RuntimeError("VoiceEncoder model not loaded. Call get_instance() first.")
        
        try:
            # Convert PCM bytes to numpy array
            audio_array = self._bytes_to_numpy(audio_pcm)
            
            # Generate embedding using Resemblyzer
            # Resemblyzer expects float32 audio normalized to [-1, 1]
            embedding = self._model.embed_utterance(audio_array)
            
            # L2 normalize for cosine similarity
            # Resemblyzer already returns normalized embeddings, but we ensure it
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
            
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}", exc_info=True)
            raise
    
    def _bytes_to_numpy(self, audio_bytes: bytes) -> np.ndarray:
        """
        Convert PCM bytes to numpy array efficiently.
        
        This method uses numpy's frombuffer for zero-copy conversion,
        then normalizes the int16 samples to float32 in range [-1, 1].
        
        Args:
            audio_bytes: Raw PCM audio bytes (16-bit signed integers)
            
        Returns:
            Float32 numpy array normalized to [-1, 1]
            
        Raises:
            ValueError: If audio_bytes is empty or invalid format
        """
        if not audio_bytes:
            raise ValueError("Audio bytes cannot be empty")
        
        # Use frombuffer for zero-copy view of bytes as int16 array
        samples = np.frombuffer(audio_bytes, dtype=np.int16)
        
        # Normalize to [-1, 1] range
        # int16 range is -32768 to 32767, so divide by 32768.0
        audio_float = samples.astype(np.float32) / 32768.0
        
        return audio_float
