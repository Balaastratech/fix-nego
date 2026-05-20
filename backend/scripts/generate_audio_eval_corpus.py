from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.audio_eval_common import write_json  # noqa: E402
from app.services.speaker_enrollment import ENROLLMENT_SCRIPT  # noqa: E402


DEFAULT_OUT_DIR = BACKEND_ROOT / "evals" / "audio_fixtures"
SAMPLE_RATE = 16000

# ---------------------------------------------------------------------------
# pyttsx3 / SAPI5 profiles (Windows TTS — David male, Zira female)
# These produce clearly distinct SpeechBrain embeddings, fixing the "unknown
# dead zone" problem that flite voices hit (0.30–0.55 similarity range).
# ---------------------------------------------------------------------------

PYTTSX3_VOICE_PROFILES = {
    "david_base": {"sapi_name": "David", "rate_delta": 0},
    "david_slow": {"sapi_name": "David", "rate_delta": -30},
    "david_fast": {"sapi_name": "David", "rate_delta": +30},
    "zira_base":  {"sapi_name": "Zira",  "rate_delta": 0},
    "zira_slow":  {"sapi_name": "Zira",  "rate_delta": -20},
}

PYTTSX3_VOICE_PAIRS = [
    {"id": "pair_01", "user_profile": "david_base", "counterparty_profile": "zira_base"},
    {"id": "pair_02", "user_profile": "david_slow", "counterparty_profile": "zira_base"},
    {"id": "pair_03", "user_profile": "david_base", "counterparty_profile": "zira_slow"},
    {"id": "pair_04", "user_profile": "david_fast", "counterparty_profile": "zira_base"},
]


def _find_sapi5_voice(engine: Any, name_fragment: str) -> str | None:
    """Return the first SAPI5 voice ID whose name contains *name_fragment* (case-insensitive)."""
    for voice in engine.getProperty("voices"):
        if name_fragment.lower() in voice.name.lower():
            return voice.id
    return None


def synthesize_pyttsx3_wav(text: str, sapi_name: str, out_path: Path, rate_delta: int = 0) -> None:
    """Synthesize *text* using pyttsx3 SAPI5 voice, save 16kHz mono WAV to *out_path*."""
    import pyttsx3
    import torchaudio
    import torch

    engine = pyttsx3.init()
    voice_id = _find_sapi5_voice(engine, sapi_name)
    if voice_id is None:
        voices = engine.getProperty("voices")
        available = [v.name for v in voices]
        raise RuntimeError(
            f"SAPI5 voice containing '{sapi_name}' not found. "
            f"Available voices: {available}"
        )

    engine.setProperty("voice", voice_id)
    base_rate = int(engine.getProperty("rate"))
    engine.setProperty("rate", max(50, base_rate + rate_delta))

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        engine.save_to_file(text, str(tmp_path))
        engine.runAndWait()

        waveform, sr = torchaudio.load(str(tmp_path))
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)
        if sr != SAMPLE_RATE:
            waveform = torchaudio.functional.resample(waveform, sr, SAMPLE_RATE)
        waveform = waveform.clamp(-1.0, 1.0)
        pcm_int16 = (waveform.squeeze(0) * 32767.0).to(torch.int16).numpy()
        sf.write(str(out_path), pcm_int16, SAMPLE_RATE, subtype="PCM_16")
    finally:
        tmp_path.unlink(missing_ok=True)


def build_pyttsx3_profile_audio(text: str, profile_id: str, cache_dir: Path) -> Path:
    profile = PYTTSX3_VOICE_PROFILES[profile_id]
    key = hashlib.sha256(f"pyttsx3::{profile_id}::{text}".encode()).hexdigest()[:16]
    cooked_path = cache_dir / f"{key}.wav"
    if not cooked_path.exists():
        synthesize_pyttsx3_wav(
            text,
            sapi_name=profile["sapi_name"],
            out_path=cooked_path,
            rate_delta=profile["rate_delta"],
        )
    return cooked_path


VOICE_PROFILES = {
    "kal_base": {"voice": "kal", "ffmpeg_filter": None},
    "kal_low": {"voice": "kal", "ffmpeg_filter": "asetrate=14500,aresample=16000,atempo=1.05"},
    "kal_bright": {"voice": "kal", "ffmpeg_filter": "asetrate=17200,aresample=16000,atempo=0.98"},
    "slt_base": {"voice": "slt", "ffmpeg_filter": None},
    "slt_low": {"voice": "slt", "ffmpeg_filter": "asetrate=15000,aresample=16000,atempo=1.04"},
    "awb_slow": {"voice": "awb", "ffmpeg_filter": "atempo=0.92"},
    "rms_base": {"voice": "rms", "ffmpeg_filter": None},
}


