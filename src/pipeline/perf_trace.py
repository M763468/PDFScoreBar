"""Opt-in, process-safe performance spans for dense pipeline attribution.

The tracer is deliberately inert unless ``PDFSCORE_PERF_TRACE_DIR`` is set.
Each process appends to its own JSONL file, so child workers never share a
descriptor with the parent or contend on a common output file.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import os
import resource
import time
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "pdfscore_perf_trace_context", default={}
)


def enabled() -> bool:
    return bool(os.environ.get("PDFSCORE_PERF_TRACE_DIR"))


def _cpu_seconds() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return float(usage.ru_utime + usage.ru_stime)


def _sync_cuda() -> bool:
    """Synchronize CUDA when available and report whether it was used."""
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.synchronize()
            return True
    except (ImportError, RuntimeError):
        pass
    return False


def _trace_path() -> Path | None:
    raw = os.environ.get("PDFSCORE_PERF_TRACE_DIR")
    if not raw:
        return None
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path / f"trace-{os.getpid()}.jsonl"


def set_context(**values: Any) -> contextvars.Token[dict[str, Any]] | None:
    """Set run/page/role metadata for spans in the current execution context."""
    if not enabled():
        return None
    merged = dict(_context.get())
    merged.update({key: value for key, value in values.items() if value is not None})
    return _context.set(merged)


def reset_context(token: contextvars.Token[dict[str, Any]] | None) -> None:
    if token is not None:
        _context.reset(token)


def record(
    name: str,
    *,
    start: float,
    cpu_start: float,
    success: bool,
    error: str | None = None,
    cuda_synchronized: bool = False,
    call_count: int | None = None,
    bytes_count: int | None = None,
    **fields: Any,
) -> None:
    path = _trace_path()
    if path is None:
        return
    end = time.perf_counter()
    payload: dict[str, Any] = {
        "schema_version": "pipeline.perf_trace.v1",
        "run_id": os.environ.get("PDFSCORE_PERF_TRACE_RUN"),
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "process_role": os.environ.get("PDFSCORE_PERF_TRACE_ROLE"),
        "stage": name,
        "start_monotonic": start,
        "end_monotonic": end,
        "duration_sec": end - start,
        "cpu_time_sec": _cpu_seconds() - cpu_start,
        "cuda_synchronized": cuda_synchronized,
        "success": success,
        **_context.get(),
        **fields,
    }
    if error is not None:
        payload["error"] = error
    if call_count is not None:
        payload["call_count"] = call_count
    if bytes_count is not None:
        payload["bytes"] = bytes_count
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


@contextlib.contextmanager
def span(
    name: str, *, cuda: bool = False, fields: Mapping[str, Any] | None = None, **extra: Any
) -> Iterator[None]:
    """Record a span and close it correctly on exceptions.

    CUDA spans synchronize immediately before and after the operation. The
    synchronization flag is false when tracing is disabled, so production
    execution is unchanged by default.
    """
    if not enabled():
        yield
        return
    sync_before = _sync_cuda() if cuda else False
    started = time.perf_counter()
    cpu_started = _cpu_seconds()
    try:
        yield
    except Exception as error:
        sync_after = _sync_cuda() if cuda else False
        record(
            name,
            start=started,
            cpu_start=cpu_started,
            success=False,
            error=f"{type(error).__name__}: {error}",
            cuda_synchronized=sync_before or sync_after,
            **(dict(fields or {}) | extra),
        )
        raise
    else:
        sync_after = _sync_cuda() if cuda else False
        record(
            name,
            start=started,
            cpu_start=cpu_started,
            success=True,
            cuda_synchronized=sync_before or sync_after,
            **(dict(fields or {}) | extra),
        )
