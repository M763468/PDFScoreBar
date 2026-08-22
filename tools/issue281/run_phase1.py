"""Collect Issue #281 Phase-1 dense latency attribution measurements.

The command runs fresh one-page and three-page workloads, plus one-page
tracing ON/OFF controls. All generated files are placed below logs/issue281.
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


class ResourceSampler:
    def __init__(self, pid: int, output: Path, interval: float = 1.0):
        self.pid, self.output, self.interval = pid, output, interval
        self.samples: list[dict[str, Any]] = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def join(self) -> None:
        self.stop.set()
        self.thread.join(timeout=3)
        self.output.write_text(json.dumps(self.samples, indent=2) + "\n", encoding="utf-8")

    def _run(self) -> None:
        while not self.stop.is_set():
            self.samples.append({"timestamp": time.time(), "gpu": self._gpu(), "pid": self.pid})
            self.stop.wait(self.interval)

    @staticmethod
    def _gpu() -> list[dict[str, str]]:
        try:
            out = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=uuid,index,memory.used,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return []
        rows = []
        for line in out.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) == 4:
                rows.append(
                    dict(zip(("uuid", "index", "memory_used_mb", "utilization_gpu_pct"), parts))
                )
        return rows


def _stage_inputs(root: Path, names: list[str]) -> Path:
    staged = root / "input_staging"
    staged.mkdir(parents=True, exist_ok=True)
    for name in names:
        source = DEFAULT_IMAGE_ROOT / name
        if not source.is_file():
            raise FileNotFoundError(source)
        link = staged / name
        if not link.exists():
            link.symlink_to(source)
    return staged


def _run_workload(root: Path, name: str, images: list[str], *, tracing: bool) -> dict[str, Any]:
    run_root = root / name
    run_root.mkdir(parents=True, exist_ok=True)
    input_root = _stage_inputs(root, images)
    trace_dir = run_root / "traces" if tracing else None
    env = os.environ.copy()
    env["PDFSCORE_PERF_TRACE_RUN"] = name
    env["PDFSCORE_PERF_TRACE_ROLE"] = "pipeline_main"
    if tracing:
        env["PDFSCORE_PERF_TRACE_DIR"] = str(trace_dir)
    else:
        env.pop("PDFSCORE_PERF_TRACE_DIR", None)
    command = [
        sys.executable,
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
        command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    sampler = ResourceSampler(completed.pid, run_root / "resource_samples.json")
    sampler.start()
    stdout, _ = completed.communicate()
    sampler.join()
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
    (root / "stage_timings.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
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
    (root / "resource_summary.json").write_text(
        json.dumps(
            {
                "workloads": [
                    str(Path(x["name"]) / "resource_samples.json") for x in workload_results
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    overhead = {
        x["name"]: x["e2e_wall_sec"] for x in workload_results if x["name"].startswith("one_page_")
    }
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
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    one = ["page_013.png"]
    three = ["page_012.png", "page_013.png", "page_014.png"]
    results = [
        _run_workload(root, "one_page_trace_on", one, tracing=True),
        _run_workload(root, "one_page_trace_off", one, tracing=False),
        _run_workload(root, "three_page_trace_on", three, tracing=True),
    ]
    provenance = {
        "schema_version": "issue281.phase1.provenance.v1",
        "commit": git("rev-parse", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
        "config_sha256": sha256(ROOT / "configs/dense_full_pipeline.yaml"),
        "inputs": {name: sha256(DEFAULT_IMAGE_ROOT / name) for name in one + three},
        "cnn_checkpoint_sha256": sha256(
            ROOT
            / "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
        ),
        "mmr_checkpoint_sha256": sha256(ROOT / "tools/mmr_training/models/mmr_classifier_best.pth"),
        "homr_profile": {
            "path": str(ROOT / "configs/detector_profiles/stage_e_verified_homr.json"),
            "sha256": sha256(ROOT / "configs/detector_profiles/stage_e_verified_homr.json"),
        },
        "docker_image": os.environ.get("PDFSCORE_ISSUE281_DOCKER_IMAGE", "pdfscore_pipeline_gpu"),
        "docker_image_identity": command_identity(
            [
                "docker",
                "image",
                "inspect",
                "--format",
                "{{.Id}}",
                os.environ.get("PDFSCORE_ISSUE281_DOCKER_IMAGE", "pdfscore_pipeline_gpu"),
            ]
        ),
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
        json.dumps({"workloads": results, "result_root": str(root)}, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
