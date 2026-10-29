"""Distill measured E2E results without adding independent component timings."""

import json
import statistics
from pathlib import Path

from tools.issue447.deepening_analyze import timeline

ROOT = Path.cwd()
ISSUE = ROOT / "logs/issue447"
OUT = ISSUE / "e2e-candidates"
rows = json.loads((OUT / "results.json").read_text())
reference = None
distilled = []
for row in rows:
    label = row["label"]
    run = ISSUE / "runs" / label
    sr = json.loads(
        (run / "pipeline/hybrid_output/pipeline/current_support/_sr_batch/result.json").read_text()
    )
    identities = [{k: r[k] for k in ("image", "sr_sha256", "shape")} for r in sr["outputs"]]
    if reference is None:
        reference = identities
    processes = {}
    for line in (run / "proc-samples.jsonl").read_text().splitlines():
        sample = json.loads(line)
        for p in sample["processes"]:
            if "-m src.pipeline.detection.omr_dln_worker " in p["command"]:
                processes[(p["pid"], p["start_ticks"])] = p["command"]
    expected = 1 if row["mode"] in ("O", "C") else 3
    handoff_checks = {}
    if row["mode"] in ("O", "C"):
        root = run / "pipeline/hybrid_output/pipeline"
        manifest = json.loads((root / "issue447_omr_reuse/completed.json").read_text())
        handoff_checks = {
            "three_fresh_rows": len(manifest["rows"]) == 3,
            "paths_belong_to_current_run": all(
                label in r["sr_image"] and label in r["predictions"] for r in manifest["rows"]
            ),
        }
        for page in ("page_012", "page_013", "page_014"):
            support = json.loads(
                (root / "current_support/Shostakovich-Sym5-Va" / page / "result.json").read_text()
            )
            handoff_checks[page] = (
                bool(support.get("issue447_omr_manifest"))
                and support["commands"][-1][0] == "issue447-same-run-omr-handoff"
                and support["memory_phase_boundaries"]
                == ["sr_batch_process_exited", "omr_batch_process_exited", "current_homr"]
            )
    checks = {
        "strict_pipeline": row["all_equal"],
        "resource_screen": row["resource_screen_passed"],
        "sr_identities_equal": identities == reference,
        "sampled_omr_process_count_expected": len(processes) == expected,
        **handoff_checks,
    }
    assert all(checks.values()), (label, checks)
    provenance = json.loads((run / "provenance.json").read_text())
    distilled.append(
        {
            **row,
            "checks": checks,
            "omr_processes_sampled": [
                {"pid": k[0], "start_ticks": k[1], "command": v} for k, v in processes.items()
            ],
            "sr_native_not_additive": {
                "batch_wall_seconds": sr["batch_wall_sec"],
                "initialization_wall_seconds": sr["model_initialization_wall_sec"],
                "identities": identities,
            },
            "host_observations": timeline(run),
            "telemetry": json.loads((run / "telemetry.json").read_text()),
            "provenance": {
                "path": str(run.relative_to(ROOT) / "provenance.json"),
                "source_commit": provenance["source_commit"],
                "command": provenance["command"],
                "script_sha256": provenance["script_sha256"],
            },
        }
    )
stats = {}
for temp in ("warm", "cold"):
    stats[temp] = {}
    for mode in ("B", "P", "O", "C"):
        cohort = [r for r in distilled if r["temperature"] == temp and r["mode"] == mode]
        if not cohort:
            continue
        times = [r["result"]["docker_e2e_wall_seconds"] for r in cohort]
        baseline = [
            r["result"]["docker_e2e_wall_seconds"]
            for r in distilled
            if r["temperature"] == temp and r["mode"] == "B"
        ]
        bm = statistics.median(baseline)
        stats[temp][mode] = {
            "n": len(times),
            "seconds": times,
            "median_seconds": statistics.median(times),
            "range_seconds": [min(times), max(times)],
            "reduction_vs_baseline_median_percent": 100 * (1 - statistics.median(times) / bm),
            "pages_per_minute_from_median": 180 / statistics.median(times),
            "max_cgroup_memory_gib": max(r["resources"]["cgroup_memory_peak_bytes"] for r in cohort)
            / 1024**3,
            "peak_device_vram_mib": max(r["gpu"]["memory.used [MiB]"]["peak"] for r in cohort),
            "cgroup_cpu_seconds": [
                r["resources"]["cgroup_cpu_cumulative"]["usage_usec"] / 1e6 for r in cohort
            ],
        }
supplements = {}
for name in (
    "replay-single/result.json",
    "replay-combined/result.json",
    "faults/result.json",
    "correction-replay/result.json",
):
    p = OUT / name
    if p.exists():
        supplements[name] = json.loads(p.read_text())
summary = {
    "schema": "issue447.e2e-candidates.results.v1",
    "harness_contract": "tools/issue447/e2e_candidates_contract.json",
    "runtime_source": "2ac7d5245fe65dbfa2093b4e0d60119c58192f86",
    "image": "sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a",
    "uid_gid": "1000:1001",
    "primary": "trace OFF host perf_counter Docker E2E",
    "statistics": stats,
    "runs": distilled,
    "supplemental_validation": supplements,
    "limitations": [
        "warm n=2 and cold n=1 per mode, fixed order",
        "compiler cold, OS/driver cache not flushed",
        "UID1000 fixed; default-root production caching differs; no root E2E",
        "no full68 or production adoption",
        "GPU/CPU clock domains not subtracted; no exact causal wait attribution",
        "WSL device PID attribution unavailable; check continuous events for external competition",
    ],
}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(stats, indent=2))
