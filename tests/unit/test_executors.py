
from orchestrator.domain.models import ModelProfile
from orchestrator.domain.workflows import TaskStep
from orchestrator.orchestration.executor import (
    DocumentExecutor,
    LLMExecutor,
    PythonExecutor,
    ToolExecutor,
)
from orchestrator.providers.base import GenerationResult, ModelGateway
from orchestrator.tools.adapters.base import ToolAdapter
from orchestrator.tools.router import ToolRouter


class StubGateway(ModelGateway):
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def generate(self, **kwargs) -> GenerationResult:
        if self.fail:
            raise RuntimeError("provider unavailable")
        return GenerationResult(content="stub reply", cost_usd=0.01, latency_ms=42)


class StubAdapter(ToolAdapter):
    def __init__(self, *, output: dict | None = None, fail: bool = False) -> None:
        self.output = output or {}
        self.fail = fail
        self.received: dict | None = None

    async def invoke(self, arguments: dict) -> dict:
        self.received = arguments
        if self.fail:
            raise RuntimeError("adapter failed")
        return self.output


def make_model(id: str) -> ModelProfile:
    return ModelProfile(
        id=id,
        provider="test",
        model_name=id,
        capabilities=frozenset({"coding"}),
        context_window=100_000,
        quality_score=0.8,
        cost_score=0.8,
        latency_score=0.8,
        privacy_class="cloud",
    )


async def test_llm_executor_returns_content_on_success():
    model = make_model("stub_model")
    executor = LLMExecutor(gateway_resolver=lambda _provider: StubGateway(), model_registry={"stub_model": model})
    step = TaskStep(id="s1", name="respond", executor_type="llm", executor_id="stub_model")

    result = await executor.execute(step, {"goal": "hi"})

    assert result.success
    assert result.output["content"] == "stub reply"
    assert result.cost_usd == 0.01


async def test_llm_executor_fails_on_unknown_model():
    executor = LLMExecutor(gateway_resolver=lambda _provider: StubGateway(), model_registry={})
    step = TaskStep(id="s1", name="respond", executor_type="llm", executor_id="missing")

    result = await executor.execute(step, {"goal": "hi"})

    assert not result.success
    assert result.error_type == "UnknownModel"


async def test_llm_executor_captures_gateway_exception():
    model = make_model("stub_model")
    executor = LLMExecutor(
        gateway_resolver=lambda _provider: StubGateway(fail=True), model_registry={"stub_model": model}
    )
    step = TaskStep(id="s1", name="respond", executor_type="llm", executor_id="stub_model")

    result = await executor.execute(step, {"goal": "hi"})

    assert not result.success
    assert result.error_type == "RuntimeError"


async def test_tool_executor_dispatches_by_explicit_executor_id():
    adapter = StubAdapter(output={"ok": True})
    executor = ToolExecutor(adapters={"python": adapter})
    step = TaskStep(id="s1", name="run", executor_type="tool", executor_id="python")

    result = await executor.execute(step, {"arguments": {"code": "print(1)"}})

    assert result.success
    assert result.output == {"ok": True}
    assert adapter.received == {"code": "print(1)"}


async def test_tool_executor_auto_selects_via_router():
    adapter = StubAdapter(output={"ok": True})
    from orchestrator.domain.tools import ToolProfile
    from orchestrator.routing.policies import PolicyEngine

    tool = ToolProfile(id="python", name="python", capabilities=frozenset({"code_execution"}))
    router = ToolRouter([tool], PolicyEngine(policies_config={}))
    executor = ToolExecutor(adapters={"python": adapter}, tool_router=router)
    step = TaskStep(id="s1", name="run", executor_type="tool", executor_id=None)

    result = await executor.execute(step, {"required_capabilities": {"code_execution"}, "arguments": {}})

    assert result.success


async def test_tool_executor_unknown_tool_fails_cleanly():
    executor = ToolExecutor(adapters={})
    step = TaskStep(id="s1", name="run", executor_type="tool", executor_id="nope")

    result = await executor.execute(step, {})

    assert not result.success
    assert result.error_type == "UnknownTool"


async def test_python_executor_success_when_returncode_zero():
    adapter = StubAdapter(output={"stdout": "2\n", "returncode": 0, "timed_out": False})
    executor = PythonExecutor(adapter)
    step = TaskStep(id="s1", name="run", executor_type="python", executor_id="python")

    result = await executor.execute(step, {"code": "print(1+1)"})

    assert result.success
    assert adapter.received == {"code": "print(1+1)"}


async def test_python_executor_fails_on_nonzero_returncode():
    adapter = StubAdapter(output={"stdout": "", "returncode": 1, "timed_out": False})
    executor = PythonExecutor(adapter)
    step = TaskStep(id="s1", name="run", executor_type="python", executor_id="python")

    result = await executor.execute(step, {"code": "raise SystemExit(1)"})

    assert not result.success


async def test_document_executor_routes_ocr_operation():
    ocr_adapter = StubAdapter(output={"text": "hi", "success": True})
    pandoc_adapter = StubAdapter(output={"success": True})
    executor = DocumentExecutor(ocr_adapter, pandoc_adapter)
    step = TaskStep(id="s1", name="doc", executor_type="document", executor_id=None)

    result = await executor.execute(step, {"operation": "ocr", "arguments": {"file_path": "x.pdf"}})

    assert result.success
    assert ocr_adapter.received == {"file_path": "x.pdf"}
    assert pandoc_adapter.received is None


async def test_document_executor_defaults_to_convert_operation():
    ocr_adapter = StubAdapter(output={})
    pandoc_adapter = StubAdapter(output={"success": True})
    executor = DocumentExecutor(ocr_adapter, pandoc_adapter)
    step = TaskStep(id="s1", name="doc", executor_type="document", executor_id=None)

    result = await executor.execute(step, {"arguments": {"input_path": "a.md", "output_path": "a.docx"}})

    assert result.success
    assert pandoc_adapter.received == {"input_path": "a.md", "output_path": "a.docx"}


async def test_document_executor_captures_adapter_failure():
    ocr_adapter = StubAdapter(fail=True)
    pandoc_adapter = StubAdapter(output={})
    executor = DocumentExecutor(ocr_adapter, pandoc_adapter)
    step = TaskStep(id="s1", name="doc", executor_type="document", executor_id=None)

    result = await executor.execute(step, {"operation": "ocr", "arguments": {}})

    assert not result.success
    assert result.error_type == "RuntimeError"
