"""Unit tests for AutonomousPlanner and TemplatePlanner."""

from orchestrator.domain.enums import TaskType
from orchestrator.domain.tasks import TaskRequest, TaskRequirements
from orchestrator.orchestration.planner import AutonomousPlanner, TemplatePlanner


def test_template_planner_coding_workflow():
    planner = TemplatePlanner()
    request = TaskRequest(
        goal="Write a fibonacci function in Python",
        requirements=TaskRequirements(task_type=TaskType.CODING),
    )

    graph = planner.create_plan(request)
    assert len(graph.steps) == 2
    assert "step_1" in graph.steps
    assert "step_2" in graph.steps
    assert graph.steps["step_2"].dependencies == ["step_1"]


def test_template_planner_general_workflow():
    planner = TemplatePlanner()
    request = TaskRequest(
        goal="What is the capital of France?",
        requirements=TaskRequirements(task_type=TaskType.GENERAL),
    )

    graph = planner.create_plan(request)
    assert len(graph.steps) == 1
    assert graph.steps["step_1"].executor_type == "llm"


def test_autonomous_planner_parse_json():
    planner = AutonomousPlanner()

    raw_json = """
    ```json
    {
      "workflow_name": "test_workflow",
      "steps": [
        {
          "id": "s1",
          "name": "Step 1",
          "executor_type": "llm",
          "dependencies": [],
          "context": {"goal": "hello"}
        },
        {
          "id": "s2",
          "name": "Step 2",
          "executor_type": "python",
          "dependencies": ["s1"],
          "context": {"code": "print(123)"}
        }
      ]
    }
    ```
    """

    graph = planner._parse_and_validate_dag(raw_json)
    assert len(graph.steps) == 2
    assert graph.steps["s1"].executor_type == "llm"
    assert graph.steps["s2"].executor_type == "python"
    assert graph.steps["s2"].dependencies == ["s1"]


def test_autonomous_planner_requirements_for():
    planner = AutonomousPlanner()
    request = TaskRequest(
        goal="Process document",
        requirements=TaskRequirements(task_type=TaskType.DOCUMENT_ANALYSIS),
    )

    step = planner.fallback_planner.create_plan(request).steps["step_1"]
    reqs = planner.requirements_for(step, request)
    assert reqs.task_type == TaskType.DOCUMENT_ANALYSIS

