"""Database helpers for the auth system (users + refresh_tokens tables).

Reuses the same sqlite3 DB file and SessionStore lock as the rest of the
persistence layer — no second connection pool, no ORM.  All writes are
parameterized to prevent SQL injection.

Call ``auth_db.initialize(db_path)`` once at startup (done implicitly via
``session_store.initialize()`` which creates the tables, then ``auth_db``
gets the path so it can open its own connections with the same WAL file).
"""

from __future__ import annotations

import sqlite3
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

_db_path: Path | None = None
_lock = threading.Lock()


def configure(db_path: str | Path) -> None:
    """Point this module at the shared DB file. Called from app startup."""
    global _db_path
    _db_path = Path(db_path)


def _connect() -> sqlite3.Connection:
    global _db_path
    if _db_path is None:
        # Lazy-configure from settings when configure() wasn't called explicitly
        # (e.g. in tests that don't go through the startup lifespan).
        from app.config import settings
        _db_path = Path(settings.SESSION_DB_PATH)
        _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── Users ──────────────────────────────────────────────────────────────────────

def upsert_user(clerk_sub: str, email: str, email_verified: bool) -> None:
    """Insert or update the user record. Updates last_login_at on every call."""
    now = time.time()
    with _lock, _connect() as conn:
        conn.execute(
            """
            INSERT INTO users (clerk_sub, email, email_verified, created_at, last_login_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(clerk_sub) DO UPDATE SET
                email          = excluded.email,
                email_verified = excluded.email_verified,
                last_login_at  = excluded.last_login_at
            """,
            (clerk_sub, email, int(email_verified), now, now),
        )


def get_user(clerk_sub: str) -> dict | None:
    """Return the user row as a dict, or None if not found."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT clerk_sub, email, email_verified, created_at, last_login_at FROM users WHERE clerk_sub = ?",
            (clerk_sub,),
        ).fetchone()
    return dict(row) if row else None


# ── Refresh tokens ─────────────────────────────────────────────────────────────

def store_refresh_token(jti: str, clerk_sub: str, expires_at: datetime) -> None:
    """Persist a newly minted refresh token jti."""
    now = time.time()
    exp_ts = expires_at.timestamp()
    with _lock, _connect() as conn:
        conn.execute(
            """
            INSERT INTO refresh_tokens (jti, clerk_sub, expires_at, revoked, created_at)
            VALUES (?, ?, ?, 0, ?)
            """,
            (jti, clerk_sub, exp_ts, now),
        )


def is_refresh_token_valid(jti: str) -> bool:
    """Return True if the jti exists, is not revoked, and has not expired."""
    now = time.time()
    with _connect() as conn:
        row = conn.execute(
            "SELECT revoked, expires_at FROM refresh_tokens WHERE jti = ?",
            (jti,),
        ).fetchone()
    if not row:
        return False
    return row["revoked"] == 0 and row["expires_at"] > now


def revoke_refresh_token(jti: str) -> None:
    """Mark a refresh token as revoked (logout / rotation)."""
    with _lock, _connect() as conn:
        conn.execute("UPDATE refresh_tokens SET revoked = 1 WHERE jti = ?", (jti,))


def get_refresh_token_sub(jti: str) -> str | None:
    """Return the clerk_sub for a valid (non-revoked, non-expired) jti, or None."""
    now = time.time()
    with _connect() as conn:
        row = conn.execute(
            "SELECT clerk_sub FROM refresh_tokens WHERE jti = ? AND revoked = 0 AND expires_at > ?",
            (jti, now),
        ).fetchone()
    return row["clerk_sub"] if row else None


def purge_expired_tokens() -> int:
    """Delete expired refresh token rows. Returns the number deleted."""
    now = time.time()
    with _lock, _connect() as conn:
        cur = conn.execute("DELETE FROM refresh_tokens WHERE expires_at <= ?", (now,))
    return cur.rowcount
