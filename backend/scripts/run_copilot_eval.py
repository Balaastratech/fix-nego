from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import websockets

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402


DEFAULT_SCENARIOS = BACKEND_ROOT / "evals" / "copilot_scenarios.json"


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run real Gemini Live copilot evaluations over backend WebSocket.")
    parser.add_argument("--ws-url", default="ws://localhost:8000/ws")
    parser.add_argument("--scenarios", default=str(DEFAULT_SCENARIOS))
    parser.add_argument("--scenario-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--query-timeout", type=float, default=45.0)
    parser.add_argument("--turn-delay", type=float, default=0.8)
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--out-dir", default=settings.EVAL_REPORT_DIR)
    args = parser.parse_args()

    scenario_doc = _load_json(Path(args.scenarios))
    scenarios = scenario_doc.get("scenarios", [])
    if args.scenario_id:
        selected = set(args.scenario_id)
        scenarios = [scenario for scenario in scenarios if scenario.get("id") in selected]
    if args.limit > 0:
        scenarios = scenarios[: args.limit]
    if not scenarios:
        raise SystemExit("No scenarios selected.")

    run_id = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out_dir) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for scenario in scenarios:
        print(f"RUN {scenario['id']}")
        try:
            result = await run_scenario(
                ws_url=args.ws_url,
                scenario=scenario,
                query_timeout=args.query_timeout,
                turn_delay=args.turn_delay,
                judge=not args.no_judge,
            )
        except Exception as exc:
            result = build_scenario_failure_result(
                scenario=scenario,
                session_id=None,
                events=[],
                ai_pairs=[],
                error=f"{type(exc).__name__}: {exc}",
                stage="scenario_exception",
            )
        results.append(result)
        _write_json(out_dir / f"{scenario['id']}.json", result)
        if result.get("error"):
            print(f"FAIL {scenario['id']} error={result['error']}")
        else:
            print(f"DONE {scenario['id']} score={result['summary']['score']:.2f} pass={result['summary']['passed']}")

    summary = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "scenario_count": len(results),
        "passed": sum(1 for result in results if result["summary"]["passed"]),
        "average_score": round(sum(result["summary"]["score"] for result in results) / max(1, len(results)), 3),
        "results": [
            {
                "scenario_id": result["scenario_id"],
                "title": result["title"],
                "score": result["summary"]["score"],
                "passed": result["summary"]["passed"],
                "report": f"{result['scenario_id']}.json",
            }
            for result in results
        ],
    }
    _write_json(out_dir / "summary.json", summary)
    print(f"REPORT {out_dir}")
    return 0 if summary["passed"] == summary["scenario_count"] else 1


