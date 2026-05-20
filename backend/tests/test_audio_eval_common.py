from __future__ import annotations

from scripts.audio_eval_common import (
    EvaluatedTurn,
    aggregate_turns,
    detect_edge_drop,
    number_recall,
    word_error_rate,
)


def test_word_error_rate_detects_single_word_change():
    assert word_error_rate("I can do eighty two only", "I can do eighty three only") == 0.1667


def test_detect_edge_drop_flags_leading_and_trailing_loss():
    result = detect_edge_drop("I can do eighty two only", "can do eighty two")
    assert result["leading_word_drop"] is True
    assert result["trailing_word_drop"] is True


def test_number_recall_tracks_missing_numeric_terms():
    result = number_recall("I need 35 sign on and 80 equity", "I need 35 sign on")
    assert result["hits"] == ["35"]
    assert result["misses"] == ["80"]
    assert result["recall"] == 0.5


def test_aggregate_turns_passes_only_when_all_hard_gates_pass():
    turns = [
        EvaluatedTurn(
            fixture_id="f1",
            scenario_id="s1",
            voice_pair_id="p1",
            condition="clean",
            expected_speaker="user",
            observed_speaker="user",
            expected_text="I can do eighty two only with net sixty",
            observed_text="I can do eighty two only with net sixty",
            transcript_count=1,
            latency_ms=420.0,
            timeout=False,
            speaker_confidence=0.98,
            stage_markers=["UTTERANCE_CLASSIFIED", "STT_RESULT"],
            metadata={},
        ).to_dict(),
        EvaluatedTurn(
            fixture_id="f2",
            scenario_id="s1",
            voice_pair_id="p1",
            condition="clean",
            expected_speaker="counterparty",
            observed_speaker="counterparty",
            expected_text="At eighty four we can keep delivery included",
            observed_text="At eighty four we can keep delivery included",
            transcript_count=1,
            latency_ms=510.0,
            timeout=False,
            speaker_confidence=0.94,
            stage_markers=["UTTERANCE_CLASSIFIED", "STT_RESULT"],
            metadata={},
        ).to_dict(),
    ]

    summary = aggregate_turns(turns, suite_name="audio_backend_eval", run_id="run-1")

    assert summary["pass"] is True
    assert summary["speaker_accuracy"] == 1.0
    assert summary["false_user_count"] == 0
    assert summary["false_counterparty_count"] == 0


def test_aggregate_turns_fails_on_false_user_claim():
    turns = [
        EvaluatedTurn(
            fixture_id="f1",
            scenario_id="s1",
            voice_pair_id="p1",
            condition="clean",
            expected_speaker="counterparty",
            observed_speaker="user",
            expected_text="No.",
            observed_text="No.",
            transcript_count=1,
            latency_ms=330.0,
            timeout=False,
            speaker_confidence=0.88,
            stage_markers=["UTTERANCE_CLASSIFIED", "STT_RESULT"],
            metadata={},
        ).to_dict()
    ]

    summary = aggregate_turns(turns, suite_name="audio_backend_eval", run_id="run-1")

    assert summary["pass"] is False
    assert summary["false_user_count"] == 1
    assert summary["speaker_accuracy"] == 0.0
