from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import soundfile as sf
import websockets

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from scripts.audio_eval_common import (  # noqa: E402
    EvaluatedTurn,
    build_report,
    compact_text,
    parse_speaker_debug_lines,
    rms_dbfs,
    tokenize,
    write_json,
)


DEFAULT_MANIFEST = BACKEND_ROOT / "evals" / "audio_fixtures" / "manifest.json"
DEFAULT_REPORT_DIR = Path("data/audio_eval_reports/backend")
DEFAULT_BACKEND_LOG = BACKEND_ROOT / "data" / "logs" / "audio_eval_backend_start.err.log"


def load_wav_pcm(path: Path) -> tuple[bytes, int]:
    audio, sample_rate = sf.read(str(path), dtype="int16")
    if audio.ndim > 1:
        audio = audio[:, 0]
    return audio.tobytes(), int(sample_rate)


def pcm_duration_ms(pcm_bytes: bytes, sample_rate: int = 16000) -> int:
    return int(round((len(pcm_bytes) / 2 / sample_rate) * 1000))


def pcm_peak_rms(pcm_bytes: bytes) -> float:
    if not pcm_bytes:
        return 0.0
    sample_count = len(pcm_bytes) // 2
    if sample_count == 0:
        return 0.0
    accum = 0.0
    for index in range(0, len(pcm_bytes), 2):
        sample = int.from_bytes(pcm_bytes[index:index + 2], byteorder="little", signed=True)
        accum += sample * sample
    return math.sqrt(accum / sample_count)


async def _send(ws, message_type: str, payload: dict[str, Any]) -> None:
    await ws.send(json.dumps({"type": message_type, "payload": payload}))


def _decode_event(raw: str | bytes) -> dict[str, Any] | None:
    if isinstance(raw, bytes):
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def _wait_for_type(ws, message_type: str, events: list[dict[str, Any]], timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.monotonic()))
        event = _decode_event(raw)
        if not event:
            continue
        events.append(event)
        if event.get("type") == "ERROR":
            raise RuntimeError(f"Backend error: {event.get('payload')}")
        if event.get("type") == message_type:
            return event
    raise TimeoutError(f"Timed out waiting for {message_type}")


async def _wait_for_enrollment_complete(ws, events: list[dict[str, Any]], timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.monotonic()))
        event = _decode_event(raw)
        if not event:
            continue
        events.append(event)
        if event.get("type") == "ERROR":
            raise RuntimeError(f"Backend error: {event.get('payload')}")
        if event.get("type") == "ENROLLMENT_FAILED":
            raise RuntimeError(f"Enrollment failed: {event.get('payload')}")
        if event.get("type") == "ENROLLMENT_COMPLETE":
            return event
    raise TimeoutError("Timed out waiting for ENROLLMENT_COMPLETE")


async def _wait_for_negotiation_end(ws, events: list[dict[str, Any]], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    saw_summary = False
    saw_idle = False
    while time.monotonic() < deadline:
        raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.monotonic()))
        event = _decode_event(raw)
        if not event:
            continue
        events.append(event)
        if event.get("type") == "ERROR":
            raise RuntimeError(f"Backend error: {event.get('payload')}")
        if event.get("type") == "OUTCOME_SUMMARY":
            saw_summary = True
        if event.get("type") == "NEGOTIATION_STATE_CHANGED" and (event.get("payload") or {}).get("current_state") == "IDLE":
            saw_idle = True
        if saw_summary and saw_idle:
            return


async def _stream_pcm(
    ws,
    pcm_bytes: bytes,
    *,
    chunk_bytes: int,
    inter_chunk_delay_ms: float | None,
    sample_rate: int = 16000,
) -> None:
    if inter_chunk_delay_ms is None or inter_chunk_delay_ms < 0:
        inter_chunk_delay_ms = (chunk_bytes / 2 / sample_rate) * 1000.0
    for offset in range(0, len(pcm_bytes), chunk_bytes):
        await ws.send(pcm_bytes[offset:offset + chunk_bytes])
        if inter_chunk_delay_ms > 0:
            await asyncio.sleep(inter_chunk_delay_ms / 1000.0)


