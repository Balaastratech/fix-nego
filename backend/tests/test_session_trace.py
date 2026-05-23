from pathlib import Path

from app.utils.session_trace import SessionTrace


def test_session_trace_writes_jsonl_and_report(tmp_path: Path) -> None:
    trace = SessionTrace("session-123", root_dir=tmp_path)

    artifact_path = trace.write_text_artifact(
        "pre_query_brief",
        "FULL BRIEF BODY",
        ext=".txt",
    )
    event = trace.record(
        category="ask_ai",
        name="pre_query_brief_sent",
        summary="Sent pre-query brief before user question",
        data={"chars": 15, "contains": ["vision", "transcript"]},
        artifacts=[artifact_path],
    )

    report_path = trace.finalize()

    jsonl_path = tmp_path / "session-123" / "trace.jsonl"
    assert jsonl_path.exists()
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert '"name": "pre_query_brief_sent"' in lines[0]
    assert event["event_id"] in lines[0]

    assert report_path.exists()
    report = report_path.read_text(encoding="utf-8")
    assert "Structured Session Trace Report" in report
    assert "pre_query_brief_sent" in report
    assert "FULL BRIEF BODY" not in report
    assert "pre_query_brief" in report
