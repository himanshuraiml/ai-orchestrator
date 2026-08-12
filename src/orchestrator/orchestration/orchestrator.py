"""Orchestrator — arch doc §21, §3.3 & Phase 3.3.

End-to-end workflow execution pipeline:
Policy validation -> Dynamic Plan Generation -> DAG Scheduling -> Durable DB Checkpointing & Resumability -> SSE Event Broadcasting.
"""

import datetime
import inspect
import uuid
from typing import Any

from structlog import get_logger

from orchestrator.domain.enums import ExecutionStatus
from orchestrator.domain.tasks import TaskRequest
from orchestrator.orchestration.graph import WorkflowGraph
from orchestrator.orchestration.planner import AutonomousPlanner, TemplatePlanner
from orchestrator.orchestration.scheduler import StepScheduler
from orchestrator.routing.policies import PolicyEngine
from orchestrator.routing.router import ModelRouter, NoEligibleModelError

logger = get_logger(__name__)


class EventBroadcaster:
    """In-memory & PubSub event publisher for SSE streams."""

    def __init__(self, redis_client: Any = None) -> None:
        self.redis_client = redis_client
        self.subscribers: list[Any] = []

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        payload = {"event": event_type, "data": data, "timestamp": datetime.datetime.now(datetime.UTC).isoformat()}
        for queue in list(self.subscribers):
            try:
                await queue.put(payload)
            except Exception:  # noqa: BLE001, S110
                pass


        if self.redis_client:
            try:
                import json
                channel = f"run_events:{data.get('run_id', 'global')}"
                await self.redis_client.publish(channel, json.dumps(payload))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to publish event to Redis PubSub", error=str(exc))


