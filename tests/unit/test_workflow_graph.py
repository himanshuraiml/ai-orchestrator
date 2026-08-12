"""Unit tests for WorkflowGraph and State Machine."""

import pytest

from orchestrator.domain.enums import ExecutionStatus
from orchestrator.domain.workflows import TaskStep
from orchestrator.orchestration.graph import (
    CycleDetectedError,
    InvalidWorkflowError,
    MaxStepsExceededError,
    WorkflowGraph,
)
from orchestrator.orchestration.state_machine import (
    InvalidStateTransitionError,
    transition_run_status,
    transition_step_status,
)


def test_workflow_graph_add_and_readiness():
    graph = WorkflowGraph(max_steps=5)

    s1 = TaskStep(id="s1", name="Step 1")
    s2 = TaskStep(id="s2", name="Step 2", dependencies=["s1"])

    graph.add_step(s1)
    graph.add_step(s2)

    completed = set()
    ready = graph.ready_steps(completed)
    assert len(ready) == 1
    assert ready[0].id == "s1"

    completed.add("s1")
    ready_2 = graph.ready_steps(completed)
    assert len(ready_2) == 1
    assert ready_2[0].id == "s2"

    completed.add("s2")
    assert graph.is_complete(completed) is True


def test_workflow_graph_cycle_detection():
    graph = WorkflowGraph()

    s1 = TaskStep(id="s1", name="Step 1", dependencies=["s2"])
    s2 = TaskStep(id="s2", name="Step 2", dependencies=["s1"])

    graph.steps["s1"] = s1
    graph.steps["s2"] = s2

    with pytest.raises(CycleDetectedError):
        graph.validate()


def test_workflow_graph_max_steps():
    graph = WorkflowGraph(max_steps=2)

    graph.add_step(TaskStep(id="s1", name="Step 1"))
    graph.add_step(TaskStep(id="s2", name="Step 2"))

    with pytest.raises(MaxStepsExceededError):
        graph.add_step(TaskStep(id="s3", name="Step 3"))


def test_workflow_graph_unknown_dependency():
    graph = WorkflowGraph()

    s1 = TaskStep(id="s1", name="Step 1", dependencies=["unknown_id"])
    with pytest.raises(InvalidWorkflowError):
        graph.add_step(s1)


def test_state_machine_transitions():
    # Valid step transition
    assert transition_step_status(ExecutionStatus.PENDING, ExecutionStatus.RUNNING) == ExecutionStatus.RUNNING
    assert transition_step_status(ExecutionStatus.RUNNING, ExecutionStatus.SUCCEEDED) == ExecutionStatus.SUCCEEDED

    # Invalid step transition (SUCCEEDED -> RUNNING)
    with pytest.raises(InvalidStateTransitionError):
        transition_step_status(ExecutionStatus.SUCCEEDED, ExecutionStatus.RUNNING)

    # Valid run transition
    assert transition_run_status(ExecutionStatus.PENDING, ExecutionStatus.RUNNING) == ExecutionStatus.RUNNING
