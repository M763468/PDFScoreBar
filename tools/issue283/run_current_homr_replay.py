"""Replay only current-runtime HOMR on a retained x4 SR image for Issue #283."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from tools.issue281.run_phase1 import ResourceSampler

ROOT = Path(__file__).resolve().parents[2]
PIPELINE_PYTHON = Path("/opt/venv_pipeline/bin/python")
DEFAULT_CONFIG = ROOT / "configs/dense_full_pipeline.yaml"


def _require_canonical_container() -> None:
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Issue #283 replay must run inside pdfscore_pipeline_gpu")
    if ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError(f"Expected repository mount at /workspace, got {ROOT}")
    if not PIPELINE_PYTHON.is_file():
        raise RuntimeError(f"Missing canonical interpreter: {PIPELINE_PYTHON}")
    if not Path(sys.executable).as_posix().startswith("/opt/venv_pipeline/"):
        raise RuntimeError(f"Runner must use /opt/venv_pipeline/bin/python, got {sys.executable}")


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _read_trace_records(trace_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(trace_dir.glob("trace-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                records.append(json.loads(line))
    return records


def _summarize(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record["stage"])].append(record)

    result: dict[str, dict[str, Any]] = {}
    for stage, rows in sorted(grouped.items()):
        durations = [float(row["duration_sec"]) for row in rows]
        cpu_times = [float(row.get("cpu_time_sec", 0.0)) for row in rows]
        result[stage] = {
            "count": len(rows),
            "total_duration_sec": sum(durations),
            "mean_duration_sec": sum(durations) / len(durations),
            "max_duration_sec": max(durations),
            "total_cpu_time_sec": sum(cpu_times),
            "cuda_synchronized": any(bool(row.get("cuda_synchronized")) for row in rows),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--sr-image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--run-id", default="issue283_current_homr_replay")
    args = parser.parse_args()

    _require_canonical_container()
    image = args.image.resolve()
    sr_image = args.sr_image.resolve()
    config_path = args.config.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not image.is_file():
        raise FileNotFoundError(image)
    if not sr_image.is_file():
        raise FileNotFoundError(sr_image)
    if not config_path.is_file():
        raise FileNotFoundError(config_path)

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    detection = config.get("detection")
    if not isinstance(detection, dict):
        raise ValueError(f"Config lacks detection mapping: {config_path}")

    request_path = output / "request.json"
    result_path = output / "result.json"
    worker_output = output / "current_homr_output"
    trace_dir = output / "traces"
    request = {
        "schema_version": "pipeline.current_homr_on_x4_request.v1",
        "detection": detection,
        "image": str(image),
        "sr_image": str(sr_image),
        "output_root": str(worker_output),
    }
    request_path.write_text(json.dumps(request, indent=2, default=str) + "\n", encoding="utf-8")

    env = os.environ.copy()
    env["PDFSCORE_PERF_TRACE_DIR"] = str(trace_dir)
    env["PDFSCORE_PERF_TRACE_RUN"] = args.run_id
    env["PDFSCORE_PERF_TRACE_ROLE"] = "current_homr_worker"
    command = [
        str(PIPELINE_PYTHON),
        "-m",
        "src.pipeline.detection.current_homr_worker",
        "--request",
        str(request_path),
        "--result",
        str(result_path),
    ]

    started = time.perf_counter()
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    sampler = ResourceSampler(process.pid, output / "resource_samples.jsonl")
    sampler.start()
    stdout, _ = process.communicate()
    resource_summary = sampler.join()
    elapsed = time.perf_counter() - started
    (output / "worker.stdout.log").write_text(stdout[-200_000:], encoding="utf-8")
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, command, output=stdout)

    records = _read_trace_records(trace_dir)
    (output / "stage_timings.json").write_text(
        json.dumps(records, indent=2, default=str) + "\n", encoding="utf-8"
    )
    stage_summary = _summarize(records)
    (output / "stage_summary.json").write_text(
        json.dumps(stage_summary, indent=2) + "\n", encoding="utf-8"
    )

    worker_result = json.loads(result_path.read_text(encoding="utf-8"))
    artifact_hashes: dict[str, str | None] = {}
    for key in (
        "current_sr_detection",
        "staff_mask",
        "connector_symbols",
        "connector_brace_dot",
    ):
        raw = worker_result.get(key)
        artifact_hashes[key] = _sha256(Path(raw)) if raw else None

    commit = os.environ.get("PDFSCORE_ISSUE283_GIT_COMMIT") or _git("rev-parse", "HEAD")
    dirty_env = os.environ.get("PDFSCORE_ISSUE283_GIT_DIRTY")
    dirty = None if dirty_env is None else dirty_env.strip().lower() in {"1", "true", "yes", "on"}
    provenance = {
        "schema_version": "issue283.current_homr_replay.provenance.v1",
        "commit": commit,
        "dirty": dirty,
        "runtime_python": sys.executable,
        "config": str(config_path),
        "config_sha256": _sha256(config_path),
        "image": str(image),
        "image_sha256": _sha256(image),
        "sr_image": str(sr_image),
        "sr_image_sha256": _sha256(sr_image),
        "docker_image": os.environ.get("PDFSCORE_ISSUE281_DOCKER_IMAGE", "pdfscore_pipeline_gpu"),
        "docker_image_identity": os.environ.get("PDFSCORE_ISSUE281_DOCKER_IMAGE_IDENTITY"),
        "artifact_hashes": artifact_hashes,
    }
    (output / "provenance.json").write_text(
        json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8"
    )

    compact = {
        "schema_version": "issue283.current_homr_replay.summary.v1",
        "run_id": args.run_id,
        "returncode": process.returncode,
        "worker_wall_sec": elapsed,
        "resource_summary": resource_summary,
        "stage_summary": stage_summary,
        "provenance": provenance,
    }
    (output / "compact_summary.json").write_text(
        json.dumps(compact, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(compact, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
