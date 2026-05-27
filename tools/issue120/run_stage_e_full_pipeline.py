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


def _merge_mapping(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge mapping values for local experiment config overlays."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge_mapping(base[key], value)
        else:
            base[key] = value
    return base


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
    summary: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "line_count": 0,
        "homr_marker_count": 0,
        "real_esrgan_marker_count": 0,
        "measure_numbering_marker_count": 0,
        "progress_bar_marker_count": 0,
        "warning_or_error_marker_count": 0,
    }
    if not path.exists():
        return summary

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            summary["line_count"] += 1
            lowered = line.lower()
            if "homr" in lowered:
                summary["homr_marker_count"] += 1
            if "real-esrgan" in lowered or "realesrgan" in lowered:
                summary["real_esrgan_marker_count"] += 1
            if "measure numbering" in lowered or "numbering" in lowered:
                summary["measure_numbering_marker_count"] += 1
            if "it/s" in lowered or "%|" in lowered:
                summary["progress_bar_marker_count"] += 1
            if "warning" in lowered or "error" in lowered or "traceback" in lowered:
                summary["warning_or_error_marker_count"] += 1
    return summary


class ResourceSampler:
    """Best-effort sampler for CPU/RSS/GPU usage during subprocess-heavy Stage E runs."""

    def __init__(self, *, output_path: Path, interval_sec: float):
        self.output_path = output_path
        self.summary_path = output_path.with_suffix(".summary.json")
        self.interval_sec = interval_sec
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._sample_count = 0
        self._started_at: float | None = None
        self._baseline_self_usage = resource.getrusage(resource.RUSAGE_SELF)
        self._baseline_children_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        self._peak_self_maxrss_bytes = 0
        self._peak_children_maxrss_bytes = 0
        self._peak_psutil_rss_bytes: int | None = None
        self._peak_psutil_children_rss_bytes: int | None = None
        self._peak_rusage_cpu_percent = 0.0
        self._peak_process_tree_cpu_percent: float | None = None
        self._peak_gpu_memory_mb_by_uuid: dict[str, int] = {}
        self._peak_gpu_utilization_pct_by_uuid: dict[str, int] = {}
        self._psutil_available = False
        self._process = None
        try:
            import psutil  # type: ignore

            self._process = psutil.Process(os.getpid())
            self._psutil_available = True
        except Exception:
            self._process = None
            self._psutil_available = False

    def start(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._started_at = time.perf_counter()
        self._thread = threading.Thread(target=self._run, name="stage-e-resource-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> dict[str, Any]:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(5.0, self.interval_sec * 2.0))
        summary = self._build_summary()
        self.summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return summary

    def _run(self) -> None:
        last_cpu_seconds = _cpu_seconds(self._baseline_self_usage) + _cpu_seconds(
            self._baseline_children_usage
        )
        last_time = self._started_at or time.perf_counter()
        last_process_tree_cpu_seconds: float | None = None
        if self._process is not None:
            last_process_tree_cpu_seconds = self._process_tree_cpu_seconds()
        with self.output_path.open("w", encoding="utf-8") as handle:
            while not self._stop_event.is_set():
                now = time.perf_counter()
                sample = self._sample(now, last_time, last_cpu_seconds, last_process_tree_cpu_seconds)
                last_time = now
                last_cpu_seconds = sample.pop("_rusage_total_cpu_seconds")
                last_process_tree_cpu_seconds = sample.pop("_process_tree_cpu_seconds", None)
                handle.write(json.dumps(sample, ensure_ascii=False) + "\n")
                handle.flush()
                self._sample_count += 1
                self._stop_event.wait(self.interval_sec)

    def _sample(
        self,
        now: float,
        last_time: float,
        last_cpu_seconds: float,
        last_process_tree_cpu_seconds: float | None,
    ) -> dict[str, Any]:
        elapsed = now - (self._started_at or now)
        interval = max(now - last_time, 1e-9)
        self_usage = resource.getrusage(resource.RUSAGE_SELF)
        children_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        self_maxrss_bytes = _linux_maxrss_bytes(self_usage.ru_maxrss)
        children_maxrss_bytes = _linux_maxrss_bytes(children_usage.ru_maxrss)
        self._peak_self_maxrss_bytes = max(self._peak_self_maxrss_bytes, self_maxrss_bytes)
        self._peak_children_maxrss_bytes = max(
            self._peak_children_maxrss_bytes, children_maxrss_bytes
        )
        total_cpu_seconds = _cpu_seconds(self_usage) + _cpu_seconds(children_usage)
        rusage_cpu_percent = ((total_cpu_seconds - last_cpu_seconds) / interval) * 100.0
        self._peak_rusage_cpu_percent = max(self._peak_rusage_cpu_percent, rusage_cpu_percent)

        psutil_sample: dict[str, Any] | None = None
        process_tree_cpu_seconds: float | None = None
        if self._process is not None:
            psutil_sample, process_tree_cpu_seconds = self._sample_process_tree(
                interval, last_process_tree_cpu_seconds
            )

        gpu_samples = _read_gpu_sample()
        for gpu_sample in gpu_samples:
            uuid = str(gpu_sample["uuid"])
            self._peak_gpu_memory_mb_by_uuid[uuid] = max(
                self._peak_gpu_memory_mb_by_uuid.get(uuid, 0), int(gpu_sample["memory_used_mb"])
            )
            self._peak_gpu_utilization_pct_by_uuid[uuid] = max(
                self._peak_gpu_utilization_pct_by_uuid.get(uuid, 0),
                int(gpu_sample["utilization_gpu_pct"]),
            )

        sample = {
            "elapsed_sec": elapsed,
            "interval_sec": interval,
            "self_maxrss_bytes": self_maxrss_bytes,
            "children_maxrss_bytes": children_maxrss_bytes,
            "rusage_cpu_percent": rusage_cpu_percent,
            "psutil": psutil_sample,
            "gpu": gpu_samples,
            "_rusage_total_cpu_seconds": total_cpu_seconds,
        }
        if process_tree_cpu_seconds is not None:
            sample["_process_tree_cpu_seconds"] = process_tree_cpu_seconds
        return sample

    def _process_tree_cpu_seconds(self) -> float | None:
        if self._process is None:
            return None
        try:
            processes = [self._process] + self._process.children(recursive=True)
            total = 0.0
            for proc in processes:
                try:
                    cpu_times = proc.cpu_times()
                except Exception:
                    continue
                total += float(cpu_times.user) + float(cpu_times.system)
            return total
        except Exception:
            return None

    def _sample_process_tree(
        self, interval: float, last_cpu_seconds: float | None
    ) -> tuple[dict[str, Any] | None, float | None]:
        if self._process is None:
            return None, None
        try:
            processes = [self._process] + self._process.children(recursive=True)
            rss_bytes = 0
            children_rss_bytes = 0
            child_count = 0
            current_cpu_seconds = 0.0
            for index, proc in enumerate(processes):
                try:
                    memory_info = proc.memory_info()
                    cpu_times = proc.cpu_times()
                except Exception:
                    continue
                rss_bytes += int(memory_info.rss)
                current_cpu_seconds += float(cpu_times.user) + float(cpu_times.system)
                if index > 0:
                    child_count += 1
                    children_rss_bytes += int(memory_info.rss)
            cpu_percent = None
            if last_cpu_seconds is not None:
                cpu_percent = ((current_cpu_seconds - last_cpu_seconds) / interval) * 100.0
            self._peak_psutil_rss_bytes = max(self._peak_psutil_rss_bytes or 0, rss_bytes)
            self._peak_psutil_children_rss_bytes = max(
                self._peak_psutil_children_rss_bytes or 0, children_rss_bytes
            )
            if cpu_percent is not None:
                self._peak_process_tree_cpu_percent = max(
                    self._peak_process_tree_cpu_percent or 0.0, cpu_percent
                )
            return (
                {
                    "process_tree_rss_bytes": rss_bytes,
                    "process_tree_children_rss_bytes": children_rss_bytes,
                    "process_tree_child_count": child_count,
                    "process_tree_cpu_percent": cpu_percent,
                },
                current_cpu_seconds,
            )
        except Exception:
            return None, last_cpu_seconds

    def _build_summary(self) -> dict[str, Any]:
        return {
            "schema_version": "tools.issue120.stage_e_full_pipeline.resource_summary.v3",
            "samples_path": str(self.output_path),
            "summary_path": str(self.summary_path),
            "sample_count": self._sample_count,
            "interval_sec": self.interval_sec,
            "duration_sec": (time.perf_counter() - self._started_at) if self._started_at else None,
            "psutil_available": self._psutil_available,
            "nvidia_smi_available": shutil.which("nvidia-smi") is not None,
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


def main():
    parser = argparse.ArgumentParser(description="Run Stage E full 68-page pipeline.")
    parser.add_argument("--config", type=Path, default="configs/issue120_stage_e_full_pipeline.yaml")
    parser.add_argument("--inventory", type=Path, default="logs/issue36_prep/20260208_bench_inventory.json")
    parser.add_argument("--exclude", type=Path, default="logs/issue36_prep/excluded_pages_for_gt_prep.json")
    parser.add_argument("--output-root", type=Path, default="logs/issue120_e2e_recovery")
    parser.add_argument(
        "--config-override",
        type=Path,
        default=None,
        help="Optional YAML overlay merged into the Stage E config for local experiments.",
    )
    parser.add_argument(
        "--dense-route-verbose-logs",
        action="store_true",
        help="Write full subprocess logs for dense-route reconstruction. Defaults to compact bounded logs.",
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
    args = parser.parse_args()

    if not args.inventory.exists():
        logger.error(f"Inventory not found: {args.inventory}")
        sys.exit(1)
    if not args.exclude.exists():
        logger.error(f"Exclude file not found: {args.exclude}")
        sys.exit(1)
    if not args.no_resource_sampling and args.resource_sample_interval_sec <= 0:
        parser.error("--resource-sample-interval-sec must be positive when resource sampling is enabled.")

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
    if args.config_override is not None:
        if not args.config_override.exists():
            logger.error("Config override not found: %s", args.config_override)
            sys.exit(1)
        override_config = load_yaml(args.config_override)
        if not isinstance(override_config, dict):
            parser.error("--config-override must point to a YAML mapping.")
        _merge_mapping(config, override_config)
    if "inputs" not in config:
        config["inputs"] = {}
    if "pdf_to_images" not in config["inputs"]:
        config["inputs"]["pdf_to_images"] = {}
    if "detection" not in config:
        config["detection"] = {}

    config["inputs"]["pdf_to_images"]["output_dir"] = str(route_images_dir)
    config["inputs"]["pdf_to_images"]["image_glob"] = "*.png"
    config["run"]["run_id"] = "stage_e_full_pipeline"
    config["detection"]["precomputed_probe_candidates_root"] = str(route_artifacts.probe_rescue_root)
    config["detection"]["cnn_bands_from"] = str(route_artifacts.filtered_root)
    config["detection"]["probe_use_original_images"] = True

    temp_config_path = route_root / "stage_e_config.yaml"
    import yaml

    with open(temp_config_path, "w") as f:
        yaml.dump(config, f, sort_keys=False)

    pipeline_console_log = args.pipeline_console_log or route_root / "pipeline_stdout_stderr.log"
    resource_sampler = None
    resource_summary: dict[str, Any] | None = None
    if not args.no_resource_sampling:
        resource_sampler = ResourceSampler(
            output_path=route_root / "stage_e_resource_samples.jsonl",
            interval_sec=args.resource_sample_interval_sec,
        )

    logger.info(f"Starting pipeline using config: {temp_config_path}")
    logger.info("Pipeline stdout/stderr will be captured to %s", pipeline_console_log)

    pipeline_started_at = time.perf_counter()
    try:
        if resource_sampler is not None:
            resource_sampler.start()
        with _redirect_stdout_stderr_to_file(pipeline_console_log):
            run_pipeline(
                config_path=temp_config_path,
                run_id="stage_e_full_pipeline",
                output_root=args.output_root,
            )
    finally:
        if resource_sampler is not None:
            resource_summary = resource_sampler.stop()
    pipeline_duration_sec = time.perf_counter() - pipeline_started_at

    pipeline_phase_summary_path = route_root / "pipeline_phase_summary.json"
    pipeline_phase_summary = _load_optional_json(pipeline_phase_summary_path)
    pipeline_console_log_summary = _summarize_console_log(pipeline_console_log)
    homr_route_experiment_summary_path = (
        route_root / "stage_e_hybrid_output" / "stage_e_full_pipeline" / "homr_route_parallel_experiment_summary.json"
    )
    homr_route_experiment_summary = _load_optional_json(homr_route_experiment_summary_path)
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
            "config_override_path": str(args.config_override) if args.config_override else None,
            "run_id": "stage_e_full_pipeline",
            "output_root": str(args.output_root),
            "phase_summary_path": str(pipeline_phase_summary_path),
            "phase_summary": pipeline_phase_summary,
            "stdout_stderr_log": str(pipeline_console_log),
            "stdout_stderr_log_size_bytes": pipeline_console_log_summary["size_bytes"],
            "stdout_stderr_log_summary": pipeline_console_log_summary,
            "homr_route_parallel_experiment_summary_path": str(homr_route_experiment_summary_path),
            "homr_route_parallel_experiment_summary": homr_route_experiment_summary,
        },
        "resource_monitor": resource_summary,
    }
    run_summary_path.write_text(json.dumps(run_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Stage E runtime summary written to %s", run_summary_path)
    logger.info("Stage E full pipeline run completed.")


if __name__ == "__main__":
    main()
