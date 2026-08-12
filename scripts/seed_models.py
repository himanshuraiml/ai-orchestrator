"""Seed the `models` / `model_capabilities` tables from configs/models.yaml.

Usage: uv run python scripts/seed_models.py
"""
import asyncio

from orchestrator.config.settings import load_model_profiles
from orchestrator.db.repositories.models import upsert_model
from orchestrator.db.session import get_sessionmaker


async def main() -> None:
    profiles = load_model_profiles()
    async with get_sessionmaker()() as session:
        for profile in profiles:
            await upsert_model(session, profile)
        await session.commit()
    print(f"Seeded {len(profiles)} models.")


if __name__ == "__main__":
    asyncio.run(main())
