"""Strict comparisons and actual correction replay over the frozen matrix."""

import json
import statistics
from pathlib import Path

from src.pipeline.steps.barlines import normalize_barlines
from tools.issue447.analyze import gpu_summary, local_path, proc_summary
from tools.issue447.deepening_analyze import pipeline_checks
from tools.issue447.e2e_correction_replay import run as correction


def main():
    root = Path.cwd()
    issue = root / "logs/issue458"
    labels = [
        "warm-b1",
        "warm-p1",
        "warm-p2",
        "warm-b2",
        "cold-b1",
        "cold-p1",
        "single-b1",
        "single-p1",
    ]
    rows = []
    for label in labels:
        directory = issue / "runs" / label
        baseline = (
            issue / "runs" / ("single-b1" if label.startswith("single") else "warm-b1") / "pipeline"
        )
        checks = pipeline_checks(root, baseline, directory / "pipeline")
        resources = proc_summary(directory / "proc-samples.jsonl")
        gpu = gpu_summary(directory / "gpu-samples.csv")
        row = dict(
            label=label,
            result=json.loads((directory / "result.json").read_text()),
            semantic=checks,
            resources=resources,
            gpu=gpu,
            resource_pass=resources["cgroup_memory_peak_bytes"] <= 16 * 1024**3
            and gpu["memory.used [MiB]"]["peak"] <= 7 * 1024,
        )
        rows.append(row)
    base = [
        r["result"]["docker_e2e_wall_seconds"] for r in rows if r["label"] in ("warm-b1", "warm-b2")
    ]
    parallel = [
        r["result"]["docker_e2e_wall_seconds"] for r in rows if r["label"] in ("warm-p1", "warm-p2")
    ]
    reduction = 1 - statistics.median(parallel) / statistics.median(base)
    manifest = json.loads((issue / "runs/warm-b1/pipeline/manifest.json").read_text())
    box = normalize_barlines(
        json.loads(local_path(root, manifest["pages"][0]["barlines_json"]).read_text())
    )[0]
    overrides = {
        "barline_overrides": [
            {"page": 0, "op": "remove", "bbox": box},
            {"page": 0, "op": "add", "bbox": [box[0] + 2, box[1], box[2] + 2, box[3]]},
        ]
    }
    corrections = []
    reference = None
    for label in labels[:6]:
        result = correction(
            label, issue / "correction" / label, overrides, source_runs=issue / "runs"
        )
        compared = {k: result[k] for k in ("corrected_boxes", "stats", "final_pages", "base_pages")}
        if reference is None:
            reference = compared
        corrections.append(
            dict(label=label, checks={**result["checks"], "equal": compared == reference})
        )
    summary = dict(
        rows=rows,
        warm_baseline=dict(median=statistics.median(base), range=[min(base), max(base)]),
        warm_parallel=dict(
            median=statistics.median(parallel), range=[min(parallel), max(parallel)]
        ),
        warm_reduction=reduction,
        performance_pass=reduction >= 0.05,
        corrections=corrections,
    )
    summary["semantic_pass"] = all(r["semantic"]["all_equal"] for r in rows) and all(
        all(r["checks"].values()) for r in corrections
    )
    summary["resource_pass"] = all(r["resource_pass"] for r in rows)
    (issue / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("rows", "corrections")}))
    assert summary["semantic_pass"] and summary["resource_pass"] and summary["performance_pass"]


if __name__ == "__main__":
    main()
