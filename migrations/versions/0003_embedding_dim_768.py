"""embedding dim 1536->768: align pgvector columns with nomic-embed-text
(the local/default embedder - tasks.md Phase 4.3), add HNSW cosine index
for document_chunks retrieval

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-12

"""
from collections.abc import Sequence

from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_DIM = 1536
NEW_DIM = 768


def upgrade() -> None:
    # No rows exist yet in either table at this point in the project, so a
    # plain type change (no USING cast) is sufficient.
    op.alter_column(
        "document_chunks", "embedding", type_=Vector(NEW_DIM), postgresql_using="NULL"
    )
    op.alter_column("lessons", "embedding", type_=Vector(NEW_DIM), postgresql_using="NULL")

    op.execute(
        "CREATE INDEX idx_document_chunks_embedding_hnsw ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_document_chunks_embedding_hnsw")
    op.alter_column(
        "document_chunks", "embedding", type_=Vector(OLD_DIM), postgresql_using="NULL"
    )
    op.alter_column("lessons", "embedding", type_=Vector(OLD_DIM), postgresql_using="NULL")
