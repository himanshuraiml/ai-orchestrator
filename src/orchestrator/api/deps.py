from collections.abc import AsyncIterator
from functools import lru_cache

from arq import ArqRedis
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.config.settings import get_settings, load_model_profiles, load_routing_config
from orchestrator.db.session import get_session, get_sessionmaker
from orchestrator.orchestration.executor import (
    DocumentExecutor,
    LLMExecutor,
    PythonExecutor,
    ToolExecutor,
)
from orchestrator.orchestration.orchestrator import Orchestrator
from orchestrator.orchestration.planner import AutonomousPlanner
from orchestrator.orchestration.scheduler import StepScheduler
from orchestrator.providers.base import ModelGateway
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
from orchestrator.tools.registry import ToolRegistry
from orchestrator.tools.router import ToolRouter

# LiteLLM covers every cloud provider we route to; local models go through Ollama.
_LITELLM_PROVIDERS = {"openai", "anthropic", "google"}


async def get_db() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


@lru_cache
def get_model_router() -> ModelRouter:
    models = load_model_profiles()
    scorer = ModelScorer(load_routing_config())
    policy_engine = PolicyEngine()
    return ModelRouter(models, scorer, policy_engine)


@lru_cache
def _litellm_gateway() -> LiteLLMGateway:
    return LiteLLMGateway()


@lru_cache
def _local_gateway() -> LocalGateway:
    return LocalGateway()


def get_gateway_for_provider(provider: str) -> ModelGateway:
    if provider in _LITELLM_PROVIDERS:
        return _litellm_gateway()
    if provider == "ollama":
        return _local_gateway()
    raise ValueError(f"No gateway registered for provider {provider!r}")


async def get_arq_pool(request: Request) -> ArqRedis:
    """Set up in apps/api/main.py's lifespan, so this is never None once
    the app is actually serving requests."""
    return request.app.state.arq_pool


@lru_cache
def get_orchestrator() -> Orchestrator:
    """Orchestrator wired for in-process (synchronous, `?sync=true`) runs —
    same executor/adapter wiring as apps/worker/main.py's Arq-job path, just
    without an Arq pool since nothing here needs to enqueue anything.
    """
    local_gateway = _local_gateway()

    def gateway_resolver(provider: str) -> ModelGateway:
        return local_gateway if provider == "ollama" else _litellm_gateway()

    model_profiles = load_model_profiles()
    model_registry = {m.id: m for m in model_profiles}

    policy_engine = PolicyEngine()
    model_router = get_model_router()

    tool_registry = ToolRegistry()
    tool_router = ToolRouter(tool_registry.list_profiles(), policy_engine)

    mcp_client = MCPToolClient()
    python_adapter = PythonAdapter(mcp_client)
    ocr_adapter = OCRAdapter(mcp_client)
    pandoc_adapter = PandocAdapter(mcp_client)
    adapters = {
        "python": python_adapter,
        "ocr": ocr_adapter,
        "pandoc": pandoc_adapter,
        "filesystem": FilesystemAdapter(),
        "browser": BrowserAdapter(),
    }

    llm_executor = LLMExecutor(gateway_resolver, model_registry)
    executors = {
        "llm": llm_executor,
        "tool": ToolExecutor(adapters, tool_router),
        "python": PythonExecutor(python_adapter),
        "document": DocumentExecutor(ocr_adapter, pandoc_adapter),
    }

    scheduler = StepScheduler(executors=executors, default_executor=llm_executor)
    planner = AutonomousPlanner(gateway=local_gateway, planner_model=get_settings().ollama_general_model)

    return Orchestrator(
        planner=planner,
        scheduler=scheduler,
        policy_engine=policy_engine,
        model_router=model_router,
        db_session_factory=get_sessionmaker(),
    )
