import base64
import structlog
from fastapi import FastAPI, Depends, Header, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional
from pydantic import BaseModel
from sqlalchemy import select

from app.config import settings
from app.logging import setup_logging
from app.db.connection import init_db, async_session_maker
from app.db.schema import UserORM
from app.services import auth as auth_service
from app.services import rate_limit
from app.services.session import SessionManager
from app.services.cache import InMemoryCacheProvider
from app.services.conversation import ConversationManager
from app.services.gateway import SpeechGateway
from app.core.models import SessionInfo

# Initialize Logger
setup_logging()
logger = structlog.get_logger(__name__)

# Global instances (Singletons/Container)
session_manager = SessionManager()
cache_provider = InMemoryCacheProvider()
conversation_manager = ConversationManager(session_manager)
speech_gateway = SpeechGateway(session_manager, conversation_manager)
conversation_manager.set_gateway(speech_gateway)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifecycle hook. Initializes DB connection on startup.
    """
    logger.info("application_starting", debug_mode=settings.server.debug)
    await init_db()
    await cache_provider.clear()
    
    # Generate mock telemetry data if DB is empty
    from app.services.telemetry import telemetry_service
    await telemetry_service.generate_mock_data_if_empty()

    # Seed the knowledge base with one example FAQ doc if empty -- proves
    # the KB ingestion/retrieval path end to end without needing real
    # business content yet (general-purpose template).
    from app.services.knowledge import seed_example_doc
    await seed_example_doc()

    # Cascaded voice pipeline (faster-whisper/Ollama/Piper): pre-load all
    # three models now, at startup, in a thread — not lazily on the first
    # user turn. Model load time is highly variable (3s-58s+ observed,
    # depending on OS disk-cache/antivirus-scan state) and must never land
    # in the middle of a user's first real conversation turn.
    if settings.voice_provider == "cascaded":
        import asyncio
        from app.services.cascaded_provider import _run_llm
        logger.info(
            "cascaded_pipeline_warmup_starting",
            stt_provider=settings.stt.provider,
            llm_provider=settings.llm.provider,
            tts_provider=settings.tts.provider,
        )
        # Only warm up the local faster-whisper/Piper fallback models if
        # they're actually the configured provider -- these packages aren't
        # installed in lean deployments (e.g. Railway) that only use the
        # hosted Deepgram/Cartesia providers, and importing them unconditionally
        # here would crash startup. Also skips ~8s of wasted local-model
        # loading whenever the app isn't even using them.
        if settings.stt.provider == "whisper":
            from app.services.cascaded_provider import _get_stt_model
            await asyncio.to_thread(_get_stt_model)
        if settings.tts.provider == "piper":
            from app.services.cascaded_provider import _get_piper_voice
            await asyncio.to_thread(_get_piper_voice, settings.tts.voice_en)
            await asyncio.to_thread(_get_piper_voice, settings.tts.voice_hi)
        # Also warm up the LLM stage now, not on the first real user turn --
        # for Ollama this forces the model into memory (avoids a cold-load
        # mid-conversation); for Gemini this is a cheap sanity check that
        # the API key/network actually work before a real user hits it.
        # Wrapped in try/except: this is a nice-to-have warm-up, not a hard
        # requirement -- the same call just happens lazily on the first
        # real turn if this fails. Confirmed live: an unguarded transient
        # Gemini 503 ("high demand") here crashed the ENTIRE backend at
        # startup, not just skipped the optimization.
        try:
            await _run_llm([{"role": "user", "content": "Hi"}])
        except Exception as e:
            logger.warning("cascaded_llm_warmup_failed_non_fatal", error=str(e))
        logger.info("cascaded_pipeline_warmup_complete")

    yield
    logger.info("application_stopping")

app = FastAPI(
    title="Sonorus Human Conversation Engine",
    description="An enterprise Speech-to-Speech natural interaction agent backend",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# REST API Endpoints
# ==========================================

@app.get("/health", tags=["System"])
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "sonorus-conversation-engine"}

@app.post("/sessions", response_model=SessionInfo, tags=["Sessions"])
async def create_session() -> SessionInfo:
    """
    Creates a new conversation session and initiates the state machine.
    """
    try:
        session_info = await session_manager.create_session()
        return session_info
    except Exception as e:
        logger.error("create_session_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to initialize session")

@app.get("/api/loan-customers", tags=["Sessions"])
async def get_loan_customers() -> list:
    """Lists the dummy loan customers available for testing outbound
    loan-reminder call sessions."""
    from app.services.loan_data import list_customers
    return list_customers()


# ==========================================
# Mobile app user accounts (signup/login)
# ==========================================

class SignupRequest(BaseModel):
    email: str
    password: str
    name: str

class LoginRequest(BaseModel):
    email: str
    password: str

async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = auth_service.decode_token(authorization[len("Bearer "):])
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return payload

@app.post("/api/auth/signup", tags=["Auth"])
async def signup(request: SignupRequest) -> Dict[str, Any]:
    email = request.email.strip().lower()
    if "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    name = request.name.strip() or email.split("@")[0]

    async with async_session_maker() as session:
        existing = await session.execute(select(UserORM).where(UserORM.email == email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        user = UserORM(email=email, password_hash=auth_service.hash_password(request.password), name=name, email_verified=False)
        session.add(user)
        await session.commit()
        await session.refresh(user)

    from app.services.email_service import send_verification_email
    verify_token = auth_service.create_verification_token(user.id)
    verify_url = f"{settings.server.public_base_url}/api/auth/verify?token={verify_token}"
    email_sent = await send_verification_email(user.email, user.name, verify_url)

    if not email_sent:
        # Resend not configured, or the send failed -- don't strand the
        # user unable to ever log in because of an email-infra problem, so
        # fall back to verified-on-signup (same behavior as before this
        # feature existed) rather than a silent dead end.
        async with async_session_maker() as session:
            result = await session.execute(select(UserORM).where(UserORM.id == user.id))
            row = result.scalar_one()
            row.email_verified = True
            await session.commit()
        token = auth_service.create_token(user.id, user.email)
        return {"token": token, "user": {"id": user.id, "email": user.email, "name": user.name}, "verification_email_sent": False}

    return {"token": None, "user": {"id": user.id, "email": user.email, "name": user.name}, "verification_email_sent": True}

@app.get("/api/auth/verify", tags=["Auth"])
async def verify_email(token: str):
    user_id = auth_service.decode_verification_token(token)
    if not user_id:
        return Response(content="<h2>This verification link is invalid or has expired.</h2>", media_type="text/html", status_code=400)

    async with async_session_maker() as session:
        result = await session.execute(select(UserORM).where(UserORM.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return Response(content="<h2>Account not found.</h2>", media_type="text/html", status_code=404)
        user.email_verified = True
        await session.commit()

    return Response(
        content="<h2>Email verified — you can return to the Sonorus app and log in now.</h2>",
        media_type="text/html",
    )

@app.post("/api/auth/login", tags=["Auth"])
async def login(request: LoginRequest) -> Dict[str, Any]:
    email = request.email.strip().lower()
    rate_key = f"login:{email}"
    if rate_limit.is_locked_out(rate_key):
        wait_s = rate_limit.seconds_until_retry(rate_key)
        raise HTTPException(status_code=429, detail=f"Too many attempts. Try again in {max(1, wait_s // 60)} minute(s).")

    async with async_session_maker() as session:
        result = await session.execute(select(UserORM).where(UserORM.email == email))
        user = result.scalar_one_or_none()

    if not user or not auth_service.verify_password(request.password, user.password_hash):
        rate_limit.record_failure(rate_key)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Verify your email before logging in — check your inbox for the link.")

    rate_limit.clear(rate_key)
    token = auth_service.create_token(user.id, user.email)
    return {"token": token, "user": {"id": user.id, "email": user.email, "name": user.name}}

@app.get("/api/auth/me", tags=["Auth"])
async def get_me(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    return {"id": user["sub"], "email": user["email"]}

class GoogleAuthRequest(BaseModel):
    id_token: str

@app.post("/api/auth/google", tags=["Auth"])
async def google_auth(request: GoogleAuthRequest) -> Dict[str, Any]:
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests

    try:
        idinfo = google_id_token.verify_oauth2_token(
            request.id_token, google_requests.Request(), settings.auth.google_client_id
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    email = (idinfo.get("email") or "").strip().lower()
    google_id = idinfo.get("sub")
    name = idinfo.get("name") or (email.split("@")[0] if email else "Sonorus User")
    if not email or not google_id:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    async with async_session_maker() as session:
        result = await session.execute(select(UserORM).where(UserORM.email == email))
        user = result.scalar_one_or_none()
        if user:
            if not user.google_id:
                user.google_id = google_id
                await session.commit()
                await session.refresh(user)
        else:
            # Google already verified this email as part of its own OAuth
            # flow -- no need to make them verify it again through us.
            user = UserORM(email=email, google_id=google_id, name=name, email_verified=True)
            session.add(user)
            await session.commit()
            await session.refresh(user)

    token = auth_service.create_token(user.id, user.email)
    return {"token": token, "user": {"id": user.id, "email": user.email, "name": user.name}}


# ==========================================
# Mobile app (push-to-talk REST turns)
# ==========================================
from app.services import mobile_turn

class MobileSessionRequest(BaseModel):
    call_type: Optional[str] = None
    customer_id: Optional[str] = None

@app.post("/api/mobile/sessions", tags=["Mobile"])
async def create_mobile_session(request: MobileSessionRequest = None, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Starts a mobile push-to-talk session. For outbound loan-reminder
    sessions, the agent speaks first -- the opening line's text + WAV
    audio (base64) come back immediately in this response."""
    req = request or MobileSessionRequest()
    try:
        session_id, opening_text, opening_wav = await mobile_turn.create_mobile_session(
            req.call_type, req.customer_id, user["sub"]
        )
    except Exception as e:
        logger.error("mobile_session_create_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to start session")
    return {
        "session_id": session_id,
        "opening_text": opening_text,
        "opening_audio_b64": base64.b64encode(opening_wav).decode() if opening_wav else None,
    }

