import json
import uuid

from arq import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from redis import asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.api.deps import get_arq_pool, get_db, get_orchestrator
from orchestrator.config.settings import get_settings, load_routing_config
from orchestrator.db.models import TaskStep as DBTaskStep
from orchestrator.db.models import WorkflowRun as DBWorkflowRun
from orchestrator.db.repositories import tasks as tasks_repo
from orchestrator.domain.tasks import TaskRequest
from orchestrator.observability.metrics import task_total
from orchestrator.orchestration.orchestrator import Orchestrator

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
    response: Response,
    sync: bool = Query(False, description="Execute synchronously if true, async via background worker if false"),
    db: AsyncSession = Depends(get_db),
    orchestrator: Orchestrator = Depends(get_orchestrator),
    arq_pool: ArqRedis = Depends(get_arq_pool),
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
    await tasks_repo.update_status(db, task.id, "running", started_at=tasks_repo.now())
    await db.commit()

    # WorkflowRun/TaskStep rows are the Orchestrator's responsibility (it
    # checkpoints them once the plan is generated — see
    # Orchestrator._checkpoint_workflow_init); the route only owns Task.
    run_id = uuid.uuid4()

    if not sync:
        await arq_pool.enqueue_job(
            "run_workflow_job",
            task_id=str(task.id),
            run_id=str(run_id),
            request_data=task_request.model_dump(mode="json"),
        )
        response.status_code = status.HTTP_202_ACCEPTED
        return TaskResponse(task_id=task.id, workflow_run_id=run_id, status="running")

    try:
        result = await orchestrator.run(task_request, task_id=task.id, run_id=run_id)
    except Exception as exc:
        await tasks_repo.update_status(db, task.id, "failed", completed_at=tasks_repo.now())
        await db.commit()
        task_total.labels(status="failed").inc()
        raise HTTPException(status_code=502, detail=f"Workflow execution failed: {exc}") from exc

    final_status = "succeeded" if result["status"] == "succeeded" else "failed"
    await tasks_repo.update_status(db, task.id, final_status, completed_at=tasks_repo.now())
    await db.commit()
    task_total.labels(status=final_status).inc()

    return TaskResponse(
        task_id=task.id,
        workflow_run_id=run_id,
        status=result["status"],
        result=json.dumps(result.get("results", {})),
        cost_usd=result.get("total_cost_usd"),
        latency_ms=result.get("total_latency_ms"),
    )


@router.get("/v1/runs/{run_id}")
async def get_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Retrieve workflow run details by ID."""
    run = await db.get(DBWorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Workflow run {run_id} not found")
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


_TERMINAL_EVENTS = {"workflow_completed", "workflow_failed"}


@router.get("/v1/runs/{run_id}/events")
async def stream_run_events(run_id: uuid.UUID):
    """SSE stream of workflow run events via Redis pub/sub — arch doc §57.

    The Orchestrator (running in the worker process) publishes to
    `run_events:{run_id}` via EventBroadcaster; this subscribes to that
    same channel and relays events to the client until the run finishes.
    """

    async def event_generator():
        redis_client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        channel = f"run_events:{run_id}"
        await pubsub.subscribe(channel)

        try:
            yield f"event: connected\ndata: {json.dumps({'run_id': str(run_id)})}\n\n"

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                payload = json.loads(message["data"])
                event_type = payload.get("event", "message")
                yield f"event: {event_type}\ndata: {json.dumps(payload.get('data', {}))}\n\n"

                if event_type in _TERMINAL_EVENTS:
                    break
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            await redis_client.aclose()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
