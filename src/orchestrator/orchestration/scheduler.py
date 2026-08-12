"""Step Scheduler — arch doc §20, §3.1.4 & Phase 3.1.4.

Schedules and executes ready DAG nodes in parallel using asyncio.gather.
Handles input reference resolution, status transitions, repair limits, and deadlock detection.
"""

import asyncio
from typing import Any

from structlog import get_logger

from orchestrator.domain.enums import ExecutionStatus
from orchestrator.domain.workflows import TaskStep
from orchestrator.orchestration.executor import ExecutionResult, Executor
from orchestrator.orchestration.graph import WorkflowGraph
from orchestrator.orchestration.state_machine import transition_step_status

logger = get_logger(__name__)


class DeadlockError(RuntimeError):
    """Raised when workflow execution deadlocks (no ready steps, graph incomplete)."""


class StepScheduler:
    """Schedules ready DAG steps concurrently and passes state between dependencies."""

    def __init__(
        self,
        executors: dict[str, Executor],
        default_executor: Executor | None = None,
        max_repair_attempts: int = 2,
    ) -> None:
        self.executors = executors
        self.default_executor = default_executor
        self.max_repair_attempts = max_repair_attempts

    def resolve_step_context(
        self, step: TaskStep, completed_steps: dict[str, TaskStep], request_context: dict[str, Any]
    ) -> dict[str, Any]:
        """Resolves inputs from completed dependency steps into step context."""
        ctx = dict(step.context)

        # Base request context if not present
        for k, v in request_context.items():
            if k not in ctx:
                ctx[k] = v

        # Aggregate outputs of dependencies
        parent_outputs: dict[str, Any] = {}
        for dep_id in step.dependencies:
            if dep_id in completed_steps:
                dep_step = completed_steps[dep_id]
                parent_outputs[dep_id] = dep_step.result

        ctx["parent_outputs"] = parent_outputs

        # If step expects specific input_refs, extract them
        if step.input_refs:
            ref_data = {}
            for ref_id in step.input_refs:
                if ref_id in completed_steps:
                    ref_data[ref_id] = completed_steps[ref_id].result
            ctx["input_refs_data"] = ref_data

        return ctx

    def get_executor_for_step(self, step: TaskStep) -> Executor:
        executor = self.executors.get(step.executor_type)
        if executor is None:
            if self.default_executor is not None:
                return self.default_executor
            raise ValueError(f"No executor registered for type {step.executor_type!r}")
        return executor

    async def execute_step(
        self, step: TaskStep, context: dict[str, Any]
    ) -> ExecutionResult:
        """Executes a single step with retry/repair handling and state tracking."""
        executor = self.get_executor_for_step(step)

        step.status = transition_step_status(step.status, ExecutionStatus.RUNNING)
        step.attempts_made += 1

        logger.info(
            "Executing DAG step",
            step_id=step.id,
            executor_type=step.executor_type,
            attempt=step.attempts_made,
        )

        try:
            result = await executor.execute(step, context)
        except Exception as exc:  # noqa: BLE001 — handle unhandled executor exceptions
            result = ExecutionResult(
                success=False, error_type=type(exc).__name__, error_message=str(exc)
            )

        if result.success:
            step.status = transition_step_status(step.status, ExecutionStatus.SUCCEEDED)
            step.result = result.output
            step.cost_usd += result.cost_usd or 0.0
            step.latency_ms += result.latency_ms or 0
        else:
            step.error = result.error_message
            if step.attempts_made <= step.retry_limit and step.attempts_made <= self.max_repair_attempts:
                logger.warning(
                    "Step execution failed; retrying",
                    step_id=step.id,
                    attempt=step.attempts_made,
                    error=step.error,
                )
                step.status = transition_step_status(step.status, ExecutionStatus.FAILED)
                # Re-transition to RUNNING for retry
                step.status = transition_step_status(step.status, ExecutionStatus.RUNNING)
                return await self.execute_step(step, context)
            else:
                step.status = transition_step_status(step.status, ExecutionStatus.FAILED)

        return result

    async def run_dag(
        self,
        graph: WorkflowGraph,
        request_context: dict[str, Any] | None = None,
        event_publisher: Any | None = None,
    ) -> dict[str, Any]:
        """Runs the entire WorkflowGraph DAG concurrently until completion or failure."""
        request_context = request_context or {}
        completed: set[str] = set()
        failed: set[str] = set()
        completed_steps: dict[str, TaskStep] = {}

        while not graph.is_complete(completed):
            ready = graph.ready_steps(completed)

            if not ready:
                if failed:
                    # Some steps failed, preventing further readiness
                    logger.error("Workflow failed due to step errors", failed_steps=list(failed))
                    break
                raise DeadlockError("Workflow deadlock: graph incomplete but no steps are ready")

            logger.info("Scheduling ready DAG steps", count=len(ready), step_ids=[s.id for s in ready])

            # Publish SSE step started events
            if event_publisher:
                for step in ready:
                    await event_publisher.publish("step_started", {"step_id": step.id, "name": step.name})

            # Execute ready steps concurrently
            tasks = [
                self.execute_step(
                    step, self.resolve_step_context(step, completed_steps, request_context)
                )
                for step in ready
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for step, res in zip(ready, results):
                if isinstance(res, Exception):
                    step.status = ExecutionStatus.FAILED
                    step.error = str(res)
                    failed.add(step.id)
                elif step.status == ExecutionStatus.SUCCEEDED:
                    completed.add(step.id)
                    completed_steps[step.id] = step
                    if event_publisher:
                        await event_publisher.publish("step_completed", {"step_id": step.id, "result": step.result})
                else:
                    failed.add(step.id)
                    if event_publisher:
                        await event_publisher.publish("step_failed", {"step_id": step.id, "error": step.error})

        return graph.final_result()
