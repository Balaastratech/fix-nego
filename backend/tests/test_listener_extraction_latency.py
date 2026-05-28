import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.negotiation import NegotiationSession
from app.services.listener_agent import ListenerAgent


@pytest.mark.asyncio
async def test_text_extraction_timeout_clears_inflight_and_allows_retry(monkeypatch):
    class SlowModels:
        async def generate_content(self, **_kwargs):
            await asyncio.sleep(0.05)
            return SimpleNamespace(text="{}")

    fake_client = SimpleNamespace(aio=SimpleNamespace(models=SlowModels()))
    monkeypatch.setattr(
        "app.services.listener_agent.genai.Client",
        lambda *args, **kwargs: fake_client,
    )
    monkeypatch.setattr(
        "app.services.listener_agent.settings.TEXT_EXTRACTION_TIMEOUT_SECONDS",
        0.01,
    )

    session = NegotiationSession(session_id="listener-timeout")
    agent = ListenerAgent(
        session=session,
        audio_buffer=object(),
        gemini_send_lock=asyncio.Lock(),
        websocket=AsyncMock(),
    )
    agent._running = True
    agent.accumulated_transcript = "User: The current offer is 900 dollars."

    await agent._run_text_extraction_cycle()

    assert agent._text_extraction_in_flight is False
    assert agent._last_extracted_transcript_hash == ""
    assert agent._last_text_extraction_time == 0.0


@pytest.mark.asyncio
async def test_listener_pause_cancels_poll_loop_and_resume_restarts(monkeypatch):
    fake_client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace()))
    monkeypatch.setattr(
        "app.services.listener_agent.genai.Client",
        lambda *args, **kwargs: fake_client,
    )

    session = NegotiationSession(session_id="listener-pause-resume")
    agent = ListenerAgent(
        session=session,
        audio_buffer=object(),
        gemini_send_lock=asyncio.Lock(),
        websocket=AsyncMock(),
    )

    agent.start()
    assert agent._task is not None
    assert agent._task.done() is False

    await agent.pause()

    assert agent._paused is True
    assert agent._task is None

    await agent.resume()

    assert agent._paused is False
    assert agent._task is not None
    assert agent._task.done() is False

    await agent.stop()
