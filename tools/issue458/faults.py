"""Real pipeline failure/publication checks using retained SR, without inference."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
OUT = ROOT / "logs/issue458/faults"


def child(case):
    import yaml

    from src.pipeline.detection import profile_sources_batch_sr as batch
    from src.pipeline.detection.maintained_profile_hybrid import (
        BatchSRVerifiedProfileHybridDetector as Detector,
    )
    from src.pipeline.main import run_pipeline

    reference = ROOT / "logs/issue458/runs/warm-b1"
    payload = json.loads(
        (
            reference / "pipeline/hybrid_output/pipeline/current_support/_sr_batch/result.json"
        ).read_text()
    )
    by_image = {Path(r["image"]).resolve(): r for r in payload["outputs"]}
    Detector._batch_sr_worker = lambda self, **kw: (by_image, ["retained-SR-fault-only"], payload)
    batch.available_resources = lambda: (16, 8, "NVIDIA GeForce RTX 4060")
    out = OUT / case
    out.mkdir(parents=True, exist_ok=False)
    script = out / "source_fault.py"
    script.write_text("""import os,sys,time,signal,json,argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--request');p.add_argument('--result');a=p.parse_args()
r=json.loads(Path(a.request).read_text())
with open(os.environ['FAULT_PIDS'],'a') as f:f.write(str(os.getpid())+'\\n')
case=os.environ['FAULT_CASE']
if case=='timeout':time.sleep(60)
if case=='oom':
    Path('/proc/self/oom_score_adj').write_text('1000')
    data=bytearray(3*2**30)
if case=='kill':os.kill(os.getpid(),signal.SIGKILL)
if case=='nonzero':sys.exit(7)
if case=='wrong-image':Path(a.result).write_text(json.dumps({'status':'completed','image':'wrong','memory_boundary':'top_level_python_per_page','sr_execution_scope':'dedicated_sr_batch_process','historical_detector_artifact_runtime_input':False,'homr_neural_inference_count':2,'x4_homr_neural_inference_count':1}))
""")
    os.environ["FAULT_PIDS"] = str(out / "pids")
    os.environ["FAULT_CASE"] = case
    os.environ["PYTHONPATH"] = str(out) + os.pathsep + os.environ.get("PYTHONPATH", "")
    Detector.source_worker_module = "source_fault"
    config = yaml.safe_load((reference / "config.yaml").read_text())
    config["run"] = {"run_id": "pipeline", "output_root": str(out)}
    config["detection"]["hybrid_output_root"] = str(out / "hybrid_output")
    config["detection"]["source_concurrency"].update(
        workers=2, timeout_sec=30 if case == "oom" else 1
    )
    path = out / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    run_pipeline(path, telemetry_summary_path=out / "telemetry.json")


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--case")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    OUT = args.output.resolve()
    if args.case:
        child(args.case)
        return
    OUT.mkdir(parents=True, exist_ok=False)
    rows = []

    def oom_kills():
        return int(
            dict(
                line.split()
                for line in Path("/sys/fs/cgroup/memory.events").read_text().splitlines()
            )["oom_kill"]
        )

    for case in ("nonzero", "missing", "wrong-image", "kill", "timeout", "oom"):
        before_oom = oom_kills()
        with (OUT / (case + ".log")).open("w") as stream:
            process = subprocess.run(
                [sys.executable, __file__, "--case", case, "--output", str(OUT)],
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=45,
            )
        directory = OUT / case
        pids = [int(p) for p in (directory / "pids").read_text().splitlines()]
        telemetry = json.loads((directory / "telemetry.json").read_text())
        text = (OUT / (case + ".log")).read_text()
        expected = {
            "nonzero": "worker failed (7)",
            "missing": "FileNotFoundError",
            "wrong-image": "Wrong source result identity",
            "kill": "worker failed (-9)",
            "timeout": "TimeoutError",
            "oom": "worker failed (-9)",
        }[case]
        checks = {
            "expected_fault": expected in text,
            "actual_oom_kill_if_requested": case != "oom" or oom_kills() > before_oom,
            "failed": process.returncode != 0,
            "children_reaped": bool(pids) and all(not Path(f"/proc/{p}").exists() for p in pids),
            "no_final_numbering": not list(directory.rglob("numbering_final.json")),
            "failure_diagnostic": bool(list(directory.rglob("failure.json"))),
            "detection_aborted": any(
                s["stage_id"] == "score_detection" and s["state"] != "completed"
                for s in telemetry["stage_spans"]
            ),
        }
        rows.append(
            {
                "case": case,
                "checks": checks,
                "exit_code": process.returncode,
                "oom_kills_before": before_oom,
                "oom_kills_after": oom_kills(),
            }
        )
    (OUT / "result.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows))
    assert all(all(r["checks"].values()) for r in rows)


if __name__ == "__main__":
    main()
