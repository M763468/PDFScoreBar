"""Run the integrated Issue #284 candidate on page_013 with tracing disabled.

This is the post-integration smoke/performance gate before the canonical full-68
checkpoint.  It compares the final hybrid and numbering JSON with the retained
post-#285 one-page baseline and records process-tree/GPU peaks.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

from tools.issue284.run_baseline import (
    CANONICAL_CONFIG,
    PIPELINE_PYTHON,
    ROOT,
    ResourceSampler,
    require_canonical_container,
    sha256,
)

SCORE = "Shostakovich-Sym5-Va"
IMAGE = ROOT / "data" / "evaluation2" / "images" / SCORE / "page_013.png"
RUN_ID = "issue284_candidate_one_page"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _baseline_workload(summary: dict[str, Any]) -> dict[str, Any]:
    for workload in summary.get("workloads", []):
        if workload.get("name") == "one_page_trace_off":
            return dict(workload)
    raise ValueError("Baseline summary lacks one_page_trace_off workload")


def _compare_json(candidate: Path, reference: Path) -> dict[str, Any]:
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    if not reference.is_file():
        raise FileNotFoundError(reference)
    left = _load_json(candidate)
    right = _load_json(reference)
    return {
        "candidate": str(candidate),
        "reference": str(reference),
        "candidate_sha256": sha256(candidate),
        "reference_sha256": sha256(reference),
        "parsed_equal": left == right,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require_canonical_container()
    if not IMAGE.is_file():
        raise FileNotFoundError(IMAGE)

    baseline_summary_path = args.baseline_summary.resolve()
    baseline = _load_json(baseline_summary_path)
    baseline_one = _baseline_workload(baseline)
    baseline_run_root = Path(str(baseline_one["config"])).resolve().parent

    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Candidate output must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    staged = output / "input_staging" / SCORE
    staged.mkdir(parents=True, exist_ok=True)
    staged_image = staged / IMAGE.name
    staged_image.symlink_to(IMAGE)

    config = yaml.safe_load(CANONICAL_CONFIG.read_text(encoding="utf-8"))
    config["inputs"]["pdf_to_images"]["output_dir"] = str(staged)
    config["detection"]["hybrid_output_root"] = str(output / "hybrid_output")
    # Make the candidate mechanism explicit in the retained derived config.
    config["detection"]["sr_channels_last"] = True
    config_path = output / "config_derived.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    command = [
        str(PIPELINE_PYTHON),
        "-m",
        "src.pipeline.main",
        "--config",
        str(config_path),
        "--run-id",
        RUN_ID,
        "--output-root",
        str(output / "pipeline_output"),
        "--page-limit",
        "1",
    ]
    env = os.environ.copy()
    env.pop("PDFSCORE_PERF_TRACE_DIR", None)
    env["PDFSCORE_PERF_TRACE_RUN"] = RUN_ID
    env["PDFSCORE_PERF_TRACE_ROLE"] = "pipeline_main"

    log_path = output / "pipeline.stdout.log"
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
        sampler = ResourceSampler(process.pid, output / "resource_samples.jsonl")
        sampler.start()
        returncode = process.wait()
        resources = sampler.finish()
    wall = time.perf_counter() - started

    if returncode != 0:
        tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-100:]
        failure = {
            "schema_version": "issue284.integrated_candidate_one_page.v1",
            "status": "failed",
            "returncode": returncode,
            "e2e_wall_sec": wall,
            "command": command,
            "log": str(log_path),
            "resources": resources,
            "log_tail": tail,
        }
        (output / "candidate_summary.json").write_text(
            json.dumps(failure, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(failure, indent=2, ensure_ascii=False))
        return returncode or 1

    candidate_run = output / "pipeline_output" / RUN_ID
    candidate_final = candidate_run / "outputs" / "page_013" / "numbering_final.json"
    candidate_hybrid = (
        output / "hybrid_output" / RUN_ID / "hybrid_results" / "page_013_hybrid.json"
    )
    sr_batch_result = (
        output / "hybrid_output" / RUN_ID / "current_support" / "_sr_batch" / "result.json"
    )
    if not sr_batch_result.is_file():
        raise FileNotFoundError(sr_batch_result)
    sr_batch = _load_json(sr_batch_result)

    baseline_final = (
        baseline_run_root
        / "pipeline_output"
        / "one_page_trace_off"
        / "outputs"
        / "page_013"
        / "numbering_final.json"
    )
    baseline_hybrid = (
        baseline_run_root
        / "hybrid_output"
        / "one_page_trace_off"
        / "hybrid_results"
        / "page_013_hybrid.json"
    )

    baseline_wall = float(baseline_one["e2e_wall_sec"])
    summary = {
        "schema_version": "issue284.integrated_candidate_one_page.v1",
        "status": "completed",
        "candidate_git_commit": os.environ.get("PDFSCORE_ISSUE284_GIT_COMMIT"),
        "image": str(IMAGE),
        "image_sha256": sha256(IMAGE),
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "command": command,
        "e2e_wall_sec": wall,
        "baseline_e2e_wall_sec": baseline_wall,
        "e2e_saved_sec": baseline_wall - wall,
        "e2e_reduction_fraction": (baseline_wall - wall) / baseline_wall,
        "resources": resources,
        "sr_batch": sr_batch,
        "hybrid": _compare_json(candidate_hybrid, baseline_hybrid),
        "numbering_final": _compare_json(candidate_final, baseline_final),
        "production_semantics_equal": bool(
            _load_json(candidate_hybrid) == _load_json(baseline_hybrid)
            and _load_json(candidate_final) == _load_json(baseline_final)
        ),
    }
    summary_path = output / "candidate_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["production_semantics_equal"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
