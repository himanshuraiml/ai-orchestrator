import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.db.models import Task


async def create_task(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    goal: str,
    requirements: dict,
    project_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    task_type: str | None = None,
    status: str = "pending",
) -> Task:
    task = Task(
        user_id=user_id,
        project_id=project_id,
        session_id=session_id,
        goal=goal,
        task_type=task_type,
        requirements=requirements,
        status=status,
    )
    session.add(task)
    await session.flush()
    return task


async def get_task(session: AsyncSession, task_id: uuid.UUID) -> Task | None:
    return await session.get(Task, task_id)


async def update_status(
    session: AsyncSession,
    task_id: uuid.UUID,
    status: str,
    *,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> None:
    task = await session.get(Task, task_id)
    if task is None:
        return
    task.status = status
    if started_at is not None:
        task.started_at = started_at
    if completed_at is not None:
        task.completed_at = completed_at


async def list_tasks_for_user(
    session: AsyncSession, user_id: uuid.UUID, *, limit: int = 50
) -> list[Task]:
    result = await session.execute(
        select(Task).where(Task.user_id == user_id).order_by(Task.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


def now() -> datetime:
    return datetime.now(UTC)