async def _collect_transcript_for_turn(
    ws,
    events: list[dict[str, Any]],
    *,
    timeout: float,
) -> tuple[list[dict[str, Any]], float | None]:
    deadline = time.monotonic() + timeout
    transcript_events: list[dict[str, Any]] = []
    first_transcript_at: float | None = None
    quiet_deadline: float | None = None

    while time.monotonic() < deadline:
        current_timeout = 0.25
        if quiet_deadline is not None:
            current_timeout = max(0.05, min(current_timeout, quiet_deadline - time.monotonic()))

        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=current_timeout)
        except TimeoutError:
            if quiet_deadline is not None and time.monotonic() >= quiet_deadline:
                break
            continue
        except asyncio.TimeoutError:
            if quiet_deadline is not None and time.monotonic() >= quiet_deadline:
                break
            continue

        event = _decode_event(raw)
        if not event:
            continue
        events.append(event)
        if event.get("type") == "ERROR":
            raise RuntimeError(f"Backend error: {event.get('payload')}")

        if event.get("type") == "TRANSCRIPT_UPDATE":
            payload = event.get("payload") or {}
            speaker = (payload.get("speaker") or "").lower()
            if speaker in {"user", "counterparty", "unknown"}:
                transcript_events.append(event)
                if first_transcript_at is None:
                    first_transcript_at = time.time()
                quiet_deadline = time.monotonic() + 0.8

    return transcript_events, first_transcript_at


def _merge_transcript_events(events: list[dict[str, Any]]) -> tuple[str | None, str, float | None, dict[str, Any]]:
    if not events:
        return None, "", None, {"speaker_set": [], "event_count": 0}

    payloads = [event.get("payload") or {} for event in events]
    speakers = [(payload.get("speaker") or "").lower() for payload in payloads if payload.get("speaker")]
    unique_speakers = sorted(set(speakers))
    merged_text = " ".join(compact_text(payload.get("text") or "") for payload in payloads if compact_text(payload.get("text") or ""))
    confidence_values = [payload.get("speaker_confidence") for payload in payloads if payload.get("speaker_confidence") is not None]
    speaker_confidence = max(confidence_values) if confidence_values else None
    observed_speaker = unique_speakers[0] if len(unique_speakers) == 1 else ("mixed" if unique_speakers else None)
    return observed_speaker, merged_text, speaker_confidence, {
        "speaker_set": unique_speakers,
        "event_count": len(events),
        "payloads": payloads,
    }


def _read_session_log_lines(log_path: Path, session_id: str) -> list[str]:
    if not log_path.exists():
        return []
    try:
        return [
            line.strip()
            for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if session_id in line
        ]
    except Exception:
        return []


def _classify_turn_failure(
    *,
    transcript_events: list[dict[str, Any]],
    stage_markers: list[str],
    session_log_lines: list[str],
    utterance_id: str,
) -> tuple[str | None, str | None]:
    if transcript_events:
        return None, None

    matching_log_lines = [line for line in session_log_lines if utterance_id in line]
    for line in matching_log_lines:
        if "STT transcription failed" in line or "retrying utterance" in line or "recognize() FAILED" in line:
            return "stt_miss", line

    if "UTTERANCE_END" in stage_markers and "UTTERANCE_CLASSIFIED" in stage_markers:
        return "pipeline_timeout", "Utterance reached classification but no transcript event was emitted."
    if "UTTERANCE_END" not in stage_markers:
        return "vad_boundary_miss", "No utterance boundary reached the backend for this fixture."
    return "pipeline_timeout", "Timed out waiting for transcript output."


