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

    # Keys whose values deserve a fenced multi-line block instead of an inline
    # backtick render. Used by _render_value to keep transcripts, AI responses,
    # advice text, and document extracts readable in the report.
    _LONG_TEXT_KEYS = {
        "question_text", "response_text", "advice_text",
        "advice_hint", "scene_summary",
        "document_text_preview", "transcript_tail_preview",
        "raw_preview", "user_query_preview",
        "key_facts", "leverage", "tactics", "gap_answer", "price_range",
    }

    # Category → human-readable section header for the Conversation Flow view.
    _CATEGORY_LABELS = {
        "session": "Session lifecycle",
        "overlay": "Overlay / desktop",
        "transcript": "Live transcripts (what we heard)",
        "extraction": "Context extraction (Flash)",
        "research": "Market research",
        "vision": "Vision analysis",
        "ask_ai": "Private ask flow (hold-to-ask)",
        "ai": "Live AI response (Gemini Live)",
        "context": "Listener context",
        "client": "Client surface",
        "error": "Errors",
    }

    def _build_report_lines(self) -> list[str]:
        lines: list[str] = [
            "# Structured Session Trace Report",
            "",
            f"- Session ID: `{self.session_id}`",
            f"- Started At: `{datetime.fromtimestamp(self._start_wall).astimezone().isoformat(timespec='milliseconds')}`",
            f"- Events: `{len(self._events)}`",
            f"- Trace JSONL: `{self.trace_path}`",
            f"- Artifacts: `{self.artifact_dir}`",
            "",
        ]
        # Conversation summary (what user said / what AI heard / what AI replied).
        summary = self._build_conversation_summary()
        if summary:
            lines.extend(["## Conversation Summary", ""])
            lines.extend(summary)
            lines.append("")
        # Per-category counts.
        counts = self._build_event_counts()
        if counts:
            lines.extend(["## Event Counts by Category", ""])
            lines.extend(counts)
            lines.append("")
        # Chronological timeline — every event in time order with full data.
        lines.extend(["## Event Timeline (chronological)", ""])
        for event in self._events:
            if not event.get("include_in_report", True):
                continue
            lines.extend(self._render_event(event))
        return lines

    def _build_event_counts(self) -> list[str]:
        counts: dict[str, int] = {}
        for ev in self._events:
            counts[ev.get("category", "?")] = counts.get(ev.get("category", "?"), 0) + 1
        out: list[str] = []
        for cat in sorted(counts):
            label = self._CATEGORY_LABELS.get(cat, cat)
            out.append(f"- **{cat}** — {counts[cat]} event(s) — _{label}_")
        return out

    def _build_conversation_summary(self) -> list[str]:
        """Linear retelling of the user/AI exchange — easiest section to read."""
        source_rank = {
            "partial": 1,
            "batch_transcription": 2,
            "gemini_live_input": 3,
        }
        def ask_quality_score(data: dict) -> tuple[int, int, int]:
            text = (data.get("question_text") or "").strip()
            src = data.get("source")
            shape = data.get("ask_shape")
            words = len(text.split())
            chars = len(text)
            base = source_rank.get(src, 0)
            if shape == "precise":
                base += 2
            elif shape == "vague":
                base -= 1
            return (base, words, chars)

        best_ask_by_key: dict[str, dict] = {}
        for ev in self._events:
            if ev.get("category") != "ask_ai" or ev.get("name") != "question_text_ready":
                continue
            data = ev.get("data") or {}
            question_text = (data.get("question_text") or "").strip()
            if not question_text:
                continue
            ask_key = data.get("ask_entry_id") or ev.get("event_id")
            current_best = best_ask_by_key.get(ask_key)
            if current_best is None:
                best_ask_by_key[ask_key] = ev
                continue
            current_score = ask_quality_score(current_best.get("data") or {})
            next_score = ask_quality_score(data)
            if next_score >= current_score:
                best_ask_by_key[ask_key] = ev

        out: list[str] = []
        for ev in self._events:
            cat = ev.get("category")
            name = ev.get("name")
            data = ev.get("data") or {}
            elapsed = ev.get("elapsed_ms", 0)
            if cat == "transcript" and name == "stream_transcript_final":
                speaker = data.get("speaker", "?").upper()
                text = (data.get("text") or "").strip()
                if not text:
                    continue
                conf = data.get("confidence")
                stt = data.get("stt") or {}
                attr = ""
                if stt.get("provider") or stt.get("model"):
                    attr = f" _[{stt.get('provider','?')}/{stt.get('model','?')}"
                    if stt.get("language"):
                        attr += f", {stt['language']}"
                    attr += "]_"
                conf_str = f" (conf {conf})" if conf is not None else ""
                out.append(f"- **+{elapsed}ms** — _{speaker} heard_{attr}{conf_str}: {self._fence_inline(text)}")
            elif cat == "ask_ai" and name == "question_text_ready":
                ask_key = data.get("ask_entry_id") or ev.get("event_id")
                best_event = best_ask_by_key.get(ask_key)
                if best_event is not ev:
                    continue
                qt = (data.get("question_text") or "").strip()
                if qt:
                    shape = data.get("ask_shape", "?")
                    src = data.get("source", "?")
                    out.append(f"- **+{elapsed}ms** — _USER asked_ (shape={shape}, via {src}): {self._fence_inline(qt)}")
            elif cat == "ask_ai" and name == "pro_advice_completed":
                txt = (data.get("advice_text") or "").strip()
                if txt:
                    lat = data.get("latency_ms")
                    out.append(f"- **+{elapsed}ms** — _Pro pre-flight advice_ (Pro, {lat}ms): {self._fence_inline(txt)}")
            elif cat == "ai" and name == "ai_response_completed":
                txt = (data.get("response_text") or "").strip()
                if txt:
                    ctx = data.get("context", "?")
                    h2r = data.get("hold_to_response_ms")
                    h2r_str = f", hold→answer {h2r}ms" if h2r else ""
                    out.append(f"- **+{elapsed}ms** — _AI spoke_ (context={ctx}{h2r_str}): {self._fence_inline(txt)}")
            elif cat == "vision" and name == "vision_analysis_completed":
                scene = data.get("scene_type", "?")
                hint = (data.get("advice_hint") or "").strip()
                lat = data.get("latency_ms")
                if hint:
                    out.append(
                        f"- **+{elapsed}ms** — _Vision saw_ scene=`{scene}` ({lat}ms): "
                        f"{self._fence_inline(hint)}"
                    )
        return out

    def _fence_inline(self, text: str) -> str:
        flat = " ".join(text.split())
        if len(flat) > 320:
            flat = flat[:317] + "…"
        # Escape backticks so markdown rendering is safe.
        return f"`{flat.replace('`', '´')}`"

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
                if key in self._LONG_TEXT_KEYS and isinstance(value, str) and value:
                    lines.append(f"  - {key}:")
                    lines.append("    ```")
                    for ln in value.splitlines() or [value]:
                        lines.append(f"    {ln}")
                    lines.append("    ```")
                else:
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
