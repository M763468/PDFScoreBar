"""Root deployment primary-gate screen; never enables production reuse."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import statistics
import subprocess
import sys
from pathlib import Path


def verdict(baseline, candidate, minimum_improvement=3):
    """A screen pass only permits further validation; it is not adoption."""
    if len(baseline) != 2 or len(candidate) != 2:
        raise ValueError("two completed observations per arm are required")
    if any(not 0 < value < float("inf") for value in baseline + candidate):
        raise ValueError("invalid wall time")
    improvement = 100 * (1 - statistics.median(candidate) / statistics.median(baseline))
    return {
        "baseline_seconds": baseline,
        "candidate_seconds": candidate,
        "baseline_median": statistics.median(baseline),
        "candidate_median": statistics.median(candidate),
        "baseline_range": [min(baseline), max(baseline)],
        "candidate_range": [min(candidate), max(candidate)],
        "improvement_percent": improvement,
        "primary_gate": "passed"
        if statistics.median(candidate)
        <= statistics.median(baseline) * (1 - minimum_improvement / 100)
        else "failed",
        "adoption": "not_authorized_by_screen",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uid", type=int, choices=(0, 1000), default=0)
    parser.add_argument("--scope", choices=("single", "multi"), default="multi")
    parser.add_argument("--compiler-state", choices=("cold", "warm"), default="warm")
    parser.add_argument("--image", required=True)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if not args.label.replace("-", "").replace("_", "").isalnum():
        parser.error("invalid label")
    root = Path(__file__).resolve().parents[2]
    seed = args.seed.resolve(strict=True)
    inventory = {
        str(p.relative_to(seed)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(seed.rglob("*"))
        if p.is_file()
    }
    if not inventory:
        parser.error("warm seed must not be empty")
    output = root / "logs/issue459/screens" / args.label
    output.mkdir(parents=True, exist_ok=False)
    (output / "seed.json").write_text(json.dumps(inventory, indent=2) + "\n")
    from tools.issue447.analyze import gpu_summary, proc_summary
    from tools.issue447.deepening_analyze import pipeline_checks

    reference = None
    values = {"b": [], "o": []}
    for index, arm in enumerate(("b", "o", "o", "b"), 1):
        label = f"{args.label}-{index}-{arm}"
        cache = output / "cache" / label
        if args.compiler_state == "warm":
            shutil.copytree(seed, cache)
        else:
            cache.mkdir(parents=True)
        command = [
            sys.executable,
            str(root / "tools/issue447/run_experiment.py"),
            "--issue-id",
            "459",
            "--uid",
            str(args.uid),
            "--gid",
            str(args.uid),
            "--home",
            "/root" if args.uid == 0 else "/tmp",
            "--image",
            args.image,
            "--label",
            label,
            "--scope",
            args.scope,
            "--compile-cache",
            str(cache),
        ]
        if arm == "o":
            command += ["--source-workers", "1", "--omr-reuse"]
        with (output / "journal.jsonl").open("a") as journal:
            journal.write(json.dumps({"event": "start", "label": label, "command": command}) + "\n")
        try:
            subprocess.run(command, cwd=root, check=True)
        except BaseException as exc:
            (output / "failed.json").write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "label": label,
                        "error": str(exc),
                        "adoption": "not_authorized_by_screen",
                    },
                    indent=2,
                )
                + "\n"
            )
            raise
        result = json.loads((root / "logs/issue459/runs" / label / "result.json").read_text())
        if result["status"] != "completed" or result["trace"] != "off" or result["timed_out"]:
            raise RuntimeError("incomplete or invalid screen run")
        directory = root / "logs/issue459/runs" / label
        reference = reference or directory / "pipeline"
        checks = pipeline_checks(root, reference, directory / "pipeline")
        resources = proc_summary(directory / "proc-samples.jsonl")
        gpu = gpu_summary(directory / "gpu-samples.csv")
        (directory / "screen-checks.json").write_text(
            json.dumps({"semantic": checks, "resources": resources, "gpu": gpu}, indent=2) + "\n"
        )
        if not checks["all_equal"]:
            raise RuntimeError("semantic screen failed; timing cannot justify adoption")
        values[arm].append(result["docker_e2e_wall_seconds"])
    primary = args.uid == 0 and args.scope == "multi" and args.compiler_state == "warm"
    summary = verdict(values["b"], values["o"], 3 if primary else -3)
    summary["cell"] = {
        "uid": args.uid,
        "scope": args.scope,
        "compiler_state": args.compiler_state,
        "minimum_improvement_percent": 3 if primary else -3,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
