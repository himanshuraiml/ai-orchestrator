import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.db.models import Document, DocumentChunk


async def create_document(
    session: AsyncSession,
    *,
    artifact_id: uuid.UUID,
    parser: str | None = None,
    page_count: int | None = None,
    extracted_text: str | None = None,
    metadata: dict | None = None,
) -> Document:
    document = Document(
        artifact_id=artifact_id,
        parser=parser,
        page_count=page_count,
        extracted_text=extracted_text,
        metadata_=metadata or {},
    )
    session.add(document)
    await session.flush()
    return document


async def get_document(session: AsyncSession, document_id: uuid.UUID) -> Document | None:
    return await session.get(Document, document_id)


async def create_chunks(
    session: AsyncSession,
    *,
    document_id: uuid.UUID,
    chunks: list[str],
    embeddings: list[list[float]],
    page_start: int | None = None,
    page_end: int | None = None,
) -> list[DocumentChunk]:
    rows = [
        DocumentChunk(
            document_id=document_id,
            chunk_index=index,
            content=content,
            page_start=page_start,
            page_end=page_end,
            embedding=embedding,
        )
        for index, (content, embedding) in enumerate(zip(chunks, embeddings, strict=True))
    ]
    session.add_all(rows)
    await session.flush()
    return rows


async def list_chunks_for_document(
    session: AsyncSession, document_id: uuid.UUID
) -> list[DocumentChunk]:
    result = await session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list(result.scalars().all())
