# Multi-LLM AI Orchestration Platform
## Production-Grade Architecture, Folder Structure, Database Schema, Python Classes, Routing Algorithm, and Docker Compose

> **Status:** Reference architecture / implementation blueprint  
> **Target:** Python + FastAPI + PostgreSQL + Redis + LiteLLM + MCP + local LLM runtime + Docker  
> **Primary goal:** Route each task to the best model/tool, allow model switching during workflows, enforce privacy and tool permissions, and produce observable/verifiable results.

---

## 1. Executive Summary

The system is an **AI orchestration layer** rather than a single-agent chatbot.

It accepts a user goal, converts it into a structured task, plans the required steps, selects models and tools dynamically, executes those steps, verifies outputs, records the run, and returns the final artifact.

The core principle is:

```text
User goal
   ↓
Task understanding
   ↓
Policy + capability requirements
   ↓
Plan / task graph
   ↓
Model router + tool router
   ↓
Execution
   ↓
Verification
   ↓
Artifact generation
   ↓
Telemetry + feedback
```

The system should not hard-code "coding = Claude" or "documents = Gemini" throughout the codebase. Instead, models advertise capabilities and the router selects among eligible executors based on task requirements, quality, cost, latency, privacy, reliability, and historical performance.

### Example workflow

```text
"Analyze this scanned annual report and produce a DOCX executive summary."

                ┌──────────────┐
                │ User Request │
                └──────┬───────┘
                       ↓
                Task Classifier
                       ↓
                Workflow Planner
                       ↓
        ┌──────────────┼──────────────┐
        ↓              ↓              ↓
      OCR           Document        Metadata
     Tool          Extraction       Parsing
        ↓              ↓
        └──────────────┘
                       ↓
              Long-context LLM
                       ↓
                    Python
              calculations/checks
                       ↓
                 Writing LLM
                       ↓
                 Review LLM
                       ↓
               Pandoc / DOCX
                       ↓
                  Final file
```

---

# 2. Design Goals

## Functional goals

1. Support multiple cloud LLM providers.
2. Support local LLMs.
3. Support deterministic tools such as Python, OCR, Pandoc, Git, browser/search, and file operations.
4. Select different models for different tasks.
5. Switch models between workflow steps.
6. Support multi-step workflows.
7. Support parallel execution where dependencies allow it.
8. Verify important outputs.
9. Enforce privacy and tool policies.
10. Track cost, latency, model choice, failures, and outcomes.
11. Keep provider-specific APIs behind an abstraction.
12. Allow new models/tools to be added without rewriting the orchestrator.

## Non-goals for v1

- Fully autonomous unrestricted agents.
- Unbounded model-to-model conversations.
- Automatic execution of arbitrary shell commands.
- Giving every model access to every tool.
- Training a routing model from day one.

Start deterministic, observable, and permissioned. Add learned routing later.

---

# 3. High-Level Production Architecture

```text
                                  ┌──────────────────────┐
                                  │       Clients        │
                                  │ Web / CLI / IDE / API│
                                  └───────────┬──────────┘
                                              │
                                              ▼
                                  ┌──────────────────────┐
                                  │      API Gateway     │
                                  │ Auth / Rate Limits   │
                                  └───────────┬──────────┘
                                              │
                                              ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                           ORCHESTRATION SERVICE                           │
│                                                                          │
│  Task Parser → Policy Engine → Planner → Router → Executor → Verifier  │
│                        │             │         │                         │
│                        └─────────────┴─────────┴──── Observability       │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
             ┌──────────────────┼───────────────────┐
             │                  │                   │
             ▼                  ▼                   ▼
     ┌──────────────┐   ┌──────────────┐    ┌──────────────┐
     │ Model Gateway│   │  Tool Runtime │    │ Context/Memory│
     │   LiteLLM    │   │     MCP       │    │ PostgreSQL    │
     └──────┬───────┘   └──────┬───────┘    │ pgvector      │
            │                  │             └──────────────┘
      ┌─────┼──────┐     ┌─────┼───────────────┐
      │     │      │     │     │       │       │
      ▼     ▼      ▼     ▼     ▼       ▼       ▼
    OpenAI Claude Gemini Python  OCR   Pandoc  Browser
                           │
                           ▼
                      Local LLM Runtime
```

---

# 4. Service Boundaries

A production deployment should begin as a **modular monolith** rather than immediately splitting everything into microservices.

Recommended logical services:

| Component | Responsibility |
|---|---|
| API | Authentication, request validation, streaming |
| Orchestrator | Workflow state machine |
| Planner | Converts goal into task graph |
| Router | Model/tool selection |
| Executor | Runs tasks |
| Verifier | Validates outputs |
| Model Gateway | Provider abstraction / retries / fallbacks |
| Tool Gateway | MCP tool discovery and invocation |
| Context Manager | Files, chunks, retrieval, context assembly |
| Policy Engine | Privacy, permissions, budgets |
| Artifact Manager | Files and generated outputs |
| Telemetry | Logs, metrics, traces, cost |
| Worker | Async/background execution |

These can initially live in one Python application with worker processes.

---

# 5. Recommended Technology Stack

```text
Python             3.12+
FastAPI             HTTP API
Pydantic            schemas / validation
SQLAlchemy          database ORM
Alembic             migrations
PostgreSQL          primary database
pgvector            vector search
Redis               queues / cache / locks
Celery or Arq       background jobs
LiteLLM              LLM gateway
MCP                  tool protocol
Ollama or equivalent local runtime
Pandoc               document conversion
LibreOffice          office rendering/conversion where required
Tesseract / OCR engine
PyMuPDF              PDF parsing
httpx                async HTTP
structlog            structured logging
OpenTelemetry        traces / metrics
Prometheus            metrics
Grafana               dashboards
Docker                packaging
```

A queue such as Celery/Arq should be introduced when workflows can exceed normal HTTP request lifetimes.

---

# 6. Repository / Folder Structure

Recommended production repository:

```text
ai-orchestrator/
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── docker-compose.yml
├── docker-compose.prod.yml
├── Makefile
│
├── apps/
│   ├── api/
│   │   └── main.py
│   └── worker/
│       └── main.py
│
├── src/
│   └── orchestrator/
│       ├── __init__.py
│       │
│       ├── config/
│       │   ├── settings.py
│       │   ├── logging.py
│       │   └── model_registry.yaml
│       │
│       ├── api/
│       │   ├── deps.py
│       │   ├── middleware.py
│       │   └── routes/
│       │       ├── tasks.py
│       │       ├── runs.py
│       │       ├── files.py
│       │       └── health.py
│       │
│       ├── domain/
│       │   ├── enums.py
│       │   ├── tasks.py
│       │   ├── models.py
│       │   ├── tools.py
│       │   ├── workflows.py
│       │   ├── artifacts.py
│       │   └── policies.py
│       │
│       ├── orchestration/
│       │   ├── orchestrator.py
│       │   ├── planner.py
│       │   ├── executor.py
│       │   ├── scheduler.py
│       │   ├── state_machine.py
│       │   └── workflow_graph.py
│       │
│       ├── routing/
│       │   ├── router.py
│       │   ├── capability_matcher.py
│       │   ├── scoring.py
│       │   ├── policies.py
│       │   ├── fallback.py
│       │   └── learned_router.py
│       │
│       ├── providers/
│       │   ├── base.py
│       │   ├── litellm_gateway.py
│       │   ├── local_gateway.py
│       │   └── health.py
│       │
│       ├── tools/
│       │   ├── registry.py
│       │   ├── mcp_client.py
│       │   ├── permissions.py
│       │   └── adapters/
│       │       ├── python.py
│       │       ├── ocr.py
│       │       ├── pandoc.py
│       │       ├── filesystem.py
│       │       └── browser.py
│       │
│       ├── context/
│       │   ├── manager.py
│       │   ├── chunker.py
│       │   ├── embeddings.py
│       │   ├── retriever.py
│       │   └── assembler.py
│       │
│       ├── verification/
│       │   ├── verifier.py
│       │   ├── validators.py
│       │   ├── factual.py
│       │   ├── structured.py
│       │   └── artifacts.py
│       │
│       ├── memory/
│       │   ├── short_term.py
│       │   ├── long_term.py
│       │   └── preferences.py
│       │
│       ├── artifacts/
│       │   ├── storage.py
│       │   ├── metadata.py
│       │   └── converters.py
│       │
│       ├── db/
│       │   ├── base.py
│       │   ├── session.py
│       │   ├── models.py
│       │   └── repositories/
│       │       ├── tasks.py
│       │       ├── runs.py
│       │       ├── models.py
│       │       └── artifacts.py
│       │
│       ├── observability/
│       │   ├── metrics.py
│       │   ├── tracing.py
│       │   └── events.py
│       │
│       └── security/
│           ├── auth.py
│           ├── secrets.py
│           ├── sandbox.py
│           └── redaction.py
│
├── migrations/
│   └── versions/
│
├── configs/
│   ├── models.yaml
│   ├── tools.yaml
│   ├── policies.yaml
│   └── routing.yaml
│
├── prompts/
│   ├── planner/
│   ├── classifier/
│   ├── verifier/
│   └── workers/
│
├── tools/
│   ├── mcp/
│   │   ├── python/
│   │   ├── ocr/
│   │   └── documents/
│   └── sandbox/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── routing/
│   ├── security/
│   └── e2e/
│
├── scripts/
│   ├── seed_models.py
│   ├── seed_tools.py
│   └── healthcheck.py
│
└── docs/
    ├── architecture.md
    ├── routing.md
    ├── security.md
    └── operations.md
```

