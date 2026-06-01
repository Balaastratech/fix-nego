"""Phase C — minimal shared-secret auth for a public/hosted backend.

A single static bearer token (``COMPANION_SHARED_TOKEN``) guards the websocket
and the sensitive REST surface when the backend is exposed on a public IP. This
is deliberately lightweight (no OTP/email/multi-user) because v1 is BYOK + solo
testing behind a firewall + Caddy TLS — the token is the "anyone who finds the
host can't drive your AI" backstop, not a full auth system.

REVERSIBILITY / NO-BREAKAGE CONTRACT
------------------------------------
When ``COMPANION_SHARED_TOKEN`` is EMPTY (the default), every check here is a
no-op → localhost dev and the current shipped behavior are completely
unchanged. Auth only activates once an operator sets the token in the VM's
``backend/.env``.

Transport
---------
- Websocket: token is read from the ``?token=`` query param (Electron/browser
  ``WebSocket`` can't set arbitrary headers, so a query param is the practical
  channel — it travels encrypted under ``wss://`` via Caddy).
- REST: token is read from ``Authorization: Bearer <token>`` or the
  ``X-Companion-Token`` header.

All comparisons use ``hmac.compare_digest`` to avoid timing leaks.
"""

from __future__ import annotations

import hmac
import logging
from dataclasses import dataclass, field

from fastapi import Header, HTTPException, WebSocket

from app.config import settings

logger = logging.getLogger(__name__)


def _configured_token() -> str:
    return (settings.COMPANION_SHARED_TOKEN or "").strip()


def auth_enabled() -> bool:
    """True only when an operator has set a non-empty shared token."""
    return bool(_configured_token())


def token_matches(candidate: str | None) -> bool:
    """Constant-time compare against the configured token.

    Returns True when auth is disabled (empty configured token) so callers stay
    a no-op in dev. Returns False for a missing/blank candidate when auth is on.
    """
    expected = _configured_token()
    if not expected:
        return True
    if not candidate:
        return False
    return hmac.compare_digest(candidate.strip(), expected)


async def require_token(
    authorization: str | None = Header(default=None),
    x_companion_token: str | None = Header(default=None),
) -> None:
    """FastAPI dependency for sensitive REST endpoints.

    No-op when auth is disabled. Otherwise requires a matching token in either
    ``Authorization: Bearer <token>`` or ``X-Companion-Token``.
    """
    if not auth_enabled():
        return

    candidate: str | None = None
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            candidate = parts[1]
        else:
            candidate = authorization
    if not candidate and x_companion_token:
        candidate = x_companion_token

    if not token_matches(candidate):
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


def websocket_token_ok(websocket: WebSocket) -> bool:
    """Validate the ``?token=`` query param for a websocket connection.

    Always True when auth is disabled. Called BEFORE ``websocket.accept()`` so an
    unauthorized client is closed during the handshake.
    """
    if not auth_enabled():
        return True
    return token_matches(websocket.query_params.get("token"))


# ── Per-user identity (Phase auth — Clerk+JWT) ─────────────────────────────────

@dataclass
class AuthUser:
    """Represents the authenticated caller for a request.

    ``is_admin`` is True for the shared-token bypass path (dev / operator).
    """
    clerk_sub: str
    email: str
    is_admin: bool = field(default=False)


_ADMIN_SUB = "__shared_token_admin__"


def _extract_bearer(authorization: str | None, x_companion_token: str | None) -> str | None:
    """Pull the raw token string from whichever auth header is present."""
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        return authorization.strip()
    if x_companion_token:
        return x_companion_token.strip()
    return None


async def get_current_user(
    authorization: str | None = Header(default=None),
    x_companion_token: str | None = Header(default=None),
) -> AuthUser:
    """FastAPI dependency: returns the authenticated user or raises 401.

    Acceptance hierarchy (AUTH_REQUIRED controls strictness):
    1. Valid app access-JWT  → real ``AuthUser`` with clerk_sub + email.
    2. Matching shared token → synthetic admin ``AuthUser`` (dev/operator bypass).
    3. AUTH_REQUIRED=False   → anonymous ``AuthUser`` (open dev mode; no JWT needed).

    When AUTH_REQUIRED=True and neither a valid JWT nor the shared token is
    provided, the request is rejected with HTTP 401.
    """
    raw = _extract_bearer(authorization, x_companion_token)

    # 1. Try to verify as an app JWT first.
    if raw:
        from app.services.app_tokens import verify_access_token, TokenError
        try:
            payload = verify_access_token(raw)
            return AuthUser(
                clerk_sub=payload["sub"],
                email=payload.get("email", ""),
            )
        except TokenError:
            pass  # fall through to shared-token check

    # 2. Shared-token bypass (Phase C admin path).
    if raw and token_matches(raw):
        return AuthUser(clerk_sub=_ADMIN_SUB, email="admin", is_admin=True)

    # 3. Auth not required → open dev mode.
    if not settings.AUTH_REQUIRED:
        return AuthUser(clerk_sub="", email="", is_admin=True)

    raise HTTPException(status_code=401, detail="Authentication required")


def websocket_get_user(websocket: WebSocket) -> AuthUser | None:
    """Extract and verify the caller identity from a WS ``?token=`` param.

    Returns an ``AuthUser`` on success, or ``None`` if auth fails. Must be
    called BEFORE ``websocket.accept()``. Never raises — caller decides to close.

    Acceptance matches ``get_current_user``:
    1. Valid app JWT in ``?token=``.
    2. Matching shared token.
    3. AUTH_REQUIRED=False → anonymous admin (open dev).
    """
    raw = (websocket.query_params.get("token") or "").strip()

    if raw:
        from app.services.app_tokens import verify_access_token, TokenError
        try:
            payload = verify_access_token(raw)
            return AuthUser(clerk_sub=payload["sub"], email=payload.get("email", ""))
        except TokenError:
            pass

    if raw and token_matches(raw):
        return AuthUser(clerk_sub=_ADMIN_SUB, email="admin", is_admin=True)

    if not settings.AUTH_REQUIRED:
        return AuthUser(clerk_sub="", email="", is_admin=True)

    return None
