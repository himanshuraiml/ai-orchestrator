from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.config.settings import load_model_profiles, load_routing_config
from orchestrator.db.session import get_session
from orchestrator.providers.base import ModelGateway
from orchestrator.providers.litellm_gateway import LiteLLMGateway
from orchestrator.providers.local_gateway import LocalGateway
from orchestrator.routing.policies import PolicyEngine
from orchestrator.routing.router import ModelRouter
from orchestrator.routing.scoring import ModelScorer

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
