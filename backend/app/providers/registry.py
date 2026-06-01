"""Provider registry: metadata, capability rules, and curated fallback models.

This module is pure data + pure functions (no network, no SDK imports). It
declares:

1. SLOTS              - the task slots the app routes AI work through.
2. PROVIDERS          - per-provider metadata (display name, base URL, key field,
                        model-list endpoint, openai-compatible flag, which slots
                        the provider can serve at all, custom-model support).
3. classify_model()   - conservative rules mapping a discovered model id (and any
                        provider metadata) to the slots it can accurately serve.
4. FALLBACK_MODELS    - curated, verified model ids per provider per slot, used by
                        model_catalog ONLY when a live fetch is unavailable.

Live Voice is intentionally restricted to Google for this release. OpenAI Realtime
is declared with phase2=True so the registry documents it but the UI hides it.

Verified May 2026 via provider docs:
- OpenAI       https://platform.openai.com/docs/models
- Anthropic    https://platform.claude.com/docs/en/about-claude/models/overview
- Groq         https://console.groq.com/docs/models
- DeepSeek     https://api-docs.deepseek.com/
- OpenRouter   https://openrouter.ai/docs/guides/overview/models
- Deepgram     https://developers.deepgram.com/docs/models-languages-overview
"""

from __future__ import annotations

# ── Task slots ──────────────────────────────────────────────────────────────
SLOT_LIVE_VOICE = "live_voice"
SLOT_REASONING = "reasoning"
SLOT_FAST_TEXT = "fast_text"
SLOT_VISION = "vision"
SLOT_STT = "stt"

SLOTS: list[str] = [
    SLOT_LIVE_VOICE,
    SLOT_REASONING,
    SLOT_FAST_TEXT,
    SLOT_VISION,
    SLOT_STT,
]

SLOT_LABELS: dict[str, str] = {
    SLOT_LIVE_VOICE: "Live Voice (Hold-to-Ask)",
    SLOT_REASONING: "Reasoning / Advice",
    SLOT_FAST_TEXT: "Fast Text (extraction, cache, translation)",
    SLOT_VISION: "Vision (screen analysis)",
    SLOT_STT: "Speech-to-Text",
}

