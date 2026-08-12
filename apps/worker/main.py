"""Arq worker process main entrypoint.

Executes asynchronous background workflow tasks dispatched by the API process.
"""

from typing import Any, ClassVar

import redis.asyncio as aioredis
from arq.connections import RedisSettings
from structlog import get_logger

from orchestrator.config.settings import get_settings, load_model_profiles
from orchestrator.db.session import get_sessionmaker
from orchestrator.domain.tasks import TaskRequest
from orchestrator.orchestration.executor import (
    DocumentExecutor,
    LLMExecutor,
    PythonExecutor,
    ToolExecutor,
)
from orchestrator.orchestration.orchestrator import EventBroadcaster, Orchestrator
from orchestrator.orchestration.planner import AutonomousPlanner
from orchestrator.orchestration.scheduler import StepScheduler
from orchestrator.providers.litellm_gateway import LiteLLMGateway
from orchestrator.providers.local_gateway import LocalGateway
from orchestrator.routing.policies import PolicyEngine
from orchestrator.routing.router import ModelRouter
from orchestrator.routing.scoring import ModelScorer
from orchestrator.tools.adapters.browser import BrowserAdapter
from orchestrator.tools.adapters.filesystem import FilesystemAdapter
from orchestrator.tools.adapters.ocr import OCRAdapter
from orchestrator.tools.adapters.pandoc import PandocAdapter
from orchestrator.tools.adapters.python import PythonAdapter
from orchestrator.tools.mcp_client import MCPToolClient
from orchestrator.tools.permissions import ToolPermissions
from orchestrator.tools.registry import ToolRegistry
from orchestrator.tools.router import ToolRouter

logger = get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    """Initialize worker dependencies, gateways, executors, DB session, and orchestrator."""
    settings = get_settings()

    # 1. DB Session Factory
    db_session_factory = get_sessionmaker()
    ctx["db_session_factory"] = db_session_factory

    # 2. Gateways & Model Registry
    litellm_gateway = LiteLLMGateway()
    local_gateway = LocalGateway(settings.ollama_base_url)

    def gateway_resolver(provider: str):
        return local_gateway if provider == "ollama" else litellm_gateway

    model_profiles = load_model_profiles()
    model_registry = {m.id: m for m in model_profiles}

    policy_engine = PolicyEngine()
    model_router = ModelRouter(model_profiles, ModelScorer(), policy_engine)

    # 3. Tools & Adapters
    tool_registry = ToolRegistry()
    # Not directly consumed here — ToolRouter/ToolExecutor already enforce
    # policy per call. Exposed via ctx for callers (e.g. future admin/UI
    # endpoints) that need to list what's currently allowed.
    ctx["tool_permissions"] = ToolPermissions(tool_registry, policy_engine)
    tool_router = ToolRouter(tool_registry.list_profiles(), policy_engine)

    mcp_client = MCPToolClient()
    python_adapter = PythonAdapter(mcp_client)
    ocr_adapter = OCRAdapter(mcp_client)
    pandoc_adapter = PandocAdapter(mcp_client)
    fs_adapter = FilesystemAdapter()
    browser_adapter = BrowserAdapter()

    adapters = {
        "python": python_adapter,
        "ocr": ocr_adapter,
        "pandoc": pandoc_adapter,
        "filesystem": fs_adapter,
        "browser": browser_adapter,
    }

    # 4. Executors
    llm_executor = LLMExecutor(gateway_resolver, model_registry)
    tool_executor = ToolExecutor(adapters, tool_router)
    python_executor = PythonExecutor(python_adapter)
    document_executor = DocumentExecutor(ocr_adapter, pandoc_adapter)

    executors = {
        "llm": llm_executor,
        "tool": tool_executor,
        "python": python_executor,
        "document": document_executor,
    }

    scheduler = StepScheduler(executors=executors, default_executor=llm_executor)
    planner = AutonomousPlanner(gateway=local_gateway, planner_model=settings.ollama_general_model)

    # Redis pub/sub is how the API process's SSE endpoint (running in a
    # separate process) receives these events — the in-memory subscribers
    # path on EventBroadcaster only fans out within a single process.
    redis_client = aioredis.from_url(settings.redis_url)
    ctx["redis_client"] = redis_client

    orchestrator = Orchestrator(
        planner=planner,
        scheduler=scheduler,
        policy_engine=policy_engine,
        model_router=model_router,
        db_session_factory=db_session_factory,
        event_broadcaster=EventBroadcaster(redis_client=redis_client),
    )
    ctx["orchestrator"] = orchestrator
    logger.info("Worker startup completed successfully")


async def shutdown(ctx: dict[str, Any]) -> None:
    redis_client = ctx.get("redis_client")
    if redis_client is not None:
        await redis_client.aclose()
    logger.info("Worker shutting down")


async def run_workflow_job(
    ctx: dict[str, Any], task_id: str, run_id: str, request_data: dict[str, Any]
) -> dict[str, Any]:
    """Background task function executed by Arq worker."""
    orchestrator: Orchestrator = ctx["orchestrator"]
    request = TaskRequest(**request_data)
    logger.info("Executing background workflow job", task_id=task_id, run_id=run_id)
    return await orchestrator.run(request, task_id=task_id, run_id=run_id)


def get_redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    functions: ClassVar[list] = [run_workflow_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = get_redis_settings()



if __name__ == "__main__":
    from arq.worker import run_worker
    run_worker(WorkerSettings)