VOICE_PAIRS = [
    {"id": "pair_01", "user_profile": "kal_base", "counterparty_profile": "slt_base"},
    {"id": "pair_02", "user_profile": "kal_low", "counterparty_profile": "slt_base"},
    {"id": "pair_03", "user_profile": "kal_base", "counterparty_profile": "slt_low"},
    {"id": "pair_04", "user_profile": "slt_base", "counterparty_profile": "rms_base"},
    {"id": "pair_05", "user_profile": "awb_slow", "counterparty_profile": "kal_bright"},
]


CONDITIONS = {
    "clean": {"tags": ["clean"], "tempo": 1.0, "noise": 0.0, "reverb": False},
    "noisy": {"tags": ["noisy", "light_room_noise"], "tempo": 1.0, "noise": 0.014, "reverb": False},
    "reverb": {"tags": ["reverb"], "tempo": 1.0, "noise": 0.0, "reverb": True},
    "fast": {"tags": ["fast_speech"], "tempo": 1.08, "noise": 0.0, "reverb": False},
}


SCENARIO_TEMPLATES = [
    {
        "id": "pricing_numbers",
        "group": "number_heavy",
        "default_condition": "clean",
        "turns": [
            # Numbers as digits: SAPI5 pronounces "82" as "eighty two", Chirp 3 returns "82" → match
            {"speaker": "user", "text": "I can do 82 only with net 60 and no auto renewal."},
            {"speaker": "counterparty", "text": "At 84 we can keep delivery and warranty included."},
            {"speaker": "user", "text": "84 is still high for 50 units."},
            {"speaker": "counterparty", "text": "Then I can review 61 if replacement terms stay standard."},
        ],
    },
    {
        "id": "salary_package",
        "group": "compensation",
        "default_condition": "clean",
        "turns": [
            {"speaker": "user", "text": "If base cannot reach 195, I need stronger sign on and equity."},
            {"speaker": "counterparty", "text": "Sign on above 25 needs approval, but equity has more flexibility."},
            {"speaker": "user", "text": "Then I need 35 sign on and 80 equity to make that work."},
            {"speaker": "counterparty", "text": "I can review that package if the base stays fixed."},
        ],
    },
    {
        "id": "rapid_switch",
        "group": "rapid_switch",
        "default_condition": "fast",
        "turns": [
            {"speaker": "user", "text": "Can you do 82?"},
            {"speaker": "counterparty", "text": "No."},
            {"speaker": "user", "text": "83 with delivery?"},
            {"speaker": "counterparty", "text": "Maybe."},
            {"speaker": "user", "text": "Then confirm net 60."},
            {"speaker": "counterparty", "text": "Net 45 only."},
        ],
    },
    {
        "id": "short_turns",
        "group": "short_turns",
        "default_condition": "clean",
        "turns": [
            {"speaker": "user", "text": "Yes."},
            {"speaker": "counterparty", "text": "No."},
            {"speaker": "user", "text": "82 only."},
            # "Net sixty no." caused "net 16 0" via Zira. Digit form fixes pronunciation.
            {"speaker": "counterparty", "text": "Net 60, no."},
        ],
    },
    {
        "id": "payment_terms",
        "group": "payment_terms",
        "default_condition": "noisy",
        "turns": [
            {"speaker": "user", "text": "I can accept 61 only if warranty delivery and replacement are clear."},
            {"speaker": "counterparty", "text": "61 works, but premium replacement coverage would move separately."},
            {"speaker": "user", "text": "Then spell out the standard replacement window in writing today."},
            {"speaker": "counterparty", "text": "I can send standard replacement and delivery terms this afternoon."},
        ],
    },
    {
        "id": "lease_reverb",
        "group": "reverb_numbers",
        "default_condition": "reverb",
        "turns": [
            {"speaker": "user", "text": "160 with 3 months rent free is my target."},
            {"speaker": "counterparty", "text": "170 with 2 months rent free is the closest path today."},
            {"speaker": "user", "text": "Then I need fit out support if 160 is off the table."},
            {"speaker": "counterparty", "text": "Fit out support is possible, but the lock in stays at 3 years."},
        ],
    },
]


def synthesize_flite_wav(text: str, voice_name: str, out_path: Path) -> None:
    escaped_text = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"flite=text='{escaped_text}':voice={voice_name}",
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        "1",
        str(out_path),
    ]
    subprocess.run(command, check=True, capture_output=True)


