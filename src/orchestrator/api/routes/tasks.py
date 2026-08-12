import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.api.deps import get_db, get_gateway_for_provider, get_model_router
from orchestrator.config.settings import load_routing_config
from orchestrator.db.models import TaskStep as DBTaskStep
from orchestrator.db.models import WorkflowRun as DBWorkflowRun
from orchestrator.db.repositories import runs as runs_repo
from orchestrator.db.repositories import tasks as tasks_repo
from orchestrator.domain.tasks import TaskRequest
from orchestrator.observability.metrics import (
    execution_cost_usd_total,
    execution_latency_ms,
    model_calls_total,
    task_total,
)
from orchestrator.routing.router import ModelRouter, NoEligibleModelError

router = APIRouter(tags=["tasks"])

DEFAULT_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class TaskResponse(BaseModel):
    task_id: uuid.UUID
    workflow_run_id: uuid.UUID
    status: str
    result: str | None = None
    model_id: str | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None


def _resolve_capabilities(task_request: TaskRequest) -> set[str]:
    if task_request.requirements.required_capabilities:
        return task_request.requirements.required_capabilities

    task_preferences = load_routing_config().get("routing", {}).get("task_preferences", {})
    entry = task_preferences.get(task_request.requirements.task_type.value, {})
    return set(entry.get("capabilities", []))


@router.post("/v1/tasks", response_model=TaskResponse)
async def create_task(
    task_request: TaskRequest,
    sync: bool = Query(False, description="Execute synchronously if true, async via background worker if false"),
    db: AsyncSession = Depends(get_db),
    model_router: ModelRouter = Depends(get_model_router),
    response: Response = None,
) -> TaskResponse:
    requirements = task_request.requirements
    requirements.required_capabilities = _resolve_capabilities(task_request)

    task = await tasks_repo.create_task(
        db,
        user_id=DEFAULT_USER_ID,
        goal=task_request.goal,
        requirements=requirements.model_dump(mode="json"),
        task_type=requirements.task_type.value,
        status="running",
    )
    run = await runs_repo.create_workflow_run(db, task_id=task.id, status="running")
    step = await runs_repo.create_task_step(
        db,
        workflow_run_id=run.id,
        step_key="main",
        name="Execute goal",
        executor_type="llm",
        status="running",
    )
    await tasks_repo.update_status(db, task.id, "running", started_at=tasks_repo.now())
    await runs_repo.update_run_status(db, run.id, "running", started_at=tasks_repo.now())
    await db.commit()

    if not sync:
        # Asynchronous execution — return 202 Accepted
        if response:
            response.status_code = status.HTTP_202_ACCEPTED
        return TaskResponse(
            task_id=task.id,
            workflow_run_id=run.id,
            status="running",
        )

    try:
        candidates = model_router.candidates(requirements)
        if not candidates:
            raise NoEligibleModelError("No eligible model found for requirements")
        selected = model_router.route(requirements)
    except NoEligibleModelError as exc:
        await _mark_failed(db, task.id, run.id, step.id, error_type="no_eligible_model", error_message=str(exc))
        await db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await runs_repo.record_routing_event(
        db,
        task_id=task.id,
        workflow_run_id=run.id,
        task_step_id=step.id,
        candidate_models=[c.id for c in candidates],
        selected_model=selected.id,
        routing_reason={"quality": requirements.quality.value, "privacy": requirements.privacy.value},
    )
    await db.commit()

    gateway = get_gateway_for_provider(selected.provider)
    messages = [{"role": "user", "content": task_request.goal}]

    try:
        generation = await gateway.generate(model=selected.model_name, messages=messages)
    except Exception as exc:
        model_calls_total.labels(model_id=selected.id, status="failed").inc()
        await runs_repo.record_execution(
            db,
            workflow_run_id=run.id,
            task_step_id=step.id,
            executor_type="llm",
            executor_id=selected.id,
            provider=selected.provider,
            status="failed",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        await _mark_failed(db, task.id, run.id, step.id, error_type=type(exc).__name__, error_message=str(exc))
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Model execution failed: {exc}") from exc

    model_calls_total.labels(model_id=selected.id, status="succeeded").inc()
    if generation.cost_usd:
        execution_cost_usd_total.labels(model_id=selected.id).inc(generation.cost_usd)
    if generation.latency_ms is not None:
        execution_latency_ms.labels(model_id=selected.id).observe(generation.latency_ms)

    await runs_repo.record_execution(
        db,
        workflow_run_id=run.id,
        task_step_id=step.id,
        executor_type="llm",
        executor_id=selected.id,
        provider=selected.provider,
        status="succeeded",
        response_metadata={"raw": generation.raw} if generation.raw else {},
        input_tokens=generation.input_tokens,
        output_tokens=generation.output_tokens,
        cost_usd=generation.cost_usd,
        latency_ms=generation.latency_ms,
    )

    completed_at = tasks_repo.now()
    await runs_repo.update_task_step(
        db, step.id, "succeeded", output={"content": generation.content}, completed_at=completed_at
    )
    await runs_repo.update_run_status(
        db,
        run.id,
        "succeeded",
        completed_at=completed_at,
        total_cost_usd=generation.cost_usd,
        total_latency_ms=generation.latency_ms,
    )
    await tasks_repo.update_status(db, task.id, "succeeded", completed_at=completed_at)
    await db.commit()

    task_total.labels(status="succeeded").inc()

    return TaskResponse(
        task_id=task.id,
        workflow_run_id=run.id,
        status="succeeded",
        result=generation.content,
        model_id=selected.id,
        cost_usd=generation.cost_usd,
        latency_ms=generation.latency_ms,
    )


@router.get("/v1/runs/{run_id}")
async def get_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Retrieve workflow run details by ID."""
    run = await db.get(DBWorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=440, detail=f"Workflow run {run_id} not found")
    return {
        "id": str(run.id),
        "task_id": str(run.task_id),
        "status": run.status,
        "plan": run.plan,
        "total_cost_usd": float(run.total_cost_usd or 0.0),
        "total_latency_ms": run.total_latency_ms,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("/v1/runs/{run_id}/steps")
async def get_run_steps(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Retrieve granular step execution breakdown for a run."""
    stmt = select(DBTaskStep).where(DBTaskStep.workflow_run_id == run_id)
    result = await db.execute(stmt)
    steps = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "step_key": s.step_key,
            "name": s.name,
            "executor_type": s.executor_type,
            "status": s.status,
            "dependencies": s.dependencies,
            "output": s.output,
        }
        for s in steps
    ]


@router.get("/v1/runs/{run_id}/events")
async def stream_run_events(run_id: uuid.UUID):
    """Server-Sent Events (SSE) endpoint for streaming workflow run updates."""
    async def event_generator():
        yield f"event: connected\ndata: {json.dumps({'run_id': str(run_id)})}\n\n"
        await asyncio.sleep(0.1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


async def _mark_failed(
    db: AsyncSession,
    task_id: uuid.UUID,
    run_id: uuid.UUID,
    step_id: uuid.UUID,
    *,
    error_type: str,
    error_message: str,
) -> None:
    completed_at = tasks_repo.now()
    await runs_repo.update_task_step(
        db,
        step_id,
        "failed",
        output={"error_type": error_type, "error": error_message},
        completed_at=completed_at,
    )
    await runs_repo.update_run_status(db, run_id, "failed", completed_at=completed_at)
    await tasks_repo.update_status(db, task_id, "failed", completed_at=completed_at)
    task_total.labels(status="failed").inc()

