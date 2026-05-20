from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)
_write_lock = Lock()
_recent_lock = Lock()
_recent_events: dict[tuple[str, str, str, str], float] = {}
_DEDUP_WINDOW_SECONDS = 3.0


def log_conversation_event(
    *,
    session_id: str,
    event: str,
    speaker: str,
    text: str,
    timestamp_ms: int | None = None,
    context: str | None = None,
    response_mode: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not getattr(settings, "CONVERSATION_AUDIT_LOG_ENABLED", False):
        return

    cleaned_text = _compact_text(text)
    if not cleaned_text:
        return

    dedupe_key = (session_id, event, speaker, cleaned_text)
    if _is_duplicate(dedupe_key):
        return

    effective_timestamp_ms = int(timestamp_ms or (time.time() * 1000))
    payload: dict[str, Any] = {
        "timestamp": datetime.fromtimestamp(
            effective_timestamp_ms / 1000.0, tz=timezone.utc
        ).astimezone().isoformat(timespec="seconds"),
        "timestamp_ms": effective_timestamp_ms,
        "session_id": session_id,
        "event": event,
        "speaker": speaker,
        "text": cleaned_text,
    }
    if context:
        payload["context"] = context
    if response_mode:
        payload["response_mode"] = response_mode
    if metadata:
        payload["metadata"] = metadata

    path = Path(settings.CONVERSATION_AUDIT_LOG_PATH)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _write_lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        logger.debug("Failed to write conversation audit log", exc_info=True)


def _compact_text(value: str | None) -> str:
    if not value:
        return ""
    compact = " ".join(str(value).split()).strip()
    if len(compact) > 2000:
        return compact[:1997] + "..."
    return compact


def _is_duplicate(key: tuple[str, str, str, str]) -> bool:
    now = time.monotonic()
    with _recent_lock:
        expired = [event_key for event_key, ts in _recent_events.items() if now - ts > _DEDUP_WINDOW_SECONDS]
        for event_key in expired:
            _recent_events.pop(event_key, None)

        previous = _recent_events.get(key)
        if previous is not None and now - previous <= _DEDUP_WINDOW_SECONDS:
            return True

        _recent_events[key] = now
        return False
