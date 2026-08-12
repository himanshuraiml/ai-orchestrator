import uuid
from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, Double, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from orchestrator.db.base import Base

# nomic-embed-text (the local/default embedder — tasks.md 4.3) natively
# outputs 768 dims; the OpenAI fallback requests the same via its
# `dimensions` param so both providers share one pgvector column.
EMBEDDING_DIM = 768


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class Session(Base):
    """Multi-turn conversation session. Gap fix vs. architecture doc §6/§9."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True
    )

    goal: Mapped[str] = mapped_column(Text, nullable=False)

    task_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirements: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", index=True)

    plan: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    total_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), default=0)
    total_latency_ms: Mapped[int | None] = mapped_column(BigInteger, default=0)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class TaskStep(Base):
    __tablename__ = "task_steps"

    id: Mapped[uuid.UUID] = _uuid_pk()
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    step_key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    dependencies: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    executor_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    executor_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    input_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", index=True)

    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Execution(Base):
    __tablename__ = "executions"

    id: Mapped[uuid.UUID] = _uuid_pk()

    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_steps.id", ondelete="CASCADE"), nullable=False
    )

    executor_type: Mapped[str] = mapped_column(Text, nullable=False)
    executor_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    provider: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(Text, nullable=False)

    request_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    response_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    input_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    error_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False, index=True)


class Model(Base):
    __tablename__ = "models"

    id: Mapped[str] = mapped_column(Text, primary_key=True)

    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)

    context_window: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    quality_score: Mapped[float | None] = mapped_column(Double, nullable=True)
    cost_score: Mapped[float | None] = mapped_column(Double, nullable=True)
    latency_score: Mapped[float | None] = mapped_column(Double, nullable=True)

    privacy_class: Mapped[str] = mapped_column(Text, nullable=False)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ModelCapability(Base):
    __tablename__ = "model_capabilities"

    model_id: Mapped[str] = mapped_column(
        Text, ForeignKey("models.id", ondelete="CASCADE"), primary_key=True
    )
    capability: Mapped[str] = mapped_column(Text, primary_key=True)


class Tool(Base):
    __tablename__ = "tools"

    id: Mapped[str] = mapped_column(Text, primary_key=True)

    name: Mapped[str] = mapped_column(Text, nullable=False)
    server: Mapped[str | None] = mapped_column(Text, nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    risk_level: Mapped[str] = mapped_column(Text, nullable=False, default="low")

    requires_network: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_filesystem: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)


class ToolCapability(Base):
    __tablename__ = "tool_capabilities"

    tool_id: Mapped[str] = mapped_column(
        Text, ForeignKey("tools.id", ondelete="CASCADE"), primary_key=True
    )
    capability: Mapped[str] = mapped_column(Text, primary_key=True)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = _uuid_pk()

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)

    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)

    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    checksum: Mapped[str | None] = mapped_column(Text, nullable=True)

    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _uuid_pk()

    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id"), nullable=False
    )

    parser: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = _uuid_pk()

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)


class RoutingEvent(Base):
    __tablename__ = "routing_events"

    id: Mapped[uuid.UUID] = _uuid_pk()

    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_runs.id"), nullable=True
    )
    task_step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_steps.id"), nullable=True
    )

    candidate_models: Mapped[list] = mapped_column(JSONB, nullable=False)
    selected_model: Mapped[str] = mapped_column(Text, nullable=False)

    routing_reason: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    predicted_score: Mapped[float | None] = mapped_column(Double, nullable=True)

    actual_success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    user_rating: Mapped[float | None] = mapped_column(Double, nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = _uuid_pk()

    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("executions.id"), nullable=True
    )

    evaluator_type: Mapped[str] = mapped_column(Text, nullable=False)

    score: Mapped[float | None] = mapped_column(Double, nullable=True)

    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    feedback: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = _uuid_pk()

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    action: Mapped[str] = mapped_column(Text, nullable=False)

    resource_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False, index=True)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = _uuid_pk()

    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_runs.id"), nullable=False
    )
    task_step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_steps.id"), nullable=False
    )

    action: Mapped[str] = mapped_column(Text, nullable=False)

    risk_level: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")

    requested_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class Lesson(Base):
    """Teacher-mined rule for the lesson system (Phase 6.3)."""

    __tablename__ = "lessons"

    id: Mapped[uuid.UUID] = _uuid_pk()

    lesson_type: Mapped[str] = mapped_column(Text, nullable=False)
    problem: Mapped[str] = mapped_column(Text, nullable=False)
    rule: Mapped[str] = mapped_column(Text, nullable=False)

    applies_when: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    priority: Mapped[float] = mapped_column(Double, nullable=False, default=0.5)
    model_applicability: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="candidate", index=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LessonApplication(Base):
    """Records each time a lesson was retrieved/applied, for effectiveness tracking."""

    __tablename__ = "lesson_applications"

    id: Mapped[uuid.UUID] = _uuid_pk()

    lesson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_steps.id"), nullable=True
    )
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("executions.id"), nullable=True
    )

    applied_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    outcome_success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    outcome_score: Mapped[float | None] = mapped_column(Double, nullable=True)


class RLExperience(Base):
    """Stage-1 RL data collection (Phase 6.4) — no training, just instrumentation."""

    __tablename__ = "rl_experiences"

    id: Mapped[uuid.UUID] = _uuid_pk()

    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_runs.id"), nullable=True
    )
    task_step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_steps.id"), nullable=True
    )

    state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    action: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    reward: Mapped[float | None] = mapped_column(Double, nullable=True)
    reward_components: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    user_score: Mapped[float | None] = mapped_column(Double, nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False, index=True)