---

# 7. Core Domain Objects

The main abstractions should be:

```text
Task
Workflow
TaskStep
Model
ModelCapability
Tool
ToolCapability
Execution
Artifact
Policy
Evaluation
```

The critical distinction is:

```text
Task != Model
Task != Tool
```

A task declares requirements.

A model/tool declares capabilities.

The router matches them.

---

# 8. Python Domain Classes

## 8.1 Enums

```python
from enum import StrEnum


class TaskType(StrEnum):
    BRAINSTORMING = "brainstorming"
    CODING = "coding"
    DOCUMENT_ANALYSIS = "document_analysis"
    WRITING = "writing"
    RESEARCH = "research"
    DATA_ANALYSIS = "data_analysis"
    EXTRACTION = "extraction"
    CLASSIFICATION = "classification"
    TRANSFORMATION = "transformation"
    GENERAL = "general"


class PrivacyLevel(StrEnum):
    PUBLIC = "public"
    NORMAL = "normal"
    SENSITIVE = "sensitive"
    PRIVATE = "private"


class QualityLevel(StrEnum):
    LOW = "low"
    STANDARD = "standard"
    HIGH = "high"
    CRITICAL = "critical"


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_APPROVAL = "waiting_approval"
```

---

# 9. Task Specification

```python
from pydantic import BaseModel, Field


class TaskRequirements(BaseModel):
    task_type: TaskType = TaskType.GENERAL

    required_capabilities: set[str] = Field(default_factory=set)

    context_tokens: int = 0

    privacy: PrivacyLevel = PrivacyLevel.NORMAL
    quality: QualityLevel = QualityLevel.STANDARD

    max_cost_usd: float | None = None
    max_latency_ms: int | None = None

    needs_tools: bool = False
    needs_web: bool = False
    needs_code_execution: bool = False
    needs_file_access: bool = False

    output_format: str | None = None
```

The user-facing request becomes:

```python
class TaskRequest(BaseModel):
    goal: str
    requirements: TaskRequirements
    file_ids: list[str] = []
    metadata: dict = {}
```

---

# 10. Model Registry

Models should be configuration-driven.

Example:

```yaml
models:

  gpt_primary:
    provider: openai
    model: <configured-model-id>
    capabilities:
      - reasoning
      - brainstorming
      - writing
      - vision
      - structured_output
    context_window: 100000
    quality_score: 0.95
    cost_score: 0.70
    latency_score: 0.80
    privacy: cloud
    enabled: true

  claude_coding:
    provider: anthropic
    model: <configured-model-id>
    capabilities:
      - coding
      - reasoning
      - code_review
      - long_context
    context_window: 100000
    quality_score: 0.96
    cost_score: 0.70
    latency_score: 0.80
    privacy: cloud
    enabled: true

  gemini_documents:
    provider: google
    model: <configured-model-id>
    capabilities:
      - document_analysis
      - multimodal
      - long_context
      - extraction
    context_window: 100000
    quality_score: 0.94
    cost_score: 0.75
    latency_score: 0.75
    privacy: cloud
    enabled: true

  local_general:
    provider: ollama
    model: <configured-local-model>
    capabilities:
      - classification
      - extraction
      - summarization
      - private
    context_window: 32000
    quality_score: 0.72
    cost_score: 1.0
    latency_score: 0.85
    privacy: local
    enabled: true
```

Do not put provider API keys in this file.

---

# 11. Model Python Classes

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    id: str
    provider: str
    model_name: str

    capabilities: frozenset[str]

    context_window: int

    quality_score: float
    cost_score: float
    latency_score: float

    privacy_class: str

    enabled: bool = True
```

---

# 12. Tool Profiles

```python
@dataclass(frozen=True)
class ToolProfile:
    id: str
    name: str

    capabilities: frozenset[str]

    requires_network: bool = False
    requires_filesystem: bool = False
    requires_approval: bool = False

    risk_level: str = "low"
```

Examples:

```text
python
  capabilities:
    computation
    data_analysis
    code_execution

ocr
  capabilities:
    image_to_text
    pdf_to_text

pandoc
  capabilities:
    document_conversion

browser
  capabilities:
    web_search
    web_navigation
```

---

# 13. Model Provider Interface

Keep provider-specific code behind an interface.

```python
from abc import ABC, abstractmethod


class ModelGateway(ABC):

    @abstractmethod
    async def generate(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        response_format: dict | None = None,
    ):
        raise NotImplementedError
```

LiteLLM becomes an implementation:

```python
class LiteLLMGateway(ModelGateway):

    async def generate(
        self,
        *,
        model,
        messages,
        tools=None,
        temperature=None,
        response_format=None,
    ):
        # Call LiteLLM here.
        # Keep provider-specific logic out of the orchestrator.
        ...
```

---

# 14. Model Router

The router should be deterministic first.

```python
class ModelRouter:

    def __init__(
        self,
        models: list[ModelProfile],
        scorer,
        policy_engine,
    ):
        self.models = models
        self.scorer = scorer
        self.policy_engine = policy_engine

    def route(self, requirements: TaskRequirements) -> ModelProfile:

        candidates = [
            model
            for model in self.models
            if model.enabled
        ]

        candidates = [
            model
            for model in candidates
            if requirements.required_capabilities
               <= model.capabilities
        ]

        candidates = [
            model
            for model in candidates
            if self.policy_engine.model_allowed(
                model,
                requirements,
            )
        ]

        if not candidates:
            raise RuntimeError(
                "No eligible model found"
            )

        return max(
            candidates,
            key=lambda model:
                self.scorer.score(model, requirements)
        )
```

---

# 15. Routing Algorithm

A useful v1 score:

```text
score =
    capability_match
  × quality_weight
  × reliability_weight
  + cost_score × cost_weight
  + latency_score × latency_weight
  + historical_success × history_weight
```

Subject to hard constraints:

```text
privacy
context window
required capability
budget
latency
tool requirements
provider availability
```

Recommended conceptual implementation:

```python
class ModelScorer:

    def score(
        self,
        model: ModelProfile,
        req: TaskRequirements,
        historical_success: float = 0.5,
    ) -> float:

        capability_match = (
            len(
                req.required_capabilities
                & model.capabilities
            )
            / max(len(req.required_capabilities), 1)
        )

        quality_weight = {
            QualityLevel.LOW: 0.10,
            QualityLevel.STANDARD: 0.30,
            QualityLevel.HIGH: 0.50,
            QualityLevel.CRITICAL: 0.65,
        }[req.quality]

        cost_weight = 0.15
        latency_weight = 0.10
        history_weight = 0.15

        return (
            capability_match * 10.0
            + model.quality_score * quality_weight * 10
            + model.cost_score * cost_weight * 10
            + model.latency_score * latency_weight * 10
            + historical_success * history_weight * 10
        )
```

For production, normalize scores and make weights configuration-driven.

---

# 16. Hard Constraints vs Soft Preferences

This distinction is essential.

## Hard constraints

The router must reject a model if:

```text
privacy requirement cannot be satisfied
context window too small
required capability missing
model disabled
budget exceeded
required tool integration unavailable
```

## Soft preferences

The router may trade off:

```text
quality
cost
latency
historical reliability
provider diversity
```

Example:

```text
Task:
privacy = PRIVATE

Gemini:
cloud → REJECT

Claude:
cloud → REJECT

Local:
local → eligible
```

Privacy is a hard constraint.

Cost is usually a soft preference.

---

# 17. Routing Configuration

```yaml
routing:

  weights:

    quality:
      low: 0.15
      standard: 0.30
      high: 0.50
      critical: 0.70

    cost: 0.15
    latency: 0.10
    reliability: 0.20
    historical_success: 0.15

  task_preferences:

    brainstorming:
      capabilities:
        - brainstorming

    coding:
      capabilities:
        - coding
        - reasoning

    document_analysis:
      capabilities:
        - document_analysis
        - long_context

    private:
      privacy: local

  fallback:
    max_attempts: 3
    provider_diversity: true
```

---

# 18. Fallback Strategy

Never blindly retry the same failed model.

Use failure classification.

```text
Model timeout
   ↓
retry same provider once

Provider unavailable
   ↓
switch provider

Context too large
   ↓
compress / retrieve / chunk

Tool failure
   ↓
retry tool / alternate tool

Invalid output
   ↓
repair / retry with stricter schema

Quality failure
   ↓
escalate to stronger model
```

Example:

```python
class FallbackManager:

    def next_candidate(
        self,
        candidates,
        failed_model,
        error_type,
    ):
        remaining = [
            m for m in candidates
            if m.id != failed_model.id
        ]

        if error_type == "provider_failure":
            remaining = [
                m for m in remaining
                if m.provider != failed_model.provider
            ]

        return remaining[0] if remaining else None
```

---

# 19. Task Planning

The planner converts a user goal into a DAG.

Example:

```text
Task:
"Create a report from this scanned PDF."

DAG:

extract_pdf
    ↓
ocr
    ↓
parse
    ├───────────────┐
    ↓               ↓
analyze          calculate
    └───────┬───────┘
            ↓
          draft
            ↓
         verify
            ↓
          export
```

Python representation:

```python
@dataclass
class TaskStep:
    id: str
    name: str

    dependencies: list[str]

    executor_type: str
    executor_id: str | None

    input_refs: list[str]
    output_schema: dict | None

    retry_limit: int = 2
