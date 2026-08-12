from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from orchestrator.api.middleware import RequestContextMiddleware
from orchestrator.api.routes import health, tasks
from orchestrator.api.routes.tasks import DEFAULT_USER_ID
from orchestrator.config.logging import configure_logging
from orchestrator.config.settings import get_settings
from orchestrator.db.models import User
from orchestrator.db.session import get_sessionmaker


async def _ensure_default_user() -> None:
    async with get_sessionmaker()() as session:
        user = await session.get(User, DEFAULT_USER_ID)
        if user is None:
            session.add(User(id=DEFAULT_USER_ID, email="local@orchestrator.local"))
            await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    await _ensure_default_user()
    app.state.arq_pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        yield
    finally:
        await app.state.arq_pool.close()


app = FastAPI(
    title="AI Orchestrator",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)

app.include_router(health.router)
app.include_router(tasks.router)


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
