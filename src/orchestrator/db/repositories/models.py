from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.db.models import Model, ModelCapability
from orchestrator.domain.models import ModelProfile


async def list_models(session: AsyncSession, *, enabled_only: bool = True) -> list[Model]:
    stmt = select(Model)
    if enabled_only:
        stmt = stmt.where(Model.enabled.is_(True))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_model(session: AsyncSession, model_id: str) -> Model | None:
    return await session.get(Model, model_id)


async def upsert_model(session: AsyncSession, profile: ModelProfile) -> Model:
    model = await session.get(Model, profile.id)
    if model is None:
        model = Model(id=profile.id)
        session.add(model)

    model.provider = profile.provider
    model.model_name = profile.model_name
    model.context_window = profile.context_window
    model.quality_score = profile.quality_score
    model.cost_score = profile.cost_score
    model.latency_score = profile.latency_score
    model.privacy_class = profile.privacy_class
    model.enabled = profile.enabled

    await session.flush()

    existing = await session.execute(
        select(ModelCapability.capability).where(ModelCapability.model_id == profile.id)
    )
    existing_caps = {row[0] for row in existing.all()}
    for capability in profile.capabilities - existing_caps:
        session.add(ModelCapability(model_id=profile.id, capability=capability))
    for capability in existing_caps - profile.capabilities:
        stmt = select(ModelCapability).where(
            ModelCapability.model_id == profile.id, ModelCapability.capability == capability
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            await session.delete(row)

    await session.flush()
    return model
