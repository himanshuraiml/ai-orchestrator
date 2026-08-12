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
