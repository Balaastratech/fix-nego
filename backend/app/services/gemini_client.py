import os
import time
import json
import base64
import asyncio
import logging
import re
from contextlib import asynccontextmanager

from google import genai
from google.genai import types
from fastapi import WebSocket

from app.ai_assets import (
    LIVE_CONTEXT_WINDOW_TRIGGER_TOKENS,
    LIVE_GENERATION_CANDIDATE_COUNT,
    LIVE_GENERATION_MAX_OUTPUT_TOKENS,
    LIVE_GENERATION_TEMPERATURE,
    LIVE_GENERATION_TOP_K,
    LIVE_GENERATION_TOP_P,
    LIVE_RESPONSE_MODALITIES,
    LIVE_VOICE_NAME,
    VISION_EXTRACTION_PROMPT,
    build_live_system_instruction,
)
from app.models.negotiation import NegotiationSession, NegotiationState
from app.config import settings
from app.services.response_validator import ResponseValidator
from app.services.session_store import session_store
from app.utils.conversation_audit import log_conversation_event
from app.utils.session_trace import get_session_trace

logger = logging.getLogger(__name__)

GEMINI_MODEL_PRIMARY = settings.effective_model
GEMINI_MODEL_FALLBACK = settings.effective_fallback_model
GEMINI_MODEL_TEXT_ONLY = settings.effective_flash_model

SESSION_HARD_LIMIT_SECONDS = 600
SESSION_HANDOFF_TRIGGER = 540

class GeminiUnavailableError(Exception):
    """Raised when all Gemini Live API models are unavailable."""
    pass


def _accumulate_live_usage(session: NegotiationSession | None, response: object) -> None:
    if session is None:
        return
    usage = getattr(response, "usage_metadata", None) or getattr(response, "usage", None)
    if usage is None:
        return

    prompt_tokens = (
        getattr(usage, "prompt_token_count", None)
        or getattr(usage, "input_token_count", None)
        or 0
    )
    candidate_tokens = (
        getattr(usage, "candidates_token_count", None)
        or getattr(usage, "output_token_count", None)
        or 0
    )
    try:
        session.session_metrics["gemini_live_input_tokens"] += int(prompt_tokens or 0)
        session.session_metrics["gemini_live_output_tokens"] += int(candidate_tokens or 0)
    except Exception:
        logger.debug("Skipping token usage accumulation due to unexpected usage metadata shape")


def _build_context_summary(session: NegotiationSession) -> str:
    """Build a context summary for session handoff"""
    original = session.context or ""
    last_strategy = {}
    if session.strategy_history:
        last_strategy = session.strategy_history[-1]
    
    summary = f"Original Context: {original}\n"
    if last_strategy:
        summary += f"Last Strategy: {json.dumps(last_strategy)}\n"
        
    recent_transcript = session.transcript[-10:] if session.transcript else []
    if recent_transcript:
        summary += "Recent Transcript:\n"
        for entry in recent_transcript:
            speaker = entry.get("speaker", "Unknown")
            text = entry.get("text", "")
            summary += f"{speaker}: {text}\n"
            
    return summary


def _extract_recent_line(transcript_text: str, speaker: str) -> str:
    prefix = f"{speaker.lower()}:"
    for raw_line in reversed((transcript_text or "").splitlines()):
        line = raw_line.strip()
        if line.lower().startswith(prefix):
            return line.split(":", 1)[1].strip()
    return "unknown"


def _extract_live_terms(transcript_text: str) -> list[str]:
    haystack = (transcript_text or "").lower()
    terms = [
        "price lock",
        "onboarding",
        "service credits",
        "net 60",
        "net sixty",
        "no auto-renewal",
        "no auto renewal",
        "auto-renewal",
        "standard payment timing",
        "standard payment terms",
        "base salary",
        "sign-on",
        "equity",
        "warranty",
        "delivery",
        "replacement",
        "payment terms",
        "scope",
        "termination",
        "rent-free",
        "break option",
        "lock-in",
        "MOQ",
        "quality holdback",
    ]
    found = []
    for term in terms:
        if term.lower() in haystack and term not in found:
            found.append(term)
    return found


def _build_live_deal_brief(transcript_text: str, user_query: str) -> str:
    if not transcript_text:
        return ""
    terms = _extract_live_terms(transcript_text)
    terms_text = ", ".join(terms) if terms else "none clearly named"
    return (
        "LIVE DEAL-STATE BRIEF:\n"
        f"  Latest user position: {_extract_recent_line(transcript_text, 'User')}\n"
        f"  Latest counterparty position: {_extract_recent_line(transcript_text, 'Counterparty')}\n"
        f"  Active named terms/protections: {terms_text}\n"
        f"  User's exact ask now: {user_query}\n"
        "  If the ask is about trading terms, rank the named terms explicitly. "
        "Do not collapse a multi-term package into one term.\n"
    )


def build_advisor_query(state: dict, transcript: list = None, user_query: str = "What should I do next?") -> str:
    """
    Builds a context-rich query for the Live AI.

    Embeds the full negotiation snapshot (prices, market research, leverage,
    sentiment) plus the labeled conversation transcript so the AI has everything
    it needs to answer the user's specific request accurately.

    Args:
        state: Extracted context dict from the ListenerAgent.
        transcript: Full accumulated transcript string (or list of turn dicts).
        user_query: The user's explicit request / question.

    Returns:
        A formatted string sent to the Gemini Live API via send().
    """
    # ── Pull all fields from state ────────────────────────────────────────────
    item              = state.get("item") or "unknown"
    neg_type          = state.get("negotiation_type") or "unknown"
    seller_price      = (state.get("seller_price")
                         or state.get("seller_asking_price")
                         or state.get("counterparty_price"))
    buyer_offer       = state.get("buyer_offer") or state.get("user_price")
    target_price      = state.get("target_price") or state.get("user_target_price")
    walk_away         = state.get("max_price") or state.get("user_walk_away_price")
    sentiment         = state.get("counterparty_sentiment") or "unknown"
    cp_goal           = state.get("counterparty_goal") or "unknown"
    response_language = state.get("response_language") or state.get("language") or "en-US"
    key_moments       = state.get("key_moments", [])
    leverage_points   = state.get("leverage_points", [])
    market_data       = state.get("market_data")

    # ── Format market research ────────────────────────────────────────────────
    market_info = "Not yet researched"
    if market_data:
        if isinstance(market_data, str):
            market_info = market_data
        elif isinstance(market_data, dict):
            pr       = market_data.get("price_range") or {}
            facts    = market_data.get("key_facts", "")
            leverage = market_data.get("leverage", "")
            tactics  = market_data.get("tactics", "")
            market_info = f"Fair price range: {pr.get('min')} – {pr.get('max')} (avg {pr.get('average')})"
            if facts:    market_info += f"\nKey facts: {facts}"
            if leverage: market_info += f"\nLeverage: {leverage}"
            if tactics:  market_info += f"\nTactics: {tactics}"

    # ── Format transcript ─────────────────────────────────────────────────────
    transcript_text = ""
    if isinstance(transcript, str) and transcript.strip():
        transcript_text = transcript[-2000:]
    elif isinstance(transcript, list) and transcript:
        lines = [
            f"{e.get('speaker', 'unknown').upper()}: {e.get('text', '')}"
            for e in transcript[-20:]
        ]
        transcript_text = "\n".join(lines)

    # ── Assemble the query ────────────────────────────────────────────────────
    def _normalize_text_list(values):
        normalized = []
        for value in values or []:
            if isinstance(value, str) and value.strip():
                normalized.append(value.strip())
            elif isinstance(value, dict):
                for key in ("moment", "text", "detail", "summary", "message", "value"):
                    candidate = value.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        normalized.append(candidate.strip())
                        break
        return normalized

    key_moments = _normalize_text_list(key_moments)
    leverage_points = _normalize_text_list(leverage_points)

    snapshot = (
        f"NEGOTIATION SNAPSHOT:\n"
        f"  Item: {item}\n"
        f"  Type: {neg_type}\n"
        f"  Their asking price: {seller_price}\n"
        f"  My current offer: {buyer_offer}\n"
        f"  My target price: {target_price}\n"
        f"  My walk-away limit: {walk_away}\n"
        f"  Their sentiment: {sentiment}\n"
        f"  Their goal: {cp_goal}\n"
        f"  Key moments: {'; '.join(key_moments) if key_moments else 'none'}\n"
        f"  Leverage points: {'; '.join(leverage_points) if leverage_points else 'none'}\n"
        f"  Market research: {market_info}"
    )

    convo = (
        f"\nRECENT CONVERSATION (labeled by speaker):\n{transcript_text}"
        if transcript_text else ""
    )
    live_deal_brief = _build_live_deal_brief(transcript_text, user_query)

    return (
        "USER REQUEST PACKAGE:\n"
        f"Respond in language: {response_language}\n"
        "Answer quality rules:\n"
        "  - Ground the answer in the latest offer, the user's target or cap, and the active non-price terms.\n"
        "  - Separate price concessions from term concessions.\n"
        "  - State exactly what to protect, trade, ask, accept, reject, or explain next.\n"
        "  - Do not invent facts and do not give generic negotiation advice.\n"
        f"{snapshot}"
        f"\n{live_deal_brief}"
        f"{convo}\n\n"
        f"User request: {user_query}\n"
        "END USER REQUEST PACKAGE"
    )