async def run_scenario(
    *,
    ws_url: str,
    manifest_root: Path,
    scenario: dict[str, Any],
    chunk_bytes: int,
    inter_chunk_delay_ms: float,
    transcript_timeout: float,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    turn_results: list[dict[str, Any]] = []
    session_log_lines: list[str] = []

    async with websockets.connect(
        ws_url,
        max_size=16 * 1024 * 1024,
        open_timeout=60,
        ping_interval=20,
        ping_timeout=90,
        close_timeout=15,
    ) as ws:
        session_id_event = await _wait_for_type(ws, "CONNECTION_ESTABLISHED", events, timeout=15.0)
        session_id = (session_id_event.get("payload") or {}).get("session_id")
        session_log_lines = _read_session_log_lines(DEFAULT_BACKEND_LOG, session_id)

        await _send(ws, "PRIVACY_CONSENT_GRANTED", {"version": "audio-eval-1", "mode": "roleplay"})
        await _wait_for_type(ws, "CONSENT_ACKNOWLEDGED", events, timeout=15.0)

        await _send(ws, "ENROLLMENT_START", {})
        await _wait_for_type(ws, "ENROLLMENT_STARTED", events, timeout=15.0)

        enrollment_pcm, sample_rate = load_wav_pcm(manifest_root / scenario["enrollment_audio_path"])
        if sample_rate != 16000:
            raise RuntimeError(f"Expected 16k enrollment clip, got {sample_rate}")
        await _stream_pcm(
            ws,
            enrollment_pcm,
            chunk_bytes=chunk_bytes,
            inter_chunk_delay_ms=inter_chunk_delay_ms,
            sample_rate=sample_rate,
        )
        await _wait_for_enrollment_complete(ws, events, timeout=20.0)

        await _send(ws, "START_NEGOTIATION", {
            "context": "",
            "audio_eval_only": True,
            "user_context": {"scenario_id": scenario["id"]},
        })
        await _wait_for_type(ws, "SESSION_STARTED", events, timeout=75.0)

        base_started_at = time.time()
        running_offset = 0.0

        for index, turn in enumerate(scenario["turns"], start=1):
            pcm_bytes, sample_rate = load_wav_pcm(manifest_root / turn["audio_path"])
            if sample_rate != 16000:
                raise RuntimeError(f"Expected 16k turn clip, got {sample_rate}")
            duration_ms = pcm_duration_ms(pcm_bytes, sample_rate)
            utterance_id = f"{scenario['id']}__turn_{index}"
            started_at = base_started_at + running_offset
            ended_at = started_at + (duration_ms / 1000.0)
            running_offset += (duration_ms / 1000.0) + 0.35

            await _stream_pcm(
                ws,
                pcm_bytes,
                chunk_bytes=chunk_bytes,
                inter_chunk_delay_ms=inter_chunk_delay_ms,
                sample_rate=sample_rate,
            )

            sent_at = time.time()
            await _send(ws, "UTTERANCE_END", {
                "utterance_id": utterance_id,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_ms": duration_ms,
                "rms": pcm_peak_rms(pcm_bytes),
            })

            transcript_events, first_transcript_at = await _collect_transcript_for_turn(
                ws,
                events,
                timeout=transcript_timeout,
            )

            observed_speaker, observed_text, speaker_confidence, event_meta = _merge_transcript_events(transcript_events)
            debug_lines = parse_speaker_debug_lines(Path(settings.SPEAKER_DEBUG_LOG_PATH), session_id)
            stage_markers = []
            for line in debug_lines:
                if utterance_id in line:
                    parts = [part.strip() for part in line.split("|")]
                    if len(parts) >= 2:
                        stage_markers.append(parts[1])
            session_log_lines = _read_session_log_lines(DEFAULT_BACKEND_LOG, session_id)
            failure_kind, failure_reason = _classify_turn_failure(
                transcript_events=transcript_events,
                stage_markers=stage_markers,
                session_log_lines=session_log_lines,
                utterance_id=utterance_id,
            )

            result = EvaluatedTurn(
                fixture_id=turn["fixture_id"],
                scenario_id=scenario["id"],
                voice_pair_id=scenario["voice_pair_id"],
                condition=scenario["condition"],
                expected_speaker=turn["speaker"],
                observed_speaker=observed_speaker,
                expected_text=turn["text"],
                observed_text=observed_text,
                transcript_count=len(transcript_events),
                latency_ms=(round((first_transcript_at - sent_at) * 1000.0, 2) if first_transcript_at else None),
                timeout=not transcript_events,
                speaker_confidence=speaker_confidence,
                stage_markers=stage_markers,
                failure_kind=failure_kind,
                failure_reason=failure_reason,
                metadata={
                    "duration_ms": duration_ms,
                    "audio_dbfs": rms_dbfs(pcm_bytes),
                    "condition_tags": turn.get("condition_tags", []),
                    "group": turn.get("group"),
                    "session_log_excerpt": [line for line in session_log_lines if utterance_id in line][-5:],
                    **event_meta,
                },
            ).to_dict()
            turn_results.append(result)

        await _send(ws, "END_NEGOTIATION", {"source": "audio_backend_eval", "reason": "scenario_complete"})
        await _wait_for_negotiation_end(ws, events)

    scenario_report = build_report(
        suite_name="audio_backend_eval",
        run_id="pending",
        manifest_id="pending",
        scenarios=[{
            "id": scenario["id"],
            "voice_pair_id": scenario["voice_pair_id"],
            "condition": scenario["condition"],
        }],
        turns=turn_results,
        extra={"session_id": session_id},
    )
    scenario_report["session_id"] = session_id
    scenario_report["events"] = events
    return scenario_report


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run backend audio pipeline evaluation over the real websocket path.")
    parser.add_argument("--ws-url", default="ws://localhost:8000/ws")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--scenario-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--chunk-bytes", type=int, default=3200)
    parser.add_argument(
        "--inter-chunk-delay-ms",
        type=float,
        default=-1.0,
        help="Delay between PCM websocket chunks. Use -1 for real-time pacing based on chunk duration.",
    )
    parser.add_argument("--transcript-timeout", type=float, default=25.0)
    parser.add_argument("--out-dir", default=str(DEFAULT_REPORT_DIR))
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        raise SystemExit(f"Audio manifest not found: {manifest_path}. Run generate_audio_eval_corpus.py first.")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scenarios = manifest.get("scenarios", [])
    if args.scenario_id:
        selected = set(args.scenario_id)
        scenarios = [scenario for scenario in scenarios if scenario["id"] in selected]
    if args.limit > 0:
        scenarios = scenarios[:args.limit]
    if not scenarios:
        raise SystemExit("No audio scenarios selected.")

    run_id = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out_dir) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    scenario_reports = []
    all_turns: list[dict[str, Any]] = []
    for scenario in scenarios:
        print(f"RUN {scenario['id']}")
        report = await run_scenario(
            ws_url=args.ws_url,
            manifest_root=manifest_path.parent,
            scenario=scenario,
            chunk_bytes=args.chunk_bytes,
            inter_chunk_delay_ms=args.inter_chunk_delay_ms,
            transcript_timeout=args.transcript_timeout,
        )
        report["run_id"] = run_id
        report["manifest_id"] = manifest["manifest_id"]
        scenario_reports.append(report)
        all_turns.extend(report["turns"])
        write_json(out_dir / f"{scenario['id']}.json", report)
        print(
            "DONE %s speaker_accuracy=%.3f wer_mean=%s pass=%s"
            % (
                scenario["id"],
                report["summary"]["speaker_accuracy"],
                report["summary"]["wer_mean"],
                report["summary"]["pass"],
            )
        )

    summary = build_report(
        suite_name="audio_backend_eval",
        run_id=run_id,
        manifest_id=manifest["manifest_id"],
        scenarios=[
            {
                "id": scenario["id"],
                "voice_pair_id": scenario["voice_pair_id"],
                "condition": scenario["condition"],
            }
            for scenario in scenarios
        ],
        turns=all_turns,
        extra={"report_count": len(scenario_reports)},
    )
    write_json(out_dir / "summary.json", summary)
    print(f"REPORT {out_dir}")
    return 0 if summary["summary"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
