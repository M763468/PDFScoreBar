"""One-job lifecycle control primitives aligned with the engine contract v1.

This module provides cooperative cancellation/deadline checks and maps those
control outcomes into the already-versioned JobStatus/EngineError envelope.
It does not implement queueing, retries, persistence, or the production
pipeline adapter.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from src.pipeline.engine_contract import EngineError, ErrorCategory, JobStatus


class LifecycleControlError(RuntimeError):
    """Base class for lifecycle-control exceptions observed at safe checkpoints."""

    def __init__(self, message: str, *, stage_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.stage_id = stage_id


class JobCancelled(LifecycleControlError):
    """Raised when explicit cancellation is observed at a safe checkpoint."""


class JobDeadlineExceeded(LifecycleControlError):
    """Raised when the monotonic one-job execution deadline has expired."""


@dataclass
class CancellationToken:
    """Thread-safe cooperative cancellation signal.

    The first cancellation reason wins so later callers cannot rewrite the
    diagnostic reason after cancellation has become observable.
    """

    _event: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _reason: Optional[str] = field(default=None, init=False, repr=False)

    def cancel(self, reason: Optional[str] = None) -> bool:
        """Request cancellation; return True only for the first request."""

        with self._lock:
            if self._event.is_set():
                return False
            self._reason = reason
            self._event.set()
            return True

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> Optional[str]:
        with self._lock:
            return self._reason


@dataclass(frozen=True)
class ExecutionDeadline:
    """Monotonic deadline for one engine attempt."""

    deadline_monotonic: float

    @classmethod
    def after(cls, seconds: float, *, now: Optional[float] = None) -> "ExecutionDeadline":
        if seconds <= 0:
            raise ValueError("deadline duration must be > 0 seconds")
        start = time.monotonic() if now is None else float(now)
        return cls(deadline_monotonic=start + float(seconds))

    def remaining_seconds(self, *, now: Optional[float] = None) -> float:
        current = time.monotonic() if now is None else float(now)
        return max(0.0, self.deadline_monotonic - current)

    def expired(self, *, now: Optional[float] = None) -> bool:
        current = time.monotonic() if now is None else float(now)
        return current >= self.deadline_monotonic


@dataclass(frozen=True)
class ExecutionControl:
    """Cancellation/deadline control checked at explicit safe boundaries."""

    cancellation: Optional[CancellationToken] = None
    deadline: Optional[ExecutionDeadline] = None

    @classmethod
    def with_timeout(
        cls,
        seconds: float,
        *,
        cancellation: Optional[CancellationToken] = None,
        now: Optional[float] = None,
    ) -> "ExecutionControl":
        return cls(
            cancellation=cancellation,
            deadline=ExecutionDeadline.after(seconds, now=now),
        )

    def checkpoint(
        self,
        *,
        stage_id: Optional[str] = None,
        now: Optional[float] = None,
    ) -> None:
        """Raise when explicit cancellation or deadline expiry is observed.

        Explicit cancellation has deterministic precedence if both conditions
        are already true at the same checkpoint.
        """

        if self.cancellation is not None and self.cancellation.cancelled:
            message = "Job cancellation requested"
            reason = self.cancellation.reason
            if reason:
                message += f": {reason}"
            raise JobCancelled(message, stage_id=stage_id)

        if self.deadline is not None and self.deadline.expired(now=now):
            raise JobDeadlineExceeded(
                "Job execution deadline exceeded",
                stage_id=stage_id,
            )

    def remaining_timeout(self, *, now: Optional[float] = None) -> Optional[float]:
        """Return remaining deadline seconds, or None when unbounded."""

        if self.deadline is None:
            return None
        return self.deadline.remaining_seconds(now=now)


def classify_control_error(
    error: LifecycleControlError,
) -> tuple[JobStatus, EngineError]:
    """Map lifecycle control exceptions into the normative engine contract v1.

    Cancellation is a distinct terminal JobStatus. Deadline expiry is a failed
    attempt with a resource-category EngineError. Detailed stage/message data is
    retained only in debug_context; default public serialization remains safe.
    """

    debug_context = {"exception": type(error).__name__, "message": str(error)}
    if error.stage_id:
        debug_context["stage_id"] = error.stage_id

    if isinstance(error, JobCancelled):
        return (
            JobStatus.CANCELLED,
            EngineError(
                category=ErrorCategory.CANCELLED,
                code="job_cancelled",
                public_message="The job was cancelled.",
                user_actionable=False,
                retryable=False,
                debug_context=debug_context,
            ),
        )

    if isinstance(error, JobDeadlineExceeded):
        return (
            JobStatus.FAILED,
            EngineError(
                category=ErrorCategory.RESOURCE,
                code="execution_deadline_exceeded",
                public_message="The job exceeded its execution deadline.",
                user_actionable=False,
                retryable=True,
                debug_context=debug_context,
            ),
        )

    raise TypeError(f"Unsupported lifecycle control error: {type(error).__name__}")
