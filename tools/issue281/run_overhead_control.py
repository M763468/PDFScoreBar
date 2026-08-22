"""Run a warm, counterbalanced Issue #281 tracing-overhead control.

This is intentionally separate from ``run_phase1.py``. The original Phase-1
sequence starts with tracing enabled, so its first ON/OFF delta is confounded by
cold model/cache initialization. This control first performs an unmeasured warmup
and then compares OFF -> ON -> OFF on the same page in the same container.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from statistics import mean
from typing import Any

from tools.issue281.run_phase1 import (
    DEFAULT_IMAGE_ROOT,
    ROOT,
    _aggregate,
    _require_canonical_container,
    _run_workload,
    command_identity,
    git,
    sha256,
)


def _env_bool(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "logs/issue281/overhead_control",
    )
    args = parser.parse_args()

    _require_canonical_container()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    one = ["page_013.png"]

    # Keep the warmup in the same container/process environment but exclude it
    # from the overhead estimate. Each pipeline invocation remains a fresh
    # production run, preserving the normal process/model lifetime contract.
    results = [
        _run_workload(root, "warmup_trace_off", one, tracing=False),
        _run_workload(root, "control_trace_off_a", one, tracing=False),
        _run_workload(root, "control_trace_on", one, tracing=True),
        _run_workload(root, "control_trace_off_b", one, tracing=False),
    ]
    _aggregate(root, results)

    by_name = {item["name"]: item for item in results}
    off_values = [
        float(by_name["control_trace_off_a"]["e2e_wall_sec"]),
        float(by_name["control_trace_off_b"]["e2e_wall_sec"]),
    ]
    trace_on = float(by_name["control_trace_on"]["e2e_wall_sec"])
    off_mean = mean(off_values)
    overhead: dict[str, Any] = {
        "schema_version": "issue281.phase1.instrumentation_overhead_control.v1",
        "method": "warmup_then_off_on_off_same_page_same_container",
        "image": one[0],
        "warmup_e2e_wall_sec": float(by_name["warmup_trace_off"]["e2e_wall_sec"]),
        "trace_off_a_e2e_wall_sec": off_values[0],
        "trace_on_e2e_wall_sec": trace_on,
        "trace_off_b_e2e_wall_sec": off_values[1],
        "trace_off_mean_e2e_wall_sec": off_mean,
        "trace_on_minus_off_mean_sec": trace_on - off_mean,
        "trace_on_overhead_fraction": (trace_on - off_mean) / off_mean if off_mean > 0 else None,
    }
    (root / "instrumentation_overhead.json").write_text(
        json.dumps(overhead, indent=2) + "\n", encoding="utf-8"
    )

    docker_image = os.environ.get("PDFSCORE_ISSUE281_DOCKER_IMAGE", "pdfscore_pipeline_gpu")
    commit = os.environ.get("PDFSCORE_ISSUE281_GIT_COMMIT") or git("rev-parse", "HEAD")
    if not commit:
        raise RuntimeError(
            "Exact Git commit is required; pass PDFSCORE_ISSUE281_GIT_COMMIT from the host."
        )
    provenance = {
        "schema_version": "issue281.phase1.overhead_control_provenance.v1",
        "commit": commit,
        "dirty": _env_bool("PDFSCORE_ISSUE281_GIT_DIRTY"),
        "runtime_python": sys.executable,
        "config_sha256": sha256(ROOT / "configs/dense_full_pipeline.yaml"),
        "input_sha256": sha256(DEFAULT_IMAGE_ROOT / one[0]),
        "docker_image": docker_image,
        "docker_image_identity": os.environ.get("PDFSCORE_ISSUE281_DOCKER_IMAGE_IDENTITY"),
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
    (root / "compact_summary.json").write_text(
        json.dumps(
            {"overhead": overhead, "workloads": results, "result_root": str(root)},
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
