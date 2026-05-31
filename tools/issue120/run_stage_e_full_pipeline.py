import argparse
import contextlib
import json
import logging
import os
import resource
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from src.pipeline.core.config import load_yaml
from src.pipeline.detector_routes.dense_full_pipeline import reconstruct_dense_full_pipeline_route
from src.pipeline.main import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _linux_maxrss_bytes(maxrss: int) -> int:
    """Convert Linux resource.ru_maxrss KiB units to bytes."""
    return maxrss * 1024


def _cpu_seconds(usage: resource.struct_rusage) -> float:
    return float(usage.ru_utime) + float(usage.ru_stime)


def _load_optional_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_gpu_sample() -> list[dict[str, Any]]:
    """Return a best-effort nvidia-smi sample. Empty when NVIDIA tooling is unavailable."""
    if shutil.which("nvidia-smi") is None:
        return []
    cmd = [
        "nvidia-smi",
        "--query-gpu=uuid,index,name,memory.used,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []

    samples: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 5:
            continue
        uuid, index, name, memory_used_mb, utilization_gpu_pct = parts
        try:
            memory_used_mb_value = int(memory_used_mb)
            utilization_gpu_pct_value = int(utilization_gpu_pct)
        except ValueError:
            continue
        samples.append(
            {
                "uuid": uuid,
                "index": int(index) if index.isdigit() else index,
                "name": name,
                "memory_used_mb": memory_used_mb_value,
                "utilization_gpu_pct": utilization_gpu_pct_value,
            }
        )
    return samples


def _summarize_console_log(path: Path) -> dict[str, Any]:
    """Summarize captured stdout/stderr without loading the whole file into memory."""
    marker_counts = {
        "homr": 0,
        "real_esrgan": 0,
        "measure_numbering": 0,
        "progress_bar": 0,
        "warning_or_error": 0,
    }
    summary: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "line_count": 0,
        "logger_counts": {},
        "marker_counts": marker_counts.copy(),
    }
    summary_path = path.with_suffix(".summary.json")
    if not path.exists():
        summary["summary_path"] = str(summary_path)
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return summary

    logger_counts: dict[str, int] = {}
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            summary["line_count"] += 1
            lower = line.lower()
            if "homr" in lower:
                marker_counts["homr"] += 1
            if "real-esrgan" in lower or "realesrgan" in lower or "real_esrgan" in lower:
                marker_counts["real_esrgan"] += 1
            if "measure_numbering" in lower:
                marker_counts["measure_numbering"] += 1
            if "|" in line and "%" in line:
                marker_counts["progress_bar"] += 1
            if "warning" in lower or "error" in lower or "traceback" in lower:
                marker_counts["warning_or_error"] += 1

            parts = line.split()
            if len(parts) >= 4 and parts[2].startswith("[") and parts[2].endswith("]"):
                logger_name = parts[3].rstrip(":")
                logger_counts[logger_name] = logger_counts.get(logger_name, 0) + 1

    summary["logger_counts"] = dict(
        sorted(logger_counts.items(), key=lambda item: item[1], reverse=True)[:20]
    )
    summary["marker_counts"] = marker_counts
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def _is_warning_or_error_line(line: str) -> bool:
    lower = line.lower()
    return any(
        marker in lower
        for marker in (
            "warning",
            "error",
            "traceback",
            "exception",
            "failed",
            "failure",
        )
    )


def _is_progress_line(line: str) -> bool:
    if "|" in line and "%" in line:
        return True
    return False


def _is_real_esrgan_tile_line(stripped: str) -> bool:
    return stripped.startswith("Tile ") and "/" in stripped


