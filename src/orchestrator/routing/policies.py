from typing import Any

from orchestrator.config.settings import load_policies_config
from orchestrator.domain.enums import PrivacyLevel
from orchestrator.domain.models import ModelProfile
from orchestrator.domain.tasks import TaskRequirements
from orchestrator.domain.tools import ToolProfile

# Privacy levels that must never leave the machine.
_LOCAL_ONLY_PRIVACY = {PrivacyLevel.PRIVATE}


class PolicyEngine:
    """Hard-constraint gate for model selection, plus a basic tool policy
    check. Arch doc §16 (privacy/context/budget) and §25 (tool permissions).
    """

    def __init__(self, policies_config: dict | None = None) -> None:
        self.policies = (policies_config or load_policies_config()).get("policies", {})

    def model_allowed(self, model: ModelProfile, requirements: TaskRequirements) -> bool:
        if requirements.privacy in _LOCAL_ONLY_PRIVACY and model.privacy_class != "local":
            return False

        if requirements.context_tokens and requirements.context_tokens > model.context_window:
            return False

        return not (requirements.max_cost_usd is not None and model.cost_score <= 0)

    def tool_allowed(self, tool: ToolProfile, *, policy_name: str = "default") -> bool:
        policy = self.policies.get(policy_name, self.policies.get("default", {}))

        if tool.requires_network and not policy.get("network", {}).get("enabled", False):
            return False

        if tool.requires_filesystem and not policy.get("filesystem", {}).get("read", False):
            return False

        # requires_approval tools need the approval workflow (Phase 9) to clear first.
        return not tool.requires_approval

    def validate_request(self, request: Any) -> None:
        """Validates basic request constraints."""
        if not getattr(request, "prompt", None) and not getattr(request, "goal", None):
            raise ValueError("Task request prompt/goal cannot be empty")

