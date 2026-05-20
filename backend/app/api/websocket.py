import uuid
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.connection_manager import connection_manager
from app.models.negotiation import NegotiationSession, NegotiationState
from app.services.negotiation_engine import NegotiationEngine

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    session_id = str(uuid.uuid4())
    session = NegotiationSession(session_id=session_id)
    
    await websocket.accept()
    await connection_manager.register(websocket, session_id, session)
    
    logger.info(f"WebSocket connection established [session={session_id}]")
    
    await websocket.send_json({
        "type": "CONNECTION_ESTABLISHED",
        "payload": {
            "session_id": session_id,
            "server_time": 0,
            "restored": False,
        }
    })
    
    try:
        while True:
            try:
                message = await websocket.receive()
                
                if message.get("type") == "websocket.disconnect":
                    if session.state in {NegotiationState.ENDING, NegotiationState.IDLE}:
                        logger.info(f"Client disconnected via ASGI after normal session end [session={session_id}]")
                    else:
                        logger.info(f"Client disconnected via ASGI [session={session_id}]")
                    break
                
                if "bytes" in message and message["bytes"]:
                    if session.state == NegotiationState.ACTIVE:
                        if not await NegotiationEngine.validate_message(websocket, session, "AUDIO_CHUNK"):
                            continue
                        await NegotiationEngine.handle_audio_chunk(session, message["bytes"])
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
                logger.error(f"Invalid JSON received [session={session_id}]: {e}")
                await websocket.send_json({
                    "type": "ERROR",
                    "payload": {"code": "INVALID_JSON", "message": "Invalid message format."}
                })
                continue
                
    except WebSocketDisconnect:
        if session.state in {NegotiationState.ENDING, NegotiationState.IDLE}:
            logger.info(f"Client disconnected after normal session end [session={session_id}]")
        else:
            logger.info(f"Client disconnected [session={session_id}]")
    except Exception as e:
        logger.error(f"WebSocket error [session={session_id}]: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "ERROR",
                "payload": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}
            })
        except Exception:
            pass
    finally:
        logger.info(f"Cleaning up WebSocket connection [session={session_id}]")
        await connection_manager.unregister(
            session_id,
            preserve_runtime=bool(session.state == NegotiationState.ACTIVE and session.session_resumable),
        )
