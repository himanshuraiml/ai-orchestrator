from orchestrator.domain.tools import ToolProfile
from orchestrator.routing.policies import PolicyEngine


class NoSuitableToolError(RuntimeError):
    pass


class ToolRouter:
    """Arch doc §23 — the same capability model applied to tools as to models."""

    def __init__(self, tools: list[ToolProfile], policy_engine: PolicyEngine) -> None:
        self.tools = tools
        self.policy_engine = policy_engine

    def candidates(
        self, required_capabilities: set[str], *, policy_name: str = "default"
    ) -> list[ToolProfile]:
        candidates = [
            tool for tool in self.tools if required_capabilities <= tool.capabilities
        ]

        return [
            tool
            for tool in candidates
            if self.policy_engine.tool_allowed(tool, policy_name=policy_name)
        ]

    def select(
        self, required_capabilities: set[str], *, policy_name: str = "default"
    ) -> ToolProfile:
        candidates = self.candidates(required_capabilities, policy_name=policy_name)

        if not candidates:
            raise NoSuitableToolError(
                f"No suitable tool for capabilities {required_capabilities!r}"
            )

        return candidates[0]
