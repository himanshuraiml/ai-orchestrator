# AI Orchestration Platform — Implementation Plan
> **Project:** Multi-LLM AI Orchestration Platform  
> **Path:** `/Users/himanshurai/project/ai-orchestrator/`  
> **Stack:** Python 3.12 · FastAPI · PostgreSQL + pgvector · Redis · Arq · LiteLLM · MCP · Ollama · Next.js UI  
> **Hardware:** 16GB RAM Mac — local model = `qwen2.5-coder:7b-q8_0` (coding) + `phi4:14b-q4_K_M` (general)  
> **Primary References:** `ai_orchestration_production_architecture.md` · `customeLLM.md` (ChatGPT conversation)  
> **Key Repos to Study:** LLMRouter · Router-R1 · RouteLLM · Open-Multi-Agent · Multi-MCP · Evo-Memory · LiteLLM · Self-Learning-Agents

---

## Phase 0 — Environment & Repository Bootstrap
> **Goal:** Runnable local dev environment. Everything else builds on this.

- [x] **0.1** Create repo structure exactly as specified in arch doc §6
  - `apps/api/` · `apps/worker/` · `src/orchestrator/` · `configs/` · `prompts/` · `tools/mcp/` · `tests/` · `migrations/`
- [x] **0.2** Create `pyproject.toml` with `uv` — pin Python 3.12
  - deps: `fastapi` · `uvicorn` · `pydantic` · `sqlalchemy[asyncio]` · `asyncpg` · `alembic` · `redis[asyncio]` · `arq` · `litellm` · `httpx` · `structlog` · `opentelemetry-sdk`
- [x] **0.3** Write `docker-compose.yml` with memory limits for 16GB Mac
  - Services: `postgres` (pgvector/pg17, 512MB limit) · `redis` (alpine, 256MB) · `ollama` (2GB limit) · `api` · `worker`
  - **No** LibreOffice in base image — reduces image by ~500MB
  - Pin all image versions (no `:latest`)
- [x] **0.4** Create `.env.example` with all variables from arch doc §53
  - Add: `OLLAMA_BASE_URL=http://ollama:11434` · `MAX_TASK_COST_USD=2.00` (personal budget)
- [x] **0.5** Write `Makefile` with targets: `up`, `down`, `migrate`, `test`, `shell`, `logs`
- [x] **0.6** Set up Alembic with `migrations/` and initial empty migration
- [ ] **0.7** Pull local models via Ollama — **skipped for now** (already have `qwen2.5-coder:7b`; registry points at it. Pull the exact tags below when you want the quality bump)
  - `ollama pull qwen2.5-coder:7b-instruct-q8_0` (coding tasks, ~8GB)
  - `ollama pull phi4:14b-q4_K_M` (general/classification, ~9GB)
  - **Note:** Never run both simultaneously on 16GB — router must enforce this

---

