"""Structured progress and optional resource telemetry for one engine job."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

from src.pipeline.engine_contract import (
    JobStatus,
    ProgressCallback,
    ProgressEvent,
    ProgressKind,
)

logger = logging.getLogger(__name__)

TELEMETRY_SUMMARY_SCHEMA = "pdfscorebar.engine.telemetry_summary.v1"

_TERMINAL_KIND_BY_STATUS = {
    JobStatus.SUCCEEDED: ProgressKind.JOB_SUCCEEDED,
    JobStatus.REVIEW_REQUIRED: ProgressKind.JOB_REVIEW_REQUIRED,
    JobStatus.FAILED: ProgressKind.JOB_FAILED,
    JobStatus.CANCELLED: ProgressKind.JOB_CANCELLED,
}


class ResourceSampler:
    """Best-effort opt-in process-tree/resource sampler.

    The sampler deliberately does not synchronize CUDA. Process-tree RSS/CPU
    uses psutil when it is available. GPU memory is attributed to PIDs in the
    sampled process tree through nvidia-smi compute-app accounting.
    """

    def __init__(self, *, interval_seconds: float = 1.0) -> None:
        if interval_seconds <= 0:
            raise ValueError("resource sample interval must be positive")
        self.interval_seconds = float(interval_seconds)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._started = False
        self._previous_sample_time: float | None = None
        self._previous_cpu_seconds: float | None = None
        self._sample_count = 0
        self._psutil_available: bool | None = None
        self._nvidia_smi_seen = False
        self._peak_process_tree_rss_bytes = 0
        self._peak_process_tree_cpu_percent = 0.0
        self._peak_process_count = 0
        self._peak_gpu_memory_bytes = 0
        self._peak_device_gpu_utilization_percent = 0.0

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def stop(self) -> None:
        if not self._started:
            return
        self._stop.set()
        self._thread.join(timeout=max(3.0, self.interval_seconds * 2.0 + 2.5))

    def _sample_process_tree(self, sample_time: float) -> tuple[set[int], int, float | None]:
        process_ids = {os.getpid()}
        try:
            import psutil  # type: ignore[import-not-found]
        except Exception:
            self._psutil_available = False
            return process_ids, 0, None

        self._psutil_available = True
        try:
            root = psutil.Process(os.getpid())
            processes = [root]
            try:
                processes.extend(root.children(recursive=True))
            except psutil.Error:
                pass
        except psutil.Error:
            return process_ids, 0, None

        rss_bytes = 0
        cpu_seconds = 0.0
        alive_ids: set[int] = set()
        for process in processes:
            try:
                memory = process.memory_info()
                cpu_times = process.cpu_times()
            except psutil.Error:
                continue
            alive_ids.add(int(process.pid))
            rss_bytes += int(memory.rss)
            cpu_seconds += float(cpu_times.user) + float(cpu_times.system)

        cpu_percent = None
        if self._previous_sample_time is not None and self._previous_cpu_seconds is not None:
            elapsed = max(sample_time - self._previous_sample_time, 1e-9)
            cpu_delta = max(cpu_seconds - self._previous_cpu_seconds, 0.0)
            cpu_percent = (cpu_delta / elapsed) * 100.0

        self._previous_sample_time = sample_time
        self._previous_cpu_seconds = cpu_seconds
        return alive_ids or process_ids, rss_bytes, cpu_percent

    @staticmethod
    def _query_gpu_process_memory(process_ids: set[int]) -> tuple[int, bool]:
        try:
            output = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-compute-apps=pid,used_gpu_memory",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return 0, False

        memory_mib = 0
        for line in output.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) != 2:
                continue
            try:
                pid = int(parts[0])
                used_mib = int(parts[1])
            except ValueError:
                continue
            if pid in process_ids:
                memory_mib += max(used_mib, 0)
        return memory_mib * 1024 * 1024, True

    @staticmethod
    def _query_device_gpu_utilization() -> tuple[float, bool]:
        try:
            output = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return 0.0, False

        values: list[float] = []
        for line in output.splitlines():
            try:
                values.append(float(line.strip()))
            except ValueError:
                continue
        return (max(values) if values else 0.0), bool(values)

    def _sample_once(self) -> None:
        sample_time = time.perf_counter()
        process_ids, rss_bytes, cpu_percent = self._sample_process_tree(sample_time)
        gpu_memory_bytes, gpu_memory_seen = self._query_gpu_process_memory(process_ids)
        gpu_utilization, gpu_utilization_seen = self._query_device_gpu_utilization()

        self._sample_count += 1
        self._peak_process_count = max(self._peak_process_count, len(process_ids))
        self._peak_process_tree_rss_bytes = max(self._peak_process_tree_rss_bytes, rss_bytes)
        if cpu_percent is not None:
            self._peak_process_tree_cpu_percent = max(
                self._peak_process_tree_cpu_percent,
                cpu_percent,
            )
        self._peak_gpu_memory_bytes = max(self._peak_gpu_memory_bytes, gpu_memory_bytes)
        self._peak_device_gpu_utilization_percent = max(
            self._peak_device_gpu_utilization_percent,
            gpu_utilization,
        )
        self._nvidia_smi_seen = self._nvidia_smi_seen or gpu_memory_seen or gpu_utilization_seen

    def _run(self) -> None:
        while not self._stop.is_set():
            self._sample_once()
            self._stop.wait(self.interval_seconds)

    def summary(self) -> dict[str, float | int]:
        """Return only numeric fields suitable for JobResult.resources."""

        result: dict[str, float | int] = {
            "resource_sample_count": self._sample_count,
            "resource_sample_interval_seconds": self.interval_seconds,
        }
        if self._psutil_available:
            result.update(
                {
                    "peak_process_tree_rss_bytes": self._peak_process_tree_rss_bytes,
                    "peak_process_tree_cpu_percent": self._peak_process_tree_cpu_percent,
                    "peak_process_count": self._peak_process_count,
                }
            )
        if self._nvidia_smi_seen:
            result.update(
                {
                    "peak_gpu_memory_bytes": self._peak_gpu_memory_bytes,
                    "peak_device_gpu_utilization_percent": (
                        self._peak_device_gpu_utilization_percent
                    ),
                }
            )
        return result


class TelemetryRecorder:
    """Emit stable ProgressEvent records and retain compact stage/resource summary."""

    def __init__(
        self,
        job_id: str,
        *,
        on_progress: ProgressCallback | None = None,
        sample_resources: bool = False,
        resource_sample_interval_seconds: float = 1.0,
    ) -> None:
        if not job_id or not job_id.strip():
            raise ValueError("job_id must be a non-empty string")
        self.job_id = job_id
        self.on_progress = on_progress
        self._sequence = 0
        self._terminal_emitted = False
        self._started = False
        self._closed = False
        self._start_ns: int | None = None
        self._finished_ns: int | None = None
        self._stage_spans: list[dict[str, Any]] = []
        self._sink_error_count = 0
        self._resource_sampler = (
            ResourceSampler(interval_seconds=resource_sample_interval_seconds)
            if sample_resources
            else None
        )

    @property
    def active(self) -> bool:
        return self.on_progress is not None or self._resource_sampler is not None

    def start_job(self) -> ProgressEvent | None:
        if self._started:
            return None
        self._started = True
        self._start_ns = time.perf_counter_ns()
        if self._resource_sampler is not None:
            self._resource_sampler.start()
        return self.emit(ProgressKind.JOB_STARTED, "job")

    def _dispatch(self, event: ProgressEvent) -> None:
        if self.on_progress is None:
            return
        try:
            self.on_progress(event)
        except Exception:
            self._sink_error_count += 1
            logger.exception("Structured progress sink raised; continuing engine execution.")

    def emit(
        self,
        kind: ProgressKind,
        stage_id: str,
        *,
        page_number: int | None = None,
        completed_units: int | None = None,
        total_units: int | None = None,
        unit: str | None = None,
        elapsed_ms: int | None = None,
        detail_code: str | None = None,
    ) -> ProgressEvent:
        if self._terminal_emitted:
            raise RuntimeError("no telemetry events are allowed after terminal")
        event = ProgressEvent(
            job_id=self.job_id,
            sequence=self._sequence,
            kind=kind,
            stage_id=stage_id,
            page_number=page_number,
            completed_units=completed_units,
            total_units=total_units,
            unit=unit,
            elapsed_ms=elapsed_ms,
            detail_code=detail_code,
        )
        self._sequence += 1
        if event.terminal:
            self._terminal_emitted = True
        self._dispatch(event)
        return event

    def progress(
        self,
        stage_id: str,
        *,
        page_number: int | None = None,
        completed_units: int | None = None,
        total_units: int | None = None,
        unit: str | None = None,
        detail_code: str | None = None,
    ) -> ProgressEvent:
        return self.emit(
            ProgressKind.STAGE_PROGRESS,
            stage_id,
            page_number=page_number,
            completed_units=completed_units,
            total_units=total_units,
            unit=unit,
            detail_code=detail_code,
        )

    @contextmanager
    def stage(
        self,
        stage_id: str,
        *,
        completed_units: int | None = None,
        total_units: int | None = None,
        unit: str | None = None,
        detail_code: str | None = None,
    ) -> Iterator[None]:
        self.emit(
            ProgressKind.STAGE_STARTED,
            stage_id,
            completed_units=completed_units,
            total_units=total_units,
            unit=unit,
            detail_code=detail_code,
        )
        started_ns = time.perf_counter_ns()
        completed = False
        try:
            yield
            completed = True
        finally:
            elapsed_ms = max((time.perf_counter_ns() - started_ns) // 1_000_000, 0)
            span = {
                "stage_id": stage_id,
                "elapsed_ms": elapsed_ms,
                "state": "completed" if completed else "aborted",
            }
            if detail_code is not None:
                span["detail_code"] = detail_code
            self._stage_spans.append(span)
            if completed and not self._terminal_emitted:
                self.emit(
                    ProgressKind.STAGE_COMPLETED,
                    stage_id,
                    completed_units=completed_units,
                    total_units=total_units,
                    unit=unit,
                    elapsed_ms=elapsed_ms,
                    detail_code=detail_code,
                )

    def terminal(self, status: JobStatus) -> ProgressEvent:
        status = JobStatus(status)
        if not self._started:
            self.start_job()
        elapsed_ms = self.elapsed_ms
        event = self.emit(
            _TERMINAL_KIND_BY_STATUS[status],
            "job",
            elapsed_ms=elapsed_ms,
        )
        self.close()
        return event

    @property
    def elapsed_ms(self) -> int:
        if self._start_ns is None:
            return 0
        end_ns = self._finished_ns if self._finished_ns is not None else time.perf_counter_ns()
        return max((end_ns - self._start_ns) // 1_000_000, 0)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._finished_ns = time.perf_counter_ns()
        if self._resource_sampler is not None:
            self._resource_sampler.stop()

    def job_resources(self) -> dict[str, float | int]:
        resources: dict[str, float | int] = {
            "wall_time_seconds": self.elapsed_ms / 1000.0,
            "progress_sink_error_count": self._sink_error_count,
        }
        if self._resource_sampler is not None:
            resources.update(self._resource_sampler.summary())
        return resources

    def summary(self) -> dict[str, Any]:
        return {
            "schema": TELEMETRY_SUMMARY_SCHEMA,
            "job_id": self.job_id,
            "stage_spans": [dict(span) for span in self._stage_spans],
            "resources": self.job_resources(),
        }
