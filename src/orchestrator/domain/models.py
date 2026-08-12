from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    id: str
    provider: str
    model_name: str

    capabilities: frozenset[str]

    context_window: int

    quality_score: float
    cost_score: float
    latency_score: float

    privacy_class: str

    enabled: bool = True
