import uuid
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.connection_manager import connection_manager
from app.models.negotiation import NegotiationSession, NegotiationState
from app.services.negotiation_engine import NegotiationEngine
from app.services.readiness import readiness
from app.services.session_store import session_store
from app.utils.session_trace import create_session_trace, get_session_trace
from app.config import settings
from app.providers import runtime_config
from app.api.auth import websocket_get_user

router = APIRouter()
logger = logging.getLogger(__name__)


def _restore_session_from_bundle(session: NegotiationSession, bundle: dict) -> None:
    context = bundle.get("context") or {}
    session.state = NegotiationState(bundle.get("state") or NegotiationState.CONSENTED.value)
    session.session_restored = True
    session.started_at = bundle.get("started_at")
    session.consent_version = bundle.get("consent_version")
    session.consent_mode = bundle.get("consent_mode")
    session.language = bundle.get("language")
    session.response_language = bundle.get("response_language")
    # Multilanguage (no-op when MULTILANG_ENABLED=False — values just sit on the session)
    session.language_profile = bundle.get("language_profile")
    session.display_language = bundle.get("display_language")
    session.per_source_language = bundle.get("per_source_language") or {}
    session.user_context = context.get("user_context") or {}
    session.degraded_mode = context.get("degraded_mode")
    session.source_mode = context.get("source_mode") or session.source_mode
    session.meeting_binding = context.get("meeting_binding") or session.meeting_binding
    session.audio_sources_active = context.get("audio_sources_active") or {}
    session.hold_state = context.get("hold_state") or session.hold_state
    session.capture_health = context.get("capture_health") or session.capture_health
    session.capture_preset = context.get("capture_preset") or session.capture_preset
    session.companion_quality_mode = context.get("companion_quality_mode") or session.companion_quality_mode
    selected_output = context.get("selected_output_device") or {}
    session.selected_output_device_id = selected_output.get("device_id")
    session.selected_output_device_label = selected_output.get("label")
    session.degraded_reasons = list(context.get("degraded_reasons") or [])
    session.resume_token = context.get("resume_token") or session.resume_token
    session.display_transcript_turns = bundle.get("transcript") or []
    session.research_history = bundle.get("research") or []
    session.advisor_history = bundle.get("advisor") or []
    session.vision_history = bundle.get("vision") or []
    session.speaker_mapping = bundle.get("speaker_mapping") or {}
    session.session_metrics.update(bundle.get("metrics") or {})
    session.final_summary = bundle.get("final_summary") or {}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Auth gate: accept a valid app JWT or the shared admin token. When
    # AUTH_REQUIRED=False and no token at all, returns an anonymous user so
    # dev/localhost behavior is completely unchanged.
    auth_user = websocket_get_user(websocket)
    if auth_user is None:
        await websocket.close(code=1008)  # 1008 = policy violation
        logger.warning("WebSocket rejected: invalid or missing token")
        return

    requested_session_id = websocket.query_params.get("session_id")
    restored = False
    restored_bundle = None

    if requested_session_id:
        existing_session = connection_manager.get_session(requested_session_id)
        if existing_session is not None:
            session = existing_session
            session_id = existing_session.session_id
            restored = True
        else:
            restored_bundle = session_store.load_session_bundle(requested_session_id)
            if restored_bundle is not None:
                session_id = requested_session_id
                session = NegotiationSession(session_id=session_id)
                _restore_session_from_bundle(session, restored_bundle)
                restored = True
            else:
                session_id = str(uuid.uuid4())
                session = NegotiationSession(session_id=session_id)
    else:
        session_id = str(uuid.uuid4())
        session = NegotiationSession(session_id=session_id)
    
    await websocket.accept()
    await connection_manager.register(websocket, session_id, session)
    trace = create_session_trace(session_id)
    session.trace_jsonl_path = str(trace.trace_path)
    session.trace_report_path = str(trace.report_path)
    trace.record(
        category="session",
        name="websocket_connected",
        summary="WebSocket connection accepted for session",
        data={
            "requested_session_id": requested_session_id,
            "restored": restored,
            "state": session.state.value,
        },
    )
    
    logger.info(f"WebSocket connection established [session={session_id}]")
    
    await websocket.send_json({
        "type": "CONNECTION_ESTABLISHED",
        "payload": {
            "session_id": session_id,
            "server_time": 0,
            "restored": restored,
            "state": session.state.value,
            "resume_token": session.resume_token,
            "trace_jsonl_path": session.trace_jsonl_path,
            "trace_report_path": session.trace_report_path,
            "ready_to_start": readiness.is_ready,
            "readiness": readiness.snapshot(),
        }
    })
    # Phase G — bind this task to the session's provider overlay (None until a
    # PROVIDER_CONFIG message arrives → identical to pre-Phase-G behavior). The
    # initial preconnect below therefore uses the .env key; once the client sends
    # its own key, handle_provider_config re-keys the Live session.
    runtime_config.set_session_overrides(session.provider_overrides)
    NegotiationEngine.start_live_preconnect(
        session,
        settings.GEMINI_API_KEY,
        context="Desktop companion virtual meeting session",
    )
    if restored:
        trace.record(
            category="session",
            name="session_restored",
            summary="Existing session state restored onto websocket connection",
            data={
                "state": session.state.value,
                "transcript_turns": len(session.display_transcript_turns),
                "research_events": len(session.research_history),
                "advisor_events": len(session.advisor_history),
                "vision_events": len(session.vision_history),
            },
        )
        await websocket.send_json({
            "type": "SESSION_RESTORED",
            "payload": {
                "session_id": session_id,
                "state": session.state.value,
                "language": session.language,
                "response_language": session.response_language,
                "transcript": list(session.display_transcript_turns),
                "research": list(session.research_history),
                "advisor": list(session.advisor_history),
                "vision": list(session.vision_history),
                "speaker_mapping": dict(session.speaker_mapping),
                "final_summary": dict(session.final_summary),
            },
        })
    
    try:
        while True:
            try:
                message = await websocket.receive()

                # Phase G — keep this task bound to the latest session overlay so
                # message handlers and any task they spawn resolve providers/keys
                # against the client's own config (set by an earlier PROVIDER_CONFIG).
                runtime_config.set_session_overrides(session.provider_overrides)

                if message.get("type") == "websocket.disconnect":
                    active_trace = get_session_trace(session_id)
                    if active_trace:
                        active_trace.record(
                            category="session",
                            name="websocket_disconnect",
                            summary="Client websocket disconnected",
                            data={"state": session.state.value},
                        )
                    if session.state in {NegotiationState.ENDING, NegotiationState.IDLE}:
                        logger.info(f"Client disconnected via ASGI after normal session end [session={session_id}]")
                    else:
                        logger.info(f"Client disconnected via ASGI [session={session_id}]")
                    break
                
                if "bytes" in message and message["bytes"]:
                    if session.state == NegotiationState.ACTIVE:
                        if not await NegotiationEngine.validate_message(websocket, session, "AUDIO_CHUNK"):
                            continue
                        await NegotiationEngine.handle_audio_chunk(session, message["bytes"], websocket)
                    elif session.state == NegotiationState.CONSENTED:
                        # Handle enrollment audio - only if enrollment service is active
                        enrollment_service = getattr(session, 'enrollment_service', None)
                        enrollment_state = enrollment_service.state.name if enrollment_service else "NONE"
                        
                        if enrollment_service and enrollment_state == "CAPTURING":
                            result = await enrollment_service.process_audio(message["bytes"])
                            if result:
                                logger.info(f"📝 Enrollment {result['type']}")
                                await websocket.send_json(result)
                        elif not enrollment_service:
                            logger.debug("No enrollment service active")
                        else:
                            logger.debug(f"Enrollment not capturing ({enrollment_state})")
                    elif session.state == NegotiationState.PAUSED:
                        continue
                    else:
                        # Send error to frontend to stop sending audio
                        await websocket.send_json({
                            "type": "ERROR",
                            "payload": {
                                "code": "INVALID_STATE",
                                "message": f"Cannot process audio in state: {session.state.value}"
                            }
                        })
                    
                elif "text" in message and message["text"]:
                    data = json.loads(message["text"])
                    msg_type = data.get("type", "UNKNOWN")
                    
                    if not await NegotiationEngine.validate_message(websocket, session, msg_type):
                        continue
                    
                    await NegotiationEngine.route_message(websocket, session, msg_type, data.get("payload", {}))
                    
            except json.JSONDecodeError as e:
                active_trace = get_session_trace(session_id)
                if active_trace:
                    active_trace.record(
                        category="error",
                        name="invalid_json",
                        summary="Invalid JSON received on websocket",
                        data={"error": str(e)},
                    )
                logger.error(f"Invalid JSON received [session={session_id}]: {e}")
                await websocket.send_json({
                    "type": "ERROR",
                    "payload": {"code": "INVALID_JSON", "message": "Invalid message format."}
                })
                continue
                
    except WebSocketDisconnect:
        active_trace = get_session_trace(session_id)
        if active_trace:
            active_trace.record(
                category="session",
                name="websocket_disconnect_exception",
                summary="WebSocketDisconnect raised during receive loop",
                data={"state": session.state.value},
            )
        if session.state in {NegotiationState.ENDING, NegotiationState.IDLE}:
            logger.info(f"Client disconnected after normal session end [session={session_id}]")
        else:
            logger.info(f"Client disconnected [session={session_id}]")
    except Exception as e:
        active_trace = get_session_trace(session_id)
        if active_trace:
            active_trace.record(
                category="error",
                name="websocket_exception",
                summary="Unhandled websocket exception",
                data={"error": str(e), "state": session.state.value},
            )
        logger.error(f"WebSocket error [session={session_id}]: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "ERROR",
                "payload": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}
            })
        except Exception:
            pass
    finally:
        active_trace = get_session_trace(session_id)
        if active_trace:
            active_trace.record(
                category="session",
                name="websocket_cleanup",
                summary="WebSocket cleanup started",
                data={"state": session.state.value},
            )
        logger.info(f"Cleaning up WebSocket connection [session={session_id}]")
        await connection_manager.unregister(
            session_id,
            preserve_runtime=bool(session.state == NegotiationState.ACTIVE and session.session_resumable),
        )
