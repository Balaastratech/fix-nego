from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SourceMode(str, Enum):
    IN_PERSON_WEB = "in_person_web"
    VIRTUAL_COMPANION_DESKTOP = "virtual_companion_desktop"


class ParticipantOrigin(str, Enum):
    LOCAL_USER = "local_user"
    REMOTE_COUNTERPARTY = "remote_counterparty"
    AI = "ai"
    UNKNOWN = "unknown"


class MeetingBinding(BaseModel):
    target_id: Optional[str] = None
    window_title: Optional[str] = None
    process_name: Optional[str] = None
    platform_hint: Optional[str] = None
    output_device_id: Optional[str] = None
    output_device_label: Optional[str] = None
    is_bound: bool = False
    bound_at: Optional[float] = None


class CaptureHealth(BaseModel):
    mic_forward_ok: bool = False
    remote_audio_ok: bool = False
    frame_capture_ok: bool = False
    reply_output_ok: bool = False
    helper_active: bool = False
    process_loopback_ok: bool = False
    unsafe_device_loopback: bool = False
    degraded_reasons: list[str] = Field(default_factory=list)


class CompanionHoldState(BaseModel):
    active: bool = False
    muted_to_meeting: bool = False
    started_at: Optional[float] = None
    released_at: Optional[float] = None
