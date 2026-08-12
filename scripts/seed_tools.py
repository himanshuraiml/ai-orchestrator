"""Seed the `tools` / `tool_capabilities` tables from configs/tools.yaml.

Usage: uv run python scripts/seed_tools.py
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.config.settings import load_tool_profiles
from orchestrator.db.models import Tool, ToolCapability
from orchestrator.db.session import get_sessionmaker
from orchestrator.domain.tools import ToolProfile


async def upsert_tool(session: AsyncSession, profile: ToolProfile) -> Tool:
    tool = await session.get(Tool, profile.id)
    if tool is None:
        tool = Tool(id=profile.id)
        session.add(tool)

    tool.name = profile.name
    tool.risk_level = profile.risk_level
    tool.requires_network = profile.requires_network
    tool.requires_filesystem = profile.requires_filesystem
    tool.requires_approval = profile.requires_approval

    await session.flush()

    existing = await session.execute(
        select(ToolCapability.capability).where(ToolCapability.tool_id == profile.id)
    )
    existing_caps = {row[0] for row in existing.all()}
    for capability in profile.capabilities - existing_caps:
        session.add(ToolCapability(tool_id=profile.id, capability=capability))
    for capability in existing_caps - profile.capabilities:
        stmt = select(ToolCapability).where(
            ToolCapability.tool_id == profile.id, ToolCapability.capability == capability
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            await session.delete(row)

    await session.flush()
    return tool


async def main() -> None:
    profiles = load_tool_profiles()
    async with get_sessionmaker()() as session:
        for profile in profiles:
            await upsert_tool(session, profile)
        await session.commit()
    print(f"Seeded {len(profiles)} tools.")


if __name__ == "__main__":
    asyncio.run(main())
