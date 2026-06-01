from __future__ import annotations

import re
import time
from typing import Any


SOURCE_PRIORITY: dict[str, int] = {
    "partial": 10,
    "snapshot_partial": 15,
    "gemini_live_input": 30,
    "snapshot_transcription": 40,
    "desktop_ask_ai": 40,
    "batch_transcription": 45,
    "deepgram_ask": 70,
}

_SHORT_PARTIAL_FILLERS = {
    "ah",
    "eh",
    "er",
    "hm",
    "hmm",
    "uh",
    "um",
    "de",
    "ex",
}


def _words(text: str | None) -> list[str]:
    return re.findall(r"[a-z0-9]+", compact_ask_text(text).lower())


def _latin_ratio(text: str | None) -> float:
    cleaned = compact_ask_text(text)
    if not cleaned:
        return 0.0
    letters = [ch for ch in cleaned if ch.isalpha()]
    if not letters:
        return 1.0
    latin = [ch for ch in letters if ("a" <= ch.lower() <= "z")]
    return len(latin) / max(1, len(letters))


def _same_start(left: str | None, right: str | None, *, words: int = 3) -> bool:
    left_words = _words(left)
    right_words = _words(right)
    if not left_words or not right_words:
        return False
    n = min(words, len(left_words), len(right_words))
    return left_words[:n] == right_words[:n]


def _same_text_family(left: str | None, right: str | None) -> bool:
    left_clean = compact_ask_text(left).lower()
    right_clean = compact_ask_text(right).lower()
    if not left_clean or not right_clean:
        return False
    return (
        left_clean.startswith(right_clean)
        or right_clean.startswith(left_clean)
        or _same_start(left_clean, right_clean)
    )


def _current_reference_texts(capture: dict[str, Any] | None) -> list[str]:
    cap = capture or {}
    candidates = cap.get("transcript_candidates") or {}
    refs: list[str] = []
    for source in ("gemini_live_input", "snapshot_transcription", "desktop_ask_ai", "batch_transcription"):
        candidate = candidates.get(source) if isinstance(candidates, dict) else None
        text = compact_ask_text((candidate or {}).get("text") if isinstance(candidate, dict) else None)
        if text and not is_short_private_partial(text):
            refs.append(text)
    for key in ("gemini_input_text", "ask_question_text"):
        text = compact_ask_text(cap.get(key))
        if text and not is_short_private_partial(text):
            refs.append(text)
    return refs


def looks_cross_ask_contaminated(capture: dict[str, Any] | None, text: str | None, source: str | None) -> bool:
    """Detect the Deepgram failure mode where an ask stream begins with an old tail.

    This is intentionally conservative and only applies when both the incoming
    text and a current-turn reference look Latin-script. Native-script Deepgram
    output must not be rejected just because Gemini also produced romanized text.
    """
    if source != "deepgram_ask":
        return False
    incoming = compact_ask_text(text)
    if is_short_private_partial(incoming) or _latin_ratio(incoming) < 0.8:
        return False
    refs = [ref for ref in _current_reference_texts(capture) if _latin_ratio(ref) >= 0.8]
    if not refs:
        return False
    return all(not _same_start(incoming, ref, words=2) for ref in refs)


def _deepgram_truncated_by_gemini(capture: dict[str, Any] | None, text: str | None) -> bool:
    incoming = compact_ask_text(text)
    if not incoming or _latin_ratio(incoming) < 0.8:
        return False
    for ref in _current_reference_texts(capture):
        if _latin_ratio(ref) < 0.8:
            continue
        if len(ref) > len(incoming) + 18 and _same_text_family(incoming, ref):
            return True
    return False


def compact_ask_text(text: str | None) -> str:
    return " ".join(str(text or "").split()).strip()


def ask_entry_id(session: Any, capture: dict[str, Any] | None = None) -> str:
    cap = capture or getattr(session, "current_ask_capture", None) or {}
    started_at_ms = cap.get("started_at_ms")
    if started_at_ms:
        return f"ask_ai_{started_at_ms}"
    question_capture_id = getattr(session, "question_capture_id", None)
    if question_capture_id:
        return question_capture_id
    return f"ask_ai_{int(time.time() * 1000)}"