async def run_scenario(
    *,
    ws_url: str,
    scenario: dict[str, Any],
    query_timeout: float,
    turn_delay: float,
    judge: bool,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    ai_pairs: list[dict[str, Any]] = []
    pending_judges: list[tuple[int, dict[str, Any]]] = []
    session_id: str | None = None

    try:
        async with websockets.connect(
            ws_url,
            max_size=16 * 1024 * 1024,
            open_timeout=60,
            ping_interval=20,
            ping_timeout=90,
            close_timeout=15,
        ) as ws:
            session_id_event = await _wait_for_type(ws, "CONNECTION_ESTABLISHED", events, timeout=15.0)
            session_id = session_id_event.get("payload", {}).get("session_id")

            await _send(ws, "PRIVACY_CONSENT_GRANTED", {"version": "eval-1", "mode": "roleplay"})
            await _wait_for_type(ws, "CONSENT_ACKNOWLEDGED", events, timeout=15.0)

            await _send(ws, "START_NEGOTIATION", {
                "context": scenario.get("context", ""),
                "user_context": {
                    "item": scenario.get("title", ""),
                    "target_price": _extract_context_number(scenario.get("context", ""), "target"),
                    "max_price": _extract_context_number(scenario.get("context", ""), "cap"),
                    "scenario_id": scenario.get("id"),
                },
            })
            await _wait_for_type(ws, "SESSION_STARTED", events, timeout=75.0)

            await _send(ws, "START_COPILOT", {})
            await _drain_until_quiet(ws, events, quiet_seconds=0.4, timeout=5.0)

            queries_by_turn = {}
            for query in scenario.get("queries", []):
                queries_by_turn.setdefault(int(query["after_turn"]), []).append(query)

            timestamp_ms = int(time.time() * 1000)
            for index, turn in enumerate(scenario.get("turns", []), start=1):
                timestamp_ms += int(max(turn_delay, 0.1) * 1000)
                await _send(ws, "SIMULATED_NEGOTIATION_TURN", {
                    "scenario_id": scenario.get("id"),
                    "turn_id": f"{scenario.get('id')}_turn_{index}",
                    "speaker": turn["speaker"],
                    "text": turn["text"],
                    "timestamp_ms": timestamp_ms,
                })
                await _wait_for_type(ws, "SIMULATED_TURN_ACCEPTED", events, timeout=15.0)
                await _drain_until_quiet(ws, events, quiet_seconds=0.2, timeout=2.0)

                for query_index, query in enumerate(queries_by_turn.get(index, []), start=1):
                    query_payload = {
                        "response_mode": query.get("mode", "advice"),
                        "query": query["text"],
                        "eval_metadata": {
                            "scenario_id": scenario.get("id"),
                            "after_turn": index,
                            "query_index": query_index,
                        },
                    }
                    await _send(ws, "ASK_ADVICE", query_payload)
                    try:
                        response = await _wait_for_ai_response(
                            ws,
                            events,
                            mode=query_payload["response_mode"],
                            timeout=query_timeout,
                        )
                        await _wait_for_ai_idle(ws, events, timeout=15.0)
                    except Exception as exc:
                        ai_pairs.append(build_failed_pair(scenario, query, index, query_payload["response_mode"], exc, events))
                        await _safe_end_negotiation(ws, events)
                        if judge and pending_judges:
                            for pair_index, pair_snapshot in pending_judges:
                                ai_pairs[pair_index]["judge"] = await asyncio.to_thread(judge_pair, scenario, pair_snapshot)
                        return build_scenario_failure_result(
                            scenario=scenario,
                            session_id=session_id,
                            events=events,
                            ai_pairs=ai_pairs,
                            error=f"{type(exc).__name__}: {exc}",
                            stage=f"query_after_turn_{index}",
                        )

                    pair = {
                        "after_turn": index,
                        "mode": query_payload["response_mode"],
                        "query": query["text"],
                        "expected_direction": query.get("expected_direction", ""),
                        "response": response.get("payload", {}).get("text", ""),
                        "timestamp_ms": response.get("payload", {}).get("timestamp"),
                    }
                    pair["deterministic_score"] = score_pair(scenario, pair)
                    if judge:
                        pending_judges.append((len(ai_pairs), pair.copy()))
                    ai_pairs.append(pair)
                    await _drain_until_quiet(ws, events, quiet_seconds=0.5, timeout=3.0)

            await _safe_end_negotiation(ws, events)
    except Exception as exc:
        if judge and pending_judges:
            for index, pair_snapshot in pending_judges:
                ai_pairs[index]["judge"] = await asyncio.to_thread(judge_pair, scenario, pair_snapshot)
        return build_scenario_failure_result(
            scenario=scenario,
            session_id=session_id,
            events=events,
            ai_pairs=ai_pairs,
            error=f"{type(exc).__name__}: {exc}",
            stage="scenario_runtime",
        )

    if judge and pending_judges:
        for index, pair_snapshot in pending_judges:
            ai_pairs[index]["judge"] = await asyncio.to_thread(judge_pair, scenario, pair_snapshot)

    summary = summarize_pairs(ai_pairs)
    return {
        "scenario_id": scenario.get("id"),
        "title": scenario.get("title"),
        "family": scenario.get("family"),
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "summary": summary,
        "ai_pairs": ai_pairs,
        "events": events,
    }


def build_failed_pair(
    scenario: dict[str, Any],
    query: dict[str, Any],
    after_turn: int,
    mode: str,
    exc: Exception,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "after_turn": after_turn,
        "mode": mode,
        "query": query.get("text", ""),
        "expected_direction": query.get("expected_direction", ""),
        "response": "",
        "timestamp_ms": None,
        "error": f"{type(exc).__name__}: {exc}",
        "diagnostic": _summarize_recent_events(events),
        "deterministic_score": {
            "score": 0.0,
            "checks": {
                "number_grounding": 0.0,
                "term_grounding": 0.0,
                "actionable": 0.0,
                "concise": 0.0,
                "non_generic": 0.0,
            },
            "relevant_numbers": [str(value).lower() for value in scenario.get("must_track_numbers", [])],
            "relevant_terms": [str(value).lower() for value in scenario.get("must_track_terms", [])],
            "number_hits": [],
            "term_hits": [],
        },
    }


def build_scenario_failure_result(
    *,
    scenario: dict[str, Any],
    session_id: str | None,
    events: list[dict[str, Any]],
    ai_pairs: list[dict[str, Any]],
    error: str,
    stage: str,
) -> dict[str, Any]:
    summary = summarize_pairs(ai_pairs)
    return {
        "scenario_id": scenario.get("id"),
        "title": scenario.get("title"),
        "family": scenario.get("family"),
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "summary": summary,
        "ai_pairs": ai_pairs,
        "events": events,
        "error": error,
        "failure_stage": stage,
        "diagnostic": _summarize_recent_events(events),
    }


def score_pair(scenario: dict[str, Any], pair: dict[str, Any]) -> dict[str, Any]:
    response = _normalize_for_matching(pair.get("response", ""))
    query = _normalize_for_matching(pair.get("query", ""))
    expected = _normalize_for_matching(pair.get("expected_direction", ""))
    numbers = [str(value).lower() for value in scenario.get("must_track_numbers", [])]
    terms = [str(value).lower() for value in scenario.get("must_track_terms", [])]

    number_aliases = {number: _number_aliases(number) for number in numbers}
    relevant_numbers = [
        number
        for number, aliases in number_aliases.items()
        if _contains_any_alias(query, aliases) or _contains_any_alias(expected, aliases)
    ]
    if not relevant_numbers:
        relevant_numbers = [
            number for number, aliases in number_aliases.items()
            if _contains_any_alias(response, aliases)
        ]
    number_hits = [
        number for number in relevant_numbers
        if _contains_any_alias(response, number_aliases[number])
    ]

    term_aliases = {term: _term_aliases(term) for term in terms}
    relevant_terms = [
        term
        for term, aliases in term_aliases.items()
        if _contains_any_alias(query, aliases) or _contains_any_alias(expected, aliases)
    ]
    if not relevant_terms:
        relevant_terms = [
            term for term, aliases in term_aliases.items()
            if _contains_any_alias(response, aliases)
        ]
    term_hits = [
        term for term in relevant_terms
        if _contains_any_alias(response, term_aliases[term])
    ]

    generic_markers = ["build rapport", "stay calm", "be confident", "listen actively"]
    generic_penalty = any(marker in response for marker in generic_markers)
    actionable = any(marker in response for marker in ("say:", "ask", "push", "counter", "offer", "close", "trade", "hold", "protect"))
    concise = len(response.split()) <= 90

    checks = {
        "number_grounding": len(number_hits) / max(1, len(relevant_numbers)),
        "term_grounding": len(term_hits) / max(1, len(relevant_terms)),
        "actionable": 1.0 if actionable else 0.0,
        "concise": 1.0 if concise else 0.0,
        "non_generic": 0.0 if generic_penalty else 1.0,
    }
    score = (
        checks["number_grounding"] * 0.30
        + checks["term_grounding"] * 0.25
        + checks["actionable"] * 0.20
        + checks["concise"] * 0.10
        + checks["non_generic"] * 0.15
    )
    return {
        "score": round(score, 3),
        "checks": checks,
        "relevant_numbers": relevant_numbers,
        "relevant_terms": relevant_terms,
        "number_hits": number_hits,
        "term_hits": term_hits,
    }


def _normalize_for_matching(text: str) -> str:
    normalized = str(text or "").lower()
    normalized = normalized.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    normalized = _replace_spoken_numbers(normalized)
    normalized = re.sub(r"\b(\d+(?:\.\d+)?)\s*k\b", lambda m: str(int(float(m.group(1)) * 1000)), normalized)
    normalized = normalized.replace(",", "")
    normalized = re.sub(r"[$₹€£]", "", normalized)
    normalized = re.sub(r"[-_/]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return f" {normalized} "


def _number_aliases(number: str) -> list[str]:
    raw = str(number).strip().lower().replace(",", "")
    aliases = {raw}
    try:
        value = float(raw)
    except ValueError:
        return sorted(aliases, key=len, reverse=True)

    if value.is_integer():
        int_value = int(value)
        aliases.add(str(int_value))
        if int_value >= 1000 and int_value % 1000 == 0:
            short = int_value // 1000
            aliases.add(f"{short}k")
            aliases.add(str(short))
            aliases.add(f"{short} thousand")
        if int_value >= 1000:
            aliases.add(f"{int_value:,}")
    else:
        aliases.add(str(value))
    return sorted(aliases, key=len, reverse=True)


def _term_aliases(term: str) -> list[str]:
    normalized = _normalize_for_matching(term).strip()
    aliases = {normalized}
    if "auto renewal" in normalized:
        aliases.add("auto renew")
    if "net 60" in normalized:
        aliases.add("standard payment timing")
        aliases.add("standard payment terms")
        aliases.add("payment timing")
        aliases.add("payment terms")
    if "net 45" in normalized:
        aliases.add("payment terms")
    return sorted(aliases, key=len, reverse=True)


def _contains_any_alias(text: str, aliases: list[str]) -> bool:
    normalized_text = text if text.startswith(" ") else _normalize_for_matching(text)
    for alias in aliases:
        normalized_alias = _normalize_for_matching(alias).strip()
        if not normalized_alias:
            continue
        if re.search(rf"(?<!\d){re.escape(normalized_alias)}(?!\d)", normalized_text):
            return True
    return False


_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
    "thousand": 1000,
}


def _replace_spoken_numbers(text: str) -> str:
    words = "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))

    def repl(match: re.Match) -> str:
        phrase = match.group(0).replace("-", " ")
        tokens = phrase.split()
        value = _parse_number_words(tokens)
        return str(value) if value is not None else match.group(0)

    return re.sub(rf"\b(?:{words})(?:[\s-]+(?:{words}))*\b", repl, text)


def _parse_number_words(tokens: list[str]) -> int | None:
    total = 0
    current = 0
    used = False
    for token in tokens:
        value = _NUMBER_WORDS.get(token)
        if value is None:
            return None
        used = True
        if value == 100:
            current = max(current, 1) * value
        elif value == 1000:
            total += max(current, 1) * value
            current = 0
        else:
            current += value
    if not used:
        return None
    return total + current


def judge_pair(scenario: dict[str, Any], pair: dict[str, Any]) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    if settings.GOOGLE_GENAI_USE_VERTEXAI:
        client = genai.Client(
            vertexai=True,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        )
        model = settings.EVAL_JUDGE_MODEL
        if not model.startswith("google/"):
            model = f"google/{model}"
    else:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        model = settings.EVAL_JUDGE_MODEL

    prompt = f"""You are judging a live negotiation copilot answer.
Return strict JSON only.

Scenario:
{json.dumps({k: scenario.get(k) for k in ('id', 'family', 'title', 'context', 'must_track_numbers', 'must_track_terms')}, ensure_ascii=False)}

User query:
{pair.get('query')}

Expected direction:
{pair.get('expected_direction')}

AI response:
{pair.get('response')}

Score each from 1 to 5:
- deal_state_grounding
- speaker_attribution
- actionability
- commercial_quality
- non_genericness
- constraint_obedience
- hallucination_avoidance
- timing_relevance

JSON shape:
{{
  "scores": {{"deal_state_grounding": 1, "speaker_attribution": 1, "actionability": 1, "commercial_quality": 1, "non_genericness": 1, "constraint_obedience": 1, "hallucination_avoidance": 1, "timing_relevance": 1}},
  "average": 1.0,
  "passed": false,
  "rationale": "short reason",
  "best_fix": "short improvement"
}}"""

    try:
        response = client.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(temperature=0.0),
        )
        return _parse_json_object(response.text or "")
    except Exception as exc:
        return {
            "scores": {},
            "average": 0.0,
            "passed": False,
            "rationale": f"judge_failed: {exc}",
            "best_fix": "Check judge model configuration and credentials.",
        }


