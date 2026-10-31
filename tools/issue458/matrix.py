"""Frozen serial production comparison. Run only after seed qualification."""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "logs/issue458"
IMAGE = "sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a"


def main():
    while not (OUT / "runs/warm-1a/result.json").exists():
        time.sleep(2)
    assert json.loads((OUT / "runs/warm-1a/result.json").read_text())["exit_code"] == 0
    seed = OUT / "seed"
    shutil.copytree(OUT / "caches/w1", seed)
    for label, workers, scope, warm in [
        ("warm-b1", 1, "multi", True),
        ("warm-p1", 2, "multi", True),
        ("warm-p2", 2, "multi", True),
        ("warm-b2", 1, "multi", True),
        ("cold-b1", 1, "multi", False),
        ("cold-p1", 2, "multi", False),
        ("single-b1", 1, "single", True),
        ("single-p1", 2, "single", True),
    ]:
        cache = OUT / "caches" / label
        if warm:
            shutil.copytree(seed, cache)
        command = [
            sys.executable,
            "tools/issue458/run_experiment.py",
            "--label",
            label,
            "--workers",
            str(workers),
            "--scope",
            scope,
            "--image",
            IMAGE,
            "--compile-cache",
            str(cache),
        ]
        subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
