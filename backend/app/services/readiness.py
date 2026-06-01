"""Backend readiness tracking.

The server accepts websocket connections immediately, but the AI capability
probes (STT / SpeechBrain) run in the background at startup and take a couple of
seconds. Until those finish we are NOT safe to start a session — doing so races
the probes and can fail. This module is the single source of truth for "is the
backend actually ready to start a session yet?".

It exposes:
  * ``readiness.is_ready``      — bool snapshot, safe to read from any thread
  * ``readiness.status_message``— a plain-language string for the UI
  * ``readiness.snapshot()``    — dict for sending over the wire
  * ``await readiness.wait()``  — resolves once the backend becomes ready
  * ``readiness.mark_ready(...)`` — called once when startup probes complete
"""

from __future__ import annotations

import asyncio
from typing import Optional

# Plain-language messages the UI shows the user (no developer jargon).
PENDING_MESSAGE = "Connecting to AI services… please wait."
READY_MESSAGE = "AI services ready — you can start a session."


class BackendReadiness:
    def __init__(self) -> None:
        self._ready = False
        self._event: Optional[asyncio.Event] = None
        self._detail: dict = {}

    def _event_for_loop(self) -> asyncio.Event:
        # Create the asyncio.Event lazily so it binds to the running loop the
        # first time a coroutine awaits/sets it (avoids "no running loop" at import).
        if self._event is None:
            self._event = asyncio.Event()
            if self._ready:
                self._event.set()
        return self._event

    def mark_ready(self, detail: Optional[dict] = None) -> None:
        """Flip the backend to ready and wake anyone waiting. Idempotent."""
        self._ready = True
        if detail:
            self._detail = dict(detail)
        if self._event is not None:
            self._event.set()

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def status_message(self) -> str:
        return READY_MESSAGE if self._ready else PENDING_MESSAGE

    def snapshot(self) -> dict:
        return {
            "ready": self._ready,
            "status_message": self.status_message,
            "detail": dict(self._detail),
        }

    async def wait(self) -> None:
        """Resolve as soon as the backend is ready (returns immediately if already ready)."""
        if self._ready:
            return
        await self._event_for_loop().wait()


readiness = BackendReadiness()