def run_ffmpeg(input_path: Path, output_path: Path, *, audio_filter: str | None = None) -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(input_path)]
    if audio_filter:
        cmd.extend(["-af", audio_filter])
    cmd.extend(["-ar", str(SAMPLE_RATE), "-ac", "1", str(output_path)])
    subprocess.run(cmd, check=True, capture_output=True)


def apply_noise(input_path: Path, output_path: Path, amount: float) -> None:
    audio, sr = sf.read(str(input_path), dtype="float32")
    rng = np.random.default_rng(seed=_stable_seed(str(input_path)))
    noise = rng.normal(0.0, amount, size=audio.shape).astype(np.float32)
    mixed = np.clip(audio + noise, -0.95, 0.95)
    sf.write(str(output_path), mixed, sr, subtype="PCM_16")


def build_profile_audio(text: str, profile_id: str, cache_dir: Path) -> Path:
    profile = VOICE_PROFILES[profile_id]
    key = hashlib.sha256(f"{profile_id}::{text}".encode("utf-8")).hexdigest()[:16]
    raw_path = cache_dir / f"{key}.raw.wav"
    cooked_path = cache_dir / f"{key}.wav"

    if not raw_path.exists():
        synthesize_flite_wav(text, profile["voice"], raw_path)
    if not cooked_path.exists():
        run_ffmpeg(raw_path, cooked_path, audio_filter=profile["ffmpeg_filter"])
    return cooked_path


def apply_condition(base_path: Path, output_path: Path, condition_id: str) -> None:
    condition = CONDITIONS[condition_id]
    working = base_path

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)

        if condition["tempo"] != 1.0:
            tempo_path = temp_root / "tempo.wav"
            run_ffmpeg(working, tempo_path, audio_filter=f"atempo={condition['tempo']}")
            working = tempo_path

        if condition["reverb"]:
            reverb_path = temp_root / "reverb.wav"
            run_ffmpeg(working, reverb_path, audio_filter="aecho=0.8:0.7:45:0.25")
            working = reverb_path

        if condition["noise"] > 0.0:
            noisy_path = temp_root / "noisy.wav"
            apply_noise(working, noisy_path, float(condition["noise"]))
            working = noisy_path

        shutil.copyfile(working, output_path)


def _stable_seed(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:16], 16)


def generate_corpus_pyttsx3(out_dir: Path) -> dict[str, Any]:
    """Generate corpus using pyttsx3 SAPI5 voices (Windows-native, distinct embeddings)."""
    fixtures_dir = out_dir / "wav"
    cache_dir = out_dir / ".cache_pyttsx3"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    scenarios: list[dict[str, Any]] = []
    utterance_count = 0

    for pair in PYTTSX3_VOICE_PAIRS:
        enrollment_base = build_pyttsx3_profile_audio(ENROLLMENT_SCRIPT, pair["user_profile"], cache_dir)
        enrollment_path = fixtures_dir / pair["id"] / "enrollment.wav"
        enrollment_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(enrollment_base, enrollment_path)

        for template in SCENARIO_TEMPLATES:
            condition_id = "clean"  # pyttsx3 always produces clean audio; conditions applied after
            scenario_id = f"{template['id']}__{pair['id']}__{condition_id}"
            turns: list[dict[str, Any]] = []

            for index, turn in enumerate(template["turns"], start=1):
                profile_id = pair["user_profile"] if turn["speaker"] == "user" else pair["counterparty_profile"]
                base_audio = build_pyttsx3_profile_audio(turn["text"], profile_id, cache_dir)
                fixture_path = fixtures_dir / pair["id"] / condition_id / f"{template['id']}__turn_{index}.wav"
                fixture_path.parent.mkdir(parents=True, exist_ok=True)
                apply_condition(base_audio, fixture_path, condition_id)
                utterance_count += 1
                turns.append({
                    "fixture_id": f"{scenario_id}__turn_{index}",
                    "speaker": turn["speaker"],
                    "text": turn["text"],
                    "audio_path": str(fixture_path.relative_to(out_dir)).replace("\\", "/"),
                    "condition_tags": CONDITIONS[condition_id]["tags"],
                    "group": template["group"],
                })

            scenarios.append({
                "id": scenario_id,
                "voice_pair_id": pair["id"],
                "user_profile": pair["user_profile"],
                "counterparty_profile": pair["counterparty_profile"],
                "condition": condition_id,
                "condition_tags": CONDITIONS[condition_id]["tags"],
                "group": template["group"],
                "enrollment_audio_path": str(enrollment_path.relative_to(out_dir)).replace("\\", "/"),
                "turns": turns,
            })

    manifest = {
        "version": 1,
        "manifest_id": "audio_eval_manifest_pyttsx3_v1",
        "sample_rate": SAMPLE_RATE,
        "tts_backend": "pyttsx3",
        "voice_profiles": PYTTSX3_VOICE_PROFILES,
        "voice_pairs": PYTTSX3_VOICE_PAIRS,
        "conditions": CONDITIONS,
        "scenario_templates": [
            {"id": t["id"], "group": t["group"], "default_condition": t["default_condition"]}
            for t in SCENARIO_TEMPLATES
        ],
        "scenario_count": len(scenarios),
        "utterance_count": utterance_count,
        "scenarios": scenarios,
    }
    write_json(out_dir / "manifest.json", manifest)
    return manifest


