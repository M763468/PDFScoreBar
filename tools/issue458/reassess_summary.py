"""Separate practical-adoption gates; never rewrites issue458's original result."""

import json
import statistics

from src.pipeline.steps.barlines import normalize_barlines
from tools.issue447.analyze import gpu_summary, local_path, proc_summary
from tools.issue447.deepening_analyze import pipeline_checks
from tools.issue447.e2e_correction_replay import run as correction
from tools.issue458.reassess import OUT, ROOT


def main():
    matrix = json.loads((OUT / "matrix.json").read_text())
    labels = [row["label"] for row in matrix]
    primary_labels = [label for label in labels if label.startswith("primary-")]
    rows = []
    for row in matrix:
        label = row["label"]
        directory = OUT / "runs" / label
        if row["exit_code"] != 0:
            rows.append(
                dict(
                    label=label,
                    status="Failed",
                    exit_code=row["exit_code"],
                    semantic={"all_equal": False},
                    resource_pass=False,
                    selection_pass=False,
                    noise=row["noise"],
                )
            )
            continue
        if label.startswith("primary-"):
            reference = OUT / "runs/primary-b1/pipeline"
        elif label.startswith("large-"):
            reference = OUT / "runs/large-b1/pipeline"
            if not (reference / "manifest.json").exists():
                reference = OUT / "runs/large-qualification/pipeline"
        else:
            reference = ROOT / "logs/issue458/runs/single-b1/pipeline"
        semantic = pipeline_checks(ROOT, reference, directory / "pipeline")
        resource = proc_summary(directory / "proc-samples.jsonl")
        gpu = gpu_summary(directory / "gpu-samples.csv")
        admission = json.loads(
            (
                directory / "pipeline/hybrid_output/pipeline/source_page_workers/admission.json"
            ).read_text()
        )
        resource_pass = (
            resource["cgroup_memory_peak_bytes"] <= 16 * 1024**3
            and gpu["memory.used [MiB]"]["peak"] <= 7 * 1024
        )
        expected = 1 if label == "single-request2" else row["workers"]
        rows.append(
            dict(
                label=label,
                elapsed=row["result"]["docker_e2e_wall_seconds"],
                semantic=semantic,
                resources=resource,
                gpu=gpu,
                resource_pass=resource_pass,
                admission=admission,
                selection_pass=admission["selected_workers"] == expected,
                noise=row["noise"],
            )
        )
    by_label = {row["label"]: row for row in rows}
    base = [row["elapsed"] for row in rows if row["label"].startswith("primary-b")]
    parallel = [row["elapsed"] for row in rows if row["label"].startswith("primary-p")]
    pairs = [
        dict(
            pair=i,
            baseline=by_label[f"primary-b{i}"]["elapsed"],
            parallel=by_label[f"primary-p{i}"]["elapsed"],
        )
        for i in range(1, 5)
    ]
    for pair in pairs:
        pair["reduction"] = 1 - pair["parallel"] / pair["baseline"]
    seconds_saved = statistics.median(base) - statistics.median(parallel)
    perf_gates = dict(
        positive_median=seconds_saved > 0,
        median_saved_at_least_5s=seconds_saved >= 5,
        wins_at_least_3_of_4=sum(p["reduction"] > 0 for p in pairs) >= 3,
        no_pair_regression_over_3pct=all(p["reduction"] >= -0.03 for p in pairs),
    )

    def stats(values):
        median = statistics.median(values)
        return dict(
            values=values,
            median=median,
            range=[min(values), max(values)],
            mad=statistics.median(abs(value - median) for value in values),
        )

    manifest = json.loads((OUT / "runs/primary-b1/pipeline/manifest.json").read_text())
    box = normalize_barlines(
        json.loads(local_path(ROOT, manifest["pages"][0]["barlines_json"]).read_text())
    )[0]
    overrides = {
        "barline_overrides": [
            {"page": 0, "op": "remove", "bbox": box},
            {"page": 0, "op": "add", "bbox": [box[0] + 2, box[1], box[2] + 2, box[3]]},
        ]
    }
    reference = None
    corrections = []
    for label in primary_labels:
        result = correction(label, OUT / "correction" / label, overrides, source_runs=OUT / "runs")
        compared = {
            key: result[key] for key in ("corrected_boxes", "stats", "final_pages", "base_pages")
        }
        if reference is None:
            reference = compared
        corrections.append(
            dict(label=label, checks={**result["checks"], "equal": compared == reference})
        )
    summary = dict(
        original_gate="Failed: 4.900958%; historical cohort unchanged",
        phase="2026-11-01 practical adoption reassessment",
        rows=rows,
        missing_runs=sorted(
            set(["large-qualification", "large-b1", "large-p1", "single-request2"]) - set(labels)
        ),
        primary_baseline=stats(base),
        primary_parallel=stats(parallel),
        pairs=pairs,
        median_saved_seconds=seconds_saved,
        median_reduction=1 - statistics.median(parallel) / statistics.median(base),
        performance_gates=perf_gates,
        performance_pass=all(perf_gates.values()),
        semantic_pass=all(r["semantic"]["all_equal"] for r in rows) and len(rows) == 12,
        resource_pass=all(r["resource_pass"] for r in rows),
        selection_pass=all(r["selection_pass"] for r in rows),
        no_persistent_cpu_competition=all(
            not r["noise"]["persistent_cpu_competition"] for r in rows
        ),
        corrections=corrections,
        correction_pass=all(all(r["checks"].values()) for r in corrections),
    )
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        json.dumps(
            {key: value for key, value in summary.items() if key not in ("rows", "corrections")}
        )
    )
    assert all(
        summary[k]
        for k in (
            "performance_pass",
            "semantic_pass",
            "resource_pass",
            "selection_pass",
            "no_persistent_cpu_competition",
            "correction_pass",
        )
    )


if __name__ == "__main__":
    main()
