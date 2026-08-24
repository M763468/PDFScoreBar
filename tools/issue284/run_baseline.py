"""Refresh the post-#285 Real-ESRGAN baseline for Issue #284.

Run inside the canonical pdfscore_pipeline_gpu container. The runner executes
one representative page with tracing disabled and the three-page representative
slice with opt-in synchronization-correct tracing enabled. Results are written
only below the caller-supplied output directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
PIPELINE_PYTHON = Path("/opt/venv_pipeline/bin/python")
IMAGE_ROOT = ROOT / "data/evaluation2/images/Shostakovich-Sym5-Va"
CANONICAL_CONFIG = ROOT / "configs/dense_full_pipeline.yaml"
TRACE_STAGES = (
    "current_support.current_sr_subprocess",
    "sr_worker.image_read_preprocess",
    "sr_worker.realesrgan_total",
    "sr_worker.realesrgan_heavy_imports",
    "sr_worker.realesrgan_model_initialization",
    "sr_worker.synchronized_enhance",
    "sr_worker.image_write",
    "sr_worker.sha256",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_canonical_container() -> None:
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Issue #284 baseline must run inside pdfscore_pipeline_gpu")
    if ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError(f"Expected repository at /workspace, got {ROOT}")
    if not PIPELINE_PYTHON.is_file():
        raise RuntimeError(f"Missing canonical interpreter: {PIPELINE_PYTHON}")
    if not Path(sys.executable).as_posix().startswith("/opt/venv_pipeline/"):
        raise RuntimeError(f"Runner must use /opt/venv_pipeline/bin/python, got {sys.executable}")


class ResourceSampler:
    """Best-effort process-tree RSS/CPU plus nvidia-smi GPU sampling."""

    def __init__(self, pid: int, output: Path, interval: float = 1.0) -> None:
        self.pid = pid
        self.output = output
        self.interval = interval
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.peak_process_tree_rss_bytes = 0
        self.peak_children_rss_bytes = 0
        self.peak_gpu_memory_mb_by_uuid: dict[str, int] = {}
        self.peak_gpu_utilization_pct_by_uuid: dict[str, int] = {}
        self.sample_count = 0

    @staticmethod
    def _gpu() -> list[dict[str, Any]]:
        try:
            output = subprocess.check_output(
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
        for line in output.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) != 5:
                continue
            uuid, index, name, memory_used, utilization = parts
            try:
                rows.append(
                    {
                        "uuid": uuid,
                        "index": int(index),
                        "name": name,
                        "memory_used_mb": int(memory_used),
                        "utilization_gpu_pct": int(utilization),
                    }
                )
            except ValueError:
                continue
        return rows

    def _process(self) -> dict[str, Any]:
        try:
            import psutil  # type: ignore[import-not-found]
        except Exception:
            return {"psutil_available": False}
        try:
            root = psutil.Process(self.pid)
            children = root.children(recursive=True)
        except psutil.Error:
            return {"psutil_available": True, "root_alive": False}
        rss = 0
        child_rss = 0
        pids: list[int] = []
        for index, process in enumerate([root, *children]):
            try:
                value = int(process.memory_info().rss)
            except psutil.Error:
                continue
            rss += value
            if index:
                child_rss += value
            pids.append(int(process.pid))
        self.peak_process_tree_rss_bytes = max(self.peak_process_tree_rss_bytes, rss)
        self.peak_children_rss_bytes = max(self.peak_children_rss_bytes, child_rss)
        return {
            "psutil_available": True,
            "root_alive": True,
            "process_tree_rss_bytes": rss,
            "children_rss_bytes": child_rss,
            "process_count": len(pids),
            "process_ids": pids,
        }

    def _run(self) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        with self.output.open("w", encoding="utf-8") as stream:
            while not self.stop.is_set():
                gpu = self._gpu()
                for row in gpu:
                    uuid = str(row["uuid"])
                    self.peak_gpu_memory_mb_by_uuid[uuid] = max(
                        self.peak_gpu_memory_mb_by_uuid.get(uuid, 0), int(row["memory_used_mb"])
                    )
                    self.peak_gpu_utilization_pct_by_uuid[uuid] = max(
                        self.peak_gpu_utilization_pct_by_uuid.get(uuid, 0),
                        int(row["utilization_gpu_pct"]),
                    )
                stream.write(
                    json.dumps(
                        {
                            "timestamp_monotonic_sec": time.perf_counter(),
                            "process": self._process(),
                            "gpu": gpu,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                stream.flush()
                self.sample_count += 1
                self.stop.wait(self.interval)

    def start(self) -> None:
        self.thread.start()

    def finish(self) -> dict[str, Any]:
        self.stop.set()
        self.thread.join(timeout=max(2.0, self.interval * 2))
        return {
            "sample_count": self.sample_count,
            "sample_interval_sec": self.interval,
            "samples_path": str(self.output),
            "peak_process_tree_rss_bytes": self.peak_process_tree_rss_bytes,
            "peak_children_rss_bytes": self.peak_children_rss_bytes,
            "peak_gpu_memory_mb_by_uuid": self.peak_gpu_memory_mb_by_uuid,
            "peak_gpu_utilization_pct_by_uuid": self.peak_gpu_utilization_pct_by_uuid,
        }


def stage_inputs(run_root: Path, image_names: list[str]) -> Path:
    staged = run_root / "input_staging"
    staged.mkdir(parents=True, exist_ok=True)
    for path in staged.iterdir():
        if path.is_symlink() or path.is_file():
            path.unlink()
    for name in image_names:
        source = IMAGE_ROOT / name
        if not source.is_file():
            raise FileNotFoundError(source)
        (staged / name).symlink_to(source)
    return staged


def derived_config(run_root: Path, staged: Path) -> Path:
    config = yaml.safe_load(CANONICAL_CONFIG.read_text(encoding="utf-8"))
    config["inputs"]["pdf_to_images"]["output_dir"] = str(staged)
    config["detection"]["hybrid_output_root"] = str(run_root / "hybrid_output")
    path = run_root / "config_derived.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def run_workload(root: Path, name: str, images: list[str], *, tracing: bool) -> dict[str, Any]:
    run_root = root / name
    run_root.mkdir(parents=True, exist_ok=True)
    staged = stage_inputs(run_root, images)
    config_path = derived_config(run_root, staged)
    trace_dir = run_root / "traces"
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
        str(config_path),
        "--run-id",
        name,
        "--output-root",
        str(run_root / "pipeline_output"),
        "--page-limit",
        str(len(images)),
    ]
    log_path = run_root / "pipeline.stdout.log"
    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        sampler = ResourceSampler(process.pid, run_root / "resource_samples.jsonl")
        sampler.start()
        returncode = process.wait()
        resources = sampler.finish()
    result = {
        "name": name,
        "images": images,
        "tracing": tracing,
        "returncode": returncode,
        "e2e_wall_sec": time.perf_counter() - started,
        "command": command,
        "config": str(config_path),
        "trace_dir": str(trace_dir) if tracing else None,
        "log": str(log_path),
        "resources": resources,
    }
    (run_root / "run_summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    if returncode:
        tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
        raise RuntimeError(f"{name} failed ({returncode})\n" + "\n".join(tail))
    return result


def read_trace_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in root.glob("**/traces/trace-*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                records.append(json.loads(line))
    return records


def summarize_stages(records: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        stage = str(record.get("stage"))
        if stage in TRACE_STAGES:
            grouped[stage].append(record)
    summary: dict[str, Any] = {}
    for stage in TRACE_STAGES:
        items = grouped.get(stage, [])
        durations = [float(item["duration_sec"]) for item in items]
        summary[stage] = {
            "count": len(items),
            "total_sec": sum(durations),
            "mean_sec": sum(durations) / len(durations) if durations else None,
            "pages": [item.get("page") for item in items],
            "cuda_synchronized_all": bool(items)
            and all(bool(item.get("cuda_synchronized")) for item in items),
        }
    return summary


def collect_sr_outputs(root: Path) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for path in root.glob("**/current_sr_result.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("status") != "completed":
            continue
        outputs.append(
            {
                "result": str(path),
                "image": payload.get("image"),
                "sr_image": payload.get("sr_image"),
                "sr_sha256": payload.get("sr_sha256"),
            }
        )
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_canonical_container()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    workloads = [
        run_workload(output, "one_page_trace_off", ["page_013.png"], tracing=False),
        run_workload(
            output,
            "three_page_trace_on",
            ["page_012.png", "page_013.png", "page_014.png"],
            tracing=True,
        ),
    ]
    records = read_trace_records(output)
    stages = summarize_stages(records)
    three_page = next(item for item in workloads if item["name"] == "three_page_trace_on")
    enhance_total = stages["sr_worker.synchronized_enhance"]["total_sec"]
    sr_subprocess_total = stages["current_support.current_sr_subprocess"]["total_sec"]

    summary = {
        "schema_version": "issue284.post285_baseline.v1",
        "provenance": {
            "git_commit": os.environ.get("PDFSCORE_ISSUE284_GIT_COMMIT"),
            "git_dirty": os.environ.get("PDFSCORE_ISSUE284_GIT_DIRTY"),
            "docker_image": os.environ.get(
                "PDFSCORE_ISSUE284_DOCKER_IMAGE", "pdfscore_pipeline_gpu"
            ),
            "docker_image_identity": os.environ.get("PDFSCORE_ISSUE284_DOCKER_IMAGE_IDENTITY"),
            "config_sha256": sha256(CANONICAL_CONFIG),
            "input_sha256": {
                name: sha256(IMAGE_ROOT / name)
                for name in ("page_012.png", "page_013.png", "page_014.png")
            },
            "python": sys.executable,
        },
        "workloads": workloads,
        "three_page_trace_on_e2e_wall_sec": three_page["e2e_wall_sec"],
        "stage_summary": stages,
        "current_enhance_mean_sec_per_page": stages["sr_worker.synchronized_enhance"]["mean_sec"],
        "current_enhance_e2e_share": enhance_total / float(three_page["e2e_wall_sec"]),
        "current_sr_subprocess_mean_sec_per_page": stages["current_support.current_sr_subprocess"][
            "mean_sec"
        ],
        "current_sr_subprocess_e2e_share": sr_subprocess_total / float(three_page["e2e_wall_sec"]),
        "sr_outputs": collect_sr_outputs(output),
    }
    (output / "trace_records.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8"
    )
    summary_path = output / "baseline_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
