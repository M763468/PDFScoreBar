"""Run semantic/fault/smoke gates after the serialized benchmark releases GPU."""

import json
import subprocess
import time

from tools.issue458.matrix import IMAGE, OUT, ROOT


def main():
    while not (OUT / "runs/single-p1/result.json").exists():
        time.sleep(2)
    manager = ROOT.parents[1]
    base = [
        "docker",
        "run",
        "--rm",
        "--user",
        "1000:1001",
        "-v",
        f"{ROOT}:/workspace",
        "-v",
        f"{manager}/data/evaluation2:/workspace/data/evaluation2:ro",
        "-e",
        "PYTHONPATH=/workspace",
        "-e",
        "HOME=/tmp",
        "-w",
        "/workspace",
    ]
    commands = [
        (
            "semantic",
            base + [IMAGE, "/opt/venv_pipeline/bin/python", "tools/issue458/summarize.py"],
        ),
        (
            "faults",
            base
            + [
                "--memory",
                "2g",
                "--memory-swap",
                "2g",
                IMAGE,
                "/opt/venv_pipeline/bin/python",
                "tools/issue458/faults.py",
            ],
        ),
        (
            "smoke",
            [
                "make",
                "verify-gpu-smoke",
                f"DOCKER_IMAGE={IMAGE}",
                f"DOCKER_EXTRA_ARGS=-v {manager}/data/evaluation2:/workspace/data/evaluation2:ro -v {manager}/models/mmr/mmr_classifier_best.pth:/workspace/models/mmr/mmr_classifier_best.pth:ro",
            ],
        ),
    ]
    rows = []
    for name, command in commands:
        with (OUT / "validation" / f"{name}.log").open("w") as stream:
            process = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        rows.append(dict(check=name, command=command, exit_code=process.returncode))
        (OUT / "validation/post-results.json").write_text(json.dumps(rows, indent=2) + "\n")
        print(json.dumps(rows[-1]), flush=True)


if __name__ == "__main__":
    main()
