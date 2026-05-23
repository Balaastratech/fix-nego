"""
Deepgram Live Streaming transcription.

One DeepgramLiveClient per audio source (local_mic / remote_app) per session.
Audio chunks are forwarded in real-time; interim results arrive word-by-word.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# Module-level registry: session_id → DeepgramStreamSession
_SESSIONS: dict[str, "DeepgramStreamSession"] = {}


class DeepgramStreamSession:
    """Manages live streaming connections for one negotiation session."""

    def __init__(self, session_id: str, api_key: str):
        self.session_id = session_id
        self.api_key = api_key
        self._clients: dict[str, DeepgramLiveClient] = {}
        self._callbacks: dict[str, Callable] = {}

    # ── Registry helpers ──────────────────────────────────────────────────────

    @classmethod
    def get_or_create(cls, session_id: str, api_key: str) -> "DeepgramStreamSession":
        if session_id not in _SESSIONS:
            _SESSIONS[session_id] = cls(session_id, api_key)
        return _SESSIONS[session_id]

    @classmethod
    def get(cls, session_id: str) -> Optional["DeepgramStreamSession"]:
        return _SESSIONS.get(session_id)

    @classmethod
    async def destroy(cls, session_id: str) -> None:
        sess = _SESSIONS.pop(session_id, None)
        if sess:
            await sess.stop_all()

    # ── Public API ────────────────────────────────────────────────────────────

    def register_callback(self, source: str, callback: Callable) -> None:
        """Register an async callback(text, is_final, speech_final, confidence) for a source."""
        self._callbacks[source] = callback

    async def push(self, source: str, pcm_bytes: bytes, language: str = "en-US") -> None:
        """Forward a raw PCM chunk to the live stream for this source."""
        # If streaming permanently failed for this source, don't retry
        failed_key = f"_failed_{source}"
        if getattr(self, failed_key, False):
            return

        client = self._clients.get(source)
        if client is None:
            cb = self._callbacks.get(source)
            if not cb:
                return
            client = DeepgramLiveClient(
                api_key=self.api_key,
                source=source,
                on_transcript=cb,
                language=language,
            )
            self._clients[source] = client
            try:
                await client.start()
            except Exception as exc:
                error_str = str(exc)
                logger.warning(
                    "[DGStream:%s] Failed to start source=%s: %s",
                    self.session_id[:8], source, exc,
                )
                self._clients.pop(source, None)
                # HTTP 400/401 = permanent failure (bad key / unsupported params) — stop retrying
                if "400" in error_str or "401" in error_str or "403" in error_str:
                    logger.error(
                        "[DGStream:%s] Permanent failure source=%s (%s) — falling back to batch STT for this session",
                        self.session_id[:8], source, error_str[:80],
                    )
                    setattr(self, failed_key, True)
                return
        client.push_pcm(pcm_bytes)

    async def stop_all(self) -> None:
        clients = list(self._clients.values())
        self._clients.clear()
        await asyncio.gather(*[c.stop() for c in clients], return_exceptions=True)
        logger.info("[DGStream:%s] All streams stopped", self.session_id[:8])


class DeepgramLiveClient:
    """One Deepgram streaming WebSocket for one audio source."""

    WS_URL = "wss://api.deepgram.com/v1/listen"

    def __init__(
        self,
        api_key: str,
        source: str,
        on_transcript: Callable,
        *,
        language: str = "en-US",
        model: str = "nova-3",
        sample_rate: int = 16000,
        endpointing_ms: int = 300,    # finalize 300ms after speech stops
        utterance_end_ms: int = 500,  # shorter wait for final result
    ):
        self.api_key = api_key
        self.source = source
        self.on_transcript = on_transcript
        self.language = language
        self.model = model
        self.sample_rate = sample_rate
        self.endpointing_ms = endpointing_ms
        self.utterance_end_ms = utterance_end_ms

        self._ws: Any = None
        self._recv_task: Optional[asyncio.Task] = None
        self._send_task: Optional[asyncio.Task] = None
        self._send_queue: asyncio.Queue = asyncio.Queue(maxsize=300)
        self._running = False

    def _build_url(self) -> str:
        # Minimal parameter set — vad_events and utterance_end_ms were causing HTTP 400.
        # smart_format=true enables automatic punctuation and number formatting.
        # endpointing controls how long Deepgram waits after speech before finalizing.
        params = [
            ("model", self.model),
            ("encoding", "linear16"),
            ("sample_rate", str(self.sample_rate)),
            ("channels", "1"),
            ("interim_results", "true"),
            ("endpointing", str(self.endpointing_ms)),
            ("smart_format", "true"),
            ("language", self.language),
        ]
        return f"{self.WS_URL}?{urlencode(params)}"

    async def start(self) -> None:
        import websockets
        url = self._build_url()
        logger.info("[DGStream] Connecting to %s", url)  # INFO so URL appears in log for diagnosis
        # websockets 16.x: use async-context-manager form.
        # compression=None is required — Deepgram rejects permessage-deflate (HTTP 400).
        self._ws = await websockets.connect(
            url,
            additional_headers={"Authorization": f"Token {self.api_key}"},
            compression=None,
            open_timeout=10,
        )
        self._running = True
        self._recv_task = asyncio.create_task(
            self._recv_loop(), name=f"dgstream-recv-{self.source}"
        )
        self._send_task = asyncio.create_task(
            self._send_loop(), name=f"dgstream-send-{self.source}"
        )
        logger.info(
            "[DGStream] Started source=%s model=%s lang=%s endpointing=%sms",
            self.source, self.model, self.language, self.endpointing_ms,
        )

    async def stop(self) -> None:
        self._running = False
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
                await asyncio.sleep(0.05)
            except Exception:
                pass
            try:
                await self._ws.close()
            except Exception:
                pass
        tasks = [t for t in [self._recv_task, self._send_task] if t and not t.done()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("[DGStream] Stopped source=%s", self.source)

    def push_pcm(self, pcm_bytes: bytes) -> None:
        """Thread-safe: queue raw PCM bytes for sending.
        If the WS has closed (idle timeout from Deepgram), trigger a reconnect
        so the stream self-heals — e.g. after user holds orb for >10s.
        """
        if not self._running:
            return
        # WS dead — schedule reconnect and drop this chunk (reconnect will resume stream)
        if self._ws is None:
            logger.info("[DGStream] WS dead on push source=%s — scheduling reconnect", self.source)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(self._reconnect(), loop=loop)
            except Exception:
                pass
            return
        try:
            self._send_queue.put_nowait(pcm_bytes)
        except asyncio.QueueFull:
            pass  # Drop oldest implicitly — queue is large enough normally

    async def _reconnect(self) -> None:
        """Restart the WebSocket connection after an idle close."""
        if self._ws is not None:
            return  # already reconnected by another call
        logger.info("[DGStream] Reconnecting source=%s", self.source)
        # Clear dead tasks
        for t in [self._recv_task, self._send_task]:
            if t and not t.done():
                t.cancel()
        self._recv_task = None
        self._send_task = None
        # Clear the send queue so stale audio doesn't play when connection resumes
        while not self._send_queue.empty():
            try:
                self._send_queue.get_nowait()
            except Exception:
                break
        try:
            await self.start()
            logger.info("[DGStream] Reconnected source=%s", self.source)
        except Exception as exc:
            logger.warning("[DGStream] Reconnect failed source=%s: %s", self.source, exc)

    async def _send_loop(self) -> None:
        while self._running:
            try:
                chunk = await asyncio.wait_for(self._send_queue.get(), timeout=0.5)
                if self._ws is not None:
                    await self._ws.send(chunk)
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                if self._running:
                    logger.warning("[DGStream] Send error source=%s: %s", self.source, exc)
                self._ws = None  # mark dead so push_pcm triggers reconnect
                break

    async def _recv_loop(self) -> None:
        while self._running:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
                try:
                    event = json.loads(raw)
                    await self._handle_event(event)
                except Exception as exc:
                    logger.debug("[DGStream] Event parse error source=%s: %s", self.source, exc)
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                if self._running:
                    logger.warning("[DGStream] Recv error source=%s: %s", self.source, exc)
                self._ws = None  # mark dead so push_pcm triggers reconnect
                break

    async def _handle_event(self, event: dict) -> None:
        etype = event.get("type")

        if etype == "Results":
            alts = ((event.get("channel") or {}).get("alternatives") or [])
            if not alts:
                return
            text = (alts[0].get("transcript") or "").strip()
            if not text:
                return
            is_final = bool(event.get("is_final"))
            speech_final = bool(event.get("speech_final"))
            confidence = float(alts[0].get("confidence") or 0.0)
            logger.debug(
                "[DGStream] source=%s is_final=%s speech_final=%s conf=%.2f text=%r",
                self.source, is_final, speech_final, confidence, text[:60],
            )
            await self.on_transcript(text, is_final, speech_final, confidence)

        elif etype == "SpeechStarted":
            logger.debug("[DGStream] SpeechStarted source=%s", self.source)

        elif etype == "UtteranceEnd":
            logger.debug("[DGStream] UtteranceEnd source=%s", self.source)

        elif etype == "Error":
            logger.error("[DGStream] API error source=%s: %s", self.source, event)

        # Metadata / Connected — ignore
