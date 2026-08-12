import uuid
import structlog
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, Float

from app.core.models import KnowledgeChunk
from app.db.schema import KnowledgeChunkORM

logger = structlog.get_logger(__name__)


class KnowledgeRepository:
    """
    General-purpose business knowledge base -- NOT session-scoped, shared
    across all conversations. Same pgvector cosine-similarity pattern as
    PostgresMemoryRepository.search_semantic_memories, applied to a
    dedicated table instead of reusing the per-session memory one.
    """

    def __init__(self, db: AsyncSession):
        self._db = db

    async def upsert_document(
        self, doc_id: str, title: str, category: Optional[str], chunks: List[str], embeddings: List[Optional[List[float]]]
    ) -> None:
        """Replaces all chunks for doc_id with the given content -- simple
        re-ingest-whole-doc semantics, no partial-chunk diffing needed at
        this scale."""
        try:
            await self._db.execute(delete(KnowledgeChunkORM).where(KnowledgeChunkORM.doc_id == doc_id))
            for idx, (content, embedding) in enumerate(zip(chunks, embeddings)):
                self._db.add(KnowledgeChunkORM(
                    id=str(uuid.uuid4()),
                    doc_id=doc_id,
                    title=title,
                    category=category,
                    chunk_index=idx,
                    content=content,
                    embedding=embedding,
                    is_active=True,
                ))
            await self._db.flush()
        except Exception as e:
            logger.error("db_upsert_knowledge_document_failed", error=str(e), doc_id=doc_id)
            raise

    async def search(self, query_embedding: List[float], limit: int = 3, max_distance: float = 0.3) -> List[KnowledgeChunk]:
        """Cosine similarity search (pgvector <=>) over active chunks.
        Falls back to empty list if pgvector/DB is unavailable -- callers
        (knowledge.py::retrieve_kb_context) already treat that as
        "no KB context this turn", not an error.

        max_distance excludes genuinely irrelevant chunks rather than always
        returning the top-`limit` regardless of relevance -- without it, a
        small KB (few chunks total) returns every chunk for every query,
        which measurably confused the LLM (an unrelated "talk to a human"
        chunk riding along on a plain hours question triggered an
        unwarranted escalation). Threshold picked from real measured
        distances against the 3 seeded chunks: a query's true match landed
        0.22-0.29, its second-closest (a different topic, but still
        generically FAQ-shaped text) landed 0.33-0.35, and a genuine
        mismatch landed 0.44+. 0.4 initially seemed safe but still let that
        0.33-0.35 near-miss through; 0.3 cleanly isolates just the true
        match across all 4 measured queries.
        """
        try:
            distance_expr = KnowledgeChunkORM.embedding.op("<=>", return_type=Float)(query_embedding)
            stmt = (
                select(KnowledgeChunkORM)
                .where(
                    KnowledgeChunkORM.is_active.is_(True),
                    KnowledgeChunkORM.embedding.isnot(None),
                    distance_expr < max_distance,
                )
                .order_by(distance_expr)
                .limit(limit)
            )
            result = await self._db.execute(stmt)
            rows = result.scalars().all()
            return [self._orm_to_model(row) for row in rows]
        except Exception as e:
            logger.debug("knowledge_search_unavailable", reason=str(e))
            return []

    async def has_any_chunks(self) -> bool:
        stmt = select(KnowledgeChunkORM.id).limit(1)
        result = await self._db.execute(stmt)
        return result.scalar() is not None

    async def list_all(self) -> List[KnowledgeChunk]:
        """All active chunks, ordered by doc then chunk index -- used by the
        mobile app's knowledge-base browsing screen (not semantic search)."""
        stmt = (
            select(KnowledgeChunkORM)
            .where(KnowledgeChunkORM.is_active.is_(True))
            .order_by(KnowledgeChunkORM.doc_id, KnowledgeChunkORM.chunk_index)
        )
        result = await self._db.execute(stmt)
        return [self._orm_to_model(row) for row in result.scalars().all()]

    def _orm_to_model(self, row: KnowledgeChunkORM) -> KnowledgeChunk:
        return KnowledgeChunk(
            id=row.id,
            doc_id=row.doc_id,
            title=row.title,
            category=row.category,
            chunk_index=row.chunk_index,
            content=row.content,
            embedding=row.embedding,
            is_active=row.is_active,
        )
