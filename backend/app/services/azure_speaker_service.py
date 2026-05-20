from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AzureVerificationResult:
    accepted: bool
    confidence: float | None
    profile_id: str | None
    reason: str
    provider: str = "azure"


class AzureSpeakerVerificationService:
    def __init__(self) -> None:
        self._ssl_context = ssl.create_default_context()

    @property
    def enabled(self) -> bool:
        return bool(
            settings.AZURE_SPEAKER_VERIFICATION_ENABLED
            and settings.AZURE_SPEAKER_SUBSCRIPTION_KEY
            and settings.AZURE_SPEAKER_REGION
        )

    def build_endpoint(self) -> str:
        return f"https://{settings.AZURE_SPEAKER_REGION}.api.cognitive.microsoft.com"

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: bytes | None = None,
        content_type: str = "application/json",
    ) -> tuple[int, dict[str, Any] | None, str]:
        if not self.enabled:
            raise RuntimeError("Azure speaker verification is not configured")

        query_string = urllib.parse.urlencode(query or {})
        url = f"{self.build_endpoint()}{path}"
        if query_string:
            url = f"{url}?{query_string}"

        request = urllib.request.Request(
            url=url,
            data=body,
            method=method,
            headers={
                "Ocp-Apim-Subscription-Key": settings.AZURE_SPEAKER_SUBSCRIPTION_KEY,
                "Content-Type": content_type,
            },
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=settings.AZURE_SPEAKER_TIMEOUT_SECONDS,
                context=self._ssl_context,
            ) as response:
                raw = response.read().decode("utf-8") if response.length != 0 else ""
                parsed = json.loads(raw) if raw else None
                return response.status, parsed, raw
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            parsed = None
            try:
                parsed = json.loads(raw) if raw else None
            except Exception:
                parsed = None
            return exc.code, parsed, raw

    def probe_capability(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "azure_credentials_missing"

        status, parsed, raw = self._request(
            "GET",
            "/speaker-recognition/verification/text-independent/profiles",
            query={"api-version": settings.AZURE_SPEAKER_API_VERSION},
        )
        if 200 <= status < 300:
            return True, "ok"
        detail = parsed or raw or f"http_{status}"
        return False, f"probe_failed:{detail}"

    def create_profile(self) -> str:
        status, parsed, raw = self._request(
            "POST",
            "/speaker-recognition/verification/text-independent/profiles",
            query={"api-version": settings.AZURE_SPEAKER_API_VERSION},
            body=json.dumps({"locale": "en-US"}).encode("utf-8"),
        )
        if not (200 <= status < 300) or not parsed:
            raise RuntimeError(f"Azure profile creation failed: {parsed or raw or status}")
        profile_id = parsed.get("profileId") or parsed.get("profile_id")
        if not profile_id:
            raise RuntimeError(f"Azure profile creation missing profile id: {parsed}")
        return str(profile_id)

    def enroll_profile(self, profile_id: str, wav_audio: bytes, *, ignore_min_length: bool = False) -> dict[str, Any]:
        query = {"api-version": settings.AZURE_SPEAKER_API_VERSION}
        if ignore_min_length:
            query["ignoreMinLength"] = "true"
        status, parsed, raw = self._request(
            "POST",
            f"/speaker-recognition/verification/text-independent/profiles/{profile_id}:enroll",
            query=query,
            body=wav_audio,
            content_type="audio/wav",
        )
        if not (200 <= status < 300) or not parsed:
            raise RuntimeError(f"Azure enrollment failed: {parsed or raw or status}")
        return parsed

    def verify_profile(self, profile_id: str, wav_audio: bytes) -> AzureVerificationResult:
        status, parsed, raw = self._request(
            "POST",
            f"/speaker-recognition/verification/text-independent/profiles/{profile_id}:verify",
            query={"api-version": settings.AZURE_SPEAKER_API_VERSION},
            body=wav_audio,
            content_type="audio/wav",
        )
        if not (200 <= status < 300) or not parsed:
            return AzureVerificationResult(
                accepted=False,
                confidence=None,
                profile_id=profile_id,
                reason=f"verify_failed:{parsed or raw or status}",
            )

        result = str(parsed.get("result") or "").lower()
        confidence = parsed.get("confidence")
        accepted = result in {"accept", "accepted"} or bool(parsed.get("accepted"))
        try:
            normalized_confidence = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            normalized_confidence = None

        return AzureVerificationResult(
            accepted=accepted,
            confidence=normalized_confidence,
            profile_id=profile_id,
            reason=result or "ok",
        )


azure_speaker_verification_service = AzureSpeakerVerificationService()
