import pytest

from orchestrator.domain.enums import PrivacyLevel, QualityLevel
from orchestrator.domain.models import ModelProfile
from orchestrator.domain.tasks import TaskRequirements
from orchestrator.routing.policies import PolicyEngine
from orchestrator.routing.router import ModelRouter, NoEligibleModelError
from orchestrator.routing.scoring import ModelScorer

ROUTING_CONFIG = {
    "routing": {
        "weights": {
            "quality": {"low": 0.15, "standard": 0.30, "high": 0.50, "critical": 0.70},
            "cost": 0.15,
            "latency": 0.10,
            "historical_success": 0.15,
        }
    }
}


def make_model(
    id: str,
    *,
    capabilities: frozenset[str],
    privacy_class: str = "cloud",
    quality_score: float = 0.8,
    cost_score: float = 0.7,
    latency_score: float = 0.8,
    context_window: int = 100_000,
    enabled: bool = True,
) -> ModelProfile:
    return ModelProfile(
        id=id,
        provider="test",
        model_name=id,
        capabilities=capabilities,
        context_window=context_window,
        quality_score=quality_score,
        cost_score=cost_score,
        latency_score=latency_score,
        privacy_class=privacy_class,
        enabled=enabled,
    )


@pytest.fixture
def router() -> ModelRouter:
    models = [
        make_model(
            "cloud_strong",
            capabilities=frozenset({"coding", "reasoning"}),
            privacy_class="cloud",
            quality_score=0.95,
        ),
        make_model(
            "local_weak",
            capabilities=frozenset({"coding"}),
            privacy_class="local",
            quality_score=0.6,
        ),
    ]
    scorer = ModelScorer(routing_config=ROUTING_CONFIG)
    policy_engine = PolicyEngine(policies_config={})
    return ModelRouter(models, scorer, policy_engine)


def test_capability_filter_excludes_models_missing_required_capability(router: ModelRouter):
    requirements = TaskRequirements(required_capabilities={"reasoning"})

    selected = router.route(requirements)

    assert selected.id == "cloud_strong"


def test_privacy_rejection_excludes_cloud_models(router: ModelRouter):
    requirements = TaskRequirements(
        required_capabilities={"coding"}, privacy=PrivacyLevel.PRIVATE
    )

    selected = router.route(requirements)

    assert selected.id == "local_weak"
    assert selected.privacy_class == "local"


def test_scoring_order_prefers_higher_quality_when_both_eligible(router: ModelRouter):
    requirements = TaskRequirements(required_capabilities={"coding"}, quality=QualityLevel.CRITICAL)

    selected = router.route(requirements)

    assert selected.id == "cloud_strong"


def test_fallback_to_next_best_when_top_choice_disabled():
    models = [
        make_model("primary", capabilities=frozenset({"coding"}), quality_score=0.95, enabled=False),
        make_model("secondary", capabilities=frozenset({"coding"}), quality_score=0.7),
    ]
    router = ModelRouter(models, ModelScorer(routing_config=ROUTING_CONFIG), PolicyEngine(policies_config={}))

    selected = router.route(TaskRequirements(required_capabilities={"coding"}))

    assert selected.id == "secondary"


def test_no_eligible_model_raises(router: ModelRouter):
    requirements = TaskRequirements(required_capabilities={"vision"})

    with pytest.raises(NoEligibleModelError):
        router.route(requirements)
