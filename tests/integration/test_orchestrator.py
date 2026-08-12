"""Integration tests for StepScheduler, Orchestrator, and end-to-end DAG execution."""

import pytest

from orchestrator.domain.enums import ExecutionStatus, TaskType
from orchestrator.domain.tasks import TaskRequest, TaskRequirements
from orchestrator.domain.workflows import TaskStep
from orchestrator.orchestration.executor import ExecutionResult, Executor
from orchestrator.orchestration.graph import WorkflowGraph
from orchestrator.orchestration.orchestrator import EventBroadcaster, Orchestrator
from orchestrator.orchestration.planner import TemplatePlanner
from orchestrator.orchestration.scheduler import StepScheduler


class MockExecutor(Executor):
    def __init__(self, return_value: str = "mock output") -> None:
        self.return_value = return_value

    async def execute(self, step: TaskStep, context: dict) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            output={"result": f"{self.return_value} for {step.id}"},
            cost_usd=0.01,
            latency_ms=50,
        )


@pytest.mark.asyncio
async def test_scheduler_dag_execution():
    mock_exec = MockExecutor("done")
    executors = {"llm": mock_exec, "python": mock_exec, "tool": mock_exec, "document": mock_exec}

    scheduler = StepScheduler(executors=executors, default_executor=mock_exec)

    graph = WorkflowGraph()
    s1 = TaskStep(id="s1", name="Step 1", executor_type="llm")
    s2 = TaskStep(id="s2", name="Step 2", executor_type="python", dependencies=["s1"])
    graph.add_step(s1)
    graph.add_step(s2)

    results = await scheduler.run_dag(graph)

    assert "s1" in results
    assert "s2" in results
    assert s1.status == ExecutionStatus.SUCCEEDED
    assert s2.status == ExecutionStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_orchestrator_end_to_end():
    mock_exec = MockExecutor("orchestrator_result")
    executors = {"llm": mock_exec, "python": mock_exec, "tool": mock_exec, "document": mock_exec}

    scheduler = StepScheduler(executors=executors, default_executor=mock_exec)
    planner = TemplatePlanner()
    orchestrator = Orchestrator(planner=planner, scheduler=scheduler, event_broadcaster=EventBroadcaster())

    request = TaskRequest(
        goal="Perform analysis task",
        requirements=TaskRequirements(task_type=TaskType.RESEARCH),
    )

    run_output = await orchestrator.run(request)

    assert run_output["status"] == "succeeded"
    assert "results" in run_output
    assert run_output["total_cost_usd"] > 0
