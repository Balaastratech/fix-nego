"""
Lightweight translation helper for the multilanguage adaptation feature.

Used by the Pro tactical-advice path: when the user is speaking a non-English
language we translate the transcript window and user query into English before
calling gemini-2.5-pro (which is most accurate on English-trained constraint
prompts), then translate the answer back into the user's response language.

Reversible: every call site checks settings.MULTILANG_ENABLED first. If the
flag is off, translate_text() is never reached and this module sits idle.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import OrderedDict
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


def _is_english(code: Optional[str]) -> bool:
    if not code:
        return True
    return code.strip().lower().split("-")[0] == "en"


def _cache_key(text: str, src: Optional[str], dst: str) -> str:
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{h}|{(src or 'auto').lower()}|{dst.lower()}"


# Tiny LRU. Sufficient — the Pro advice path translates ~2KB of transcript
# plus a 200-char question per turn, and repeats are common within a session.
_CACHE: "OrderedDict[str, str]" = OrderedDict()


def _cache_get(key: str) -> Optional[str]:
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    return None


def _cache_put(key: str, value: str) -> None:
    _CACHE[key] = value
    _CACHE.move_to_end(key)
    while len(_CACHE) > max(50, settings.TRANSLATION_CACHE_MAX_ENTRIES):
        _CACHE.popitem(last=False)


def clear_cache() -> None:
    """Test hook."""
    _CACHE.clear()


async def translate_text(
    text: str,
    source_lang: Optional[str],
    target_lang: str,
) -> str:
    """Translate `text` from `source_lang` (BCP-47 or None for auto) to `target_lang`.

    Returns the translated string. On any error returns the original text — the
    caller can still proceed; worst case the model gets a non-English input it
    can usually handle anyway.
    """
    if not text or not text.strip():
        return text
    # Skip when source is a sentinel non-language ("multi", "auto", "unknown") —
    # those come from Deepgram's code-switch mode where we never resolved an
    # actual BCP-47 code. Trying to translate from them just burns the 2.5s
    # timeout budget and the user sees nothing.
    if source_lang and source_lang.strip().lower() in ("multi", "auto", "unknown", ""):
        logger.debug("translate_text: skipping non-language source %r", source_lang)
        return text
    if _is_english(source_lang) and _is_english(target_lang):
        return text
    src_root = (source_lang or "").split("-")[0].lower()
    dst_root = target_lang.split("-")[0].lower()
    if src_root and src_root == dst_root:
        return text

    key = _cache_key(text, source_lang, target_lang)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    src_hint = source_lang or "auto-detect"
    prompt = (
        f"Translate the following text from {src_hint} to {target_lang}. "
        "Return ONLY the translation, no quotes, no explanation, no language tags.\n\n"
        f"TEXT:\n{text}"
    )

    # Multi-provider: when the Fast Text slot is NOT Google, route translation
    # through the provider-agnostic text client. Google keeps its existing path.
    from app.providers import runtime_config
    from app.providers.registry import SLOT_FAST_TEXT
    if not runtime_config.is_google(SLOT_FAST_TEXT):
        try:
            from app.providers import text_client
            translated = await asyncio.wait_for(
                text_client.generate(
                    SLOT_FAST_TEXT,
                    user_text=prompt,
                    temperature=0.0,
                    max_output_tokens=max(512, min(4096, len(text) * 3)),
                    timeout=settings.TRANSLATION_TIMEOUT_SECONDS,
                ),
                timeout=settings.TRANSLATION_TIMEOUT_SECONDS,
            )
            translated = (translated or "").strip()
            if not translated:
                return text
            _cache_put(key, translated)
            return translated
        except Exception as exc:
            logger.warning("translate_text: provider path failed (%s); returning original", exc)
            return text

    # Lazy import — keep this module importable when google-genai isn't installed
    # (e.g. unit tests with the flag off).
    try:
        from google import genai
        from google.genai import types
    except Exception as exc:
        logger.warning("translate_text: google-genai unavailable (%s); returning original", exc)
        return text

    from app.providers import runtime_config as _rc
    if _rc.google_use_vertex():
        client = genai.Client(
            vertexai=True,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        )
    else:
        client = genai.Client(api_key=_rc.google_api_key())

    src_hint = source_lang or "auto-detect"
    prompt = (
        f"Translate the following text from {src_hint} to {target_lang}. "
        "Return ONLY the translation, no quotes, no explanation, no language tags.\n\n"
        f"TEXT:\n{text}"
    )

    try:
        response = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=settings.TRANSLATION_MODEL,
                    contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        max_output_tokens=max(512, min(4096, len(text) * 3)),
                    ),
                ),
            ),
            timeout=settings.TRANSLATION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("translate_text: timeout src=%s dst=%s len=%d", source_lang, target_lang, len(text))
        return text
    except Exception as exc:
        logger.warning("translate_text: failed src=%s dst=%s err=%s", source_lang, target_lang, exc)
        return text

    translated = (getattr(response, "text", None) or "").strip()
    if not translated:
        return text
    _cache_put(key, translated)
    return translated
