from orchestrator.config.settings import (
    load_registered_tools,
    load_tool_profiles,
    load_tools_config,
)
from orchestrator.domain.tools import RegisteredTool, ToolProfile


class ToolRegistry:
    """Dynamic tool registration from configs/tools.yaml — tasks.md 2.1.3."""

    def __init__(self, configs_dir=None) -> None:
        self._raw = load_tools_config(configs_dir)
        self.profiles: dict[str, ToolProfile] = {
            profile.id: profile for profile in load_tool_profiles(configs_dir)
        }
        self.registered_tools: dict[str, RegisteredTool] = {
            tool.id: tool for tool in load_registered_tools(configs_dir)
        }

    def list_profiles(self) -> list[ToolProfile]:
        return list(self.profiles.values())

    def get(self, tool_id: str) -> ToolProfile:
        return self.profiles[tool_id]

    def server_for(self, tool_id: str) -> str | None:
        return self._raw.get("tools", {}).get(tool_id, {}).get("server")

    def mcp_tool_name(self, tool_id: str) -> str | None:
        entry = self._raw.get("tools", {}).get(tool_id, {})
        return entry.get("mcp_tool") if entry.get("server") else None

    def is_mcp_backed(self, tool_id: str) -> bool:
        return self.server_for(tool_id) is not None