def summarize_pairs(ai_pairs: list[dict[str, Any]]) -> dict[str, Any]:
    if not ai_pairs:
        return {"score": 0.0, "passed": False, "query_count": 0}
    deterministic = [pair["deterministic_score"]["score"] for pair in ai_pairs]
    judge_scores = [
        float(pair.get("judge", {}).get("average", 0.0)) / 5.0
        for pair in ai_pairs
        if pair.get("judge")
    ]
    blended = []
    for index, base_score in enumerate(deterministic):
        if index < len(judge_scores):
            blended.append((base_score * 0.45) + (judge_scores[index] * 0.55))
        else:
            blended.append(base_score)
    score = round(sum(blended) / max(1, len(blended)), 3)
    # Threshold raised from 0.78 -> 0.85 after Pro-tier advisor upgrade.
    # 0.85 keeps the average ~0.90 target achievable while leaving room for one
    # off-target answer per scenario.
    return {
        "score": score,
        "passed": score >= 0.85,
        "query_count": len(ai_pairs),
        "deterministic_average": round(sum(deterministic) / len(deterministic), 3),
        "judge_average": round(sum(judge_scores) / len(judge_scores), 3) if judge_scores else None,
    }


async def _safe_end_negotiation(ws, events: list[dict[str, Any]]) -> None:
    try:
        await _send(ws, "END_NEGOTIATION", {
            "source": "eval_harness",
            "reason": "scenario_complete",
        })
    except Exception:
        return
    try:
        await _wait_for_negotiation_end(ws, events, timeout=8.0)
    except Exception:
        return


