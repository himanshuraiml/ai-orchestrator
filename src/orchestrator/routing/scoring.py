from orchestrator.config.settings import load_routing_config
from orchestrator.domain.enums import QualityLevel
from orchestrator.domain.models import ModelProfile
from orchestrator.domain.tasks import TaskRequirements

DEFAULT_HISTORICAL_SUCCESS = 0.5


class ModelScorer:
    """Deterministic v1 scorer — arch doc §15."""

    def __init__(self, routing_config: dict | None = None) -> None:
        config = routing_config or load_routing_config()
        self.weights = config.get("routing", {}).get("weights", {})

    def score(
        self,
        model: ModelProfile,
        req: TaskRequirements,
        historical_success: float = DEFAULT_HISTORICAL_SUCCESS,
    ) -> float:
        capability_match = (
            len(req.required_capabilities & model.capabilities)
            / max(len(req.required_capabilities), 1)
        )

        quality_weights = self.weights.get("quality", {})
        quality_weight = quality_weights.get(
            QualityLevel(req.quality).value,
            {
                QualityLevel.LOW: 0.15,
                QualityLevel.STANDARD: 0.30,
                QualityLevel.HIGH: 0.50,
                QualityLevel.CRITICAL: 0.70,
            }[req.quality],
        )

        cost_weight = self.weights.get("cost", 0.15)
        latency_weight = self.weights.get("latency", 0.10)
        history_weight = self.weights.get("historical_success", 0.15)

        return (
            capability_match * 10.0
            + model.quality_score * quality_weight * 10
            + model.cost_score * cost_weight * 10
            + model.latency_score * latency_weight * 10
            + historical_success * history_weight * 10
        )