def is_short_private_partial(text: str | None) -> bool:
    cleaned = compact_ask_text(text)
    if not cleaned:
        return True
    norm = re.sub(r"[^a-z0-9]+", "", cleaned.lower())
    words = cleaned.split()
    if norm in _SHORT_PARTIAL_FILLERS:
        return True
    return len(words) <= 1 and len(norm) <= 3


def source_priority(source: str | None) -> int:
    return SOURCE_PRIORITY.get(source or "", 0)


def record_candidate(
    session: Any,
    *,
    text: str,
    source: str,
    entry_id: str | None = None,
    is_final: bool = False,
    confidence: float | None = None,
    timestamp_ms: int | None = None,
) -> dict[str, Any]:
    cleaned = compact_ask_text(text)
    capture = dict(getattr(session, "current_ask_capture", {}) or {})
    if not entry_id:
        entry_id = ask_entry_id(session, capture)
    capture["entry_id"] = entry_id
    candidates = dict(capture.get("transcript_candidates") or {})
    candidates[source] = {
        "text": cleaned,
        "source": source,
        "entry_id": entry_id,
        "is_final": bool(is_final),
        "confidence": confidence,
        "updated_at_ms": int(timestamp_ms or (time.time() * 1000)),
        "priority": source_priority(source),
    }
    capture["transcript_candidates"] = candidates
    if source == "gemini_live_input":
        capture["gemini_input_text"] = cleaned
    if is_final:
        capture["ask_question_text"] = cleaned
    session.current_ask_capture = capture
    return capture


def best_candidate(capture: dict[str, Any] | None, *, allow_partial: bool = False) -> dict[str, Any] | None:
    candidates = list((capture or {}).get("transcript_candidates", {}).values())
    if not candidates:
        legacy_text = compact_ask_text((capture or {}).get("ask_question_text") or (capture or {}).get("gemini_input_text"))
        if legacy_text and not is_short_private_partial(legacy_text):
            return {
                "text": legacy_text,
                "source": "gemini_live_input" if (capture or {}).get("gemini_input_text") else "partial",
                "entry_id": (capture or {}).get("entry_id"),
                "is_final": False,
                "priority": source_priority("gemini_live_input"),
                "updated_at_ms": int(time.time() * 1000),
            }
        return None

    usable: list[dict[str, Any]] = []
    for candidate in candidates:
        text = compact_ask_text(candidate.get("text"))
        if not text:
            continue
        source = candidate.get("source")
        is_final = bool(candidate.get("is_final"))
        if source in {"partial", "snapshot_partial"} and not allow_partial:
            continue
        if not is_final and source not in {"gemini_live_input", "snapshot_transcription", "batch_transcription"} and not allow_partial:
            continue
        if is_short_private_partial(text) and not is_final:
            continue
        if looks_cross_ask_contaminated(capture, text, source):
            continue
        priority = source_priority(source)
        if source == "deepgram_ask" and _deepgram_truncated_by_gemini(capture, text):
            priority = source_priority("gemini_live_input") - 1
        usable.append({**candidate, "text": text, "priority": priority})

    if not usable:
        return None

    usable.sort(
        key=lambda c: (
            int(c.get("priority") or 0),
            1 if c.get("is_final") else 0,
            len(c.get("text") or ""),
            int(c.get("updated_at_ms") or 0),
        ),
        reverse=True,
    )
    return usable[0]


def should_replace_frontend_text(existing_source: str | None, new_source: str, existing_text: str | None, new_text: str | None) -> bool:
    incoming = compact_ask_text(new_text)
    existing = compact_ask_text(existing_text)
    if not incoming:
        return False
    if not existing:
        return True
    if incoming == existing:
        return False
    if source_priority(new_source) > source_priority(existing_source):
        return True
    if source_priority(new_source) == source_priority(existing_source) and len(incoming) > len(existing) + 8:
        return True
    if existing_source == "deepgram_ask" and new_source == "gemini_live_input":
        if _latin_ratio(existing) >= 0.8 and _latin_ratio(incoming) >= 0.8:
            if len(incoming) > len(existing) + 18 and _same_text_family(existing, incoming):
                return True
    return False
