import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from app.services.deepgram_stream import DeepgramLiveClient


def test_deepgram_stream_url_uses_endpointing_without_utterance_end():
    client = DeepgramLiveClient(
        api_key="dg-key",
        source="local_mic",
        on_transcript=AsyncMock(),
        language="en-US",
        endpointing_ms=150,
    )

    url = client._build_url()

    assert "endpointing=150" in url
    assert "language=en-US" in url
    assert "interim_results=true" in url
    assert "utterance_end_ms" not in url


@pytest.mark.asyncio
async def test_deepgram_send_loop_sends_keepalive_when_idle():
    class FakeWebSocket:
        def __init__(self):
            self.sent = []

        async def send(self, message):
            self.sent.append(message)

    ws = FakeWebSocket()
    client = DeepgramLiveClient(
        api_key="dg-key",
        source="remote_app",
        on_transcript=AsyncMock(),
        keepalive_seconds=0.01,
    )
    client._ws = ws
    client._running = True
    client._last_send_at = 0.0

    task = asyncio.create_task(client._send_loop())
    await asyncio.sleep(0.6)
    client._running = False
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert json.loads(ws.sent[0]) == {"type": "KeepAlive"}


@pytest.mark.asyncio
async def test_deepgram_start_disables_websocket_compression(monkeypatch):
    captured = {}

    class FakeWebSocket:
        async def recv(self):
            await asyncio.sleep(60)

        async def send(self, _message):
            return None

        async def close(self):
            return None

    async def fake_connect(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeWebSocket()

    import websockets

    monkeypatch.setattr(websockets, "connect", fake_connect)
    client = DeepgramLiveClient(
        api_key="dg-key",
        source="local_mic",
        on_transcript=AsyncMock(),
    )

    await client.start()
    await client.stop()

    assert captured["kwargs"]["compression"] is None


def test_deepgram_stream_url_supports_language_multi():
    """Nova-3 code-switch streaming uses the literal `multi` token."""
    client = DeepgramLiveClient(
        api_key="dg-key",
        source="local_mic",
        on_transcript=AsyncMock(),
        language="multi",
    )
    url = client._build_url()
    assert "language=multi" in url


def test_deepgram_stream_url_supports_pinned_gujarati():
    """Gujarati is only available as a monolingual stream — make sure the code is emitted as-is."""
    client = DeepgramLiveClient(
        api_key="dg-key",
        source="local_mic",
        on_transcript=AsyncMock(),
        language="gu-IN",
    )
    url = client._build_url()
    assert "language=gu-IN" in url


def test_resolve_deepgram_language_default_when_flag_off(monkeypatch):
    """When MULTILANG_ENABLED is False, the resolver always returns the legacy default."""
    from app.config import settings
    monkeypatch.setattr(settings, "MULTILANG_ENABLED", False)
    monkeypatch.setattr(settings, "DEEPGRAM_STREAM_LANGUAGE", "en-US")
    assert settings.resolve_deepgram_language("auto_multi") == "en-US"
    assert settings.resolve_deepgram_language("pinned:gu-IN", "pinned:hi-IN") == "en-US"


def test_resolve_deepgram_language_honors_profile_when_flag_on(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "MULTILANG_ENABLED", True)
    assert settings.resolve_deepgram_language("auto_multi") == "multi"
    assert settings.resolve_deepgram_language("pinned:gu-IN") == "gu-IN"
    # per-source override wins over the session profile
    assert settings.resolve_deepgram_language("auto_multi", "pinned:hi-IN") == "hi-IN"
    # bare BCP-47 is treated as a pinned monolingual code
    assert settings.resolve_deepgram_language("es-US") == "es-US"


def test_ask_native_audio_flag_exists_and_is_bool():
    """The new flag must exist on settings and be bool-typed so handlers can toggle it."""
    from app.config import settings, Config
    assert hasattr(settings, "ASK_AI_NATIVE_AUDIO")
    assert isinstance(settings.ASK_AI_NATIVE_AUDIO, bool)
    # The class default may be True or False depending on operator preference
    # (it's intentionally configurable). We only check the field is defined.
    assert "ASK_AI_NATIVE_AUDIO" in Config.model_fields


@pytest.mark.asyncio
async def test_capture_private_ask_audio_skips_realtime_when_flag_off(monkeypatch):
    """When ASK_AI_NATIVE_AUDIO is off, no send_realtime_input call is made even if a Live session exists."""
    from app.config import settings
    from app.services.companion_runtime import CompanionRuntime
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setattr(settings, "ASK_AI_NATIVE_AUDIO", False)

    runtime = CompanionRuntime()
    session = MagicMock()
    session.session_id = "sess-test"
    session.question_capture_started_at = 0.0
    session.question_capture_id = None
    session.question_capture_bytes = b""
    session.question_capture_chunk_count = 0
    session.companion_partial_tasks = {}
    session.current_ask_capture = {}
    session.session_metrics = {}
    session.live_session = MagicMock()
    session.live_session.send_realtime_input = AsyncMock()
    session.ask_audio_activity_open = True   # would normally trigger send

    ws = AsyncMock()
    await runtime._capture_private_ask_audio(
        session=session, websocket=ws,
        payload={"started_at_ms": 0, "timestamp_ms": 0},
        chunk=b"\x00" * 1024, now=0.0,
    )
    assert session.live_session.send_realtime_input.call_count == 0
    assert session.question_capture_bytes == b"\x00" * 1024  # buffering still works


@pytest.mark.asyncio
async def test_capture_private_ask_audio_streams_realtime_when_flag_on(monkeypatch):
    """When ASK_AI_NATIVE_AUDIO is on and activity is open, each chunk gets streamed to Live."""
    from app.config import settings
    from app.services.companion_runtime import CompanionRuntime
    from unittest.mock import AsyncMock, MagicMock
    import asyncio as _asyncio

    monkeypatch.setattr(settings, "ASK_AI_NATIVE_AUDIO", True)

    runtime = CompanionRuntime()
    session = MagicMock()
    session.session_id = "sess-test"
    session.question_capture_started_at = 0.0
    session.question_capture_id = None
    session.question_capture_bytes = b""
    session.question_capture_chunk_count = 0
    session.companion_partial_tasks = {}
    session.current_ask_capture = {}
    session.session_metrics = {}
    session.live_session = MagicMock()
    session.live_session.send_realtime_input = AsyncMock()
    session.ask_audio_activity_open = True
    session.gemini_send_lock = _asyncio.Lock()

    ws = AsyncMock()
    await runtime._capture_private_ask_audio(
        session=session, websocket=ws,
        payload={"started_at_ms": 0, "timestamp_ms": 0},
        chunk=b"\x00" * 1024, now=0.0,
    )
    assert session.live_session.send_realtime_input.call_count == 1
    # Audio kwarg used (not activity_start / activity_end)
    kwargs = session.live_session.send_realtime_input.call_args.kwargs
    assert "audio" in kwargs
    assert session.question_capture_bytes == b"\x00" * 1024  # still buffered for text fallback


@pytest.mark.asyncio
async def test_deepgram_session_rebuilds_client_when_language_changes(monkeypatch):
    """Switching languages mid-session tears down the old client and starts a new one."""
    from app.services.deepgram_stream import DeepgramStreamSession

    started_with = []
    stopped = []

    class FakeClient:
        def __init__(self, *_, language, **__):
            self.language = language
            started_with.append(language)

        async def start(self):
            return None

        async def stop(self):
            stopped.append(self.language)

        def push_pcm(self, _b):
            return None

    monkeypatch.setattr("app.services.deepgram_stream.DeepgramLiveClient", FakeClient)
    sess = DeepgramStreamSession("sess-test", "dg-key")
    sess.register_callback("local_mic", AsyncMock())

    await sess.push("local_mic", b"\x00" * 10, language="multi")
    await sess.push("local_mic", b"\x00" * 10, language="multi")  # same → no rebuild
    await sess.push("local_mic", b"\x00" * 10, language="gu-IN")  # change → rebuild

    assert started_with == ["multi", "gu-IN"]
    assert stopped == ["multi"]
    await sess.stop_all()
