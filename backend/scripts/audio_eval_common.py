from __future__ import annotations

import json
import math
import re
import statistics
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)?")
NUMBER_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compact_text(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def tokenize(value: str | None) -> list[str]:
    return [match.group(0).lower() for match in WORD_RE.finditer(compact_text(value))]


def extract_numbers(value: str | None) -> list[str]:
    return [match.group(0).lower() for match in NUMBER_TOKEN_RE.finditer(compact_text(value))]


def levenshtein_words(reference: list[str], hypothesis: list[str]) -> int:
    m, n = len(reference), len(hypothesis)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if reference[i - 1] == hypothesis[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],
                    dp[i][j - 1],
                    dp[i - 1][j - 1],
                )
    return dp[m][n]


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref_tokens = tokenize(reference)
    hyp_tokens = tokenize(hypothesis)
    if not ref_tokens:
        return 0.0 if not hyp_tokens else 1.0
    return round(levenshtein_words(ref_tokens, hyp_tokens) / len(ref_tokens), 4)


def _common_prefix_length(reference: list[str], hypothesis: list[str]) -> int:
    count = 0
    for ref_token, hyp_token in zip(reference, hypothesis):
        if ref_token != hyp_token:
            break
        count += 1
    return count


def _common_suffix_length(reference: list[str], hypothesis: list[str]) -> int:
    count = 0
    for ref_token, hyp_token in zip(reversed(reference), reversed(hypothesis)):
        if ref_token != hyp_token:
            break
        count += 1
    return count


def detect_edge_drop(reference: str, hypothesis: str) -> dict[str, Any]:
    ref_tokens = tokenize(reference)
    hyp_tokens = tokenize(hypothesis)

    if not ref_tokens:
        return {
            "leading_word_drop": False,
            "trailing_word_drop": False,
            "leading_drop_count": 0,
            "trailing_drop_count": 0,
        }

    prefix = _common_prefix_length(ref_tokens, hyp_tokens)
    suffix = _common_suffix_length(ref_tokens[prefix:], hyp_tokens[prefix:]) if prefix < len(ref_tokens) else 0

    leading_drop_count = 0
    trailing_drop_count = 0

    if hyp_tokens:
        if ref_tokens[0] != hyp_tokens[0]:
            leading_drop_count = 1
        if ref_tokens[-1] != hyp_tokens[-1]:
            trailing_drop_count = 1
    else:
        leading_drop_count = 1
        trailing_drop_count = 1

    return {
        "leading_word_drop": leading_drop_count > 0,
        "trailing_word_drop": trailing_drop_count > 0,
        "leading_drop_count": leading_drop_count,
        "trailing_drop_count": trailing_drop_count,
        "common_prefix_tokens": prefix,
        "common_suffix_tokens": suffix,
    }


def number_recall(reference: str, hypothesis: str) -> dict[str, Any]:
    expected = extract_numbers(reference)
    observed = extract_numbers(hypothesis)
    observed_counter = Counter(observed)
    hits: list[str] = []
    misses: list[str] = []

    for number in expected:
        if observed_counter[number] > 0:
            hits.append(number)
            observed_counter[number] -= 1
        else:
            misses.append(number)

    recall = 1.0 if not expected else round(len(hits) / len(expected), 4)
    return {
        "expected": expected,
        "observed": observed,
        "hits": hits,
        "misses": misses,
        "recall": recall,
    }


def rms_dbfs(pcm_bytes: bytes) -> float:
    if not pcm_bytes:
        return float("-inf")
    sample_count = len(pcm_bytes) // 2
    if sample_count == 0:
        return float("-inf")
    accum = 0.0
    for index in range(0, len(pcm_bytes), 2):
        sample = int.from_bytes(pcm_bytes[index:index + 2], byteorder="little", signed=True)
        accum += (sample / 32768.0) ** 2
    rms = math.sqrt(accum / sample_count)
    if rms <= 0.0:
        return float("-inf")
    return round(20.0 * math.log10(rms), 3)


def p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return round(float(ordered[idx]), 3)


def safe_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(statistics.mean(values)), 3)


@dataclass
class EvaluatedTurn:
    fixture_id: str
    scenario_id: str
    voice_pair_id: str
    condition: str
    expected_speaker: str
    observed_speaker: str | None
    expected_text: str
    observed_text: str
    transcript_count: int
    latency_ms: float | None
    timeout: bool
    speaker_confidence: float | None
    stage_markers: list[str]
    metadata: dict[str, Any]
    failure_kind: str | None = None
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        edge = detect_edge_drop(self.expected_text, self.observed_text)
        num = number_recall(self.expected_text, self.observed_text)
        speaker_correct = self.observed_speaker == self.expected_speaker
        missing = not compact_text(self.observed_text)
        return {
            "fixture_id": self.fixture_id,
            "scenario_id": self.scenario_id,
            "voice_pair_id": self.voice_pair_id,
            "condition": self.condition,
            "expected_speaker": self.expected_speaker,
            "observed_speaker": self.observed_speaker,
            "speaker_correct": speaker_correct,
            "wrong_label": bool(self.observed_speaker and not speaker_correct),
            "missing_transcript": missing,
            "timeout": self.timeout,
            "failure_kind": self.failure_kind,
            "failure_reason": self.failure_reason,
            "expected_text": self.expected_text,
            "observed_text": compact_text(self.observed_text),
            "wer": word_error_rate(self.expected_text, self.observed_text),
            "number_recall": num,
            "leading_word_drop": edge["leading_word_drop"],
            "trailing_word_drop": edge["trailing_word_drop"],
            "leading_drop_count": edge["leading_drop_count"],
            "trailing_drop_count": edge["trailing_drop_count"],
            "transcript_count": self.transcript_count,
            "latency_ms": self.latency_ms,
            "speaker_confidence": self.speaker_confidence,
            "stage_markers": self.stage_markers,
            "metadata": self.metadata,
        }


