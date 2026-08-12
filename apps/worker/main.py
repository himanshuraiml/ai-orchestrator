"""Arq worker process main entrypoint.

Executes asynchronous background workflow tasks dispatched by the API process.
"""

from typing import Any, ClassVar

from arq.connections import RedisSettings
from orchestrator.routing.model_router import ModelRouter
from orchestrator.routing.policies import PolicyEngine
from orchestrator.routing.scorer import ModelScorer
from structlog import get_logger

from orchestrator.config.settings import get_settings
from orchestrator.db.session import create_session_factory
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
from orchestrator.tools.adapters.browser import BrowserAdapter
from orchestrator.tools.adapters.filesystem import FilesystemAdapter
from orchestrator.tools.adapters.ocr import OCRAdapter
from orchestrator.tools.adapters.pandoc import PandocAdapter
from orchestrator.tools.adapters.python import PythonAdapter
from orchestrator.tools.mcp_client import MCPClient
from orchestrator.tools.permissions import ToolPermissions
from orchestrator.tools.registry import ToolRegistry
from orchestrator.tools.router import ToolRouter

logger = get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    """Initialize worker dependencies, gateways, executors, DB session, and orchestrator."""
    settings = get_settings()

    # 1. DB Session Factory
    db_session_factory = create_session_factory(settings.database_url)
    ctx["db_session_factory"] = db_session_factory

    # 2. Gateways & Model Router
    litellm_gateway = LiteLLMGateway(settings.openai_api_key)
    local_gateway = LocalGateway(settings.ollama_base_url)

    def gateway_resolver(provider: str):
        return local_gateway if provider == "ollama" else litellm_gateway

    from orchestrator.config.settings import load_model_profiles, load_tool_profiles
    model_profiles = load_model_profiles()
    model_registry = {m.id: m for m in model_profiles}

    scorer = ModelScorer()
    _ = ModelRouter(model_profiles, scorer)


    # 3. Tools & Adapters
    tool_profiles = load_tool_profiles()
    tool_registry = ToolRegistry(tool_profiles)
    tool_permissions = ToolPermissions()
    tool_router = ToolRouter(tool_registry, tool_permissions)

    mcp_client = MCPClient()
    python_adapter = PythonAdapter(mcp_client)
    ocr_adapter = OCRAdapter(mcp_client)
    pandoc_adapter = PandocAdapter(mcp_client)
    fs_adapter = FilesystemAdapter()
    browser_adapter = BrowserAdapter(settings.brave_search_api_key)

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
    policy_engine = PolicyEngine()

    orchestrator = Orchestrator(
        planner=planner,
        scheduler=scheduler,
        policy_engine=policy_engine,
        db_session_factory=db_session_factory,
        event_broadcaster=EventBroadcaster(),
    )
    ctx["orchestrator"] = orchestrator
    logger.info("Worker startup completed successfully")


async def shutdown(ctx: dict[str, Any]) -> None:
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
    settings = get_settings()
    # Parse host/port from redis_url
    url = settings.redis_url.replace("redis://", "")
    host_port = url.split("/")[0]
    if ":" in host_port:
        host, port = host_port.split(":")
        return RedisSettings(host=host, port=int(port))
    return RedisSettings(host=host_port)


class WorkerSettings:
    functions: ClassVar[list] = [run_workflow_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = get_redis_settings()



if __name__ == "__main__":
    from arq.worker import run_worker
    run_worker(WorkerSettings)
