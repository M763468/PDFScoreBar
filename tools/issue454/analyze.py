"""Offline strict gates for frozen cache E2E runs; never starts inference."""

import json
import statistics
from pathlib import Path

import cv2
import numpy as np

from tools.issue447.analyze import gpu_summary, load, local_path, proc_summary
from tools.issue447.deepening_analyze import pipeline_checks

ROOT = Path.cwd()
ISSUE = ROOT / "logs/issue454/final"


def sr_result(run):
    return load(run / "pipeline/hybrid_output/pipeline/current_support/_sr_batch/result.json")


def compare_sr(a, b):
    aa, bb = sr_result(a)["outputs"], sr_result(b)["outputs"]
    if len(aa) != len(bb):
        return False
    for x, y in zip(aa, bb):
        if any(x[k] != y[k] for k in ("image", "shape", "sr_sha256")):
            return False
        one = cv2.imread(str(local_path(ROOT, x["sr_image"])), cv2.IMREAD_UNCHANGED)
        two = cv2.imread(str(local_path(ROOT, y["sr_image"])), cv2.IMREAD_UNCHANGED)
        if one is None or two is None or not np.array_equal(one, two):
            return False
    return True


def main():
    out = {"cohorts": [], "all_passed": True}
    for uid in (0, 1000):
        for scope in ("single", "multi"):
            rows = []
            cold_times, warm_times, deltas = [], [], []
            reference = ISSUE / "runs" / f"u0-{scope}-1-cold"
            for pair in (1, 2, 3):
                runs = []
                for state in ("cold", "warm"):
                    label = f"u{uid}-{scope}-{pair}-{state}"
                    run = ISSUE / "runs" / label
                    result = load(run / "result.json")
                    sr = sr_result(run)
                    cache = sr["compiler_cache"]
                    counters = sr["compiler_counters"]
                    indu = counters.get("inductor", {})
                    hit, miss = indu.get("fxgraph_cache_hit", 0), indu.get("fxgraph_cache_miss", 0)
                    geometry = pipeline_checks(ROOT, reference / "pipeline", run / "pipeline")
                    gpu = gpu_summary(run / "gpu-samples.csv")
                    peak = gpu["memory.used [MiB]"]["peak"]
                    checks = {
                        "completed": result["exit_code"] == 0 and result["trace"] == "off",
                        "sr_digest_and_pixels": compare_sr(reference, run),
                        "strict_pipeline": geometry["all_equal"],
                        "uid": cache["identity"]["uid"] == uid,
                        "expected_cache_state": cache["state"]
                        == ("empty" if state == "cold" else "verified-reuse"),
                        "compiler_observed": hit + miss > 0,
                        "warm_has_hits": state == "cold" or hit > 0,
                        "no_graph_break": not counters.get("graph_break"),
                        "resource_screen": peak <= 7168,
                    }
                    wall = result["docker_e2e_wall_seconds"]
                    (cold_times if state == "cold" else warm_times).append(wall)
                    row = dict(
                        label=label,
                        wall=wall,
                        checks=checks,
                        compiler_counters=counters,
                        cache_key=cache["key"],
                        gpu=gpu,
                        processes=proc_summary(run / "proc-samples.jsonl"),
                        semantics=geometry,
                    )
                    rows.append(row)
                    runs.append(sr)
                    out["all_passed"] &= all(checks.values())
                paired_identity = (
                    runs[0]["compiler_cache"]["identity"] == runs[1]["compiler_cache"]["identity"]
                )
                out["all_passed"] &= paired_identity
                deltas.append(cold_times[-1] - warm_times[-1])
            cm, wm = statistics.median(cold_times), statistics.median(warm_times)
            performance_passed = wm <= 0.8 * cm
            out["all_passed"] &= performance_passed
            out["cohorts"].append(
                dict(
                    uid=uid,
                    scope=scope,
                    cold=cold_times,
                    warm=warm_times,
                    cold_median=cm,
                    warm_median=wm,
                    cold_range=[min(cold_times), max(cold_times)],
                    warm_range=[min(warm_times), max(warm_times)],
                    paired_saving=deltas,
                    paired_saving_median=statistics.median(deltas),
                    improvement_percent=100 * (1 - wm / cm),
                    performance_passed=performance_passed,
                    rows=rows,
                )
            )
    path = ISSUE / "analysis.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "cohorts"}))
    assert out["all_passed"], str(path)


if __name__ == "__main__":
    main()
