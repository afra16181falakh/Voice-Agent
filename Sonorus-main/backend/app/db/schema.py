import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Integer, ARRAY, Float
from app.db.connection import Base

# Safe import for pgvector
try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False

class UserORM(Base):
    """
    Mobile app user accounts -- email + password, or Google sign-in.
    Google-only accounts have no password_hash (nullable).
    """
    __tablename__ = "users"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=True)
    google_id = Column(String(100), nullable=True, unique=True, index=True)
    name = Column(String(200), nullable=False)
    email_verified = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CallHistoryORM(Base):
    """
    Per-user record of past mobile app voice sessions, for the "Call
    History" screen -- separate from HistorySegmentORM (which logs raw
    per-turn transcript rows for the web app's WebSocket sessions) since
    this is per-session, user-scoped, and stores the whole transcript as
    one JSON blob rather than one row per utterance.
    """
    __tablename__ = "call_history"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(50), nullable=False, index=True)
    session_id = Column(String(100), nullable=False)
    call_type = Column(String(50), nullable=True)
    customer_name = Column(String(200), nullable=True)
    transcript_json = Column(Text, nullable=False, default="[]")
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)


class HistorySegmentORM(Base):
    """
    SQLAlchemy table schema for logging conversation turn transcripts.
    """
    __tablename__ = "conversation_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, index=True)
    speaker = Column(String(50), nullable=False)
    text = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)


class MemoryItemORM(Base):
    """
    SQLAlchemy table schema for storing facts, preferences, and semantic vector memories.
    """
    __tablename__ = "user_memories"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(100), nullable=False, index=True)
    memory_type = Column(String(50), nullable=False, index=True)
    key = Column(String(200), nullable=False)
    value = Column(Text, nullable=False)
    
    # Store 1536-dimensional embeddings (e.g. text-embedding-004 from Gemini API)
    if HAS_PGVECTOR:
        embedding = Column(Vector(1536), nullable=True)
    else:
        embedding = Column(ARRAY(Float), nullable=True)
        
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class TelemetryEventORM(Base):
    """
    SQLAlchemy table schema for storing telemetry metric events, pipeline stages,
    wellbeing/stress analytics, alerts, and audit logs.
    """
    __tablename__ = "telemetry_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=True, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    stage_name = Column(String(100), nullable=True, index=True)
    latency_ms = Column(Float, nullable=True)
    status = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    payload = Column(Text, nullable=True)  # Store JSON stringified payload
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
