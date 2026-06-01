"""Provider-agnostic async text/vision generation.

`generate()` resolves the provider/model/key for a task slot and dispatches to
the right SDK, returning plain text so existing callers (which JSON-parse or
read the text) are unchanged.

Design rule used by callers: the Google/Gemini path at each call site is left
exactly as-is (fully instrumented). Callers only route HERE when the slot's
resolved provider is NOT Google. text_client still implements a Google branch
for completeness/testing, but it is not the default production path.

Supported dispatch:
- anthropic                      → anthropic.AsyncAnthropic (messages API)
- openai / groq / deepseek / openrouter (openai_compatible) → openai.AsyncOpenAI
- google                         → google.genai (generate_content)
"""

from __future__ import annotations

import asyncio
import base64
import logging

from app.providers import registry
from app.providers import runtime_config

logger = logging.getLogger(__name__)


class ProviderNotConfigured(RuntimeError):
    pass


def _images_to_data_urls(images: list[bytes] | None, mime: str) -> list[str]:
    out: list[str] = []
    for raw in images or []:
        b64 = base64.b64encode(raw).decode("ascii")
        out.append(f"data:{mime};base64,{b64}")
    return out


async def generate(
    slot: str,
    *,
    user_text: str,
    system: str | None = None,
    images: list[bytes] | None = None,
    image_mime: str = "image/jpeg",
    json_mode: bool = False,
    temperature: float = 0.2,
    max_output_tokens: int = 2048,
    timeout: float = 8.0,
) -> str:
    """Generate text for a task slot using its configured provider/model.

    Returns the model's text output. Raises on transport/SDK errors (callers
    already wrap calls in try/except + timeouts).
    """
    provider = runtime_config.provider_for(slot)
    model = runtime_config.model_for(slot)
    api_key = runtime_config.api_key_for(provider)
    if not model:
        raise ProviderNotConfigured(f"no model resolved for slot '{slot}'")
    if not api_key and provider != "google":
        raise ProviderNotConfigured(f"no API key for provider '{provider}'")

    meta = registry.provider_meta(provider)

    if provider == "anthropic":
        return await _generate_anthropic(
            model, api_key, system, user_text, images, image_mime,
            json_mode, temperature, max_output_tokens, timeout,
        )

    if meta and meta.get("openai_compatible"):
        return await _generate_openai_compatible(
            meta["base_url"], model, api_key, system, user_text, images,
            image_mime, json_mode, temperature, max_output_tokens, timeout,
        )

    if provider == "google":
        return await _generate_google(
            model, api_key, system, user_text, images, image_mime,
            json_mode, temperature, max_output_tokens, timeout,
        )

    raise ProviderNotConfigured(f"unsupported provider '{provider}' for slot '{slot}'")


async def _generate_anthropic(
    model, api_key, system, user_text, images, image_mime,
    json_mode, temperature, max_output_tokens, timeout,
) -> str:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key, timeout=timeout)
    content: list[dict] = []
    for raw in images or []:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image_mime,
                "data": base64.b64encode(raw).decode("ascii"),
            },
        })
    prompt = user_text
    if json_mode:
        prompt += "\n\nRespond with ONLY valid JSON. No prose, no markdown fences."
    content.append({"type": "text", "text": prompt})

    kwargs: dict = {
        "model": model,
        "max_tokens": max_output_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        kwargs["system"] = system
    resp = await client.messages.create(**kwargs)
    parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return "".join(parts).strip()


async def _generate_openai_compatible(
    base_url, model, api_key, system, user_text, images, image_mime,
    json_mode, temperature, max_output_tokens, timeout,
) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    user_content: list[dict] = [{"type": "text", "text": user_text}]
    for url in _images_to_data_urls(images, image_mime):
        user_content.append({"type": "image_url", "image_url": {"url": url}})

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    # If no images, send plain string content for broadest compatibility.
    if len(user_content) == 1:
        messages.append({"role": "user", "content": user_text})
    else:
        messages.append({"role": "user", "content": user_content})

    kwargs: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_output_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = await client.chat.completions.create(**kwargs)
    return (resp.choices[0].message.content or "").strip()


async def _generate_google(
    model, api_key, system, user_text, images, image_mime,
    json_mode, temperature, max_output_tokens, timeout,
) -> str:
    from google import genai
    from google.genai import types

    if api_key:
        client = genai.Client(api_key=api_key)
    else:
        # Vertex / ADC path (mirrors existing services).
        client = genai.Client()

    parts: list = [types.Part(text=user_text)]
    for raw in images or []:
        parts.append(types.Part(inline_data=types.Blob(data=raw, mime_type=image_mime)))

    config_kwargs: dict = {
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
    }
    if system:
        config_kwargs["system_instruction"] = system
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"

    resp = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: client.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(**config_kwargs),
        ),
    )
    return (resp.text or "").strip()
