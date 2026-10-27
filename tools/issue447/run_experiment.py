"""Launch a frozen Issue #447 experiment without changing production configuration."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--image", required=True, help="Verified immutable sha256 image ID")
    parser.add_argument("--scope", choices=("single", "multi"), default="single")
    parser.add_argument("--compile-mode", choices=("production", "off"), default="production")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument(
        "--source-workers",
        type=int,
        choices=(1, 2),
        help="Experimental ordered source prefetch only; production source remains unchanged",
    )
    parser.add_argument(
        "--python-cache", type=Path, help="Optional private writable interpreter bytecode cache"
    )
    parser.add_argument(
        "--compile-cache",
        type=Path,
        help="Explicit cache directory; use a new empty directory for a cold reproduction",
    )
    parser.add_argument(
        "--component",
        choices=(
            "sr-screen",
            "homr-profile",
            "omr-profile",
            "source-parallel",
            "homr-wall",
            "omr-wall",
            "source-paired",
            "python-imports",
            "omr-serial",
            "omr-batch",
            "compiled-tiles1",
            "compiled-tiles2",
        ),
    )
    parser.add_argument("--timeout", type=float, default=1800)
    args = parser.parse_args()
    if args.component == "source-paired" and args.source_workers is None:
        parser.error("source-paired requires explicit --source-workers")
    if args.component not in (None, "source-paired") and args.source_workers is not None:
        parser.error("--source-workers applies only to E2E or source-paired")
    if not args.image.startswith("sha256:") or len(args.image) != 71:
        parser.error("--image must be an immutable full sha256 ID")
    if not args.label.replace("-", "").replace("_", "").isalnum():
        parser.error("label must contain only letters, digits, hyphens and underscores")
    root = Path(__file__).resolve().parents[2]
    manager = Path(
        subprocess.check_output(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=root, text=True
        ).strip()
    ).parent
    cache = Path(
        os.environ.get(
            "PDFSCOREBAR_MODEL_CACHE",
            str(
                Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
                / "pdfscorebar/models"
            ),
        )
    )
    issue = root / "logs/issue447"
    dest = issue / "runs" / args.label
    dest.mkdir(parents=True, exist_ok=False)
    rel = dest.relative_to(root)
    compile_cache = (args.compile_cache or (issue / "cache")).resolve()
    compile_cache.mkdir(parents=True, exist_ok=True)
    compile_cache_empty = not any(compile_cache.iterdir())
    config = yaml.safe_load((root / "configs/dense_full_pipeline.yaml").read_text())
    config["run"] = {"run_id": "pipeline", "output_root": str(rel)}
    config["inputs"]["pdf_to_images"] = {
        "output_dir": "data/evaluation2/images/Shostakovich-Sym5-Va",
        "image_glob": "page_013.png" if args.scope == "single" else "page_01[234].png",
    }
    config["detection"]["hybrid_output_root"] = str(rel / "pipeline/hybrid_output")
    if args.compile_mode == "off":
        config["detection"]["sr_compile_mode"] = None
    config_path = dest / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    omr_manifest = json.loads((root / "models/omr_dln/manifest.json").read_text())
    omr = omr_manifest["runtime_path"]
    name = "pdfscore-issue447-" + args.label
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--gpus",
        "all",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-v",
        f"{root}:/workspace",
        "-w",
        "/workspace",
        "-v",
        f"{manager}/data/evaluation2/images:/workspace/data/evaluation2/images:ro",
        "-v",
        f"{manager}/models/mmr/mmr_classifier_best.pth:/workspace/models/mmr/mmr_classifier_best.pth:ro",
        "-v",
        f"{cache}:/model-cache:ro",
        "-v",
        f"{compile_cache}:/compile-cache",
        "-v",
        f"{cache / omr_manifest['cache_path']}:{omr}:ro",
        "-e",
        "PDFSCOREBAR_MODEL_CACHE=/model-cache",
        "-e",
        "HOME=/tmp",
        "-e",
        "TORCHINDUCTOR_CACHE_DIR=/compile-cache/inductor",
        "-e",
        "TRITON_CACHE_DIR=/compile-cache/triton",
        "-e",
        "PYTHONPATH=/workspace",
        "-e",
        f"OMR_DLN_MODEL_PATH={omr}",
    ]
    if args.component in {"source-parallel", "source-serial"} or args.source_workers is not None:
        command += ["--memory", "16g"]
    if args.python_cache is not None:
        args.python_cache = args.python_cache.resolve()
        args.python_cache.mkdir(parents=True, exist_ok=True)
        command += [
            "-v",
            f"{args.python_cache}:/python-cache",
            "-e",
            "PYTHONPYCACHEPREFIX=/python-cache",
        ]
    if args.source_workers is not None:
        command += [
            "-e",
            f"ISSUE447_SOURCE_WORKERS={args.source_workers}",
            "-e",
            f"ISSUE447_SOURCE_EVENTS=/workspace/{rel}/source-schedule.jsonl",
        ]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    command += ["-e", f"PDFSCORE_HOST_SOURCE_COMMIT={commit}"]
    if args.trace:
        command += [
            "-e",
            f"PDFSCORE_PERF_TRACE_DIR=/workspace/{rel}/trace",
            "-e",
            f"PDFSCORE_PERF_TRACE_RUN={args.label}",
        ]
    command += [args.image, "/opt/venv_pipeline/bin/python"]
    if args.component == "source-paired":
        command += [
            "tools/issue447/pipeline_poc.py",
            "--source-component",
            "--workers",
            str(args.source_workers),
            "--output",
            str(rel / "component"),
        ]
    elif args.component in {
        "python-imports",
        "omr-serial",
        "omr-batch",
        "compiled-tiles1",
        "compiled-tiles2",
    }:
        command += [
            "tools/issue447/deepening_components.py",
            "--kind",
            args.component,
            "--output",
            str(rel / "component"),
        ]
    elif args.component:
        command += [
            "tools/issue447/component_poc.py",
            "--kind",
            args.component,
            "--output",
            str(rel / "component"),
            "--config",
            str(rel / "config.yaml"),
        ]
    else:
        command += [
            "tools/issue447/pipeline_poc.py"
            if args.source_workers is not None
            else "src/pipeline/main.py",
            "--config",
            str(rel / "config.yaml"),
            "--telemetry-summary",
            str(rel / "telemetry.json"),
        ]
        if args.trace:
            command += ["--sample-resources"]
    gpu = subprocess.check_output(
        ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv"],
        text=True,
    )
    (dest / "gpu-before.csv").write_text(gpu)
    if len(gpu.strip().splitlines()) > 1:
        raise RuntimeError("GPU compute process present; refusing benchmark")
    (dest / "containers-before.json").write_text(
        subprocess.check_output(["docker", "ps", "--format", "{{json .}}"], text=True)
    )
    provenance = {
        "command": command,
        "cwd": str(root),
        "source_commit": commit,
        "source_diff": subprocess.check_output(["git", "diff", "HEAD"], cwd=root, text=True),
        "image_id": args.image,
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "experiment": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "compile_cache_empty_at_start": compile_cache_empty,
        "script_sha256": {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((root / "tools/issue447").glob("*.py"))
        },
        "cache_state": "fresh container/process; persistent Issue-local compile cache; OS cache not flushed",
    }
    (dest / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    snapshots = dest / "script-snapshots"
    snapshots.mkdir()
    for script in sorted((root / "tools/issue447").glob("*.py")):
        (snapshots / script.name).write_bytes(script.read_bytes())
    streams = []
    monitors = []
    gpu_stream = (dest / "gpu-samples.csv").open("w")
    streams.append(gpu_stream)
    monitors.append(
        subprocess.Popen(
            [
                "nvidia-smi",
                "--query-gpu=timestamp,utilization.gpu,memory.used,power.draw",
                "--format=csv",
                "-l",
                "1",
            ],
            stdout=gpu_stream,
            stderr=subprocess.STDOUT,
        )
    )
    started = time.perf_counter()
    try:
        with (dest / "console.log").open("w") as stream:
            process = subprocess.Popen(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT)
            while process.poll() is None:
                try:
                    (dest / "container-inspect.json").write_text(
                        subprocess.check_output(
                            ["docker", "inspect", name], text=True, stderr=subprocess.DEVNULL
                        )
                    )
                    break
                except subprocess.CalledProcessError:
                    time.sleep(0.1)
            for filename, monitor in [
                ("docker-stats.jsonl", ["docker", "stats", "--format", "{{json .}}", name]),
                (
                    "container-events.jsonl",
                    ["docker", "events", "--filter", "type=container", "--format", "{{json .}}"],
                ),
                (
                    "proc-observer.log",
                    [
                        "docker",
                        "exec",
                        "--user",
                        f"{os.getuid()}:{os.getgid()}",
                        "-w",
                        "/workspace",
                        name,
                        "/opt/venv_pipeline/bin/python",
                        "tools/issue447/observe_processes.py",
                        "--output",
                        str(rel / "proc-samples.jsonl"),
                    ],
                ),
                (
                    "gpu-processes.csv",
                    [
                        "nvidia-smi",
                        "--query-compute-apps=pid,process_name,used_memory",
                        "--format=csv",
                        "-l",
                        "2",
                    ],
                ),
            ]:
                monitor_stream = (dest / filename).open("w")
                streams.append(monitor_stream)
                monitors.append(
                    subprocess.Popen(monitor, stdout=monitor_stream, stderr=subprocess.STDOUT)
                )
            timed_out = False
            try:
                code = process.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                subprocess.run(["docker", "stop", "--time", "10", name], check=False)
                code = process.wait()
            elapsed = time.perf_counter() - started
    finally:
        for monitor in monitors:
            if monitor.poll() is None:
                monitor.terminate()
            monitor.wait()
        for stream in streams:
            stream.close()
    result = {
        "status": "completed" if code == 0 else "failed",
        "exit_code": code,
        "docker_e2e_wall_seconds": elapsed,
        "timed_out": timed_out,
        "trace": "on" if args.trace else "off",
        "component": args.component,
        "scope": args.scope,
        "monitor_teardown_seconds": time.perf_counter() - started - elapsed,
    }
    (dest / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    (dest / "containers-after.json").write_text(
        subprocess.check_output(["docker", "ps", "--format", "{{json .}}"], text=True)
    )
    print(json.dumps(result), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
