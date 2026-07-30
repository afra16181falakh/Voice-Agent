import uuid
import structlog
from datetime import datetime
from typing import Dict, Any, Optional
from app.core.models import SessionInfo, ConversationState
from app.core.state import ConversationStateMachine

logger = structlog.get_logger(__name__)

class ActiveSession:
    """
    Represents an active, in-memory conversation session state.
    """
    def __init__(self, session_id: str):
        self.info = SessionInfo(session_id=session_id)
        self.state_machine = ConversationStateMachine(session_id)
        self.connection: Optional[Any] = None
        self.metadata: Dict[str, Any] = {}


class SessionManager:
    """
    Manages session lifecycles, active WebSocket connections,
    and associated Conversation State Machines.
    """

    def __init__(self):
        self._sessions: Dict[str, ActiveSession] = {}

    async def create_session(self) -> SessionInfo:
        """Creates a new session and returns its basic info."""
        session_id = str(uuid.uuid4())
        active_session = ActiveSession(session_id)
        self._sessions[session_id] = active_session
        
        logger.info("session_created", session_id=session_id)
        return active_session.info

    async def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """Gets info for a given session."""
        session = self._sessions.get(session_id)
        if not session:
            return None
        return session.info

    async def get_state_machine(self, session_id: str) -> Optional[ConversationStateMachine]:
        """Gets the state machine associated with the session."""
        session = self._sessions.get(session_id)
        if not session:
            return None
        return session.state_machine

    async def register_connection(self, session_id: str, connection: Any) -> None:
        """Registers a connection object (e.g. WebSocket connection) for the session."""
        session = self._sessions.get(session_id)
        if session:
            session.connection = connection
            logger.info("connection_registered", session_id=session_id)
        else:
            logger.warning("attempted_register_connection_on_missing_session", session_id=session_id)

    async def get_connection(self, session_id: str) -> Optional[Any]:
        """Gets the active connection for the session."""
        session = self._sessions.get(session_id)
        if not session:
            return None
        return session.connection

    async def close_session(self, session_id: str) -> None:
        """Closes and cleans up session resources."""
        session = self._sessions.pop(session_id, None)
        if session:
            session.info.is_active = False
            session.info.end_time = datetime.utcnow()
            # Clean up connection
            session.connection = None
            logger.info("session_closed", session_id=session_id)
