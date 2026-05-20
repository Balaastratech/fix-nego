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
        self._google_stt = CapabilityStatus(False, "not_probed", "google_stt")
        self._speechbrain = CapabilityStatus(False, "not_probed", "speechbrain")

    def set_google_stt(self, status: CapabilityStatus) -> None:
        with self._lock:
            self._google_stt = status

    def set_speechbrain(self, status: CapabilityStatus) -> None:
        with self._lock:
            self._speechbrain = status

    def google_stt(self) -> CapabilityStatus:
        with self._lock:
            return CapabilityStatus(**asdict(self._google_stt))

    def speechbrain(self) -> CapabilityStatus:
        with self._lock:
            return CapabilityStatus(**asdict(self._speechbrain))

    def active_path(self) -> str:
        google_ok = self.google_stt().available
        speechbrain_ok = self.speechbrain().available
        if google_ok and speechbrain_ok:
            return "full"
        return "degraded"


capability_registry = CapabilityRegistry()
