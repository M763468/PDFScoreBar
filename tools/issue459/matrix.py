"""Finish fixed performance cells after the root warm primary screen.

Stop on the first failed required gate and retain all prior cells. This cannot
activate production and never retries or excludes an observation.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-protocol", action="store_true")
    parser.add_argument("--image", required=True)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if not args.label.replace("-", "").replace("_", "").isalnum():
        parser.error("invalid label")
    root = Path(__file__).resolve().parents[2]
    primary = json.loads(args.primary.read_text())
    protocol = "job-v1" if args.job_protocol else "issue447-poc"
    if primary.get("candidate_protocol", "issue447-poc") != protocol:
        raise ValueError("primary belongs to another candidate protocol")
    if primary["primary_gate"] != "passed":
        raise RuntimeError("primary screen failed; no adoption")
    out = root / "logs/issue459/matrices" / args.label
    out.mkdir(parents=True, exist_ok=False)
    cells = [
        (0, "multi", "cold"),
        (0, "single", "warm"),
        (0, "single", "cold"),
        (1000, "multi", "warm"),
        (1000, "multi", "cold"),
        (1000, "single", "warm"),
        (1000, "single", "cold"),
    ]
    results = []
    for uid, scope, state in cells:
        label = f"{args.label}-{uid}-{scope}-{state}"
        command = [
            sys.executable,
            "-m",
            "tools.issue459.screen",
            "--image",
            args.image,
            "--seed",
            str(args.seed.resolve()),
            "--label",
            label,
            "--uid",
            str(uid),
            "--scope",
            scope,
            "--compiler-state",
            state,
        ]
        if args.job_protocol:
            command += ["--job-protocol"]
        with (out / "journal.jsonl").open("a") as journal:
            journal.write(json.dumps({"label": label, "command": command}) + "\n")
        subprocess.run(command, cwd=root, check=True)
        summary = json.loads((root / "logs/issue459/screens" / label / "summary.json").read_text())
        results.append(summary)
        payload = {
            "cells": results,
            "adoption": "pending_quality_and_recovery_gates",
            "remaining_cells": len(cells) - len(results),
        }
        if summary["primary_gate"] != "passed":
            payload["adoption"] = "rejected_required_performance_gate"
        (out / "results.json").write_text(json.dumps(payload, indent=2) + "\n")
        if payload["adoption"].startswith("rejected"):
            return


if __name__ == "__main__":
    main()
