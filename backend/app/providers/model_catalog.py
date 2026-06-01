"""Live model discovery.

Fetches each provider's OWN model-list API, classifies every returned model into
the task slots it can accurately serve, caches the result (TTL + key-hash), and
falls back to the curated registry list only when a live fetch is unavailable.

This is what makes the Settings dropdowns reflect each provider's CURRENT catalog
— if Google/OpenAI/etc. add or drop a model, it appears/disappears on the next
fetch (or an explicit refresh) with no code change.

Network failures never raise to the caller: they degrade to the curated fallback
list and mark source="fallback" so the UI can show an "offline list" hint.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

import httpx

from app.providers import registry
from app.providers import runtime_config

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 3600.0
_FETCH_TIMEOUT = 8.0

# provider -> {"key_hash": str, "at": float, "models": {model_id: set[slot]}}
_cache: dict[str, dict[str, Any]] = {}
_locks: dict[str, asyncio.Lock] = {}


def _key_hash(key: str) -> str:
    return hashlib.sha256((key or "").encode("utf-8")).hexdigest()[:16]


def _lock_for(provider: str) -> asyncio.Lock:
    lock = _locks.get(provider)
    if lock is None:
        lock = asyncio.Lock()
        _locks[provider] = lock
    return lock


# ── Per-provider fetch + classify ─────────────────────────────────────────────

async def _fetch_models(provider: str, client: httpx.AsyncClient) -> dict[str, set[str]]:
    """Return {model_id: set(slots)} from the provider's live list endpoint."""
    meta = registry.provider_meta(provider)
    if not meta or not meta.get("list_endpoint"):
        return {}
    key = runtime_config.api_key_for(provider)
    if not key:
        return {}
    url = meta["list_endpoint"]

    if provider == "google":
        resp = await client.get(url, params={"key": key})
        resp.raise_for_status()
        out: dict[str, set[str]] = {}
        for m in resp.json().get("models", []):
            name = (m.get("name") or "").split("/")[-1]
            if not name:
                continue
            slots = registry.classify_google(name, m.get("supportedGenerationMethods"))
            if slots:
                out[name] = slots
        return out

    if provider == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        out = {}
        for m in resp.json().get("data", []):
            mid = m.get("id")
            if not mid:
                continue
            slots = registry.classify_anthropic(mid)
            if slots:
                out[mid] = slots
        return out

    if provider == "openrouter":
        headers = {"Authorization": f"Bearer {key}"}
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        out = {}
        for m in resp.json().get("data", []):
            mid = m.get("id")
            if not mid:
                continue
            slots = registry.classify_openrouter(m)
            if slots:
                out[mid] = slots
        return out

    if provider == "deepgram":
        headers = {"Authorization": f"Token {key}"}
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        body = resp.json()
        out = {}
        # Deepgram returns categorized lists. Prefer the explicit STT list; fall
        # back to flattening while excluding TTS (aura*) voices.
        candidates: list[dict] = []
        if isinstance(body, dict) and isinstance(body.get("stt"), list):
            candidates = [x for x in body["stt"] if isinstance(x, dict)]
        elif isinstance(body, dict):
            for k, v in body.items():
                if k.lower() in ("tts", "speak", "voices"):
                    continue
                if isinstance(v, list):
                    candidates.extend([x for x in v if isinstance(x, dict)])
        elif isinstance(body, list):
            candidates = [x for x in body if isinstance(x, dict)]
        for m in candidates:
            mid = m.get("canonical_name") or m.get("name") or m.get("model")
            if not mid:
                continue
            arch = (m.get("architecture") or m.get("type") or "").lower()
            if "tts" in arch or "speak" in arch:
                continue
            # aura* are Deepgram TTS voices, not STT models.
            if str(mid).lower().startswith("aura"):
                continue
            out[mid] = {registry.SLOT_STT}
        return out

    if meta.get("openai_compatible"):
        # openai / groq / deepseek
        headers = {"Authorization": f"Bearer {key}"}
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        out = {}
        for m in resp.json().get("data", []):
            mid = m.get("id")
            if not mid:
                continue
            slots = registry.classify_openai_like(mid)
            if slots:
                out[mid] = slots
        return out

    return {}


async def _get_provider_models(provider: str, *, force: bool) -> tuple[dict[str, set[str]], str]:
    """Return ({model_id: slots}, source) with caching + fallback."""
    key = runtime_config.api_key_for(provider)
    if not key:
        return {}, "fallback"

    kh = _key_hash(key)
    entry = _cache.get(provider)
    now = time.monotonic()
    if (
        not force
        and entry is not None
        and entry.get("key_hash") == kh
        and (now - entry.get("at", 0)) < _CACHE_TTL_SECONDS
    ):
        return entry["models"], "live"

    async with _lock_for(provider):
        # re-check after acquiring the lock
        entry = _cache.get(provider)
        if (
            not force
            and entry is not None
            and entry.get("key_hash") == kh
            and (now - entry.get("at", 0)) < _CACHE_TTL_SECONDS
        ):
            return entry["models"], "live"
        try:
            async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
                models = await _fetch_models(provider, client)
            if models:
                _cache[provider] = {"key_hash": kh, "at": now, "models": models}
                return models, "live"
            return {}, "fallback"
        except Exception as exc:
            logger.warning("model list fetch failed for %s: %s", provider, exc)
            return {}, "fallback"


# ── Public API ────────────────────────────────────────────────────────────────

async def list_for_slot(slot: str, *, force: bool = False) -> dict[str, dict[str, Any]]:
    """Return {provider: {"models": [...], "source": "live"|"fallback",
    "key_status": "present"|"missing"}} for every provider that can serve `slot`."""
    providers = registry.slot_providers(slot)
    results: dict[str, dict[str, Any]] = {}

    async def one(provider: str) -> None:
        models_map, source = await _get_provider_models(provider, force=force)
        live_models = sorted(
            [mid for mid, slots in models_map.items() if slot in slots]
        )
        if not live_models:
            live_models = list(registry.FALLBACK_MODELS.get(provider, {}).get(slot, []))
            source = "fallback"
        results[provider] = {
            "models": live_models,
            "source": source,
            "key_status": runtime_config.key_status(provider),
            "supports_custom_model": bool(
                (registry.provider_meta(provider) or {}).get("supports_custom_model")
            ),
        }

    await asyncio.gather(*(one(p) for p in providers))
    return results


async def full_registry(*, force: bool = False) -> dict[str, Any]:
    """Everything the frontend needs to render the Settings page."""
    slots_payload: dict[str, Any] = {}
    for slot in registry.SLOTS:
        slots_payload[slot] = {
            "label": registry.SLOT_LABELS.get(slot, slot),
            "providers": await list_for_slot(slot, force=force),
        }
    providers_meta = {
        pid: {
            "display_name": meta["display_name"],
            "supports_custom_model": bool(meta.get("supports_custom_model")),
        }
        for pid, meta in registry.PROVIDERS.items()
    }
    return {"slots": slots_payload, "providers": providers_meta}


def clear_cache() -> None:
    _cache.clear()
