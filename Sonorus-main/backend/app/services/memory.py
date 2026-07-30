import json
import structlog
from datetime import datetime
from collections import deque
from typing import Dict, List, Optional, Any, Deque

from app.core.interfaces.memory import IMemoryManager
from app.core.models import (
    MemoryItem, TranscriptSegment, MemoryType, Speaker
)
from app.db.connection import async_session_maker
from app.db.repositories.memory_repo import PostgresMemoryRepository

logger = structlog.get_logger(__name__)

# Max turns held in short-term working memory per session
SHORT_TERM_MAX_TURNS = 15


class InMemoryShortTermCache:
    """
    Per-session short-term memory backed by an in-process deque.
    Holds the last N transcript segments for immediate context injection.
    """

    def __init__(self):
        self._sessions: Dict[str, Deque[TranscriptSegment]] = {}

    def _get(self, session_id: str) -> Deque[TranscriptSegment]:
        if session_id not in self._sessions:
            self._sessions[session_id] = deque(maxlen=SHORT_TERM_MAX_TURNS)
        return self._sessions[session_id]

    def push(self, session_id: str, segment: TranscriptSegment) -> None:
        self._get(session_id).append(segment)

    def get_all(self, session_id: str) -> List[TranscriptSegment]:
        return list(self._get(session_id))

    def clear(self, session_id: str) -> None:
        if session_id in self._sessions:
            del self._sessions[session_id]


class MemoryManager(IMemoryManager):
    """
    Orchestrates all memory tiers:
      - Short-term: in-process deque (last N turns)
      - Conversation history: persisted to PostgreSQL via repository
      - Long-term facts / preferences: persisted via repository + retrieved by key
      - Semantic search: pgvector cosine similarity (graceful no-op if unavailable)
    """

    def __init__(self):
        self._short_term = InMemoryShortTermCache()
        self._user_facts: Dict[str, Dict[str, str]] = {}  # session_id -> {key: value}

    async def record_utterance(
        self, session_id: str, segment: TranscriptSegment
    ) -> None:
        """Stores a new dialogue segment in short-term cache only.

        Intentionally does NOT persist raw per-turn text to Postgres — that
        would grow the conversation_history table one row per turn. Durable
        memory is written in condensed form instead (see save_summary())."""
        self._short_term.push(session_id, segment)

    async def get_working_memory(self, session_id: str) -> List[TranscriptSegment]:
        """Fetches the active working context (last N turns) from short-term cache."""
        return self._short_term.get_all(session_id)

    async def retrieve_contextual_memories(
        self, session_id: str, query_text: str
    ) -> List[MemoryItem]:
        """
        Attempts semantic retrieval from PostgreSQL via pgvector.
        Falls back to condensed session summaries if pgvector/DB is unavailable.
        Never raises — a down/unreachable DB degrades to an empty result.
        """
        try:
            # Attempt semantic search — returns empty list if pgvector not installed
            embedding = await self._get_dummy_embedding(query_text)
            if embedding:
                async with async_session_maker() as db:
                    repo = PostgresMemoryRepository(db)
                    return await repo.search_semantic_memories(session_id, embedding, limit=5)
        except Exception as e:
            logger.debug(
                "semantic_search_unavailable",
                reason=str(e),
                session_id=session_id
            )

        # Fallback: return condensed summaries for this session
        try:
            async with async_session_maker() as db:
                repo = PostgresMemoryRepository(db)
                return await repo.get_memories_by_type(session_id, MemoryType.SUMMARY)
        except Exception as e:
            logger.warning(
                "failed_retrieving_contextual_memories",
                error=str(e),
                session_id=session_id
            )
            return []

    async def save_user_fact(
        self,
        session_id: str,
        key: str,
        value: str,
        is_preference: bool = False
    ) -> None:
        """Saves a discovered user fact (name, occupation, preference, etc.)."""
        # In-process store for immediate recall this session
        if session_id not in self._user_facts:
            self._user_facts[session_id] = {}
        self._user_facts[session_id][key] = value

        memory_type = MemoryType.PREFERENCE if is_preference else MemoryType.PERSONAL_INFO
        item = MemoryItem(memory_type=memory_type, key=key, value=value)
        try:
            async with async_session_maker() as db:
                repo = PostgresMemoryRepository(db)
                await repo.save_memory_item(session_id, item)
                await db.commit()
            logger.debug(
                "user_fact_saved",
                key=key,
                memory_type=memory_type.value,
                session_id=session_id
            )
        except Exception as e:
            logger.warning(
                "failed_persisting_user_fact",
                key=key,
                error=str(e),
                session_id=session_id
            )

    async def save_summary(self, session_id: str, summary_text: str) -> None:
        """
        Persists a condensed, multi-turn summary as a single MemoryItem
        (MemoryType.SUMMARY) instead of storing every raw turn — keeps the
        DB compact regardless of how long a session runs.
        """
        if not summary_text or not summary_text.strip():
            return

        item = MemoryItem(
            memory_type=MemoryType.SUMMARY,
            key="conversation_summary",
            value=summary_text,
        )
        try:
            async with async_session_maker() as db:
                repo = PostgresMemoryRepository(db)
                await repo.save_memory_item(session_id, item)
                await db.commit()
            logger.debug("conversation_summary_saved", session_id=session_id, length=len(summary_text))
        except Exception as e:
            logger.warning(
                "failed_persisting_conversation_summary",
                error=str(e),
                session_id=session_id
            )

    async def load_user_profile(self, session_id: str) -> Dict[str, Any]:
        """Returns all in-memory user facts and preferences for this session."""
        return self._user_facts.get(session_id, {})

    async def clear_session_memory(self, session_id: str) -> None:
        """Clears short-term caches for a terminated session."""
        self._short_term.clear(session_id)
        self._user_facts.pop(session_id, None)
        logger.info("session_memory_cleared", session_id=session_id)

    async def build_context_block(self, session_id: str, query_text: str = "") -> str:
        """
        Assembles a single structured text block for injection into the Gemini prompt.
        Includes: working memory (recent turns) + user facts + retrieved memories.
        """
        parts: List[str] = []

        # 1. User profile facts
        profile = await self.load_user_profile(session_id)
        if profile:
            facts = "; ".join(f"{k}={v}" for k, v in profile.items())
            parts.append(f"[Known about user: {facts}]")

        # 2. Short-term working memory (recent dialogue)
        working_memory = await self.get_working_memory(session_id)
        if working_memory:
            history_lines = []
            for seg in working_memory:
                speaker_label = "User" if seg.speaker == Speaker.USER else "Sonorus"
                history_lines.append(f"{speaker_label}: {seg.text}")
            parts.append("[Recent conversation:\n" + "\n".join(history_lines) + "]")

        # 3. Semantically relevant long-term memories
        if query_text:
            relevant = await self.retrieve_contextual_memories(session_id, query_text)
            if relevant:
                memories_text = "; ".join(m.value for m in relevant[:3])
                parts.append(f"[Relevant memories: {memories_text}]")

        return "\n".join(parts)

    async def _get_dummy_embedding(self, text: str) -> Optional[List[float]]:
        """
        Placeholder for real embedding generation.
        In Phase 9+ this will call the Gemini Embedding API.
        Returns None to gracefully skip pgvector search for now.
        """
        return None  # Will be replaced with real embedding call
