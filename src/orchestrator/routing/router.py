from orchestrator.domain.models import ModelProfile
from orchestrator.domain.tasks import TaskRequirements
from orchestrator.routing.policies import PolicyEngine
from orchestrator.routing.scoring import ModelScorer


class NoEligibleModelError(RuntimeError):
    pass


class ModelRouter:
    """Deterministic v1 router — arch doc §14."""

    def __init__(
        self,
        models: list[ModelProfile],
        scorer: ModelScorer,
        policy_engine: PolicyEngine,
    ) -> None:
        self.models = models
        self.scorer = scorer
        self.policy_engine = policy_engine

    def candidates(self, requirements: TaskRequirements) -> list[ModelProfile]:
        candidates = [model for model in self.models if model.enabled]

        candidates = [
            model
            for model in candidates
            if requirements.required_capabilities <= model.capabilities
        ]

        candidates = [
            model
            for model in candidates
            if self.policy_engine.model_allowed(model, requirements)
        ]

        return candidates

    def route(self, requirements: TaskRequirements) -> ModelProfile:
        candidates = self.candidates(requirements)

        if not candidates:
            raise NoEligibleModelError("No eligible model found for requirements")

        return max(candidates, key=lambda model: self.scorer.score(model, requirements))
