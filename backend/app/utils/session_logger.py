"""
session_logger.py — Complete per-session human-readable log.

One log file per session: data/logs/sessions/{session_id}.log

Millisecond timestamps. Every extraction, injection, vision analysis,
research result, and AI interaction logged with full detail.
"""
from __future__ import annotations

import os
import time
import threading
from datetime import datetime
from typing import Any

# ── Registry ──────────────────────────────────────────────────────────────────
_loggers: dict[str, "SessionLogger"] = {}
_lock = threading.Lock()

LOG_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "logs", "sessions"
)


def get_session_logger(session_id: str) -> "SessionLogger | None":
    return _loggers.get(session_id)


def create_session_logger(session_id: str) -> "SessionLogger":
    with _lock:
        if session_id in _loggers:
            return _loggers[session_id]
        sl = SessionLogger(session_id)
        _loggers[session_id] = sl
        return sl


def close_session_logger(session_id: str) -> None:
    with _lock:
        sl = _loggers.pop(session_id, None)
    if sl:
        sl._close()


# ── SessionLogger ──────────────────────────────────────────────────────────────

class SessionLogger:
    """Writes complete human-readable session log to data/logs/sessions/{session_id}.log"""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._start_time = time.time()
        self._event_count = 0
        os.makedirs(LOG_DIR, exist_ok=True)
        path = os.path.join(LOG_DIR, f"{session_id}.log")
        self._f = open(path, "w", encoding="utf-8", buffering=1)
        self._write_header(path)

    # ── Internal ────────────────────────────────────────────────────────────────

    def _ts(self) -> str:
        """Millisecond timestamp: HH:MM:SS.mmm"""
        now = datetime.now()
        return now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"

    def _elapsed(self) -> str:
        s = time.time() - self._start_time
        m, sec = divmod(int(s), 60)
        ms = int((s - int(s)) * 1000)
        return f"{m:02d}:{sec:02d}.{ms:03d}"

    def _write(self, lines: list[str]) -> None:
        try:
            self._f.write("\n".join(lines) + "\n\n")
            self._f.flush()
        except Exception:
            pass

    def _write_header(self, path: str) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._write([
            "=" * 72,
            "  NEGOTIATION SESSION LOG",
            f"  Session   : {self.session_id}",
            f"  Started   : {ts}",
            f"  Log file  : {path}",
            "=" * 72,
        ])

    def _close(self) -> None:
        try:
            self._f.flush()
            self._f.close()
        except Exception:
            pass

    def _fmt(self, val: object, max_len: int = 200) -> str:
        s = str(val) if val is not None else "(none)"
        return s[:max_len] + "..." if len(s) > max_len else s

    # ── Session lifecycle ────────────────────────────────────────────────────────

    def session_started(self, *, mode: str, meeting_title: str | None = None,
                        model: str | None = None, source_mode: str | None = None) -> None:
        self._write([
            f"[{self._ts()}] SESSION STARTED",
            f"  Mode        : {mode}",
            f"  Meeting     : {meeting_title or '(none)'}",
            f"  AI Model    : {model or 'unknown'}",
            f"  Source mode : {source_mode or 'unknown'}",
        ])

    def session_ended(self, *, stats: dict | None = None) -> None:
        lines = [
            f"[{self._ts()}] SESSION ENDED  (total elapsed: {self._elapsed()})",
            f"  Events logged : {self._event_count}",
        ]
        if stats:
            lines += [
                f"  STT           : {stats.get('stt_successes',0)} ok / {stats.get('stt_requests',0)} sent  empty={stats.get('stt_empty_results',0)}",
                f"  Research      : {stats.get('research_requests',0)} runs  failures={stats.get('research_failures',0)}",
                f"  Ask-AI        : {stats.get('ask_capture_dedicated_count',0) or stats.get('ask_attempts',0)} holds",
                f"  Vision        : {stats.get('vision_pro_call_count',0)} Pro calls",
            ]
        self._write(lines)
        self._close()

    def gemini_live_connected(self, *, model: str) -> None:
        self._write([f"[{self._ts()}] GEMINI LIVE CONNECTED  model={model}"])

    def gemini_live_reconnected(self, *, attempt: int) -> None:
        self._write([f"[{self._ts()}] GEMINI LIVE RECONNECTED  attempt={attempt}"])

    def copilot_activated(self) -> None:
        self._write([f"[{self._ts()}] COPILOT ACTIVATED  (auto context injection begins)"])

    # ── Transcription ────────────────────────────────────────────────────────────

    def transcript(self, *, speaker: str, text: str, confidence: float | None = None,
                   duration_ms: int | None = None, source: str | None = None) -> None:
        self._event_count += 1
        conf = f"{confidence*100:.1f}%" if confidence is not None else "n/a"
        dur = f"{duration_ms/1000:.2f}s" if duration_ms else "n/a"
        role = {"user": "YOU", "counterparty": "COUNTERPARTY"}.get(speaker, speaker.upper())
        self._write([
            f"[{self._ts()}] TRANSCRIPT — {role}",
            f'  Text        : "{self._fmt(text, 400)}"',
            f"  Confidence  : {conf}  |  Duration: {dur}  |  Source: {source or 'unknown'}",
        ])

    def transcript_diarized_turn(self, *, speaker: str, text: str, start_s: float,
                                  end_s: float, confidence: float | None = None) -> None:
        """A single speaker turn from diarized utterance."""
        self._event_count += 1
        conf = f"{confidence*100:.1f}%" if confidence is not None else "n/a"
        role = {"user": "YOU", "counterparty": "COUNTERPARTY"}.get(speaker, speaker.upper())
        self._write([
            f"[{self._ts()}] TRANSCRIPT TURN — {role}  [{start_s:.2f}s – {end_s:.2f}s]",
            f'  Text        : "{self._fmt(text, 400)}"',
            f"  Confidence  : {conf}",
        ])

    # ── Text extraction (listener_agent._run_text_extraction_cycle) ──────────────

    def text_extraction_result(self, *, cycle: int, extracted: dict) -> None:
        """Log what the text extraction cycle extracted from the transcript."""
        self._event_count += 1
        lines = [f"[{self._ts()}] TEXT EXTRACTION  (cycle {cycle})"]
        fields = [
            ("Item",            "item"),
            ("Type",            "negotiation_type"),
            ("Their price",     "counterparty_price"),
            ("User price",      "user_price"),
            ("Target price",    "user_target_price"),
            ("Walk-away",       "user_walk_away_price"),
            ("Sentiment",       "counterparty_sentiment"),
            ("Their goal",      "counterparty_goal"),
            ("Person detected", "counterparty_person_name"),
            ("Company detected","counterparty_company"),
        ]
        for label, key in fields:
            val = extracted.get(key)
            if val:
                lines.append(f"  {label:<18}: {self._fmt(val)}")
        moments = extracted.get("key_moments") or []
        leverage = extracted.get("leverage_points") or []
        if moments:
            lines.append(f"  Key moments      : {self._fmt('; '.join(str(m) for m in moments[:3]))}")
        if leverage:
            lines.append(f"  Leverage         : {self._fmt('; '.join(str(l) for l in leverage[:3]))}")
        snippet = extracted.get("transcript_snippet") or ""
        if snippet:
            lines.append(f"  Snippet          : \"{self._fmt(snippet, 150)}\"")
        research_q = extracted.get("research_query")
        if research_q:
            lines.append(f"  Research query   : {research_q}")
        self._write(lines)

    # ── Audio extraction (EXTRACTION_PROMPT / analyze_vision_frames diarization) ─

    def audio_extraction_result(self, *, utterance_id: str, speaker: str,
                                 text: str, diarized_turns: list,
                                 duration_ms: int) -> None:
        """Log what the audio-based extraction produced (diarization + context)."""
        self._event_count += 1
        lines = [
            f"[{self._ts()}] AUDIO EXTRACTION  id={utterance_id[:30]}",
            f"  Speaker     : {speaker}  |  Duration: {duration_ms/1000:.2f}s",
            f'  Full text   : "{self._fmt(text, 300)}"',
        ]
        if diarized_turns:
            lines.append(f"  Diarization : {len(diarized_turns)} turn(s)")
            for i, t in enumerate(diarized_turns[:4]):
                t_spk = t.get("diarized_speaker_id") or t.get("speaker", "?")
                t_txt = self._fmt(t.get("text",""), 120)
                t_start = t.get("start_time", 0)
                lines.append(f"    [{i+1}] {t_spk} @ {t_start:.2f}s : \"{t_txt}\"")
        self._write(lines)

    # ── Context extracted (every N cycles) ────────────────────────────────────────

    def context_extracted(self, *, context: dict) -> None:
        self._event_count += 1
        lines = [
            f"[{self._ts()}] CONTEXT STATE (latest accumulated)",
            f"  Item        : {context.get('item') or '(unknown)'}",
            f"  Type        : {context.get('negotiation_type') or '(unknown)'}",
            f"  Their price : {context.get('counterparty_price') or context.get('seller_asking_price') or '(unknown)'}",
            f"  Your price  : {context.get('user_price') or context.get('buyer_offer') or '(unknown)'}",
            f"  Target      : {context.get('user_target_price') or '(not set)'}",
            f"  Walk-away   : {context.get('user_walk_away_price') or '(not set)'}",
            f"  Sentiment   : {context.get('counterparty_sentiment') or 'unknown'}",
            f"  Their goal  : {self._fmt(context.get('counterparty_goal') or '(unknown)')}",
        ]
        moments = context.get("key_moments") or []
        leverage = context.get("leverage_points") or []
        if moments:
            lines.append(f"  Key moments : {self._fmt('; '.join(str(m) for m in moments[:3]))}")
        if leverage:
            lines.append(f"  Leverage    : {self._fmt('; '.join(str(l) for l in leverage[:3]))}")
        if context.get("market_data"):
            lines.append(f"  Market data : {self._fmt(str(context['market_data']), 200)}")
        self._write(lines)

    # ── Research ─────────────────────────────────────────────────────────────────

    def research_triggered(self, *, trigger: str, query: str) -> None:
        self._event_count += 1
        self._write([
            f"[{self._ts()}] RESEARCH TRIGGERED",
            f"  Trigger     : {trigger}",
            f"  Query       : {query}",
        ])

    def research_complete(self, *, query: str, data: dict | str) -> None:
        self._event_count += 1
        lines = [
            f"[{self._ts()}] RESEARCH COMPLETE",
            f"  Query       : {self._fmt(query)}",
        ]
        if isinstance(data, dict):
            for label, key in [("Price range","price_range"),("Key facts","key_facts"),
                               ("Leverage","leverage"),("Tactics","tactics"),
                               ("Gap answer","gap_answer")]:
                val = data.get(key)
                if val and val != "null":
                    lines.append(f"  {label:<12}: {self._fmt(val, 300)}")
        else:
            lines.append(f"  Result      : {self._fmt(str(data), 400)}")
        self._write(lines)

    def person_research_complete(self, *, name: str, data: dict) -> None:
        self._event_count += 1
        self._write([
            f"[{self._ts()}] PERSON RESEARCH COMPLETE — {name}",
            f"  Title       : {data.get('title','(unknown)')}",
            f"  Seniority   : {data.get('seniority','unknown')}  |  Decision-maker: {data.get('decision_maker','?')}",
            f"  Dept        : {data.get('department','unknown')}",
            f"  Background  : {self._fmt(data.get('background','(none)'), 200)}",
            f"  Negs style  : {self._fmt(data.get('negotiation_style','unknown'), 150)}",
            f"  Pain points : {self._fmt(data.get('pain_points','unknown'), 150)}",
            f"  Leverage    : {self._fmt(data.get('leverage','none'), 200)}",
            f"  Recent news : {self._fmt(data.get('recent_activity','none'), 150)}",
        ])

    def company_research_complete(self, *, name: str, data: dict) -> None:
        self._event_count += 1
        self._write([
            f"[{self._ts()}] COMPANY RESEARCH COMPLETE — {name}",
            f"  Industry    : {data.get('industry','unknown')}  |  Size: {data.get('size','unknown')}",
            f"  Revenue     : {data.get('revenue_range','unknown')}",
            f"  Fin. health : {data.get('financial_health','unknown')}",
            f"  Procurement : {self._fmt(data.get('procurement_style','unknown'), 150)}",
            f"  Urgency     : {self._fmt(data.get('urgency_signals','none'), 150)}",
            f"  Leverage pts: {self._fmt('; '.join(data.get('key_leverage_points',[])[:3]), 200)}",
            f"  Pain points : {self._fmt('; '.join(data.get('known_pain_points',[])[:3]), 200)}",
            f"  Recent news : {self._fmt(data.get('recent_news','none'), 150)}",
        ])

    # ── Vision ────────────────────────────────────────────────────────────────────

    def vision_analyzed(self, *, scene_type: str, confidence: str,
                         item: str | None = None, doc_text: str | None = None,
                         advice_hint: str | None = None, prices: list | None = None,
                         terms: list | None = None, defects: list | None = None,
                         body_language: dict | None = None,
                         contract_analysis: dict | None = None) -> None:
        self._event_count += 1
        lines = [
            f"[{self._ts()}] VISION ANALYZED",
            f"  Scene       : {scene_type}  |  Confidence: {confidence}",
        ]
        if item:
            lines.append(f"  Item seen   : {item}")
        if defects:
            lines.append(f"  Defects     : {', '.join(defects[:5])}")
        if prices:
            lines.append(f"  Prices seen : {prices}")
        if terms:
            lines.append(f"  Terms seen  : {', '.join(str(t) for t in terms[:5])}")
        if doc_text:
            lines.append(f"  DOC TEXT    : \"{self._fmt(doc_text, 500)}\"")
        if body_language and body_language.get("expression") not in (None, "none_visible"):
            bl = body_language
            lines.append(
                f"  Body lang   : expression={bl.get('expression')}  posture={bl.get('posture')}  "
                f"stress={bl.get('stress_signal')}  engagement={bl.get('engagement')}"
            )
        if contract_analysis:
            ca = contract_analysis
            if ca.get("parties"):
                lines.append(f"  Parties     : {ca['parties']}")
            if ca.get("risk_terms"):
                lines.append(f"  Risk terms  : {ca['risk_terms'][:3]}")
            if ca.get("negotiable_items"):
                lines.append(f"  Negotiable  : {ca['negotiable_items'][:3]}")
        if advice_hint:
            lines.append(f"  AI hint     : {self._fmt(advice_hint, 200)}")
        self._write(lines)

    def document_page_captured(self, *, page_num: int, text_len: int,
                                prices: list, terms: list | None = None) -> None:
        self._event_count += 1
        self._write([
            f"[{self._ts()}] DOCUMENT PAGE CAPTURED  (page ~{page_num})",
            f"  Text length : {text_len} chars",
            f"  Prices      : {prices or 'none'}",
            f"  Terms       : {terms or 'none'}",
        ])

    # ── Intel injection ────────────────────────────────────────────────────────────

    def pre_query_brief_sent(self, *, chars: int, has_vision: bool,
                              has_market: bool, has_person: bool = False,
                              has_company: bool = False,
                              has_document: bool = False) -> None:
        self._event_count += 1
        items = []
        if has_market:     items.append("market research")
        if has_vision:     items.append("vision intel")
        if has_person:     items.append("person intel")
        if has_company:    items.append("company intel")
        if has_document:   items.append("document analysis")
        items.append("live transcript")
        self._write([
            f"[{self._ts()}] PRE-QUERY BRIEF SENT  (hold orb pressed)",
            f"  Size        : {chars:,} chars",
            f"  Contains    : {', '.join(items)}",
            f"  Purpose     : inject negotiation context before user's question",
        ])

    def intel_injected(self, *, chars: int, cycle: int | None = None,
                        contains: list[str] | None = None) -> None:
        self._event_count += 1
        cycle_str = f"  cycle={cycle}" if cycle else ""
        items = contains or ["transcript", "context", "market research"]
        self._write([
            f"[{self._ts()}] INTEL INJECTED TO GEMINI LIVE{cycle_str}",
            f"  Size        : {chars:,} chars",
            f"  Contains    : {', '.join(items)}",
            f"  Purpose     : keep Gemini informed of latest negotiation state",
        ])

    # ── Ask-AI (hold-orb) flow ─────────────────────────────────────────────────────

    def hold_activated(self) -> None:
        self._event_count += 1
        self._write([
            f"[{self._ts()}] USER HELD ORB — ASK-AI ACTIVATED",
            f"  Mic audio now streaming directly to Gemini Live as user speaks...",
        ])

    def hold_released(self, *, audio_bytes: int, chunks: int) -> None:
        dur = audio_bytes / 32000
        self._write([
            f"[{self._ts()}] ORB RELEASED",
            f"  Audio       : {dur:.2f}s  ({audio_bytes:,} bytes, {chunks} chunks)",
            f"  Action      : sending audio as WAV to Gemini Live, awaiting response...",
        ])

    def ask_ai_question(self, *, question: str) -> None:
        self._event_count += 1
        self._write([
            f"[{self._ts()}] USER QUESTION (transcribed for display, sent as audio to AI)",
            f'  Text        : "{self._fmt(question, 400)}"',
        ])

    def ai_response(self, *, text: str, mode: str = "auto") -> None:
        self._event_count += 1
        self._write([
            f"[{self._ts()}] AI RESPONDED",
            f"  Mode        : {mode.upper()}",
            f'  Response    : "{self._fmt(text, 600)}"',
        ])

    # ── Misc ──────────────────────────────────────────────────────────────────────

    def error(self, *, where: str, message: str) -> None:
        self._write([
            f"[{self._ts()}] ERROR  [{where}]",
            f"  {self._fmt(message, 400)}",
        ])

    def note(self, *, message: str) -> None:
        self._write([f"[{self._ts()}] {self._fmt(message, 300)}"])