# ── Provider metadata ─────────────────────────────────────────────────────────
# openai_compatible providers share one adapter (OpenAI Chat Completions schema);
# they differ only by base_url + key. Google and Anthropic use native SDKs.
PROVIDERS: dict[str, dict] = {
    "google": {
        "display_name": "Google Gemini",
        "key_field": "GEMINI_API_KEY",
        "openai_compatible": False,
        # Gemini ListModels (api-key form). Vertex path is handled separately.
        "list_endpoint": "https://generativelanguage.googleapis.com/v1beta/models",
        "base_url": None,
        "supports_custom_model": False,
        "slots": [SLOT_LIVE_VOICE, SLOT_REASONING, SLOT_FAST_TEXT, SLOT_VISION, SLOT_STT],
        # STT for google is Google Cloud STT (chirp_3) handled by stt_service; the
        # Gemini ListModels endpoint does not enumerate Cloud STT recognizers, so
        # google STT relies on the curated fallback list below.
    },
    "openai": {
        "display_name": "OpenAI",
        "key_field": "OPENAI_API_KEY",
        "openai_compatible": True,
        "base_url": "https://api.openai.com/v1",
        "list_endpoint": "https://api.openai.com/v1/models",
        "supports_custom_model": True,
        "slots": [SLOT_REASONING, SLOT_FAST_TEXT, SLOT_VISION, SLOT_STT],
        # live_voice (gpt-realtime) is phase2 — see LIVE_VOICE_PHASE2 below.
    },
    "anthropic": {
        "display_name": "Anthropic Claude",
        "key_field": "ANTHROPIC_API_KEY",
        "openai_compatible": False,
        "base_url": "https://api.anthropic.com/v1",
        "list_endpoint": "https://api.anthropic.com/v1/models",
        "supports_custom_model": True,
        "slots": [SLOT_REASONING, SLOT_FAST_TEXT, SLOT_VISION],
    },
    "groq": {
        "display_name": "Groq",
        "key_field": "GROQ_API_KEY",
        "openai_compatible": True,
        "base_url": "https://api.groq.com/openai/v1",
        "list_endpoint": "https://api.groq.com/openai/v1/models",
        "supports_custom_model": True,
        "slots": [SLOT_REASONING, SLOT_FAST_TEXT, SLOT_VISION, SLOT_STT],
    },
    "deepseek": {
        "display_name": "DeepSeek",
        "key_field": "DEEPSEEK_API_KEY",
        "openai_compatible": True,
        "base_url": "https://api.deepseek.com",
        "list_endpoint": "https://api.deepseek.com/models",
        "supports_custom_model": True,
        "slots": [SLOT_REASONING, SLOT_FAST_TEXT],
    },
    "openrouter": {
        "display_name": "OpenRouter",
        "key_field": "OPENROUTER_API_KEY",
        "openai_compatible": True,
        "base_url": "https://openrouter.ai/api/v1",
        "list_endpoint": "https://openrouter.ai/api/v1/models",
        "supports_custom_model": True,
        "slots": [SLOT_REASONING, SLOT_FAST_TEXT, SLOT_VISION],
    },
    "deepgram": {
        "display_name": "Deepgram",
        "key_field": "DEEPGRAM_API_KEY",
        "openai_compatible": False,
        "base_url": "https://api.deepgram.com",
        "list_endpoint": "https://api.deepgram.com/v1/models",
        "supports_custom_model": True,
        "slots": [SLOT_STT],
    },
    "assemblyai": {
        "display_name": "AssemblyAI",
        "key_field": "ASSEMBLYAI_API_KEY",
        "openai_compatible": False,
        "base_url": "https://api.assemblyai.com",
        "list_endpoint": None,  # no public model-list endpoint → curated fallback
        "supports_custom_model": False,
        "slots": [SLOT_STT],
    },
    "elevenlabs": {
        "display_name": "ElevenLabs",
        "key_field": "ELEVENLABS_API_KEY",
        "openai_compatible": False,
        "base_url": "https://api.elevenlabs.io",
        "list_endpoint": None,  # curated — model list endpoint mixes TTS/STT/etc.
        "supports_custom_model": True,
        "slots": [SLOT_STT],
    },
}

# OpenAI Realtime exists for live_voice but is deferred. The registry records it
# so a future phase can flip it on; the frontend hides phase2 entries.
LIVE_VOICE_PHASE2: dict[str, list[str]] = {
    "openai": ["gpt-realtime", "gpt-realtime-2"],
}

# The STT provider id used internally by stt_service for Google Cloud STT.
GOOGLE_STT_PROVIDER_VALUE = "google_stt"

