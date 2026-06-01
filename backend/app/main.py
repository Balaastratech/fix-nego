import base64
import json as _json
from urllib.parse import quote

from fastapi import FastAPI, Request, Body, HTTPException, Depends
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
import asyncio
from asgi_correlation_id.middleware import CorrelationIdMiddleware
from typing import Dict, Any

# ── k2_fsa Patch (MUST be first, before any pyannote imports) ────────────────
from app.utils.speechbrain_patch import patch_speechbrain_k2
patch_speechbrain_k2()
# ──────────────────────────────────────────────────────────────────────────────

# ── Compatibility shim ────────────────────────────────────────────────────────
# pyannote.audio 3.1.1 calls hf_hub_download(use_auth_token=...) internally,
# but huggingface_hub >= 0.23.0 removed that parameter (renamed to `token`).
# This patch translates the old kwarg to the new one so both work transparently.
import huggingface_hub
import huggingface_hub.file_download as _hf_file_download

_original_hf_hub_download = huggingface_hub.hf_hub_download

def _patched_hf_hub_download(*args, **kwargs):
    if 'use_auth_token' in kwargs:
        legacy_token = kwargs.pop('use_auth_token')
        if legacy_token is not None and 'token' not in kwargs:
            kwargs['token'] = legacy_token
    return _original_hf_hub_download(*args, **kwargs)

huggingface_hub.hf_hub_download = _patched_hf_hub_download
_hf_file_download.hf_hub_download = _patched_hf_hub_download
# ─────────────────────────────────────────────────────────────────────────────

from app.config import settings
from app.api.auth import get_current_user
from app.models.negotiation import NegotiationSession
from app.services.capability_registry import capability_registry, CapabilityStatus
from app.services.connection_manager import connection_manager
from app.services.readiness import readiness
from app.services.session_store import session_store
from app.services.speechbrain_service import speechbrain_service
from app.services.stt_service import SpeechTranscriptionService
from app.utils.logging_config import setup_logging