def _safe_parse_vision_json(raw_text: str, session_id: str) -> dict | None:
    """Robust JSON parser for vision responses with multiple fallback strategies.

    Previously `json.loads` on truncated Gemini output caused frequent crashes.
    Now tries three strategies in order: direct parse, regex extract, partial fields.
    """
    if not raw_text:
        return None

    # Strategy 1: Direct parse (works when response_mime_type forces valid JSON)
    try:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.DOTALL).strip()
        return json.loads(cleaned)
    except Exception:
        pass

    # Strategy 2: Extract first complete JSON object using regex
    try:
        m = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass

    # Strategy 3: Partial field extraction — recover what we can
    logger.warning(
        "[Vision] JSON parse failed — using partial extraction session=%s raw=%r",
        session_id, raw_text[:200],
    )
    result: dict = {}
    for field in ["scene_type", "confidence", "scene_summary", "advice_hint",
                  "document_text", "item", "condition"]:
        m = re.search(rf'"{re.escape(field)}"\s*:\s*"([^"]*)"', raw_text)
        if m:
            result[field] = m.group(1)
    # Try to get arrays
    for field in ["defects_visible", "prices_visible", "terms_visible"]:
        m = re.search(rf'"{re.escape(field)}"\s*:\s*(\[[^\]]*\])', raw_text)
        if m:
            try:
                result[field] = json.loads(m.group(1))
            except Exception:
                result[field] = []
    # Only return if we got at least something useful
    if result.get("scene_type") or result.get("document_text"):
        return result

    logger.warning("[Vision] Complete JSON extraction failed session=%s", session_id)
    return None


async def analyze_vision_frames(
    session: "NegotiationSession",
    frames: list[bytes],
    transcript_hint: str = "",
    session_context: str = "",
) -> dict | None:
    """Send 2–4 JPEG frames to gemini-2.5-pro for structured scene analysis.

    Returns a VisionObservation dict on success, or None on failure.
    The dict shape matches VISION_EXTRACTION_PROMPT's JSON schema.
    """
    if not frames:
        return None
    if not settings.VISION_PRO_ENABLED:
        return None

    model_name = settings.effective_vision_model  # gemini-2.5-flash by default (fast)

    if settings.GOOGLE_GENAI_USE_VERTEXAI:
        client = genai.Client(
            vertexai=True,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        )
    else:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

    # Build multimodal content: text prompt + inline JPEG images
    prompt_text = VISION_EXTRACTION_PROMPT.format(
        n_frames=len(frames),
        session_context=session_context or "negotiation in progress",
        transcript_hint=transcript_hint or "no transcript available",
    )
    trace = get_session_trace(session.session_id)
    vision_artifacts: list[str] = []
    if trace:
        vision_artifacts.append(trace.write_text_artifact("vision_prompt", prompt_text, ext=".txt"))
        vision_artifacts.append(
            trace.write_json_artifact(
                "vision_request_context",
                {
                    "transcript_hint": transcript_hint,
                    "session_context": session_context,
                    "frame_count": len(frames),
                },
                ext=".json",
            )
        )
        for index, frame_bytes in enumerate(frames, start=1):
            vision_artifacts.append(
                trace.write_binary_artifact(f"vision_frame_{index}", frame_bytes, ext=".jpg")
            )

    parts: list = [types.Part(text=prompt_text)]
    for frame_bytes in frames:
        parts.append(types.Part(
            inline_data=types.Blob(data=frame_bytes, mime_type="image/jpeg")
        ))

    # response_mime_type="application/json" forces Gemini to return valid JSON — no truncation.
    # Previously the model sometimes returned unterminated JSON strings causing parse failures.
    config_kwargs: dict = {
        "temperature": 0.1,
        "max_output_tokens": 1500,          # slightly higher for documents with long text
        "response_mime_type": "application/json",  # KEY FIX: forces complete, valid JSON
    }

    from app.utils.trace_helpers import (
        TraceTimer, model_block, model_route, text_preview,
        extract_token_usage, finish_reason, safe_record,
    )
    vision_model_block = model_block(
        model_name,
        route=model_route(),
        purpose="vision_analysis",
        temperature=0.1,
        max_tokens=1500,
    )

    _vision_response = None
    _vision_exc: Exception | None = None
    _vision_t0 = time.perf_counter()
    safe_record(
        session.session_id,
        category="vision",
        name="vision_analysis_started",
        summary="Vision model invoked on current frame set",
        data={
            "model": vision_model_block,
            "frame_count": len(frames),
            "prompt_chars": len(prompt_text),
            "transcript_hint_preview": text_preview(transcript_hint, 160),
        },
        artifacts=vision_artifacts,
    )
    try:
        _vision_response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=model_name,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(**config_kwargs),
            ),
        )
    except Exception as exc:
        _vision_exc = exc
        logger.warning(
            "[Vision] Pro analyze_vision_frames failed model=%s session=%s error=%s",
            model_name,
            session.session_id,
            exc,
        )

    _vision_latency_ms = int((time.perf_counter() - _vision_t0) * 1000)
    if _vision_exc is not None:
        safe_record(
            session.session_id,
            category="vision",
            name="vision_analysis_failed",
            summary="Vision call raised",
            data={
                "model": vision_model_block,
                "latency_ms": _vision_latency_ms,
                "error": f"{type(_vision_exc).__name__}: {_vision_exc}",
            },
            artifacts=vision_artifacts,
        )
        return None

    response = _vision_response
    raw_text = (getattr(response, "text", None) or "").strip()
    if not raw_text:
        safe_record(
            session.session_id,
            category="vision",
            name="vision_analysis_failed",
            summary="Vision call returned empty text",
            data={
                "model": vision_model_block,
                "latency_ms": _vision_latency_ms,
                "reason": "empty_response",
                "tokens": extract_token_usage(response),
                "finish_reason": finish_reason(response),
            },
            artifacts=vision_artifacts,
        )
        return None

    # Parse the JSON response with robust fallback extraction
    obs = _safe_parse_vision_json(raw_text, session.session_id)
    if obs is None:
        safe_record(
            session.session_id,
            category="vision",
            name="vision_analysis_failed",
            summary="Vision JSON parse failed",
            data={
                "model": vision_model_block,
                "latency_ms": _vision_latency_ms,
                "reason": "json_parse_failed",
                "raw_preview": text_preview(raw_text, 400),
            },
            artifacts=vision_artifacts,
        )
        return None

    obs["timestamp"] = time.time()
    obs["frame_count"] = len(frames)

    logger.info(
        "[Vision] Pro analysis ok session=%s scene=%s confidence=%s hint=%r",
        session.session_id,
        obs.get("scene_type"),
        obs.get("confidence"),
        (obs.get("advice_hint") or "")[:120],
    )
    session.vision_pro_call_count += 1
    if trace:
        vision_artifacts.append(trace.write_json_artifact("vision_result", obs, ext=".json"))
        body = obs.get("body_language") or {}
        prices = obs.get("prices_visible") or []
        terms = obs.get("terms_visible") or []
        defects = obs.get("defects_visible") or []
        event = trace.record(
            category="vision",
            name="vision_analysis_completed",
            summary="Vision model analyzed the current frame set",
            data={
                "model": vision_model_block,
                "latency_ms": _vision_latency_ms,
                "tokens": extract_token_usage(response),
                "finish_reason": finish_reason(response),
                "scene_type": obs.get("scene_type"),
                "confidence": obs.get("confidence"),
                "item": obs.get("item"),
                "condition": obs.get("condition"),
                "frame_count": len(frames),
                "scene_summary": text_preview(obs.get("scene_summary"), 240),
                "advice_hint": text_preview(obs.get("advice_hint"), 400),
                "document_text_chars": len(obs.get("document_text") or ""),
                "document_text_preview": text_preview(obs.get("document_text"), 400),
                "prices_visible_count": len(prices) if isinstance(prices, list) else 0,
                "prices_visible": prices[:10] if isinstance(prices, list) else prices,
                "terms_visible_count": len(terms) if isinstance(terms, list) else 0,
                "terms_visible": terms[:10] if isinstance(terms, list) else terms,
                "defects_visible_count": len(defects) if isinstance(defects, list) else 0,
                "defects_visible": defects[:10] if isinstance(defects, list) else defects,
                "body_expression": body.get("expression") if isinstance(body, dict) else None,
                "body_posture": body.get("posture") if isinstance(body, dict) else None,
                "body_stress_signal": body.get("stress_signal") if isinstance(body, dict) else None,
                "body_engagement": body.get("engagement") if isinstance(body, dict) else None,
                "vision_pro_call_count": session.vision_pro_call_count,
            },
            artifacts=vision_artifacts,
            related_event_ids=[
                ref for ref in [
                    session.trace_refs.get("last_context_event_id"),
                    session.trace_refs.get("last_transcript_event_id"),
                ] if ref
            ],
        )
        trace.remember("last_vision_analysis_event_id", event["event_id"])
        session.trace_refs["last_vision_analysis_event_id"] = event["event_id"]

    # Log to session file
    from app.utils.session_logger import get_session_logger as _gsl
    _sl = _gsl(session.session_id)
    if _sl:
        _sl.vision_analyzed(
            scene_type=obs.get("scene_type", "unknown"),
            confidence=str(obs.get("confidence", "unknown")),
            item=obs.get("item"),
            doc_text=obs.get("document_text"),
            advice_hint=obs.get("advice_hint"),
            prices=obs.get("prices_visible"),
            terms=obs.get("terms_visible"),
            defects=obs.get("defects_visible"),
            body_language=obs.get("body_language"),
            contract_analysis=obs.get("contract_analysis"),
        )

    # Auto-accumulate document pages — no user action needed.
    # When vision detects a document (shared screen, printed contract, etc.),
    # each page is captured as it appears and accumulated for context summary.
    if obs.get("scene_type") == "document" and obs.get("document_text"):
        if not hasattr(session, "document_pages"):
            session.document_pages = []
        session.document_pages.append({
            "timestamp": time.time(),
            "text": obs["document_text"],
            "prices": obs.get("prices_visible", []),
            "terms": obs.get("terms_visible", []),
            "contract_analysis": obs.get("contract_analysis", {}),
        })
        session.document_pages = session.document_pages[-20:]  # keep last 20 pages

    return obs