# ── Curated fallback models (verified May 2026) ───────────────────────────────
# Used by model_catalog ONLY when a provider has no key or its live list call
# fails. Never the authoritative source when a live fetch succeeds.
FALLBACK_MODELS: dict[str, dict[str, list[str]]] = {
    "google": {
        SLOT_LIVE_VOICE: ["gemini-live-2.5-flash-native-audio"],
        SLOT_REASONING: ["gemini-2.5-pro", "gemini-2.5-flash"],
        SLOT_FAST_TEXT: ["gemini-2.5-flash"],
        SLOT_VISION: ["gemini-2.5-flash", "gemini-2.5-pro"],
        SLOT_STT: ["chirp_3", "chirp_2"],
    },
    "openai": {
        SLOT_REASONING: ["gpt-5.5", "gpt-5.4-mini"],
        SLOT_FAST_TEXT: ["gpt-5.4-mini", "gpt-5.4-nano"],
        SLOT_VISION: ["gpt-5.5", "gpt-5.4-mini"],
        SLOT_STT: ["gpt-4o-mini-transcribe", "gpt-4o-transcribe", "whisper-1"],
    },
    "anthropic": {
        SLOT_REASONING: ["claude-opus-4-8", "claude-sonnet-4-6"],
        SLOT_FAST_TEXT: ["claude-haiku-4-5", "claude-sonnet-4-6"],
        SLOT_VISION: ["claude-sonnet-4-6", "claude-opus-4-8"],
    },
    "groq": {
        SLOT_REASONING: ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"],
        SLOT_FAST_TEXT: ["llama-3.1-8b-instant"],
        SLOT_VISION: ["meta-llama/llama-4-scout-17b-16e-instruct"],
        SLOT_STT: ["whisper-large-v3-turbo", "whisper-large-v3"],
    },
    "deepseek": {
        SLOT_REASONING: ["deepseek-reasoner", "deepseek-chat"],
        SLOT_FAST_TEXT: ["deepseek-chat"],
    },
    "openrouter": {
        SLOT_REASONING: ["anthropic/claude-opus-4-8", "openai/gpt-5.5"],
        SLOT_FAST_TEXT: ["openai/gpt-5.4-mini", "google/gemini-2.5-flash"],
        SLOT_VISION: ["openai/gpt-5.5", "google/gemini-2.5-flash"],
    },
    "deepgram": {
        SLOT_STT: ["nova-3", "nova-2"],
    },
    "assemblyai": {
        SLOT_STT: ["best", "nano"],
    },
    "elevenlabs": {
        SLOT_STT: ["scribe_v2", "scribe_v1"],
    },
}

# ── Capability classification ─────────────────────────────────────────────────
# Conservative: a model only appears in a slot if a known-good rule matches.
# Unknown / unclassifiable models are dropped (still reachable via custom-model
# entry where the provider supports it).

# id substrings that mark a model as NOT a chat/vision/reasoning model.
_NON_CHAT_MARKERS = (
    "embed", "embedding", "rerank", "moderation", "tts", "image", "dall-e",
    "guard", "whisper", "transcribe", "realtime", "audio", "search-",
)


def _is_chat_like(model_id: str) -> bool:
    mid = model_id.lower()
    return not any(marker in mid for marker in _NON_CHAT_MARKERS)


def classify_openai_like(model_id: str) -> set[str]:
    """Classify an OpenAI/Groq/DeepSeek-style model id into slots by id patterns."""
    mid = model_id.lower()
    slots: set[str] = set()

    # STT
    if "transcribe" in mid or "whisper" in mid:
        slots.add(SLOT_STT)
        return slots
    # Live voice (handled as phase2; not surfaced, but classify for completeness)
    if "realtime" in mid:
        slots.add(SLOT_LIVE_VOICE)
        return slots
    if not _is_chat_like(model_id):
        return slots

    # Chat/reasoning families across openai-compatible providers.
    reasoning_markers = (
        "gpt-5", "gpt-4o", "o1", "o3", "o4", "gpt-oss",
        "llama-3.3", "llama-4", "llama3.3", "llama4",
        "deepseek-chat", "deepseek-reasoner", "deepseek-v",
        "mixtral", "qwen", "gemma",
    )
    if any(m in mid for m in reasoning_markers):
        slots.add(SLOT_REASONING)
        slots.add(SLOT_FAST_TEXT)
        # Vision: only families known to accept image input.
        vision_markers = ("gpt-5", "gpt-4o", "llama-4", "llama4", "scout", "maverick")
        if any(m in mid for m in vision_markers):
            slots.add(SLOT_VISION)
    return slots


def classify_anthropic(model_id: str) -> set[str]:
    mid = model_id.lower()
    if "claude" not in mid:
        return set()
    slots = {SLOT_REASONING, SLOT_FAST_TEXT, SLOT_VISION}
    return slots


