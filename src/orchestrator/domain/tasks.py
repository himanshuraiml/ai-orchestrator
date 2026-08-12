from pydantic import BaseModel, Field

from orchestrator.domain.enums import PrivacyLevel, QualityLevel, TaskType


class TaskRequirements(BaseModel):
    task_type: TaskType = TaskType.GENERAL

    required_capabilities: set[str] = Field(default_factory=set)

    context_tokens: int = 0

    privacy: PrivacyLevel = PrivacyLevel.NORMAL
    quality: QualityLevel = QualityLevel.STANDARD

    max_cost_usd: float | None = None
    max_latency_ms: int | None = None

    needs_tools: bool = False
    needs_web: bool = False
    needs_code_execution: bool = False
    needs_file_access: bool = False

    output_format: str | None = None


class TaskRequest(BaseModel):
    goal: str
    requirements: TaskRequirements
    file_ids: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    # Not in the architecture doc: needed so a personal multi-turn session
    # can thread context across tasks (see Phase 6.1 short-term memory).
    session_id: str | None = None
