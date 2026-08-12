import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.db.models import Execution, RoutingEvent, TaskStep, WorkflowRun


async def create_workflow_run(
    session: AsyncSession,
    *,
    task_id: uuid.UUID,
    plan: dict | None = None,
    status: str = "pending",
) -> WorkflowRun:
    run = WorkflowRun(task_id=task_id, plan=plan or {}, status=status)
    session.add(run)
    await session.flush()
    return run


async def get_workflow_run(session: AsyncSession, run_id: uuid.UUID) -> WorkflowRun | None:
    return await session.get(WorkflowRun, run_id)


async def update_run_status(
    session: AsyncSession,
    run_id: uuid.UUID,
    status: str,
    *,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    total_cost_usd: Decimal | float | None = None,
    total_latency_ms: int | None = None,
) -> None:
    run = await session.get(WorkflowRun, run_id)
    if run is None:
        return
    run.status = status
    if started_at is not None:
        run.started_at = started_at
    if completed_at is not None:
        run.completed_at = completed_at
    if total_cost_usd is not None:
        run.total_cost_usd = total_cost_usd
    if total_latency_ms is not None:
        run.total_latency_ms = total_latency_ms


async def create_task_step(
    session: AsyncSession,
    *,
    workflow_run_id: uuid.UUID,
    step_key: str,
    name: str,
    executor_type: str | None = None,
    executor_id: str | None = None,
    dependencies: list | None = None,
    input_refs: list | None = None,
    status: str = "pending",
) -> TaskStep:
    step = TaskStep(
        workflow_run_id=workflow_run_id,
        step_key=step_key,
        name=name,
        executor_type=executor_type,
        executor_id=executor_id,
        dependencies=dependencies or [],
        input_refs=input_refs or [],
        status=status,
    )
    session.add(step)
    await session.flush()
    return step


async def update_task_step(
    session: AsyncSession,
    step_id: uuid.UUID,
    status: str,
    *,
    output: dict | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> None:
    step = await session.get(TaskStep, step_id)
    if step is None:
        return
    step.status = status
    if output is not None:
        step.output = output
    if started_at is not None:
        step.started_at = started_at
    if completed_at is not None:
        step.completed_at = completed_at


async def record_execution(
    session: AsyncSession,
    *,
    workflow_run_id: uuid.UUID,
    task_step_id: uuid.UUID,
    executor_type: str,
    executor_id: str,
    status: str,
    provider: str | None = None,
    request_metadata: dict | None = None,
    response_metadata: dict | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cost_usd: Decimal | float | None = None,
    latency_ms: int | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> Execution:
    execution = Execution(
        workflow_run_id=workflow_run_id,
        task_step_id=task_step_id,
        executor_type=executor_type,
        executor_id=executor_id,
        provider=provider,
        status=status,
        request_metadata=request_metadata or {},
        response_metadata=response_metadata or {},
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        error_type=error_type,
        error_message=error_message,
    )
    session.add(execution)
    await session.flush()
    return execution


async def record_routing_event(
    session: AsyncSession,
    *,
    candidate_models: list,
    selected_model: str,
    task_id: uuid.UUID | None = None,
    workflow_run_id: uuid.UUID | None = None,
    task_step_id: uuid.UUID | None = None,
    routing_reason: dict | None = None,
    predicted_score: float | None = None,
) -> RoutingEvent:
    event = RoutingEvent(
        task_id=task_id,
        workflow_run_id=workflow_run_id,
        task_step_id=task_step_id,
        candidate_models=candidate_models,
        selected_model=selected_model,
        routing_reason=routing_reason or {},
        predicted_score=predicted_score,
    )
    session.add(event)
    await session.flush()
    return event
