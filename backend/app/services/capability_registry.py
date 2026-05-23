from __future__ import annotations

import threading
from dataclasses import dataclass, asdict

from app.config import settings


@dataclass
class CapabilityStatus:
    available: bool
    reason: str = ""
    provider: str = ""
    region: str = ""


class CapabilityRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stt = CapabilityStatus(False, "not_probed", settings.TRANSCRIPTION_PROVIDER)
        self._speechbrain = CapabilityStatus(False, "not_probed", "speechbrain")

    def set_stt(self, status: CapabilityStatus) -> None:
        with self._lock:
            self._stt = status

    def stt(self) -> CapabilityStatus:
        with self._lock:
            return CapabilityStatus(**asdict(self._stt))

    def set_google_stt(self, status: CapabilityStatus) -> None:
        self.set_stt(status)

    def set_speechbrain(self, status: CapabilityStatus) -> None:
        with self._lock:
            self._speechbrain = status

    def google_stt(self) -> CapabilityStatus:
        return self.stt()

    def speechbrain(self) -> CapabilityStatus:
        with self._lock:
            return CapabilityStatus(**asdict(self._speechbrain))

    def active_path(self) -> str:
        stt_ok = self.stt().available
        speechbrain_ok = self.speechbrain().available
        if stt_ok and speechbrain_ok:
            return "full"
        return "degraded"


capability_registry = CapabilityRegistry()
