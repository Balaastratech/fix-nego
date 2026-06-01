from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict, Field
import asyncio
import time
import uuid

from app.models.companion import CaptureHealth, CompanionHoldState, MeetingBinding, SourceMode


class NegotiationState(str, Enum):
    """State machine states for negotiation sessions."""
    IDLE = "IDLE"
    CONSENTED = "CONSENTED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ENDING = "ENDING"


class NegotiationSession(BaseModel):
    """Model representing a negotiation session.
    
    Tracks session state, consent information, and negotiation data
    including transcript and strategy history.
    """
    session_id: str
    state: NegotiationState = NegotiationState.IDLE
    consent_version: Optional[str] = None
    consent_mode: Optional[str] = None  # "live" or "roleplay"
    started_at: Optional[float] = None  # unix timestamp
    context: str = ""  # negotiation context string
    language: Optional[str] = None
    response_language: Optional[str] = None
    # Multilanguage adaptation (only consulted when settings.MULTILANG_ENABLED).
    # language_profile: "auto_multi" | "pinned:<bcp47>" | "" (use settings default)
    # display_language: BCP-47 the overlay wants to render transcripts in (None = same as spoken)
    # per_source_language: maps companion source key (LOCAL_MIC_PCM / REMOTE_APP_PCM / ASK_AI_PCM)
    #                     to a Deepgram language profile string overriding language_profile.
    # voice_fallback_text_only: defensive — set True if response_language is outside the
    #                           Gemini Live 97-lang set so the overlay renders a text bubble
    #                           instead of expecting audio.
    language_profile: Optional[str] = None
    display_language: Optional[str] = None
    per_source_language: dict[str, str] = Field(default_factory=dict)
    voice_fallback_text_only: bool = False
    session_resumable: bool = True
    session_restored: bool = False
    resume_token: str = Field(default_factory=lambda: uuid.uuid4().hex)
    last_persisted_at: Optional[float] = None
    degraded_mode: Optional[str] = None
    source_mode: str = SourceMode.IN_PERSON_WEB.value
    meeting_binding: dict = Field(default_factory=lambda: MeetingBinding().model_dump())
    audio_sources_active: dict = Field(default_factory=dict)
    hold_state: dict = Field(default_factory=lambda: CompanionHoldState().model_dump())
    capture_health: dict = Field(default_factory=lambda: CaptureHealth().model_dump())
    capture_preset: str = "browser_default"
    companion_quality_mode: str = "inactive"
    selected_output_device_id: Optional[str] = None
    selected_output_device_label: Optional[str] = None
    capture_helper_active: bool = False
    degraded_reasons: list[str] = Field(default_factory=list)
    
    # Gemini Live session handle (not serialized - runtime only)
    live_session: Optional[Any] = None
    # Async context manager returned by open_live_session – kept so __aexit__ can be called on end
    live_session_cm: Optional[Any] = None
    # API key stored for auto-reconnect on 1007 codec errors
    api_key: Optional[str] = None
    # Phase G — per-session BYOK overlay sent by the desktop via PROVIDER_CONFIG.
    # Shape mirrors the runtime JSON: {"slots":{}, "keys":{}, "settings":{}}.
    # Scoped to this websocket session only (applied through a runtime_config
    # ContextVar in the WS receive loop); never persisted to the global JSON.
    provider_overrides: Optional[dict] = None
    live_session_receive_task: Optional[Any] = None
    live_session_keepalive_task: Optional[Any] = None
    live_session_monitor_task: Optional[Any] = None
    live_reconnect_task: Optional[Any] = None
    live_preconnect_task: Optional[Any] = None
    live_preconnected_context: str = ""
    live_preconnect_error: Optional[str] = None
    live_preconnected_at: Optional[float] = None

    # Dual-Model: rolling audio buffer (shared between audio sender & listener)
    audio_buffer: Optional[Any] = None
    # Dual-Model: background listener agent task
    listener_agent: Optional[Any] = None
    speech_transcriber: Optional[Any] = None

    # Flag — True only during deliberate long-press window; gates mic audio to Live AI
    user_addressing_ai: bool = False
    # Tracks whether we've opened a manual user-audio activity on the Live session
    # (only used when settings.ASK_AI_NATIVE_AUDIO=True). Prevents double activity_start
    # if hold-state messages arrive twice, and ensures activity_end always fires.
    ask_audio_activity_open: bool = False
    # True from the moment the user presses hold until the first AI response after
    # release is dispatched (or a ~5s timeout fires if Gemini never responds).
    # Used by gemini_client to classify AI responses as ask_ai vs advisor — when
    # ASK_AI_NATIVE_AUDIO=True the audio response may arrive before direct_query_in_flight
    # would normally be set by the text-question path. This flag covers that gap.
    ask_window_active: bool = False
    # Monotonically incremented on every hold press. The orphan-close safety
    # timer captures its current value at scheduling time and only acts if the
    # value still matches when it fires — prevents the previous cycle's stale
    # timer from killing a brand-new ask window.
    ask_cycle_gen: int = 0
    # Flag — True after user presses Start Copilot; persists for the whole negotiation
    copilot_active: bool = False
    
    # AI speaking state - used to pause intel injections while AI is generating audio
    ai_is_speaking: bool = False
    # True while frontend is actively playing Gemini PCM in the user's earphone.
    # This gates remote loopback capture so the AI does not transcribe itself.
    ai_audio_playing: bool = False
    # Queue for intel injections that were skipped while AI was speaking
    pending_injections: list = Field(default_factory=list)
    pending_live_snapshot: Optional[dict] = None
    pending_intel_context: Optional[dict] = None
    pending_intel_critical_events: list[dict] = Field(default_factory=list)
    intel_injection_task: Optional[Any] = None
    last_intel_injected_at: float = 0.0
    
    # Stores the last transcribed text from the user's direct address to the AI
    last_user_transcript: str = ""
    # Set True when user releases long-press so receive_responses knows the next
    # turn_complete is from a direct user query — prevents flush_pending_injections
    # from firing and triggering a second proactive AI response.
    direct_query_in_flight: bool = False
    
    # Accumulates AI response text for validation at turn_complete
    current_ai_response: str = ""
    recent_ai_responses: list[str] = Field(default_factory=list)
    last_ai_audio_played_at: float = 0.0
    last_ask_response_at: float = 0.0

    # Retained for compatibility with older clients. The active behavior is now
    # a single automatic answer policy that chooses the response shape from the
    # user's question instead of a manual mode toggle.
    response_mode: str = "auto"

    # Context submitted via the SetupDialog (item, target_price, max_price, extra_context)
    user_context: dict = Field(default_factory=dict)

    # Lock that serializes ALL send_realtime_input calls for this session.
    # The Gemini Live SDK raises errors if audio and text are sent concurrently.
    gemini_send_lock: Any = Field(default_factory=asyncio.Lock)

    # Speaker identification (manual selection only)
    current_speaker: str = "unknown"  # "user", "counterparty", or "unknown"
    manual_override_until: Optional[float] = None # Timestamp until which auto-recognition is paused
    speaker_last_updated: float = 0.0  # timestamp of last speaker update
    # Timeline of speaker changes: [{speaker, timestamp}] — used by ListenerAgent for per-window attribution
    speaker_timeline: list = Field(default_factory=list)
    # Speaker mapping for Gemini diarization: {"Speaker 1": "user", "Speaker 2": "counterparty"}
    speaker_mapping: dict = Field(default_factory=dict)
    speaker_mapping_state: str = "unmapped"
    speaker_mapping_confidence: Optional[float] = None
    speaker_mapping_locked_at: Optional[float] = None
    speaker_mapping_last_validated_at: Optional[float] = None
    speaker_embedding_cache: dict = Field(default_factory=dict)
    speaker_cluster_centroids: dict = Field(default_factory=dict)
    mapping_contradiction_count: int = 0
    mapping_state_transitions: list[dict] = Field(default_factory=list)
    mapping_contradictions: dict = Field(default_factory=dict)
    permanent_unknown_speaker_ids: set[str] = Field(default_factory=set)
    
    # Speaker Recognition Fields (Requirements 11.1, 11.2, 11.3)
    user_embedding: Optional[Any] = None  # 256-dimensional voice fingerprint (numpy array)
    enrollment_audio: Optional[bytes] = None  # Raw PCM audio from enrollment (for diarization)
    speaker_mode: str = "manual"  # "auto" or "manual"
    speaker_recognition_enabled: bool = False  # Feature toggle
    speaker_confidence_history: list[dict] = Field(default_factory=list)  # Classification history
    counterparty_candidates: list[dict] = Field(default_factory=list)
    counterparty_cluster_embedding: Optional[Any] = None
    counterparty_cluster_promoted_at: Optional[float] = None
    speechbrain_profile_state: str = "none"
    speechbrain_reference_embedding: Optional[Any] = None
    speechbrain_last_result: Optional[dict] = None
    speechbrain_verification_attempts: int = 0
    speechbrain_verification_successes: int = 0
    speechbrain_verification_failures: int = 0
    azure_profile_id: Optional[str] = None
    azure_profile_state: str = "none"
    azure_last_verification_at: Optional[float] = None
    azure_last_verification_result: Optional[dict] = None
    azure_verification_attempts: int = 0
    azure_verification_successes: int = 0
    azure_verification_failures: int = 0
    azure_fallback_to_resemblyzer_count: int = 0
    azure_verification_calls: int = 0
    
    # Runtime speaker service instances (not serialized)
    speaker_service: Optional[Any] = None
    enrollment_service: Optional[Any] = None
    perfect_listener: Optional[Any] = None  # PerfectListenerSystem instance
    
    # Transcript buffering (for accurate speaker labeling)
    pending_transcripts: list[dict] = Field(default_factory=list)  # Transcripts waiting for speaker confirmation
    display_transcript_turns: list[dict] = Field(default_factory=list)
    eligible_transcript_turns: list[dict] = Field(default_factory=list)
    pending_utterance_audio: bytes = b""
    pending_utterance_id: Optional[str] = None
    pending_utterance_started_at: Optional[float] = None
    pending_utterance_rms: float = 0.0
    partial_transcript_text: Optional[str] = None
    partial_transcript_task: Optional[Any] = None
    partial_transcript_started_at: Optional[float] = None
    partial_transcript_last_emit_at: float = 0.0
    partial_transcript_source: Optional[str] = None

    # Speaker segment tracking — who is speaking NOW (set on button click)
    speaker_segment_start: float = 0.0      # kept for manual_mode guard only
    speaker_segment_speaker: str = "unknown"

    # Direct audio accumulation for the current speaker turn.
    # Audio is appended here on every AUDIO_CHUNK while this speaker is active.
    # On the NEXT button click the buffer is extracted and transcribed with the
    # PREVIOUS speaker label — no timestamp arithmetic, no clock-drift issues.
    current_segment_audio: bytes = b""

    # Captures raw PCM audio while user holds the "Ask AI" button.
    # Transcribed to text on button release for reliable Live AI question answering.
    # Audio is NOT pushed to the listener buffer during this window.
    question_capture_bytes: bytes = b""
    question_capture_id: Optional[str] = None
    question_capture_started_at: Optional[float] = None
    question_capture_chunk_count: int = 0
    question_capture_last_chunk_at: Optional[float] = None
    ignore_local_mic_until: float = 0.0
    current_ask_capture: dict = Field(default_factory=dict)
    companion_audio_buffers: dict[str, bytes] = Field(default_factory=dict)
    companion_audio_started_at: dict[str, float] = Field(default_factory=dict)
    companion_last_chunk_at: dict[str, float] = Field(default_factory=dict)
    companion_last_transcript_at: dict[str, float] = Field(default_factory=dict)
    companion_partial_tasks: dict[str, Any] = Field(default_factory=dict)
    companion_partial_text: dict[str, str] = Field(default_factory=dict)
    companion_partial_started_at: dict[str, float] = Field(default_factory=dict)

    # Outcome tracking
    initial_price: Optional[float] = None
    final_price: Optional[float] = None
    final_summary: dict = Field(default_factory=dict)
    transcript: list[dict] = Field(default_factory=list)
    research_history: list[dict] = Field(default_factory=list)
    advisor_history: list[dict] = Field(default_factory=list)
    vision_history: list[dict] = Field(default_factory=list)
    trace_jsonl_path: Optional[str] = None
    trace_report_path: Optional[str] = None
    trace_refs: dict = Field(default_factory=dict)

    # Continuous Pro Vision Analysis fields
    # Stores structured VisionObservation dicts produced by analyze_vision_frames()
    vision_observations: list[dict] = Field(default_factory=list)
    # Ring buffer of raw JPEG bytes waiting to be sent to Pro (max VISION_PRO_MAX_FRAMES)
    vision_frame_buffer: list = Field(default_factory=list)
    # MD5 hex of the last 64×64 thumbnail used for scene-change detection
    vision_last_hash: str = ""
    # True when a new scene change has been buffered and Pro hasn't been called yet
    vision_needs_analysis: bool = False
    # Epoch time of last Pro vision call — used to enforce cooldown
    vision_last_pro_call_at: float = 0.0
    # Total number of Pro vision calls in this session (for cost monitoring)
    vision_pro_call_count: int = 0
    vision_analysis_task: Optional[Any] = None
    # ── Next-move cache (per-live-session, not persisted) ─────────────────
    # Populated by app.services.next_move_cache.refresh_next_move() after
    # _on_context_ready fires. Keys: text, model, generated_at, is_pro,
    # context_basis_hash. Empty dict = no cache yet. Read by
    # handle_user_addressing_ai to inject [RECOMMENDED NEXT MOVE] into the
    # pre-query brief when fresh (≤ NEXT_MOVE_MAX_AGE_SECONDS).
    next_move_cache: dict = Field(default_factory=dict)
    next_move_task: Optional[Any] = None
    next_move_last_refresh_at: float = 0.0
    # Hold-to-ask timing — used by ai_response_completed trace event to
    # compute the end-to-end latency from button release to spoken answer.
    last_hold_started_ms: int = 0
    last_hold_released_ms: int = 0
    vision_live_send_task: Optional[Any] = None
    vision_live_pending_frame_b64: Optional[str] = None
    vision_live_last_sent_at: float = 0.0
    vision_live_drop_count: int = 0
    strategy_history: list[dict] = Field(default_factory=list)
    session_metrics: dict = Field(
        default_factory=lambda: {
            "stt_requests": 0,
            "stt_successes": 0,
            "stt_empty_results": 0,
            "stt_retry_count": 0,
            "speaker_user_count": 0,
            "speaker_counterparty_count": 0,
            "speaker_unknown_count": 0,
            "avg_utterance_duration_ms": 0.0,
            "utterance_count": 0,
            "gemini_reconnect_count": 0,
            "research_requests": 0,
            "research_failures": 0,
            "google_stt_minutes": 0.0,
            "deepgram_stt_minutes": 0.0,
            "speechbrain_verification_calls": 0,
            "speechbrain_ambiguous_turns": 0,
            "azure_verification_calls": 0,
            "gemini_live_input_tokens": 0,
            "gemini_live_output_tokens": 0,
            "research_calls": 0,
            "ask_attempts": 0,
            "ask_retry_count": 0,
            "ask_audio_input_failures": 0,
            "ask_capture_dedicated_count": 0,
            "transcript_duplicate_drops": 0,
        }
    )
    sidecar_lock: Any = Field(default_factory=asyncio.Lock)
    stt_lock: Any = Field(default_factory=asyncio.Lock)
    research_lock: Any = Field(default_factory=asyncio.Lock)

    model_config = ConfigDict(
        arbitrary_types_allowed=True  # required for live_session handle and asyncio.Lock
    )
