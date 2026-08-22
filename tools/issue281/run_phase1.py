"""Collect Issue #281 Phase-1 dense latency attribution measurements.

The command runs fresh one-page and three-page workloads, plus one-page
tracing ON/OFF controls. It must run inside the canonical pipeline container.
All generated files are placed below logs/issue281.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMAGE_ROOT = ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va"
PIPELINE_PYTHON = Path("/opt/venv_pipeline/bin/python")


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str) -> str | None:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def command_identity(command: list[str]) -> str | None:
    try:
        return subprocess.check_output(
            command, cwd=ROOT, text=True, stderr=subprocess.STDOUT
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _require_canonical_container() -> None:
    """Refuse the profiling run when the main pipeline would execute on the host."""
    if not Path("/.dockerenv").exists():
        raise RuntimeError(
            "Issue #281 Phase-1 profiling must run inside pdfscore_pipeline_gpu; "
            "invoke this runner with docker run/exec."
        )
    if not PIPELINE_PYTHON.is_file():
        raise RuntimeError(f"Canonical pipeline interpreter is missing: {PIPELINE_PYTHON}")
    if ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError(f"Expected repository mount at /workspace, got {ROOT}")
    if not Path(sys.executable).as_posix().startswith("/opt/venv_pipeline/"):
        raise RuntimeError(
            "Issue #281 runner must use /opt/venv_pipeline/bin/python inside the container; "
            f"got {sys.executable}"
        )


class ResourceSampler:
    """Best-effort process-tree CPU/RSS and GPU sampler rooted at the pipeline PID."""

    def __init__(self, pid: int, output: Path, interval: float = 1.0):
        if interval <= 0:
            raise ValueError("Resource sample interval must be positive")
        self.pid = pid
        self.output = output
        self.interval = interval
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.sample_count = 0
        self.psutil_available: bool | None = None
        self.nvidia_smi_seen = False
        self.peak_process_tree_rss_bytes = 0
        self.peak_children_rss_bytes = 0
        self.peak_process_tree_cpu_percent = 0.0
        self.peak_gpu_memory_mb_by_uuid: dict[str, int] = {}
        self.peak_gpu_utilization_pct_by_uuid: dict[str, int] = {}
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.previous_process_sample_time: float | None = None
        self.previous_process_cpu_sec: float | None = None

    def start(self) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.started_at = time.perf_counter()
        self.thread.start()

    def join(self) -> dict[str, Any]:
        self.stop.set()
        self.thread.join(timeout=max(self.interval * 2, 1.0))
        self.finished_at = time.perf_counter()
        summary = self.summary()
        summary_path = self.output.with_suffix(".summary.json")
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        summary["summary_path"] = str(summary_path)
        return summary

    def _process_tree(self, sample_time: float) -> dict[str, Any]:
        sample: dict[str, Any] = {
            "root_pid": self.pid,
            "psutil_available": False,
            "root_alive": False,
        }
        try:
            import psutil  # type: ignore[import-not-found]
        except Exception:
            self.psutil_available = False
            return sample

        self.psutil_available = True
        try:
            root = psutil.Process(self.pid)
            processes = [root]
            try:
                processes.extend(root.children(recursive=True))
            except psutil.Error:
                pass
        except psutil.Error:
            sample["psutil_available"] = True
            return sample

        rss_bytes = 0
        children_rss_bytes = 0
        process_tree_cpu_times_sec = 0.0
        process_count = 0
        process_ids: list[int] = []
        for index, process in enumerate(processes):
            try:
                memory = process.memory_info()
                cpu_times = process.cpu_times()
                rss_bytes += int(memory.rss)
                if index > 0:
                    children_rss_bytes += int(memory.rss)
                process_tree_cpu_times_sec += float(cpu_times.user) + float(cpu_times.system)
                process_count += 1
                process_ids.append(int(process.pid))
            except psutil.Error:
                continue

        cpu_percent = None
        if (
            self.previous_process_sample_time is not None
            and self.previous_process_cpu_sec is not None
        ):
            elapsed = max(sample_time - self.previous_process_sample_time, 1e-9)
            cpu_delta = max(process_tree_cpu_times_sec - self.previous_process_cpu_sec, 0.0)
            cpu_percent = (cpu_delta / elapsed) * 100.0
            self.peak_process_tree_cpu_percent = max(
                self.peak_process_tree_cpu_percent, cpu_percent
            )
        self.previous_process_sample_time = sample_time
        self.previous_process_cpu_sec = process_tree_cpu_times_sec
        self.peak_process_tree_rss_bytes = max(self.peak_process_tree_rss_bytes, rss_bytes)
        self.peak_children_rss_bytes = max(self.peak_children_rss_bytes, children_rss_bytes)

        sample.update(
            {
                "psutil_available": True,
                "root_alive": True,
                "process_tree_rss_bytes": rss_bytes,
                "children_rss_bytes": children_rss_bytes,
                "process_count": process_count,
                "process_ids": process_ids,
                "process_tree_cpu_times_sec": process_tree_cpu_times_sec,
                "process_tree_cpu_percent_since_previous_sample": cpu_percent,
            }
        )
        return sample

    @staticmethod
    def _gpu() -> list[dict[str, Any]]:
        try:
            out = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=uuid,index,name,memory.used,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return []
        rows: list[dict[str, Any]] = []
        for line in out.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) != 5:
                continue
            uuid, index, name, memory_used_mb, utilization_gpu_pct = parts
            try:
                rows.append(
                    {
                        "uuid": uuid,
                        "index": int(index),
                        "name": name,
                        "memory_used_mb": int(memory_used_mb),
                        "utilization_gpu_pct": int(utilization_gpu_pct),
                    }
                )
            except ValueError:
                continue
        return rows

    def _record_gpu_peaks(self, samples: list[dict[str, Any]]) -> None:
        if samples:
            self.nvidia_smi_seen = True
        for sample in samples:
            uuid = str(sample["uuid"])
            self.peak_gpu_memory_mb_by_uuid[uuid] = max(
                self.peak_gpu_memory_mb_by_uuid.get(uuid, 0),
                int(sample["memory_used_mb"]),
            )
            self.peak_gpu_utilization_pct_by_uuid[uuid] = max(
                self.peak_gpu_utilization_pct_by_uuid.get(uuid, 0),
                int(sample["utilization_gpu_pct"]),
            )

    def _run(self) -> None:
        with self.output.open("w", encoding="utf-8") as stream:
            while not self.stop.is_set():
                sample_time = time.perf_counter()
                gpu = self._gpu()
                self._record_gpu_peaks(gpu)
                sample = {
                    "timestamp_monotonic_sec": sample_time,
                    "process": self._process_tree(sample_time),
                    "gpu": gpu,
                }
                stream.write(json.dumps(sample, ensure_ascii=False) + "\n")
                stream.flush()
                self.sample_count += 1
                self.stop.wait(self.interval)

    def summary(self) -> dict[str, Any]:
        duration_sec = None
        if self.started_at is not None:
            end = self.finished_at if self.finished_at is not None else time.perf_counter()
            duration_sec = end - self.started_at
        return {
            "schema_version": "issue281.phase1.resource_summary.v1",
            "root_pid": self.pid,
            "samples_path": str(self.output),
            "sample_count": self.sample_count,
            "sample_interval_sec": self.interval,
            "duration_sec": duration_sec,
            "psutil_available": self.psutil_available,
            "nvidia_smi_seen": self.nvidia_smi_seen,
            "peak_process_tree_rss_bytes": self.peak_process_tree_rss_bytes,
            "peak_process_tree_children_rss_bytes": self.peak_children_rss_bytes,
            "peak_process_tree_cpu_percent": self.peak_process_tree_cpu_percent,
            "peak_gpu_memory_mb_by_uuid": self.peak_gpu_memory_mb_by_uuid,
            "peak_gpu_utilization_pct_by_uuid": self.peak_gpu_utilization_pct_by_uuid,
        }


def _stage_inputs(run_root: Path, names: list[str]) -> Path:
    staged = run_root / "input_staging"
    staged.mkdir(parents=True, exist_ok=True)
    for stale in staged.iterdir():
        if stale.is_symlink() or stale.is_file():
            stale.unlink()
    for name in names:
        source = DEFAULT_IMAGE_ROOT / name
        if not source.is_file():
            raise FileNotFoundError(source)
        (staged / name).symlink_to(source)
    return staged


def _run_workload(root: Path, name: str, images: list[str], *, tracing: bool) -> dict[str, Any]:
    run_root = root / name
    run_root.mkdir(parents=True, exist_ok=True)
    input_root = _stage_inputs(run_root, images)
    trace_dir = run_root / "traces" if tracing else None
    env = os.environ.copy()
    env["PDFSCORE_PERF_TRACE_RUN"] = name
    env["PDFSCORE_PERF_TRACE_ROLE"] = "pipeline_main"
    if tracing:
        env["PDFSCORE_PERF_TRACE_DIR"] = str(trace_dir)
    else:
        env.pop("PDFSCORE_PERF_TRACE_DIR", None)
    command = [
        str(PIPELINE_PYTHON),
        "-m",
        "src.pipeline.main",
        "--config",
        str(ROOT / "configs/dense_full_pipeline.yaml"),
        "--run-id",
        name,
        "--output-root",
        str(run_root / "pipeline_output"),
        "--page-limit",
        str(len(images)),
    ]
    # collect_images sees the canonical config's output_dir; use a temporary
    # mechanically derived config without modifying the canonical file.
    import yaml

    config = yaml.safe_load((ROOT / "configs/dense_full_pipeline.yaml").read_text())
    config["inputs"]["pdf_to_images"]["output_dir"] = str(input_root)
    config["detection"]["hybrid_output_root"] = str(run_root / "hybrid_output")
    config_path = run_root / "config_derived.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    command[command.index(str(ROOT / "configs/dense_full_pipeline.yaml"))] = str(config_path)

    started = time.perf_counter()
    completed = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    sampler = ResourceSampler(completed.pid, run_root / "resource_samples.jsonl")
    sampler.start()
    stdout, _ = completed.communicate()
    resource_summary = sampler.join()
    (run_root / "pipeline.stdout.log").write_text(stdout[-200_000:], encoding="utf-8")
    result = {
        "name": name,
        "images": images,
        "tracing": tracing,
        "command": command,
        "returncode": completed.returncode,
        "e2e_wall_sec": time.perf_counter() - started,
        "config": str(config_path),
        "trace_dir": str(trace_dir) if trace_dir else None,
        "resource_summary": resource_summary,
    }
    (run_root / "run_summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    if completed.returncode:
        raise subprocess.CalledProcessError(completed.returncode, command)
    return result


def _aggregate(root: Path, workload_results: list[dict[str, Any]]) -> None:
    records: list[dict[str, Any]] = []
    for result in workload_results:
        trace_dir = result.get("trace_dir")
        if trace_dir:
            for path in Path(trace_dir).glob("trace-*.jsonl"):
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line:
                        records.append(json.loads(line))
    (root / "stage_timings.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8"
    )
    with (root / "stage_timings.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = [
            "run_id",
            "page",
            "process_role",
            "pid",
            "ppid",
            "stage",
            "duration_sec",
            "cpu_time_sec",
            "cuda_synchronized",
            "success",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    page_rows = [
        {
            "run": item["name"],
            "pages": len(item["images"]),
            "e2e_wall_sec": item["e2e_wall_sec"],
            "returncode": item["returncode"],
        }
        for item in workload_results
    ]
    with (root / "page_summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=page_rows[0].keys())
        writer.writeheader()
        writer.writerows(page_rows)

    resource_summary = {
        "schema_version": "issue281.phase1.resource_summary_bundle.v1",
        "workloads": {item["name"]: item["resource_summary"] for item in workload_results},
    }
    (root / "resource_summary.json").write_text(
        json.dumps(resource_summary, indent=2) + "\n", encoding="utf-8"
    )

    one_page = {
        item["name"]: item["e2e_wall_sec"]
        for item in workload_results
        if item["name"].startswith("one_page_")
    }
    trace_on = one_page.get("one_page_trace_on")
    trace_off = one_page.get("one_page_trace_off")
    overhead: dict[str, Any] = {"workloads": one_page}
    if trace_on is not None and trace_off is not None:
        overhead["trace_on_minus_off_sec"] = trace_on - trace_off
        overhead["trace_on_overhead_fraction"] = (
            (trace_on - trace_off) / trace_off if trace_off > 0 else None
        )
    (root / "instrumentation_overhead.json").write_text(
        json.dumps(overhead, indent=2) + "\n", encoding="utf-8"
    )

    startup_rows = [
        {
            "run": row.get("run_id"),
            "page": row.get("page"),
            "stage": row["stage"],
            "pid": row["pid"],
            "duration_sec": row["duration_sec"],
        }
        for row in records
        if row["stage"].endswith("parent_wall") or row["stage"].endswith("internal_total")
    ]
    with (root / "process_startup.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["run", "page", "stage", "pid", "duration_sec"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(startup_rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "logs/issue281/phase1")
    args = parser.parse_args()
    _require_canonical_container()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    one = ["page_013.png"]
    three = ["page_012.png", "page_013.png", "page_014.png"]
    results = [
        _run_workload(root, "one_page_trace_on", one, tracing=True),
        _run_workload(root, "one_page_trace_off", one, tracing=False),
        _run_workload(root, "three_page_trace_on", three, tracing=True),
    ]

    docker_image = os.environ.get("PDFSCORE_ISSUE281_DOCKER_IMAGE", "pdfscore_pipeline_gpu")
    docker_image_identity = os.environ.get("PDFSCORE_ISSUE281_DOCKER_IMAGE_IDENTITY")
    if docker_image_identity is None:
        docker_image_identity = command_identity(
            ["docker", "image", "inspect", "--format", "{{.Id}}", docker_image]
        )
    provenance = {
        "schema_version": "issue281.phase1.provenance.v1",
        "commit": git("rev-parse", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
        "runtime_python": sys.executable,
        "config_sha256": sha256(ROOT / "configs/dense_full_pipeline.yaml"),
        "inputs": {name: sha256(DEFAULT_IMAGE_ROOT / name) for name in dict.fromkeys(one + three)},
        "cnn_checkpoint_sha256": sha256(
            ROOT
            / "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1"
            / "cnn_classifier_best.pth"
        ),
        "mmr_checkpoint_sha256": sha256(
            ROOT / "tools/mmr_training/models/mmr_classifier_best.pth"
        ),
        "homr_profile": {
            "path": str(ROOT / "configs/detector_profiles/stage_e_verified_homr.json"),
            "sha256": sha256(ROOT / "configs/detector_profiles/stage_e_verified_homr.json"),
        },
        "docker_image": docker_image,
        "docker_image_identity": docker_image_identity,
        "gpu_driver_identity": command_identity(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"]
        ),
        "gpu_identity": command_identity(
            ["nvidia-smi", "--query-gpu=name,uuid", "--format=csv,noheader"]
        ),
        "workloads": results,
    }
    (root / "provenance.json").write_text(
        json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8"
    )
    _aggregate(root, results)
    (root / "compact_summary.json").write_text(
        json.dumps(
            {"workloads": results, "result_root": str(root)}, indent=2, default=str
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
