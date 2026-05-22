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


class ResourceSampler:
    """Best-effort process/GPU resource sampler for long Stage E runs."""

    def __init__(self, *, output_path: Path, interval_sec: float) -> None:
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
        self._psutil_available: bool | None = None
        self._nvidia_smi_seen = False
        self._started_at: float | None = None
        self._finished_at: float | None = None

    def start(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._started_at = time.perf_counter()
        self._thread = threading.Thread(target=self._run, name="stage-e-resource-sampler", daemon=True)
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

    def _sample_process_tree(self) -> dict[str, Any]:
        self_rusage = resource.getrusage(resource.RUSAGE_SELF)
        children_rusage = resource.getrusage(resource.RUSAGE_CHILDREN)
        self_maxrss_bytes = _linux_maxrss_bytes(self_rusage.ru_maxrss)
        children_maxrss_bytes = _linux_maxrss_bytes(children_rusage.ru_maxrss)
        self._peak_self_maxrss_bytes = max(self._peak_self_maxrss_bytes, self_maxrss_bytes)
        self._peak_children_maxrss_bytes = max(self._peak_children_maxrss_bytes, children_maxrss_bytes)

        sample: dict[str, Any] = {
            "self_maxrss_bytes": self_maxrss_bytes,
            "children_maxrss_bytes": children_maxrss_bytes,
            "psutil_available": False,
        }

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
        cpu_percent = 0.0
        process_count = 0
        for idx, child in enumerate(processes):
            try:
                memory = child.memory_info()
                rss_bytes += int(memory.rss)
                if idx > 0:
                    children_rss_bytes += int(memory.rss)
                cpu_percent += float(child.cpu_percent(interval=None))
                process_count += 1
            except psutil.Error:
                continue

        self._peak_psutil_rss_bytes = max(self._peak_psutil_rss_bytes, rss_bytes)
        self._peak_psutil_children_rss_bytes = max(self._peak_psutil_children_rss_bytes, children_rss_bytes)
        sample.update(
            {
                "psutil_available": True,
                "process_tree_rss_bytes": rss_bytes,
                "children_rss_bytes": children_rss_bytes,
                "process_count": process_count,
                "process_tree_cpu_percent": cpu_percent,
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
                sample = {
                    "timestamp_monotonic_sec": time.perf_counter(),
                    "process": self._sample_process_tree(),
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
            "schema_version": "tools.issue120.stage_e_resource_summary.v1",
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

    pipeline_console_log_size = pipeline_console_log.stat().st_size if pipeline_console_log.exists() else 0
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
            "stdout_stderr_log": str(pipeline_console_log),
            "stdout_stderr_log_size_bytes": pipeline_console_log_size,
        },
        "resource_monitor": resource_summary,
    }
    run_summary_path.write_text(json.dumps(run_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Stage E runtime summary written to %s", run_summary_path)
    logger.info("Stage E full pipeline run completed.")


if __name__ == "__main__":
    main()
