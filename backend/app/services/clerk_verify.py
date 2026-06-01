"""Clerk JWT verification service.

Fetches Clerk's JWKS once, caches it with a 5-minute TTL, and verifies incoming
Clerk session tokens (RS256, signed by Clerk's instance key). Returns the decoded
claims dict on success; raises ``ClerkTokenError`` on any failure.

This module is intentionally stateless (no DB, no FastAPI coupling) so it can be
unit-tested with a fake JWKS without spinning up the full app.

Usage
-----
    from app.services.clerk_verify import verify_clerk_token, ClerkTokenError
    try:
        claims = await verify_clerk_token(raw_jwt)
    except ClerkTokenError as exc:
        raise HTTPException(401, str(exc))
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
from jose import jwt, jwk, JWTError

from app.config import settings

logger = logging.getLogger(__name__)

# In-process JWKS cache: (keys_list, fetched_at_epoch)
_jwks_cache: tuple[list[dict], float] | None = None
_JWKS_TTL = 300  # 5 minutes
_jwks_lock = asyncio.Lock()


class ClerkTokenError(Exception):
    """Raised when a Clerk JWT is invalid, expired, or fails verification."""


async def _fetch_jwks() -> list[dict]:
    """Fetch Clerk's JWKS, refreshing the cache when stale."""
    global _jwks_cache
    now = time.monotonic()

    async with _jwks_lock:
        if _jwks_cache and (now - _jwks_cache[1]) < _JWKS_TTL:
            return _jwks_cache[0]

        url = settings.CLERK_JWKS_URL
        if not url:
            raise ClerkTokenError("CLERK_JWKS_URL is not configured")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            raise ClerkTokenError(f"Failed to fetch Clerk JWKS: {exc}") from exc

        keys = data.get("keys", [])
        if not keys:
            raise ClerkTokenError("Clerk JWKS response contained no keys")

        _jwks_cache = (keys, now)
        logger.debug("Clerk JWKS refreshed (%d keys)", len(keys))
        return keys


def _find_key(keys: list[dict], kid: str | None) -> Any:
    """Return the JWK matching the token's kid, or the first key if no kid."""
    if kid:
        for k in keys:
            if k.get("kid") == kid:
                return jwk.construct(k)
    # Fallback: first key (single-key tenancies)
    if keys:
        return jwk.construct(keys[0])
    raise ClerkTokenError("No matching key found in Clerk JWKS")


async def verify_clerk_token(raw_token: str) -> dict:
    """Verify a Clerk session token and return its decoded claims.

    Checks:
    - RS256 signature against Clerk's current JWKS.
    - ``iss`` matches ``CLERK_ISSUER`` (when configured).
    - ``exp`` / ``nbf`` via jose (automatic).
    - ``azp`` matches ``CLERK_AUTHORIZED_PARTY`` (when configured).

    Does NOT check ``email_verified`` — callers must assert that themselves so
    the /exchange endpoint can return a clear error to the desktop.
    """
    if not raw_token:
        raise ClerkTokenError("Empty token")

    # Peek at the header to get the kid, without verifying yet.
    try:
        header = jwt.get_unverified_header(raw_token)
    except JWTError as exc:
        raise ClerkTokenError(f"Cannot decode token header: {exc}") from exc

    kid = header.get("kid")
    keys = await _fetch_jwks()

    # If the kid doesn't match any cached key, force a JWKS refresh (rotation).
    if kid and not any(k.get("kid") == kid for k in keys):
        async with _jwks_lock:
            global _jwks_cache
            _jwks_cache = None
        keys = await _fetch_jwks()

    public_key = _find_key(keys, kid)

    options: dict = {"verify_exp": True, "verify_nbf": True}
    decode_kwargs: dict = {
        "algorithms": ["RS256"],
        "options": options,
    }

    issuer = (settings.CLERK_ISSUER or "").strip()
    if issuer:
        decode_kwargs["issuer"] = issuer

    azp = (settings.CLERK_AUTHORIZED_PARTY or "").strip()

    try:
        claims: dict = jwt.decode(raw_token, public_key, **decode_kwargs)
    except JWTError as exc:
        raise ClerkTokenError(f"Token verification failed: {exc}") from exc

    if azp and claims.get("azp") != azp:
        raise ClerkTokenError(
            f"Token azp '{claims.get('azp')}' does not match CLERK_AUTHORIZED_PARTY"
        )

    return claims


def invalidate_jwks_cache() -> None:
    """Force a JWKS refresh on the next verification (useful for testing)."""
    global _jwks_cache
    _jwks_cache = None