```

---

# 20. Workflow Graph

```python
class WorkflowGraph:

    def __init__(self):
        self.steps: dict[str, TaskStep] = {}

    def add_step(self, step: TaskStep):
        self.steps[step.id] = step

    def ready_steps(
        self,
        completed: set[str],
    ) -> list[TaskStep]:

        return [
            step
            for step in self.steps.values()
            if step.id not in completed
            and all(
                dep in completed
                for dep in step.dependencies
            )
        ]
```

This enables parallel execution.

For example:

```text
extract
   ↓
parse
 ┌─┴────────────┐
 ↓              ↓
analysis      calculations
 └──────┬───────┘
        ↓
      report
```

Analysis and calculations can run concurrently.

---

# 21. Orchestrator

```python
class Orchestrator:

    def __init__(
        self,
        planner,
        router,
        executor,
        verifier,
        policy_engine,
    ):
        self.planner = planner
        self.router = router
        self.executor = executor
        self.verifier = verifier
        self.policy_engine = policy_engine

    async def run(self, request: TaskRequest):

        self.policy_engine.validate_request(request)

        workflow = await self.planner.create_plan(
            request
        )

        completed = set()

        while not workflow.is_complete(completed):

            ready = workflow.ready_steps(completed)

            if not ready:
                raise RuntimeError(
                    "Workflow deadlock"
                )

            for step in ready:

                requirements = (
                    self.planner.requirements_for(
                        step,
                        request,
                    )
                )

                executor = self.router.select_executor(
                    requirements
                )

                result = await self.executor.execute(
                    step=step,
                    executor=executor,
                )

                verification = await self.verifier.verify(
                    step,
                    result,
                )

                if not verification.success:
                    await self.executor.repair(
                        step,
                        verification,
                    )
                else:
                    completed.add(step.id)

        return workflow.final_result()
```

---

# 22. Executor Abstraction

Models and tools should share an executor interface.

```python
class Executor(ABC):

    @abstractmethod
    async def execute(
        self,
        step: TaskStep,
        context: dict,
    ):
        raise NotImplementedError
```

Implementations:

```text
LLMExecutor
ToolExecutor
PythonExecutor
DocumentExecutor
```

The orchestrator doesn't need to know provider details.

---

# 23. Tool Router

The same capability model should apply to tools.

```python
class ToolRouter:

    def __init__(
        self,
        tools: list[ToolProfile],
        policy_engine,
    ):
        self.tools = tools
        self.policy_engine = policy_engine

    def select(
        self,
        required_capabilities: set[str],
    ) -> ToolProfile:

        candidates = [
            tool
            for tool in self.tools
            if required_capabilities
               <= tool.capabilities
        ]

        candidates = [
            tool for tool in candidates
            if self.policy_engine.tool_allowed(tool)
        ]

        if not candidates:
            raise RuntimeError(
                "No suitable tool"
            )

        return candidates[0]
```

---

# 24. MCP Integration

Treat MCP as the standardized tool boundary.

```text
Orchestrator
     │
     ▼
MCP Client
     │
     ├── Python MCP Server
     ├── OCR MCP Server
     ├── Document MCP Server
     ├── Browser MCP Server
     └── Git MCP Server
```

The tool registry should maintain metadata:

```python
@dataclass
class RegisteredTool:
    id: str
    server: str
    name: str
    description: str
    input_schema: dict
    capabilities: frozenset[str]
    risk_level: str
```

Do not expose every registered tool to every model.

Use per-workflow allowlists.

---

# 25. Tool Permission Policy

Example:

```yaml
policies:

  default:

    filesystem:
      read: true
      write: false

    network:
      enabled: false

    shell:
      enabled: false

    python:
      enabled: true

  coding:

    filesystem:
      read: true
      write: true

    network:
      enabled: false

    shell:
      enabled: true

    git:
      enabled: true

  document:

    filesystem:
      read: true
      write: true

    network:
      enabled: true

    shell:
      enabled: false
```

High-risk actions should require explicit approval.

---

# 26. Python Execution Sandbox

Never execute model-generated Python directly in the main API process.

Use an isolated worker/container:

```text
Orchestrator
     ↓
Job Queue
     ↓
Sandbox Worker
     ↓
Ephemeral container
     ↓
Python
     ↓
Result artifact
```

Security controls should include:

```text
CPU limit
memory limit
execution timeout
read-only base filesystem
temporary workspace
network disabled by default
maximum output size
process limit
no host Docker socket
```

---

# 27. Context Manager

The context manager owns all context assembly.

Responsibilities:

```text
file parsing
OCR
chunking
metadata
embeddings
retrieval
summarization
context compression
token budgeting
```

Interface:

```python
class ContextManager:

    async def ingest_file(
        self,
        file_id: str,
    ):
        ...

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 10,
    ):
        ...

    async def build_context(
        self,
        query: str,
        token_budget: int,
    ):
        ...
```

---

# 28. Context Strategy

Do not send full files to every model.

Use:

```text
file
 ↓
parse
 ↓
chunk
 ↓
index
 ↓
retrieve
 ↓
rerank
 ↓
context compression
 ↓
model
```

For very large documents:

```text
document
 ↓
section summaries
 ↓
section-level analysis
 ↓
global synthesis
```

This avoids excessive context cost and makes the system model-independent.

---

# 29. Database Schema

Use PostgreSQL as the system of record.

Core tables:

```text
users
projects
tasks
task_steps
workflow_runs
executions
models
model_capabilities
tools
tool_capabilities
artifacts
documents
document_chunks
memories
evaluations
routing_events
audit_events
approvals
```

---

# 30. PostgreSQL DDL

## Users

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## Projects

```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    settings JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_projects_user
ON projects(user_id);
```

## Tasks

```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    project_id UUID REFERENCES projects(id),

    goal TEXT NOT NULL,

    task_type TEXT,
    requirements JSONB NOT NULL DEFAULT '{}',

    status TEXT NOT NULL DEFAULT 'pending',

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_tasks_user_status
ON tasks(user_id, status);

CREATE INDEX idx_tasks_created
ON tasks(created_at DESC);
```

---

# 31. Workflow Runs

```sql
CREATE TABLE workflow_runs (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id),

    status TEXT NOT NULL DEFAULT 'pending',

    plan JSONB NOT NULL DEFAULT '{}',

    total_cost_usd NUMERIC(12, 6) DEFAULT 0,
    total_latency_ms BIGINT DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_workflow_runs_task
ON workflow_runs(task_id);