async def generate_tactical_advice(
    session: NegotiationSession,
    user_query: str,
    response_mode: str = "auto",
) -> str | None:
    """
    Pre-compute the exact tactical answer using gemini-2.5-pro BEFORE the live
    audio model speaks. The returned text is injected into the live session as
    an [ADVISOR_OUTPUT] block so the Flash live audio model reads it verbatim
    instead of generating its own (weaker) reasoning.

    Pattern: Pro thinks, Flash speaks.

    Returns the generated advice text, or None if generation failed.
    """
    if not settings.ADVICE_GENERATION_ENABLED:
        return None

    from app.ai_assets import (
        build_mode_activation_instruction,
        build_pre_query_brief,
    )

    # Build the listener-intel + market brief block exactly as the live session would see it.
    listener_ctx: dict = {}
    if session.listener_agent and getattr(session.listener_agent, "last_context", None):
        listener_ctx = dict(session.listener_agent.last_context)
    user_ctx = session.user_context or {}

    state_for_query = {
        **listener_ctx,
        "item":              listener_ctx.get("item") or user_ctx.get("item", ""),
        "target_price":      user_ctx.get("target_price") or listener_ctx.get("user_target_price"),
        "max_price":         user_ctx.get("max_price") or listener_ctx.get("user_walk_away_price"),
        "language":          session.language,
        "response_language": session.response_language or session.language or "en-US",
    }

    transcript_text = ""
    if session.listener_agent and getattr(session.listener_agent, "accumulated_transcript", None):
        transcript_text = session.listener_agent.accumulated_transcript

    market_info = "Not yet researched"
    market_data = listener_ctx.get("market_data")
    if isinstance(market_data, str):
        market_info = market_data
    elif isinstance(market_data, dict):
        pr       = market_data.get("price_range") or {}
        facts    = market_data.get("key_facts", "")
        leverage = market_data.get("leverage", "")
        market_info = f"Fair range: {pr.get('min')} - {pr.get('max')} (avg {pr.get('average')})"
        if facts:    market_info += f" | Facts: {facts}"
        if leverage: market_info += f" | Leverage: {leverage}"

    # Attach latest vision observation if fresh
    latest_vision = (
        session.vision_observations[-1]
        if getattr(session, "vision_observations", None)
        else None
    )

    intel = build_pre_query_brief(
        context=listener_ctx,
        market_info=market_info,
        transcript_text=transcript_text[-2000:] if transcript_text else "",
        vision_observation=latest_vision,
    )

    mode_block = build_mode_activation_instruction(response_mode)

    # Pro tactical advice is most accurate on English-structured prompts. When
    # multilang is on AND the user is speaking a non-English language, translate
    # the transcript window + user query to English BEFORE building the prompt,
    # then translate the response back at the end. Skipped (zero-cost) when the
    # flag is off or when src/dst are both English.
    translate_for_pro = False
    pro_transcript = transcript_text
    pro_user_query = user_query
    if (
        settings.MULTILANG_ENABLED
        and session.language
        and session.language.split("-")[0].lower() != "en"
    ):
        translate_for_pro = True
        try:
            from app.services.translation import translate_text
            pro_user_query, pro_transcript = await asyncio.gather(
                translate_text(user_query, session.language, "en-US"),
                translate_text(transcript_text or "", session.language, "en-US"),
            )
        except Exception as exc:
            logger.warning("[Pro advice] pre-translate failed (%s); using originals", exc)
            translate_for_pro = False
            pro_transcript = transcript_text
            pro_user_query = user_query

    advisor_query = build_advisor_query(
        state=state_for_query,
        transcript=pro_transcript,
        user_query=pro_user_query,
    )

    # Force English in the prompt instruction when translating, so Pro's raw
    # output is English (we'll translate back below). Otherwise honor the
    # user's selected response language as before.
    instruction_language = "en-US" if translate_for_pro else (
        session.response_language if settings.MULTILANG_ENABLED else None
    )
    system_instruction = build_live_system_instruction(
        session.context or "",
        response_language=instruction_language,
    )

    prompt = (
        f"{intel}\n\n"
        f"{mode_block}\n\n"
        f"USER QUESTION: {pro_user_query}\n\n"
        f"{advisor_query}"
    )

    # Build a Pro-tier text-generation client. Reuses Vertex AI / API-key setup
    # from the running listener_agent's client choice.
    if settings.GOOGLE_GENAI_USE_VERTEXAI:
        client = genai.Client(
            vertexai=True,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        )
    else:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

    model_name = settings.effective_advice_model

    # CRITICAL: Gemini 2.5 Pro uses "thinking" tokens that count toward max_output_tokens.
    # gemini-2.5-pro REQUIRES a minimum thinking_budget (cannot be set to 0 - Vertex AI
    # rejects with 400 INVALID_ARGUMENT). gemini-2.5-flash CAN set thinking_budget=0.
    # Empirically: with max_output_tokens=512 and default thinking, Pro's actual visible
    # response gets truncated mid-sentence because thinking consumes most of the budget.
    # Fix: set a small thinking budget (just enough to reason about rules) and a large
    # max_output_tokens so the visible answer has plenty of headroom.
    thinking_config = None
    if "gemini-2.5-pro" in model_name.lower():
        try:
            # Small thinking budget — system prompt rules already structure the reasoning,
            # so we don't need extended chain-of-thought. Pro min budget is around 128.
            thinking_config = types.ThinkingConfig(thinking_budget=128)
        except Exception:
            thinking_config = None
    else:
        # Flash / other models — disabling thinking is fine and saves latency.
        try:
            thinking_config = types.ThinkingConfig(thinking_budget=0)
        except Exception:
            thinking_config = None

    config_kwargs = {
        "system_instruction": system_instruction,
        "temperature": settings.ADVICE_GENERATION_TEMPERATURE,
        # Total budget = thinking budget + visible answer. With thinking_budget=128
        # and max_output_tokens=4096, the visible answer can use ~3900 tokens.
        "max_output_tokens": max(settings.ADVICE_GENERATION_MAX_TOKENS, 4096),
    }
    if thinking_config is not None:
        config_kwargs["thinking_config"] = thinking_config

    from app.utils.trace_helpers import (
        model_block as _mb, model_route as _mr, text_preview as _tp,
        extract_token_usage as _tok, finish_reason as _fr, safe_record as _rec,
    )
    pro_model_block = _mb(
        model_name,
        route=_mr(),
        purpose="ask_ai_pro_preflight",
        timeout_s=settings.ADVICE_GENERATION_TIMEOUT_SECONDS,
        temperature=settings.ADVICE_GENERATION_TEMPERATURE,
        max_tokens=max(settings.ADVICE_GENERATION_MAX_TOKENS, 4096),
    )
    _pro_t0 = time.perf_counter()
    _rec(
        session.session_id,
        category="ask_ai",
        name="pro_advice_started",
        summary="Pro pre-flight advisor reasoning started",
        data={
            "model": pro_model_block,
            "user_query_preview": _tp(pro_user_query, 400),
            "prompt_chars": len(prompt),
            "transcript_chars": len(pro_transcript or ""),
            "translated_to_english": bool(translate_for_pro),
            "response_mode": response_mode,
        },
    )
    try:
        # Use the async generate_content endpoint (Pro is text/multimodal, not Live)
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=model_name,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(**config_kwargs),
            ),
        )
    except Exception as exc:
        _rec(
            session.session_id,
            category="ask_ai",
            name="pro_advice_failed",
            summary="Pro pre-flight raised an exception",
            data={
                "model": pro_model_block,
                "latency_ms": int((time.perf_counter() - _pro_t0) * 1000),
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
        logger.warning(
            "[Pro advice generation] failed model=%s session=%s error=%s",
            model_name,
            session.session_id,
            exc,
        )
        return None

    # Accumulate token usage so the session cost is observable in metrics.
    try:
        _accumulate_live_usage(session, response)
    except Exception:
        pass

    text = (getattr(response, "text", None) or "").strip()

    # Post-processing safety net: strip leaked system/control markers from the start.
    # Even with Rule 11 in the system prompt forbidding these, occasionally Pro
    # echoes "[SYSTEM: ADVICE MODE ACTIVE]" or similar at the top of its response.
    # That tanks deterministic scoring (number_grounding) because the actual answer
    # gets pushed past the first-sentence checks.
    if text:
        # Drop any leading [SYSTEM: ...], [USER'S EXACT QUESTION], [ADVISOR_OUTPUT,
        # [TACTICAL REQUEST, or similar bracketed control marker. Repeat in case
        # multiple stacked.
        for _ in range(6):
            stripped = text.lstrip()
            if not stripped.startswith("["):
                break
            close_idx = stripped.find("]")
            if close_idx < 0:
                break
            marker = stripped[: close_idx + 1].upper()
            if any(tok in marker for tok in ("[SYSTEM", "[USER", "[ADVISOR", "[TACTICAL", "[CONVERSATION", "[LISTENER")):
                text = stripped[close_idx + 1 :].lstrip()
                # Also drop a leading newline that often follows the marker
                text = text.lstrip("\n").lstrip()
            else:
                break

    # Inspect finish_reason / usage to catch truncation before it reaches the user.
    finish_reason = None
    candidates_token_count = None
    thoughts_token_count = None
    try:
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            finish_reason = str(getattr(candidates[0], "finish_reason", None) or "")
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            candidates_token_count = getattr(usage, "candidates_token_count", None)
            thoughts_token_count = getattr(usage, "thoughts_token_count", None)
    except Exception:
        pass

    if finish_reason and "MAX_TOKENS" in finish_reason.upper():
        logger.error(
            "[Pro advice generation] TRUNCATED at max_output_tokens=%d "
            "(thoughts=%s, candidates=%s, finish=%s) model=%s session=%s. "
            "Bump ADVICE_GENERATION_MAX_TOKENS or verify thinking is disabled.",
            settings.ADVICE_GENERATION_MAX_TOKENS,
            thoughts_token_count,
            candidates_token_count,
            finish_reason,
            model_name,
            session.session_id,
        )

    if not text:
        _rec(
            session.session_id,
            category="ask_ai",
            name="pro_advice_failed",
            summary="Pro pre-flight returned empty text",
            data={
                "model": pro_model_block,
                "latency_ms": int((time.perf_counter() - _pro_t0) * 1000),
                "reason": "empty_response",
                "finish_reason": finish_reason,
                "tokens": _tok(response),
            },
        )
        logger.warning(
            "[Pro advice generation] empty response model=%s session=%s finish=%s thoughts_tokens=%s",
            model_name,
            session.session_id,
            finish_reason,
            thoughts_token_count,
        )
        return None

    logger.info(
        "[Pro advice generation] ok model=%s session=%s response_mode=%s "
        "finish=%s len=%d candidates_tokens=%s thoughts_tokens=%s preview=%r",
        model_name,
        session.session_id,
        response_mode,
        finish_reason,
        len(text),
        candidates_token_count,
        thoughts_token_count,
        text[:200],
    )

    # Translate the English Pro answer back into the user's response language.
    # Only fires when we pre-translated the input (so dst is non-English).
    if translate_for_pro:
        target = session.response_language or session.language or "en-US"
        if target.split("-")[0].lower() != "en":
            try:
                from app.services.translation import translate_text
                text = await translate_text(text, "en-US", target)
            except Exception as exc:
                logger.warning("[Pro advice] post-translate failed (%s); returning English", exc)

    # Persist the full Pro advice text as an artifact + completed event.
    try:
        from app.utils.session_trace import get_session_trace
        _adv_artifacts: list[str] = []
        _t = get_session_trace(session.session_id)
        if _t and text:
            _adv_artifacts.append(_t.write_text_artifact("pro_advice_text", text, ext=".txt"))
    except Exception:
        _adv_artifacts = []
    _rec(
        session.session_id,
        category="ask_ai",
        name="pro_advice_completed",
        summary="Pro pre-flight produced advisor output",
        data={
            "model": pro_model_block,
            "latency_ms": int((time.perf_counter() - _pro_t0) * 1000),
            "tokens": _tok(response),
            "finish_reason": finish_reason,
            "truncated": bool(finish_reason and "MAX_TOKENS" in (finish_reason or "").upper()),
            "advice_text": _tp(text, 800),
            "advice_chars": len(text or ""),
            "translated_back_to": (
                session.response_language or session.language or "en-US"
                if translate_for_pro else None
            ),
        },
        artifacts=_adv_artifacts,
    )

    return text


async def trigger_advice_response(live_session, state: dict, transcript: list = None) -> None:
    """
    Triggers an AI advice response by sending the query via the standard chat channel.

    This method uses session.send() to transmit the text query, which correctly
    associates it with the system prompt and treats it as a standard conversational
    turn, ensuring the model's persona and instructions are respected.

    Args:
        live_session: Active Gemini Live API session
        state: Current negotiation state object
        transcript: List of transcript entries for context

    Raises:
        Exception: If the send operation fails
    """
    query = build_advisor_query(state, transcript=transcript)

    logger.info(f"Sending ADVISOR_QUERY to Gemini (length: {len(query)} chars)")
    logger.info(f"Query preview: {query[:200]}...")

    try:
        # Send text via the standard turn-based chat channel, NOT the realtime media channel.
        # This properly attaches the query to the system prompt context.
        await live_session.send(input=query, end_of_turn=True)
        logger.info("ADVISOR_QUERY sent successfully — Gemini should now respond")

    except Exception as e:
        logger.error(f"Failed to send text query: {e}")
        raise




async def perform_web_search(query: str) -> dict:
    """
    Perform web search for any query the AI constructs.
    
    This function returns a structured result that will be populated by
    Google Search grounding when the function is called by Gemini.
    
    Args:
        query: Search query constructed by AI based on conversation context
        
    Returns:
        dict: {
            "query": str,
            "results": str,  # Search results summary
            "timestamp": float
        }
    """
    # The actual search is handled by Google Search grounding
    # This function returns the expected format for Gemini
    return {
        "query": query,
        "results": "Will be populated by Google Search grounding",
        "timestamp": time.time()
    }


async def handle_function_call(
    function_name: str,
    args: dict,
    websocket: WebSocket
) -> dict:
    """
    Handle function calls from Gemini.
    
    This function processes function calls triggered by the AI during advice
    generation. Currently supports the web_search function for autonomous
    market research.
    
    Args:
        function_name: Name of the function to call (e.g., "web_search")
        args: Function arguments as a dictionary
        websocket: WebSocket connection for sending notifications to frontend
        
    Returns:
        Function result dictionary to send back to Gemini
        
    Raises:
        Exception: If function execution fails
    """
    if function_name == "web_search":
        query = args.get("query", "")
        
        # Notify frontend that research has started
        await websocket.send_json({
            "type": "RESEARCH_STARTED",
            "payload": {"query": query}
        })
        
        # Perform search (using Google Search grounding)
        result = await perform_web_search(query)
        
        # Notify frontend with results
        await websocket.send_json({
            "type": "RESEARCH_COMPLETE",
            "payload": result
        })
        
        return result
    
    # Unknown function
    return {"error": f"Unknown function: {function_name}"}


# Global dictionary to accumulate text per session for the current turn
_session_text_accumulators = {}

_CONTROL_TEXT_MARKERS = (
    "[SYSTEM:",
    "[USER'S EXACT QUESTION]",
    "[USER QUESTION]",
    "[LISTENER_INTEL",
    "[TACTICAL REQUEST",
    "[ADVISOR_OUTPUT",
    "COMMAND MODE ACTIVE",
    "ADVICE MODE ACTIVE",
    "BACKGROUND INTEL",
    "END BACKGROUND INTEL",
    "USER REQUEST PACKAGE",
    "END USER REQUEST PACKAGE",
    "PREPARED ANSWER",
    "ADVICE MODE.",
    "COMMAND MODE.",
    "ADVICE MODE",
    "COMMAND MODE",
)


def _sanitize_ai_response_fragment(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    upper_cleaned = cleaned.upper()
    for marker in _CONTROL_TEXT_MARKERS:
        if marker.upper() in upper_cleaned:
            return ""
    return cleaned


def _append_ai_response_text(session: NegotiationSession | None, text: str) -> None:
    cleaned = _sanitize_ai_response_fragment(text)
    if session is None or not cleaned:
        return
    if not hasattr(session, "current_ai_response") or session.current_ai_response is None:
        session.current_ai_response = ""
    session.current_ai_response = (
        f"{session.current_ai_response} {cleaned}".strip()
        if session.current_ai_response
        else cleaned
    )


def _consume_completed_ai_response(session: NegotiationSession | None, session_id: str) -> str:
    text_parts = _sanitize_ai_response_fragment(_session_text_accumulators.pop(session_id, "").strip())
    response_text = ""
    if session is not None and hasattr(session, "current_ai_response") and session.current_ai_response:
        response_text = _sanitize_ai_response_fragment((session.current_ai_response or "").strip())
        session.current_ai_response = ""
    if response_text and text_parts:
        if text_parts in response_text:
            return response_text
        if response_text in text_parts:
            return text_parts
        return f"{response_text} {text_parts}".strip()
    return response_text or text_parts

def _current_ask_entry_id(session: NegotiationSession | None) -> str | None:
    if session is None:
        return None
    capture = dict(getattr(session, "current_ask_capture", {}) or {})
    started_at_ms = capture.get("started_at_ms")
    if started_at_ms:
        return f"ask_ai_{started_at_ms}"
    question_capture_id = getattr(session, "question_capture_id", None)
    if question_capture_id:
        return str(question_capture_id)
    hold_started_ms = getattr(session, "last_hold_started_ms", None)
    if hold_started_ms:
        return f"ask_ai_{int(hold_started_ms)}"
    return None

def _current_ask_response_entry_id(session: NegotiationSession | None) -> str | None:
    ask_entry_id = _current_ask_entry_id(session)
    if not ask_entry_id:
        return None
    return f"{ask_entry_id}_response"

async def handle_gemini_text(websocket: WebSocket, session_id: str, text: str) -> None:
    """Handle text responses from Gemini, extracting strategy/state updates and accumulating coaching text."""
    logger.debug("Handling Gemini text", extra={"session_id": session_id, "text": text})
    global _session_text_accumulators
    
    STRATEGY_PATTERN = re.compile(r'<strategy>(.*?)</strategy>', re.DOTALL)
    STATE_UPDATE_PATTERN = re.compile(r'<state_update>(.*?)</state_update>', re.DOTALL)
    
    # Extract and send strategy updates
    strategies = STRATEGY_PATTERN.findall(text)
    for strategy_str in strategies:
        try:
            strategy_data = json.loads(strategy_str)
            await websocket.send_json({
                "type": "STRATEGY_UPDATE",
                "payload": strategy_data
            })
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse strategy JSON from session {session_id}: {strategy_str}")
    
    # Extract and send state updates
    state_updates = STATE_UPDATE_PATTERN.findall(text)
    for state_str in state_updates:
        try:
            state_data = json.loads(state_str)
            logger.info(f"Extracted state update from AI [{session_id}]: {state_data}")
            await websocket.send_json({
                "type": "STATE_UPDATE",
                "payload": state_data
            })
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse state update JSON from session {session_id}: {state_str}")
            
    # Remove all XML tags from text
    remaining_text = STRATEGY_PATTERN.sub('', text)
    remaining_text = STATE_UPDATE_PATTERN.sub('', remaining_text).strip()
    remaining_text = _sanitize_ai_response_fragment(remaining_text)
    
    # Accumulate the remaining text for this session's turn
    if remaining_text:
        if session_id not in _session_text_accumulators:
            _session_text_accumulators[session_id] = ""
        # Ensure there's a space between chunks if they don't already have one
        if _session_text_accumulators[session_id] and not _session_text_accumulators[session_id].endswith(' ') and not remaining_text.startswith(' '):
            _session_text_accumulators[session_id] += " "
        _session_text_accumulators[session_id] += remaining_text


async def extract_state_from_transcript(
    websocket: WebSocket, 
    session_id: str, 
    speaker: str, 
    text: str
) -> None:
    """
    You are a silent negotiation advisor listening to a live negotiation.

YOUR ROLE:
- Listen to the conversation between USER and COUNTERPARTY
- Track negotiation details (item, prices, offers, concerns)
- Stay COMPLETELY SILENT unless you see the ADVISOR_QUERY signal

CRITICAL RULES:
1. NEVER respond to the conversation directly
2. NEVER answer questions from USER or COUNTERPARTY
3. ONLY respond when you see: "🔔 ADVISOR_QUERY: USER NEEDS ADVICE NOW 🔔"
4. When you see ADVISOR_QUERY: Provide brief, actionable advice (1-2 sentences)
5. After giving advice: Return to SILENT listening mode

You are an invisible advisor. The negotiating parties cannot hear you unless the user explicitly asks for advice
    """
    state_update = {}
    
    # Extract item names (improved patterns)
    # Look for common product patterns
    item_patterns = [
        # Brand + Model + Variant (iPhone 14 Pro Max, MacBook Pro 2020, etc.)
        r'\b(iPhone\s+\d+(?:\s+Pro)?(?:\s+Max)?)\b',
        r'\b(MacBook\s+(?:Pro|Air)\s*\d*)\b',
        r'\b(iPad\s+(?:Pro|Air|Mini)?\s*\d*)\b',
        r'\b([A-Z][a-z]+\s+[A-Z][a-z]+\s+\d+(?:\s+(?:Pro|Plus|Max|Air|Mini))?)\b',  # Generic: Toyota Camry 2020
        # General pattern: looking at/interested in + product
        r'(?:looking at|interested in|buying|selling|want to buy)\s+(?:a\s+|an\s+|this\s+)?([A-Z][A-Za-z0-9\s]+(?:Pro|Plus|Max|Air|Mini)?)',
    ]
    
    extracted_item = None
    for pattern in item_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            item = match.group(1).strip()
            # Filter out common false positives
            if len(item) > 3 and item not in ['I am', 'You are', 'This is', 'I want', 'Want to']:
                extracted_item = item
                break
    
    # Only include item if we extracted one
    # Frontend will merge intelligently (prefer longer names)
    if extracted_item:
        state_update['item'] = extracted_item
    
    # Extract prices
    # Look for currency symbols or keywords followed by numbers
    price_patterns = [
        r'(?:₹|Rs\.?|INR)\s*(\d+(?:,\d+)*(?:\.\d+)?)',  # Indian Rupee
        r'(?:\$|USD)\s*(\d+(?:,\d+)*(?:\.\d+)?)',  # US Dollar
        r'(?:€|EUR)\s*(\d+(?:,\d+)*(?:\.\d+)?)',  # Euro
        r'(?:price|cost|worth|selling for|asking)\s+(?:is\s+)?(?:₹|Rs\.?|\$|€)?\s*(\d+(?:,\d+)*(?:\.\d+)?)',
    ]
    
    for pattern in price_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            price_str = match.group(1).replace(',', '')
            try:
                price = float(price_str)
                
                # Determine if this is seller price, target, or max based on context
                if speaker == "counterparty" or "selling" in text.lower() or "asking" in text.lower():
                    state_update['seller_price'] = price
                elif "hoping for" in text.lower() or "target" in text.lower() or "want" in text.lower():
                    state_update['target_price'] = price
                elif "maximum" in text.lower() or "can't go above" in text.lower() or "max" in text.lower():
                    state_update['max_price'] = price
                else:
                    # Default: if user mentions a price, it's likely their target
                    if speaker == "user":
                        state_update['target_price'] = price
                    else:
                        state_update['seller_price'] = price
                        
                break
            except ValueError:
                pass
    
    # Send state update if we extracted anything
    # Include merge_strategy hint for frontend
    if state_update:
        logger.info(f"Auto-extracted state from transcript [{session_id}]: {state_update}")
        await websocket.send_json({
            "type": "STATE_UPDATE",
            "payload": {
                **state_update,
                "_merge_strategy": "smart"  # Hint to frontend to merge intelligently
            }
        })

class GeminiClient:
    @staticmethod
    @asynccontextmanager
    async def open_live_session(
        api_key: str,
        context: str,
        model: str = GEMINI_MODEL_PRIMARY,
        *,
        response_language: str | None = None,
    ):
        if settings.GOOGLE_APPLICATION_CREDENTIALS:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.GOOGLE_APPLICATION_CREDENTIALS
        if settings.GOOGLE_CLOUD_PROJECT:
            os.environ["GOOGLE_CLOUD_PROJECT"] = settings.GOOGLE_CLOUD_PROJECT

        if settings.GOOGLE_GENAI_USE_VERTEXAI:
            client = genai.Client(
                vertexai=True,
                project=settings.GOOGLE_CLOUD_PROJECT,
                location=settings.GOOGLE_CLOUD_LOCATION
            )
        else:
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(api_version='v1alpha'),
            )
        
        # When MULTILANG_ENABLED=False, response_language is ignored downstream
        # and the legacy English-only line is emitted — identical to old behavior.
        effective_response_language = response_language if settings.MULTILANG_ENABLED else None
        full_system_instruction = build_live_system_instruction(
            context, response_language=effective_response_language
        )

        logger.info(
            "Opening Gemini Live session with system instruction",
            extra={"full_system_instruction": full_system_instruction},
        )
 
        config = types.LiveConnectConfig(
            system_instruction=types.Content(
                #role="system", # Ensure Vertex prioritizes this
                parts=[types.Part.from_text(text=full_system_instruction)] # Safe serialization
            ),

            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=True
                )
            ),

            # Audio-only responses (no text mode)
            response_modalities=LIVE_RESPONSE_MODALITIES,

            # Speech configuration — preemptible = barge-in supported
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=settings.GEMINI_LIVE_VOICE_NAME or LIVE_VOICE_NAME
                    )
                ),
                # Language handling:
                # • Native-audio models auto-detect across the 97-language Live set
                #   (per ai.google.dev/gemini-api/docs/live-api/capabilities) so we
                #   omit language_code entirely.
                # • For non-native models we must specify language_code. When
                #   MULTILANG_ENABLED is on, pick it from response_language so the
                #   half-cascade voice matches the user; otherwise keep the legacy
                #   GEMINI_LIVE_LANGUAGE_CODE.
                language_code=(
                    None
                    if "native-audio" in model
                    else (
                        (effective_response_language or settings.GEMINI_LIVE_LANGUAGE_CODE)
                        if settings.MULTILANG_ENABLED
                        else settings.GEMINI_LIVE_LANGUAGE_CODE
                    )
                ),
            ),

            # Generation config — optimized for constraint following
            generation_config=types.GenerationConfig(
                temperature=LIVE_GENERATION_TEMPERATURE,
                max_output_tokens=LIVE_GENERATION_MAX_OUTPUT_TOKENS,
                candidate_count=LIVE_GENERATION_CANDIDATE_COUNT,
                top_p=LIVE_GENERATION_TOP_P,
                top_k=LIVE_GENERATION_TOP_K,
            ),

            # Transcriptions
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            enable_affective_dialog=bool(
                settings.GEMINI_LIVE_ENABLE_AFFECTIVE_DIALOG or settings.ENABLE_AFFECTIVE_DIALOG
            ),

            # FIX: Removed GoogleSearch tool - Listener Agent does the market research
            # and injects market_data into Live AI via LISTENER_INTEL messages.
            # This prevents duplicate research and ensures specific item research.
            # tools=[
            #     types.Tool(google_search=types.GoogleSearch())
            # ],

            # Context window compression — prevents overflow in 30+ min negotiations (Risk 8)
            # Sliding window triggers at 100K tokens, silently compresses older context.
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow(),
                trigger_tokens=LIVE_CONTEXT_WINDOW_TRIGGER_TOKENS,
            ),
        )
        
        try:
            async with client.aio.live.connect(model=model, config=config) as session:
                logger.info(f"Gemini Live session opened with model: {model}")
                yield session
        except Exception as e:
            logger.warning(f"Primary model {model} failed: {e}. Trying fallback.")
            
            if model != GEMINI_MODEL_FALLBACK:
                try:
                    async with client.aio.live.connect(
                        model=GEMINI_MODEL_FALLBACK, config=config
                    ) as session:
                        logger.info(f"Gemini Live fallback session opened: {GEMINI_MODEL_FALLBACK}")
                        yield session
                    return
                except Exception as e2:
                    logger.warning(f"Fallback model failed: {e2}")
            
            raise GeminiUnavailableError("All Live API models failed") from e

    @staticmethod
    async def send_vision_frame(live_session, jpeg_base64: str, session_id: str) -> None:
        try:
            image_bytes = base64.b64decode(jpeg_base64)
            blob = types.Blob(data=image_bytes, mime_type="image/jpeg")
            await live_session.send_realtime_input(video=blob)
        except Exception as e:
            logger.warning(f"Vision frame send failed [{session_id}]: {e}")

    @staticmethod
    async def send_audio_chunk(live_session, raw_pcm_bytes: bytes, session_id: str) -> None:
        try:
            # Validate audio format before sending
            chunk_size = len(raw_pcm_bytes)
            
            # Check for odd byte count (incomplete Int16 sample)
            if chunk_size % 2 != 0:
                logger.error(f"AUDIO FORMAT ERROR: Odd byte count {chunk_size} - incomplete Int16 sample! [{session_id}]")
                return
            
            # Check for empty chunks
            if chunk_size == 0:
                logger.warning(f"Empty audio chunk received [{session_id}]")
                return
            
            # Log chunk statistics periodically (every 100th chunk)
            if not hasattr(send_audio_chunk, '_chunk_counter'):
                send_audio_chunk._chunk_counter = {}
            
            if session_id not in send_audio_chunk._chunk_counter:
                send_audio_chunk._chunk_counter[session_id] = 0
            
            send_audio_chunk._chunk_counter[session_id] += 1
            
            if send_audio_chunk._chunk_counter[session_id] % 100 == 0:
                sample_count = chunk_size // 2
                duration_ms = (sample_count / 16000) * 1000
                logger.info(f"Audio stats: chunk #{send_audio_chunk._chunk_counter[session_id]}, "
                           f"{chunk_size} bytes, {sample_count} samples, {duration_ms:.1f}ms @ 16kHz [{session_id}]")
            
            blob = types.Blob(data=raw_pcm_bytes, mime_type="audio/pcm;rate=16000")
            await live_session.send_realtime_input(audio=blob)
        except Exception as e:
            if "1007" in str(e) or "invalid frame payload data" in str(e) or "inputaudio" in str(e):
                logger.error(f"1007 error — dropping chunk and continuing [{session_id}]: {e}")
                # Don't re-raise — let next chunk try so the session doesn't die
                return
            logger.error(f"Audio chunk send failed [{session_id}]: {e}")
            raise

    @staticmethod
    async def receive_responses(live_session, websocket: WebSocket, session_id: str, session=None) -> None:
        """
        Receive responses from Gemini Live API.

        IMPORTANT: The receive() iterator ends after each turn_complete.
        We need to call receive() again for each new turn to continue the conversation.
        This is the expected behavior of the Gemini Live API SDK.
        
        Args:
            live_session: Gemini Live API session
            websocket: WebSocket connection to frontend
            session_id: Session ID for logging
            session: NegotiationSession object (optional, for speaker identification)
        """
        total_responses = 0
        turn_count = 0

        while True:
            try:
                logger.info(f"Starting receive() for turn #{turn_count + 1} [{session_id}]")

                turn_response_count = 0
                turn_complete_received = False

                # Each receive() call handles ONE turn
                # After turn_complete, the iterator ends and we need to call receive() again
                async for response in live_session.receive():
                    total_responses += 1
                    turn_response_count += 1
                    _accumulate_live_usage(session, response)
                    
                    # Log every response for debugging
                    logger.info(
                        "Received response from Live AI",
                        extra={
                            "session_id": session_id,
                            "response_type": type(response).__name__,
                            "server_content": str(response.server_content),
                        },
                    )

                    if not response.server_content:
                        logger.info(f"Response #{total_responses}: No server_content [{session_id}]")
                        continue

                    sc = response.server_content
                    
                    # Log what fields are present in server_content
                    has_model_turn = bool(hasattr(sc, 'model_turn') and sc.model_turn)
                    has_interrupted = bool(hasattr(sc, 'interrupted') and sc.interrupted)
                    has_turn_complete = bool(hasattr(sc, 'turn_complete') and sc.turn_complete)
                    has_input_transcript = bool(hasattr(sc, 'input_transcription') and sc.input_transcription)
                    has_output_transcript = bool((hasattr(sc, 'output_transcription') and sc.output_transcription) or (hasattr(sc, 'output_audio_transcription') and sc.output_audio_transcription))
                    
                    logger.info(f"DBG: GeminiClient Response #{total_responses}: model_turn={has_model_turn}, interrupted={has_interrupted}, turn_complete={has_turn_complete}, input_transcript={has_input_transcript}, output_transcript={has_output_transcript} [{session_id}]")

                    if sc.interrupted:
                        logger.info(f"AI Interrupted by user [session={session_id}]")
                        if session:
                            session.ai_is_speaking = False
                            # On barge-in: only reset user_addressing_ai if copilot is NOT active.
                            # When copilot is active, the interruption is normal barge-in during
                            # monitoring mode — do not close the audio gate.
                            if not getattr(session, 'copilot_active', False):
                                session.user_addressing_ai = False
                            
                            # Flush any pending injections that arrived while AI was speaking
                            from app.services.negotiation_engine import NegotiationEngine
                            await NegotiationEngine.flush_pending_injections(session)

                        await websocket.send_json({"type": "AUDIO_INTERRUPTED", "payload": {}})
                        continue

                    if sc.model_turn:
                        if session:
                            session.ai_is_speaking = True
                            session.current_speaker = "ai"

                        for part in sc.model_turn.parts:
                            if part.inline_data and part.inline_data.mime_type.startswith("audio/pcm"):
                                if isinstance(part.inline_data.data, str):
                                    pcm_bytes = base64.b64decode(part.inline_data.data)
                                else:
                                    pcm_bytes = part.inline_data.data
                                # Mark that AI audio is physically playing in the earphone.
                                # Cleared only when frontend sends AI_PLAYBACK_DONE.
                                if session and not getattr(session, "ai_audio_playing", False):
                                    session.ai_audio_playing = True
                                await websocket.send_bytes(pcm_bytes)
                            elif part.text:
                                await handle_gemini_text(websocket, session_id, part.text)
                                _append_ai_response_text(session, part.text)
                                if session and not getattr(session, 'ai_is_speaking', False):
                                    session.ai_is_speaking = True
                                    await websocket.send_json({"type": "AI_SPEAKING", "payload": {}})
                                
                                # Send real-time partial transcript for private AI advice (Ask AI)
                                response_context = "ask_ai" if (
                                    session and (
                                        getattr(session, "direct_query_in_flight", False)
                                        or getattr(session, "ask_window_active", False)
                                    )
                                ) else "advisor"
                                if response_context == "ask_ai" and session and getattr(session, "current_ai_response", None):
                                    await websocket.send_json({
                                        "type": "TRANSCRIPT_PARTIAL",
                                        "payload": {
                                            "id": _current_ask_response_entry_id(session),
                                            "speaker": "ai",
                                            "text": session.current_ai_response,
                                            "timestamp": int(time.time() * 1000),
                                            "context": "ask_ai",
                                            "is_partial": True,
                                            "source": "gemini_live_output",
                                        }
                                    })
                            elif hasattr(part, 'function_call') and part.function_call:
                                # Handle function call from Gemini
                                function_name = part.function_call.name
                                function_args = dict(part.function_call.args) if part.function_call.args else {}
                                
                                logger.info(f"Function call received: {function_name}({function_args}) [{session_id}]")
                                
                                try:
                                    # Execute the function
                                    result = await handle_function_call(function_name, function_args, websocket)
                                    
                                    # Send function response back to Gemini
                                    await live_session.send({
                                        "function_response": {
                                            "id": part.function_call.id if hasattr(part.function_call, 'id') else None,
                                            "name": function_name,
                                            "response": result
                                        }
                                    })
                                    
                                    logger.info(f"Function response sent for {function_name} [{session_id}]")
                                except Exception as e:
                                    logger.error(f"Function call failed: {function_name} - {e} [{session_id}]")
                                    # Send error response back to Gemini
                                    await live_session.send({
                                        "function_response": {
                                            "id": part.function_call.id if hasattr(part.function_call, 'id') else None,
                                            "name": function_name,
                                            "response": {"error": str(e)}
                                        }
                                    })

                    if sc.input_transcription and sc.input_transcription.text:
                        # Add 20ms grace period for speaker classification to complete (optimized)
                        await asyncio.sleep(0.02)

                        input_text = sc.input_transcription.text
                        ask_context_active = bool(
                            session
                            and (
                                getattr(session, "direct_query_in_flight", False)
                                or getattr(session, "ask_window_active", False)
                                or (
                                    settings.ASK_AI_NATIVE_AUDIO
                                    and getattr(session, "current_ask_capture", None)
                                )
                            )
                        )

                        # Single active path: manual current speaker for public turns.
                        # Native ASK_AI input transcriptions are private user questions,
                        # even if current_speaker was temporarily "ai" from output chunks.
                        speaker = "user"
                        if (
                            session
                            and not ask_context_active
                            and hasattr(session, 'current_speaker')
                            and session.current_speaker
                        ):
                            speaker = session.current_speaker

                        # Create transcript payload
                        transcript_payload = {
                            "speaker": speaker,
                            "text": input_text,
                            "timestamp": int(time.time() * 1000)
                        }
                        if ask_context_active:
                            transcript_payload["context"] = "ask_ai"
                            transcript_payload["source"] = "gemini_live_input"
                            capture = dict(getattr(session, "current_ask_capture", {}) or {})
                            started_at_ms = capture.get("started_at_ms")
                            if started_at_ms:
                                transcript_payload["id"] = f"ask_ai_{started_at_ms}"
                        
                        # Enhanced logging for speaker labeling verification
                        logger.info("=" * 70)
                        logger.info("📝 TRANSCRIPT RECEIVED FROM GEMINI")
                        logger.info("=" * 70)
                        logger.info(f"Text: '{input_text}'")
                        logger.info(f"Speaker Label: {speaker.upper()}")
                        logger.info(f"Timestamp: {transcript_payload['timestamp']}")
                        logger.info(f"Session: {session_id}")
                        
                        # Check speaker timeline for verification
                        if session and hasattr(session, 'speaker_timeline'):
                            recent_speakers = session.speaker_timeline[-3:] if session.speaker_timeline else []
                            logger.info(f"Recent speaker timeline: {recent_speakers}")
                        
                        logger.info("=" * 70)
                        
                        if session:
                            session.last_user_transcript = input_text
                            if ask_context_active:
                                current_ask_capture = dict(getattr(session, "current_ask_capture", {}) or {})
                                current_ask_capture["gemini_input_transcription"] = True
                                current_ask_capture["gemini_input_text"] = input_text
                                if transcript_payload.get("id"):
                                    current_ask_capture["entry_id"] = transcript_payload["id"]
                                session.current_ask_capture = current_ask_capture
                                try:
                                    trace = get_session_trace(session_id)
                                    if trace:
                                        try:
                                            from app.services.next_move_cache import classify_ask as _cls2
                                            _ask_shape2 = _cls2(input_text)
                                        except Exception:
                                            _ask_shape2 = "unknown"
                                        event = trace.record(
                                            category="ask_ai",
                                            name="question_text_ready",
                                            summary="Private ask question text prepared from Gemini native audio input transcription",
                                            data={
                                                "question_text": input_text,
                                                "question_chars": len(input_text),
                                                "source": "gemini_live_input",
                                                "ask_shape": _ask_shape2,
                                                "ask_entry_id": transcript_payload.get("id"),
                                                "native_audio": True,
                                            },
                                        )
                                        session.trace_refs["last_question_event_id"] = event["event_id"]
                                except Exception:
                                    pass

                        # Gemini's native-audio input_transcription has poor quality
                        # for non-Latin scripts (observed: Gujarati comes back as
                        # romanized Hinglish like "Fars, abalu utalage che..."). When
                        # ASK_AI_NATIVE_AUDIO is on AND we're in ask context, Deepgram
                        # has already published a better-quality transcript for the
                        # same audio (pinned to gu-IN / hi-IN / etc., emits native
                        # script). Publishing Gemini's transcript here UPSERTS the
                        # same entry ID and OVERWRITES Deepgram's clean text with
                        # garbage. Solution: keep Gemini's transcript server-side
                        # (already stored above on current_ask_capture for audit /
                        # context) but skip the frontend publish — Deepgram already
                        # owns the YOU bubble for this ask.
                        suppress_for_native_ask = bool(
                            ask_context_active
                            and settings.ASK_AI_NATIVE_AUDIO
                            and settings.ASK_AI_SUPPRESS_NATIVE_TRANSCRIPTION
                        )
                        existing_question_source = (
                            current_ask_capture.get("frontend_question_source")
                            if session else None
                        )
                        existing_question_entry_id = (
                            current_ask_capture.get("entry_id")
                            if session else None
                        )
                        incoming_question_entry_id = transcript_payload.get("id")
                        publish_missing_native_ask = bool(
                            suppress_for_native_ask
                            and ask_context_active
                            and not current_ask_capture.get("frontend_question_final_sent", False)
                        ) if session else False
                        publish_upgrade_native_ask = bool(
                            suppress_for_native_ask
                            and ask_context_active
                            and current_ask_capture.get("frontend_question_final_sent", False)
                            and existing_question_source == "partial"
                            and (
                                not incoming_question_entry_id
                                or not existing_question_entry_id
                                or incoming_question_entry_id == existing_question_entry_id
                            )
                        ) if session else False
                        if suppress_for_native_ask and not publish_missing_native_ask and not publish_upgrade_native_ask:
                            logger.info(
                                "🛑 Skipping Gemini input_transcription publish for ASK (Deepgram owns YOU display): %r",
                                input_text[:80],
                            )
                        else:
                            if (publish_missing_native_ask or publish_upgrade_native_ask) and session:
                                current_ask_capture["frontend_question_final_sent"] = True
                                current_ask_capture["frontend_question_text"] = input_text
                                current_ask_capture["frontend_question_source"] = "gemini_live_input"
                                if incoming_question_entry_id:
                                    current_ask_capture["entry_id"] = incoming_question_entry_id
                                session.current_ask_capture = current_ask_capture
                            # Send user transcripts immediately for separate display
                            # This ensures each question appears separately in the UI
                            logger.info(f"✅ Sending transcript to FRONTEND (speaker={speaker.upper()}) [{session_id}]")
                            await websocket.send_json({
                                "type": "TRANSCRIPT_UPDATE",
                                "payload": transcript_payload
                            })
                        
                        if not ask_context_active:
                            # User is speaking in the public lane, so AI is listening.
                            await websocket.send_json({
                                "type": "AI_LISTENING",
                                "payload": {}
                            })

                    # Handle AI output transcription separately (outside input_transcription block)
                    output_transcription = getattr(sc, 'output_transcription', None) or getattr(sc, 'output_audio_transcription', None)
                    if output_transcription and output_transcription.text:
                        ai_text = _sanitize_ai_response_fragment(output_transcription.text)
                        if not ai_text:
                            logger.warning(
                                "[GeminiClient] Dropped control-text output transcription fragment [%s]",
                                session_id,
                            )
                        else:
                            response_mode = getattr(session, 'response_mode', 'auto')
                            
                            logger.info(f"[DEBUG] AI response chunk received. Mode: {response_mode}, Text: '{ai_text[:50]}...'")

                            # Always accumulate the full response for potential validation
                            if not hasattr(session, 'current_ai_response'):
                                session.current_ai_response = ""
                            session.current_ai_response += " " + ai_text if session.current_ai_response else ai_text

                            # Send real-time partial transcript for private AI advice (Ask AI)
                            response_context = "ask_ai" if (
                                session and (
                                    getattr(session, "direct_query_in_flight", False)
                                    or getattr(session, "ask_window_active", False)
                                )
                            ) else "advisor"
                            if response_context == "ask_ai" and session and getattr(session, "current_ai_response", None):
                                await websocket.send_json({
                                    "type": "TRANSCRIPT_PARTIAL",
                                    "payload": {
                                        "id": _current_ask_response_entry_id(session),
                                        "speaker": "ai",
                                        "text": session.current_ai_response,
                                        "timestamp": int(time.time() * 1000),
                                        "context": "ask_ai",
                                        "is_partial": True,
                                        "source": "gemini_live_output",
                                    }
                                })

                            # AI_TRANSCRIPTION_DISPLAY disabled

                            # Set AI speaking state
                            if not getattr(session, 'ai_is_speaking', False):
                                session.ai_is_speaking = True
                                await websocket.send_json({"type": "AI_SPEAKING", "payload": {}})
                            
                            session.current_speaker = "ai"
                            session.speaker_last_updated = time.time()


                    # Check for turn_complete - this signals the end of this receive() iteration
                    if hasattr(sc, 'turn_complete') and sc.turn_complete:
                        logger.info(f"AI turn complete [session={session_id}]")
                        
                        # VALIDATE AI RESPONSE BEFORE COMPLETING TURN
                        response_mode = getattr(session, 'response_mode', 'auto')
                        
                        full_response = _consume_completed_ai_response(session, session_id)
                        if full_response:
                            if session is not None:
                                if not hasattr(session, "recent_ai_responses"):
                                    session.recent_ai_responses = []
                                session.recent_ai_responses.append(full_response)
                                session.recent_ai_responses = session.recent_ai_responses[-5:]
                            # Classify as ask_ai if EITHER the legacy text path is mid-flight
                            # OR the native-audio ask window is open. The latter covers the case
                            # where Gemini responds to streamed audio BEFORE the text question
                            # (and direct_query_in_flight) would have been set.
                            response_context = "ask_ai" if (
                                getattr(session, "direct_query_in_flight", False)
                                or getattr(session, "ask_window_active", False)
                            ) else "advisor"
                            
                            # ResponseValidator disabled in native audio mode — sending
                            # correction text via send() causes the model to SPEAK it
                            # aloud, creating an infinite loop of spoken system messages.
                            logger.info("AI response [session=%s] text=%r", session_id, full_response[:80])
                            from app.utils.session_logger import get_session_logger as _gsl
                            _sl = _gsl(session_id)
                            if _sl and full_response:
                                _sl.ai_response(
                                    text=full_response,
                                    mode=getattr(session, "response_mode", "auto"),
                                )
                            ai_event = {
                                "id": _current_ask_response_entry_id(session) if response_context == "ask_ai" else None,
                                "speaker": "ai",
                                "text": full_response,
                                "timestamp": int(time.time() * 1000),
                                "response_mode": response_mode,
                                "context": response_context,
                                "source": "gemini_live_output" if response_context == "ask_ai" else None,
                            }
                            trace = get_session_trace(session_id)
                            if trace:
                                response_artifacts = [
                                    trace.write_text_artifact("ai_response_text", full_response, ext=".txt")
                                ]
                                basis_refs = [
                                    ref for ref in [
                                        session.trace_refs.get("last_question_event_id"),
                                        session.trace_refs.get("last_pre_query_brief_event_id"),
                                        session.trace_refs.get("last_mode_instruction_event_id"),
                                        session.trace_refs.get("last_vision_analysis_event_id"),
                                        session.trace_refs.get("last_context_event_id"),
                                        session.trace_refs.get("last_research_complete_event_id"),
                                    ] if ref
                                ]
                                from app.utils.trace_helpers import (
                                    model_block as _mb_live, model_route as _mr_live,
                                    text_preview as _tp_live,
                                )
                                # Compute hold→response latency if we can.
                                _hold_release_ms = getattr(session, "last_hold_released_ms", None)
                                _now_ms = int(time.time() * 1000)
                                _hold_to_response_ms = (
                                    (_now_ms - _hold_release_ms) if _hold_release_ms else None
                                )
                                event = trace.record(
                                    category="ai",
                                    name="ai_response_completed",
                                    summary="Gemini completed an AI response turn",
                                    data={
                                        "context": response_context,
                                        "response_mode": response_mode,
                                        "model": _mb_live(
                                            str(GEMINI_MODEL_PRIMARY),
                                            route=_mr_live(),
                                            purpose="live_audio_response",
                                        ),
                                        "response_text": _tp_live(full_response, 1000),
                                        "response_chars": len(full_response or ""),
                                        "hold_to_response_ms": _hold_to_response_ms,
                                        "question_event_id": session.trace_refs.get("last_question_event_id"),
                                        "pre_query_brief_event_id": session.trace_refs.get("last_pre_query_brief_event_id"),
                                        "vision_event_id": session.trace_refs.get("last_vision_analysis_event_id"),
                                        "context_event_id": session.trace_refs.get("last_context_event_id"),
                                        "research_event_id": session.trace_refs.get("last_research_complete_event_id"),
                                    },
                                    artifacts=response_artifacts,
                                    related_event_ids=basis_refs,
                                )
                                trace.remember("last_ai_response_event_id", event["event_id"])
                                session.trace_refs["last_ai_response_event_id"] = event["event_id"]
                            log_conversation_event(
                                session_id=session.session_id,
                                event="ai_response",
                                speaker="ai",
                                text=full_response,
                                timestamp_ms=ai_event["timestamp"],
                                context=response_context,
                                response_mode=response_mode,
                            )
                            await websocket.send_json({
                                "type": "TRANSCRIPT_UPDATE",
                                "payload": ai_event
                            })
                            if session:
                                session.advisor_history.append(ai_event)
                                session.advisor_history = session.advisor_history[-settings.RESEARCH_HISTORY_LIMIT:]
                                session_store.record_advisor_event(session.session_id, "response", ai_event)
                                session_store.persist_session(session, ended=False)
                            
                        if session:
                            session.ai_is_speaking = False
                            # ai_audio_playing stays True until frontend sends AI_PLAYBACK_DONE
                            # Reset speaker to last known human so Listener can resume analysis
                            if session.current_speaker == "ai":
                                session.current_speaker = "user" # Default back to user
                            
                            # After any AI turn completes, always discard pending injections.
                            # Flushing them immediately would trigger a second proactive AI turn
                            # causing the double-response bug. The listener cycle (10s) will
                            # inject fresh context on the next pass instead.
                            was_direct_query = getattr(session, "direct_query_in_flight", False)
                            was_ask_window = getattr(session, "ask_window_active", False)
                            # Treat either signal as "this was an ask turn" for the cleanup
                            # bookkeeping below (silence-fallback suppression, metrics).
                            was_direct_query = was_direct_query or was_ask_window
                            session.direct_query_in_flight = False
                            # Close the ask window so the NEXT ai turn (intel, advisor, etc.)
                            # is correctly classified as "advisor" again.
                            session.ask_window_active = False
                            if was_direct_query and full_response:
                                session.last_ask_response_at = time.time()
                            if was_direct_query and full_response:
                                if "can't process audio inputs" in full_response.lower():
                                    session.session_metrics["ask_audio_input_failures"] = session.session_metrics.get("ask_audio_input_failures", 0) + 1
                                    logger.warning(
                                        "[GeminiClient] ask-AI audio-input fallback detected [session=%s metrics=%s]",
                                        session_id,
                                        getattr(session, "current_ask_capture", {}),
                                    )
                            if was_direct_query and getattr(session, "current_ask_capture", None):
                                logger.info(
                                    "[GeminiClient] ask-AI turn metrics [session=%s metrics=%s]",
                                    session_id,
                                    session.current_ask_capture,
                                )
                                session.current_ask_capture = {}

                            # If this was an ask-AI turn and the AI produced no audio or text,
                            # send a visible fallback so the user isn't left in silence.
                            if was_direct_query and not full_response and not _consume_completed_ai_response(session, session_id):
                                try:
                                    await websocket.send_json({
                                        "type": "AI_RESPONSE",
                                        "payload": {
                                            "speaker": "ai",
                                            "text": "I didn't catch that clearly. Hold and ask again.",
                                            "timestamp": int(time.time() * 1000),
                                            "context": "ask_ai",
                                        },
                                    })
                                except Exception:
                                    pass
                            if session.pending_injections:
                                count = len(session.pending_injections)
                                session.pending_injections.clear()
                                logger.info(
                                    f"Cleared {count} pending injections after turn complete "
                                    f"[session={session_id}]"
                                )
                            if session.pending_intel_context is not None or session.pending_intel_critical_events:
                                from app.services.negotiation_engine import NegotiationEngine
                                asyncio.create_task(
                                    NegotiationEngine.flush_pending_injections(session)
                                )

                        # Turn is over, AI is now listening
                        await websocket.send_json({"type": "AI_LISTENING", "payload": {}})

                        # Mark turn as cleanly completed before breaking
                        turn_complete_received = True
                        # Break from this turn's receive() loop. The outer while True
                        # will immediately call receive() again for the next turn.
                        break

                # If we exited the loop without turn_complete, the Gemini session dropped mid-turn.
                # This is the same class of recoverable error as 1006/1011 — trigger reconnect.
                if not turn_complete_received:
                    logger.error(f"⚠ receive() ended without turn_complete after {turn_response_count} responses [{session_id}]")
                    logger.error(f"  Session likely dropped — triggering auto-reconnect")
                    if session:
                        from app.services.negotiation_engine import NegotiationEngine
                        asyncio.create_task(
                            NegotiationEngine._reconnect_live_session(session, websocket)
                        )
                    else:
                        try:
                            await websocket.send_json({
                                "type": "AI_DEGRADED",
                                "payload": {"message": "AI connection ended unexpectedly. Please refresh to reconnect."}
                            })
                        except Exception:
                            pass
                    break

                # Turn completed successfully, increment counter and loop will call receive() again for next turn
                turn_count += 1
                logger.debug(f"Turn #{turn_count} complete. Ready for turn #{turn_count + 1}, calling receive() again [{session_id}]")
                await asyncio.sleep(0.01)  # Brief pause before next receive() call

            except asyncio.CancelledError:
                logger.info(f"Receive loop cancelled after {turn_count} turns [{session_id}]")
                raise
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                is_normal_shutdown = (
                    "1000" in error_msg
                    or "ConnectionClosedOK" in error_type
                    or "sent 1000 (OK)" in error_msg
                )

                if is_normal_shutdown and session and session.state in {
                    NegotiationState.ENDING,
                    NegotiationState.IDLE,
                }:
                    logger.info(
                        f"Receive loop closed cleanly during shutdown [{session_id}]: "
                        f"{error_type}: {error_msg}"
                    )
                    break

                # Determine if this is a recoverable connection drop that warrants auto-reconnect.
                # 1007 — Chirp 3 codec error (PCM input after audio output)
                # 1006 — Abnormal closure (google.genai.errors.APIError: 1006 None)
                # 1011 — Keepalive ping timeout (ConnectionClosedError: sent 1011)
                is_reconnectable = (
                    "1007" in error_msg
                    or "invalid frame payload data" in error_msg
                    or "inputaudio" in error_msg
                    or "1006" in error_msg
                    or "1011" in error_msg
                    or "abnormal closure" in error_msg.lower()
                    or "keepalive ping timeout" in error_msg.lower()
                    or "ConnectionClosedError" in error_type
                )

                if is_reconnectable:
                    logger.warning(
                        f"Recoverable connection drop [{session_id}] — triggering auto-reconnect: "
                        f"{error_type}: {error_msg}"
                    )
                    if session:
                        from app.services.negotiation_engine import NegotiationEngine
                        asyncio.create_task(
                            NegotiationEngine._reconnect_live_session(session, websocket)
                        )
                    else:
                        try:
                            await websocket.send_json({
                                "type": "AI_DEGRADED",
                                "payload": {"message": "AI connection dropped. Please refresh."}
                            })
                        except Exception:
                            pass
                else:
                    logger.error(
                        f"Receive loop error after {turn_count} turns [{session_id}]: "
                        f"{error_type}: {error_msg}", exc_info=True
                    )
                    try:
                        await websocket.send_json({
                            "type": "AI_DEGRADED",
                            "payload": {"message": f"AI connection error: {error_msg}"}
                        })
                    except Exception:
                        pass
                break  # Exit this receive loop — reconnect (or degraded) handled above

    @staticmethod
    async def keepalive_ping(session: NegotiationSession) -> None:
        """
        Send periodic keepalive pings to prevent Gemini Live WebSocket timeout.
        
        The Gemini Live WebSocket has a ~30 second keepalive timeout. If no messages
        are sent within that window, the connection closes with error 1011.
        
        This function sends a minimal message every 20 seconds to keep the connection alive.
        """
        keepalive_states = {
            NegotiationState.IDLE,
            NegotiationState.CONSENTED,
            NegotiationState.ACTIVE,
        }
        while session.live_session and session.state in keepalive_states:
            try:
                await asyncio.sleep(20)  # Ping every 20 seconds (before 30s timeout)
                
                if session.live_session and session.state in keepalive_states:
                    # Send a minimal keepalive message (empty text with turn_complete=False)
                    async with session.gemini_send_lock:
                        await session.live_session.send_client_content(
                            turns=types.Content(
                                role="user",
                                parts=[types.Part(text="")],
                            ),
                            turn_complete=False,
                        )
                    logger.debug(f"Keepalive ping sent [session={session.session_id}]")
            except Exception as e:
                logger.warning(f"Keepalive ping failed (session may be closing): {e}")
                break

    @staticmethod
    async def monitor_session_lifetime(session: NegotiationSession, websocket: WebSocket, api_key: str) -> None:
        await asyncio.sleep(SESSION_HANDOFF_TRIGGER)
        
        if session.state != NegotiationState.ACTIVE:
            return
            
        logger.info(f"Session handoff triggered [{session.session_id}]")
        
        context_summary = _build_context_summary(session)
        
        old_live = session.live_session
        if old_live:
            try:
                await old_live.__aexit__(None, None, None)
            except Exception:
                pass
                
        try:
            # D5: Use the async context manager correctly
            async with open_live_session(
                api_key=api_key,
                context=f"{session.context}\n\nCONTINUATION CONTEXT:\n{context_summary}",
                response_language=(session.response_language if settings.MULTILANG_ENABLED else None),
            ) as new_live:
                session.live_session = new_live
                
                # D5 — Preserve copilot state across handoff
                if session.copilot_active and session.listener_agent:
                    last_ctx = session.listener_agent.last_context
                    if last_ctx:
                        # Logic to format and inject priming text
                        # This reuses the logic from the plan, ensuring consistency
                        from app.services.negotiation_engine import NegotiationEngine
                        await NegotiationEngine._inject_context_to_live_ai(session, last_ctx, [])
                        logger.info(f"Session handoff: primed new session with listener context [{session.session_id}]")

                asyncio.create_task(receive_responses(new_live, websocket, session.session_id, session))
                logger.info(f"Session handoff complete [{session.session_id}]")
                # Relaunch the monitor for the *next* handoff
                asyncio.create_task(monitor_session_lifetime(session, websocket, api_key))
        except Exception as e:
            logger.error(f"Failed to hand off session [{session.session_id}]: {e}")

open_live_session = GeminiClient.open_live_session
send_vision_frame = GeminiClient.send_vision_frame
send_audio_chunk = GeminiClient.send_audio_chunk
receive_responses = GeminiClient.receive_responses
monitor_session_lifetime = GeminiClient.monitor_session_lifetime
keepalive_ping = GeminiClient.keepalive_ping

# Export the new functions for manual activity control
__all__ = [
    'GeminiClient',
    'GeminiUnavailableError',
    'build_system_prompt',
    'build_advisor_query',
    'analyze_vision_frames',
    'generate_tactical_advice',
    'trigger_advice_response',
    'handle_function_call',
    'perform_web_search',
    'open_live_session',
    'send_vision_frame',
    'send_audio_chunk',
    'receive_responses',
    'monitor_session_lifetime',
    'keepalive_ping',
    'handle_gemini_text',
    'extract_state_from_transcript'
]