## Phase 1 — Core Domain & Model Gateway (Milestone 1)
> **Goal:** Single API request → model selected → execution logged. Reference: arch doc §§7–15, §43–44.  
> **Study first:** [LiteLLM repo](https://github.com/BerriAI/litellm) — provider abstraction patterns

### 1.1 Domain Objects
- [x] **1.1.1** Implement `src/orchestrator/domain/enums.py`
  - `TaskType` · `PrivacyLevel` · `QualityLevel` · `ExecutionStatus`
- [x] **1.1.2** Implement `src/orchestrator/domain/tasks.py`
  - `TaskRequirements` (Pydantic) — all fields from arch doc §9
  - `TaskRequest` — add `session_id: str | None` (missing from doc — needed for personal multi-turn)
- [x] **1.1.3** Implement `src/orchestrator/domain/models.py`
  - `ModelProfile` (frozen dataclass) — arch doc §11
- [x] **1.1.4** Implement `src/orchestrator/domain/tools.py`
  - `ToolProfile` (frozen dataclass) — arch doc §12
  - `RegisteredTool` — arch doc §24

### 1.2 Configuration
- [x] **1.2.1** Write `configs/models.yaml` — model registry
  - Entries: `openai_primary` · `claude_coding` · `gemini_documents` · `local_coder` (qwen2.5) · `local_general` (phi4)
  - Include: capabilities · context_window · quality_score · cost_score · latency_score · privacy_class
- [x] **1.2.2** Write `configs/tools.yaml` — tool registry  
  - Entries: `python` · `ocr` · `pandoc` · `filesystem` · `browser` · `git`
- [x] **1.2.3** Write `configs/routing.yaml` — weights + task preferences — arch doc §17
- [x] **1.2.4** Implement `src/orchestrator/config/settings.py` — load all YAML + env vars via Pydantic Settings

### 1.3 Database Layer
- [x] **1.3.1** Implement all SQLAlchemy models in `src/orchestrator/db/models.py`
  - Tables from arch doc: `users` · `projects` · `tasks` · `workflow_runs` · `task_steps` · `executions` · `models` · `model_capabilities` · `tools` · `tool_capabilities` · `artifacts` · `documents` · `document_chunks` · `routing_events` · `evaluations` · `audit_events` · `approvals`
  - **Add tables missing from doc:** `sessions` (multi-turn) · `lessons` · `lesson_applications` · `rl_experiences` (instrument from day 1)
- [x] **1.3.2** Write Alembic migration for all tables
- [x] **1.3.3** Implement `src/orchestrator/db/session.py` — async SQLAlchemy session factory
- [x] **1.3.4** Implement repositories: `tasks.py` · `runs.py` · `models.py` · `artifacts.py`
- [x] **1.3.5** Write seed scripts: `scripts/seed_models.py` · `scripts/seed_tools.py`

### 1.4 Model Gateway
- [x] **1.4.1** Implement abstract `ModelGateway` — arch doc §13
- [x] **1.4.2** Implement `LiteLLMGateway(ModelGateway)` — route to OpenAI/Anthropic/Google via LiteLLM
- [x] **1.4.3** Implement `LocalGateway(ModelGateway)` — route to Ollama REST API
  - Add: model availability check (prevent running both local models simultaneously on 16GB)
- [x] **1.4.4** Implement `CLIModelGateway(ModelGateway)` — fallback for CLI-only models
  - Uses `asyncio.subprocess` · JSON-mode output contract · timeout + stderr capture
  - **Gap in arch doc** — define JSON envelope protocol for CLI stdout
- [x] **1.4.5** Implement `src/orchestrator/providers/health.py` — liveness check for all providers

### 1.5 Basic Router (Deterministic V1)
- [x] **1.5.1** Implement `ModelScorer` — arch doc §15 scoring formula
- [x] **1.5.2** Implement `ModelRouter` — arch doc §14
  - Hard constraint filters: privacy · context window · capability · budget
  - Soft scoring: quality · cost · latency · historical_success
- [x] **1.5.3** Implement `PolicyEngine` — privacy + tool permission checks — arch doc §25
- [x] **1.5.4** Write unit tests for router: capability filter · privacy rejection · scoring order · fallback
  - Reference: [LLMRouterBench](https://github.com/ynulihao/LLMRouterBench) for evaluation patterns

### 1.6 Minimal FastAPI App + First Endpoint
- [x] **1.6.1** Implement `apps/api/main.py` — FastAPI app + middleware + routers
- [x] **1.6.2** Implement `POST /v1/tasks` — create task, route to model, execute, return result
- [x] **1.6.3** Implement `GET /health` · `GET /ready` — arch doc §54
- [x] **1.6.4** Implement `src/orchestrator/observability/metrics.py` — basic Prometheus counters
  - `task_total` · `model_calls_total` · `execution_cost_usd_total` · `execution_latency_ms`
- [x] **1.6.5** Record every model invocation to `executions` table
- [x] **1.6.6** Record every routing decision to `routing_events` table — **critical for future RL**

**✅ Milestone 1 Deliverable:** `POST /v1/tasks` → model selected by capability/privacy/score → result returned → execution + routing logged to DB

---

## Phase 2 — Tools & MCP Integration (Milestone 2)
> **Goal:** Tasks can invoke tools. Reference: arch doc §§23–26.  
> **Study first:** [Multi-MCP repo](https://github.com/religa/multi_mcp) — Claude+Gemini+GPT+local+MCP patterns

### 2.1 Tool Router
- [x] **2.1.1** Implement `ToolRouter` — arch doc §23
- [x] **2.1.2** Implement `src/orchestrator/tools/permissions.py` — per-workflow tool allowlists
- [x] **2.1.3** Implement `src/orchestrator/tools/registry.py` — dynamic tool registration from `configs/tools.yaml`

### 2.2 MCP Client + Servers
- [x] **2.2.1** Implement `src/orchestrator/tools/mcp_client.py` — MCP tool discovery + invocation
  - Stateless: spawns the target server subprocess per call, tears it down after. Right tradeoff for personal/low-concurrency use; revisit with a pooled session if call volume grows.
  - Passes the full parent environment to server subprocesses (the MCP SDK's default inherited-env allowlist strips `LANG`, which broke tesseract's stderr decoding — see 2.2.3 note)
- [x] **2.2.2** Build `tools/mcp/python/` — Python execution MCP server
  - Lightweight subprocess sandbox: CPU limit via `resource` · memory limit (best-effort — macOS rejects finite `RLIMIT_AS`) · configurable timeout (default 30s) · no network (enforced via macOS `sandbox-exec` Seatbelt profile when available)
- [x] **2.2.3** Build `tools/mcp/ocr/` — OCR MCP server (PyMuPDF text-layer fast path + **PaddleOCR**, not Tesseract)
  - Swapped to PaddleOCR per user direction — already installed/validated in a prior local project (`~/project/pdf-ocr-converter`), more accurate than Tesseract, and its model weights were already cached locally (`~/.paddlex/official_models`) so no fresh download was needed
  - Must `import pymupdf` (not the legacy `fitz` alias) — the alias prints a deprecation warning to *stdout*, which corrupts the MCP stdio JSON-RPC stream
- [x] **2.2.4** Build `tools/mcp/documents/` — Pandoc MCP server (DOCX, MD, PDF)

### 2.3 Tool Adapters
- [x] **2.3.1** `src/orchestrator/tools/adapters/python.py` — sandboxed Python subprocess (via the `python` MCP server)
- [x] **2.3.2** `src/orchestrator/tools/adapters/ocr.py` — scanned PDF → text pipeline (via the `ocr` MCP server)
- [x] **2.3.3** `src/orchestrator/tools/adapters/pandoc.py` — document conversion (via the `documents` MCP server)
- [x] **2.3.4** `src/orchestrator/tools/adapters/filesystem.py` — read/write with path restrictions (in-process, no MCP hop)
- [x] **2.3.5** `src/orchestrator/tools/adapters/browser.py` — web search via httpx + Brave Search API (needs `BRAVE_SEARCH_API_KEY`; raises a clear config error when unset)
- [x] **2.3.6** Implement `src/orchestrator/security/sandbox.py` — sandbox policy enforcement (`run_sandboxed` + `resolve_within`)

### 2.4 Executor Abstraction
- [x] **2.4.1** Abstract `Executor` — arch doc §22 (`src/orchestrator/orchestration/executor.py`)
  - Added `src/orchestrator/domain/workflows.py::TaskStep` ahead of Phase 3.1.2 — the Executor signature is typed against it; Phase 3 builds the WorkflowGraph/scheduler on top of this same dataclass
- [x] **2.4.2** `LLMExecutor` · `ToolExecutor` · `PythonExecutor` · `DocumentExecutor`

### 2.5 Tests
- [x] **2.5.1** Unit: tool permissions · sandbox limits · capability matching (`tests/unit/test_tool_router.py`, `tests/unit/test_tool_permissions.py`, `tests/unit/test_executors.py`, `tests/security/test_sandbox.py`)
- [x] **2.5.2** Integration: PDF → OCR → parse → Pandoc → DOCX, through the real MCP servers (`tests/integration/test_document_pipeline.py`)

**✅ Milestone 2 Deliverable:** Single request → model + tool. E.g. "Extract tables from PDF" → OCR → Python → response.

---

## Phase 3 — Multi-Step Workflow Engine (Milestone 3)
> **Goal:** One user request → DAG of steps → parallel execution. Reference: arch doc §§19–21.  
> **Study first:** [Open-Multi-Agent](https://github.com/open-multi-agent/open-multi-agent) — DAG + checkpoint/resume

### 3.1 Workflow Graph
- [x] **3.1.1** Implement `WorkflowGraph` — arch doc §20
  - `ready_steps(completed)` · `is_complete(completed)`
  - **Add:** cycle detection (critical gap for autonomous planner)
  - **Add:** `max_steps` hard cap (default 25 for personal use)
- [x] **3.1.2** Implement `TaskStep` dataclass — arch doc §19
- [x] **3.1.3** Implement `state_machine.py` — step status transitions
- [x] **3.1.4** Implement `scheduler.py` — `asyncio.gather` for parallel steps

### 3.2 Autonomous Planner
- [x] **3.2.1** Write `prompts/planner/v1.txt` — **most critical prompt in the system**
  - Output: structured JSON DAG with `steps[].id` · `steps[].executor_type` · `steps[].depends_on` · `steps[].output_schema`
  - Hard constraints in prompt: max 20 steps · no circular deps · only registered executors
- [x] **3.2.2** Implement `planner.py`
  - Calls cheap model (phi4-local or GPT-mini) to generate DAG
  - Validates DAG JSON against schema before executing
  - Falls back to rule-based template planner if output invalid
- [x] **3.2.3** Implement `requirements_for(step, request)` — per-step `TaskRequirements` for per-step routing
- [x] **3.2.4** Write rule-based template planner (fallback)
  - Templates: `coding_workflow` · `document_workflow` · `research_workflow` · `writing_workflow` · `data_analysis_workflow`

### 3.3 Orchestrator
- [x] **3.3.1** Implement `Orchestrator.run()` — arch doc §21
  - Policy check → plan → DAG schedule → route → execute → verify → complete
  - Add: `max_repair_attempts` per step (default 2) · deadlock detection
- [x] **3.3.2** Persist workflow state to DB with resume support
- [x] **3.3.3** Emit SSE events at each lifecycle point — arch doc §57

### 3.4 Async Worker with Arq
- [x] **3.4.1** Implement `apps/worker/main.py` — Arq worker process
- [x] **3.4.2** Move `Orchestrator.run()` to background Arq job
- [x] **3.4.3** `POST /v1/tasks` → `202 Accepted` + `{task_id, run_id, status: "running"}`
- [x] **3.4.4** `GET /v1/runs/{run_id}/events` — SSE stream from Redis pub/sub
- [x] **3.4.5** `GET /v1/runs/{run_id}` · `GET /v1/runs/{run_id}/steps`

### 3.5 Tests
- [x] **3.5.1** Unit: DAG scheduling · parallel step detection · cycle detection · deadlock
- [x] **3.5.2** Integration: multi-step workflow (mock models)
- [x] **3.5.3** E2E: "Analyze scanned PDF → extract → calculate → write report → export DOCX"


**✅ Milestone 3 Deliverable:** Autonomous plan generation → DAG execution → SSE stream of live progress to client.

---

## Phase 4 — Context Manager & RAG

- [ ] **4.1** Implement `ContextManager` — arch doc §27
  - `ingest_file()` → parse → chunk → embed → store in `document_chunks`
  - `retrieve(query, top_k)` → pgvector ANN search
  - `build_context(query, token_budget)` → retrieve + rerank + compress
- [ ] **4.2** Implement `chunker.py` — semantic chunking (512 tokens + 64 overlap)
- [ ] **4.3** Implement `embeddings.py`
  - Local: `nomic-embed-text` via Ollama (free, no API cost)
  - Fallback: OpenAI `text-embedding-3-small`
- [ ] **4.4** Implement `retriever.py` — pgvector cosine similarity search
- [ ] **4.5** Implement `assembler.py` — token-budget-aware context assembly
- [ ] **4.6** Implement `POST /v1/files` — upload → ingest → return `file_id`

---

## Phase 5 — Verification Engine

- [ ] **5.1** Abstract `Verifier` — `verify(step, result) -> VerificationResult`
- [ ] **5.2** `SchemaVerifier` — JSON Schema / Pydantic validation
- [ ] **5.3** `PythonVerifier` — deterministic calculation checks
- [ ] **5.4** `FileVerifier` — DOCX/PDF integrity + required sections
- [ ] **5.5** `LLMVerifier` — second model review (only for HIGH/CRITICAL quality tasks)
- [ ] **5.6** `factual.py` — cross-check numerical claims via Python
- [ ] **5.7** Wire verification into `Orchestrator.run()` — repair loop on failure

**Key principle:** `Python > LLM` · `pytest > LLM` · `schema validator > LLM`

---

## Phase 6 — Memory & Lesson System (Instrumentation)
> **Study first:** [Evo-Memory](https://github.com/zhaosnw/evo_mem) · [Self-Learning-Agents](https://github.com/omdivyatej/Self-Learning-Agents)

### 6.1 Session Memory (Gap fix)
- [ ] **6.1.1** `short_term.py` — Redis-backed session context, last 20 messages, TTL 24h
- [ ] **6.1.2** Wire into context assembly — prepend session history

### 6.2 Long-Term Memory
- [ ] **6.2.1** `long_term.py` — pgvector episodic memory (task summaries + outcomes)
- [ ] **6.2.2** `preferences.py` — user preference key-value store

### 6.3 Lesson System (Teacher-Guided RAG)
> Reference: arch doc §§83–88 · ChatGPT doc lines 826–1466

- [ ] **6.3.1** `teacher.py` — calls Claude/GPT to review local model outputs
  - Selective: only when `local_confidence < 0.7` OR task risk >= HIGH OR verification failed
- [ ] **6.3.2** `lesson_miner.py` — extracts reusable rules from teacher critique
  - Output: `{lesson_type, problem, rule, applies_when, priority}`
- [ ] **6.3.3** `lesson_store.py` — persists to `lessons` table with pgvector embedding
- [ ] **6.3.4** `lesson_retriever.py` — top-K lessons before local model invocation
  - Considers: relevance · priority · recency · model_applicability · token_cost
- [ ] **6.3.5** `evaluator.py` + `promotion.py` — validate lessons against benchmark before promoting
- [ ] **6.3.6** Write `policies/coding.yaml` · `policies/writing.yaml` · `policies/document.yaml` · `policies/research.yaml`
- [ ] **6.3.7** Wire lesson retrieval into local model invocation pipeline

### 6.4 RL Instrumentation (Stage 1 — Data Only)
> Reference: arch doc §113 Stage 1 · ChatGPT doc lines 1791–1817

- [ ] **6.4.1** Implement `rewards/reward.py` — composite reward formula
  - `0.30*quality + 0.30*correctness + 0.15*verification + 0.15*user_score + 0.10*completion - cost_penalty - latency_penalty`
- [ ] **6.4.2** Record every decision to `rl_experiences` after each workflow completes
- [ ] **6.4.3** Implement `POST /v1/feedback` — user thumbs up/down → update `rl_experiences.user_score`
- [ ] **6.4.4** Nightly Arq cron: select 10 uncertain/failed executions → teacher review → lesson extraction

**✅ Phase 6 Deliverable:** Local model gets relevant lessons injected. Teacher reviews failures nightly. System collects full RL experience data. No parameter training needed.

---

## Phase 7 — Web UI (Parallel with Phase 3+)

- [ ] **7.1** Scaffold Next.js app in `apps/web/` (TypeScript · Tailwind · shadcn/ui)
- [ ] **7.2** Chat interface — text input + file upload → `POST /v1/tasks`
- [ ] **7.3** Workflow visualizer — SSE subscription → live DAG with step statuses + executor + cost
- [ ] **7.4** Output viewer — markdown · DOCX download · code block
- [ ] **7.5** Task history — past runs with cost/latency summary
- [ ] **7.6** Model dashboard — registered models · capabilities · health
- [ ] **7.7** Thumbs up/down feedback → `POST /v1/feedback`
- [ ] **7.8** Lesson browser — active lessons · priority · improvement metrics
- [ ] **7.9** Cost tracker — running total per session/day/model

---

## Phase 8 — Intelligent Routing (Milestone 6)
> **Study first:** [RouteLLM](https://github.com/lm-sys/RouteLLM) · [LLMRouter](https://github.com/ulab-uiuc/LLMRouter) · [NVIDIA LLM Router](https://github.com/NVIDIA-AI-Blueprints/llm-router)

- [ ] **8.1** Build model performance database — query `routing_events` + `evaluations` + `executions`
- [ ] **8.2** Wire `historical_success` into `ModelScorer` — replace static 0.5 default with real data
- [ ] **8.3** A/B testing — 90% current policy / 10% challenger
- [ ] **8.4** Contextual bandit in `learned_router.py`
  - Epsilon-greedy over (task_type, quality_level) → model
  - Study: [Router-R1](https://github.com/ulab-uiuc/Router-R1) for RL routing algorithm reference
- [ ] **8.5** Escalation policy — "should we trust local model?"
  - Input: local_confidence · task_difficulty · rag_relevance · historical_performance
  - Output: `accept_local` | `escalate_to_claude` | `escalate_to_gpt`
- [ ] **8.6** Policy versioning — record version in every `routing_events` row
- [ ] **8.7** Shadow mode — new policy predicts but doesn't execute (N=500 tasks before promoting)

---

## Phase 9 — Security Hardening

- [ ] **9.1** `redaction.py` — PII/secret detection before cloud calls (API keys · passwords · SSNs)
- [ ] **9.2** `secrets.py` — secrets never appear in model context
- [ ] **9.3** Approval workflow — pause for high-risk tool actions
- [ ] **9.4** Circuit breaker per provider — auto-disable after N consecutive failures
- [ ] **9.5** Dead-letter queue for failed Arq jobs
- [ ] **9.6** Security tests — arch doc §74 checklist

---

## Phase 10 — Observability & Operations

- [ ] **10.1** OpenTelemetry traces — request → policy → plan → each step → executor → verifier
- [ ] **10.2** Full Prometheus metrics — arch doc §58 complete list
- [ ] **10.3** Grafana dashboards — system · model · routing · business metrics
- [ ] **10.4** Artifact TTL cleanup job — nightly Arq cron, delete artifacts > 30 days
- [ ] **10.5** `docs/operations.md` runbook

---

## Reference: GitHub Repos by Component

| Component | Study This Repo | Why |
|---|---|---|
| Learned routing algorithm | [ulab-uiuc/LLMRouter](https://github.com/ulab-uiuc/LLMRouter) | KNN/SVM/MLP/Elo/graph routing strategies |
| RL-based routing | [ulab-uiuc/Router-R1](https://github.com/ulab-uiuc/Router-R1) | RL multi-round routing with cost coefficient |
| Cost/quality threshold routing | [lm-sys/RouteLLM](https://github.com/lm-sys/RouteLLM) | Trained routers, cost savings benchmarks |
| DAG orchestration + multi-model | [open-multi-agent/open-multi-agent](https://github.com/open-multi-agent/open-multi-agent) | DAG + checkpoint/resume + consensus |
| Multi-model + MCP + CLI | [religa/multi_mcp](https://github.com/religa/multi_mcp) | Claude/Gemini/GPT/Ollama + MCP + CLI |
| Self-evolving memory/RAG | [zhaosnw/evo_mem](https://github.com/zhaosnw/evo_mem) | Search→Synthesize→Evolve memory loop |
| Feedback → memory (simple) | [omdivyatej/Self-Learning-Agents](https://github.com/omdivyatej/Self-Learning-Agents) | No-retraining improvement loop |
| Neural routing | [NVIDIA-AI-Blueprints/llm-router](https://github.com/NVIDIA-AI-Blueprints/llm-router) | Intent-based + neural routing |
| Router evaluation | [ynulihao/LLMRouterBench](https://github.com/ynulihao/LLMRouterBench) | Pareto frontier, cost savings metrics |
| CLI agent orchestration | [awslabs/cli-agent-orchestrator](https://github.com/awslabs/cli-agent-orchestrator) | Claude Code + Gemini CLI + supervisor |
| Deterministic YAML workflows | [microsoft/conductor](https://github.com/microsoft/conductor) | No-token orchestration decisions |
| Self-RAG (when to retrieve) | [akariasai/self-rag](https://github.com/akariasai/self-rag) | RL for retrieval decisions |
| Self-improving survey | [selfimproving-agent/Awesome-Self-Improving-Agents](https://github.com/selfimproving-agent/Awesome-Self-Improving-Agents) | Memory, RL, continual learning |
| Unified LLM gateway | [BerriAI/litellm](https://github.com/BerriAI/litellm) | Provider abstraction, cost tracking |

---

## Key Gaps Fixed vs. Architecture Doc

| Gap | Fix Applied |
|---|---|
| No multi-turn session memory | `session_id` in TaskRequest + Redis session store (Phase 6.1) |
| Autonomous planner has no guardrails | Cycle detection + `max_steps` cap + schema validation + template fallback (Phase 3.1) |
| CLI gateway has no protocol spec | JSON envelope protocol + asyncio subprocess adapter (Phase 1.4.4) |
| 16GB RAM — two local models can't coexist | LocalGateway checks/evicts before loading second model (Phase 1.4.3) |
| Planner prompt absent | `prompts/planner/v1.txt` is first artifact to design (Phase 3.2.1) |
| LibreOffice bloats image | Removed — Pandoc handles 95% of conversions |
| Celery is heavy for single user | Replaced with `arq` — lighter, native async Python |
| RL infrastructure never detailed | `rl_experiences` table + reward engine + instrumentation from day 1 (Phase 6.4) |
| `learned_router.py` scaffolded but empty | Contextual bandit spec with study references (Phase 8.4) |
| No streaming UI spec | SSE events + web UI subscribes to `/v1/runs/{id}/events` (Phase 7.3) |
| Cost exploration can burn personal budget | `exploration_disabled_if_budget_remaining < $0.50` policy |
| No embedding model choice specified | Local `nomic-embed-text` via Ollama, fallback to `text-embedding-3-small` |
