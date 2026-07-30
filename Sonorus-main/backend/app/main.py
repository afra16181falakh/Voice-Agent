import structlog
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Dict, Any

from app.config import settings
from app.logging import setup_logging
from app.db.connection import init_db
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
    if request.username == "admin" and request.password == "SonorusDashboard22":
        await telemetry_service.record_event(
            event_type="admin_login",
            status="success",
            payload={"operator": "admin", "action": "login", "details": "Successful admin login"}
        )
        return {"token": "mock-admin-token-777", "status": "authenticated"}
    else:
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
