from dataclasses import dataclass, field
from typing import Any

from orchestrator.domain.enums import ExecutionStatus


@dataclass
class TaskStep:
    """A single DAG node — arch doc §19.

    Used by WorkflowGraph, Executor, Scheduler, and Orchestrator.
    """

    id: str
    name: str

    dependencies: list[str] = field(default_factory=list)

    executor_type: str = "llm"  # llm | tool | python | document
    executor_id: str | None = None

    input_refs: list[str] = field(default_factory=list)
    output_schema: dict | None = None

    retry_limit: int = 2
    attempts_made: int = 0

    status: ExecutionStatus = ExecutionStatus.PENDING
    context: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    cost_usd: float = 0.0
    latency_ms: int = 0

