from __future__ import annotations

import logging
import time
from typing import Any

from app.config import settings
from app.models.negotiation import NegotiationSession
from app.services.capability_registry import capability_registry
from app.services.speechbrain_service import speechbrain_service
from app.services.session_store import session_store
from app.utils.speaker_debug import log_speaker_debug

logger = logging.getLogger(__name__)


class SpeakerMappingService:
    def __init__(self, session: NegotiationSession) -> None:
        self.session = session

    def begin_calibration(self) -> None:
        if self.session.speaker_mapping_state == "unmapped":
            self._transition("calibrating")

    def _transition(self, state: str) -> None:
        now = time.time()
        if self.session.speaker_mapping_state != state:
            event = {"from": self.session.speaker_mapping_state, "to": state, "timestamp": now}
            self.session.mapping_state_transitions.append(event)
            session_store.record_speaker_mapping_event(self.session.session_id, event)
        self.session.speaker_mapping_state = state

    async def label_diarized_turns(self, turns: list[dict[str, Any]], utterance_audio: bytes) -> list[dict[str, Any]]:
        self.begin_calibration()
        enriched_turns = self._attach_turn_audio(turns, utterance_audio)
        self._mark_third_speakers(enriched_turns)
        log_speaker_debug(
            "MAPPING_START",
            session_id=self.session.session_id,
            mapping_state=self.session.speaker_mapping_state,
            known_mapping=self.session.speaker_mapping,
            permanent_unknown_ids=sorted(self.session.permanent_unknown_speaker_ids),
            turns=[
                {
                    "speaker_id": str(turn.get("diarized_speaker_id", "unknown")),
                    "duration": round(self._turn_duration(turn), 3),
                    "text": turn.get("text"),
                }
                for turn in enriched_turns
            ],
        )

        labeled_turns: list[dict[str, Any]] = []
        for turn in enriched_turns:
            diarized_id = str(turn.get("diarized_speaker_id", "unknown"))
            turn_duration = self._turn_duration(turn)
            is_ephemeral = self._is_ephemeral_diarized_id(diarized_id)
            if not is_ephemeral:
                self._remember_turn(diarized_id, turn_duration)

            if diarized_id in self.session.permanent_unknown_speaker_ids:
                speaker = "unknown"
            elif self.session.speaker_mapping_state == "degraded":
                speaker = await self._handle_degraded_mapping(diarized_id, turn, is_ephemeral=is_ephemeral)
            else:
                speaker = await self._label_non_degraded_turn(diarized_id, turn, is_ephemeral=is_ephemeral)

            labeled_turn = dict(turn)
            labeled_turn["speaker"] = speaker
            log_speaker_debug(
                "MAPPING_DECISION",
                session_id=self.session.session_id,
                diarized_id=diarized_id,
                decided_speaker=speaker,
                turn_duration=round(turn_duration, 3),
                mapping_state=self.session.speaker_mapping_state,
                known_mapping=self.session.speaker_mapping,
                speechbrain_last_result=self.session.speechbrain_last_result,
                text=turn.get("text"),
            )
            labeled_turns.append(labeled_turn)

        return labeled_turns

    async def _label_non_degraded_turn(self, diarized_id: str, turn: dict[str, Any], *, is_ephemeral: bool) -> str:
        mapped_role = self.session.speaker_mapping.get(diarized_id)
        turn_duration = self._turn_duration(turn)
        if is_ephemeral:
            return await self._classify_ephemeral_turn(turn)
        if mapped_role == "user":
            return await self._recheck_user_mapping(diarized_id, turn)
        if mapped_role == "counterparty":
            return "counterparty"

        if self._mapped_id("user") is None:
            if turn_duration >= settings.SPEECHBRAIN_MIN_BIND_SECONDS:
                return await self._attempt_user_binding(diarized_id, turn)
            return "unknown"

        if self._is_stable_counterparty_candidate(diarized_id):
            existing_counterparty = self._mapped_id("counterparty")
            if existing_counterparty and existing_counterparty != diarized_id:
                self.session.permanent_unknown_speaker_ids.add(diarized_id)
                return "unknown"
            self.session.speaker_mapping[diarized_id] = "counterparty"
            self._transition("mapped")
            return "counterparty"

        return "unknown"

    async def _handle_degraded_mapping(self, diarized_id: str, turn: dict[str, Any], *, is_ephemeral: bool) -> str:
        if is_ephemeral:
            return await self._classify_ephemeral_turn(turn)
        mapped_role = self.session.speaker_mapping.get(diarized_id)
        if mapped_role != "user":
            return "unknown"

        decision = await self._verify_user_candidate(turn, threshold=settings.SPEECHBRAIN_RECHECK_THRESHOLD)
        if decision["accepted"]:
            self.session.mapping_contradictions[diarized_id] = []
            self.session.speaker_mapping_last_validated_at = time.time()
            self._transition("mapped")
            return "user"
        return "unknown"

    async def _attempt_user_binding(self, diarized_id: str, turn: dict[str, Any]) -> str:
        decision = await self._verify_user_candidate(turn, threshold=settings.SPEECHBRAIN_ACCEPT_THRESHOLD)
        if decision["accepted"]:
            current_user_id = self._mapped_id("user")
            if current_user_id and current_user_id != diarized_id:
                self.session.speaker_mapping.pop(current_user_id, None)

            self.session.speaker_mapping[diarized_id] = "user"
            self.session.speaker_mapping_confidence = decision.get("confidence")
            self.session.speaker_mapping_locked_at = time.time()
            self.session.speaker_mapping_last_validated_at = time.time()
            self._transition("mapped")
            return "user"

        self._transition("calibrating")
        return "unknown"

    async def _classify_ephemeral_turn(self, turn: dict[str, Any]) -> str:
        threshold = (
            settings.SPEECHBRAIN_ACCEPT_THRESHOLD
            if self._mapped_id("user") is None
            else settings.SPEECHBRAIN_RECHECK_THRESHOLD
        )
        decision = await self._verify_user_candidate(turn, threshold=threshold)
        if decision["accepted"]:
            return "user"
        if decision.get("ambiguous"):
            return "unknown"
        if decision.get("strong_reject"):
            return "counterparty"
        return "unknown"

    async def _recheck_user_mapping(self, diarized_id: str, turn: dict[str, Any]) -> str:
        turn_duration = self._turn_duration(turn)
        if turn_duration < settings.SPEECHBRAIN_MIN_BIND_SECONDS:
            return "user"

        decision = await self._verify_user_candidate(turn, threshold=settings.SPEECHBRAIN_RECHECK_THRESHOLD)
        if decision["accepted"]:
            self.session.mapping_contradictions[diarized_id] = []
            self.session.speaker_mapping_last_validated_at = time.time()
            return "user"

        if decision.get("ambiguous"):
            return "unknown"

        if decision.get("strong_reject"):
            evidence = decision.get("confidence")
            if evidence is not None:
                self.record_contradiction(diarized_id, evidence)
            return "unknown"

        return "unknown"

    async def _verify_user_candidate(self, turn: dict[str, Any], *, threshold: float) -> dict[str, Any]:
        now = time.time()
        turn_duration = self._turn_duration(turn)
        turn_audio = turn.get("turn_audio") or b""

        self.session.speechbrain_verification_attempts += 1
        self.session.session_metrics["speechbrain_verification_calls"] += 1

        speechbrain_available = capability_registry.speechbrain().available
        if (
            speechbrain_available
            and self.session.speechbrain_reference_embedding is not None
            and turn_duration >= settings.SPEECHBRAIN_MIN_BIND_SECONDS
            and turn_audio
        ):
            result = speechbrain_service.verify_against_embedding(self.session.speechbrain_reference_embedding, turn_audio)
            self.session.speechbrain_last_result = {
                "accepted": result.accepted,
                "confidence": result.confidence,
                "reason": result.reason,
                "provider": result.provider,
                "ambiguous": result.ambiguous,
                "strong_reject": result.strong_reject,
                "timestamp": now,
            }

            if result.ambiguous:
                self.session.session_metrics["speechbrain_ambiguous_turns"] += 1
                return {
                    "accepted": False,
                    "confidence": result.confidence,
                    "provider": result.provider,
                    "ambiguous": True,
                    "strong_reject": False,
                }

            accepted = (result.confidence or 0.0) >= threshold
            if accepted:
                self.session.speechbrain_verification_successes += 1
            else:
                self.session.speechbrain_verification_failures += 1
            log_speaker_debug(
                "SPEECHBRAIN_VERIFY",
                session_id=self.session.session_id,
                threshold=threshold,
                accepted=accepted,
                confidence=result.confidence,
                ambiguous=result.ambiguous,
                strong_reject=result.strong_reject,
                provider=result.provider,
                reason=result.reason,
                turn_duration=round(turn_duration, 3),
                audio_bytes=len(turn_audio),
                text=turn.get("text"),
            )
            return {
                "accepted": accepted,
                "confidence": result.confidence,
                "provider": result.provider,
                "ambiguous": False,
                "strong_reject": result.strong_reject,
            }

        self.session.speechbrain_verification_failures += 1
        log_speaker_debug(
            "SPEECHBRAIN_VERIFY_SKIPPED",
            session_id=self.session.session_id,
            threshold=threshold,
            speechbrain_available=speechbrain_available,
            has_reference=self.session.speechbrain_reference_embedding is not None,
            turn_duration=round(turn_duration, 3),
            min_bind_seconds=settings.SPEECHBRAIN_MIN_BIND_SECONDS,
            audio_bytes=len(turn_audio),
            text=turn.get("text"),
        )
        return {
            "accepted": False,
            "confidence": None,
            "provider": "none",
            "ambiguous": False,
            "strong_reject": False,
        }

    def _attach_turn_audio(self, turns: list[dict[str, Any]], utterance_audio: bytes) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        bytes_per_second = 16000 * 2
        utterance_length = len(utterance_audio)
        for turn in turns:
            start_time = max(0.0, float(turn.get("start_time", 0.0) or 0.0))
            end_time = max(start_time, float(turn.get("end_time", 0.0) or 0.0))
            start_index = min(utterance_length, int(start_time * bytes_per_second))
            end_index = min(utterance_length, int(end_time * bytes_per_second))
            turn_audio = utterance_audio[start_index:end_index]
            enriched_turn = dict(turn)
            enriched_turn["turn_audio"] = turn_audio
            enriched.append(enriched_turn)
        return enriched

    def _mark_third_speakers(self, turns: list[dict[str, Any]]) -> None:
        known_ids = {str(key) for key in self.session.speaker_mapping.keys()}
        observed_ids = {
            str(turn.get("diarized_speaker_id"))
            for turn in turns
            if turn.get("diarized_speaker_id") is not None
            and not self._is_ephemeral_diarized_id(str(turn.get("diarized_speaker_id")))
        }
        candidate_ids = sorted((known_ids | observed_ids) - self.session.permanent_unknown_speaker_ids)
        allowed_ids = set(sorted(known_ids)[:2])
        for diarized_id in candidate_ids:
            if diarized_id not in allowed_ids and len(allowed_ids) >= 2:
                self.session.permanent_unknown_speaker_ids.add(diarized_id)
            elif len(allowed_ids) < 2:
                allowed_ids.add(diarized_id)

    def _remember_turn(self, diarized_id: str, turn_duration: float) -> None:
        cache = self.session.speaker_embedding_cache.setdefault(
            diarized_id,
            {"seen": 0, "total_duration": 0.0, "last_seen_at": 0.0},
        )
        cache["seen"] += 1
        cache["total_duration"] += turn_duration
        cache["last_seen_at"] = time.time()

    def _is_stable_counterparty_candidate(self, diarized_id: str) -> bool:
        cache = self.session.speaker_embedding_cache.get(diarized_id, {})
        return (
            diarized_id not in self.session.permanent_unknown_speaker_ids
            and (
                float(cache.get("total_duration", 0.0)) >= settings.SPEECHBRAIN_MIN_BIND_SECONDS
                or int(cache.get("seen", 0)) >= 2
            )
        )

    def _mapped_id(self, role: str) -> str | None:
        for diarized_id, mapped_role in self.session.speaker_mapping.items():
            if mapped_role == role:
                return diarized_id
        return None

    @staticmethod
    def _is_ephemeral_diarized_id(diarized_id: str) -> bool:
        normalized = (diarized_id or "").strip().casefold()
        return normalized in {"", "unknown", "user", "counterparty", "none", "null"}

    def _turn_duration(self, turn: dict[str, Any]) -> float:
        return max(0.0, float(turn.get("end_time", 0.0) or 0.0) - float(turn.get("start_time", 0.0) or 0.0))

    def record_contradiction(self, diarized_id: str, evidence: float) -> None:
        if diarized_id not in self.session.speaker_mapping:
            return
        now = time.time()
        self.session.mapping_contradiction_count += 1
        history = self.session.mapping_contradictions.setdefault(diarized_id, [])
        history.append({"timestamp": now, "evidence": evidence})
        history = [
            item
            for item in history
            if now - item["timestamp"] <= settings.SPEAKER_RECHECK_WINDOW_SECONDS
        ]
        self.session.mapping_contradictions[diarized_id] = history
        if len(history) >= 2:
            self._transition("degraded")
