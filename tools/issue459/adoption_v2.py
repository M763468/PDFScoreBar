"""Issue #459 adoption-v2 runner; contract: docs/performance/issue459/adoption-v2.md.

Research only. It never activates production reuse, retries, or excludes observations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V2 = "logs/issue459/v2"
SEED = "logs/issue459/cache/root-multi-cold-b2"
PRIMARY_BLOCKS = ("v2-primary-2", "v2-primary-3", "v2-primary-4")
REFERENCE = "logs/issue459/runs/v2-primary-2-1-b"
CELLS = (
    (0, "multi", "cold"),
    (0, "single", "warm"),
    (0, "single", "cold"),
    (1000, "multi", "warm"),
    (1000, "multi", "cold"),
    (1000, "single", "warm"),
    (1000, "single", "cold"),
)
MIXED_SOURCES = (
    "Shostakovich-Festival_Overture_Va",
    "Sibelius-Violin_Concerto-Viola",
    "Va_Prokofiev_Symphony1",
    "Va__Prokofiev_Symphony5",
)


def cell_label(uid, scope, state):
    return f"v2-cell-{uid}-{scope}-{state}"


# -- pure gate evaluation ------------------------------------------------------


def improvement(baseline, candidate):
    return 100 * (1 - statistics.median(candidate) / statistics.median(baseline))


def performance_gates(blocks):
    """blocks: [(baseline_seconds, candidate_seconds)] for the v2 primary ABBA blocks."""
    if len(blocks) != len(PRIMARY_BLOCKS) or any(len(b) != 2 or len(o) != 2 for b, o in blocks):
        raise ValueError("three complete ABBA blocks are required")
    per_block = [improvement(b, o) for b, o in blocks]
    baseline = [v for b, _ in blocks for v in b]
    candidate = [v for _, o in blocks for v in o]
    pooled = improvement(baseline, candidate)
    noise = 100 * (max(baseline) - min(baseline)) / statistics.median(baseline)
    return {
        "block_improvement_percent": per_block,
        "pooled_improvement_percent": pooled,
        "baseline_noise_percent": noise,
        "baseline_median": statistics.median(baseline),
        "candidate_median": statistics.median(candidate),
        "seconds_saved_per_job": statistics.median(baseline) - statistics.median(candidate),
        "P1": "passed" if all(v > 0 for v in per_block) else "failed",
        "P2": "passed" if pooled >= noise / 2 else "failed",
        "P3": "passed" if pooled >= 1.5 else "failed",
    }


def memory_gate(baseline, candidate):
    """M1: O RAM peak <= 1.10 x B and O device VRAM peak <= B + 512 MiB."""
    ram = candidate["ram_peak_bytes"] <= 1.10 * baseline["ram_peak_bytes"]
    vram = candidate["vram_peak_mib"] <= baseline["vram_peak_mib"] + 512
    return "passed" if ram and vram else "failed"


def decide(gates):
    """Every gate must pass; any failure wins over missing evidence."""
    values = list(gates.values())
    if any(v == "failed" for v in values):
        return "not_eligible"
    if all(v == "passed" for v in values):
        return "eligible_for_production_integration_proposal"
    return "undecided"


# -- execution helpers ----------------------------------------------------------


def launch(label, scope, *, candidate, cache, uid=0, extra=(), timeout=5400):
    command = [
        sys.executable,
        str(ROOT / "tools/issue447/run_experiment.py"),
        "--issue-id",
        "459",
        "--uid",
        str(uid),
        "--gid",
        str(uid),
        "--home",
        "/root" if uid == 0 else "/tmp",
        "--image",
        IMAGE[0],
        "--label",
        label,
        "--scope",
        scope,
        "--compile-cache",
        str(cache),
        "--timeout",
        str(timeout),
        *extra,
    ]
    if candidate:
        command += ["--source-workers", "1", "--omr-reuse", "--job-protocol"]
    return command


IMAGE = [None]


def warm_cache(out, label):
    cache = out / "cache" / label
    shutil.copytree(ROOT / SEED, cache)
    return cache


def run_dir(label):
    return ROOT / "logs/issue459/runs" / label


def run_checks(label, reference):
    from tools.issue447.analyze import gpu_summary, proc_summary
    from tools.issue447.deepening_analyze import pipeline_checks

    directory = run_dir(label)
    result = json.loads((directory / "result.json").read_text())
    checks = None
    if result["status"] == "completed":
        checks = pipeline_checks(ROOT, reference, directory / "pipeline")
    payload = {
        "result": result,
        "semantic": checks,
        "resources": proc_summary(directory / "proc-samples.jsonl"),
        "gpu": gpu_summary(directory / "gpu-samples.csv"),
    }
    (directory / "v2-checks.json").write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def journal(out, record):
    with (out / "journal.jsonl").open("a") as stream:
        stream.write(json.dumps(record) + "\n")


def prepare_mixed():
    """Interleave pages from four scores with four distinct page sizes (copies, hashed)."""
    from PIL import Image

    manager = Path(
        subprocess.check_output(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=ROOT, text=True
        ).strip()
    ).parent
    out = ROOT / "logs/issue459/inputs/mixed-shape-v2"
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    for index in (1, 2):
        for score in MIXED_SOURCES:
            source = sorted((manager / "data/evaluation2/images" / score).glob("page_*.png"))[index]
            target = out / f"page_{len(rows) + 1:03d}.png"
            shutil.copyfile(source, target)
            rows.append(
                {
                    "page": target.name,
                    "source": str(source.relative_to(manager)),
                    "size": Image.open(target).size,
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                }
            )
    (ROOT / "logs/issue459/inputs/mixed-shape-v2.json").write_text(
        json.dumps(rows, indent=2) + "\n"
    )


def cells(args):
    out = ROOT / V2 / "cells"
    out.mkdir(parents=True, exist_ok=True)
    for uid, scope, state in CELLS:
        label = cell_label(uid, scope, state)
        command = [
            sys.executable,
            "-m",
            "tools.issue459.screen",
            "--job-protocol",
            "--image",
            IMAGE[0],
            "--seed",
            str(ROOT / SEED),
            "--label",
            label,
            "--uid",
            str(uid),
            "--scope",
            scope,
            "--compiler-state",
            state,
        ]
        journal(out, {"label": label, "command": command})
        code = subprocess.run(command, cwd=ROOT).returncode
        journal(out, {"label": label, "exit_code": code})


def pair(args):
    out = ROOT / V2 / f"pair-{args.scope}"
    out.mkdir(parents=True, exist_ok=False)
    labels = {"b": f"v2-{args.scope}-b", "o": f"v2-{args.scope}-o"}
    for arm, label in labels.items():
        command = launch(label, args.scope, candidate=arm == "o", cache=warm_cache(out, label))
        journal(out, {"label": label, "command": command})
        code = subprocess.run(command, cwd=ROOT).returncode
        journal(out, {"label": label, "exit_code": code})
    reference = run_dir(labels["b"]) / "pipeline"
    summary = {arm: run_checks(label, reference) for arm, label in labels.items()}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


def _container(label):
    return "pdfscore-issue459-" + label


def _worker_running(name):
    top = subprocess.run(["docker", "top", name, "-eo", "pid,args"], capture_output=True, text=True)
    return top.returncode == 0 and "tools.issue459.job_worker" in top.stdout


def fault(args):
    out = ROOT / V2 / f"fault-{args.kind}"
    out.mkdir(parents=True, exist_ok=False)
    label = f"v2-fault-{args.kind}"
    name = _container(label)
    command = launch(label, "multi", candidate=True, cache=warm_cache(out, label), timeout=1800)
    journal(out, {"label": label, "command": command})
    events = []

    def watch():
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline and process.poll() is None:
            if _worker_running(name):
                events.append({"event": "worker_observed", "monotonic": time.monotonic()})
                time.sleep(args.delay)
                if args.kind == "kill":
                    action = ["docker", "kill", name]
                else:
                    action = ["docker", "update", "--memory", "256m", "--memory-swap", "256m", name]
                done = subprocess.run(action, capture_output=True, text=True)
                events.append(
                    {
                        "event": "fault_injected",
                        "command": action,
                        "exit_code": done.returncode,
                        "stdout": done.stdout,
                        "stderr": done.stderr,
                        "monotonic": time.monotonic(),
                    }
                )
                return
            time.sleep(0.5)

    process = subprocess.Popen(command, cwd=ROOT)
    watcher = threading.Thread(target=watch)
    watcher.start()
    code = process.wait()
    watcher.join()
    directory = run_dir(label)
    jobs = [
        p.parent for p in directory.rglob("request.json") if (p.parent / "command.json").exists()
    ]
    container_events = (directory / "container-events.jsonl").read_text()
    oom = any(
        json.loads(line).get("Action") == "oom"
        and json.loads(line).get("Actor", {}).get("Attributes", {}).get("name") == name
        for line in container_events.splitlines()
        if line.startswith("{")
    )
    survivors = subprocess.run(
        ["docker", "ps", "-q", "--filter", f"name=^{name}$"], capture_output=True, text=True
    ).stdout.strip()
    fault_result = {
        "launcher_exit_code": code,
        "events": events,
        "job_directories": [str(p.relative_to(ROOT)) for p in jobs],
        "completed_json": [str(p) for j in jobs for p in [j / "completed.json"] if p.exists()],
        "diagnostics_retained": bool(jobs)
        and all((j / "request.json").exists() and (j / "worker.log").exists() for j in jobs),
        "downstream_manifest": (directory / "pipeline/manifest.json").exists(),
        "oom_event": oom,
        "surviving_container": bool(survivors),
    }
    injected = any(e["event"] == "fault_injected" and e["exit_code"] == 0 for e in events)
    passed = (
        injected
        and code != 0
        and not fault_result["completed_json"]
        and fault_result["diagnostics_retained"]
        and not fault_result["downstream_manifest"]
        and not fault_result["surviving_container"]
        and (args.kind == "kill" or oom)
    )
    fault_result["fault_gate"] = "passed" if passed else "failed"
    recovery = f"v2-recovery-{args.kind}"
    command = launch(recovery, "multi", candidate=True, cache=warm_cache(out, recovery))
    journal(out, {"label": recovery, "command": command})
    subprocess.run(command, cwd=ROOT)
    checks = run_checks(recovery, ROOT / REFERENCE / "pipeline")
    fault_result["recovery_gate"] = (
        "passed"
        if checks["result"]["status"] == "completed" and checks["semantic"]["all_equal"]
        else "failed"
    )
    (out / "summary.json").write_text(json.dumps(fault_result, indent=2) + "\n")


def replay(args):
    from src.pipeline.steps.barlines import normalize_barlines
    from tools.issue447 import e2e_correction_replay as correction
    from tools.issue447.analyze import local_path

    out = ROOT / V2 / "correction-replay"
    out.mkdir(parents=True, exist_ok=False)
    labels = [f"{PRIMARY_BLOCKS[0]}-1-b", f"{PRIMARY_BLOCKS[0]}-2-o"]
    manifest = json.loads((run_dir(labels[0]) / "pipeline/manifest.json").read_text())
    box = normalize_barlines(
        json.loads(local_path(ROOT, manifest["pages"][0]["barlines_json"]).read_text())
    )[0]
    overrides = {
        "barline_overrides": [
            {"page": 0, "op": "remove", "bbox": box},
            {"page": 0, "op": "add", "bbox": [box[0] + 2, box[1], box[2] + 2, box[3]]},
        ]
    }
    (out / "fixed-overrides.json").write_text(json.dumps(overrides, indent=2) + "\n")
    keys = ("corrected_boxes", "stats", "final_pages", "base_pages")
    results = {
        label: correction.run(
            label, out / label, overrides, source_runs=ROOT / "logs/issue459/runs"
        )
        for label in labels
    }
    compared = [{k: r[k] for k in keys} for r in results.values()]
    summary = {
        "labels": labels,
        "checks": {label: r["checks"] for label, r in results.items()},
        "b_o_equal": compared[0] == compared[1],
    }
    summary["Q2"] = (
        "passed"
        if summary["b_o_equal"] and all(all(r["checks"].values()) for r in results.values())
        else "failed"
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


def _load(path):
    path = ROOT / path
    return json.loads(path.read_text()) if path.exists() else None


def _peaks(checks):
    return {
        "ram_peak_bytes": checks["resources"]["cgroup_memory_peak_bytes"],
        "vram_peak_mib": checks["gpu"]["memory.used [MiB]"]["peak"],
    }


OMR_ENTRYPOINTS = ("src.pipeline.detection.omr_dln_worker", "tools.issue459.job_worker")


def omr_process_count(resources):
    """Distinct sampled (pid) identities running a production or job OMR entrypoint."""
    return len(
        {
            p["pid"]
            for p in resources["process_residency_not_additive"]
            if any(f"-m {entry}" in p["command"] for entry in OMR_ENTRYPOINTS)
        }
    )


def evaluate(args):
    gates = {}
    report = {}
    summaries = [_load(f"logs/issue459/screens/{label}/summary.json") for label in PRIMARY_BLOCKS]
    if all(summaries):
        perf = performance_gates(
            [(s["baseline_seconds"], s["candidate_seconds"]) for s in summaries]
        )
        report["performance"] = perf
        gates.update({k: perf[k] for k in ("P1", "P2", "P3")})
    else:
        gates.update({k: "not_run" for k in ("P1", "P2", "P3")})
    cell_summaries = {
        cell_label(*c): _load(f"logs/issue459/screens/{cell_label(*c)}/summary.json") for c in CELLS
    }
    report["cells"] = cell_summaries
    if all(cell_summaries.values()):
        gates["R"] = (
            "passed"
            if all(s["primary_gate"] == "passed" for s in cell_summaries.values())
            else "failed"
        )
    else:
        failed = [
            label
            for label in cell_summaries
            if (ROOT / f"logs/issue459/screens/{label}/failed.json").exists()
        ]
        gates["R"] = "failed" if failed else "not_run"
    # Q1: every completed primary/cell screen enforces semantic equality before summary.
    gates["Q1"] = (
        "passed"
        if all(summaries) and all(cell_summaries.values())
        else ("failed" if gates["R"] == "failed" else "not_run")
    )
    replay_summary = _load(f"{V2}/correction-replay/summary.json")
    gates["Q2"] = replay_summary["Q2"] if replay_summary else "not_run"
    for gate, scope in (("L1", "long"), ("L2", "mixed")):
        pair_summary = _load(f"{V2}/pair-{scope}/summary.json")
        report[f"pair_{scope}"] = pair_summary
        if not pair_summary:
            gates[gate] = gates[f"M1_{scope}"] = "not_run"
            continue
        b, o = pair_summary["b"], pair_summary["o"]
        completed = all(x["result"]["status"] == "completed" for x in (b, o))
        workers = omr_process_count(o["resources"])
        report[f"pair_{scope}_omr_processes"] = {
            "b": omr_process_count(b["resources"]),
            "o": workers,
        }
        gates[gate] = (
            "passed"
            if completed
            and o["semantic"]["all_equal"]
            and b["semantic"]["all_equal"]
            and workers == 1
            else "failed"
        )
        gates[f"M1_{scope}"] = memory_gate(_peaks(b), _peaks(o)) if completed else "failed"
    for kind, gate in (("kill", "F1"), ("oom", "F2")):
        fault_summary = _load(f"{V2}/fault-{kind}/summary.json")
        report[f"fault_{kind}"] = fault_summary
        gates[gate] = fault_summary["fault_gate"] if fault_summary else "not_run"
        gates[f"F3_{kind}"] = fault_summary["recovery_gate"] if fault_summary else "not_run"
    report["gates"] = gates
    report["decision"] = decide(gates)
    out = ROOT / V2
    out.mkdir(parents=True, exist_ok=True)
    (out / "decision.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"gates": gates, "decision": report["decision"]}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=None)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("prepare-mixed")
    sub.add_parser("cells")
    pair_parser = sub.add_parser("pair")
    pair_parser.add_argument("--scope", choices=("long", "mixed"), required=True)
    fault_parser = sub.add_parser("fault")
    fault_parser.add_argument("--kind", choices=("kill", "oom"), required=True)
    fault_parser.add_argument("--delay", type=float, default=3.0)
    sub.add_parser("replay")
    sub.add_parser("evaluate")
    args = parser.parse_args()
    if args.action in ("cells", "pair", "fault"):
        if not args.image or not args.image.startswith("sha256:"):
            parser.error("--image sha256:<id> is required")
        IMAGE[0] = args.image
    {
        "prepare-mixed": lambda a: prepare_mixed(),
        "cells": cells,
        "pair": pair,
        "fault": fault,
        "replay": replay,
        "evaluate": evaluate,
    }[args.action](args)


if __name__ == "__main__":
    main()
