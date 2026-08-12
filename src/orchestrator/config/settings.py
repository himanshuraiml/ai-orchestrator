from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

from orchestrator.domain.models import ModelProfile
from orchestrator.domain.tools import RegisteredTool, ToolProfile

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIGS_DIR = REPO_ROOT / "configs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"

    database_url: str = "postgresql+asyncpg://orchestrator:orchestrator@localhost:5432/orchestrator"
    redis_url: str = "redis://localhost:6379/0"

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""

    ollama_base_url: str = "http://localhost:11434"
    ollama_coding_model: str = "qwen2.5-coder:7b-instruct-q8_0"
    ollama_general_model: str = "phi4:14b-q4_K_M"
    ollama_embedding_model: str = "nomic-embed-text"

    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 768

    artifact_root: str = "/data/artifacts"

    brave_search_api_key: str = ""

    log_level: str = "INFO"

    max_task_cost_usd: float = 2.00
    max_workflow_steps: int = 25
    default_task_timeout_seconds: int = 900

    configs_dir: Path = CONFIGS_DIR


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _load_yaml(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f) or {}


@lru_cache
def load_models_config(configs_dir: Path | None = None) -> dict:
    return _load_yaml((configs_dir or CONFIGS_DIR) / "models.yaml")


@lru_cache
def load_tools_config(configs_dir: Path | None = None) -> dict:
    return _load_yaml((configs_dir or CONFIGS_DIR) / "tools.yaml")


@lru_cache
def load_routing_config(configs_dir: Path | None = None) -> dict:
    return _load_yaml((configs_dir or CONFIGS_DIR) / "routing.yaml")


@lru_cache
def load_policies_config(configs_dir: Path | None = None) -> dict:
    return _load_yaml((configs_dir or CONFIGS_DIR) / "policies.yaml")


def load_model_profiles(configs_dir: Path | None = None) -> list[ModelProfile]:
    raw = load_models_config(configs_dir)
    return [
        ModelProfile(
            id=model_id,
            provider=entry["provider"],
            model_name=entry["model"],
            capabilities=frozenset(entry.get("capabilities", [])),
            context_window=entry["context_window"],
            quality_score=entry["quality_score"],
            cost_score=entry["cost_score"],
            latency_score=entry["latency_score"],
            privacy_class=entry["privacy_class"],
            enabled=entry.get("enabled", True),
        )
        for model_id, entry in raw.get("models", {}).items()
    ]


def load_tool_profiles(configs_dir: Path | None = None) -> list[ToolProfile]:
    raw = load_tools_config(configs_dir)
    return [
        ToolProfile(
            id=tool_id,
            name=entry["name"],
            capabilities=frozenset(entry.get("capabilities", [])),
            requires_network=entry.get("requires_network", False),
            requires_filesystem=entry.get("requires_filesystem", False),
            requires_approval=entry.get("requires_approval", False),
            risk_level=entry.get("risk_level", "low"),
        )
        for tool_id, entry in raw.get("tools", {}).items()
    ]


def load_registered_tools(configs_dir: Path | None = None) -> list[RegisteredTool]:
    """MCP-backed tools only (`server` set in tools.yaml) — arch doc §24.
    Tools implemented in-process (server: null) aren't part of the MCP
    boundary and have no RegisteredTool entry.
    """
    raw = load_tools_config(configs_dir)
    return [
        RegisteredTool(
            id=tool_id,
            server=entry["server"],
            name=entry.get("mcp_tool", tool_id),
            description=entry.get("description", ""),
            input_schema=entry.get("input_schema", {}),
            capabilities=frozenset(entry.get("capabilities", [])),
            risk_level=entry.get("risk_level", "low"),
        )
        for tool_id, entry in raw.get("tools", {}).items()
        if entry.get("server")
    ]
