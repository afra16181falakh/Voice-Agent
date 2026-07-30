from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from app.core.models import MemoryItem, TranscriptSegment, MemoryType

class IMemoryRepository(ABC):
    """
    Interface for persistence of memories and history (e.g. PostgreSQL + pgvector).
    """
    
    @abstractmethod
    async def save_memory_item(self, session_id: str, item: MemoryItem) -> None:
        """Persists a single memory item to long-term database storage."""
        pass
        
    @abstractmethod
    async def get_memories_by_type(self, session_id: str, memory_type: MemoryType) -> List[MemoryItem]:
        """Retrieves memories filtered by type (e.g. preferences, personal details)."""
        pass
        
    @abstractmethod
    async def search_semantic_memories(self, session_id: str, query_embedding: List[float], limit: int = 5) -> List[MemoryItem]:
        """Performs pgvector similarity search on stored semantic memories."""
        pass

    @abstractmethod
    async def save_history_segment(self, session_id: str, segment: TranscriptSegment) -> None:
        """Saves a single transcript segment to session history."""
        pass

    @abstractmethod
    async def get_history(self, session_id: str, limit: int = 50) -> List[TranscriptSegment]:
        """Retrieves full conversation history logs for a session."""
        pass


class IMemoryManager(ABC):
    """
    High-level memory orchestrator coordinating short-term caching,
    long-term SQL databases, and vector similarity retrieval.
    """
    
    @abstractmethod
    async def record_utterance(self, session_id: str, segment: TranscriptSegment) -> None:
        """Stores a new dialogue segment in short-term and conversation history."""
        pass

    @abstractmethod
    async def get_working_memory(self, session_id: str) -> List[TranscriptSegment]:
        """Fetches the active context (short-term conversation history)."""
        pass

    @abstractmethod
    async def retrieve_contextual_memories(self, session_id: str, query_text: str) -> List[MemoryItem]:
        """Uses embeddings to query and retrieve semantically relevant memories."""
        pass

    @abstractmethod
    async def save_user_fact(self, session_id: str, key: str, value: str, is_preference: bool = False) -> None:
        """Extracts and saves a key-value fact about the user (e.g. name, work, preference)."""
        pass

    @abstractmethod
    async def load_user_profile(self, session_id: str) -> Dict[str, Any]:
        """Gets all preferences, personal information, and profile parameters."""
        pass

    @abstractmethod
    async def clear_session_memory(self, session_id: str) -> None:
        """Clears short-term active caches for a session."""
        pass