def _low_value_marker_keys(line: str) -> list[str]:
    stripped = line.strip()
    markers: list[str] = []
    marker_checks = (
        ("realesrgan_tile", _is_real_esrgan_tile_line(stripped)),
        ("homr_download_progress", stripped.startswith("Downloaded ")),
        ("homr_dewarping_staff", stripped.startswith("Dewarping staff")),
        (
            "homr_tromr_inference",
            stripped.startswith("Running TrOmr inference on staff image"),
        ),
        ("homr_creating_bounds", stripped.startswith("Creating bounds for")),
        ("homr_cache_notice", stripped.startswith(("Found a cache", "Loading from cache"))),
        ("homr_tuple_cleanup", stripped.startswith("Removing tuplets from measure")),
        ("homr_choice_check", stripped.startswith("_check_choices_intelligently:")),
        ("rapidocr_info", "[RapidOCR]" in stripped),
        ("onnxruntime_warning", "[W:onnxruntime" in stripped),
        ("onnxruntime_fallback", "Fallback mode. May be extremely slow." in stripped),
        ("homr_staff_fragment_count", " staff line fragments" in stripped),
        ("homr_notehead_count", " noteheads" in stripped),
        ("homr_note_segmentation_count", " notes during segmentation" in stripped),
        ("homr_notehead_height", "Average note head height:" in stripped),
        ("homr_tromr_timing", "Inference Time Tromr:" in stripped),
        ("homr_segnet_timing", "Segnet Inference time:" in stripped),
    )
    for key, matched in marker_checks:
        if matched:
            markers.append(key)
    return markers


def _is_low_value_external_line(
    line: str,
    *,
    preserve_homr_internal: bool = False,
    preserve_sr_tile_logs: bool = False,
) -> bool:
    if _is_warning_or_error_line(line):
        return False
    stripped = line.strip()
    lower = stripped.lower()
    if not stripped:
        return False
    if _is_real_esrgan_tile_line(stripped):
        return not preserve_sr_tile_logs
    if preserve_homr_internal:
        return False
    low_value_prefixes = (
        "Downloaded ",
        "Dewarping staff",
        "Running TrOmr inference on staff image",
        "Creating bounds for",
        "Found a cache",
        "Loading from cache",
        "Saving cache",
        "Removing tuplets from measure",
        "_check_choices_intelligently:",
    )
    low_value_markers = (
        "[RapidOCR]",
        "[W:onnxruntime",
        "Fallback mode. May be extremely slow.",
        " staff line fragments",
        " noteheads",
        " notes during segmentation",
        "Average note head height:",
        "Inference Time Tromr:",
        "Segnet Inference time:",
    )
    return stripped.startswith(low_value_prefixes) or any(
        marker.lower() in lower for marker in low_value_markers
    )


def _strip_low_value_suffix_from_progress_line(line: str) -> str:
    if not _is_progress_line(line):
        return line
    for marker in (
        "\x1b[",
        "Found ",
        "Inference Time Tromr:",
        "Removing tuplets from measure",
        "_check_choices_intelligently:",
    ):
        if marker in line:
            prefix = line.split(marker, 1)[0].rstrip()
            if prefix:
                return prefix + "\n"
    return line


def _suppress_low_value_external_raw_log(
    path: Path,
    *,
    preserve_homr_internal: bool = False,
    preserve_sr_tile_logs: bool = False,
) -> dict[str, Any]:
    """Rewrite raw stdout/stderr with known low-value external chatter removed."""
    stats = {
        "schema_version": "tools.issue120.stage_e_low_value_raw_suppression.v1",
        "path": str(path),
        "preserve_homr_internal": preserve_homr_internal,
        "preserve_sr_tile_logs": preserve_sr_tile_logs,
        "input_line_count": 0,
        "output_line_count": 0,
        "suppressed_line_count": 0,
        "sanitized_progress_line_count": 0,
        "low_value_marker_counts": {},
        "suppressed_marker_counts": {},
    }
    if not path.exists():
        return stats
    low_value_marker_counts: dict[str, int] = {}
    suppressed_marker_counts: dict[str, int] = {}
    temp_path = path.with_name(f"{path.stem}.filtered{path.suffix}")
    with path.open("r", encoding="utf-8", errors="replace") as src:
        with temp_path.open("w", encoding="utf-8") as dst:
            for line in src:
                stats["input_line_count"] += 1
                marker_keys = _low_value_marker_keys(line)
                for marker_key in marker_keys:
                    low_value_marker_counts[marker_key] = (
                        low_value_marker_counts.get(marker_key, 0) + 1
                    )
                sanitized = _strip_low_value_suffix_from_progress_line(line)
                marker_removed_by_sanitization = sanitized != line and bool(marker_keys)
                if sanitized != line:
                    stats["sanitized_progress_line_count"] += 1
                    for marker_key in marker_keys:
                        suppressed_marker_counts[marker_key] = (
                            suppressed_marker_counts.get(marker_key, 0) + 1
                        )
                if _is_low_value_external_line(
                    sanitized,
                    preserve_homr_internal=preserve_homr_internal,
                    preserve_sr_tile_logs=preserve_sr_tile_logs,
                ):
                    stats["suppressed_line_count"] += 1
                    if not marker_removed_by_sanitization:
                        for marker_key in marker_keys:
                            suppressed_marker_counts[marker_key] = (
                                suppressed_marker_counts.get(marker_key, 0) + 1
                            )
                    continue
                dst.write(sanitized)
                stats["output_line_count"] += 1
    stats["low_value_marker_counts"] = dict(sorted(low_value_marker_counts.items()))
    stats["suppressed_marker_counts"] = dict(sorted(suppressed_marker_counts.items()))
    temp_path.replace(path)
    return stats


