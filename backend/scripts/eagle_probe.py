"""
Standalone Picovoice Eagle proof harness.

Usage:
  python scripts/eagle_probe.py enrollment.pcm genuine.pcm impostor.pcm
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.services.eagle_service import eagle_service


def main() -> int:
    if len(sys.argv) != 4:
        print("Usage: python scripts/eagle_probe.py enrollment.pcm genuine.pcm impostor.pcm")
        return 1

    enrollment_path = Path(sys.argv[1])
    genuine_path = Path(sys.argv[2])
    impostor_path = Path(sys.argv[3])

    profiler = eagle_service.create_profiler()
    try:
        enrollment_audio = enrollment_path.read_bytes()
        progress = eagle_service.enroll(profiler, enrollment_audio)
        print(f"Enrollment progress: {progress}")
        if float(progress.get('percentage') or 0.0) < 100.0:
            print("Profile is not complete yet. Provide a longer enrollment sample.")
            return 2

        profile_bytes = eagle_service.export_profile(profiler)
    finally:
        eagle_service.release_profiler(profiler)

    recognizer = eagle_service.create_recognizer([profile_bytes])
    try:
        genuine = eagle_service.verify_profile(recognizer, genuine_path.read_bytes())
        impostor = eagle_service.verify_profile(recognizer, impostor_path.read_bytes())
        print("Genuine result:", genuine)
        print("Impostor result:", impostor)
    finally:
        eagle_service.release_recognizer(recognizer)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
