from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from fastapi import WebSocket

from app.config import settings
from app.models.negotiation import NegotiationSession
from app.services.session_store import session_store
from app.utils.session_trace import close_session_trace, get_session_trace

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks active and temporarily suspended live sessions."""

    def __init__(self) -> None:
        self.active_connections: Dict[str, Dict[str, Any]] = {}
        self.suspended_sessions: Dict[str, Dict[str, Any]] = {}

    async def register(
        self,
        websocket: WebSocket,
        session_id: str,
        session: NegotiationSession,
    ) -> None:
        suspended = self.suspended_sessions.pop(session_id, None)
        if suspended:
            cleanup_task = suspended.get("cleanup_task")
            if cleanup_task:
                cleanup_task.cancel()
        self.active_connections[session_id] = {"websocket": websocket, "session": session}
        logger.info("Registered connection", extra={"session_id": session_id})

    async def unregister(self, session_id: str, preserve_runtime: bool = False) -> None:
        connection_data = self.active_connections.pop(session_id, None)
        if connection_data is None:
            logger.warning("Attempted to unregister non-existent session", extra={"session_id": session_id})
            return

        session: NegotiationSession = connection_data["session"]
        session_store.persist_session(session, ended=False)

        if preserve_runtime and session.state.value == "ACTIVE" and session.session_resumable:
            trace = get_session_trace(session_id)
            if trace:
                trace.record(
                    category="session",
                    name="session_suspended",
                    summary="Session runtime preserved for reconnect grace period",
                    data={"state": session.state.value},
                )
            cleanup_task = asyncio.create_task(self._cleanup_after_grace(session_id, session))
            self.suspended_sessions[session_id] = {
                "session": session,
                "cleanup_task": cleanup_task,
                "suspended_at": time.time(),
            }
            logger.info("Suspended active session for resume", extra={"session_id": session_id})
            return

        await self._finalize_session_cleanup(session)
        logger.info("Unregistered session", extra={"session_id": session_id})

    async def _cleanup_after_grace(self, session_id: str, session: NegotiationSession) -> None:
        try:
            await asyncio.sleep(settings.SESSION_RESUME_GRACE_SECONDS)
        except asyncio.CancelledError:
            return

        self.suspended_sessions.pop(session_id, None)
        await self._finalize_session_cleanup(session)
        logger.info("Expired suspended session after grace period", extra={"session_id": session_id})

    async def _finalize_session_cleanup(self, session: NegotiationSession) -> None:
        if session.listener_agent is not None:
            try:
                await session.listener_agent.stop()
            except Exception as exc:
                logger.error("Error stopping listener agent", extra={"session_id": session.session_id, "error": str(exc)})
            finally:
                session.listener_agent = None

        if session.live_session is not None:
            try:
                await self._close_gemini_session(session)
            except Exception as exc:
                logger.error("Error closing Gemini session", extra={"session_id": session.session_id, "error": str(exc)})

        for task_attr in (
            "live_session_receive_task",
            "live_session_keepalive_task",
            "live_session_monitor_task",
            "live_reconnect_task",
            "live_preconnect_task",
        ):
            task = getattr(session, task_attr, None)
            if task:
                task.cancel()
                setattr(session, task_attr, None)

        session_store.persist_session(session, ended=session.state.value == "IDLE")
        # Copy direct attributes into session_metrics so session_ended footer is accurate.
        # vision_pro_call_count is stored as a direct attribute on the model, not in the dict.
        metrics = getattr(session, "session_metrics", {})
        metrics["vision_pro_call_count"] = getattr(session, "vision_pro_call_count", 0)
        trace = get_session_trace(session.session_id)
        if trace:
            trace.record(
                category="session",
                name="session_finalized",
                summary="Session cleanup finalized and report generation starting",
                data={
                    "state": session.state.value,
                    "metrics": metrics,
                },
            )
        logger.info("Session summary", extra={"session_id": session.session_id, **metrics})
        from app.utils.session_logger import close_session_logger
        from app.utils.session_logger import get_session_logger as _gsl
        _sl = _gsl(session.session_id)
        if _sl:
            _sl.session_ended(stats=metrics)
        close_session_logger(session.session_id)
        report_path = close_session_trace(session.session_id)
        if report_path is not None:
            session.trace_report_path = str(report_path)

    async def _close_gemini_session(self, session: NegotiationSession) -> None:
        if session.live_session is None and session.live_session_cm is None:
            return
        try:
            if session.live_session_cm is not None:
                await session.live_session_cm.__aexit__(None, None, None)
            elif hasattr(session.live_session, "close"):
                await session.live_session.close()
            elif hasattr(session.live_session, "aio") and hasattr(session.live_session.aio, "close"):
                await session.live_session.aio.close()
            logger.info("Closed Gemini session", extra={"session_id": session.session_id})
        except Exception as exc:
            logger.warning("Error during Gemini session close", extra={"session_id": session.session_id, "error": str(exc)})
        finally:
            session.live_session = None
            session.live_session_cm = None

    def get_session(self, session_id: str) -> Optional[NegotiationSession]:
        connection_data = self.active_connections.get(session_id)
        if connection_data:
            return connection_data["session"]
        suspended = self.suspended_sessions.get(session_id)
        if suspended:
            return suspended["session"]
        return None

    def get_websocket(self, session_id: str) -> Optional[WebSocket]:
        connection_data = self.active_connections.get(session_id)
        if connection_data:
            return connection_data["websocket"]
        return None

    def get_all_sessions(self) -> Dict[str, NegotiationSession]:
        sessions = {sid: data["session"] for sid, data in self.active_connections.items()}
        for sid, data in self.suspended_sessions.items():
            sessions.setdefault(sid, data["session"])
        return sessions

    @property
    def active_session_count(self) -> int:
        return len(self.active_connections)


connection_manager = ConnectionManager()
