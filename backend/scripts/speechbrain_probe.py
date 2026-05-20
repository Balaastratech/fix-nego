import argparse
import json
import statistics
import time
from pathlib import Path

from app.config import settings
from app.services.speechbrain_service import speechbrain_service


def _score(reference_embedding, pcm: bytes) -> dict:
    started = time.perf_counter()
    result = speechbrain_service.verify_against_embedding(reference_embedding, pcm)
    return {
        "confidence": result.confidence,
        "accepted": result.accepted,
        "ambiguous": result.ambiguous,
        "strong_reject": result.strong_reject,
        "reason": result.reason,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def _summary(items: list[dict]) -> dict:
    confidences = [item["confidence"] for item in items if item["confidence"] is not None]
    latencies = [item["latency_ms"] for item in items]
    return {
        "count": len(items),
        "confidence_min": min(confidences) if confidences else None,
        "confidence_max": max(confidences) if confidences else None,
        "confidence_mean": round(statistics.mean(confidences), 4) if confidences else None,
        "latency_ms_mean": round(statistics.mean(latencies), 2) if latencies else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark SpeechBrain speaker verification on local audio files.")
    parser.add_argument("--enrollment", required=True, help="Path to the enrollment WAV file.")
    parser.add_argument("--genuine", nargs="+", required=True, help="One or more genuine verification WAV files.")
    parser.add_argument("--impostor", nargs="+", required=True, help="One or more impostor verification WAV files.")
    parser.add_argument("--overlap", nargs="*", default=[], help="Optional overlap/noisy WAV files.")
    args = parser.parse_args()

    ok, reason = speechbrain_service.probe_capability()
    if not ok:
        raise SystemExit(f"SpeechBrain probe failed: {reason}")

    enrollment_path = Path(args.enrollment)
    cold_started = time.perf_counter()
    enrollment_pcm = speechbrain_service.load_audio_file(str(enrollment_path))
    reference_embedding = speechbrain_service.extract_embedding(enrollment_pcm)
    cold_load_ms = round((time.perf_counter() - cold_started) * 1000, 2)

    genuine_results = [
        {"path": path, **_score(reference_embedding, speechbrain_service.load_audio_file(path))}
        for path in args.genuine
    ]
    impostor_results = [
        {"path": path, **_score(reference_embedding, speechbrain_service.load_audio_file(path))}
        for path in args.impostor
    ]
    overlap_results = [
        {"path": path, **_score(reference_embedding, speechbrain_service.load_audio_file(path))}
        for path in args.overlap
    ]

    print(
        json.dumps(
            {
                "speechbrain_device": settings.SPEECHBRAIN_DEVICE,
                "cold_load_ms": cold_load_ms,
                "thresholds": {
                    "accept": settings.SPEECHBRAIN_ACCEPT_THRESHOLD,
                    "recheck": settings.SPEECHBRAIN_RECHECK_THRESHOLD,
                    "ambiguous_low": settings.SPEECHBRAIN_AMBIGUOUS_LOW,
                    "ambiguous_high": settings.SPEECHBRAIN_AMBIGUOUS_HIGH,
                },
                "genuine": {
                    "summary": _summary(genuine_results),
                    "results": genuine_results,
                },
                "impostor": {
                    "summary": _summary(impostor_results),
                    "results": impostor_results,
                },
                "overlap": {
                    "summary": _summary(overlap_results),
                    "results": overlap_results,
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
