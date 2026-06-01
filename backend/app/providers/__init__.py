"""Provider-agnostic AI layer.

This package makes the app's AI calls provider-agnostic. The user can pick a
provider + model per task slot (reasoning, fast_text, vision, stt, live_voice)
and paste an API key from the in-app Settings page. Nothing here changes the
default behavior: with an empty runtime config every resolver falls back to the
existing Google/Gemini values, so the app keeps working exactly as before.

Modules:
- registry        : static provider metadata, capability rules, curated fallbacks
- runtime_config  : hot-apply overlay (JSON) over env defaults; resolvers
- model_catalog   : live model discovery from each provider's own list API
- text_client     : provider-agnostic async text/vision generation
"""
