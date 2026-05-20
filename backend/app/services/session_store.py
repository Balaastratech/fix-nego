from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from app.config import settings
from app.models.negotiation import NegotiationSession

logger = logging.getLogger(__name__)


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True, default=str)


class SessionStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        state TEXT NOT NULL,
                        consent_version TEXT,
                        consent_mode TEXT,
                        started_at REAL,
                        updated_at REAL NOT NULL,
                        ended_at REAL,
                        language TEXT,
                        response_language TEXT,
                        context_json TEXT NOT NULL,
                        transcript_json TEXT NOT NULL,
                        speaker_mapping_json TEXT NOT NULL,
                        last_context_json TEXT NOT NULL,
                        research_json TEXT NOT NULL,
                        advisor_json TEXT NOT NULL,
                        vision_json TEXT NOT NULL,
                        metrics_json TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS turns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        turn_id TEXT NOT NULL,
                        speaker TEXT NOT NULL,
                        language TEXT,
                        text TEXT NOT NULL,
                        timestamp_ms INTEGER NOT NULL,
                        source TEXT,
                        diarized_speaker_id TEXT,
                        transcription_confidence REAL,
                        metadata_json TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS research_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        query TEXT NOT NULL,
                        status TEXT NOT NULL,
                        provider TEXT,
                        created_at REAL NOT NULL,
                        payload_json TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS advisor_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        payload_json TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS speaker_mapping_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        payload_json TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS vision_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    """
                )
            self._initialized = True
            logger.info("SessionStore initialized", extra={"db_path": str(self.db_path)})

    def persist_session(self, session: NegotiationSession, *, ended: bool = False) -> None:
        self.initialize()
        now = time.time()
        transcript = list(session.display_transcript_turns)[-settings.TRANSCRIPT_HISTORY_LIMIT :]
        research_history = list(session.research_history)[-settings.RESEARCH_HISTORY_LIMIT :]
        advisor_history = list(session.advisor_history)[-settings.RESEARCH_HISTORY_LIMIT :]
        vision_history = list(session.vision_history)[-settings.RESEARCH_HISTORY_LIMIT :]
        context_payload = {
            "user_context": session.user_context,
            "last_context": getattr(session.listener_agent, "last_context", {}) if session.listener_agent else {},
            "degraded_mode": session.degraded_mode,
            "source_mode": session.source_mode,
            "meeting_binding": session.meeting_binding,
            "audio_sources_active": session.audio_sources_active,
            "hold_state": session.hold_state,
            "capture_health": session.capture_health,
            "capture_preset": session.capture_preset,
            "companion_quality_mode": session.companion_quality_mode,
            "selected_output_device": {
                "device_id": session.selected_output_device_id,
                "label": session.selected_output_device_label,
            },
            "degraded_reasons": list(session.degraded_reasons),
        }

        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, state, consent_version, consent_mode, started_at, updated_at, ended_at,
                    language, response_language, context_json, transcript_json, speaker_mapping_json,
                    last_context_json, research_json, advisor_json, vision_json, metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    state=excluded.state,
                    consent_version=excluded.consent_version,
                    consent_mode=excluded.consent_mode,
                    started_at=excluded.started_at,
                    updated_at=excluded.updated_at,
                    ended_at=excluded.ended_at,
                    language=excluded.language,
                    response_language=excluded.response_language,
                    context_json=excluded.context_json,
                    transcript_json=excluded.transcript_json,
                    speaker_mapping_json=excluded.speaker_mapping_json,
                    last_context_json=excluded.last_context_json,
                    research_json=excluded.research_json,
                    advisor_json=excluded.advisor_json,
                    vision_json=excluded.vision_json,
                    metrics_json=excluded.metrics_json
                """,
                (
                    session.session_id,
                    session.state.value,
                    session.consent_version,
                    session.consent_mode,
                    session.started_at,
                    now,
                    now if ended else None,
                    session.language,
                    session.response_language,
                    _json_dumps(context_payload),
                    _json_dumps(transcript),
                    _json_dumps(session.speaker_mapping),
                    _json_dumps(getattr(session.listener_agent, "last_context", {}) if session.listener_agent else {}),
                    _json_dumps(research_history),
                    _json_dumps(advisor_history),
                    _json_dumps(vision_history),
                    _json_dumps(session.session_metrics),
                ),
            )
        session.last_persisted_at = now

    def record_turn(self, session_id: str, turn: dict[str, Any], *, language: str | None = None) -> None:
        self.initialize()
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO turns (
                    session_id, turn_id, speaker, language, text, timestamp_ms, source,
                    diarized_speaker_id, transcription_confidence, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    turn.get("id") or f"turn_{int(time.time() * 1000)}",
                    turn.get("speaker", "unknown"),
                    language,
                    turn.get("text", ""),
                    int(turn.get("timestamp") or int(time.time() * 1000)),
                    turn.get("source"),
                    turn.get("diarized_speaker_id"),
                    turn.get("transcription_confidence"),
                    _json_dumps(turn),
                ),
            )

    def record_research_event(self, session_id: str, query: str, status: str, payload: dict[str, Any]) -> None:
        self.initialize()
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO research_events (session_id, query, status, provider, created_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    query,
                    status,
                    payload.get("provider"),
                    time.time(),
                    _json_dumps(payload),
                ),
            )

    def record_advisor_event(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.initialize()
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO advisor_events (session_id, event_type, created_at, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, event_type, time.time(), _json_dumps(payload)),
            )

    def record_speaker_mapping_event(self, session_id: str, payload: dict[str, Any]) -> None:
        self.initialize()
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO speaker_mapping_events (session_id, created_at, payload_json)
                VALUES (?, ?, ?)
                """,
                (session_id, time.time(), _json_dumps(payload)),
            )

    def record_vision_event(self, session_id: str, payload: dict[str, Any]) -> None:
        self.initialize()
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO vision_events (session_id, created_at, payload_json)
                VALUES (?, ?, ?)
                """,
                (session_id, time.time(), _json_dumps(payload)),
            )

    def load_session_bundle(self, session_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            session_row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if session_row is None:
                return None

            turns = conn.execute(
                "SELECT metadata_json FROM turns WHERE session_id = ? ORDER BY id ASC LIMIT ?",
                (session_id, settings.TRANSCRIPT_HISTORY_LIMIT),
            ).fetchall()
            research_rows = conn.execute(
                "SELECT payload_json FROM research_events WHERE session_id = ? ORDER BY id ASC LIMIT ?",
                (session_id, settings.RESEARCH_HISTORY_LIMIT),
            ).fetchall()
            advisor_rows = conn.execute(
                "SELECT payload_json FROM advisor_events WHERE session_id = ? ORDER BY id ASC LIMIT ?",
                (session_id, settings.RESEARCH_HISTORY_LIMIT),
            ).fetchall()
            vision_rows = conn.execute(
                "SELECT payload_json FROM vision_events WHERE session_id = ? ORDER BY id ASC LIMIT ?",
                (session_id, settings.RESEARCH_HISTORY_LIMIT),
            ).fetchall()

        return {
            "session_id": session_row["session_id"],
            "state": session_row["state"],
            "consent_version": session_row["consent_version"],
            "consent_mode": session_row["consent_mode"],
            "started_at": session_row["started_at"],
            "updated_at": session_row["updated_at"],
            "ended_at": session_row["ended_at"],
            "language": session_row["language"],
            "response_language": session_row["response_language"],
            "context": json.loads(session_row["context_json"] or "{}"),
            "transcript": json.loads(session_row["transcript_json"] or "[]"),
            "speaker_mapping": json.loads(session_row["speaker_mapping_json"] or "{}"),
            "last_context": json.loads(session_row["last_context_json"] or "{}"),
            "research": json.loads(session_row["research_json"] or "[]"),
            "advisor": json.loads(session_row["advisor_json"] or "[]"),
            "vision": json.loads(session_row["vision_json"] or "[]"),
            "metrics": json.loads(session_row["metrics_json"] or "{}"),
            "turns": [json.loads(row["metadata_json"]) for row in turns],
            "research_events": [json.loads(row["payload_json"]) for row in research_rows],
            "advisor_events": [json.loads(row["payload_json"]) for row in advisor_rows],
            "vision_events": [json.loads(row["payload_json"]) for row in vision_rows],
        }

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        self.initialize()
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT session_id, state, started_at, updated_at, ended_at, language, response_language
                , context_json
                FROM sessions
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        sessions: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            context = json.loads(payload.pop("context_json") or "{}")
            payload["source_mode"] = context.get("source_mode")
            payload["meeting_binding"] = context.get("meeting_binding") or {}
            sessions.append(payload)
        return sessions


session_store = SessionStore(settings.SESSION_DB_PATH)
