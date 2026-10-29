"""CPU-only fault propagation through actual pipeline; retained SR, no performance score."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path.cwd()
OUT = ROOT / "logs/issue447/e2e-candidates/faults"


def child(case):
    from src.pipeline.detection.maintained_profile_hybrid import (
        BatchSRVerifiedProfileHybridDetector as Detector,
    )
    from src.pipeline.main import run_pipeline
    from tools.issue447 import omr_reuse_poc as reuse
    from tools.issue447.pipeline_poc import install_source_prefetch

    out = OUT / case
    out.mkdir(parents=True, exist_ok=False)
    reference = ROOT / "logs/issue447/runs/e2ec-warm-b-1"
    payload = json.loads(
        (
            reference / "pipeline/hybrid_output/pipeline/current_support/_sr_batch/result.json"
        ).read_text()
    )
    by_image = {Path(r["image"]).resolve(): r for r in payload["outputs"]}

    def retained_sr(self, *, support_output):
        print("fault-only retained SR handoff", case, flush=True)
        return by_image, ["fault-only-retained-sr-no-inference"], payload

    Detector._batch_sr_worker = retained_sr
    if case in ("omr-exit", "omr-missing-output"):
        original = reuse.build_manifest

        def failed(command, **kwargs):
            # A real short-lived child exits; this never loads models or consumes the GPU.
            return subprocess.run(
                [sys.executable, "-c", "import sys;sys.exit(7)" if case == "omr-exit" else "pass"],
                **kwargs,
            )

        def phase(images, outputs, directory):
            return original(images, outputs, directory, execute=failed)

        reuse.build_manifest = phase
        reuse.install()
    else:
        module = out / "issue447_fault_child.py"
        module.write_text(
            'import os,sys\nwith open(os.environ["ISSUE447_FAULT_PID_FILE"],"a") as f:f.write(str(os.getpid())+"\\n")\nprint("injected source child failure",os.getpid(),flush=True)\nsys.exit(7)\n'
        )
        os.environ["ISSUE447_FAULT_PID_FILE"] = str(out / "child-pids.txt")
        os.environ["PYTHONPATH"] = str(out) + os.pathsep + os.environ.get("PYTHONPATH", "")
        Detector.source_worker_module = "issue447_fault_child"
    install_source_prefetch(2)
    config = yaml.safe_load((reference / "config.yaml").read_text())
    config["run"] = {"run_id": "pipeline", "output_root": str(out)}
    config["detection"]["hybrid_output_root"] = str(out / "hybrid_output")
    path = out / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    run_pipeline(path, telemetry_summary_path=out / "telemetry.json")
    raise RuntimeError("fault should never succeed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case")
    args = parser.parse_args()
    if args.case:
        child(args.case)
        return
    OUT.mkdir(parents=True, exist_ok=False)
    results = []
    for case in ("omr-exit", "omr-missing-output", "source-exit"):
        log = OUT / (case + ".log")
        with log.open("w") as stream:
            process = subprocess.run(
                [sys.executable, __file__, "--case", case],
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=90,
            )
        directory = OUT / case
        telemetry = json.loads((directory / "telemetry.json").read_text())
        final = list(directory.rglob("numbering_final.json"))
        handoff = list(directory.rglob("completed.json"))
        pid_file = directory / "child-pids.txt"
        pids = [int(x) for x in pid_file.read_text().splitlines()] if pid_file.exists() else []
        text = log.read_text()
        expected = (
            "non-zero exit status 7" in text
            if case == "omr-exit"
            else "FileNotFoundError" in text and "predictions.json" in text
            if case == "omr-missing-output"
            else "injected source child failure" in text and "worker failed (7)" in text
        )
        checks = {
            "reached_retained_SR_boundary": "fault-only retained SR handoff" in text,
            "expected_fault_observed": expected,
            "source_children_exited": case != "source-exit"
            or bool(pids)
            and all(not Path("/proc").joinpath(str(pid)).exists() for pid in pids),
            "nonzero_exit": process.returncode != 0,
            "no_final_numbering": not final,
            "no_completed_omr_handoff": not handoff,
            "detection_not_completed": any(
                s["stage_id"] == "score_detection" and s["state"] != "completed"
                for s in telemetry["stage_spans"]
            ),
        }
        results.append(
            {
                "case": case,
                "exit_code": process.returncode,
                "checks": checks,
                "telemetry": telemetry,
                "log": str(log),
            }
        )
    (OUT / "result.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results))
    assert all(all(r["checks"].values()) for r in results)


if __name__ == "__main__":
    main()