async def _wait_for_negotiation_end(ws, events: list[dict[str, Any]], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    saw_outcome_summary = False
    saw_idle_state = False

    while time.monotonic() < deadline:
        remaining = max(0.1, deadline - time.monotonic())
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        event = _decode_event(raw)
        if not event:
            continue
        events.append(event)
        if event.get("type") == "ERROR":
            raise RuntimeError(f"Backend error: {event.get('payload')}")

        event_type = event.get("type")
        payload = event.get("payload") or {}
        if event_type == "OUTCOME_SUMMARY":
            saw_outcome_summary = True
        elif event_type == "NEGOTIATION_STATE_CHANGED" and payload.get("current_state") == "IDLE":
            saw_idle_state = True

        if saw_outcome_summary and saw_idle_state:
            return

    raise TimeoutError("Timed out waiting for negotiation end acknowledgement")


def _summarize_recent_events(events: list[dict[str, Any]], limit: int = 12) -> dict[str, Any]:
    recent = events[-limit:]
    type_counts: dict[str, int] = {}
    recent_types: list[str] = []
    ai_transcript_payloads: list[dict[str, Any]] = []
    for event in recent:
        event_type = str(event.get("type") or "UNKNOWN")
        type_counts[event_type] = type_counts.get(event_type, 0) + 1
        recent_types.append(event_type)
        payload = event.get("payload") or {}
        if event_type == "TRANSCRIPT_UPDATE" and payload.get("speaker") == "ai":
            ai_transcript_payloads.append(payload)
    return {
        "recent_event_types": recent_types,
        "recent_event_counts": type_counts,
        "last_ai_transcript_payload": ai_transcript_payloads[-1] if ai_transcript_payloads else None,
        "last_event": recent[-1] if recent else None,
    }


async def _send(ws, message_type: str, payload: dict[str, Any]) -> None:
    await ws.send(json.dumps({"type": message_type, "payload": payload}))


async def _wait_for_type(ws, message_type: str, events: list[dict[str, Any]], timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = max(0.1, deadline - time.monotonic())
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        event = _decode_event(raw)
        if not event:
            continue
        events.append(event)
        if event.get("type") == "ERROR":
            raise RuntimeError(f"Backend error: {event.get('payload')}")
        if event.get("type") == message_type:
            return event
    raise TimeoutError(f"Timed out waiting for {message_type}")


async def _wait_for_ai_response(ws, events: list[dict[str, Any]], mode: str, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    correction_extensions = 0
    while time.monotonic() < deadline:
        remaining = max(0.1, deadline - time.monotonic())
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        event = _decode_event(raw)
        if not event:
            continue
        events.append(event)
        if event.get("type") == "ERROR":
            raise RuntimeError(f"Backend error: {event.get('payload')}")
        if event.get("type") == "AI_CORRECTION_SENT" and correction_extensions < 2:
            correction_extensions += 1
            deadline = max(deadline, time.monotonic() + min(timeout, 20.0))
            continue
        payload = event.get("payload") or {}
        if event.get("type") == "TRANSCRIPT_UPDATE" and payload.get("speaker") == "ai":
            if payload.get("response_mode") in (None, mode):
                return event
    raise TimeoutError("Timed out waiting for AI response")


async def _wait_for_ai_idle(ws, events: list[dict[str, Any]], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = max(0.1, deadline - time.monotonic())
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        event = _decode_event(raw)
        if not event:
            continue
        events.append(event)
        if event.get("type") == "ERROR":
            raise RuntimeError(f"Backend error: {event.get('payload')}")
        if event.get("type") in {"AI_LISTENING", "AI_DEGRADED"}:
            return
    raise TimeoutError("Timed out waiting for AI_LISTENING after response")


async def _drain_until_quiet(ws, events: list[dict[str, Any]], quiet_seconds: float, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=quiet_seconds)
        except asyncio.TimeoutError:
            return
        event = _decode_event(raw)
        if event:
            events.append(event)


def _decode_event(raw: str | bytes) -> dict[str, Any] | None:
    if isinstance(raw, bytes):
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        stripped = stripped[start : end + 1]
    return json.loads(stripped)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _first_number(text: str) -> str | None:
    match = re.search(r"\b\d+(?:\.\d+)?\b", text or "")
    return match.group(0) if match else None


def _extract_context_number(text: str, label: str) -> str | None:
    text = text or ""
    patterns = {
        "target": [
            r"\btarget\s+is\s+(\d+(?:\.\d+)?)\b",
            r"\bwants?\s+(\d+(?:\.\d+)?)\b",
        ],
        "cap": [
            r"\bcap\s+is\s+(\d+(?:\.\d+)?)\b",
            r"\bwalk[-\s]?away\s+(?:is\s+)?(\d+(?:\.\d+)?)\b",
            r"\bmax(?:imum)?\s+(?:is\s+)?(\d+(?:\.\d+)?)\b",
        ],
    }
    for pattern in patterns.get(label, []):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