@app.post("/api/mobile/turn", tags=["Mobile"])
async def mobile_turn_endpoint(
    session_id: str = Form(...),
    audio: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """One push-to-talk turn: upload a recorded utterance (m4a/wav/whatever
    the device recorded), get back the transcript, reply text, and reply
    audio (WAV, base64) in one response."""
    audio_bytes = await audio.read()
    content_type = audio.content_type or "audio/mp4"
    try:
        transcript, reply_text, wav_bytes = await mobile_turn.run_mobile_turn(session_id, audio_bytes, content_type)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    except Exception as e:
        logger.error("mobile_turn_failed", error=str(e), session_id=session_id)
        raise HTTPException(status_code=500, detail="Turn failed")
    return {
        "transcript": transcript,
        "reply_text": reply_text,
        "reply_audio_b64": base64.b64encode(wav_bytes).decode() if wav_bytes else None,
    }

@app.delete("/api/mobile/sessions/{session_id}", tags=["Mobile"])
async def end_mobile_session_endpoint(session_id: str, user: dict = Depends(get_current_user)) -> Dict[str, str]:
    await mobile_turn.end_mobile_session(session_id)
    return {"status": "ended"}

@app.get("/api/mobile/history", tags=["Mobile"])
async def get_call_history(user: dict = Depends(get_current_user)) -> list:
    """Past voice sessions for the signed-in user, most recent first --
    each entry has the full transcript, for the mobile app's Call History
    screen."""
    return await mobile_turn.list_call_history(user["sub"])

@app.get("/api/knowledge/documents", tags=["Knowledge"])
async def list_knowledge_documents() -> list:
    """All active knowledge-base chunks -- for the mobile app's knowledge
    base browsing screen (not semantic search, just a plain listing)."""
    from app.db.repositories.knowledge_repo import KnowledgeRepository
    async with async_session_maker() as session:
        repo = KnowledgeRepository(session)
        chunks = await repo.list_all()
    return [
        {"id": c.id, "doc_id": c.doc_id, "title": c.title, "category": c.category, "content": c.content}
        for c in chunks
    ]


@app.get("/sessions/{session_id}", response_model=SessionInfo, tags=["Sessions"])
async def get_session(session_id: str) -> SessionInfo:
    """
    Retrieves information regarding an active or historical conversation session.
    """
    session_info = await session_manager.get_session_info(session_id)
    if not session_info:
        raise HTTPException(status_code=404, detail="Session not found")
    return session_info

@app.delete("/sessions/{session_id}", tags=["Sessions"])
async def end_session(session_id: str) -> Dict[str, str]:
    """
    Gracefully terminates a session and clears its transient cache/connection states.
    """
    session_info = await session_manager.get_session_info(session_id)
    if not session_info:
        raise HTTPException(status_code=404, detail="Session not found")
    
    await session_manager.close_session(session_id)
    return {"status": "terminated", "session_id": session_id}

# ==========================================
# WebSocket Endpoint (Stub for Phase 6)
# ==========================================

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    Bi-directional streaming WebSocket endpoint for raw PCM audio.
    Delegates connection lifecycle handling to SpeechGateway.
    """
    session_info = await session_manager.get_session_info(session_id)
    if not session_info:
        logger.warning("ws_connection_rejected_missing_session", session_id=session_id)
        await websocket.close(code=4004, reason="Session not found")
        return
        
    await websocket.accept()
    await speech_gateway.handle_connection(websocket, session_id)


# ==========================================
# Telemetry and Admin Dashboard Endpoints
# ==========================================
from app.services.telemetry import telemetry_service
from pydantic import BaseModel

class AdminLoginRequest(BaseModel):
    username: str
    password: str

class AuditLogRequest(BaseModel):
    action: str
    details: str

@app.post("/api/telemetry/admin/login")
async def admin_login(request: AdminLoginRequest):
    rate_key = f"admin_login:{request.username}"
    if rate_limit.is_locked_out(rate_key):
        wait_s = rate_limit.seconds_until_retry(rate_key)
        raise HTTPException(status_code=429, detail=f"Too many attempts. Try again in {max(1, wait_s // 60)} minute(s).")

    if request.username == settings.admin.username and settings.admin.password and request.password == settings.admin.password:
        rate_limit.clear(rate_key)
        await telemetry_service.record_event(
            event_type="admin_login",
            status="success",
            payload={"operator": "admin", "action": "login", "details": "Successful admin login"}
        )
        return {"token": "mock-admin-token-777", "status": "authenticated"}
    else:
        rate_limit.record_failure(rate_key)
        await telemetry_service.record_event(
            event_type="admin_login",
            status="error",
            error_message="Invalid credentials attempt",
            payload={"operator": request.username, "action": "login", "details": "Failed admin login attempt"}
        )
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

@app.post("/api/telemetry/audit")
async def log_audit_action(request: AuditLogRequest):
    await telemetry_service.record_event(
        event_type="audit_log",
        payload={"operator": "admin", "action": request.action, "details": request.details}
    )
    return {"status": "logged"}

@app.get("/api/telemetry/overview")
async def get_overview():
    return await telemetry_service.get_overview_metrics()

@app.get("/api/telemetry/live-sessions")
async def get_live_sessions():
    return await telemetry_service.get_live_sessions()

@app.get("/api/telemetry/wellbeing")
async def get_wellbeing():
    return await telemetry_service.get_wellbeing_analytics()

@app.get("/api/telemetry/stress")
async def get_stress():
    return await telemetry_service.get_stress_analytics()

@app.get("/api/telemetry/conversation")
async def get_conversation():
    return await telemetry_service.get_conversation_analytics()

@app.get("/api/telemetry/ai-performance")
async def get_ai_performance():
    return await telemetry_service.get_ai_performance()

@app.get("/api/telemetry/voice-pipeline")
async def get_voice_pipeline():
    return await telemetry_service.get_voice_pipeline_metrics()

@app.get("/api/telemetry/latency")
async def get_latency():
    return await telemetry_service.get_latency_metrics()

@app.get("/api/telemetry/alerts")
async def get_alerts():
    return await telemetry_service.get_alerts()

@app.get("/api/telemetry/audit-logs")
async def get_audit_logs():
    return await telemetry_service.get_audit_logs()