def aggregate_turns(
    turns: list[dict[str, Any]],
    *,
    suite_name: str,
    run_id: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    total = len(turns)
    wrong_label_count = sum(1 for turn in turns if turn["wrong_label"])
    false_user_count = sum(1 for turn in turns if turn["observed_speaker"] == "user" and turn["expected_speaker"] != "user")
    false_counterparty_count = sum(
        1 for turn in turns if turn["observed_speaker"] == "counterparty" and turn["expected_speaker"] != "counterparty"
    )
    missing_count = sum(1 for turn in turns if turn["missing_transcript"])
    timeout_count = sum(1 for turn in turns if turn["timeout"])
    failure_kind_counts = Counter(turn["failure_kind"] or "none" for turn in turns)
    leading_drop_count = sum(1 for turn in turns if turn["leading_word_drop"])
    trailing_drop_count = sum(1 for turn in turns if turn["trailing_word_drop"])
    latencies = [float(turn["latency_ms"]) for turn in turns if turn.get("latency_ms") is not None]
    wers = [float(turn["wer"]) for turn in turns]
    correct_labels = sum(1 for turn in turns if turn["speaker_correct"])

    confusion_counter: dict[str, dict[str, int]] = {}
    for turn in turns:
        expected = turn["expected_speaker"]
        observed = turn["observed_speaker"] or "missing"
        confusion_counter.setdefault(expected, {})
        confusion_counter[expected][observed] = confusion_counter[expected].get(observed, 0) + 1

    by_condition: dict[str, dict[str, Any]] = {}
    for condition in sorted({turn["condition"] for turn in turns}):
        condition_turns = [turn for turn in turns if turn["condition"] == condition]
        by_condition[condition] = {
            "turn_count": len(condition_turns),
            "speaker_accuracy": round(
                sum(1 for turn in condition_turns if turn["speaker_correct"]) / max(1, len(condition_turns)),
                4,
            ),
            "false_user_count": sum(
                1 for turn in condition_turns if turn["observed_speaker"] == "user" and turn["expected_speaker"] != "user"
            ),
            "false_counterparty_count": sum(
                1 for turn in condition_turns
                if turn["observed_speaker"] == "counterparty" and turn["expected_speaker"] != "counterparty"
            ),
            "missing_transcript_count": sum(1 for turn in condition_turns if turn["missing_transcript"]),
            "wer_mean": safe_mean([float(turn["wer"]) for turn in condition_turns]),
            "p95_latency_ms": p95([float(turn["latency_ms"]) for turn in condition_turns if turn.get("latency_ms") is not None]),
            "leading_word_drop_count": sum(1 for turn in condition_turns if turn["leading_word_drop"]),
            "trailing_word_drop_count": sum(1 for turn in condition_turns if turn["trailing_word_drop"]),
        }

    summary = {
        "suite": suite_name,
        "run_id": run_id,
        "turn_count": total,
        "speaker_accuracy": round(correct_labels / max(1, total), 4),
        "false_user_count": false_user_count,
        "false_counterparty_count": false_counterparty_count,
        "wrong_label_count": wrong_label_count,
        "missing_transcript_count": missing_count,
        "timeout_count": timeout_count,
        "failure_kind_counts": dict(sorted(failure_kind_counts.items())),
        "wer_mean": safe_mean(wers),
        "leading_word_drop_count": leading_drop_count,
        "trailing_word_drop_count": trailing_drop_count,
        "latency_ms_mean": safe_mean(latencies),
        "latency_ms_p95": p95(latencies),
        "confusion_matrix": confusion_counter,
        "by_condition": by_condition,
        "pass": (
            round(correct_labels / max(1, total), 4) >= 0.99
            and false_user_count == 0
            and false_counterparty_count == 0
            and (missing_count / max(1, total)) < 0.01
            and (safe_mean(wers) or 0.0) <= 0.15
            and (leading_drop_count / max(1, total)) < 0.01
            and (trailing_drop_count / max(1, total)) < 0.01
        ),
    }
    if extra:
        summary.update(extra)
    return summary


def parse_speaker_debug_lines(path: Path, session_id: str, limit: int = 200) -> list[str]:
    if not path.exists():
        return []
    lines = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if session_id in line:
            lines.append(line.strip())
    return lines[-limit:]


def build_report(
    *,
    suite_name: str,
    run_id: str,
    manifest_id: str,
    scenarios: list[dict[str, Any]],
    turns: list[dict[str, Any]],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = aggregate_turns(turns, suite_name=suite_name, run_id=run_id, extra=extra)
    return {
        "suite": suite_name,
        "run_id": run_id,
        "manifest_id": manifest_id,
        "created_at_ms": int(time.time() * 1000),
        "scenario_count": len(scenarios),
        "summary": summary,
        "scenarios": scenarios,
        "turns": turns,
    }
