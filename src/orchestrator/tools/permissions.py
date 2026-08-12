from orchestrator.domain.tools import ToolProfile
from orchestrator.routing.policies import PolicyEngine
from orchestrator.tools.registry import ToolRegistry


class ToolPermissions:
    """Per-workflow tool allowlists — arch doc §25 / tasks.md 2.1.2.

    Wraps PolicyEngine.tool_allowed() to resolve, for a given workflow
    policy name (e.g. "default", "coding", "document"), which registered
    tools a step is permitted to invoke. Do not expose every registered
    tool to every model — arch doc §24.
    """

    def __init__(self, registry: ToolRegistry, policy_engine: PolicyEngine) -> None:
        self.registry = registry
        self.policy_engine = policy_engine

    def allowed_tools(self, policy_name: str = "default") -> list[ToolProfile]:
        return [
            tool
            for tool in self.registry.list_profiles()
            if self.policy_engine.tool_allowed(tool, policy_name=policy_name)
        ]

    def is_allowed(self, tool_id: str, policy_name: str = "default") -> bool:
        tool = self.registry.profiles.get(tool_id)
        if tool is None:
            return False
        return self.policy_engine.tool_allowed(tool, policy_name=policy_name)
