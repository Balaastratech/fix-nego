"""App-session JWT service.

Mints and verifies our OWN short-lived access tokens and long-lived refresh
tokens (HS256, signed with ``JWT_SECRET_KEY``). These are entirely separate from
the Clerk tokens — after a one-time Clerk verification we hand out our own tokens
so the desktop never has to deal with Clerk's 60-second session-token TTL.

Refresh token records live in the ``refresh_tokens`` DB table (managed by
``app.services.auth_db``) for rotation and revocation support.

Token shapes
------------
Access token payload:
    { "sub": clerk_sub, "email": email, "type": "access",
      "iat": ..., "exp": ... }

Refresh token payload:
    { "sub": clerk_sub, "jti": uuid4, "type": "refresh",
      "iat": ..., "exp": ... }
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import TypedDict

from jose import jwt, JWTError

from app.config import settings


class TokenPair(TypedDict):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int  # access token TTL in seconds


class TokenError(Exception):
    """Raised when a token is invalid, expired, or has the wrong type."""


def _secret() -> str:
    secret = (settings.JWT_SECRET_KEY or "").strip()
    if not secret:
        raise RuntimeError(
            "JWT_SECRET_KEY is not configured. Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    return secret


def _now() -> datetime:
    return datetime.now(timezone.utc)


def make_access_token(clerk_sub: str, email: str) -> str:
    """Mint a short-lived access token for a verified user."""
    ttl = settings.JWT_ACCESS_TTL_MINUTES
    now = _now()
    payload = {
        "sub": clerk_sub,
        "email": email,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=ttl),
    }
    return jwt.encode(payload, _secret(), algorithm=settings.JWT_ALGORITHM)


def make_refresh_token(clerk_sub: str) -> tuple[str, str, datetime]:
    """Mint a long-lived refresh token.

    Returns ``(raw_token, jti, expires_at)`` so the caller can persist the
    ``jti`` + ``expires_at`` in the ``refresh_tokens`` table.
    """
    jti = str(uuid.uuid4())
    ttl_days = settings.JWT_REFRESH_TTL_DAYS
    now = _now()
    expires_at = now + timedelta(days=ttl_days)
    payload = {
        "sub": clerk_sub,
        "jti": jti,
        "type": "refresh",
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, _secret(), algorithm=settings.JWT_ALGORITHM)
    return token, jti, expires_at


def verify_access_token(raw_token: str) -> dict:
    """Decode and verify an access token. Returns the payload dict."""
    try:
        payload = jwt.decode(
            raw_token,
            _secret(),
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise TokenError(f"Invalid access token: {exc}") from exc

    if payload.get("type") != "access":
        raise TokenError("Token is not an access token")
    return payload


def verify_refresh_token(raw_token: str) -> dict:
    """Decode and verify a refresh token. Returns the payload dict."""
    try:
        payload = jwt.decode(
            raw_token,
            _secret(),
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise TokenError(f"Invalid refresh token: {exc}") from exc

    if payload.get("type") != "refresh":
        raise TokenError("Token is not a refresh token")
    return payload


def make_token_pair(clerk_sub: str, email: str) -> tuple[TokenPair, str, datetime]:
    """Convenience: mint both tokens at once.

    Returns ``(TokenPair, refresh_jti, refresh_expires_at)`` so callers can
    persist the jti in a single call.
    """
    access = make_access_token(clerk_sub, email)
    refresh, jti, expires_at = make_refresh_token(clerk_sub)
    pair: TokenPair = {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": settings.JWT_ACCESS_TTL_MINUTES * 60,
    }
    return pair, jti, expires_at
