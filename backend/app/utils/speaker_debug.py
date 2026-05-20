from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)
_write_lock = Lock()


def log_speaker_debug(event: str, **fields: Any) -> None:
    if not getattr(settings, "SPEAKER_DEBUG_LOG_ENABLED", False):
        return

    path = Path(settings.SPEAKER_DEBUG_LOG_PATH)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        payload = " | ".join(
            f"{key}={_format_value(value)}"
            for key, value in fields.items()
            if value is not None
        )
        line = f"{timestamp} | {event}"
        if payload:
            line = f"{line} | {payload}"
        with _write_lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except Exception:
        logger.debug("Failed to write speaker debug log", exc_info=True)


def _format_value(value: Any) -> str:
    if isinstance(value, str):
        compact = " ".join(value.split())
        if len(compact) > 220:
            compact = compact[:217] + "..."
        return json.dumps(compact, ensure_ascii=False)
    if isinstance(value, (list, dict, tuple)):
        text = json.dumps(value, ensure_ascii=False, default=str)
        if len(text) > 400:
            text = text[:397] + "..."
        return text
    return str(value)
