from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FinalizedUtterance:
    utterance_id: str
    audio: bytes
    started_at: float
    ended_at: float
    duration_ms: int
    rms: float
    source: str = "stt"
    transcript_text: str = ""
    transcription_confidence: float | None = None
    speaker: str = "unknown"
    speaker_confidence: float | None = None
    eligible_for_display: bool = False
    eligible_for_context: bool = False
    eligible_for_research: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CounterpartyCandidate:
    embedding: Any
    timestamp: float
    utterance_id: str
