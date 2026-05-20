"""
Integration tests for frontend message formats and WebSocket handling.

Tests for Task 21: Frontend Integration
- 21.1: Verify TRANSCRIPT_UPDATE message format
- 21.2: Verify CONTEXT_UPDATE message format
- 21.3: Verify message ordering
- 21.4: Implement WebSocket error handling
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from app.services.perfect_listener import PerfectListenerSystem
from app.services.listener_agent import ListenerAgent
from app.models.negotiation import NegotiationSession


class TestTranscriptUpdateMessageFormat:
    """
    Task 21.1: Verify TRANSCRIPT_UPDATE message format
    Requirements: 21.1, 21.2
    """
    
    @pytest.mark.asyncio
    async def test_transcript_update_includes_all_required_fields(self):
        """
        Verify TRANSCRIPT_UPDATE message includes:
        - id
        - speaker
        - text
        - timestamp
        - start_time
        - end_time
        """
        # Arrange
        session = MagicMock(spec=NegotiationSession)
        session.session_id = "test_session"
        session.speaker_timeline = []
        
        websocket = AsyncMock()
        
        listener_agent = MagicMock(spec=ListenerAgent)
        listener_agent.accumulated_transcript = ""
        
        perfect_listener = PerfectListenerSystem(
            session=session,
            websocket=websocket,
            listener_agent=listener_agent
        )
        
        # Mock the Gemini Flash client
        mock_flash_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Hello, this is a test transcript"
        mock_flash_client.models.generate_content.return_value = mock_response
        perfect_listener.flash_client = mock_flash_client
        
        # Act
        audio = b'\x00' * 16000  # 1 second of silence
        start_time = 1234567890.5
        end_time = 1234567891.5
        speaker = "user"
        
        await perfect_listener._transcribe_turn(audio, speaker, start_time, end_time)
        
        # Assert
        websocket.send_json.assert_called_once()
        message = websocket.send_json.call_args[0][0]
        
        assert message["type"] == "TRANSCRIPT_UPDATE"
        assert "payload" in message
        
        payload = message["payload"]
        assert "id" in payload
        assert "speaker" in payload
        assert "text" in payload
        assert "timestamp" in payload
        assert "start_time" in payload
        assert "end_time" in payload
        
        # Verify field values
        assert payload["speaker"] == "user"
        assert payload["text"] == "Hello, this is a test transcript"
        assert payload["start_time"] == start_time
        assert payload["end_time"] == end_time
        assert payload["timestamp"] == int(start_time * 1000)
        assert payload["id"].startswith("turn_")
    
    @pytest.mark.asyncio
    async def test_transcript_update_format_matches_manual_mode(self):
        """
        Verify TRANSCRIPT_UPDATE format from PerfectListenerSystem matches
        the format from manual mode (ListenerAgent.transcribe_segment)
        """
        # Test PerfectListenerSystem format
        session = MagicMock(spec=NegotiationSession)
        session.session_id = "test_session"
        session.speaker_timeline = []
        
        websocket_perfect = AsyncMock()
        
        listener_agent = MagicMock(spec=ListenerAgent)
        listener_agent.accumulated_transcript = ""
        
        perfect_listener = PerfectListenerSystem(
            session=session,
            websocket=websocket_perfect,
            listener_agent=listener_agent
        )
        
        mock_flash_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Test transcript"
        mock_flash_client.models.generate_content.return_value = mock_response
        perfect_listener.flash_client = mock_flash_client
        
        audio = b'\x00' * 16000
        start_time = 1234567890.5
        end_time = 1234567891.5
        
        await perfect_listener._transcribe_turn(audio, "user", start_time, end_time)
        
        perfect_message = websocket_perfect.send_json.call_args[0][0]
        perfect_payload = perfect_message["payload"]
        
        # Test manual mode format (ListenerAgent.transcribe_segment)
        websocket_manual = AsyncMock()
        
        listener = ListenerAgent(
            session=session,
            audio_buffer=MagicMock(),
            gemini_send_lock=asyncio.Lock(),
            websocket=websocket_manual,
            on_context_ready=AsyncMock()
        )
        
        # Mock the _fast_transcribe method
        with patch.object(listener, '_fast_transcribe', return_value="Test transcript"):
            await listener.transcribe_segment("user", audio, start_time, end_time)
        
        manual_message = websocket_manual.send_json.call_args[0][0]
        manual_payload = manual_message["payload"]
        
        # Assert both formats have the same structure
        assert perfect_message["type"] == manual_message["type"] == "TRANSCRIPT_UPDATE"
        assert set(perfect_payload.keys()) == set(manual_payload.keys())
        
        # Verify field types match
        assert isinstance(perfect_payload["id"], str)
        assert isinstance(manual_payload["id"], str)
        assert isinstance(perfect_payload["speaker"], str)
        assert isinstance(manual_payload["speaker"], str)
        assert isinstance(perfect_payload["text"], str)
        assert isinstance(manual_payload["text"], str)
        assert isinstance(perfect_payload["timestamp"], int)
        assert isinstance(manual_payload["timestamp"], int)
        assert isinstance(perfect_payload["start_time"], float)
        assert isinstance(manual_payload["start_time"], float)
        assert isinstance(perfect_payload["end_time"], float)
        assert isinstance(manual_payload["end_time"], float)


class TestContextUpdateMessageFormat:
    """
    Task 21.2: Verify CONTEXT_UPDATE message format
    Requirements: 21.3
    """
    
    @pytest.mark.asyncio
    async def test_context_update_includes_all_fields(self):
        """
        Verify CONTEXT_UPDATE message includes all expected context fields
        """
        # Arrange
        session = MagicMock(spec=NegotiationSession)
        session.session_id = "test_session"
        session.copilot_active = False
        
        websocket = AsyncMock()
        
        listener = ListenerAgent(
            session=session,
            audio_buffer=MagicMock(),
            gemini_send_lock=asyncio.Lock(),
            websocket=websocket,
            on_context_ready=AsyncMock()
        )
        
        # Set up context
        listener.last_context = {
            "item": "Laptop",
            "negotiation_type": "buying",
            "counterparty_price": 1000,
            "user_price": 800,
            "user_target_price": 850,
            "user_walk_away_price": 900,
            "counterparty_sentiment": "neutral",
            "counterparty_goal": "maximize profit",
            "key_moments": ["Initial offer made"],
            "leverage_points": ["Market research shows lower prices"],
            "market_data": {"average_price": 875}
        }
        
        context = {
            "transcript_snippet": "Recent conversation..."
        }
        
        # Act
        await listener._send_context_update(context)
        
        # Assert
        websocket.send_json.assert_called_once()
        message = websocket.send_json.call_args[0][0]
        
        assert message["type"] == "CONTEXT_UPDATE"
        assert "payload" in message
        
        payload = message["payload"]
        expected_fields = [
            "item",
            "negotiation_type",
            "seller_price",
            "user_offer",
            "user_target_price",
            "user_max_price",
            "sentiment",
            "counterparty_goal",
            "key_moments",
            "leverage_points",
            "transcript_snippet",
            "market_data",
            "cycle"
        ]
        
        for field in expected_fields:
            assert field in payload, f"Missing field: {field}"
        
        # Verify field values
        assert payload["item"] == "Laptop"
        assert payload["negotiation_type"] == "buying"
        assert payload["seller_price"] == 1000
        assert payload["user_offer"] == 800
        assert payload["sentiment"] == "neutral"


class TestMessageOrdering:
    """
    Task 21.3: Verify message ordering
    Requirements: 21.5
    """
    
    @pytest.mark.asyncio
    async def test_transcript_update_sent_before_context_update(self):
        """
        Verify TRANSCRIPT_UPDATE is sent before CONTEXT_UPDATE
        """
        # Arrange
        session = MagicMock(spec=NegotiationSession)
        session.session_id = "test_session"
        session.speaker_timeline = []
        session.copilot_active = False
        
        websocket = AsyncMock()
        call_order = []
        
        # Track call order
        async def track_send_json(message):
            call_order.append(message["type"])
        
        websocket.send_json.side_effect = track_send_json
        
        listener_agent = ListenerAgent(
            session=session,
            audio_buffer=MagicMock(),
            gemini_send_lock=asyncio.Lock(),
            websocket=websocket,
            on_context_ready=AsyncMock()
        )
        listener_agent.accumulated_transcript = ""
        listener_agent.last_context = {
            "item": "Test",
            "counterparty_sentiment": "neutral"
        }
        
        perfect_listener = PerfectListenerSystem(
            session=session,
            websocket=websocket,
            listener_agent=listener_agent
        )
        
        # Mock Gemini Flash
        mock_flash_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Test transcript"
        mock_flash_client.models.generate_content.return_value = mock_response
        perfect_listener.flash_client = mock_flash_client
        
        # Act - Transcribe turn (sends TRANSCRIPT_UPDATE)
        audio = b'\x00' * 16000
        await perfect_listener._transcribe_turn(audio, "user", 1234567890.5, 1234567891.5)
        
        # Simulate context extraction cycle (sends CONTEXT_UPDATE)
        context = {"transcript_snippet": "Test"}
        await listener_agent._send_context_update(context)
        
        # Assert
        assert len(call_order) >= 2
        # Find indices of TRANSCRIPT_UPDATE and CONTEXT_UPDATE
        transcript_idx = call_order.index("TRANSCRIPT_UPDATE")
        context_idx = call_order.index("CONTEXT_UPDATE")
        
        assert transcript_idx < context_idx, \
            "TRANSCRIPT_UPDATE should be sent before CONTEXT_UPDATE"


class TestWebSocketErrorHandling:
    """
    Task 21.4: Implement WebSocket error handling
    Requirements: 21.6
    """
    
    @pytest.mark.asyncio
    async def test_websocket_disconnection_handled_gracefully(self):
        """
        Verify WebSocket disconnections are handled gracefully without crashing
        """
        # Arrange
        session = MagicMock(spec=NegotiationSession)
        session.session_id = "test_session"
        session.speaker_timeline = []
        
        websocket = AsyncMock()
        # Simulate WebSocket disconnection
        websocket.send_json.side_effect = Exception("WebSocket disconnected")
        
        listener_agent = MagicMock(spec=ListenerAgent)
        listener_agent.accumulated_transcript = ""
        
        perfect_listener = PerfectListenerSystem(
            session=session,
            websocket=websocket,
            listener_agent=listener_agent
        )
        
        # Mock Gemini Flash
        mock_flash_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Test transcript"
        mock_flash_client.models.generate_content.return_value = mock_response
        perfect_listener.flash_client = mock_flash_client
        
        # Act - Should not raise exception
        audio = b'\x00' * 16000
        try:
            await perfect_listener._transcribe_turn(audio, "user", 1234567890.5, 1234567891.5)
            exception_raised = False
        except Exception:
            exception_raised = True
        
        # Assert
        assert not exception_raised, "WebSocket error should be handled gracefully"
        
        # Verify transcript was still appended despite WebSocket error
        assert len(listener_agent.accumulated_transcript) > 0
    
    @pytest.mark.asyncio
    async def test_websocket_errors_are_logged(self):
        """
        Verify WebSocket errors are logged with appropriate context
        """
        # Arrange
        session = MagicMock(spec=NegotiationSession)
        session.session_id = "test_session"
        session.speaker_timeline = []
        
        websocket = AsyncMock()
        websocket.send_json.side_effect = Exception("Connection lost")
        
        listener_agent = MagicMock(spec=ListenerAgent)
        listener_agent.accumulated_transcript = ""
        
        perfect_listener = PerfectListenerSystem(
            session=session,
            websocket=websocket,
            listener_agent=listener_agent
        )
        
        # Mock Gemini Flash
        mock_flash_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Test transcript"
        mock_flash_client.models.generate_content.return_value = mock_response
        perfect_listener.flash_client = mock_flash_client
        
        # Act
        audio = b'\x00' * 16000
        
        with patch('app.services.perfect_listener.logger') as mock_logger:
            await perfect_listener._transcribe_turn(audio, "user", 1234567890.5, 1234567891.5)
            
            # Assert - Check that error was logged
            # Look for error log calls
            error_logged = False
            for call_args in mock_logger.error.call_args_list:
                if "websocket" in str(call_args).lower() or "connection" in str(call_args).lower():
                    error_logged = True
                    break
            
            assert error_logged, "WebSocket error should be logged"
    
    @pytest.mark.asyncio
    async def test_context_update_websocket_error_handled(self):
        """
        Verify CONTEXT_UPDATE WebSocket errors are handled gracefully
        """
        # Arrange
        session = MagicMock(spec=NegotiationSession)
        session.session_id = "test_session"
        session.copilot_active = False
        
        websocket = AsyncMock()
        websocket.send_json.side_effect = Exception("WebSocket error")
        
        listener = ListenerAgent(
            session=session,
            audio_buffer=MagicMock(),
            gemini_send_lock=asyncio.Lock(),
            websocket=websocket,
            on_context_ready=AsyncMock()
        )
        
        listener.last_context = {
            "item": "Test",
            "counterparty_sentiment": "neutral"
        }
        
        # Act - Should not raise exception
        context = {"transcript_snippet": "Test"}
        try:
            await listener._send_context_update(context)
            exception_raised = False
        except Exception:
            exception_raised = True
        
        # Assert
        assert not exception_raised, "WebSocket error should be handled gracefully"
