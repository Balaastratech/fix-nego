"""
Unit tests for NegotiationSession speaker recognition fields.

Tests verify that the new speaker recognition fields added in task 1.6
are properly initialized and can be set/retrieved correctly.
"""

import pytest
import numpy as np
from app.models.negotiation import NegotiationSession, NegotiationState


def test_negotiation_session_speaker_fields_defaults():
    """Test that speaker recognition fields have correct default values."""
    session = NegotiationSession(session_id="test-123")
    
    # Verify speaker recognition fields (Requirements 11.1, 11.2, 11.3)
    assert session.user_embedding is None
    assert session.speaker_mode == "manual"
    assert session.speaker_recognition_enabled is False
    assert session.speaker_confidence_history == []
    assert session.speaker_service is None
    assert session.enrollment_service is None


def test_negotiation_session_user_embedding_storage():
    """Test that user_embedding can store numpy arrays."""
    session = NegotiationSession(session_id="test-123")
    
    # Create a 256-dimensional embedding
    embedding = np.random.randn(256)
    embedding = embedding / np.linalg.norm(embedding)  # Normalize
    
    # Store in session
    session.user_embedding = embedding
    
    # Verify storage
    assert session.user_embedding is not None
    assert isinstance(session.user_embedding, np.ndarray)
    assert session.user_embedding.shape == (256,)


def test_negotiation_session_speaker_mode_toggle():
    """Test that speaker_mode can be toggled between auto and manual."""
    session = NegotiationSession(session_id="test-123")
    
    # Default is manual
    assert session.speaker_mode == "manual"
    
    # Toggle to auto
    session.speaker_mode = "auto"
    assert session.speaker_mode == "auto"
    
    # Toggle back to manual
    session.speaker_mode = "manual"
    assert session.speaker_mode == "manual"


def test_negotiation_session_confidence_history_append():
    """Test that speaker_confidence_history can store classification results."""
    session = NegotiationSession(session_id="test-123")
    
    # Add classification results
    session.speaker_confidence_history.append({
        "timestamp": 1234567890.0,
        "speaker": "user",
        "confidence": 0.85
    })
    
    session.speaker_confidence_history.append({
        "timestamp": 1234567891.0,
        "speaker": "counterparty",
        "confidence": 0.72
    })
    
    # Verify history
    assert len(session.speaker_confidence_history) == 2
    assert session.speaker_confidence_history[0]["speaker"] == "user"
    assert session.speaker_confidence_history[1]["speaker"] == "counterparty"


def test_negotiation_session_speaker_recognition_enabled_toggle():
    """Test that speaker_recognition_enabled can be toggled."""
    session = NegotiationSession(session_id="test-123")
    
    # Default is False
    assert session.speaker_recognition_enabled is False
    
    # Enable
    session.speaker_recognition_enabled = True
    assert session.speaker_recognition_enabled is True
    
    # Disable
    session.speaker_recognition_enabled = False
    assert session.speaker_recognition_enabled is False


def test_negotiation_session_runtime_service_instances():
    """Test that runtime service instances can be stored."""
    session = NegotiationSession(session_id="test-123")
    
    # Mock service instances
    mock_speaker_service = object()
    mock_enrollment_service = object()
    
    # Store instances
    session.speaker_service = mock_speaker_service
    session.enrollment_service = mock_enrollment_service
    
    # Verify storage
    assert session.speaker_service is mock_speaker_service
    assert session.enrollment_service is mock_enrollment_service