def _filter_default_console_log(*, raw_path: Path, filtered_path: Path) -> dict[str, Any]:
    """Write a bounded default console log while preserving raw stdout/stderr separately."""
    stats = {
        "schema_version": "tools.issue120.stage_e_console_filter.v1",
        "raw_path": str(raw_path),
        "filtered_path": str(filtered_path),
        "raw_line_count": 0,
        "kept_line_count": 0,
        "dropped_line_count": 0,
        "dropped_progress_line_count": 0,
        "dropped_external_raw_line_count": 0,
        "filtered_log_written": False,
    }
    filtered_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = filtered_path.with_name(f"{filtered_path.stem}.tmp{filtered_path.suffix}")
    with raw_path.open("r", encoding="utf-8", errors="replace") as src:
        with temp_path.open("w", encoding="utf-8") as dst:
            for line in src:
                stats["raw_line_count"] += 1
                if _is_warning_or_error_line(line):
                    dst.write(line)
                    stats["kept_line_count"] += 1
                    continue
                stats["dropped_line_count"] += 1
                if _is_progress_line(line):
                    stats["dropped_progress_line_count"] += 1
                else:
                    stats["dropped_external_raw_line_count"] += 1
    if stats["kept_line_count"] > 0:
        temp_path.replace(filtered_path)
        stats["filtered_log_written"] = True
    else:
        temp_path.unlink(missing_ok=True)
        filtered_path.unlink(missing_ok=True)
    return stats


