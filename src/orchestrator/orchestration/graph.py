"""Workflow Graph — arch doc §20 & Phase 3.1.1.

Manages DAG nodes (TaskSteps), dependency validation, cycle detection,
max_steps cap enforcement, and topological readiness checks.
"""

from collections import defaultdict, deque
from typing import Any

from orchestrator.domain.enums import ExecutionStatus
from orchestrator.domain.workflows import TaskStep


class CycleDetectedError(ValueError):
    """Raised when a cycle is detected in the TaskStep DAG."""


class MaxStepsExceededError(ValueError):
    """Raised when the number of steps exceeds max_steps cap."""


class InvalidWorkflowError(ValueError):
    """Raised when workflow validation fails (e.g. unknown dependency ID)."""


class WorkflowGraph:
    """DAG structure representing a multi-step task decomposition."""

    def __init__(self, max_steps: int = 25) -> None:
        self.max_steps = max_steps
        self.steps: dict[str, TaskStep] = {}

    def add_step(self, step: TaskStep) -> None:
        """Add a step to the graph, enforcing max_steps and verifying DAG state."""
        if len(self.steps) >= self.max_steps:
            raise MaxStepsExceededError(
                f"Workflow step count exceeds maximum limit of {self.max_steps}"
            )
        self.steps[step.id] = step
        self.validate()

    def get_step(self, step_id: str) -> TaskStep | None:
        return self.steps.get(step_id)

    def validate(self) -> None:
        """Validates dependency existence and cycle absence."""
        # 1. Verify dependency IDs exist in step dict (if referenced)
        for step in self.steps.values():
            for dep_id in step.dependencies:
                if dep_id not in self.steps:
                    raise InvalidWorkflowError(
                        f"Step {step.id!r} references unknown dependency {dep_id!r}"
                    )

        # 2. Cycle detection via Kahn's algorithm (topological sort)
        in_degree: dict[str, int] = {step_id: 0 for step_id in self.steps}
        adj_list: dict[str, list[str]] = defaultdict(list)

        for step in self.steps.values():
            for dep_id in step.dependencies:
                adj_list[dep_id].append(step.id)
                in_degree[step.id] += 1

        queue: deque[str] = deque([sid for sid, deg in in_degree.items() if deg == 0])
        visited_count = 0

        while queue:
            node = queue.popleft()
            visited_count += 1
            for neighbor in adj_list[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count < len(self.steps):
            raise CycleDetectedError("Circular dependency detected in workflow DAG")

    def ready_steps(self, completed: set[str]) -> list[TaskStep]:
        """Returns steps whose dependencies are all completed and are not themselves completed."""
        return [
            step
            for step in self.steps.values()
            if step.id not in completed
            and step.status in (ExecutionStatus.PENDING, ExecutionStatus.WAITING_APPROVAL)
            and all(dep in completed for dep in step.dependencies)
        ]

    def is_complete(self, completed: set[str]) -> bool:
        """Returns True if all graph steps are in the completed set."""
        return len(self.steps) > 0 and len(completed) == len(self.steps)

    def final_result(self) -> dict[str, Any]:
        """Aggregates results from leaf steps or all completed steps."""
        results: dict[str, Any] = {}
        for step_id, step in self.steps.items():
            results[step_id] = step.result
        return results