def generate_corpus(out_dir: Path) -> dict[str, Any]:
    fixtures_dir = out_dir / "wav"
    cache_dir = out_dir / ".cache"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    scenarios: list[dict[str, Any]] = []
    utterance_count = 0

    for pair in VOICE_PAIRS:
        enrollment_base = build_profile_audio(ENROLLMENT_SCRIPT, pair["user_profile"], cache_dir)
        enrollment_path = fixtures_dir / pair["id"] / "enrollment.wav"
        enrollment_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(enrollment_base, enrollment_path)

        for template in SCENARIO_TEMPLATES:
            condition_id = template["default_condition"]
            scenario_id = f"{template['id']}__{pair['id']}__{condition_id}"
            turns: list[dict[str, Any]] = []

            for index, turn in enumerate(template["turns"], start=1):
                profile_id = pair["user_profile"] if turn["speaker"] == "user" else pair["counterparty_profile"]
                base_audio = build_profile_audio(turn["text"], profile_id, cache_dir)
                fixture_path = fixtures_dir / pair["id"] / condition_id / f"{template['id']}__turn_{index}.wav"
                fixture_path.parent.mkdir(parents=True, exist_ok=True)
                apply_condition(base_audio, fixture_path, condition_id)
                utterance_count += 1
                turns.append(
                    {
                        "fixture_id": f"{scenario_id}__turn_{index}",
                        "speaker": turn["speaker"],
                        "text": turn["text"],
                        "audio_path": str(fixture_path.relative_to(out_dir)).replace("\\", "/"),
                        "condition_tags": CONDITIONS[condition_id]["tags"],
                        "group": template["group"],
                    }
                )

            scenarios.append(
                {
                    "id": scenario_id,
                    "voice_pair_id": pair["id"],
                    "user_profile": pair["user_profile"],
                    "counterparty_profile": pair["counterparty_profile"],
                    "condition": condition_id,
                    "condition_tags": CONDITIONS[condition_id]["tags"],
                    "group": template["group"],
                    "enrollment_audio_path": str(enrollment_path.relative_to(out_dir)).replace("\\", "/"),
                    "turns": turns,
                }
            )

    manifest = {
        "version": 1,
        "manifest_id": "audio_eval_manifest_v1",
        "sample_rate": SAMPLE_RATE,
        "voice_profiles": VOICE_PROFILES,
        "voice_pairs": VOICE_PAIRS,
        "conditions": CONDITIONS,
        "scenario_templates": [
            {"id": template["id"], "group": template["group"], "default_condition": template["default_condition"]}
            for template in SCENARIO_TEMPLATES
        ],
        "scenario_count": len(scenarios),
        "utterance_count": utterance_count,
        "scenarios": scenarios,
    }
    write_json(out_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic audio fixtures for audio pipeline evals.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument(
        "--tts-backend",
        choices=["flite", "pyttsx3"],
        default="flite",
        help="TTS engine to use. 'flite' requires ffmpeg with flite filter. "
             "'pyttsx3' uses Windows SAPI5 (David/Zira) — produces distinct embeddings.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    if args.tts_backend == "pyttsx3":
        try:
            import pyttsx3  # noqa: F401
        except ImportError:
            print("ERROR: pyttsx3 not installed. Run: pip install pyttsx3", file=sys.stderr)
            return 1
        manifest = generate_corpus_pyttsx3(out_dir)
    else:
        manifest = generate_corpus(out_dir)

    print(json.dumps({
        "out_dir": str(out_dir),
        "manifest": str(out_dir / "manifest.json"),
        "tts_backend": args.tts_backend,
        "scenario_count": manifest["scenario_count"],
        "utterance_count": manifest["utterance_count"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
