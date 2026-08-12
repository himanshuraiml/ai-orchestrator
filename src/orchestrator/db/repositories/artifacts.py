import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.db.models import Artifact


async def create_artifact(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    mime_type: str,
    storage_uri: str,
    task_id: uuid.UUID | None = None,
    size_bytes: int | None = None,
    checksum: str | None = None,
    metadata: dict | None = None,
) -> Artifact:
    artifact = Artifact(
        user_id=user_id,
        task_id=task_id,
        name=name,
        mime_type=mime_type,
        storage_uri=storage_uri,
        size_bytes=size_bytes,
        checksum=checksum,
        metadata_=metadata or {},
    )
    session.add(artifact)
    await session.flush()
    return artifact


async def get_artifact(session: AsyncSession, artifact_id: uuid.UUID) -> Artifact | None:
    return await session.get(Artifact, artifact_id)


async def list_artifacts_for_task(session: AsyncSession, task_id: uuid.UUID) -> list[Artifact]:
    result = await session.execute(select(Artifact).where(Artifact.task_id == task_id))
    return list(result.scalars().all())
