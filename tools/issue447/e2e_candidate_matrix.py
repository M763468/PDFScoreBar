"""Serial, predeclared E2E matrix; never launches full68 or edits production."""

from __future__ import annotations

import hashlib
import json
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

from tools.issue447.analyze import gpu_summary, proc_summary
from tools.issue447.deepening_analyze import pipeline_checks

ROOT = Path(__file__).resolve().parents[2]
ISSUE = ROOT / "logs/issue447"
OUT = ISSUE / "e2e-candidates"
IMAGE = "sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a"
MODES = {
    "B": [],
    "P": ["--source-workers", "2"],
    "O": ["--source-workers", "1", "--omr-reuse"],
    "C": ["--source-workers", "2", "--omr-reuse"],
}


def inventory(path):
    rows = [
        (str(p.relative_to(path)), p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in sorted(path.rglob("*"))
        if p.is_file()
    ]
    return {
        "files": len(rows),
        "bytes": sum(r[1] for r in rows),
        "digest": hashlib.sha256(json.dumps(rows).encode()).hexdigest(),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "validation").mkdir(parents=True, exist_ok=True)
    seed = OUT / "warm-seed"
    shutil.copytree(ISSUE / "cache", seed)
    seed_inventory = inventory(seed)
    (OUT / "seed-inventory.json").write_text(json.dumps(seed_inventory, indent=2) + "\n")
    rows, counts = [], {}
    reference = ISSUE / "runs/multi-off-warm/pipeline"
    with (OUT / "matrix.jsonl").open("x", buffering=1) as journal:

        def record(payload):
            journal.write(json.dumps(payload) + "\n")
            print(json.dumps(payload), flush=True)

        def run(mode, temperature):
            nonlocal reference
            key = (mode, temperature)
            counts[key] = counts.get(key, 0) + 1
            label = f"e2ec-{temperature}-{mode.lower()}-{counts[key]}"
            directory = ISSUE / "runs" / label
            cache = OUT / "caches" / label
            if temperature == "warm":
                shutil.copytree(seed, cache)
                assert inventory(cache) == seed_inventory
            else:
                cache.mkdir(parents=True)
            before = inventory(cache)
            command = [
                sys.executable,
                "tools/issue447/run_experiment.py",
                "--label",
                label,
                "--scope",
                "multi",
                "--image",
                IMAGE,
                "--compile-cache",
                str(cache),
                *MODES[mode],
            ]
            record(
                {
                    "event": "start",
                    "label": label,
                    "mode": mode,
                    "temperature": temperature,
                    "epoch": time.time(),
                    "command": command,
                    "cache_before": before,
                }
            )
            code = subprocess.run(command, cwd=ROOT).returncode
            record({"event": "executed", "label": label, "exit_code": code, "epoch": time.time()})
            if code:
                raise RuntimeError(f"{label} failed; no rerun/fallback or silent exclusion")
            checks = pipeline_checks(ROOT, reference, directory / "pipeline")
            (directory / "semantic-check.json").write_text(json.dumps(checks, indent=2) + "\n")
            resource = proc_summary(directory / "proc-samples.jsonl")
            gpu = gpu_summary(directory / "gpu-samples.csv")
            bounded = (
                resource["cgroup_memory_peak_bytes"] <= 16 * 1024**3
                and gpu["memory.used [MiB]"]["peak"] <= 7 * 1024
            )
            row = {
                "label": label,
                "mode": mode,
                "temperature": temperature,
                "result": json.loads((directory / "result.json").read_text()),
                "all_equal": checks["all_equal"],
                "resource_screen_passed": bounded,
                "resources": {
                    k: v for k, v in resource.items() if k != "process_residency_not_additive"
                },
                "gpu": gpu,
                "cache_before": before,
                "cache_after": inventory(cache),
            }
            rows.append(row)
            record({"event": "result", **row})
            (OUT / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
            if not checks["all_equal"] or not bounded:
                raise RuntimeError(
                    f"{label} failed semantic/resource gate; retained, not adoption-ready"
                )
            if len(rows) == 1:
                reference = directory / "pipeline"

        for mode in ("B", "P", "O", "O", "P", "B"):
            run(mode, "warm")
        # Fixed independent cold compiler caches; all three inputs remain unchanged.
        for mode in ("B", "P", "O"):
            run(mode, "cold")
        warm = {
            m: [
                r["result"]["docker_e2e_wall_seconds"]
                for r in rows
                if r["temperature"] == "warm" and r["mode"] == m
            ]
            for m in ("B", "P", "O")
        }
        # O/P order in the second reversed block is reversed back by per-mode occurrence.
        advance = all(
            statistics.median(warm[m]) <= 0.97 * statistics.median(warm["B"])
            and all(c < b for c, b in zip(warm[m], warm["B"]))
            for m in ("P", "O")
        )
        record(
            {
                "event": "advance_speed_gate",
                "advance": advance,
                "warm_seconds": warm,
                "note": "Phase C gates are checked before combined execution by the replay command below",
            }
        )
        command = [
            "docker",
            "run",
            "--rm",
            "--user",
            "1000:1001",
            "-v",
            f"{ROOT}:/workspace",
            "-v",
            f"{ROOT.parent.parent}/data/evaluation2/images:/workspace/data/evaluation2/images:ro",
            "-w",
            "/workspace",
            "-e",
            "PYTHONPATH=/workspace",
            "-e",
            "HOME=/tmp",
            IMAGE,
            "/opt/venv_pipeline/bin/python",
            "tools/issue447/e2e_semantic_replay.py",
            "--labels",
            *[r["label"] for r in rows],
            "--output",
            "logs/issue447/e2e-candidates/replay-single",
        ]
        record({"event": "replay_start", "command": command})
        with (OUT / "validation/replay-single.log").open("w") as stream:
            subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True)
        if advance:
            for temperature in ("warm", "warm", "cold"):
                run("C", temperature)
            command[command.index("--labels") + 1 :] = [
                rows[0]["label"],
                *[r["label"] for r in rows if r["mode"] == "C"],
                "--output",
                "logs/issue447/e2e-candidates/replay-combined",
            ]
            with (OUT / "validation/replay-combined.log").open("w") as stream:
                subprocess.run(
                    command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True
                )
        record({"event": "complete", "epoch": time.time(), "combined_executed": advance})


if __name__ == "__main__":
    main()
