"""Run the Issue #283 post-vectorization full-pipeline E2E gate."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from tools.issue281.run_phase1 import (
    DEFAULT_IMAGE_ROOT,
    _require_canonical_container,
    _run_workload,
    git,
    sha256,
)

ROOT = Path(__file__).resolve().parents[2]
BASELINES = {
    "one_page_trace_off": 304.259915,
    "three_page_trace_on": 879.274089,
}


def _comparison(name: str, current: float) -> dict[str, float]:
    baseline = BASELINES[name]
    saved = baseline - current
    return {
        "baseline_e2e_wall_sec": baseline,
        "current_e2e_wall_sec": current,
        "saved_sec": saved,
        "reduction_fraction": saved / baseline,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    _require_canonical_container()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    results = [
        _run_workload(output, "one_page_trace_off", ["page_013.png"], tracing=False),
        _run_workload(
            output,
            "three_page_trace_on",
            ["page_012.png", "page_013.png", "page_014.png"],
            tracing=True,
        ),
    ]
    by_name = {item["name"]: item for item in results}

    commit = os.environ.get("PDFSCORE_ISSUE283_GIT_COMMIT") or git("rev-parse", "HEAD")
    dirty_env = os.environ.get("PDFSCORE_ISSUE283_GIT_DIRTY")
    dirty = (
        None
        if dirty_env is None
        else dirty_env.strip().lower() in {"1", "true", "yes", "on"}
    )
    provenance = {
        "schema_version": "issue283.e2e_validation.provenance.v1",
        "commit": commit,
        "dirty": dirty,
        "docker_image": os.environ.get(
            "PDFSCORE_ISSUE281_DOCKER_IMAGE", "pdfscore_pipeline_gpu"
        ),
        "docker_image_identity": os.environ.get("PDFSCORE_ISSUE281_DOCKER_IMAGE_IDENTITY"),
        "config_sha256": sha256(ROOT / "configs/dense_full_pipeline.yaml"),
        "inputs": {
            name: sha256(DEFAULT_IMAGE_ROOT / name)
            for name in ("page_012.png", "page_013.png", "page_014.png")
        },
    }
    comparisons = {
        name: _comparison(name, float(by_name[name]["e2e_wall_sec"])) for name in BASELINES
    }
    summary = {
        "schema_version": "issue283.e2e_validation.summary.v1",
        "provenance": provenance,
        "comparisons": comparisons,
        "three_page_current_avg_sec_per_page": float(
            by_name["three_page_trace_on"]["e2e_wall_sec"]
        )
        / 3.0,
        "workloads": results,
    }
    (output / "e2e_summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
