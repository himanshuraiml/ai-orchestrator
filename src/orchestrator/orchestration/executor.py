"""Executor abstraction — arch doc §22 / tasks.md 2.4. Models and tools
share one interface so the (Phase 3) orchestrator doesn't need to know
provider/tool details, just how to call `execute(step, context)`.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field

from orchestrator.domain.models import ModelProfile
from orchestrator.domain.workflows import TaskStep
from orchestrator.providers.base import ModelGateway
from orchestrator.tools.adapters.base import ToolAdapter
from orchestrator.tools.router import ToolRouter


@dataclass
class ExecutionResult:
    success: bool
    output: dict = field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None


class Executor(ABC):
    @abstractmethod
    async def execute(self, step: TaskStep, context: dict) -> ExecutionResult:
        raise NotImplementedError


class LLMExecutor(Executor):
    """`step.executor_id` names a model id in `model_registry`; `context`
    supplies either `messages` directly or a `goal` string to wrap as one.
    """

    def __init__(
        self,
        gateway_resolver: Callable[[str], ModelGateway],
        model_registry: dict[str, ModelProfile],
    ) -> None:
        self.gateway_resolver = gateway_resolver
        self.model_registry = model_registry

    async def execute(self, step: TaskStep, context: dict) -> ExecutionResult:
        model = self.model_registry.get(step.executor_id) if step.executor_id else None
        if model is None:
            return ExecutionResult(
                success=False,
                error_type="UnknownModel",
                error_message=f"No model registered for id {step.executor_id!r}",
            )

        gateway = self.gateway_resolver(model.provider)
        messages = context.get("messages") or [{"role": "user", "content": context.get("goal", "")}]

        try:
            generation = await gateway.generate(model=model.model_name, messages=messages)
        except Exception as exc:  # noqa: BLE001 — provider errors vary widely, surface uniformly
            return ExecutionResult(success=False, error_type=type(exc).__name__, error_message=str(exc))

        return ExecutionResult(
            success=True,
            output={"content": generation.content},
            cost_usd=generation.cost_usd,
            latency_ms=generation.latency_ms,
        )


class ToolExecutor(Executor):
    """`step.executor_id` names a tool id directly; if unset, `tool_router`
    picks one from `context["required_capabilities"]`. Arguments for the
    call come from `context["arguments"]`.
    """

    def __init__(
        self, adapters: dict[str, ToolAdapter], tool_router: ToolRouter | None = None
    ) -> None:
        self.adapters = adapters
        self.tool_router = tool_router

    async def execute(self, step: TaskStep, context: dict) -> ExecutionResult:
        tool_id = step.executor_id

        if tool_id is None:
            if self.tool_router is None:
                return ExecutionResult(
                    success=False,
                    error_type="NoToolSelected",
                    error_message="No tool_router configured to auto-select a tool",
                )
            try:
                tool_id = self.tool_router.select(context.get("required_capabilities", set())).id
            except Exception as exc:  # noqa: BLE001 — NoSuitableToolError and friends
                return ExecutionResult(success=False, error_type=type(exc).__name__, error_message=str(exc))
        elif self.tool_router is not None:
            # Explicit executor_id (e.g. planner-selected) still needs a
            # policy check — auto-selection already filters through
            # tool_router.candidates(), but a direct pick must too.
            allowed = any(tool.id == tool_id for tool in self.tool_router.candidates(set()))
            if not allowed:
                return ExecutionResult(
                    success=False,
                    error_type="ToolNotPermitted",
                    error_message=f"Tool {tool_id!r} is not permitted by current policy",
                )

        adapter = self.adapters.get(tool_id)
        if adapter is None:
            return ExecutionResult(
                success=False,
                error_type="UnknownTool",
                error_message=f"No adapter registered for tool {tool_id!r}",
            )

        try:
            output = await adapter.invoke(context.get("arguments", {}))
        except Exception as exc:  # noqa: BLE001 — adapter failures vary widely, surface uniformly
            return ExecutionResult(success=False, error_type=type(exc).__name__, error_message=str(exc))

        return ExecutionResult(success=True, output=output)


class PythonExecutor(Executor):
    """Pinned to the python adapter — arch doc calls this out as its own
    executor type (deterministic verification, arch doc §50: Python > LLM).
    `context["code"]` is required; `context["timeout_seconds"]` optional.
    """

    def __init__(self, adapter: ToolAdapter) -> None:
        self.adapter = adapter

    async def execute(self, step: TaskStep, context: dict) -> ExecutionResult:
        arguments = {"code": context["code"]}
        if "timeout_seconds" in context:
            arguments["timeout_seconds"] = context["timeout_seconds"]

        try:
            output = await self.adapter.invoke(arguments)
        except Exception as exc:  # noqa: BLE001 — sandbox/adapter failures vary widely
            return ExecutionResult(success=False, error_type=type(exc).__name__, error_message=str(exc))

        success = output.get("returncode") == 0 and not output.get("timed_out", False)
        return ExecutionResult(success=success, output=output)


class DocumentExecutor(Executor):
    """Wraps OCR + Pandoc; `context["operation"]` selects which ("ocr" or
    "convert", default "convert"), `context["arguments"]` are its call args.
    """

    def __init__(self, ocr_adapter: ToolAdapter, pandoc_adapter: ToolAdapter) -> None:
        self.ocr_adapter = ocr_adapter
        self.pandoc_adapter = pandoc_adapter

    async def execute(self, step: TaskStep, context: dict) -> ExecutionResult:
        operation = context.get("operation", "convert")
        adapter = self.ocr_adapter if operation == "ocr" else self.pandoc_adapter

        try:
            output = await adapter.invoke(context.get("arguments", {}))
        except Exception as exc:  # noqa: BLE001 — adapter failures vary widely, surface uniformly
            return ExecutionResult(success=False, error_type=type(exc).__name__, error_message=str(exc))

        return ExecutionResult(success=output.get("success", True), output=output)
