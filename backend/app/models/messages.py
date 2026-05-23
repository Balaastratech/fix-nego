from typing import Optional
from pydantic import BaseModel, Field


# =============================================================================
# Client → Server Messages (Text Frames / JSON)
# =============================================================================

class ConsentPayload(BaseModel):
    """Payload for PRIVACY_CONSENT_GRANTED message."""
    version: str
    mode: str  # "live" or "roleplay"


class StartNegotiationPayload(BaseModel):
    """Payload for START_NEGOTIATION message."""
    context: str  # user-provided description of negotiation situation
    source_mode: Optional[str] = None
    meeting_binding: Optional[dict] = None
    capture_preset: Optional[str] = None
    companion_quality_mode: Optional[str] = None
    selected_output_device: Optional[dict] = None


class VisionFramePayload(BaseModel):
    """Payload for VISION_FRAME message."""
    image: str  # base64-encoded JPEG
    timestamp: int  # Unix milliseconds
    source_mode: Optional[str] = None
    source: Optional[str] = None


class SetResponseLanguagePayload(BaseModel):
    """Payload for SET_RESPONSE_LANGUAGE message."""
    language: str


class MeetingBindingPayload(BaseModel):
    """Payload for MEETING_BINDING message."""
    target_id: Optional[str] = None
    window_title: Optional[str] = None
    process_name: Optional[str] = None
    platform_hint: Optional[str] = None
    output_device_id: Optional[str] = None
    output_device_label: Optional[str] = None
    is_bound: bool = False


class CaptureHealthPayload(BaseModel):
    """Payload for CAPTURE_HEALTH message."""
    mic_forward_ok: bool = False
    remote_audio_ok: bool = False
    frame_capture_ok: bool = False
    reply_output_ok: bool = False
    helper_active: bool = False
    process_loopback_ok: bool = False
    unsafe_device_loopback: bool = False
    degraded_reasons: list[str] = Field(default_factory=list)


class HoldToAskStatePayload(BaseModel):
    """Payload for HOLD_TO_ASK_STATE / USER_ADDRESSING_AI messages."""
    active: bool = False
    muted_to_meeting: bool = False


class CompanionAudioPayload(BaseModel):
    """Payload for LOCAL_MIC_PCM / REMOTE_APP_PCM / ASK_AI_PCM messages."""
    pcm_base64: str
    timestamp_ms: int
    is_final: bool = False
    utterance_id: Optional[str] = None
    started_at_ms: Optional[int] = None
    rms: Optional[float] = None


class EndNegotiationPayload(BaseModel):
    """Payload for END_NEGOTIATION message."""
    final_price: Optional[float] = None  # agreed final price (null if no deal)
    initial_price: Optional[float] = None  # original asking price


class TranscriptEntry(BaseModel):
    """Transcript entry for TRANSCRIPT_UPDATE."""
    id: str  # unique ID with txn_ prefix
    speaker: str  # "user" | "counterparty" | "ai"
    text: str
    timestamp: int  # Unix milliseconds


class StrategyUpdate(BaseModel):
    """Strategy update payload for STRATEGY_UPDATE."""
    target_price: Optional[float] = None
    current_offer: Optional[float] = None
    recommended_response: str
    key_points: list[str]
    approach_type: str  # "aggressive" | "collaborative" | "walkaway"
    confidence: float
    walkaway_threshold: Optional[float] = None
    web_search_used: bool
    search_sources: list[str]


class OutcomeSummary(BaseModel):
    """Outcome summary for OUTCOME_SUMMARY."""
    deal_reached: bool
    initial_price: Optional[float] = None
    final_price: Optional[float] = None
    savings: Optional[float] = None
    savings_percentage: Optional[float] = None
    market_value: Optional[float] = None
    vs_market: Optional[float] = None
    negotiation_duration_seconds: int
    key_moves: list[str]
    effectiveness_score: float
    transcript_summary: str


# =============================================================================
# Server → Client Messages (Text Frames / JSON)
# =============================================================================

class ConnectionEstablishedPayload(BaseModel):
    """Payload for CONNECTION_ESTABLISHED."""
    session_id: str
    server_time: int
    restored: bool = False
    resume_token: Optional[str] = None


class ConsentAcknowledgedPayload(BaseModel):
    """Payload for CONSENT_ACKNOWLEDGED."""
    mode: str
    recording_active: bool


class SessionStartedPayload(BaseModel):
    """Payload for SESSION_STARTED."""
    session_id: str
    model: str
    features: dict  # {"audio": bool, "vision": bool, "web_search": bool}


class SessionRestoredPayload(BaseModel):
    """Payload for SESSION_RESTORED."""
    session_id: str
    language: Optional[str] = None
    response_language: Optional[str] = None
    transcript: list[dict] = []
    research: list[dict] = []
    advisor: list[dict] = []
    vision: list[dict] = []
    speaker_mapping: dict = {}


class PersistenceStatusPayload(BaseModel):
    """Payload for PERSISTENCE_STATUS."""
    ready: bool
    session_id: str


class VisionStatusPayload(BaseModel):
    """Payload for VISION_STATUS."""
    timestamp: int
    event: str
    size: Optional[int] = None
    observation: Optional[str] = None


class LanguageUpdatePayload(BaseModel):
    """Payload for LANGUAGE_UPDATE."""
    language: Optional[str] = None
    response_language: Optional[str] = None


class DegradedModeUpdatePayload(BaseModel):
    """Payload for DEGRADED_MODE_UPDATE."""
    active: bool
    mode: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)


class MeetingBindingUpdatePayload(BaseModel):
    """Payload for MEETING_BINDING_UPDATE."""
    binding: dict


class CaptureHealthUpdatePayload(BaseModel):
    """Payload for CAPTURE_HEALTH_UPDATE."""
    health: dict


class TranscriptUpdatePayload(BaseModel):
    """Payload for TRANSCRIPT_UPDATE."""
    id: str
    speaker: str
    text: str
    timestamp: int
    is_partial: bool = False
    source: Optional[str] = None
    context: Optional[str] = None


class StrategyUpdatePayload(BaseModel):
    """Payload for STRATEGY_UPDATE."""
    target_price: Optional[float] = None
    current_offer: Optional[float] = None
    recommended_response: str
    key_points: list[str]
    approach_type: str
    confidence: float
    walkaway_threshold: Optional[float] = None
    web_search_used: bool
    search_sources: list[str]


class AIResponsePayload(BaseModel):
    """Payload for AI_RESPONSE."""
    text: str
    response_type: str  # "analysis" | "coaching" | "alert" | "summary"
    timestamp: int


class AudioInterruptedPayload(BaseModel):
    """Payload for AUDIO_INTERRUPTED."""
    pass  # Empty payload


class SessionReconnectingPayload(BaseModel):
    """Payload for SESSION_RECONNECTING."""
    reason: str  # "gemini_session_dropped" | "session_timeout" | "model_fallback"
    attempt: int
    max_attempts: int


class AIDegradedPayload(BaseModel):
    """Payload for AI_DEGRADED."""
    message: str
    features_available: list[str]


class ErrorPayload(BaseModel):
    """Payload for ERROR messages."""
    code: str
    message: str
