"""
Next-move cache service.

Purpose: precompute a concise "what should the user do right now" recommendation
in the background so vague private asks ("What now?", "Trap?", "Accept?") resolve
from a fresh cache the moment the user holds the orb — instead of waiting for
synchronous Pro reasoning at hold-time.

Lifecycle:
  - listener_agent._on_context_ready fires after a meaningful counterparty turn
    or context update. It schedules refresh_next_move() as a background task.
  - refresh_next_move() debounces, computes a context_basis_hash, calls Flash
    for a fast recommendation, then optionally upgrades to Pro. Result lands
    in session.next_move_cache.
  - During hold-to-ask (handle_user_addressing_ai), format_for_brief() renders
    the [RECOMMENDED NEXT MOVE] block into the pre-query brief when fresh.

The cache only changes the INPUT to Gemini Live. handle_ask_advice's Pro
pre-flight path is unchanged.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from typing import TYPE_CHECKING, Literal, Optional

from google import genai
from google.genai import types

from app.config import settings

if TYPE_CHECKING:
    from app.models.negotiation import NegotiationSession

logger = logging.getLogger(__name__)

_WS_RE = re.compile(r"\s+")


def classify_ask(query: str) -> Literal["vague", "precise"]:
    """Classify an ask as vague (next-step) or precise (detailed).

    Vague: short asks that depend on cached "current best move" context, e.g.
    "what now", "trap?", "can i accept?", "best counter".

    Precise: longer detailed prompts that already supply their own framing.

    Heuristic: token-based substring match against settings.NEXT_MOVE_VAGUE_TOKENS,
    combined with a length cap (<= 60 chars after normalization).
    """
    if not query:
        return "vague"
    norm = _WS_RE.sub(" ", query.strip().lower()).strip(" ?.!,;:")
    if not norm:
        return "vague"
    # Anything over ~60 chars is almost certainly a detailed prompt.
    if len(norm) > 60:
        return "precise"
    tokens = settings.next_move_vague_tokens_list
    for tok in tokens:
        if not tok:
            continue
        if tok == norm or tok in norm:
            return "vague"
    # Short but unrecognized → still treat as vague (cache injection is a no-op
    # when stale, so misclassifying precise→vague is harmless).
    return "vague" if len(norm) <= 30 else "precise"


def _context_basis_hash(session: "NegotiationSession") -> str:
    """Hash the inputs that should invalidate the cache.

    Combines transcript tail + intel snapshot keys + latest vision obs id so
    that a stale Pro upgrade landing AFTER a newer Flash refresh can be detected
    and dropped.
    """
    listener = getattr(session, "listener_agent", None)
    transcript = ""
    ctx: dict = {}
    if listener is not None:
        transcript = (getattr(listener, "accumulated_transcript", "") or "")[-1200:]
        ctx = dict(getattr(listener, "last_context", {}) or {})
    intel_keys = (
        ctx.get("counterparty_price"),
        ctx.get("seller_asking_price"),
        ctx.get("buyer_offer"),
        ctx.get("counterparty_sentiment"),
        ctx.get("counterparty_goal"),
        tuple(ctx.get("key_moments") or [])[-5:],
        tuple(ctx.get("leverage_points") or [])[-5:],
    )
    latest_vision = None
    obs_list = getattr(session, "vision_observations", None) or []
    if obs_list:
        last = obs_list[-1]
        if isinstance(last, dict):
            latest_vision = (last.get("timestamp"), last.get("scene_type"))
    payload = repr((transcript, intel_keys, latest_vision)).encode("utf-8", errors="replace")
    return hashlib.md5(payload).hexdigest()


def should_refresh_cache(session: "NegotiationSession") -> bool:
    """True when the cache should be refreshed.

    Skips if disabled, if within debounce window, or if the basis hash is
    unchanged from the most recent cache entry.
    """
    if not settings.NEXT_MOVE_CACHE_ENABLED:
        return False
    debounce_s = max(0.0, settings.NEXT_MOVE_BACKGROUND_DEBOUNCE_MS / 1000.0)
    last_at = getattr(session, "next_move_last_refresh_at", 0.0) or 0.0
    if time.time() - last_at < debounce_s:
        return False
    cache = getattr(session, "next_move_cache", {}) or {}
    if cache:
        basis_now = _context_basis_hash(session)
        if cache.get("context_basis_hash") == basis_now:
            return False
    return True


def format_for_brief(cache: dict | None) -> str:
    """Render the [RECOMMENDED NEXT MOVE] block, or "" if stale/empty.

    Returns a brief-ready string that build_pre_query_brief inserts verbatim.
    """
    if not cache:
        return ""
    generated_at = float(cache.get("generated_at") or 0.0)
    if generated_at <= 0:
        return ""
    age = time.time() - generated_at
    if age > settings.NEXT_MOVE_MAX_AGE_SECONDS:
        return ""
    text = (cache.get("text") or "").strip()
    if not text:
        return ""
    tier = "pro" if cache.get("is_pro") else "fast"
    return (
        f"[RECOMMENDED NEXT MOVE — precomputed {age:.1f}s ago, tier={tier}]\n"
        f"{text}\n"
        f"[/RECOMMENDED NEXT MOVE]\n"
        f"If the user's question is a short next-step ask (e.g. \"what now\", "
        f"\"trap?\", \"accept?\", \"best counter\"), use this as your primary "
        f"answer. If they ask something more specific, answer that precisely "
        f"and treat the above as background only."
    )


def _vague_user_query() -> str:
    """The synthetic user query used to drive Flash/Pro for the cache.

    Phrased to elicit a short, actionable recommendation the Live model can
    speak verbatim when the user asks "what now".
    """
    return (
        "What is the single best next move for me RIGHT NOW? Give the exact "
        "line to say (one short sentence), then in one short line each: what "
        "to protect, what to trade, and the main risk to watch."
    )


def _trace_event(session: "NegotiationSession", name: str, data: dict) -> None:
    try:
        from app.utils.session_trace import get_session_trace
        trace = get_session_trace(session.session_id)
        if trace:
            trace.record(
                category="ask_ai",
                name=name,
                summary=f"next_move_cache: {name}",
                data=data,
            )
    except Exception:
        pass


async def _generate_flash(session: "NegotiationSession") -> Optional[str]:
    """Fast recommendation via NEXT_MOVE_FAST_MODEL.

    Reuses build_advisor_query + the pre-query brief shape so the Flash call
    sees the same intel slice that Live and Pro see.
    """
    from app.ai_assets import build_pre_query_brief
    from app.services.gemini_client import build_advisor_query

    listener = getattr(session, "listener_agent", None)
    listener_ctx: dict = dict(getattr(listener, "last_context", {}) or {})
    user_ctx = session.user_context or {}
    transcript_text = (getattr(listener, "accumulated_transcript", "") or "")[-2000:] if listener else ""

    market_info = "Not yet researched"
    market_data = listener_ctx.get("market_data")
    if isinstance(market_data, str):
        market_info = market_data
    elif isinstance(market_data, dict):
        pr = market_data.get("price_range") or {}
        facts = market_data.get("key_facts", "")
        leverage = market_data.get("leverage", "")
        market_info = f"Fair range: {pr.get('min')} - {pr.get('max')} (avg {pr.get('average')})"
        if facts:
            market_info += f" | Facts: {facts}"
        if leverage:
            market_info += f" | Leverage: {leverage}"

    latest_vision = (
        session.vision_observations[-1]
        if getattr(session, "vision_observations", None)
        else None
    )

    intel = build_pre_query_brief(
        context=listener_ctx,
        market_info=market_info,
        transcript_text=transcript_text,
        vision_observation=latest_vision,
    )

    state_for_query = {
        **listener_ctx,
        "item": listener_ctx.get("item") or user_ctx.get("item", ""),
        "target_price": user_ctx.get("target_price") or listener_ctx.get("user_target_price"),
        "max_price": user_ctx.get("max_price") or listener_ctx.get("user_walk_away_price"),
        "language": session.language,
        "response_language": session.response_language or session.language or "en-US",
    }

    advisor_query = build_advisor_query(
        state=state_for_query,
        transcript=transcript_text,
        user_query=_vague_user_query(),
    )

    prompt = f"{intel}\n\n{advisor_query}"

    if settings.GOOGLE_GENAI_USE_VERTEXAI:
        client = genai.Client(
            vertexai=True,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        )
    else:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

    from app.ai_assets import qualify_model_name
    model_name = qualify_model_name(settings.NEXT_MOVE_FAST_MODEL, settings.GOOGLE_GENAI_USE_VERTEXAI)

    config_kwargs = {
        "temperature": 0.2,
        "max_output_tokens": 512,
    }
    try:
        config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    except Exception:
        pass

    try:
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=model_name,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(**config_kwargs),
            ),
        )
    except Exception as exc:
        logger.warning("[next_move_cache] flash call failed session=%s err=%s", session.session_id, exc)
        return None

    text = (getattr(response, "text", None) or "").strip()
    return text or None


async def _generate_pro(session: "NegotiationSession") -> Optional[str]:
    """Pro upgrade via existing generate_tactical_advice."""
    from app.services.gemini_client import generate_tactical_advice
    try:
        return await generate_tactical_advice(
            session=session,
            user_query=_vague_user_query(),
            response_mode="advice",
        )
    except Exception as exc:
        logger.warning("[next_move_cache] pro upgrade failed session=%s err=%s", session.session_id, exc)
        return None


async def refresh_next_move(session: "NegotiationSession") -> None:
    """Background task: refresh session.next_move_cache.

    Safe to call concurrently — earlier in-flight tasks are cancelled by the
    caller (listener_agent). Debounce + basis-hash guard against wasted spend.
    """
    if not should_refresh_cache(session):
        return

    session.next_move_last_refresh_at = time.time()
    basis = _context_basis_hash(session)
    _trace_event(session, "next_move_cache_started", {"basis": basis[:12]})

    fast_text: Optional[str] = None
    try:
        fast_text = await asyncio.wait_for(
            _generate_flash(session),
            timeout=settings.NEXT_MOVE_FAST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.info("[next_move_cache] flash timeout session=%s", session.session_id)
    except Exception as exc:
        logger.warning("[next_move_cache] flash error session=%s err=%s", session.session_id, exc)

    if fast_text:
        # Only overwrite if a newer Flash entry hasn't already landed.
        existing = session.next_move_cache or {}
        if existing.get("context_basis_hash") != basis or not existing.get("is_pro"):
            session.next_move_cache = {
                "text": fast_text,
                "model": settings.NEXT_MOVE_FAST_MODEL,
                "generated_at": time.time(),
                "context_basis_hash": basis,
                "is_pro": False,
            }
            _trace_event(session, "next_move_cache_ready", {
                "basis": basis[:12],
                "chars": len(fast_text),
                "tier": "fast",
            })

    if not settings.NEXT_MOVE_PRO_UPGRADE_ENABLED:
        return

    pro_text: Optional[str] = None
    try:
        pro_text = await asyncio.wait_for(
            _generate_pro(session),
            timeout=settings.NEXT_MOVE_PRO_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.info("[next_move_cache] pro timeout session=%s", session.session_id)
    except Exception as exc:
        logger.warning("[next_move_cache] pro error session=%s err=%s", session.session_id, exc)

    if pro_text:
        # Only replace if basis hash still matches — otherwise a newer refresh
        # ran underneath us and we'd be writing a stale Pro answer.
        current = session.next_move_cache or {}
        if current.get("context_basis_hash") == basis:
            session.next_move_cache = {
                "text": pro_text,
                "model": settings.ADVICE_GENERATION_MODEL,
                "generated_at": time.time(),
                "context_basis_hash": basis,
                "is_pro": True,
            }
            _trace_event(session, "next_move_pro_upgrade_ready", {
                "basis": basis[:12],
                "chars": len(pro_text),
                "tier": "pro",
            })
        else:
            _trace_event(session, "next_move_pro_upgrade_dropped_stale", {"basis": basis[:12]})


def schedule_refresh(session: "NegotiationSession") -> None:
    """Fire-and-forget scheduler hooked from listener_agent._on_context_ready.

    Cancels any in-flight refresh whose context is now stale.
    """
    if not settings.NEXT_MOVE_CACHE_ENABLED:
        return
    if not should_refresh_cache(session):
        return
    prev = getattr(session, "next_move_task", None)
    if prev is not None and not prev.done():
        prev.cancel()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    session.next_move_task = loop.create_task(refresh_next_move(session))