def classify_google(model_id: str, supported_methods: list[str] | None = None) -> set[str]:
    """Classify a Gemini model using its supportedGenerationMethods when available."""
    mid = model_id.lower()
    methods = {m.lower() for m in (supported_methods or [])}
    slots: set[str] = set()
    if "embed" in mid or "aqa" in mid or "imagen" in mid:
        return slots
    if not methods:
        # No metadata → infer from id.
        if "live" in mid or "native-audio" in mid:
            slots.add(SLOT_LIVE_VOICE)
        if "gemini" in mid:
            slots.update({SLOT_REASONING, SLOT_FAST_TEXT, SLOT_VISION})
        return slots
    if "bidigeneratecontent" in methods:
        slots.add(SLOT_LIVE_VOICE)
    if "generatecontent" in methods:
        # All current Gemini generateContent models accept images.
        slots.update({SLOT_REASONING, SLOT_FAST_TEXT, SLOT_VISION})
    return slots


def classify_openrouter(model: dict) -> set[str]:
    """Classify an OpenRouter model dict using its rich modality metadata."""
    arch = model.get("architecture") or {}
    input_mods = {m.lower() for m in (arch.get("input_modalities") or [])}
    output_mods = {m.lower() for m in (arch.get("output_modalities") or [])}
    supported = {p.lower() for p in (model.get("supported_parameters") or [])}
    slots: set[str] = set()
    # Must produce text to be useful for our text slots.
    if "text" not in output_mods and output_mods:
        return slots
    if "text" in input_mods or not input_mods:
        slots.add(SLOT_REASONING)
        slots.add(SLOT_FAST_TEXT)
    if "image" in input_mods:
        slots.add(SLOT_VISION)
    # Keep reasoning only when it can actually follow tools/structured prompts.
    # (We don't hard-require tools; structured prompting works without it.)
    _ = supported
    return slots


_GOOGLE_STT_AVAILABLE: bool | None = None


def _google_cloud_stt_available() -> bool:
    """True only if Google Cloud Speech-to-Text can actually run here.

    Unlike the other STT providers (Deepgram/AssemblyAI/ElevenLabs/OpenAI/Groq),
    which are reached over HTTP with a pasted BYOK key, the "google" STT path uses
    the ``google.cloud.speech_v2`` SDK with GCP credentials (ADC) — it is NOT
    key-only / BYOK-portable. On the lean hosted profile that SDK is intentionally
    not installed, so offering "google" in the STT dropdown there would only lead
    to an ImportError at session time. We gate on SDK presence (a lightweight
    ``find_spec`` — no actual import, keeps this module SDK-free) so Google STT
    shows on a full local/Vertex install and is hidden on the lean hosted box.
    """
    global _GOOGLE_STT_AVAILABLE
    if _GOOGLE_STT_AVAILABLE is None:
        try:
            import importlib.util
            _GOOGLE_STT_AVAILABLE = (
                importlib.util.find_spec("google.cloud.speech_v2") is not None
            )
        except Exception:
            _GOOGLE_STT_AVAILABLE = False
    return _GOOGLE_STT_AVAILABLE


def slot_providers(slot: str, *, include_phase2: bool = False) -> list[str]:
    """Providers that can serve a slot at all (ignores key presence)."""
    out = [pid for pid, meta in PROVIDERS.items() if slot in meta["slots"]]
    if slot == SLOT_LIVE_VOICE:
        out = ["google"]
        if include_phase2:
            out += [p for p in LIVE_VOICE_PHASE2 if p not in out]
    elif slot == SLOT_STT and not _google_cloud_stt_available():
        # Hide Google Cloud STT where its SDK isn't installed (lean hosted profile).
        # The 5 BYOK/HTTP STT providers remain. Google still serves the other slots
        # (live voice / reasoning / vision / fast text) via the AI-Studio key.
        out = [p for p in out if p != "google"]
    return out


def provider_meta(provider: str) -> dict | None:
    return PROVIDERS.get(provider)
