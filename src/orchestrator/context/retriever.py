"""pgvector cosine similarity retrieval — arch doc §27-28 / tasks.md 4.4."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.db.models import DocumentChunk

DEFAULT_TOP_K = 10


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    chunk_index: int
    distance: float
    metadata: dict

    @property
    def similarity(self) -> float:
        """Cosine similarity in [0, 2] -> [1, -1]; clamped to [0, 1] for display."""
        return max(0.0, 1.0 - self.distance)


async def retrieve_chunks(
    session: AsyncSession,
    query_embedding: list[float],
    *,
    top_k: int = DEFAULT_TOP_K,
    document_id: uuid.UUID | None = None,
) -> list[RetrievedChunk]:
    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    stmt = select(DocumentChunk, distance.label("distance")).where(
        DocumentChunk.embedding.is_not(None)
    )
    if document_id is not None:
        stmt = stmt.where(DocumentChunk.document_id == document_id)
    stmt = stmt.order_by(distance).limit(top_k)

    result = await session.execute(stmt)
    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            content=chunk.content,
            chunk_index=chunk.chunk_index,
            distance=float(dist),
            metadata=chunk.metadata_,
        )
        for chunk, dist in result.all()
    ]
