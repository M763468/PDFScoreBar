"""Re-score retained Issue #447 logs; this script never launches inference."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def proc_summary(path: Path) -> dict:
    processes = {}
    first_time = last_time = None
    peak_rss = 0
    cgroup = {}
    observer_cpu = 0.0
    count = 0
    with path.open() as stream:
        for line in stream:
            try:
                sample = json.loads(line)
            except json.JSONDecodeError:
                continue
            count += 1
            now = sample["monotonic"]
            first_time = now if first_time is None else first_time
            last_time = now
            cgroup = sample["cgroup"]
            peak_rss = max(peak_rss, sum(p["rss_bytes"] for p in sample["processes"]))
            for process in sample["processes"]:
                if process["pid"] == sample["observer_pid"]:
                    observer_cpu = max(observer_cpu, process["cpu_seconds"])
                key = (process["pid"], process["start_ticks"])
                item = processes.setdefault(
                    key,
                    {
                        "pid": process["pid"],
                        "command": process["command"],
                        "first_seen": now,
                        "last_seen": now,
                        "cpu_seconds": 0,
                        "peak_rss_bytes": 0,
                        "max_sampled_io": {},
                    },
                )
                item["last_seen"] = now
                item["cpu_seconds"] = max(item["cpu_seconds"], process["cpu_seconds"])
                item["peak_rss_bytes"] = max(item["peak_rss_bytes"], process["rss_bytes"])
                for k, v in process["io"].items():
                    item["max_sampled_io"][k] = max(item["max_sampled_io"].get(k, 0), v)
    for item in processes.values():
        item["observed_residency_seconds"] = item["last_seen"] - item["first_seen"]
        item["left_censored"] = item["first_seen"] == first_time
        item["right_censored"] = item["last_seen"] == last_time
    physical_io = {"rbytes": 0, "wbytes": 0, "rios": 0, "wios": 0}
    for line in cgroup.get("io.stat", "").splitlines():
        for field in line.split()[1:]:
            key, value = field.split("=")
            if key in physical_io:
                physical_io[key] += int(value)
    cpu = {}
    for line in cgroup.get("cpu.stat", "").splitlines():
        key, value = line.split()
        cpu[key] = int(value)
    return {
        "sample_count": count,
        "first_monotonic": first_time,
        "last_monotonic": last_time,
        "interval_seconds": 0.2,
        "sampled_peak_sum_rss_bytes": peak_rss,
        "observer_cpu_seconds": observer_cpu,
        "cgroup_memory_peak_bytes": int(cgroup.get("memory.peak", "0")),
        "cgroup_cpu_cumulative": cpu,
        "cgroup_physical_io_cumulative": physical_io,
        "process_residency_not_additive": list(processes.values()),
        "limits": "final sample may precede process exit; residency endpoints uncertain by interval; nested workers overlap; per-process I/O must not be summed as exclusive E2E I/O",
    }


def gpu_summary(path: Path) -> dict:
    if not path.is_file():
        return {}
    result = {}
    for row in csv.DictReader(path.open()):
        for column, value in row.items():
            if column is None:
                continue
            name = column.strip()
            if name not in ("utilization.gpu [%]", "memory.used [MiB]"):
                continue
            try:
                number = float(value.strip().split()[0])
            except (ValueError, IndexError, AttributeError):
                continue
            values = result.setdefault(name, [])
            values.append(number)
    return {
        key: {"count": len(values), "mean": sum(values) / len(values), "peak": max(values)}
        for key, values in result.items()
    }


def load(path: Path):
    return json.loads(path.read_text())


def local_path(root: Path, path: str) -> Path:
    return root / path.removeprefix("/workspace/")


def compare_bundle(root: Path, a: dict, b: dict, detection_key: str, masks: tuple) -> dict:
    import cv2
    import numpy as np

    result = {
        "ordered_predictions": load(local_path(root, a[detection_key]))["predictions"]
        == load(local_path(root, b[detection_key]))["predictions"]
    }
    for key in masks:
        aa = cv2.imread(str(local_path(root, a[key])), -1)
        bb = cv2.imread(str(local_path(root, b[key])), -1)
        if aa is None or bb is None:
            raise FileNotFoundError(f"missing semantic mask {key}")
        result[key] = {
            "equal": bool(aa.shape == bb.shape and np.array_equal(aa, bb)),
            "different_values": int(np.count_nonzero(aa != bb)) if aa.shape == bb.shape else None,
        }
    return result


def parallel_semantics(root: Path, issue: Path) -> dict:
    base = issue / "runs/multi-off-warm/pipeline/hybrid_output/pipeline"
    other = issue / "runs/source-parallel-two/component"
    result = {}
    for page in ("page_012", "page_014"):
        a = load(base / "baseline/batch" / page / "worker_result.json")["artifacts"]
        b = load(other / "baseline/batch" / page / "worker_result.json")["artifacts"]
        checks = {
            "original_homr": compare_bundle(
                root, a, b, "detections", ("staff_mask", "connector_symbols", "connector_brace_dot")
            )
        }
        a_path = base / "current_support/Shostakovich-Sym5-Va" / page / "artifacts"
        b_path = other / "current_support/Shostakovich-Sym5-Va" / page / "artifacts"
        checks["x4_homr"] = compare_bundle(
            root,
            load(a_path / "current_homr_result.json"),
            load(b_path / "current_homr_result.json"),
            "current_sr_detection",
            ("staff_mask", "connector_symbols", "connector_brace_dot"),
        )
        checks["omr_ordered_predictions"] = load(
            a_path / "omr_sr" / page / "predictions.json"
        ) == load(b_path / "omr_sr" / page / "predictions.json")
        result[page] = checks
    return result


def source_semantics(root: Path, baseline: Path, candidate: Path) -> dict:
    """Compare named semantic outputs and decoded masks, not counts/PNG bytes."""
    import cv2
    import numpy as np

    result = {}
    for name in ("numbering_base.json", "numbering_final.json"):
        a, b = next(baseline.rglob(name), None), next(candidate.rglob(name), None)
        if a is not None and b is not None:
            result[name] = load(a)["pages"] == load(b)["pages"]
    a, b = (
        next(baseline.rglob("pipeline2_no_peak_filtered_cnn.json"), None),
        next(candidate.rglob("pipeline2_no_peak_filtered_cnn.json"), None),
    )
    if a is not None and b is not None:
        result["ordered_detector_geometry"] = load(a) == load(b)
    a, b = (
        next(baseline.rglob("overrides_mmr.json"), None),
        next(candidate.rglob("overrides_mmr.json"), None),
    )
    if a is not None and b is not None:

        def mmr(path):
            return [
                {k: v for k, v in item.items() if k != "comment"}
                for item in load(path)["measure_overrides"]
            ]

        result["mmr_targets_and_skips"] = mmr(a) == mmr(b)
    a, b = (
        next(baseline.rglob("current_homr_result.json"), None),
        next(candidate.rglob("current_homr_result.json"), None),
    )
    if a is not None and b is not None:
        pa, pb = load(a), load(b)
        result["x4_homr_ordered_predictions"] = (
            load(local_path(root, pa["current_sr_detection"]))["predictions"]
            == load(local_path(root, pb["current_sr_detection"]))["predictions"]
        )
        for key in ("staff_mask", "connector_symbols", "connector_brace_dot"):
            aa, bb = (
                cv2.imread(str(local_path(root, pa[key])), -1),
                cv2.imread(str(local_path(root, pb[key])), -1),
            )
            if aa is None or bb is None:
                raise FileNotFoundError(f"missing semantic mask {key}")
            same_shape = aa.shape == bb.shape
            result["x4_" + key] = {
                "equal": bool(same_shape and np.array_equal(aa, bb)),
                "different_values": int(np.count_nonzero(aa != bb)) if same_shape else None,
                "shape_a": list(aa.shape),
                "shape_b": list(bb.shape),
            }
    if (baseline / "manifest.json").is_file() and (candidate / "manifest.json").is_file():

        def support(path):
            return [
                {
                    "page_id": p["page_id"],
                    "image_path": p["image_path"],
                    "mappings": p["mmr_support"]["mappings"],
                    "coordinate_space": p["mmr_support"]["coordinate_space"],
                }
                for p in load(path)["pages"]
            ]

        result["page_identity_and_mmr_geometry_mappings"] = support(
            baseline / "manifest.json"
        ) == support(candidate / "manifest.json")
    return result


def select_process_samples(
    directory: Path, legacy_multi_proc: Path | None = None
) -> tuple[Path | None, str]:
    """Keep observations attached to their run; legacy evidence requires opt-in."""
    local = directory / "proc-samples.jsonl"
    if local.is_file():
        return local, "run-local"
    if directory.name == "multi-off-warm" and legacy_multi_proc is not None:
        if not legacy_multi_proc.is_file():
            raise FileNotFoundError(legacy_multi_proc)
        return legacy_multi_proc, "explicit-legacy-fallback"
    return None, "no-run-local-samples"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("logs/issue447/followup/summary.json"))
    parser.add_argument(
        "--legacy-multi-proc",
        type=Path,
        help="Explicit observer file for the original multi-off-warm attempt only; run-local samples always take precedence",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    issue = root / "logs/issue447"
    summary = {"source_commit": "2ac7d5245fe65dbfa2093b4e0d60119c58192f86", "runs": {}}
    for directory in sorted((issue / "runs").iterdir()):
        if not (directory / "result.json").is_file():
            continue
        run = {
            "result": load(directory / "result.json"),
            "gpu": gpu_summary(directory / "gpu-samples.csv"),
        }
        if (directory / "telemetry.json").is_file():
            run["telemetry"] = load(directory / "telemetry.json")
        sr = next(directory.rglob("_sr_batch/result.json"), None)
        if sr is not None:
            run["sr"] = load(sr)
        run["maintained_original_homr"] = [
            load(p)["timings_sec"] for p in sorted(directory.rglob("worker_result.json"))
        ]
        proc, association = select_process_samples(directory, args.legacy_multi_proc)
        run["process_sample_association"] = association
        if proc is not None:
            run["process_sample_path"] = str(proc.resolve())
            run["process_observations"] = proc_summary(proc)
        component = directory / "component/result.json"
        if component.is_file():
            run["component"] = load(component)
        summary["runs"][directory.name] = run
    for label in ("single-off-cold", "single-on-warm", "single-off-eager"):
        target = issue / "runs" / label / "pipeline"
        if target.is_dir():
            summary.setdefault("single_page_semantics_vs_compiled_warm", {})[label] = (
                source_semantics(root, issue / "runs/single-off-warm/pipeline", target)
            )
    if (issue / "runs/source-parallel-two/component/result.json").is_file():
        summary["parallel_source_semantics"] = parallel_semantics(root, issue)
    for label in ("current-homr-cpu-profile", "current-homr-wall"):
        result_path = issue / "runs" / label / "component/homr-result.json"
        if result_path.is_file():
            baseline = load(
                next((issue / "runs/single-off-warm/pipeline").rglob("current_homr_result.json"))
            )
            summary.setdefault("retained_input_homr_semantics", {})[label] = compare_bundle(
                root,
                baseline,
                load(result_path),
                "current_sr_detection",
                ("staff_mask", "connector_symbols", "connector_brace_dot"),
            )
    reference_omr = load(
        next((issue / "runs/single-off-warm/pipeline").rglob("omr_sr/page_013/predictions.json"))
    )
    for label in ("omr-dln-cpu-profile", "omr-dln-wall", "omr-dln-wall-device"):
        predictions = issue / "runs" / label / "component/omr/page_013/predictions.json"
        if predictions.is_file():
            summary.setdefault("retained_input_omr_semantics", {})[label] = reference_omr == load(
                predictions
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    for label, run in summary["runs"].items():
        print(label, run["result"]["status"], round(run["result"]["docker_e2e_wall_seconds"], 3))


if __name__ == "__main__":
    main()
