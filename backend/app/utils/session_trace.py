from __future__ import annotations

import json
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TRACE_ROOT = Path(__file__).resolve().parents[2] / "data" / "logs" / "session_traces"

_traces: dict[str, "SessionTrace"] = {}
_lock = threading.Lock()


def create_session_trace(session_id: str) -> "SessionTrace":
    with _lock:
        trace = _traces.get(session_id)
        if trace is None:
            trace = SessionTrace(session_id)
            _traces[session_id] = trace
        return trace


def get_session_trace(session_id: str) -> "SessionTrace | None":
    return _traces.get(session_id)


def close_session_trace(session_id: str) -> Path | None:
    with _lock:
        trace = _traces.pop(session_id, None)
    if trace is None:
        return None
    return trace.finalize()


class SessionTrace:
    def __init__(self, session_id: str, root_dir: Path | None = None) -> None:
        self.session_id = session_id
        self.root_dir = Path(root_dir or TRACE_ROOT)
        self.session_dir = self.root_dir / session_id
        self.artifact_dir = self.session_dir / "artifacts"
        self.trace_path = self.session_dir / "trace.jsonl"
        self.report_path = self.session_dir / "report.md"
        self._write_lock = threading.Lock()
        self._start_wall = time.time()
        self._start_perf = time.perf_counter()
        self._events: list[dict[str, Any]] = []
        self._seq = 0
        self.state: dict[str, Any] = {}
        self._finalized = False

        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._bootstrap_from_disk()

    def _bootstrap_from_disk(self) -> None:
        if not self.trace_path.exists():
            return
        try:
            for raw_line in self.trace_path.read_text(encoding="utf-8").splitlines():
                if not raw_line.strip():
                    continue
                event = json.loads(raw_line)
                self._events.append(event)
                self._seq = max(self._seq, int(event.get("seq", 0)))
        except Exception:
            self._events = []
            self._seq = 0

    @staticmethod
    def _json_default(value: Any) -> str:
        return str(value)

    @staticmethod
    def _slug(value: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip().lower())
        return safe.strip("_") or "artifact"

    def _iso_now(self) -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")

    def _elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._start_perf) * 1000)

    def remember(self, key: str, value: Any) -> None:
        self.state[key] = value

    def recall(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def write_text_artifact(self, slug: str, content: str, *, ext: str = ".txt") -> str:
        return self._write_artifact(slug, content.encode("utf-8"), ext=ext)

    def write_json_artifact(self, slug: str, payload: Any, *, ext: str = ".json") -> str:
        data = json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default).encode("utf-8")
        return self._write_artifact(slug, data, ext=ext)

    def write_binary_artifact(self, slug: str, content: bytes, *, ext: str) -> str:
        return self._write_artifact(slug, content, ext=ext)

    def _write_artifact(self, slug: str, content: bytes, *, ext: str) -> str:
        base_slug = self._slug(slug)
        candidate = self.artifact_dir / f"{base_slug}{ext}"
        index = 1
        while candidate.exists():
            index += 1
            candidate = self.artifact_dir / f"{base_slug}_{index}{ext}"
        candidate.write_bytes(content)
        return str(candidate.relative_to(self.session_dir)).replace("\\", "/")

    def record(
        self,
        *,
        category: str,
        name: str,
        summary: str,
        data: dict[str, Any] | None = None,
        artifacts: list[str] | None = None,
        related_event_ids: list[str] | None = None,
        include_in_report: bool = True,
    ) -> dict[str, Any]:
        with self._write_lock:
            self._seq += 1
            event = {
                "event_id": f"evt_{self._seq:05d}",
                "seq": self._seq,
                "session_id": self.session_id,
                "timestamp": self._iso_now(),
                "timestamp_ms": int(time.time() * 1000),
                "elapsed_ms": self._elapsed_ms(),
                "category": category,
                "name": name,
                "summary": summary,
                "data": deepcopy(data or {}),
                "artifacts": list(artifacts or []),
                "related_event_ids": list(related_event_ids or []),
                "include_in_report": include_in_report,
            }
            self.trace_path.parent.mkdir(parents=True, exist_ok=True)
            with self.trace_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, default=self._json_default) + "\n")
            self._events.append(event)
            return event

    def finalize(self) -> Path:
        if self._finalized:
            return self.report_path
        with self._write_lock:
            report_lines = self._build_report_lines()
            self.report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
            self._finalized = True
        return self.report_path

    def _build_report_lines(self) -> list[str]:
        lines = [
            "# Structured Session Trace Report",
            "",
            f"- Session ID: `{self.session_id}`",
            f"- Started At: `{datetime.fromtimestamp(self._start_wall).astimezone().isoformat(timespec='milliseconds')}`",
            f"- Events: `{len(self._events)}`",
            f"- Trace JSONL: `{self.trace_path}`",
            f"- Artifacts: `{self.artifact_dir}`",
            "",
            "## Event Timeline",
            "",
        ]
        for event in self._events:
            if not event.get("include_in_report", True):
                continue
            lines.extend(self._render_event(event))
        return lines

    def _render_event(self, event: dict[str, Any]) -> list[str]:
        header = (
            f"### {event['seq']:04d} | +{event['elapsed_ms']} ms | "
            f"{event['category']}.{event['name']}"
        )
        lines = [
            header,
            "",
            f"- Summary: {event['summary']}",
            f"- Event ID: `{event['event_id']}`",
            f"- Wall Time: `{event['timestamp']}`",
        ]
        if event.get("related_event_ids"):
            refs = ", ".join(f"`{ref}`" for ref in event["related_event_ids"])
            lines.append(f"- Related Events: {refs}")
        if event.get("artifacts"):
            refs = ", ".join(f"`{artifact}`" for artifact in event["artifacts"])
            lines.append(f"- Artifacts: {refs}")
        data = event.get("data") or {}
        if data:
            lines.append("- Data:")
            for key, value in data.items():
                rendered = self._render_value(value)
                lines.append(f"  - {key}: {rendered}")
        lines.append("")
        return lines

    def _render_value(self, value: Any) -> str:
        if isinstance(value, str):
            collapsed = " ".join(value.split())
            if len(collapsed) > 220:
                return f"`{collapsed[:217]}...`"
            return f"`{collapsed}`"
        if isinstance(value, (int, float, bool)) or value is None:
            return f"`{value}`"
        rendered = json.dumps(value, ensure_ascii=False, default=self._json_default)
        if len(rendered) > 220:
            rendered = rendered[:217] + "..."
        return f"`{rendered}`"
