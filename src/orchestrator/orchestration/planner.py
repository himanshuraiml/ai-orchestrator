"""Planner module — arch doc §19, §3.2 & Phase 3.2.

Provides AutonomousPlanner (LLM-based JSON DAG generation with prompt validation)
and TemplatePlanner (deterministic rule-based fallback).
"""

import json
from pathlib import Path

from structlog import get_logger

from orchestrator.domain.enums import TaskType
from orchestrator.domain.tasks import TaskRequest, TaskRequirements
from orchestrator.domain.workflows import TaskStep
from orchestrator.orchestration.graph import WorkflowGraph
from orchestrator.providers.base import ModelGateway

logger = get_logger(__name__)

ALLOWED_EXECUTOR_TYPES = {"llm", "tool", "python", "document"}


class PlannerError(RuntimeError):
    """Base error for planner failures."""


class TemplatePlanner:
    """Deterministic rule-based planner used as fallback or template engine."""

    def create_plan(self, request: TaskRequest) -> WorkflowGraph:
        graph = WorkflowGraph(max_steps=20)
        ttype = (request.requirements.task_type if request.requirements else None) or TaskType.GENERAL
        prompt_text = getattr(request, "prompt", None) or getattr(request, "goal", "")

        if ttype == TaskType.CODING:
            s1 = TaskStep(
                id="step_1",
                name="Plan Code Structure",
                executor_type="llm",
                context={"goal": f"Plan solution for: {prompt_text}"},
            )
            s2 = TaskStep(
                id="step_2",
                name="Implement & Execute Code",
                executor_type="python",
                dependencies=["step_1"],
                input_refs=["step_1"],
                context={"code": f"# Implementation for: {prompt_text}\nprint('Execution complete')"},
            )
            graph.add_step(s1)
            graph.add_step(s2)

        elif ttype == TaskType.DOCUMENT_ANALYSIS:
            s1 = TaskStep(
                id="step_1",
                name="Process Document",
                executor_type="document",
                context={"operation": "convert", "arguments": {"text": prompt_text}},
            )
            s2 = TaskStep(
                id="step_2",
                name="Analyze Document Content",
                executor_type="llm",
                dependencies=["step_1"],
                input_refs=["step_1"],
                context={"goal": f"Analyze extracted document text: {prompt_text}"},
            )
            graph.add_step(s1)
            graph.add_step(s2)

        elif ttype == TaskType.RESEARCH:
            s1 = TaskStep(
                id="step_1",
                name="Search Information",
                executor_type="tool",
                executor_id="browser",
                context={"arguments": {"query": prompt_text}},
            )
            s2 = TaskStep(
                id="step_2",
                name="Synthesize Research",
                executor_type="llm",
                dependencies=["step_1"],
                input_refs=["step_1"],
                context={"goal": f"Synthesize research findings for: {prompt_text}"},
            )
            graph.add_step(s1)
            graph.add_step(s2)

        else:
            s1 = TaskStep(
                id="step_1",
                name="Execute Task",
                executor_type="llm",
                context={"goal": prompt_text},
            )
            graph.add_step(s1)

        return graph


class AutonomousPlanner:
    """LLM-backed dynamic DAG planner with prompt guardrails and template fallback."""

    def __init__(
        self,
        gateway: ModelGateway | None = None,
        planner_model: str = "phi4:14b-q4_K_M",
        prompt_path: Path | str | None = None,
        fallback_planner: TemplatePlanner | None = None,
    ) -> None:
        self.gateway = gateway
        self.planner_model = planner_model
        self.fallback_planner = fallback_planner or TemplatePlanner()

        if prompt_path is None:
            # Default to prompts/planner/v1.txt relative to repository root
            prompt_path = (
                Path(__file__).resolve().parents[3] / "prompts" / "planner" / "v1.txt"
            )
        self.prompt_path = Path(prompt_path)

    def _load_prompt_template(self) -> str:
        if self.prompt_path.exists():
            return self.prompt_path.read_text(encoding="utf-8")
        return "Decompose task into JSON DAG:\n{request_prompt}"

    async def create_plan(self, request: TaskRequest) -> WorkflowGraph:
        """Attempts LLM DAG planning. Falls back to TemplatePlanner on failure."""
        if self.gateway is None:
            logger.info("No gateway provided to AutonomousPlanner; using template fallback")
            return self.fallback_planner.create_plan(request)

        try:
            template = self._load_prompt_template()
            prompt_text = getattr(request, "prompt", None) or getattr(request, "goal", "")
            prompt = template.format(request_prompt=prompt_text)

            messages = [{"role": "user", "content": prompt}]
            generation = await self.gateway.generate(
                model=self.planner_model, messages=messages, temperature=0.1
            )

            graph = self._parse_and_validate_dag(generation.content)
            logger.info("AutonomousPlanner generated valid DAG", step_count=len(graph.steps))
            return graph
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "AutonomousPlanner failed; falling back to TemplatePlanner",
                error=str(exc),
            )
            return self.fallback_planner.create_plan(request)

    def _parse_and_validate_dag(self, raw_content: str) -> WorkflowGraph:
        clean = raw_content.strip()
        start_idx = clean.find("{")
        end_idx = clean.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            clean = clean[start_idx : end_idx + 1]

        data = json.loads(clean)
        steps_data = data.get("steps", [])
        if not steps_data:
            raise PlannerError("Planner output JSON contains no steps")

        graph = WorkflowGraph(max_steps=20)
        for sdata in steps_data:
            etype = sdata.get("executor_type", "llm")
            if etype not in ALLOWED_EXECUTOR_TYPES:
                raise PlannerError(f"Invalid executor_type {etype!r} in step {sdata.get('id')!r}")

            step = TaskStep(
                id=sdata["id"],
                name=sdata.get("name", sdata["id"]),
                dependencies=sdata.get("dependencies", []),
                executor_type=etype,
                executor_id=sdata.get("executor_id"),
                input_refs=sdata.get("input_refs", []),
                output_schema=sdata.get("output_schema"),
                context=sdata.get("context", {}),
            )
            graph.add_step(step)

        return graph

    def requirements_for(self, step: TaskStep, request: TaskRequest) -> TaskRequirements:
        """Formulates per-step TaskRequirements for per-step router selection."""
        step_ttype = request.requirements.task_type if request.requirements else TaskType.GENERAL
        if step.executor_type == "python":
            step_ttype = TaskType.CODING
        elif step.executor_type == "document":
            step_ttype = TaskType.DOCUMENT_ANALYSIS
        elif step.executor_type == "tool":
            step_ttype = TaskType.RESEARCH

        privacy = request.requirements.privacy if request.requirements else PrivacyLevel.NORMAL
        quality = request.requirements.quality if request.requirements else QualityLevel.STANDARD
        max_cost = request.requirements.max_cost_usd if request.requirements else None

        return TaskRequirements(
            task_type=step_ttype,
            privacy=privacy,
            quality=quality,
            max_cost_usd=max_cost,
        )

