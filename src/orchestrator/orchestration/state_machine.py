"""State Machine — arch doc Phase 3.1.3.

Validates and executes state transitions for TaskStep and WorkflowRun entities.
"""

from orchestrator.domain.enums import ExecutionStatus


class InvalidStateTransitionError(ValueError):
    """Raised when an invalid state transition is attempted."""


# Allowed state transitions: current_state -> set of valid target_states
STEP_TRANSITIONS: dict[ExecutionStatus, set[ExecutionStatus]] = {
    ExecutionStatus.PENDING: {
        ExecutionStatus.RUNNING,
        ExecutionStatus.CANCELLED,
        ExecutionStatus.WAITING_APPROVAL,
    },
    ExecutionStatus.WAITING_APPROVAL: {
        ExecutionStatus.RUNNING,
        ExecutionStatus.CANCELLED,
    },
    ExecutionStatus.RUNNING: {
        ExecutionStatus.SUCCEEDED,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
    },
    ExecutionStatus.FAILED: {
        ExecutionStatus.RUNNING,  # Allowed for retry/repair
        ExecutionStatus.CANCELLED,
    },
    ExecutionStatus.SUCCEEDED: set(),  # Terminal
    ExecutionStatus.CANCELLED: set(),  # Terminal
}


RUN_TRANSITIONS: dict[ExecutionStatus, set[ExecutionStatus]] = {
    ExecutionStatus.PENDING: {
        ExecutionStatus.RUNNING,
        ExecutionStatus.CANCELLED,
    },
    ExecutionStatus.RUNNING: {
        ExecutionStatus.SUCCEEDED,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
    },
    ExecutionStatus.FAILED: {
        ExecutionStatus.RUNNING,  # Re-run / resume
    },
    ExecutionStatus.SUCCEEDED: set(),
    ExecutionStatus.CANCELLED: set(),
}


def transition_step_status(
    current: ExecutionStatus, target: ExecutionStatus
) -> ExecutionStatus:
    """Transition a step state, validating against STEP_TRANSITIONS."""
    if current == target:
        return current
    allowed = STEP_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStateTransitionError(
            f"Cannot transition TaskStep from {current.value!r} to {target.value!r}"
        )
    return target


def transition_run_status(
    current: ExecutionStatus, target: ExecutionStatus
) -> ExecutionStatus:
    """Transition a run state, validating against RUN_TRANSITIONS."""
    if current == target:
        return current
    allowed = RUN_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStateTransitionError(
            f"Cannot transition WorkflowRun from {current.value!r} to {target.value!r}"
        )
    return target
