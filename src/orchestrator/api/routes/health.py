from fastapi import APIRouter
from sqlalchemy import text

from orchestrator.db.session import get_engine
from orchestrator.providers.health import check_all

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict:
    checks: dict[str, bool] = {}

    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:  # noqa: BLE001 — any failure means "not ready", not a crash
        checks["database"] = False

    provider_health = await check_all()
    checks.update({name: h.available for name, h in provider_health.items()})

    ready_status = checks["database"]
    return {"status": "ready" if ready_status else "not_ready", "checks": checks}
