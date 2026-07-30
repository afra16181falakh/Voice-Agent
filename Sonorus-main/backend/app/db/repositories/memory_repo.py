import structlog
from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert

from app.core.interfaces.memory import IMemoryRepository
from app.core.models import MemoryItem, TranscriptSegment, MemoryType, Speaker
from app.db.schema import HistorySegmentORM, MemoryItemORM

logger = structlog.get_logger(__name__)


class PostgresMemoryRepository(IMemoryRepository):
    """
    Implements IMemoryRepository against PostgreSQL using SQLAlchemy async sessions.
    Handles conversation history logs and long-term user memory storage.
    pgvector similarity search is attempted if extension is available.
    """

    def __init__(self, db: AsyncSession):
        self._db = db

    async def save_memory_item(self, session_id: str, item: MemoryItem) -> None:
        """Persists a single MemoryItem to the user_memories table."""
        try:
            orm_obj = MemoryItemORM(
                id=item.id,
                session_id=session_id,
                memory_type=item.memory_type.value,
                key=item.key,
                value=item.value,
                embedding=item.embedding,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            self._db.add(orm_obj)
            await self._db.flush()
        except Exception as e:
            logger.error(
                "db_save_memory_item_failed",
                error=str(e),
                session_id=session_id,
                key=item.key
            )
            raise

    async def get_memories_by_type(
        self, session_id: str, memory_type: MemoryType
    ) -> List[MemoryItem]:
        """Retrieves all memories for a session filtered by MemoryType."""
        try:
            stmt = select(MemoryItemORM).where(
                MemoryItemORM.session_id == session_id,
                MemoryItemORM.memory_type == memory_type.value
            )
            result = await self._db.execute(stmt)
            rows = result.scalars().all()
            return [self._orm_to_model(row) for row in rows]
        except Exception as e:
            logger.error(
                "db_get_memories_by_type_failed",
                error=str(e),
                session_id=session_id
            )
            return []

    async def search_semantic_memories(
        self,
        session_id: str,
        query_embedding: List[float],
        limit: int = 5
    ) -> List[MemoryItem]:
        """
        Performs cosine similarity search using pgvector.
        Falls back to empty list if pgvector is not installed.
        """
        try:
            # pgvector operator <=> = cosine distance
            stmt = (
                select(MemoryItemORM)
                .where(
                    MemoryItemORM.session_id == session_id,
                    MemoryItemORM.embedding.isnot(None)
                )
                .order_by(MemoryItemORM.embedding.op("<=>")(query_embedding))
                .limit(limit)
            )
            result = await self._db.execute(stmt)
            rows = result.scalars().all()
            return [self._orm_to_model(row) for row in rows]
        except Exception as e:
            logger.debug(
                "pgvector_search_unavailable",
                reason=str(e),
                session_id=session_id
            )
            return []

    async def save_history_segment(
        self, session_id: str, segment: TranscriptSegment
    ) -> None:
        """Saves a single transcript turn to conversation_history table."""
        try:
            orm_obj = HistorySegmentORM(
                session_id=session_id,
                speaker=segment.speaker.value,
                text=segment.text,
                timestamp=segment.timestamp,
            )
            self._db.add(orm_obj)
            await self._db.flush()
        except Exception as e:
            logger.error(
                "db_save_history_segment_failed",
                error=str(e),
                session_id=session_id
            )
            raise

    async def get_history(
        self, session_id: str, limit: int = 50
    ) -> List[TranscriptSegment]:
        """Retrieves conversation history from the database, most recent first."""
        try:
            stmt = (
                select(HistorySegmentORM)
                .where(HistorySegmentORM.session_id == session_id)
                .order_by(HistorySegmentORM.timestamp.desc())
                .limit(limit)
            )
            result = await self._db.execute(stmt)
            rows = result.scalars().all()
            # Reverse to chronological order
            return [self._history_orm_to_model(row) for row in reversed(rows)]
        except Exception as e:
            logger.error(
                "db_get_history_failed",
                error=str(e),
                session_id=session_id
            )
            return []

    def _orm_to_model(self, row: MemoryItemORM) -> MemoryItem:
        return MemoryItem(
            id=row.id,
            memory_type=MemoryType(row.memory_type),
            key=row.key,
            value=row.value,
            embedding=row.embedding,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _history_orm_to_model(self, row: HistorySegmentORM) -> TranscriptSegment:
        return TranscriptSegment(
            speaker=Speaker(row.speaker),
            text=row.text,
            timestamp=row.timestamp,
            is_final=True,
        )