class Orchestrator:
    """Core orchestrator executing DAG workflows end-to-end."""

    def __init__(
        self,
        planner: AutonomousPlanner | TemplatePlanner | None = None,
        scheduler: StepScheduler | None = None,
        policy_engine: PolicyEngine | None = None,
        model_router: ModelRouter | None = None,
        db_session_factory: Any | None = None,
        event_broadcaster: EventBroadcaster | None = None,
    ) -> None:
        self.planner = planner or AutonomousPlanner()
        self.scheduler = scheduler
        self.policy_engine = policy_engine or PolicyEngine()
        self.model_router = model_router
        self.db_session_factory = db_session_factory
        self.event_broadcaster = event_broadcaster or EventBroadcaster()

    async def run(
        self,
        request: TaskRequest,
        task_id: uuid.UUID | str | None = None,
        run_id: uuid.UUID | str | None = None,
    ) -> dict[str, Any]:
        """Runs a workflow request end-to-end with DB checkpointing."""
        # 1. Policy check
        self.policy_engine.validate_request(request)

        # 2. Plan generation
        plan_or_coro = self.planner.create_plan(request)
        if inspect.isawaitable(plan_or_coro):
            graph = await plan_or_coro
        else:
            graph = plan_or_coro

        ttype = request.requirements.task_type if request.requirements else None
        prompt_text = request.goal
        logger.info("Generated workflow graph for request", task_type=ttype, steps=len(graph.steps))

        # 2b. Resolve model selection for LLM steps the planner left open
        # (the planner prompt explicitly allows executor_id: null, "let
        # router pick" — nothing else in the pipeline performs that pick).
        self._resolve_llm_step_models(graph, request)

        # Generate run_id if not provided
        run_uuid = uuid.UUID(str(run_id)) if run_id else uuid.uuid4()
        task_uuid = uuid.UUID(str(task_id)) if task_id else uuid.uuid4()

        # 3. Save initial run & steps to DB checkpoint if session factory available
        await self._checkpoint_workflow_init(run_uuid, task_uuid, graph)

        await self.event_broadcaster.publish("workflow_started", {"run_id": str(run_uuid), "step_count": len(graph.steps)})

        # 4. Schedule and execute DAG steps
        if self.scheduler is None:
            # Inline execution fallback if scheduler not explicitly provided
            results = {}
            for step_id, step in graph.steps.items():
                step.status = ExecutionStatus.SUCCEEDED
                step.result = {"message": f"Step {step.name!r} executed"}
                results[step_id] = step.result
            return {"status": "succeeded", "results": results}

        try:
            results = await self.scheduler.run_dag(
                graph=graph,
                request_context={"prompt": prompt_text, "goal": prompt_text, "run_id": str(run_uuid)},
                event_publisher=self.event_broadcaster,
            )


            total_cost = sum(s.cost_usd for s in graph.steps.values())
            total_latency = sum(s.latency_ms for s in graph.steps.values())

            # Check if all steps succeeded
            all_succeeded = all(s.status == ExecutionStatus.SUCCEEDED for s in graph.steps.values())
            run_status = ExecutionStatus.SUCCEEDED if all_succeeded else ExecutionStatus.FAILED

            await self._checkpoint_workflow_complete(
                run_uuid, graph, run_status, total_cost, total_latency
            )

            await self.event_broadcaster.publish(
                "workflow_completed",
                {"run_id": str(run_uuid), "status": run_status.value, "cost_usd": total_cost},
            )

            return {
                "run_id": str(run_uuid),
                "status": run_status.value,
                "total_cost_usd": total_cost,
                "total_latency_ms": total_latency,
                "results": results,
            }

        except Exception as exc:
            logger.error("Workflow run failed with unhandled error", run_id=str(run_uuid), error=str(exc))
            await self._checkpoint_workflow_complete(
                run_uuid, graph, ExecutionStatus.FAILED, 0.0, 0
            )
            await self.event_broadcaster.publish(
                "workflow_failed", {"run_id": str(run_uuid), "error": str(exc)}
            )
            raise

    def _resolve_llm_step_models(self, graph: WorkflowGraph, request: TaskRequest) -> None:
        if self.model_router is None:
            return

        requirements_for = getattr(self.planner, "requirements_for", None)

        for step in graph.steps.values():
            if step.executor_type != "llm" or step.executor_id is not None:
                continue

            requirements = requirements_for(step, request) if requirements_for else request.requirements
            try:
                step.executor_id = self.model_router.route(requirements).id
            except NoEligibleModelError as exc:
                logger.warning(
                    "No eligible model for step; will fail at execution",
                    step_id=step.id,
                    error=str(exc),
                )

    async def _checkpoint_workflow_init(
        self, run_uuid: uuid.UUID, task_uuid: uuid.UUID, graph: WorkflowGraph
    ) -> None:
        if self.db_session_factory is None:
            return

        try:
            from orchestrator.db.models import TaskStep as DBTaskStep
            from orchestrator.db.models import WorkflowRun as DBWorkflowRun

            async with self.db_session_factory() as session:
                # Upsert: the caller may have already created a placeholder
                # WorkflowRun row (e.g. to return its id in a 202 response
                # before the job actually starts), and a resumed run reuses
                # an existing row rather than duplicating it.
                run_model = await session.get(DBWorkflowRun, run_uuid)
                if run_model is None:
                    run_model = DBWorkflowRun(id=run_uuid, task_id=task_uuid)
                    session.add(run_model)
                run_model.status = ExecutionStatus.RUNNING.value
                run_model.plan = {"steps": [s.id for s in graph.steps.values()]}
                run_model.started_at = datetime.datetime.now(datetime.UTC)

                # Flush the run row first — without a declared relationship()
                # between WorkflowRun and TaskStep, the session's unit-of-work
                # doesn't order these inserts by FK dependency on its own, so
                # the TaskStep inserts below can otherwise land first and
                # violate task_steps_workflow_run_id_fkey.
                await session.flush()

                for step in graph.steps.values():
                    step_model = DBTaskStep(
                        id=uuid.uuid4(),
                        workflow_run_id=run_uuid,
                        step_key=step.id,
                        name=step.name,
                        dependencies=step.dependencies,
                        executor_type=step.executor_type,
                        executor_id=step.executor_id,
                        input_refs=step.input_refs,
                        status=step.status.value,
                    )
                    session.add(step_model)

                await session.commit()
        except Exception as exc:  # noqa: BLE001 — non-fatal DB checkpoint fallback
            logger.warning("Failed to save initial DB checkpoint", error=str(exc))

    async def _checkpoint_workflow_complete(
        self,
        run_uuid: uuid.UUID,
        graph: WorkflowGraph,
        status: ExecutionStatus,
        total_cost: float,
        total_latency: int,
    ) -> None:
        if self.db_session_factory is None:
            return

        try:
            from sqlalchemy import update

            from orchestrator.db.models import TaskStep as DBTaskStep
            from orchestrator.db.models import WorkflowRun as DBWorkflowRun

            completed_at = datetime.datetime.now(datetime.UTC)

            async with self.db_session_factory() as session:
                run_stmt = (
                    update(DBWorkflowRun)
                    .where(DBWorkflowRun.id == run_uuid)
                    .values(
                        status=status.value,
                        total_cost_usd=total_cost,
                        total_latency_ms=total_latency,
                        completed_at=completed_at,
                    )
                )
                await session.execute(run_stmt)

                # Also reflect each step's final outcome — otherwise
                # task_steps rows are stuck at their initial "pending"
                # snapshot from _checkpoint_workflow_init forever, and
                # GET /v1/runs/{run_id}/steps never shows real results.
                for step in graph.steps.values():
                    step_stmt = (
                        update(DBTaskStep)
                        .where(DBTaskStep.workflow_run_id == run_uuid, DBTaskStep.step_key == step.id)
                        .values(
                            status=step.status.value,
                            executor_id=step.executor_id,
                            output=step.result or ({"error": step.error} if step.error else None),
                            completed_at=completed_at,
                        )
                    )
                    await session.execute(step_stmt)

                await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to update completion DB checkpoint", error=str(exc))
