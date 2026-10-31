"""Semantic gates and non-additive resource summaries for the continued investigation."""

from __future__ import annotations

import argparse
import json
import statistics
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


def numbering_payload(run: Path, pages: list[str], section: str, name: str):
    """Single-page runs retain per-page numbering; multi-page runs require combined JSON."""
    combined = run / section / name
    if len(pages) == 1 and not combined.exists():
        return load(run / section / pages[0] / name)
    return load(combined)


def pipeline_checks(root: Path, a: Path, b: Path) -> dict:
    ma, mb = load(a / "manifest.json"), load(b / "manifest.json")
    pages = [p["page_id"] for p in ma["pages"]]
    checks = {
        "page_order": pages == [p["page_id"] for p in mb["pages"]],
        "input_order": [p["image_path"] for p in ma["pages"]]
        == [p["image_path"] for p in mb["pages"]],
        "combined_base": numbering_payload(a, pages, "intermediate", "numbering_base.json")
        == numbering_payload(b, pages, "intermediate", "numbering_base.json"),
        "combined_final_and_movement_metadata": numbering_payload(
            a, pages, "outputs", "numbering_final.json"
        )
        == numbering_payload(b, pages, "outputs", "numbering_final.json"),
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


def is_source_worker(command: str) -> bool:
    """Recognize sampled top-level source entrypoints, excluding nested support.

    The sampler joins /proc argv with spaces. Match module/flag tokens rather
    than substrings in request paths or lookalike module names.
    """
    args = command.split()
    try:
        index = args.index("-m")
        module = args[index + 1]
    except (ValueError, IndexError):
        return False
    if module == "src.pipeline.detection.maintained_source_page_worker":
        return True
    return module == "tools.issue447.omr_reuse_poc" and "--support" not in args[index + 2 :]


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
    if not samples:
        return {"status": "Blocked", "reason": "no valid process samples"}
    phases = {}
    cpu_last = None
    time_last = None
    queues = {}
    for sample in samples:
        fields = dict(line.split() for line in sample["cgroup"].get("cpu.stat", "").splitlines())
        cpu = int(fields.get("usage_usec", 0)) / 1e6
        now = sample["monotonic"]
        if any("current_sr_batch_worker" in p["command"] for p in sample["processes"]):
            phase = "SR"
        elif any(is_source_worker(p["command"]) for p in sample["processes"]):
            phase = "source"
        else:
            phase = "other"
        if time_last is not None and cpu_last is not None:
            elapsed = now - time_last
            item = phases.setdefault(phase, {"sampled_seconds": 0.0, "cgroup_cpu_seconds": 0.0})
            item["sampled_seconds"] += elapsed
            item["cgroup_cpu_seconds"] += max(0.0, cpu - cpu_last)
        for process in sample["processes"]:
            key = (process["pid"], process["start_ticks"])
            queues[key] = max(
                queues.get(key, 0), process.get("scheduler", {}).get("runqueue_wait_ns", 0)
            )
        cpu_last, time_last = cpu, now
    return {
        "status": "Passed",
        "host_phase_samples_not_exclusive_stages": phases,
        "gpu_cpu_clock_correlation": "Blocked: calibrated device/host clock domains differ; raw GPU summary remains independent",
        "sum_sampled_main_thread_runqueue_wait_seconds": sum(queues.values()) / 1e9,
        "limits": "Host monotonic samples only. Phase identity follows observed worker commands and includes polling uncertainty. Scheduler counters cover sampled main threads, not all threads. Neither low GPU utilization nor main-thread wait identifies causal CPU/I/O wait.",
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
