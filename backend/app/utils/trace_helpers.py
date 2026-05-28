"""Helpers for emitting rich, never-raising trace events.

Used by gemini_client / listener_agent / negotiation_engine / next_move_cache
to make every AI call self-describing in the session trace:

    with TraceTimer(session, category="ask_ai", name="pro_advice") as t:
        result = await do_pro_call()
        t.complete(data={"text": result, "model": model_block(...)})

Design principles:
- ALL helpers swallow exceptions. Tracing must never break the runtime path.
- Every meaningful AI call ends with a *_completed or *_failed event so
  the report shows the result, not just the trigger.
- Latency is wall-clock measured by the helper; callers don't roll their own.
- The 'model' block has a uniform shape so the report renderer can format it.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


def model_block(
    name: str,
    *,
    route: str | None = None,
    timeout_s: float | None = None,
    purpose: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Uniform attribution block for any model invocation.

    Keep keys stable — the report renderer surfaces them in a consistent order.
    """
    out: dict[str, Any] = {"name": name}
    if route:
        out["route"] = route
    if purpose:
        out["purpose"] = purpose
    if timeout_s is not None:
        out["timeout_s"] = timeout_s
    if temperature is not None:
        out["temperature"] = temperature
    if max_tokens is not None:
        out["max_tokens"] = max_tokens
    return out


def model_route() -> str:
    """Return 'vertex' or 'api' based on settings — used by model_block callers."""
    try:
        from app.config import settings
        return "vertex" if settings.GOOGLE_GENAI_USE_VERTEXAI else "api"
    except Exception:
        return "api"


def safe_record(session_id: str, **record_kwargs: Any) -> Optional[dict]:
    """trace.record() that never raises and is a no-op if no trace exists."""
    try:
        from app.utils.session_trace import get_session_trace
        trace = get_session_trace(session_id)
        if trace is None:
            return None
        return trace.record(**record_kwargs)
    except Exception:
        logger.debug("[trace_helpers] safe_record failed", exc_info=True)
        return None


def text_preview(text: str | None, limit: int = 400) -> str:
    """Return a single-line truncated preview suitable for the trace 'data' field."""
    if not text:
        return ""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1] + "…"


def extract_token_usage(response: Any) -> dict[str, Any]:
    """Best-effort token usage extraction from a Gemini response object."""
    out: dict[str, Any] = {}
    try:
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            return out
        for src, dst in (
            ("prompt_token_count", "prompt_tokens"),
            ("candidates_token_count", "candidates_tokens"),
            ("thoughts_token_count", "thoughts_tokens"),
            ("total_token_count", "total_tokens"),
            ("cached_content_token_count", "cached_tokens"),
        ):
            val = getattr(usage, src, None)
            if val is not None:
                out[dst] = val
    except Exception:
        pass
    return out


def finish_reason(response: Any) -> str | None:
    try:
        cands = getattr(response, "candidates", None) or []
        if cands:
            return str(getattr(cands[0], "finish_reason", None) or "") or None
    except Exception:
        return None
    return None


class TraceTimer:
    """Context manager that emits started/completed/failed events with latency.

    Usage:
        with TraceTimer(session_id, category="ask_ai", name="pro_advice",
                        summary="Pro pre-flight reasoning",
                        started_data={"model": model_block(...)}) as t:
            text = await do_call()
            t.complete(summary="Pro pre-flight returned", data={
                "text_preview": text_preview(text),
                "chars": len(text or ""),
            })

    If the with-block raises, a *_failed event is emitted automatically with
    the exception type. The original exception is NOT swallowed (it propagates).
    Call t.fail(reason=...) to record a non-exception failure (timeout, empty).
    """

    def __init__(
        self,
        session_id: str,
        *,
        category: str,
        name: str,
        summary: str = "",
        started_data: dict | None = None,
        artifacts: list[str] | None = None,
        related_event_ids: list[str] | None = None,
        emit_started: bool = True,
    ) -> None:
        self.session_id = session_id
        self.category = category
        self.name = name
        self.summary = summary
        self._started_data = dict(started_data or {})
        self._artifacts = list(artifacts or [])
        self._related = list(related_event_ids or [])
        self._emit_started = emit_started
        self._t0 = 0.0
        self._closed = False
        self.started_event_id: Optional[str] = None
        self.completed_event_id: Optional[str] = None

    def __enter__(self) -> "TraceTimer":
        self._t0 = time.perf_counter()
        if self._emit_started:
            ev = safe_record(
                self.session_id,
                category=self.category,
                name=f"{self.name}_started",
                summary=self.summary or f"{self.name} started",
                data=self._started_data,
                artifacts=self._artifacts,
                related_event_ids=self._related,
            )
            if ev:
                self.started_event_id = ev.get("event_id")
        return self

    def _latency_ms(self) -> int:
        return int((time.perf_counter() - self._t0) * 1000)

    def complete(
        self,
        *,
        summary: str | None = None,
        data: dict | None = None,
        artifacts: list[str] | None = None,
    ) -> None:
        if self._closed:
            return
        self._closed = True
        payload = dict(data or {})
        payload.setdefault("latency_ms", self._latency_ms())
        related = list(self._related)
        if self.started_event_id:
            related.append(self.started_event_id)
        all_artifacts = list(self._artifacts) + list(artifacts or [])
        ev = safe_record(
            self.session_id,
            category=self.category,
            name=f"{self.name}_completed",
            summary=summary or self.summary or f"{self.name} completed",
            data=payload,
            artifacts=all_artifacts,
            related_event_ids=related,
        )
        if ev:
            self.completed_event_id = ev.get("event_id")

    def fail(
        self,
        *,
        reason: str,
        summary: str | None = None,
        data: dict | None = None,
        artifacts: list[str] | None = None,
    ) -> None:
        if self._closed:
            return
        self._closed = True
        payload = dict(data or {})
        payload.setdefault("latency_ms", self._latency_ms())
        payload.setdefault("reason", reason)
        related = list(self._related)
        if self.started_event_id:
            related.append(self.started_event_id)
        all_artifacts = list(self._artifacts) + list(artifacts or [])
        safe_record(
            self.session_id,
            category=self.category,
            name=f"{self.name}_failed",
            summary=summary or self.summary or f"{self.name} failed",
            data=payload,
            artifacts=all_artifacts,
            related_event_ids=related,
        )

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if not self._closed:
            if exc_type is None:
                # Caller forgot to call complete(); still emit one so the
                # report shows latency.
                self.complete(summary=self.summary or f"{self.name} completed")
            else:
                self.fail(
                    reason=f"{exc_type.__name__}: {exc_val}",
                    summary=self.summary or f"{self.name} raised",
                )
        # Do not suppress exceptions.
        return None