class CapturedProgressMirror:
    """Mirror selected captured fd-level lines to the original console while retaining raw logs."""

    def __init__(self, *, capture_path: Path, mirror_progress: bool = True) -> None:
        self.capture_path = capture_path
        self.mirror_progress = mirror_progress
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._console_stderr_fd: int | None = None
        self._position = 0
        self._mirrored_progress_line_count = 0
        self._mirrored_warning_or_error_line_count = 0
        self._lock = threading.Lock()

    def start(self) -> None:
        self._console_stderr_fd = os.dup(2)
        self._thread = threading.Thread(
            target=self._run,
            name="stage-e-captured-progress-mirror",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._drain_once()
        if self._console_stderr_fd is not None:
            os.write(self._console_stderr_fd, b"\n")
            os.close(self._console_stderr_fd)
            self._console_stderr_fd = None
        return self.summary()

    def summary(self) -> dict[str, Any]:
        return {
            "schema_version": "tools.issue120.stage_e_console_progress_mirror.v1",
            "capture_path": str(self.capture_path),
            "mirror_progress": self.mirror_progress,
            "mirrored_progress_line_count": self._mirrored_progress_line_count,
            "mirrored_warning_or_error_line_count": self._mirrored_warning_or_error_line_count,
        }

    def _run(self) -> None:
        while not self._stop.wait(0.5):
            self._drain_once()

    def _drain_once(self) -> None:
        with self._lock:
            if self._console_stderr_fd is None or not self.capture_path.exists():
                return
            with self.capture_path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(self._position)
                while True:
                    line = f.readline()
                    if not line:
                        break
                    self._position = f.tell()
                    self._mirror_line(line)

    def _mirror_line(self, line: str) -> None:
        if self._console_stderr_fd is None:
            return
        if _is_warning_or_error_line(line):
            os.write(self._console_stderr_fd, ("\n" + line).encode("utf-8", errors="replace"))
            self._mirrored_warning_or_error_line_count += 1
            return
        if self.mirror_progress and _is_progress_line(line):
            os.write(
                self._console_stderr_fd,
                ("\r" + line.rstrip()).encode("utf-8", errors="replace"),
            )
            self._mirrored_progress_line_count += 1


class ResourceSampler:
    """Best-effort process/GPU resource sampler for long Stage E runs."""

    def __init__(self, *, output_path: Path, interval_sec: float) -> None:
        if interval_sec <= 0:
            raise ValueError("Resource sample interval must be positive.")
        self.output_path = output_path
        self.interval_sec = interval_sec
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sample_count = 0
        self._peak_self_maxrss_bytes = 0
        self._peak_children_maxrss_bytes = 0
        self._peak_psutil_rss_bytes = 0
        self._peak_psutil_children_rss_bytes = 0
        self._peak_gpu_memory_mb_by_uuid: dict[str, int] = {}
        self._peak_gpu_utilization_pct_by_uuid: dict[str, int] = {}
        self._peak_process_tree_cpu_percent = 0.0
        self._peak_rusage_cpu_percent = 0.0
        self._psutil_available: bool | None = None
        self._nvidia_smi_seen = False
        self._started_at: float | None = None
        self._finished_at: float | None = None
        self._previous_sample_time: float | None = None
        self._previous_rusage_cpu_sec: float | None = None
        self._previous_process_tree_sample_time: float | None = None
        self._previous_process_tree_cpu_sec: float | None = None

    def start(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._started_at = time.perf_counter()
        self._thread = threading.Thread(
            target=self._run, name="stage-e-resource-sampler", daemon=True
        )
        self._thread.start()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(self.interval_sec * 2, 1.0))
        self._finished_at = time.perf_counter()
        summary = self.summary()
        summary_path = self.output_path.with_suffix(".summary.json")
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        summary["summary_path"] = str(summary_path)
        return summary

    def _sample_rusage(self, sample_time: float) -> dict[str, Any]:
        self_rusage = resource.getrusage(resource.RUSAGE_SELF)
        children_rusage = resource.getrusage(resource.RUSAGE_CHILDREN)
        self_maxrss_bytes = _linux_maxrss_bytes(self_rusage.ru_maxrss)
        children_maxrss_bytes = _linux_maxrss_bytes(children_rusage.ru_maxrss)
        self._peak_self_maxrss_bytes = max(self._peak_self_maxrss_bytes, self_maxrss_bytes)
        self._peak_children_maxrss_bytes = max(
            self._peak_children_maxrss_bytes, children_maxrss_bytes
        )

        total_cpu_sec = _cpu_seconds(self_rusage) + _cpu_seconds(children_rusage)
        rusage_cpu_percent = None
        if self._previous_sample_time is not None and self._previous_rusage_cpu_sec is not None:
            elapsed = max(sample_time - self._previous_sample_time, 1e-9)
            cpu_delta = max(total_cpu_sec - self._previous_rusage_cpu_sec, 0.0)
            rusage_cpu_percent = (cpu_delta / elapsed) * 100.0
            self._peak_rusage_cpu_percent = max(self._peak_rusage_cpu_percent, rusage_cpu_percent)
        self._previous_sample_time = sample_time
        self._previous_rusage_cpu_sec = total_cpu_sec

        return {
            "self_maxrss_bytes": self_maxrss_bytes,
            "children_maxrss_bytes": children_maxrss_bytes,
            "self_cpu_sec": _cpu_seconds(self_rusage),
            "children_cpu_sec": _cpu_seconds(children_rusage),
            "total_rusage_cpu_sec": total_cpu_sec,
            "rusage_cpu_percent_since_previous_sample": rusage_cpu_percent,
        }

    def _sample_process_tree(self, sample_time: float) -> dict[str, Any]:
        sample: dict[str, Any] = {**self._sample_rusage(sample_time), "psutil_available": False}

        try:
            import psutil  # type: ignore[import-not-found]
        except Exception:
            self._psutil_available = False
            return sample

        self._psutil_available = True
        proc = psutil.Process(os.getpid())
        processes = [proc]
        try:
            processes.extend(proc.children(recursive=True))
        except psutil.Error:
            pass

        rss_bytes = 0
        children_rss_bytes = 0
        process_count = 0
        process_tree_cpu_times_sec = 0.0
        for idx, child in enumerate(processes):
            try:
                memory = child.memory_info()
                cpu_times = child.cpu_times()
                rss_bytes += int(memory.rss)
                if idx > 0:
                    children_rss_bytes += int(memory.rss)
                process_tree_cpu_times_sec += float(cpu_times.user) + float(cpu_times.system)
                process_count += 1
            except psutil.Error:
                continue

        process_tree_cpu_percent = None
        if (
            self._previous_process_tree_sample_time is not None
            and self._previous_process_tree_cpu_sec is not None
        ):
            elapsed = max(sample_time - self._previous_process_tree_sample_time, 1e-9)
            cpu_delta = max(process_tree_cpu_times_sec - self._previous_process_tree_cpu_sec, 0.0)
            process_tree_cpu_percent = (cpu_delta / elapsed) * 100.0
            self._peak_process_tree_cpu_percent = max(
                self._peak_process_tree_cpu_percent, process_tree_cpu_percent
            )
        self._previous_process_tree_sample_time = sample_time
        self._previous_process_tree_cpu_sec = process_tree_cpu_times_sec

        self._peak_psutil_rss_bytes = max(self._peak_psutil_rss_bytes, rss_bytes)
        self._peak_psutil_children_rss_bytes = max(
            self._peak_psutil_children_rss_bytes, children_rss_bytes
        )
        sample.update(
            {
                "psutil_available": True,
                "process_tree_rss_bytes": rss_bytes,
                "children_rss_bytes": children_rss_bytes,
                "process_count": process_count,
                "process_tree_cpu_times_sec": process_tree_cpu_times_sec,
                "process_tree_cpu_percent_since_previous_sample": process_tree_cpu_percent,
            }
        )
        return sample

    def _record_gpu_peaks(self, gpu_samples: list[dict[str, Any]]) -> None:
        if gpu_samples:
            self._nvidia_smi_seen = True
        for sample in gpu_samples:
            uuid = str(sample.get("uuid"))
            memory = int(sample.get("memory_used_mb", 0))
            utilization = int(sample.get("utilization_gpu_pct", 0))
            self._peak_gpu_memory_mb_by_uuid[uuid] = max(
                self._peak_gpu_memory_mb_by_uuid.get(uuid, 0), memory
            )
            self._peak_gpu_utilization_pct_by_uuid[uuid] = max(
                self._peak_gpu_utilization_pct_by_uuid.get(uuid, 0), utilization
            )

    def _run(self) -> None:
        with self.output_path.open("w", encoding="utf-8") as f:
            while not self._stop.is_set():
                sample_time = time.perf_counter()
                sample = {
                    "timestamp_monotonic_sec": sample_time,
                    "process": self._sample_process_tree(sample_time),
                    "gpu": _read_gpu_sample(),
                }
                self._record_gpu_peaks(sample["gpu"])
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
                f.flush()
                self._sample_count += 1
                self._stop.wait(self.interval_sec)

    def summary(self) -> dict[str, Any]:
        duration_sec = None
        if self._started_at is not None:
            end = self._finished_at if self._finished_at is not None else time.perf_counter()
            duration_sec = end - self._started_at
        return {
            "schema_version": "tools.issue120.stage_e_resource_summary.v3",
            "samples_path": str(self.output_path),
            "sample_count": self._sample_count,
            "sample_interval_sec": self.interval_sec,
            "duration_sec": duration_sec,
            "psutil_available": self._psutil_available,
            "nvidia_smi_seen": self._nvidia_smi_seen,
            "peak_self_maxrss_bytes": self._peak_self_maxrss_bytes,
            "peak_children_maxrss_bytes": self._peak_children_maxrss_bytes,
            "peak_process_tree_rss_bytes": self._peak_psutil_rss_bytes,
            "peak_process_tree_children_rss_bytes": self._peak_psutil_children_rss_bytes,
            "peak_rusage_cpu_percent": self._peak_rusage_cpu_percent,
            "peak_process_tree_cpu_percent": self._peak_process_tree_cpu_percent,
            "peak_gpu_memory_mb_by_uuid": self._peak_gpu_memory_mb_by_uuid,
            "peak_gpu_utilization_pct_by_uuid": self._peak_gpu_utilization_pct_by_uuid,
        }


@contextlib.contextmanager
def _redirect_stdout_stderr_to_file(path: Path):
    """Redirect fd-level stdout/stderr so subprocess-heavy logs are kept in a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout.flush()
    sys.stderr.flush()
    original_stdout_fd = os.dup(1)
    original_stderr_fd = os.dup(2)
    with path.open("w", encoding="utf-8", buffering=1) as log_file:
        os.dup2(log_file.fileno(), 1)
        os.dup2(log_file.fileno(), 2)
        try:
            yield
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(original_stdout_fd, 1)
            os.dup2(original_stderr_fd, 2)
            os.close(original_stdout_fd)
            os.close(original_stderr_fd)


@contextlib.contextmanager
def _temporary_env(overrides: dict[str, str]):
    """Temporarily set environment variables and restore their previous values."""
    previous = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _env_flag_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def main():
    parser = argparse.ArgumentParser(description="Run Stage E full 68-page pipeline.")
    parser.add_argument(
        "--config", type=Path, default="configs/issue120_stage_e_full_pipeline.yaml"
    )
    parser.add_argument(
        "--inventory", type=Path, default="logs/issue36_prep/20260208_bench_inventory.json"
    )
    parser.add_argument(
        "--exclude", type=Path, default="logs/issue36_prep/excluded_pages_for_gt_prep.json"
    )
    parser.add_argument("--output-root", type=Path, default="logs/issue120_e2e_recovery")
    parser.add_argument(
        "--dense-route-verbose-logs",
        action="store_true",
        help="Write full subprocess logs for dense-route reconstruction. Defaults to compact bounded logs.",
    )
    parser.add_argument(
        "--expected-pages",
        type=int,
        default=68,
        help="Expected dense-route page count. Keep 68 for canonical Stage E; use a smaller value only for smoke checks.",
    )
    parser.add_argument(
        "--resource-sample-interval-sec",
        type=float,
        default=5.0,
        help="Sampling interval for Stage E process/GPU resource usage.",
    )
    parser.add_argument(
        "--no-resource-sampling",
        action="store_true",
        help="Disable Stage E process/GPU resource sampling.",
    )
    parser.add_argument(
        "--pipeline-console-log",
        type=Path,
        default=None,
        help="File for stdout/stderr emitted by full pipeline execution. Defaults under the Stage E run directory.",
    )
    parser.add_argument(
        "--pipeline-diagnostic-logs",
        action="store_true",
        help=(
            "Keep verbose pipeline INFO/progress output in the captured stdout/stderr log. "
            "By default Stage E captures warning/error output and leaves detailed logs in pipeline.log."
        ),
    )
    args = parser.parse_args()

    if not args.inventory.exists():
        logger.error(f"Inventory not found: {args.inventory}")
        sys.exit(1)
    if not args.exclude.exists():
        logger.error(f"Exclude file not found: {args.exclude}")
        sys.exit(1)
    if not args.no_resource_sampling and args.resource_sample_interval_sec <= 0:
        parser.error(
            "--resource-sample-interval-sec must be positive when resource sampling is enabled."
        )

    route_root = args.output_root / "stage_e_full_pipeline"
    if route_root.exists():
        logger.info("Removing stale Stage E run directory: %s", route_root)
        shutil.rmtree(route_root)
    route_root.mkdir(parents=True, exist_ok=True)

    run_started_at = time.perf_counter()
    route_artifacts = reconstruct_dense_full_pipeline_route(
        inventory=args.inventory,
        exclude=args.exclude,
        route_root=route_root,
        expected_pages=args.expected_pages,
        verbose_logs=args.dense_route_verbose_logs,
    )

    route_images_dir = route_root / "images"
    route_images_dir.mkdir(parents=True, exist_ok=True)

    image_copy_started_at = time.perf_counter()
    logger.info(f"Copying {len(route_artifacts.image_paths)} images to {route_images_dir}...")
    for img_path in route_artifacts.image_paths:
        dest_path = route_images_dir / f"{img_path.parent.name}_{img_path.name}"
        shutil.copy2(img_path, dest_path)
    image_copy_duration_sec = time.perf_counter() - image_copy_started_at

    config = load_yaml(args.config)
    if "inputs" not in config:
        config["inputs"] = {}
    if "pdf_to_images" not in config["inputs"]:
        config["inputs"]["pdf_to_images"] = {}
    if "detection" not in config:
        config["detection"] = {}

    config["inputs"]["pdf_to_images"]["output_dir"] = str(route_images_dir)
    config["inputs"]["pdf_to_images"]["image_glob"] = "*.png"
    config["run"]["run_id"] = "stage_e_full_pipeline"
    config["detection"]["precomputed_probe_candidates_root"] = str(
        route_artifacts.probe_rescue_root
    )
    config["detection"]["cnn_bands_from"] = str(route_artifacts.filtered_root)
    config["detection"]["probe_use_original_images"] = True

    temp_config_path = route_root / "stage_e_config.yaml"
    import yaml

    with open(temp_config_path, "w") as f:
        yaml.dump(config, f, sort_keys=False)

    pipeline_console_log = args.pipeline_console_log or route_root / "pipeline_stdout_stderr.log"
    pipeline_diagnostic_logs = args.pipeline_diagnostic_logs or _env_flag_enabled(
        "PDFSCORE_STAGE_E_DIAGNOSTIC_LOGS"
    )
    pipeline_capture_log = (
        pipeline_console_log
        if pipeline_diagnostic_logs
        else pipeline_console_log.with_name(
            f"{pipeline_console_log.stem}.raw{pipeline_console_log.suffix}"
        )
    )
    pipeline_console_level = logging.INFO if pipeline_diagnostic_logs else logging.WARNING
    progress_env_overrides: dict[str, str] = {}
    resource_sampler = None
    resource_summary: dict[str, Any] | None = None
    progress_mirror = None
    progress_mirror_summary = None
    if not args.no_resource_sampling:
        resource_sampler = ResourceSampler(
            output_path=route_root / "stage_e_resource_samples.jsonl",
            interval_sec=args.resource_sample_interval_sec,
        )

    logger.info(f"Starting pipeline using config: {temp_config_path}")
    logger.info("Pipeline stdout/stderr will be captured to %s", pipeline_capture_log)
    logger.info(
        "Pipeline logging mode: %s (console_level=%s, progress_bars=%s)",
        "diagnostic" if pipeline_diagnostic_logs else "default_quiet",
        logging.getLevelName(pipeline_console_level),
        "captured" if pipeline_diagnostic_logs else "mirrored_to_console_and_filtered_from_log",
    )

    pipeline_started_at = time.perf_counter()
    try:
        if resource_sampler is not None:
            resource_sampler.start()
        if not pipeline_diagnostic_logs:
            progress_mirror = CapturedProgressMirror(capture_path=pipeline_capture_log)
            progress_mirror.start()
        with _redirect_stdout_stderr_to_file(pipeline_capture_log):
            with _temporary_env(progress_env_overrides):
                run_pipeline(
                    config_path=temp_config_path,
                    run_id="stage_e_full_pipeline",
                    output_root=args.output_root,
                    console_log_level=pipeline_console_level,
                )
    finally:
        if progress_mirror is not None:
            progress_mirror_summary = progress_mirror.stop()
        if resource_sampler is not None:
            resource_summary = resource_sampler.stop()
    pipeline_duration_sec = time.perf_counter() - pipeline_started_at

    pipeline_phase_summary_path = route_root / "pipeline_phase_summary.json"
    pipeline_phase_summary = _load_optional_json(pipeline_phase_summary_path)
    low_value_raw_suppression_summary = None
    console_filter_summary = None
    if not pipeline_diagnostic_logs:
        low_value_raw_suppression_summary = _suppress_low_value_external_raw_log(
            pipeline_capture_log,
            preserve_homr_internal=_env_flag_enabled("PDFSCORE_HOMR_VERBOSE_INTERNAL_LOGS"),
            preserve_sr_tile_logs=_env_flag_enabled("PDFSCORE_SR_TILE_LOGS"),
        )
        console_filter_summary = _filter_default_console_log(
            raw_path=pipeline_capture_log,
            filtered_path=pipeline_console_log,
        )
    pipeline_console_log_summary = _summarize_console_log(pipeline_console_log)
    run_summary_path = route_root / "stage_e_runtime_summary.json"
    run_summary = {
        "schema_version": "tools.issue120.stage_e_full_pipeline.runtime_summary.v1",
        "total_duration_sec": time.perf_counter() - run_started_at,
        "dense_route_execution_summary": route_artifacts.execution_summary,
        "image_copy": {
            "duration_sec": image_copy_duration_sec,
            "image_count": len(route_artifacts.image_paths),
            "output_dir": str(route_images_dir),
        },
        "pipeline": {
            "duration_sec": pipeline_duration_sec,
            "config_path": str(temp_config_path),
            "run_id": "stage_e_full_pipeline",
            "output_root": str(args.output_root),
            "phase_summary_path": str(pipeline_phase_summary_path),
            "phase_summary": pipeline_phase_summary,
            "stdout_stderr_log": str(pipeline_console_log),
            "stdout_stderr_raw_log": str(pipeline_capture_log)
            if pipeline_capture_log != pipeline_console_log
            else None,
            "stdout_stderr_raw_log_size_bytes": pipeline_capture_log.stat().st_size
            if pipeline_capture_log.exists()
            else 0,
            "stdout_stderr_log_size_bytes": pipeline_console_log_summary["size_bytes"],
            "stdout_stderr_log_summary": pipeline_console_log_summary,
            "stdout_stderr_low_value_raw_suppression_summary": (low_value_raw_suppression_summary),
            "stdout_stderr_filter_summary": console_filter_summary,
            "stdout_stderr_progress_mirror_summary": progress_mirror_summary,
            "logging_policy": {
                "schema_version": "tools.issue120.stage_e_pipeline_logging_policy.v1",
                "mode": "diagnostic" if pipeline_diagnostic_logs else "default_quiet",
                "console_log_level": logging.getLevelName(pipeline_console_level),
                "progress_bars_console_mirrored": not pipeline_diagnostic_logs,
                "detail_artifact": str(route_root / "pipeline.log"),
                "raw_stdout_stderr_artifact": str(pipeline_capture_log)
                if pipeline_capture_log != pipeline_console_log
                else None,
                "diagnostic_enable": (
                    "--pipeline-diagnostic-logs or PDFSCORE_STAGE_E_DIAGNOSTIC_LOGS=1"
                ),
            },
        },
        "resource_monitor": resource_summary,
    }
    run_summary_path.write_text(
        json.dumps(run_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(
        "Captured pipeline stdout/stderr summary: lines=%s size_bytes=%s markers=%s",
        pipeline_console_log_summary["line_count"],
        pipeline_console_log_summary["size_bytes"],
        pipeline_console_log_summary["marker_counts"],
    )
    logger.info("Stage E runtime summary written to %s", run_summary_path)
    logger.info("Stage E full pipeline run completed.")


if __name__ == "__main__":
    main()
