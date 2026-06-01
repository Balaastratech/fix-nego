"""REST API for the in-app provider Settings page.

Endpoints (all under /api/providers):
- GET  /registry  → provider metadata + LIVE classified model lists per slot
- POST /refresh   → force re-fetch of all provider model catalogs
- GET  /config    → current per-slot provider/model + per-provider key_status
- PUT  /config    → persist provider/model choices and API keys (hot-applied)
- POST /test       → validate a provider+key with a tiny live ping

API key VALUES are never returned by any endpoint — only present/missing status.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from app.api.auth import get_current_user
from app.providers import model_catalog, registry, runtime_config, text_client

logger = logging.getLogger(__name__)

# Phase C — the provider Settings API can read/write API keys, so it is gated by
# the shared token when one is configured (no-op in dev). The desktop Settings
# page sends the token via the X-Companion-Token header.
router = APIRouter(prefix="/api/providers", tags=["providers"], dependencies=[Depends(get_current_user)])


@router.get("/registry")
async def get_registry():
    """Live, capability-classified model lists per task slot."""
    return await model_catalog.full_registry(force=False)


@router.post("/refresh")
async def refresh_registry():
    """Force a re-fetch of every provider's model catalog (bypasses TTL)."""
    model_catalog.clear_cache()
    return await model_catalog.full_registry(force=True)


@router.get("/config")
async def get_config():
    """Current selections + key presence (never key values)."""
    runtime_config.reload()
    return runtime_config.safe_config()


@router.put("/config")
async def put_config(patch: dict = Body(...)):
    """Persist provider/model choices and/or API keys. Hot-applied.

    Body shape:
      {
        "slots": {"reasoning": {"provider": "anthropic", "model": "claude-haiku-4-5"}},
        "keys":  {"anthropic": "sk-ant-..."}     # "" removes a stored key
      }
    """
    try:
        safe = runtime_config.update(patch)
    except runtime_config.ConfigError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    # Invalidate catalog cache for any provider whose key changed so the next
    # registry read fetches its live model list.
    if patch.get("keys"):
        model_catalog.clear_cache()
    return {
        "config": safe,
        "note": (
            "Vision and advice changes apply immediately. Provider, API key, "
            "Live Voice, and STT changes apply on your next session."
        ),
    }


@router.post("/test")
async def test_provider(payload: dict = Body(...)):
    """Validate a provider+key with a minimal live call.

    Body: {"provider": "anthropic", "key": "sk-...", "model": "claude-haiku-4-5"?}
    If "key" is provided it is tested directly (not persisted). Otherwise the
    stored/env key is used.
    """
    provider = (payload.get("provider") or "").strip()
    if provider not in registry.PROVIDERS:
        return JSONResponse(status_code=400, content={"ok": False, "error": "unknown provider"})

    meta = registry.PROVIDERS[provider]
    test_key = (payload.get("key") or "").strip() or runtime_config.api_key_for(provider)
    if not test_key:
        return {"ok": False, "error": "no API key provided or configured"}

    t0 = time.perf_counter()
    try:
        ok = await _ping_provider(provider, meta, test_key, payload.get("model"))
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": bool(ok), "latency_ms": latency_ms}
    except Exception as exc:  # surface a clean message to the UI
        latency_ms = int((time.perf_counter() - t0) * 1000)
        msg = f"{type(exc).__name__}: {exc}"
        logger.info("provider test failed provider=%s err=%s", provider, msg)
        return {"ok": False, "latency_ms": latency_ms, "error": msg[:300]}


async def _ping_provider(provider: str, meta: dict, key: str, model: str | None) -> bool:
    """Cheapest possible liveness check per provider."""
    import httpx

    # For list-endpoint providers, a models-list GET validates the key cheaply.
    if meta.get("list_endpoint"):
        url = meta["list_endpoint"]
        async with httpx.AsyncClient(timeout=8.0) as client:
            if provider == "google":
                r = await client.get(url, params={"key": key})
            elif provider == "anthropic":
                r = await client.get(url, headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
            elif provider == "deepgram":
                r = await client.get(url, headers={"Authorization": f"Token {key}"})
            else:  # openai-compatible + openrouter
                r = await client.get(url, headers={"Authorization": f"Bearer {key}"})
            return r.status_code == 200

    # AssemblyAI has no list endpoint — probe the account/transcript root.
    if provider == "assemblyai":
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "https://api.assemblyai.com/v2/transcript",
                headers={"Authorization": key},
            )
            # 200 or 400 (bad params) both mean the key authenticated; 401 = bad key.
            return r.status_code != 401

    return False
