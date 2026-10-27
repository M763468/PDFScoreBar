"""Semantic gates and non-additive resource summaries for the continued investigation."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import statistics
from bisect import bisect_right
from pathlib import Path

from tools.issue447.analyze import compare_bundle, gpu_summary, load, local_path, proc_summary


def all_equal(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        if "equal" in value:
            return value["equal"]
        return all(all_equal(v) for v in value.values())
    return True


def source_checks(root: Path, a: Path, b: Path, pages: list[str]) -> dict:
    checks = {}
    for page in pages:
        original_a = load(a / "baseline/batch" / page / "worker_result.json")["artifacts"]
        original_b = load(b / "baseline/batch" / page / "worker_result.json")["artifacts"]
        current_a = a / "current_support/Shostakovich-Sym5-Va" / page / "artifacts"
        current_b = b / "current_support/Shostakovich-Sym5-Va" / page / "artifacts"
        checks[page] = {
            "original": compare_bundle(
                root,
                original_a,
                original_b,
                "detections",
                ("staff_mask", "connector_symbols", "connector_brace_dot"),
            ),
            "x4": compare_bundle(
                root,
                load(current_a / "current_homr_result.json"),
                load(current_b / "current_homr_result.json"),
                "current_sr_detection",
                ("staff_mask", "connector_symbols", "connector_brace_dot"),
            ),
            "omr": load(current_a / "omr_sr" / page / "predictions.json")
            == load(current_b / "omr_sr" / page / "predictions.json"),
        }
    return checks


def pipeline_checks(root: Path, a: Path, b: Path) -> dict:
    ma, mb = load(a / "manifest.json"), load(b / "manifest.json")
    pages = [p["page_id"] for p in ma["pages"]]
    checks = {
        "page_order": pages == [p["page_id"] for p in mb["pages"]],
        "input_order": [p["image_path"] for p in ma["pages"]]
        == [p["image_path"] for p in mb["pages"]],
        "combined_base": load(a / "intermediate/numbering_base.json")
        == load(b / "intermediate/numbering_base.json"),
        "combined_final_and_movement_metadata": load(a / "outputs/numbering_final.json")
        == load(b / "outputs/numbering_final.json"),
        "filters": load(a / "filters.json") == load(b / "filters.json"),
    }
    per_page = {}
    for pa, pb in zip(ma["pages"], mb["pages"]):
        page = pa["page_id"]

        def support(p):
            return {k: v for k, v in p["mmr_support"].items() if k != "current_homr_staff_mask"}

        def overrides(path):
            return [
                {k: v for k, v in item.items() if k != "comment"}
                for item in load(path)["measure_overrides"]
            ]

        per_page[page] = {
            "source_reference": pa["source_reference"] == pb["source_reference"],
            "detector_geometry": load(local_path(root, pa["barlines_json"]))
            == load(local_path(root, pb["barlines_json"])),
            "mmr_geometry": support(pa) == support(pb),
            "correction_stats": pa.get("barline_overrides") == pb.get("barline_overrides"),
            "numbering_base": load(a / "intermediate" / page / "numbering_base.json")
            == load(b / "intermediate" / page / "numbering_base.json"),
            "numbering_final_and_metadata": load(a / "outputs" / page / "numbering_final.json")
            == load(b / "outputs" / page / "numbering_final.json"),
            "mmr_targets_skips": overrides(a / "intermediate" / page / "overrides_mmr.json")
            == overrides(b / "intermediate" / page / "overrides_mmr.json"),
        }
    checks["per_page"] = per_page
    checks["source"] = source_checks(
        root, a / "hybrid_output/pipeline", b / "hybrid_output/pipeline", pages
    )
    return {
        "all_equal": all_equal(checks),
        "checks": checks,
        "allowed_differences": "run paths and display-only OCR score comments; no geometry/order/number/mapping tolerances",
    }


def timeline(run: Path) -> dict:
    """Correlate coarse utilization with CPU activity, without calling it causal wait."""
    proc = run / "proc-samples.jsonl"
    if not proc.is_file():
        return {"status": "Not run", "reason": "no run-local process samples"}
    samples = []
    with proc.open() as stream:
        for line in stream:
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    gpu = []
    with (run / "gpu-samples.csv").open() as stream:
        for row in csv.DictReader(stream):
            row = {k.strip(): v.strip() for k, v in row.items() if k is not None}
            try:
                stamp = (
                    dt.datetime.strptime(row["timestamp"], "%Y/%m/%d %H:%M:%S.%f")
                    .replace(tzinfo=dt.timezone.utc)
                    .timestamp()
                )
                gpu.append((stamp, float(row["utilization.gpu [%]"].split()[0])))
            except (KeyError, ValueError):
                pass
    if not samples or not gpu:
        return {"status": "Blocked", "reason": "no valid process/GPU timestamps"}
    offset_hours = round((gpu[0][0] - samples[0]["epoch"]) / 3600)
    gpu = [(t - offset_hours * 3600, utilization) for t, utilization in gpu]
    times = [t for t, _ in gpu]
    phases = {}
    cpu_last = None
    time_last = None
    queues = {}
    for sample in samples:
        fields = dict(line.split() for line in sample["cgroup"].get("cpu.stat", "").splitlines())
        cpu = int(fields.get("usage_usec", 0)) / 1e6
        now = sample["epoch"]
        if any("current_sr_batch_worker" in p["command"] for p in sample["processes"]):
            phase = "SR"
        elif any("maintained_source_page_worker" in p["command"] for p in sample["processes"]):
            phase = "source"
        else:
            phase = "other"
        if time_last is not None and cpu_last is not None:
            elapsed = now - time_last
            index = max(0, min(len(gpu) - 1, bisect_right(times, now) - 1))
            utilization = gpu[index][1]
            item = phases.setdefault(
                phase,
                {
                    "sampled_seconds": 0.0,
                    "gpu_high_seconds": 0.0,
                    "gpu_low_cpu_active_seconds": 0.0,
                    "gpu_low_cpu_low_seconds": 0.0,
                    "mixed_seconds": 0.0,
                },
            )
            item["sampled_seconds"] += elapsed
            if utilization >= 80:
                key = "gpu_high_seconds"
            elif utilization < 10:
                key = (
                    "gpu_low_cpu_active_seconds"
                    if cpu - cpu_last > elapsed * 0.5
                    else "gpu_low_cpu_low_seconds"
                )
            else:
                key = "mixed_seconds"
            item[key] += elapsed
        for process in sample["processes"]:
            key = (process["pid"], process["start_ticks"])
            queues[key] = max(
                queues.get(key, 0), process.get("scheduler", {}).get("runqueue_wait_ns", 0)
            )
        cpu_last, time_last = cpu, now
    return {
        "status": "Passed",
        "gpu_timestamp_inferred_offset_hours": offset_hours,
        "phase_utilization_correlation_not_causal_wait": phases,
        "sum_sampled_main_thread_runqueue_wait_seconds": sum(queues.values()) / 1e9,
        "limits": "GPU samples ~1 second, CPU threshold 0.5 cores; clock-hour offset inferred; scheduler counters are sampled main threads, not all process threads; low GPU is not automatically CPU/I/O waiting",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("logs/issue447/deepening/summary.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    issue = root / "logs/issue447"
    journal = issue / "deepening/cache-matrix.jsonl"
    cache_rows = [json.loads(line) for line in journal.read_text().splitlines() if line]
    completed = [r for r in cache_rows if r["event"] == "complete"]
    summary = {"cache_observations": completed, "runs": {}}
    if completed:
        summary["cache_statistics"] = {}
        for condition in ("cold", "warm"):
            values = [
                r["result"]["docker_e2e_wall_seconds"]
                for r in completed
                if r["condition"] == condition
            ]
            if values:
                summary["cache_statistics"][condition] = {
                    "n": len(values),
                    "median": statistics.median(values),
                    "min": min(values),
                    "max": max(values),
                }
    for run in sorted((issue / "runs").glob("deep-*")):
        if not (run / "result.json").is_file():
            continue
        data = {
            "result": load(run / "result.json"),
            "gpu": gpu_summary(run / "gpu-samples.csv"),
            "timeline": timeline(run),
        }
        if (run / "proc-samples.jsonl").is_file():
            resource = proc_summary(run / "proc-samples.jsonl")
            data["resources"] = {
                k: v for k, v in resource.items() if k != "process_residency_not_additive"
            }
        if (run / "component/result.json").is_file():
            data["component"] = load(run / "component/result.json")
        if (run / "telemetry.json").is_file():
            data["telemetry"] = load(run / "telemetry.json")
        sr = next(run.rglob("_sr_batch/result.json"), None)
        if sr is not None:
            payload = load(sr)
            data["sr"] = {
                k: payload[k]
                for k in ("batch_wall_sec", "model_initialization_wall_sec", "outputs")
            }
        summary["runs"][run.name] = data
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary.get("cache_statistics", {}), indent=2))


if __name__ == "__main__":
    main()
