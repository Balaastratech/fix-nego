"""Runtime provider config: a hot-apply overlay over env defaults.

The in-app Settings page writes provider/model choices and API keys here. This
module persists them to a single JSON file and exposes resolvers used across the
services. Resolution order for every value:

    runtime JSON  →  env default (settings)  →  registry fallback

So an EMPTY runtime file == today's exact behavior (Google everywhere). Changing
a value is hot-applied: services that build their AI client per-call pick it up
on the next call; per-session clients (the listener + Gemini Live session) pick
it up on the next session start. No backend restart, no redeploy.

Security: API keys are stored in the JSON but NEVER returned by any read API.
Only key_status() (present|missing) is exposed.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from app.config import settings
from app.providers import registry

logger = logging.getLogger(__name__)

# Stored next to the SQLite DB under backend/data/. Overridable via env for tests.
_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "runtime_providers.json"
_CONFIG_PATH = Path(os.environ.get("RUNTIME_PROVIDERS_PATH", str(_DEFAULT_PATH)))

_lock = threading.RLock()
_cache: dict[str, Any] | None = None

# ── Phase G: per-session overlay (multi-tenant BYOK) ──────────────────────────
# A ContextVar carrying ONE session's provider overrides, scoped to the current
# asyncio task (the websocket receive loop sets it; tasks it spawns inherit it).
# Same shape as the persisted JSON: {"slots": {}, "keys": {}, "settings": {}}.
# When None (the default, and whenever PER_SESSION_PROVIDER_OVERRIDE_ENABLED is
# False) every resolver behaves EXACTLY as the pre-Phase-G global path. The
# overlay is read-only here — it is never written to disk, so concurrent sessions
# with different keys cannot clobber each other or the global runtime_providers.json.
_session_overrides: "contextvars.ContextVar[dict[str, Any] | None]" = contextvars.ContextVar(
    "session_provider_overrides", default=None
)


def _per_session_enabled() -> bool:
    return bool(getattr(settings, "PER_SESSION_PROVIDER_OVERRIDE_ENABLED", True))


def set_session_overrides(overrides: dict[str, Any] | None):
    """Bind the current task's per-session provider overlay. Returns a reset token.

    A None / empty overlay restores pure global behavior for this task.
    """
    if not _per_session_enabled():
        overrides = None
    return _session_overrides.set(overrides or None)


def reset_session_overrides(token) -> None:
    try:
        _session_overrides.reset(token)
    except Exception:
        pass


def current_session_overrides() -> dict[str, Any] | None:
    if not _per_session_enabled():
        return None
    return _session_overrides.get()


def _sess_slot(slot: str) -> dict[str, Any]:
    ov = current_session_overrides()
    if not ov:
        return {}
    return (ov.get("slots") or {}).get(slot) or {}


def _sess_key(provider: str) -> str:
    ov = current_session_overrides()
    if not ov:
        return ""
    return ((ov.get("keys") or {}).get(provider) or "").strip()


def _sess_setting(name: str) -> str:
    ov = current_session_overrides()
    if not ov:
        return ""
    val = (ov.get("settings") or {}).get(name)
    return (val or "").strip() if isinstance(val, str) else ""

# Slot → (provider field, model field) on settings for env defaults.
_SLOT_ENV_FIELDS: dict[str, tuple[str, str]] = {
    registry.SLOT_LIVE_VOICE: ("LIVE_VOICE_PROVIDER", "LIVE_VOICE_MODEL"),
    registry.SLOT_REASONING: ("REASONING_PROVIDER", "REASONING_MODEL"),
    registry.SLOT_FAST_TEXT: ("FAST_TEXT_PROVIDER", "FAST_TEXT_MODEL"),
    registry.SLOT_VISION: ("VISION_PROVIDER", "VISION_MODEL"),
    registry.SLOT_STT: ("STT_PROVIDER", "STT_MODEL"),
}


def _empty() -> dict[str, Any]:
    return {"slots": {}, "keys": {}, "settings": {}}


def _override_enabled() -> bool:
    """Master switch (env). When False, the runtime JSON is ignored entirely and
    every resolver falls back to .env / registry — i.e. exact pre-multi-provider
    behavior. This is the one-flag revert if anything misbehaves."""
    return bool(getattr(settings, "PROVIDER_RUNTIME_OVERRIDE_ENABLED", True))


def _load_unlocked() -> dict[str, Any]:
    global _cache
    if not _override_enabled():
        # Do not cache the empty view — flag may flip back on without restart.
        return _empty()
    if _cache is not None:
        return _cache
    data = _empty()
    try:
        if _CONFIG_PATH.exists():
            raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data["slots"] = raw.get("slots", {}) or {}
                data["keys"] = raw.get("keys", {}) or {}
                data["settings"] = raw.get("settings", {}) or {}
    except Exception as exc:  # never let a bad file break startup
        logger.warning("runtime_providers.json unreadable (%s); using defaults", exc)
        data = _empty()
    _cache = data
    return _cache


def reload() -> dict[str, Any]:
    """Drop the in-memory cache and re-read the file."""
    global _cache
    with _lock:
        _cache = None
        return _load_unlocked()


def _write_unlocked(data: dict[str, Any]) -> None:
    global _cache
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(_CONFIG_PATH.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, _CONFIG_PATH)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    _cache = data


# ── Resolvers ─────────────────────────────────────────────────────────────────

def provider_for(slot: str) -> str:
    """Resolve the provider id for a task slot. Session overlay → JSON → env → registry."""
    sess = (_sess_slot(slot).get("provider") or "").strip()
    if sess:
        return sess
    with _lock:
        data = _load_unlocked()
        slot_cfg = data["slots"].get(slot) or {}
        chosen = (slot_cfg.get("provider") or "").strip()
        if chosen:
            return chosen
        prov_field, _ = _SLOT_ENV_FIELDS.get(slot, ("", ""))
        env_val = (getattr(settings, prov_field, "") or "").strip() if prov_field else ""
        if env_val:
            return env_val
        # STT special-case: fall back to the legacy TRANSCRIPTION_PROVIDER.
        if slot == registry.SLOT_STT:
            legacy = (settings.TRANSCRIPTION_PROVIDER or "google_stt").strip()
            return "google" if legacy == registry.GOOGLE_STT_PROVIDER_VALUE else legacy
        return "google"


def model_for(slot: str) -> str:
    """Resolve the model id for a task slot. Session overlay → JSON → env → registry."""
    sess = (_sess_slot(slot).get("model") or "").strip()
    if sess:
        return sess
    with _lock:
        data = _load_unlocked()
        slot_cfg = data["slots"].get(slot) or {}
        chosen = (slot_cfg.get("model") or "").strip()
        if chosen:
            return chosen
        _, model_field = _SLOT_ENV_FIELDS.get(slot, ("", ""))
        env_val = (getattr(settings, model_field, "") or "").strip() if model_field else ""
        if env_val:
            return env_val
        # Fall back to the first curated model for the resolved provider.
        prov = provider_for(slot)
        fallback = registry.FALLBACK_MODELS.get(prov, {}).get(slot, [])
        return fallback[0] if fallback else ""


def api_key_for(provider: str) -> str:
    """Resolve the API key for a provider: session overlay → runtime JSON → env default."""
    sess = _sess_key(provider)
    if sess:
        return sess
    # legacy 'google_stt' shares google's key — honor a session 'google' key too
    if provider == registry.GOOGLE_STT_PROVIDER_VALUE:
        sess_google = _sess_key("google")
        if sess_google:
            return sess_google
    with _lock:
        data = _load_unlocked()
        stored = (data["keys"].get(provider) or "").strip()
        if stored:
            return stored
    meta = registry.provider_meta(provider)
    if not meta:
        # legacy 'google_stt' maps to google's key
        if provider == registry.GOOGLE_STT_PROVIDER_VALUE:
            return (settings.GEMINI_API_KEY or "").strip()
        return ""
    return (getattr(settings, meta["key_field"], "") or "").strip()


def key_status(provider: str) -> str:
    """'present' | 'missing' — never the key value itself."""
    return "present" if api_key_for(provider) else "missing"


def has_runtime_key(provider: str) -> bool:
    """True only if a key was saved via the Settings UI (the JSON store) — NOT if
    it merely comes from .env. Used to decide when the user explicitly opted into a
    provider/key (e.g. paste a Google key → use AI Studio instead of Vertex)."""
    if _sess_key(provider):
        return True
    with _lock:
        data = _load_unlocked()
        return bool((data["keys"].get(provider) or "").strip())


# ── Google credential resolution (portability) ───────────────────────────────
def google_api_key() -> str:
    """Effective Google API key: runtime (UI) key → env GEMINI_API_KEY."""
    return api_key_for("google")


def google_backend() -> str:
    """Effective Google backend: 'vertex' | 'ai_studio'.

    Resolution: explicit Settings toggle (runtime JSON `settings.google_backend`)
    → env GOOGLE_GENAI_USE_VERTEXAI. The choice drives BOTH the client auth mode
    AND model qualification / Live model IDs (which differ per backend), so they
    can never desync. AI Studio uses a simple API key (no GCP project) → portable.
    """
    sess = _sess_setting("google_backend").lower()
    if sess in ("vertex", "ai_studio"):
        return sess
    with _lock:
        data = _load_unlocked()
        val = ((data.get("settings", {}) or {}).get("google_backend") or "").strip().lower()
    if val in ("vertex", "ai_studio"):
        return val
    return "vertex" if bool(getattr(settings, "GOOGLE_GENAI_USE_VERTEXAI", False)) else "ai_studio"


def google_use_vertex() -> bool:
    """Whether the Google client should use Vertex AI (else AI Studio / Gemini API)."""
    return google_backend() == "vertex"


def google_live_models() -> tuple[str, str]:
    """(primary, fallback) Live model IDs for the effective backend.

    Vertex keeps the existing `google/`-qualified names (unchanged). AI Studio uses
    the bare Gemini-API Live model IDs (which are different strings, not just a
    missing prefix).
    """
    if google_use_vertex():
        return settings.effective_model, settings.effective_fallback_model
    return (
        (settings.GEMINI_LIVE_MODEL_AISTUDIO or "").strip(),
        (settings.GEMINI_LIVE_FALLBACK_AISTUDIO or "").strip(),
    )


def is_google(slot: str) -> bool:
    """Whether a slot currently resolves to Google (used to keep Live/research on Google)."""
    return provider_for(slot) in ("google", registry.GOOGLE_STT_PROVIDER_VALUE)


# ── Mutation ────────────────────────────────────────────────────────────────

class ConfigError(ValueError):
    pass


def _validate_patch(patch: dict[str, Any]) -> None:
    slots = patch.get("slots") or {}
    for slot, cfg in slots.items():
        if slot not in registry.SLOTS:
            raise ConfigError(f"unknown slot: {slot}")
        provider = (cfg or {}).get("provider")
        if provider:
            allowed = registry.slot_providers(slot)
            # accept legacy google_stt for the stt slot
            if slot == registry.SLOT_STT:
                allowed = allowed + [registry.GOOGLE_STT_PROVIDER_VALUE]
            if provider not in allowed:
                raise ConfigError(
                    f"provider '{provider}' cannot serve slot '{slot}'"
                )
    keys = patch.get("keys") or {}
    for provider in keys:
        if provider not in registry.PROVIDERS:
            raise ConfigError(f"unknown provider for key: {provider}")
    s = patch.get("settings") or {}
    if "google_backend" in s:
        gb = (s.get("google_backend") or "").strip().lower()
        if gb not in ("", "vertex", "ai_studio"):
            raise ConfigError(f"invalid google_backend: {gb}")


def update(patch: dict[str, Any]) -> dict[str, Any]:
    """Merge a patch into the stored config and persist atomically.

    patch shape:
        {
          "slots": { "reasoning": {"provider": "anthropic", "model": "claude-..."} },
          "keys":  { "anthropic": "sk-ant-..." }   # "" deletes a stored key
        }
    Returns the safe (key-free) current config.
    """
    _validate_patch(patch)
    with _lock:
        data = _load_unlocked()
        # merge slots
        for slot, cfg in (patch.get("slots") or {}).items():
            cur = data["slots"].get(slot, {})
            if cfg.get("provider") is not None:
                cur["provider"] = (cfg.get("provider") or "").strip()
            if cfg.get("model") is not None:
                cur["model"] = (cfg.get("model") or "").strip()
            data["slots"][slot] = cur
        # merge keys (empty string removes a stored key → falls back to env)
        for provider, value in (patch.get("keys") or {}).items():
            value = (value or "").strip()
            if value:
                data["keys"][provider] = value
            else:
                data["keys"].pop(provider, None)
        # merge settings (e.g. google_backend). Empty string → clear (use env).
        data.setdefault("settings", {})
        for skey, sval in (patch.get("settings") or {}).items():
            sval = (sval or "").strip() if isinstance(sval, str) else sval
            if sval:
                data["settings"][skey] = sval
            else:
                data["settings"].pop(skey, None)
        _write_unlocked(data)
    return safe_config()


def safe_config() -> dict[str, Any]:
    """Current config with key values replaced by present/missing status."""
    out_slots: dict[str, Any] = {}
    for slot in registry.SLOTS:
        out_slots[slot] = {"provider": provider_for(slot), "model": model_for(slot)}
    key_states = {p: key_status(p) for p in registry.PROVIDERS}
    return {
        "slots": out_slots,
        "key_status": key_states,
        "settings": {"google_backend": google_backend()},
        "path": str(_CONFIG_PATH),
    }