setup_logging(log_level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Negotiation Copilot", version="1.0.0")

app.add_middleware(CorrelationIdMiddleware)

# Desktop (Electron) renderer pages load from file:// so their Origin header is
# "null". Add desktop-friendly origins alongside the configurable web origins so
# the in-app Settings page can call the REST config API. These fetches send no
# credentials, so echoing the "null" origin is safe.
_DESKTOP_ORIGINS = ["null", "file://", "app://.", "http://localhost:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list + _DESKTOP_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _log_google_auth_context() -> None:
    """Log the configured Vertex target and the resolved ADC identity when available."""
    logger.info(
        "Google AI configuration",
        extra={
            "use_vertex_ai": settings.GOOGLE_GENAI_USE_VERTEXAI,
            "configured_project": settings.GOOGLE_CLOUD_PROJECT or None,
            "configured_location": settings.GOOGLE_CLOUD_LOCATION,
        },
    )

    if not settings.GOOGLE_GENAI_USE_VERTEXAI:
        return

    try:
        import google.auth

        credentials, detected_project = google.auth.default()
        credential_identity = (
            getattr(credentials, "service_account_email", None)
            or getattr(credentials, "account", None)
            or credentials.__class__.__name__
        )
        logger.info(
            "Resolved Google ADC credentials",
            extra={
                "credential_identity": credential_identity,
                "detected_project": detected_project,
                "quota_project_id": getattr(credentials, "quota_project_id", None),
            },
        )
    except Exception as exc:
        logger.warning(f"Failed to resolve Google ADC credentials: {exc}", exc_info=True)


def _validate_runtime_configuration() -> None:
    def _explicitly_enabled(value: object) -> bool:
        return value is True

    supported_auto_languages = set(settings.supported_auto_speaker_languages_list)
    requested_languages = set(settings.transcription_language_codes_list)

    if settings.SPEECHBRAIN_ENABLED:
        conflicting = []
        if _explicitly_enabled(settings.RESEMBLYZER_ENABLED):
            conflicting.append("RESEMBLYZER_ENABLED")
        if _explicitly_enabled(settings.WESPEAKER_ENABLED):
            conflicting.append("WESPEAKER_ENABLED")
        if _explicitly_enabled(getattr(settings, "AZURE_SPEAKER_VERIFICATION_ENABLED", False)):
            conflicting.append("AZURE_SPEAKER_VERIFICATION_ENABLED")
        if conflicting:
            raise RuntimeError(
                "SpeechBrain is configured as the sole biometric provider, "
                f"but conflicting providers are still enabled: {', '.join(conflicting)}"
            )

    unsupported_languages = sorted(requested_languages - supported_auto_languages)
    if unsupported_languages:
        logger.warning(
            "Requested STT languages exceed the verified auto-speaker launch set",
            extra={
                "unsupported_languages": unsupported_languages,
                "supported_auto_languages": sorted(supported_auto_languages),
            },
        )


async def _run_capability_probes_in_background() -> None:
    probe_session = NegotiationSession(session_id="startup-probe")
    stt_service = SpeechTranscriptionService(probe_session)
    stt_provider = settings.TRANSCRIPTION_PROVIDER

    try:
        stt_ok, stt_reason = await asyncio.wait_for(
            asyncio.to_thread(stt_service.probe_capability),
            timeout=settings.STARTUP_PROBE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        stt_ok, stt_reason = False, f"probe_timed_out_after_{settings.STARTUP_PROBE_TIMEOUT_SECONDS}s"
    except Exception as exc:
        stt_ok, stt_reason = False, str(exc) or type(exc).__name__

    if stt_provider == "deepgram":
        if stt_ok:
            logger.info(
                "Deepgram STT probe succeeded",
                extra={
                    "stt_provider": stt_provider,
                    "stt_model": settings.DEEPGRAM_MODEL,
                    "deepgram_base_url": settings.DEEPGRAM_API_BASE_URL,
                },
            )
        else:
            logger.error(
                "Deepgram STT probe failed",
                extra={
                    "stt_provider": stt_provider,
                    "stt_model": settings.DEEPGRAM_MODEL,
                    "deepgram_base_url": settings.DEEPGRAM_API_BASE_URL,
                    "reason": stt_reason,
                },
            )
    elif stt_ok:
        logger.info(
            "Google STT diarization probe succeeded",
            extra={
                "stt_provider": stt_provider,
                "google_stt_region": settings.GOOGLE_STT_REGION,
                "google_stt_location": settings.GOOGLE_STT_LOCATION,
                "google_stt_recognizer": settings.GOOGLE_STT_RECOGNIZER,
                "stt_model": settings.GOOGLE_STT_MODEL,
            },
        )
    else:
        logger.error(
            "Google STT diarization probe failed",
            extra={
                "stt_provider": stt_provider,
                "google_stt_region": settings.GOOGLE_STT_REGION,
                "google_stt_location": settings.GOOGLE_STT_LOCATION,
                "google_stt_recognizer": settings.GOOGLE_STT_RECOGNIZER,
                "reason": stt_reason,
            },
        )
    capability_registry.set_stt(
        CapabilityStatus(
            available=stt_ok,
            reason=stt_reason,
            provider=stt_provider,
            region=settings.GOOGLE_STT_REGION if stt_provider == "google_stt" else settings.DEEPGRAM_API_BASE_URL,
        )
    )

    try:
        speechbrain_ok, speechbrain_reason = await asyncio.wait_for(
            asyncio.to_thread(speechbrain_service.probe_capability),
            timeout=settings.STARTUP_PROBE_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        speechbrain_ok, speechbrain_reason = False, str(exc)

    capability_registry.set_speechbrain(
        CapabilityStatus(
            available=speechbrain_ok,
            reason=speechbrain_reason,
            provider="speechbrain",
            region=settings.SPEECHBRAIN_DEVICE,
        )
    )
    if speechbrain_ok:
        logger.info(
            "SpeechBrain probe succeeded",
            extra={"speechbrain_device": settings.SPEECHBRAIN_DEVICE},
        )
    else:
        logger.warning(
            "SpeechBrain probe failed; disabling SpeechBrain runtime path",
            extra={"speechbrain_device": settings.SPEECHBRAIN_DEVICE, "reason": speechbrain_reason},
        )

    logger.info(
        "Capability path selected",
        extra={
            "active_capability_path": capability_registry.active_path(),
            "stt_provider": stt_provider,
            "google_stt_region": settings.GOOGLE_STT_REGION,
            "speechbrain_enabled": settings.SPEECHBRAIN_ENABLED,
        },
    )

    # Probes are done — the backend is now safe to start a session against.
    # Flip the readiness flag (and wake any websocket clients waiting on it) so
    # the desktop UI can enable the Start button with a clear "ready" indicator.
    readiness.mark_ready(
        {
            "capability_path": capability_registry.active_path(),
            "stt_provider": stt_provider,
            "stt_available": stt_ok,
        }
    )
    await connection_manager.broadcast_backend_ready()
    logger.info("Backend marked ready for sessions")

@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting AI Negotiation Copilot with primary model: {settings.GEMINI_MODEL}")
    _log_google_auth_context()
    _validate_runtime_configuration()
    
    logger.info(
        "Speaker recognition providers configured",
        extra={
            "speaker_recognition_enabled": settings.SPEAKER_RECOGNITION_ENABLED,
            "resemblyzer_enabled": settings.RESEMBLYZER_ENABLED,
            "wespeaker_enabled": settings.WESPEAKER_ENABLED,
            "speechbrain_enabled": settings.SPEECHBRAIN_ENABLED,
        },
    )
    session_store.initialize()
    # auth_db must be configured AFTER session_store.initialize() (which creates
    # the auth tables) so auth_db can open connections to the same DB file.
    from app.services import auth_db
    auth_db.configure(settings.SESSION_DB_PATH)
    asyncio.create_task(_run_capability_probes_in_background(), name="startup-capability-probes")
    logger.info(
        "Capability probes scheduled in background",
        extra={
            "stt_provider": settings.TRANSCRIPTION_PROVIDER,
            "google_stt_region": settings.GOOGLE_STT_REGION,
            "speechbrain_device": settings.SPEECHBRAIN_DEVICE,
        },
    )
    logger.info(
        "Capability report",
        extra={
            "stt_mode": settings.TRANSCRIPTION_PROVIDER,
            "speaker_mode": "speechbrain" if settings.SPEECHBRAIN_ENABLED else "manual",
            "supported_launch_languages": settings.transcription_language_codes_list,
            "persistence_enabled": False,
            "vision_enabled": settings.VISION_ENABLED,
            "session_resumption_enabled": False,
        },
    )

@app.get("/")
async def clerk_root_handler(
    request: Request,
    __clerk_handshake: str | None = None,
    __clerk_db_jwt: str | None = None,
):
    """Handle every browser landing on the backend root during the Clerk flow.

    Two cases both end by bouncing the browser back to /auth/login-page:

    1. **Handshake** (``?__clerk_handshake=<JWT>``): Clerk JS, loaded on our origin
       (different from Clerk's own domain), redirects here to sync its session
       cookies. We decode the JWT and replay the Set-Cookie headers it carries.

    2. **Post-sign-in landing** (no handshake param): after a successful sign-in
       Clerk navigates to its default ``afterSignInUrl`` of ``/``. There's no
       handshake here — we simply redirect back to the login page, where Clerk JS
       now sees an authenticated session and completes the token handoff.

    The ``_clerk_redirect`` cookie (set when the login page was first served) tells
    us the loopback callback URL to thread back through.
    """
    redirect_uri = request.cookies.get("_clerk_redirect", "")
    signout = request.cookies.get("_clerk_signout", "")

    login_url = "/auth/login-page"
    params = []
    if redirect_uri:
        params.append(f"redirect={quote(redirect_uri, safe='')}")
    if signout == "1":
        # Preserve the signout intent across this handshake so Clerk.user can be
        # populated before we sign out. /auth/clear-signout deletes the flag once
        # the sign-out completes — do NOT delete it here (that broke mid-handshake).
        params.append("signout=1")
    if params:
        login_url += "?" + "&".join(params)

    response = RedirectResponse(url=login_url, status_code=302)

    handshake_jwt = __clerk_handshake or __clerk_db_jwt
    if handshake_jwt:
        # Decode the payload (no signature verify — it's just a cookie transport).
        try:
            parts = handshake_jwt.split(".")
            padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
            payload = _json.loads(base64.urlsafe_b64decode(padded))
            for cookie_str in payload.get("handshake", []):
                response.headers.append("Set-Cookie", cookie_str)
        except Exception:
            logger.warning("Failed to decode Clerk handshake JWT", exc_info=True)

    return response


@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/health")
async def health_check_root():
    return {"status": "healthy"}

@app.get("/api/ready")
async def readiness_check():
    """Plain readiness snapshot for the desktop UI. Returns whether the AI
    capability probes have finished (i.e. it is safe to start a session) plus a
    plain-language status message. Polled by the full window so its Start button
    and status banner don't depend on the overlay's BroadcastChannel relay."""
    return readiness.snapshot()

@app.get("/api/sessions", dependencies=[Depends(get_current_user)])
async def list_sessions(limit: int = 20):
    return {"sessions": session_store.list_sessions(limit=limit)}

@app.get("/api/sessions/{session_id}", dependencies=[Depends(get_current_user)])
async def get_session_history(session_id: str):
    bundle = session_store.load_session_bundle(session_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return bundle

frontend_logger = logging.getLogger("frontend")

@app.post("/api/log")
async def log_frontend_message(request: Request, payload: Dict[str, Any] = Body(...)):
    # The correlation ID is automatically picked up by the logger from the request context
    frontend_logger.info(payload.get("message", "No message"), extra=payload)
    return {"status": "logged"}


from app.api.websocket import router as websocket_router
app.include_router(websocket_router)

from app.api.providers import router as providers_router
app.include_router(providers_router)

from app.api.auth_routes import router as auth_router
app.include_router(auth_router)