CREATE INDEX idx_workflow_runs_status
ON workflow_runs(status);
```

---

# 32. Task Steps

```sql
CREATE TABLE task_steps (
    id UUID PRIMARY KEY,
    workflow_run_id UUID NOT NULL
        REFERENCES workflow_runs(id)
        ON DELETE CASCADE,

    step_key TEXT NOT NULL,
    name TEXT NOT NULL,

    dependencies JSONB NOT NULL DEFAULT '[]',

    executor_type TEXT,
    executor_id TEXT,

    input_refs JSONB NOT NULL DEFAULT '[]',
    output JSONB,

    status TEXT NOT NULL DEFAULT 'pending',

    retry_count INTEGER NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_task_steps_workflow
ON task_steps(workflow_run_id);

CREATE INDEX idx_task_steps_status
ON task_steps(status);
```

---

# 33. Model Registry Tables

```sql
CREATE TABLE models (
    id TEXT PRIMARY KEY,

    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,

    context_window BIGINT,

    quality_score DOUBLE PRECISION,
    cost_score DOUBLE PRECISION,
    latency_score DOUBLE PRECISION,

    privacy_class TEXT NOT NULL,

    enabled BOOLEAN NOT NULL DEFAULT true,

    metadata JSONB NOT NULL DEFAULT '{}',

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

```sql
CREATE TABLE model_capabilities (
    model_id TEXT NOT NULL REFERENCES models(id)
        ON DELETE CASCADE,

    capability TEXT NOT NULL,

    PRIMARY KEY (model_id, capability)
);
```

---

# 34. Tool Registry Tables

```sql
CREATE TABLE tools (
    id TEXT PRIMARY KEY,

    name TEXT NOT NULL,
    server TEXT,

    description TEXT,

    risk_level TEXT NOT NULL DEFAULT 'low',

    requires_network BOOLEAN NOT NULL DEFAULT false,
    requires_filesystem BOOLEAN NOT NULL DEFAULT false,
    requires_approval BOOLEAN NOT NULL DEFAULT false,

    enabled BOOLEAN NOT NULL DEFAULT true,

    metadata JSONB NOT NULL DEFAULT '{}'
);
```

```sql
CREATE TABLE tool_capabilities (
    tool_id TEXT NOT NULL REFERENCES tools(id)
        ON DELETE CASCADE,

    capability TEXT NOT NULL,

    PRIMARY KEY (tool_id, capability)
);
```

---

# 35. Execution Table

Every model/tool invocation should be recorded.

```sql
CREATE TABLE executions (
    id UUID PRIMARY KEY,

    workflow_run_id UUID NOT NULL
        REFERENCES workflow_runs(id)
        ON DELETE CASCADE,

    task_step_id UUID NOT NULL
        REFERENCES task_steps(id)
        ON DELETE CASCADE,

    executor_type TEXT NOT NULL,
    executor_id TEXT NOT NULL,

    provider TEXT,

    status TEXT NOT NULL,

    request_metadata JSONB NOT NULL DEFAULT '{}',
    response_metadata JSONB NOT NULL DEFAULT '{}',

    input_tokens BIGINT,
    output_tokens BIGINT,

    cost_usd NUMERIC(12, 6),
    latency_ms BIGINT,

    error_type TEXT,
    error_message TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_executions_workflow
ON executions(workflow_run_id);

CREATE INDEX idx_executions_executor
ON executions(executor_type, executor_id);

CREATE INDEX idx_executions_created
ON executions(created_at DESC);
```

---

# 36. Artifacts

```sql
CREATE TABLE artifacts (
    id UUID PRIMARY KEY,

    user_id UUID NOT NULL REFERENCES users(id),
    task_id UUID REFERENCES tasks(id),

    name TEXT NOT NULL,
    mime_type TEXT NOT NULL,

    storage_uri TEXT NOT NULL,

    size_bytes BIGINT,

    checksum TEXT,

    metadata JSONB NOT NULL DEFAULT '{}',

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_artifacts_task
ON artifacts(task_id);
```

Do not store large files directly in PostgreSQL. Store them in object storage or a controlled filesystem and keep metadata in PostgreSQL.

---

# 37. Documents and Chunks

```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY,

    artifact_id UUID NOT NULL
        REFERENCES artifacts(id),

    parser TEXT,
    page_count INTEGER,

    extracted_text TEXT,

    metadata JSONB NOT NULL DEFAULT '{}',

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

With pgvector enabled:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

```sql
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY,

    document_id UUID NOT NULL
        REFERENCES documents(id)
        ON DELETE CASCADE,

    chunk_index INTEGER NOT NULL,

    content TEXT NOT NULL,

    page_start INTEGER,
    page_end INTEGER,

    metadata JSONB NOT NULL DEFAULT '{}',

    embedding vector(1536)
);
```

Use the embedding dimension appropriate to the selected embedding model.

---

# 38. Routing Events

This table is important if you eventually want learned routing.

```sql
CREATE TABLE routing_events (
    id UUID PRIMARY KEY,

    task_id UUID REFERENCES tasks(id),
    workflow_run_id UUID REFERENCES workflow_runs(id),
    task_step_id UUID REFERENCES task_steps(id),

    candidate_models JSONB NOT NULL,
    selected_model TEXT NOT NULL,

    routing_reason JSONB NOT NULL DEFAULT '{}',

    predicted_score DOUBLE PRECISION,

    actual_success BOOLEAN,
    user_rating DOUBLE PRECISION,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

This becomes your dataset for future routing optimization.

---

# 39. Evaluations

```sql
CREATE TABLE evaluations (
    id UUID PRIMARY KEY,

    execution_id UUID REFERENCES executions(id),

    evaluator_type TEXT NOT NULL,

    score DOUBLE PRECISION,

    passed BOOLEAN,

    feedback JSONB NOT NULL DEFAULT '{}',

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Examples:

```text
schema_validator
unit_tests
document_validator
human_rating
LLM_judge
factual_checker
```

---

# 40. Audit Log

```sql
CREATE TABLE audit_events (
    id UUID PRIMARY KEY,

    user_id UUID REFERENCES users(id),

    action TEXT NOT NULL,

    resource_type TEXT,
    resource_id TEXT,

    metadata JSONB NOT NULL DEFAULT '{}',

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_created
ON audit_events(created_at DESC);
```

Record security-sensitive events such as:

```text
tool execution
file access
network access
model selection
approval
policy denial
credential access
```

---

# 41. Approval Workflow

High-risk tools should pause the workflow.

```text
Planner
  ↓
Tool requires approval
  ↓
WAITING_APPROVAL
  ↓
User approves
  ↓
Tool executes
```

Schema:

```sql
CREATE TABLE approvals (
    id UUID PRIMARY KEY,

    workflow_run_id UUID NOT NULL
        REFERENCES workflow_runs(id),

    task_step_id UUID NOT NULL
        REFERENCES task_steps(id),

    action TEXT NOT NULL,

    risk_level TEXT NOT NULL,

    status TEXT NOT NULL DEFAULT 'pending',

    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,

    resolved_by UUID REFERENCES users(id)
);
```

---

# 42. Database Relationship Overview

```text
users
  │
  ├── projects
  │
  ├── tasks
  │      │
  │      └── workflow_runs
  │             │
  │             ├── task_steps
  │             │      │
  │             │      └── executions
  │             │
  │             ├── routing_events
  │             └── approvals
  │
  └── artifacts
         │
         └── documents
                │
                └── document_chunks

models
  └── model_capabilities

tools
  └── tool_capabilities
```

---

# 43. FastAPI API

Recommended endpoints:

```text
POST   /v1/tasks
GET    /v1/tasks/{task_id}

POST   /v1/tasks/{task_id}/cancel

GET    /v1/runs/{run_id}
GET    /v1/runs/{run_id}/events
GET    /v1/runs/{run_id}/steps

POST   /v1/files
GET    /v1/files/{file_id}

POST   /v1/approvals/{approval_id}/approve
POST   /v1/approvals/{approval_id}/reject

GET    /v1/models
GET    /v1/tools

GET    /health
GET    /ready
```

---

# 44. Example API Request

```json
{
  "goal": "Analyze this annual report and produce an executive summary.",
  "requirements": {
    "task_type": "document_analysis",
    "privacy": "normal",
    "quality": "high",
    "output_format": "docx",
    "needs_file_access": true
  },
  "file_ids": [
    "document-uuid"
  ]
}
```

Response:

```json
{
  "task_id": "uuid",
  "workflow_run_id": "uuid",
  "status": "running"
}
```

---

# 45. Workflow Example

Input:

```text
Analyze scanned annual report.
Extract financial tables.
Calculate YoY changes.
Write executive summary.
Export DOCX.
```

Planner output:

```json
{
  "steps": [
    {
      "id": "ocr",
      "executor": "ocr",
      "depends_on": []
    },
    {
      "id": "extract",
      "executor": "document_parser",
      "depends_on": ["ocr"]
    },
    {
      "id": "analysis",
      "executor": "gemini_documents",
      "depends_on": ["extract"]
    },
    {
      "id": "calculations",
      "executor": "python",
      "depends_on": ["extract"]
    },
    {
      "id": "write",
      "executor": "gpt_primary",
      "depends_on": ["analysis", "calculations"]
    },
    {
      "id": "verify",
      "executor": "claude_coding",
      "depends_on": ["write"]
    },
    {
      "id": "export",
      "executor": "pandoc",
      "depends_on": ["verify"]
    }
  ]
}
```

---

# 46. Intelligent Routing Evolution

## Version 1

Rules:

```text
coding → coding-capable model
documents → long-context model
private → local
simple → cheap/local
```

## Version 2

Weighted scoring:

```text
capability
quality
cost
latency
reliability
```

## Version 3

Historical performance:

```text
task characteristics
        ↓
candidate models
        ↓
historical success
        ↓
cost / latency
        ↓
selected model
```

## Version 4

Learned routing:

```text
Task embedding
     ↓
Routing model
     ↓
Expected utility per model
     ↓
Model selection
```

Do not jump to Version 4 before collecting enough trustworthy execution data.

---

# 47. Model Selection Formula

A production-friendly formulation is:

```text
Utility(model, task) =

  w_capability * CapabilityMatch

+ w_quality    * Quality
+ w_reliability * Reliability
+ w_history    * HistoricalSuccess
+ w_latency    * LatencyScore
+ w_cost       * CostScore

- penalties
```

With hard constraints applied first.

Example:

```python
def utility(
    model,
    task,
    *,
    capability_weight=0.25,
    quality_weight=0.25,
    reliability_weight=0.20,
    history_weight=0.15,
    latency_weight=0.075,
    cost_weight=0.075,
):
    capability = capability_match(model, task)
    quality = model.quality_score
    reliability = model.reliability_score
    history = model.historical_success
    latency = model.latency_score
    cost = model.cost_score

    return (
        capability_weight * capability
        + quality_weight * quality
        + reliability_weight * reliability
        + history_weight * history
        + latency_weight * latency
        + cost_weight * cost
    )
```

---

# 48. Reliability Tracking

For each model/provider maintain:

```text
success rate
timeout rate
invalid response rate
tool-call failure rate
average latency
p50 latency
p95 latency
average cost
user rating
verification pass rate
```

Do not rely only on provider marketing or static model rankings.

Your system should learn what works **for your workload**.

---

# 49. Verification Strategy

Verification should be proportional to risk.

```text
LOW
  → schema validation

STANDARD
  → schema + basic checks

HIGH
  → schema + independent verifier

CRITICAL
  → deterministic checks
  + independent model
  + artifact validation
  + human approval if required
```

Examples:

### Coding

```text
generate code
    ↓
run tests
    ↓
lint/type check
    ↓
review
```

### Data analysis

```text
LLM analysis
    ↓
Python recalculation
    ↓
compare results
```

### Document generation

```text
generate DOCX
    ↓
render
    ↓
check file integrity
    ↓
check required sections
```

---

# 50. Important Principle: Deterministic Verification Beats LLM Verification

Whenever possible:

```text
Python > LLM
unit test > LLM
schema validator > LLM
file parser > LLM
checksum > LLM
```

Use another LLM only where deterministic verification cannot answer the question.

---

# 51. Docker Compose

A practical local development stack:

```yaml
services:

  api:
    build:
      context: .
      dockerfile: Dockerfile
    command: uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
    env_file:
      - .env
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./src:/app/src
      - ./apps:/app/apps
      - ./configs:/app/configs
      - ./prompts:/app/prompts
      - artifacts:/data/artifacts

  worker:
    build:
      context: .
      dockerfile: Dockerfile
    command: python apps/worker/main.py
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - artifacts:/data/artifacts

  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_DB: orchestrator
      POSTGRES_USER: orchestrator
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test:
        - CMD-SHELL
        - pg_isready -U orchestrator -d orchestrator
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test:
        - CMD
        - redis-cli
        - ping
      interval: 5s
      timeout: 3s
      retries: 10

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

  mcp-python:
    build:
      context: ./tools/mcp/python
    environment:
      SANDBOX_MODE: "true"
    volumes:
      - artifacts:/data/artifacts

  mcp-documents:
    build:
      context: ./tools/mcp/documents
    volumes:
      - artifacts:/data/artifacts

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./infra/prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
    volumes:
      - grafana_data:/var/lib/grafana

volumes:
  postgres_data:
  redis_data:
  ollama_data:
  artifacts:
  grafana_data:
```

Pin image versions in production rather than using `latest`.

---

# 52. Dockerfile

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       pandoc \
       libreoffice \
       tesseract-ocr \
       poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN pip install --no-cache-dir uv \
    && uv sync --frozen

COPY src ./src
COPY apps ./apps
COPY configs ./configs
COPY prompts ./prompts

ENV PYTHONPATH=/app

CMD ["uv", "run", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

For production, use a multi-stage build and run as a non-root user.

---

# 53. Environment Variables

`.env.example`:

```env
APP_ENV=development

DATABASE_URL=postgresql+asyncpg://orchestrator:password@postgres:5432/orchestrator

REDIS_URL=redis://redis:6379/0

OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=

OLLAMA_BASE_URL=http://ollama:11434

ARTIFACT_ROOT=/data/artifacts

LOG_LEVEL=INFO

MAX_TASK_COST_USD=5.00
MAX_WORKFLOW_STEPS=50
DEFAULT_TASK_TIMEOUT_SECONDS=900
```

Never commit real credentials.

Use a secret manager in production.

---

# 54. FastAPI Application

```python
from fastapi import FastAPI

app = FastAPI(
    title="AI Orchestrator",
    version="1.0.0",
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    # Check database, Redis, model gateway, etc.
    return {"status": "ready"}
```

---

# 55. Request Lifecycle

```text
HTTP request
    ↓
Authentication
    ↓
Validate request
    ↓
Create Task
    ↓
Policy evaluation
    ↓
Create Workflow Run
    ↓
Planner
    ↓
Task graph
    ↓
Scheduler
    ↓
Router
    ↓
Executor
    ↓
Verifier
    ↓
Persist result
    ↓
Artifact storage
    ↓
Event stream
    ↓
Client
```

---

# 56. Asynchronous Execution

Long tasks should not block an HTTP request.

Use:

```text
POST /v1/tasks
       ↓
202 Accepted
       ↓
queue
       ↓
worker
       ↓
workflow execution
```

Client can then subscribe to:

```text
GET /v1/runs/{run_id}/events
```

or use WebSockets/SSE.

---

# 57. Event Model

Emit events such as:

```json
{
  "type": "step.started",
  "run_id": "uuid",
  "step_id": "analysis",
  "executor": "gemini_documents",
  "timestamp": "..."
}
```

Other events:

```text
task.created
workflow.created
plan.created
step.started
model.selected
tool.selected
tool.approval_required
step.completed
step.failed
verification.failed
model.fallback
artifact.created
workflow.completed
workflow.failed
```

This makes the system observable and debuggable.

---

# 58. Observability

Track:

## System metrics

```text
requests/sec
workflow duration
queue depth
worker utilization
error rate
```

## Model metrics

```text
calls/model
tokens/model
cost/model
latency/model
failure rate/model
verification pass rate/model
```

## Routing metrics

```text
selected model
candidate models
routing score
fallback rate
model win rate
```

## Business metrics

```text
tasks completed
tasks requiring human intervention
user satisfaction
cost per completed task
```

---

# 59. Cost Controls

Implement budgets at three levels:

```text
request budget
workflow budget
user/project budget
```

Example:

```python
class BudgetPolicy:

    def can_spend(
        self,
        current_cost: float,
        estimated_cost: float,
        max_cost: float,
    ) -> bool:
        return (
            current_cost + estimated_cost
            <= max_cost
        )
```

Before every model invocation:

```text
estimate cost
    ↓
check budget
    ↓
allow / downgrade / reject
```

---

# 60. Privacy Routing

A useful policy matrix:

| Data | Local | Cloud |
|---|---:|---:|
| Public text | optional | yes |
| Normal business docs | optional | yes |
| Confidential docs | preferred | policy-dependent |
| Secrets/API keys | yes | no |
| Highly private files | yes | no |

Implement automatic redaction before cloud calls where possible.

---

# 61. Secrets Protection

Never allow models to directly read:

```text
.env
SSH keys
cloud credentials
database passwords
API keys
system secrets
```

Instead:

```text
Model
 ↓
approved tool
 ↓
secret manager
 ↓
credential injection
 ↓
operation
```

Keep secrets outside the model context.

---

# 62. Prompt Architecture

Do not store giant prompts in Python source.

Use versioned files:

```text
prompts/
├── planner/
│   ├── v1.txt
│   └── v2.txt
├── classifier/
│   └── v1.txt
├── verifier/
│   └── v1.txt
└── workers/
    ├── writing_v1.txt
    ├── coding_v1.txt
    └── document_v1.txt
```

Record the prompt version in each execution.

This allows reproducibility.

---

# 63. Model Configuration Should Be Data

Do not do this:

```python
if task_type == "coding":
    return "claude"
```

Instead:

```yaml
coding:
  required_capabilities:
    - coding
    - reasoning
```

Then the router chooses among all eligible models.

This lets you change model assignments without redeploying application code.

---

# 64. Example Model Registry

```yaml
models:

  coding_primary:
    provider: anthropic
    model: <configured-coding-model>
    capabilities:
      - coding
      - reasoning
      - code_review

  brainstorming_primary:
    provider: openai
    model: <configured-reasoning-model>
    capabilities:
      - brainstorming
      - reasoning
      - writing

  document_primary:
    provider: google
    model: <configured-document-model>
    capabilities:
      - document_analysis
      - multimodal
      - long_context

  local_fast:
    provider: ollama
    model: <configured-local-model>
    capabilities:
      - classification
      - extraction
      - summarization
      - private
```

Model IDs should be filled with currently supported models in deployment configuration.

---

# 65. Agent Roles

Use role-based workers:

```text
Planner
Classifier
Researcher
Coder
Document Analyst
Writer
Data Analyst
Verifier
Artifact Builder
```

But these are logical roles, not necessarily separate LLM agents.

A role is simply:

```text
required capabilities
prompt
allowed tools
quality threshold
verification policy
```

Example:

```yaml
roles:

  coder:
    capabilities:
      - coding
      - reasoning

    tools:
      - filesystem
      - git
      - python
      - test_runner

    verification:
      - tests
      - lint
      - typecheck
```

---

# 66. Example: Coding Workflow

```text
User:
"Fix the failing tests in this repository."

        ↓

Classifier
        ↓
coding + filesystem + test_execution
        ↓
Planner
        ↓
inspect repository
        ↓
Claude / coding-capable model
        ↓
edit files
        ↓
run tests
        ↓
if failure:
    inspect failure
    revise
    rerun
        ↓
all tests pass
        ↓
verification
        ↓
final response
```

The model should never be allowed to claim tests passed without the test runner actually returning success.

---

# 67. Example: Document Workflow

```text
PDF
 ↓
file inspection
 ↓
is scanned?
 ├── yes → OCR
 └── no  → parser
 ↓
chunk/index
 ↓
retrieve relevant sections
 ↓
document-capable model
 ↓
Python for calculations
 ↓
writer model
 ↓
verification
 ↓
Pandoc / LibreOffice
 ↓
DOCX
```

---

# 68. Example: Brainstorming Workflow

This can be much simpler:

```text
User
 ↓
classifier
 ↓
brainstorming capability
 ↓
one strong model
 ↓
optional critic
 ↓
final synthesis
```

Don't invoke OCR, Python, MCP, or multiple models unless needed.

---

# 69. Example: Private Workflow

```text
Private document
       ↓
Policy engine
       ↓
Cloud models rejected
       ↓
Local parser
       ↓
Local LLM
       ↓
Local Python
       ↓
Local artifact
```

The policy engine, not the model, should enforce this.

---

# 70. Learned Router — Future Architecture

After enough execution data exists:

```text
Task
 │
 ├── task type
 ├── complexity
 ├── context size
 ├── privacy
 ├── output format
 ├── required capabilities
 └── historical performance
        ↓
Routing model
        ↓
Expected utility
        ↓
Top N models
        ↓
Policy filter
        ↓
Final model
```

The learned router should never override hard security/privacy constraints.

---

# 71. A/B Testing Models

You can evaluate new models without changing production routing.

```text
90% traffic → current model
10% traffic → candidate model
```

Compare:

```text
quality
verification pass rate
latency
cost
user rating
failure rate
```

Store all results in `routing_events` and `evaluations`.

---

# 72. Provider Failover

A provider outage should not kill the workflow.

Example:

```text
Primary:
OpenAI

fails
 ↓
Anthropic

fails
 ↓
Google

fails
 ↓
Local model
```

But provider diversity must respect task requirements and privacy.

For private data:

```text
cloud provider A
cloud provider B
cloud provider C
   ↓
all rejected
   ↓
local
```

---

# 73. Human-in-the-Loop

Require approval for:

```text
sending emails
publishing content
deleting files
financial actions
production deployments
external network actions
changing permissions
executing high-risk shell commands
```

Do not rely on the LLM to decide whether its own action is safe.

The policy engine should decide.

---

# 74. Testing Strategy

## Unit tests

Test:

```text
router
scoring
policy engine
workflow graph
budget manager
fallback logic
```

## Integration tests

Test:

```text
PostgreSQL
Redis
LiteLLM
MCP servers
artifact storage
```

## E2E tests

Test:

```text
upload PDF
 → OCR
 → analysis
 → verification
 → DOCX
```

## Security tests

Test:

```text
private task never reaches cloud
unauthorized tool blocked
sandbox cannot access host
secret files inaccessible
network disabled when required
```

---

# 75. Golden Test Set

Create a fixed evaluation dataset:

```text
100 coding tasks
100 document tasks
100 writing tasks
100 research tasks
100 extraction tasks
```

For every routing change compare:

```text
quality
cost
latency
failure rate
verification
```

This prevents router regressions.

---

# 76. Suggested Implementation Roadmap

## Milestone 1 — Foundation

Build:

```text
FastAPI
PostgreSQL
Redis
LiteLLM
model registry
basic router
```

Deliverable:

```text
one API request
→ one selected model
→ logged execution
```

---

## Milestone 2 — Tools

Add:

```text
MCP
Python
OCR
Pandoc
filesystem
```

Deliverable:

```text
one request
→ model + tool
→ result
```

---

## Milestone 3 — Workflows

Add:

```text
planner
task graph
scheduler
async workers
```

Deliverable:

```text
request
→ multiple steps
→ multiple executors
```

---

## Milestone 4 — Verification

Add:

```text
schema verification
Python verification
file validation
secondary model review
```

Deliverable:

```text
model output
→ verification
→ repair if needed
```

---

## Milestone 5 — Security

Add:

```text
RBAC
tool policies
sandbox
privacy classification
approvals
audit logs
secret isolation
```

---

## Milestone 6 — Intelligent Routing

Add:

```text
execution statistics
model performance database
routing events
historical scoring
A/B testing
```

---

## Milestone 7 — Learned Routing

Only after sufficient data:

```text
task features
→ routing model
→ expected utility
→ candidate selection
```

---

# 77. Recommended MVP

Do not build the entire platform first.

Build this exact vertical slice:

```text
                    USER
                      │
                      ▼
                 FastAPI
                      │
                      ▼
               Task Classifier
                      │
                      ▼
                Model Router
                      │
              ┌───────┼───────┐
              ▼       ▼       ▼
             GPT    Claude  Gemini
              │       │       │
              └───────┼───────┘
                      ▼
                   Executor
                      │
                      ▼
                  PostgreSQL
```

Then add:

```text
MCP → Python
MCP → OCR
MCP → Pandoc
```

Then workflows.

This gives you a usable system quickly without prematurely creating a distributed architecture.

---

# 78. Production Readiness Checklist

## Architecture

- [ ] Provider abstraction
- [ ] Capability-based routing
- [ ] Workflow DAG
- [ ] Async workers
- [ ] Persistent state
- [ ] Artifact storage

## Reliability

- [ ] Timeouts
- [ ] Retries
- [ ] Provider failover
- [ ] Circuit breakers
- [ ] Idempotency
- [ ] Dead-letter queue

## Security

- [ ] Authentication
- [ ] Authorization
- [ ] Tool allowlists
- [ ] Sandbox
- [ ] Secret isolation
- [ ] Network restrictions
- [ ] Audit log
- [ ] Approval workflow

## AI quality

- [ ] Structured outputs
- [ ] Verification
- [ ] Evaluation dataset
- [ ] Prompt versioning
- [ ] Model performance tracking

## Operations

- [ ] Metrics
- [ ] Traces
- [ ] Structured logs
- [ ] Cost tracking
- [ ] Health checks
- [ ] Backups
- [ ] Database migrations

---

# 79. Final Reference Architecture

The finished platform should conceptually look like this:

```text
┌────────────────────────────────────────────────────────────────────┐
│                            USER / APPS                             │
│                    Web · CLI · IDE · API · Desktop                 │
└────────────────────────────────┬───────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                           API GATEWAY                               │
│                Auth · Rate limits · Streaming · Files              │
└────────────────────────────────┬───────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR                                │
│                                                                    │
│  Classifier → Policy → Planner → DAG Scheduler → Executor          │
│                         │                 │                         │
│                         │                 ├── Model Router          │
│                         │                 └── Tool Router            │
│                         │                                           │
│                         └──────────────→ Verifier                   │
└───────────────┬───────────────────────┬────────────────────────────┘
                │                       │
                ▼                       ▼
┌──────────────────────────┐  ┌─────────────────────────────────────┐
│      MODEL GATEWAY       │  │             TOOL GATEWAY            │
│                          │  │                                     │
│ LiteLLM                  │  │ MCP                                 │
│                          │  │                                     │
│ OpenAI                   │  │ Python                              │
│ Anthropic                │  │ OCR                                 │
│ Google                   │  │ Pandoc                              │
│ Local LLM                │  │ Browser                             │
└─────────────┬────────────┘  │ Git                                 │
              │               │ Filesystem                          │
              │               └─────────────────┬───────────────────┘
              │                                 │
              ▼                                 ▼
       ┌───────────────┐                 ┌───────────────┐
       │ Cloud Models  │                 │ Sandboxed     │
       │ + Local Models│                 │ Tool Workers  │
       └───────────────┘                 └───────────────┘

                ┌──────────────────────────────────┐
                │         CONTEXT / MEMORY         │
                │ PostgreSQL · pgvector · Redis    │
                │ Files · Documents · Embeddings   │
                └──────────────────────────────────┘

                ┌──────────────────────────────────┐
                │          OBSERVABILITY            │
                │ Logs · Metrics · Traces · Costs  │
                └──────────────────────────────────┘
```

---

# 80. The Core Engineering Principle

The most important design decision is:

```text
                    DO NOT BUILD

             "a chatbot that calls models"

                         ↓

                    BUILD THIS

                  "an execution
                    operating system"

                         ↓

              ┌──────────────────────┐
              │       GOAL           │
              └──────────┬───────────┘
                         ↓
                 CAPABILITIES
                         ↓
               TASK / WORKFLOW GRAPH
                         ↓
          ┌──────────────┼──────────────┐
          ↓              ↓              ↓
        MODEL           TOOL          MEMORY
          ↓              ↓              ↓
       execute        execute        retrieve
          └──────────────┼──────────────┘
                         ↓
                     VERIFY
                         ↓
                      OUTPUT
                         ↓
                    LEARN FROM
                     OUTCOME
```

If you keep **capabilities, policies, routing, execution, verification, and state** separate from individual model providers, you can replace or add models without redesigning the platform.

That is the architecture that will let this evolve from a personal multi-model assistant into a production-grade orchestration platform.

---

# 81. Continual Learning and Reinforcement Learning Layer

The orchestration platform can be extended into a **self-optimizing system** without immediately modifying the parameters of the local LLM.

The recommended progression is:

```text
                         EXECUTION
                            │
                            ▼
                     EVALUATION DATA
                            │
              ┌─────────────┼─────────────┐
              │             │             │
              ▼             ▼             ▼
           MEMORY        POLICY          DATASET
             RAG           RL          Fine-tuning
              │             │             │
              ▼             ▼             ▼
        Better context  Better choices  Optional future
```

The objective is not simply to make the model produce better answers. The larger objective is:

> **Produce the required quality at the lowest possible external-model cost and latency, while maintaining correctness and reliability.**

This means the system should learn not only **what answer to generate**, but also:

- whether a cloud model is needed at all;
- which local model is sufficient;
- when to retrieve additional context;
- when to invoke Claude/GPT/Gemini;
- when deterministic tools are better than an LLM;
- when a second reviewer is necessary;
- when an answer can be accepted immediately;
- when an existing lesson can avoid another expensive call;
- how many tokens are actually necessary;
- when escalation is not worth the cost.

---

# 82. The Optimization Objective

The orchestration layer should optimize a utility function such as:

```text
Utility =
    quality
  + correctness
  + user_satisfaction
  + verification_success

  - external_llm_cost
  - latency
  - unnecessary_tool_calls
  - unnecessary_context
  - failure_cost
```

A more explicit formulation:

```python
reward = (
    0.30 * quality_score
    + 0.30 * correctness_score
    + 0.15 * verification_score
    + 0.15 * user_score
    + 0.10 * task_completion_score
    - cost_penalty
    - latency_penalty
    - unnecessary_call_penalty
)
```

The weights should be configuration-driven and tuned using the system's actual evaluation data.

The important principle is:

```text
HIGH QUALITY + LOW COST
```

rather than:

```text
MAXIMUM MODEL USAGE
```

---

# 83. Claude as Teacher / Reviewer

Claude can operate as a **teacher, critic, evaluator, and lesson generator** for local models.

This does not mean Claude directly trains the local model's weights.

Instead:

```text
Local LLM
    ↓
Answer
    ↓
Claude reviewer
    ↓
Critique
    ↓
Lesson extraction
    ↓
Validated memory
    ↓
Future local task
```

Example reviewer output:

```json
{
  "quality": 0.82,
  "correctness": 0.91,
  "completeness": 0.76,
  "instruction_following": 0.95,
  "issues": [
    "Missed requirement X",
    "Incorrect assumption about Y"
  ],
  "lesson": {
    "rule": "Always verify the user's requested constraints before finalizing.",
    "domain": "general",
    "priority": 0.87
  }
}
```

Claude should not automatically be considered correct. Its output should become a **candidate evaluation or lesson**.

---

# 84. Teacher Feedback Must Be Validated

Do not create this dangerous loop:

```text
Local model makes mistake
       ↓
Claude proposes lesson
       ↓
Lesson stored permanently
       ↓
Local model follows bad lesson
       ↓
More mistakes
```

Instead:

```text
Claude lesson
     ↓
Candidate lesson
     ↓
Evaluation
     ↓
Benchmark
     ↓
Improves performance?
     │
 ┌───┴────┐
 NO       YES
 │         │
discard   promote
```

A lesson should become persistent only when it passes the relevant validation threshold.

---

# 85. Lesson Memory

Add a learning/lesson subsystem:

```text
src/orchestrator/
└── learning/
    ├── teacher.py
    ├── critic.py
    ├── lesson_miner.py
    ├── lesson_store.py
    ├── lesson_retriever.py
    ├── evaluator.py
    ├── promotion.py
    └── rewards/
        ├── reward.py
        ├── quality.py
        ├── cost.py
        └── latency.py
```

Lessons can contain:

```text
successful strategy
common mistake
formatting rule
domain rule
tool-use strategy
coding pattern
verification requirement
user preference
model-specific correction
```

Example:

```yaml
lesson:
  id: test_before_claim
  domain: coding
  priority: 0.95

  rule: >
    Never claim that code works unless the relevant tests
    have actually been executed successfully.

  applies_when:
    - coding
    - repository_modification
```

---

# 86. Memory Types

Separate memory by purpose.

```text
                    MEMORY
                       │
       ┌───────────────┼────────────────┐
       │               │                │
       ▼               ▼                ▼
   User Memory     Task Memory      Model Memory
       │               │                │
 preferences       past tasks        lessons
 style              mistakes        strategies
```

For model improvement:

```text
Model Memory
├── successful strategies
├── common errors
├── verified lessons
├── task-specific rules
├── domain knowledge
├── tool usage patterns
└── verification patterns
```

---

# 87. Retrieval of Lessons

Before invoking a local model:

```text
New task
   ↓
Task classifier
   ↓
Retrieve relevant lessons
   ↓
Rank lessons
   ↓
Apply only top relevant lessons
   ↓
Local LLM
```

Do not inject the entire lesson database.

The context manager should consider:

```text
relevance
priority
recency
model applicability
task type
historical effectiveness
token cost
```

This makes RAG itself cost-aware.

---

# 88. Lesson Effectiveness

Every lesson should have measurable effectiveness.

Example:

```text
Lesson:
"Run tests after modifying executable code."

Applications: 1,200
Before lesson: 72% success
After lesson: 91% success
Improvement: +19%
```

Store this information.

A lesson that repeatedly fails to improve results should be:

```text
demoted
archived
re-evaluated
```

The system should therefore learn **which lessons are useful**, not merely accumulate more text.

---

# 89. Reinforcement Learning: What Should Actually Be Learned?

The first RL target should be the **orchestration policy**, not the local model's parameters.

Good RL actions include:

```text
choose local model
choose cloud model
choose model provider
escalate to teacher
retrieve memory
retrieve more memory
call deterministic tool
call second verifier
retry
change strategy
finish
```

The state may contain:

```python
state = {
    "task_type": "...",
    "complexity": 0.72,
    "context_size": 12000,
    "privacy": "normal",
    "budget_remaining": 1.20,
    "local_confidence": 0.61,
    "rag_relevance": 0.84,
    "previous_attempts": 1,
    "available_models": [...],
    "historical_success": {...}
}
```

The action could be:

```python
action = {
    "type": "escalate",
    "target": "claude"
}
```

The resulting reward tells the system whether that decision was worthwhile.

---

# 90. Start With Contextual Bandits

Do not begin with a large, complicated RL system.

The first optimization problem is naturally a **contextual bandit**:

```text
Context:
    task characteristics

Actions:
    Local
    GPT
    Claude
    Gemini

Reward:
    quality - cost - latency
```

The system learns:

```text
For this kind of task,
which model has the highest expected utility?
```

This is substantially simpler than full sequential RL and is an excellent first learning layer.

---

# 91. First RL Problem: Should We Escalate?

A particularly valuable policy is:

```text
Should the local model be trusted?
```

Example:

```text
Task
 ↓
Local LLM
 ↓
confidence = 0.94
 ↓
policy
 ↓
accept
```

versus:

```text
Task
 ↓
Local LLM
 ↓
confidence = 0.43
 ↓
policy
 ↓
Claude review
```

The policy can learn from historical outcomes:

```text
local confidence
+
task difficulty
+
RAG relevance
+
historical model performance
+
verification results
```

and predict whether an external call is worth its cost.

This can dramatically reduce unnecessary API usage.

---

# 92. Token-Efficient Escalation

The system should not send a full conversation/document to a frontier model every time.

Instead:

```text
Local model
     ↓
identify uncertainty
     ↓
extract relevant context
     ↓
retrieve relevant lessons
     ↓
build minimal review package
     ↓
Claude
```

For example, instead of:

```text
500-page PDF
+
20,000-token conversation
+
entire local response
```

send:

```text
Task
+
relevant 5 pages
+
local answer
+
specific uncertainty
+
evaluation criteria
```

This makes teacher calls substantially cheaper.

---

# 93. Cascaded Model Architecture

Use a model cascade:

```text
                 TASK
                   │
                   ▼
             Cheap/local model
                   │
          ┌────────┴────────┐
          │                 │
       confident         uncertain
          │                 │
          ▼                 ▼
        ACCEPT          stronger model
                            │
                      ┌─────┴─────┐
                      │           │
                  sufficient   difficult
                      │           │
                      ▼           ▼
                    ACCEPT      Claude/GPT
```

The goal is:

> **Use the smallest/cheapest executor capable of achieving the required quality.**

---

# 94. Dynamic Verification

Verification itself should be adaptive.

```text
Low-risk task
    ↓
schema validation

Medium-risk task
    ↓
deterministic check

High-risk task
    ↓
deterministic check + teacher

Critical task
    ↓
deterministic check
+ teacher
+ independent reviewer
+ human approval if required
```

This prevents the system from wasting multiple external calls on trivial tasks.

---

# 95. Deterministic Tools Should Be Preferred Over LLM Calls

Whenever the answer can be verified or generated deterministically:

```text
Python > LLM
pytest > LLM
mypy > LLM
Pandoc > LLM
OCR engine > LLM
checksum > LLM
JSON schema validator > LLM
```

The LLM should decide **when a tool is useful**, but the tool should perform the deterministic operation.

This improves both reliability and token efficiency.

---

# 96. Full Self-Optimization Loop

The complete architecture becomes:

```text
                         USER TASK
                            │
                            ▼
                      ORCHESTRATOR
                            │
                            ▼
                       POLICY/RL
                            │
                 ┌──────────┴──────────┐
                 ▼                     ▼
            LOCAL LLM              TOOL / RAG
                 │                     │
                 ▼                     │
              ANSWER                   │
                 │                     │
          ┌──────┴────────┐            │
          ▼               ▼            │
     Deterministic     Teacher         │
       Checks          (Claude)        │
          │               │            │
          └───────┬───────┘            │
                  ▼                    │
              EVALUATOR                │
                  │                    │
          ┌───────┼────────┐           │
          ▼       ▼        ▼           │
        Reward  Lesson   Metrics       │
          │       │        │           │
          ▼       ▼        ▼           │
       RL Buffer RAG   Telemetry       │
          │       │        │           │
          └───────┼────────┘           │
                  ▼                    │
             POLICY UPDATE             │
                  │                    │
                  └────────────────────┘
```

This creates a closed-loop optimization system.

---

# 97. Experience Replay

Store every important decision:

```sql
CREATE TABLE rl_experiences (
    id UUID PRIMARY KEY,

    task_id UUID REFERENCES tasks(id),
    workflow_run_id UUID REFERENCES workflow_runs(id),

    state JSONB NOT NULL,
    action JSONB NOT NULL,

    reward DOUBLE PRECISION,
    next_state JSONB,

    done BOOLEAN NOT NULL DEFAULT false,

    quality_score DOUBLE PRECISION,
    correctness_score DOUBLE PRECISION,
    verification_score DOUBLE PRECISION,
    user_score DOUBLE PRECISION,

    cost_usd NUMERIC(12, 6),
    latency_ms BIGINT,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_rl_experiences_created
ON rl_experiences(created_at DESC);
```

This becomes the system's historical learning dataset.

---

# 98. Reward Calculation

Create a dedicated reward engine:

```python
class RewardEngine:

    def calculate(
        self,
        *,
        quality: float,
        correctness: float,
        verification: float,
        user_score: float,
        cost_usd: float,
        latency_ms: int,
    ) -> float:

        positive = (
            0.30 * quality
            + 0.30 * correctness
            + 0.20 * verification
            + 0.20 * user_score
        )

        cost_penalty = min(cost_usd / 2.0, 1.0) * 0.15
        latency_penalty = min(
            latency_ms / 60000,
            1.0
        ) * 0.05

        return (
            positive
            - cost_penalty
            - latency_penalty
        )
```

The exact formula should be tuned experimentally.

---

# 99. Reward Hacking Protection

The optimizer can accidentally learn undesirable shortcuts.

For example:

```text
Never call Claude
```

would reduce cost, but could destroy quality.

Or:

```text
Always call Claude
```

could improve quality while destroying the budget.

Therefore use hard constraints and balanced rewards.

Examples:

```text
minimum quality threshold
maximum cost
maximum latency
mandatory verification for critical tasks
privacy constraints
```

The optimization problem becomes:

```text
maximize quality
subject to:

cost <= budget
latency <= limit
privacy == policy
quality >= minimum
```

This is safer than unconstrained reward maximization.

---

# 100. Exploration vs Exploitation

The RL router must occasionally try alternatives.

Otherwise it may learn:

```text
Claude works well
→ always use Claude
```

and never discover that the local model has improved.

Use controlled exploration:

```text
95% exploit best-known strategy
5% explore alternative
```

The exploration rate can decrease as confidence in the routing policy increases.

Exploration should never violate:

```text
privacy
security
quality minimum
budget
approval requirements
```

---

# 101. Measuring the Value of an External Call

A very useful metric is:

```text
Marginal Value of Model Call
```

Conceptually:

```text
value =
quality_after_call
-
quality_without_call
```

Then compare it against:

```text
call_cost
call_latency
```

Example:

```text
Local answer quality:      0.86
Claude-reviewed quality:   0.89

Improvement:               +0.03
Claude cost:               $0.08
```

The system can learn that the call probably isn't worthwhile for similar tasks.

Another case:

```text
Local answer quality:      0.52
Claude-reviewed quality:   0.93

Improvement:               +0.41
Claude cost:               $0.08
```

Here escalation is clearly valuable.

---

# 102. Token Budget as a First-Class Resource

Treat external tokens like a budget:

```text
Task budget
├── planning tokens
├── execution tokens
├── review tokens
└── retry tokens
```

Before each external call:

```text
estimate tokens
     ↓
estimate cost
     ↓
estimate expected quality improvement
     ↓
call worth it?
     ├── no → local/tool/finish
     └── yes → external model
```

This turns token optimization into a formal orchestration decision.

---

# 103. Teacher Calls Should Be Selective

Claude should not review every local response.

Use triggers:

```text
local confidence < threshold
OR
task risk >= high
OR
verification failed
OR
new task category
OR
model recently underperformed
OR
user explicitly requests high quality
OR
RL exploration
```

Otherwise:

```text
Local model
→ deterministic verification
→ accept
```

---

# 104. Teacher Calls Can Also Be Batch-Based

For some applications, review can happen asynchronously.

Instead of:

```text
Every task
→ Claude
```

use:

```text
100 local executions
        ↓
select difficult/representative examples
        ↓
Claude batch review
        ↓
extract lessons
        ↓
update memory
```

This is especially useful for improving the system without adding latency to every user request.

---

# 105. Continuous Improvement Pipeline

A production learning cycle can run periodically:

```text
Every N tasks / daily:

1. Collect experiences
2. Select representative failures
3. Ask teacher to analyze failures
4. Generate candidate lessons
5. Validate lessons
6. Evaluate routing alternatives
7. Update lesson priorities
8. Update routing policy
9. Run regression benchmark
10. Promote only if benchmark improves
```

This is much safer than continuously changing the production policy after every single task.

---

# 106. Policy Versioning

Every routing policy should have a version:

```text
routing-policy-v1
routing-policy-v2
routing-policy-v3
```

Record:

```text
policy version
model registry version
prompt version
lesson set version
```

for every execution.

Then you can answer:

> "Why did the system choose Claude for this task?"

and reproduce the decision.

---

# 107. Safe Policy Promotion

Use:

```text
candidate policy
       ↓
offline benchmark
       ↓
shadow traffic
       ↓
small percentage of production
       ↓
compare
       ↓
promote / rollback
```

Example:

```text
v3 current: 91.2% success
v4 candidate: 92.8% success

cost:
v3 = $0.19/task
v4 = $0.11/task

→ promote v4
```

A candidate should not be promoted merely because its quality improved if cost or safety becomes unacceptable.

---

# 108. Shadow Mode

Before letting RL control production:

```text
Real request
   │
   ├── Current policy → executes
   │
   └── RL policy → predicts only
```

Compare:

```text
"What would RL have chosen?"
```

without actually risking production.

Once the policy demonstrates improvement:

```text
1%
→ 5%
→ 20%
→ 50%
→ 100%
```

This makes the learning system much safer.

---

# 109. Model-Specific Lessons

Lessons should be scoped:

```text
global
task_type
domain
model
tool
user/project
```

Example:

```json
{
  "lesson": "Run tests after code modification.",
  "scope": {
    "task_type": "coding",
    "model": "local-coding-model"
  }
}
```

This prevents a lesson that helps coding from accidentally influencing document writing.

---

# 110. Local Model Improvement Without Parameter Training

The complete non-training improvement stack is:

```text
             LOCAL LLM
                 │
        ┌────────┼─────────┐
        │        │         │
        ▼        ▼         ▼
      Prompt     RAG     Tool Use
        │        │         │
        └────────┼─────────┘
                 ▼
              Output
                 │
        ┌────────┼─────────┐
        ▼        ▼         ▼
     Tests     Claude    User
        │      review    feedback
        └────────┼─────────┘
                 ▼
              Lessons
                 │
                 ▼
          Better future context
```

The local model's parameters remain unchanged.

The **system around the model becomes smarter**.

---

# 111. Optional Future Parameter Training

If you later decide that RAG/policy improvements are no longer sufficient:

```text
validated experiences
        ↓
high-quality dataset
        ↓
filter / deduplicate
        ↓
benchmark
        ↓
optional fine-tuning
        ↓
new local model
        ↓
A/B test
```

This should be a separate pipeline.

Never automatically fine-tune the production model after every lesson.

---

# 112. Recommended Learning Architecture

The final architecture becomes:

```text
                         ┌─────────────────────┐
                         │      USER TASK      │
                         └──────────┬──────────┘
                                    ↓
                         ┌─────────────────────┐
                         │    ORCHESTRATOR     │
                         └──────────┬──────────┘
                                    ↓
                         ┌─────────────────────┐
                         │ ROUTING POLICY / RL │
                         └──────────┬──────────┘
                                    ↓
                 ┌──────────────────┼──────────────────┐
                 │                  │                  │
                 ▼                  ▼                  ▼
             Local LLM             RAG              Tools
                 │                  │                  │
                 └──────────────────┼──────────────────┘
                                    ↓
                                  RESULT
                                    │
                   ┌────────────────┼────────────────┐
                   │                │                │
                   ▼                ▼                ▼
             Deterministic       Claude            Human
              evaluation         teacher           feedback
                   │                │                │
                   └────────────────┼────────────────┘
                                    ↓
                              REWARD ENGINE
                                    │
                       ┌────────────┼─────────────┐
                       ▼            ▼             ▼
                 RL Experience   Lessons      Telemetry
                       │            │
                       ▼            ▼
                  RL Policy      RAG Memory
                       │            │
                       └─────┬──────┘
                             ↓
                     FUTURE TASKS
                             ↓
                     BETTER + CHEAPER
```

---

# 113. Recommended Implementation Order for RL

Do not build everything simultaneously.

## Stage 1 — Instrument everything

Collect:

```text
task
model
tokens
cost
latency
tool calls
verification
user feedback
outcome
```

No RL yet.

---

## Stage 2 — Add teacher evaluation

```text
Local answer
→ Claude review
→ quality score
→ lesson candidate
```

No automated policy changes yet.

---

## Stage 3 — Add validated RAG lessons

```text
lesson
→ benchmark
→ approve
→ retrieve on future tasks
```

Now the local model can improve immediately without parameter training.

---

## Stage 4 — Add contextual bandit

Optimize:

```text
Which model?
```

Then:

```text
Should we escalate?
```

Then:

```text
Should we retrieve more context?
```

---

## Stage 5 — Add cost-aware policy

Optimize:

```text
quality / dollar
```

rather than just quality.

---

## Stage 6 — Add sequential RL

Only after enough reliable data:

```text
choose model
→ retrieve
→ execute
→ verify
→ escalate
→ retry
→ finish
```

The policy now learns workflow strategies.

---

## Stage 7 — Optional fine-tuning

Only if there is a demonstrated benefit:

```text
validated examples
→ training dataset
→ local model fine-tuning
```

---

# 114. The Ultimate Objective

The system should eventually behave like this:

```text
Simple request
    ↓
Local LLM
    ↓
Done

Moderate request
    ↓
Local LLM
    ↓
Python/tool verification
    ↓
Done

Difficult request
    ↓
Local LLM
    ↓
Claude review
    ↓
Done

Very difficult request
    ↓
Claude/GPT/Gemini
    ↓
Tools
    ↓
Independent verification
    ↓
Done
```

The system should **not** learn:

```text
"Always use Claude."
```

It should learn:

> **"Use Claude when the expected improvement in quality/correctness is greater than the cost and latency of invoking Claude."**

That is the central RL objective for this platform.

---

# 115. Final Learning Principle

The long-term architecture should therefore optimize five things simultaneously:

```text
                 AI ORCHESTRATOR
                       │
       ┌───────────────┼────────────────┐
       │               │                │
       ▼               ▼                ▼
     QUALITY          COST          LATENCY
       │               │                │
       └───────────────┼────────────────┘
                       ▼
                  RELIABILITY
                       │
                       ▼
                    SAFETY
```

And the system should improve through:

```text
RAG
+
Teacher feedback
+
Deterministic verification
+
Human feedback
+
Contextual bandits
+
Reinforcement learning
+
Optional future fine-tuning
```

The result is not merely a multi-LLM application.

It becomes a **cost-aware, self-optimizing AI execution platform** whose policy learns when to use local intelligence, when to use deterministic tools, and when an external frontier model is genuinely worth the tokens.
