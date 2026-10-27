"""Bounded remaining hypotheses for #447; no production changes or full evaluation."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")


def imports(output: Path) -> dict:
    code = """
import json,os,sys,time
from pathlib import Path
started=time.perf_counter()
import ultralytics
klass=ultralytics.YOLO
import torch
print(json.dumps({'import_seconds':time.perf_counter()-started,'class':klass.__module__+'.'+klass.__qualname__,
'torch':torch.__version__,'pycache_prefix':sys.pycache_prefix,'cuda_initialized':torch.cuda.is_initialized(),
'site_cache_writable':os.access(Path(torch.__file__).parent/'__pycache__',os.W_OK)}))
"""
    prefix = (output / "bytecode-cache").resolve()
    prefix.mkdir()
    rows = []
    for phase, variant in [
        ("first", "A"),
        ("first", "B"),
        ("warm", "A"),
        ("warm", "B"),
        ("warm", "B"),
        ("warm", "A"),
    ]:
        env = os.environ.copy()
        env.pop("PYTHONPYCACHEPREFIX", None)
        if variant == "B":
            env["PYTHONPYCACHEPREFIX"] = str(prefix)
        started = time.perf_counter()
        result = subprocess.run(
            [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
        )
        row = json.loads(result.stdout.strip().splitlines()[-1])
        row.update(
            {
                "phase": phase,
                "variant": variant,
                "process_wall_seconds": time.perf_counter() - started,
            }
        )
        rows.append(row)
        (output / "partial.json").write_text(json.dumps(rows, indent=2) + "\n")
    identities = {(r["class"], r["torch"]) for r in rows}
    return {
        "status": "completed",
        "kind": "imports",
        "rows": rows,
        "class_identity_equal": len(identities) == 1,
        "cuda_never_initialized": not any(r["cuda_initialized"] for r in rows),
        "limits": "CPU-only import/process microbenchmark; prefix first-call cost separate; not E2E/model correctness acceptance",
    }


def omr(output: Path, batch: bool) -> dict:
    reference = Path("logs/issue447/runs/multi-off-warm/pipeline")
    sr = json.loads(next(reference.rglob("_sr_batch/result.json")).read_text())["outputs"]
    staged = output / "sr-inputs"
    staged.mkdir()
    images = []
    for item in sr:
        image = Path(item["image"])
        (staged / image.name).symlink_to(item["sr_image"])
        images.append(image)
    groups = [images] if batch else [[p] for p in images]
    commands = []
    started = time.perf_counter()
    for index, group in enumerate(groups):
        command = [
            sys.executable,
            "-m",
            "src.pipeline.detection.omr_dln_worker",
            "--images",
            *[str(p) for p in group],
            "--output-dir",
            str(output / "predictions"),
            "--pre-computed-sr",
            str(staged),
        ]
        commands.append(command)
        with (output / f"worker-{index}.log").open("w") as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
    elapsed = time.perf_counter() - started
    checks = {}
    for image in images:
        old = (
            reference
            / "hybrid_output/pipeline/current_support/Shostakovich-Sym5-Va"
            / image.stem
            / "artifacts/omr_sr"
            / image.stem
            / "predictions.json"
        )
        new = output / "predictions" / image.stem / "predictions.json"
        checks[image.stem] = json.loads(old.read_text()) == json.loads(new.read_text())
    return {
        "status": "completed",
        "kind": "omr-reuse",
        "batch": batch,
        "component_wall_seconds": elapsed,
        "commands": commands,
        "ordered_source_predictions_equal": checks,
        "limits": "one worker reusing model/predictor vs fresh worker per page, retained SR; source-only and not integrated E2E",
    }


def compiled_tiles(output: Path, batch_size: int) -> dict:
    import cv2
    import numpy as np

    from src.pipeline.detection.current_sr_runtime import CurrentX4SRRuntime
    from tools.issue447.component_poc import pixel_difference

    image = cv2.imread("data/evaluation2/images/Shostakovich-Sym5-Va/page_013.png")
    if image is None:
        raise FileNotFoundError("fixed original page")
    initialized = time.perf_counter()
    runtime = CurrentX4SRRuntime(compile_mode="reduce-overhead")
    initialization = time.perf_counter() - initialized
    torch = runtime.torch
    rgb = cv2.cvtColor(image.astype(np.float32) / 255.0, cv2.COLOR_BGR2RGB)
    full = (
        torch.from_numpy(np.transpose(rgb, (2, 0, 1)))
        .float()
        .unsqueeze(0)
        .to(runtime.device)
        .half()
    )
    full = full.contiguous(memory_format=torch.channels_last)
    positions = [(400, 400), (800, 400)]
    inputs = [
        full[:, :, y - 10 : y + 410, x - 10 : x + 410].contiguous(memory_format=torch.channels_last)
        for x, y in positions
    ]

    def once():
        pairs, cores, enqueue, readback = [], [], 0.0, 0.0
        torch.cuda.synchronize()
        started = time.perf_counter()
        with torch.inference_mode():
            for index in range(0, 2, batch_size):
                tile = (
                    torch.cat(inputs[index : index + batch_size], dim=0)
                    if batch_size == 2
                    else inputs[index]
                )
                tile = tile.contiguous(memory_format=torch.channels_last)
                first, last = (
                    torch.cuda.Event(enable_timing=True),
                    torch.cuda.Event(enable_timing=True),
                )
                first.record()
                host_start = time.perf_counter()
                prediction = runtime.model(tile)
                enqueue += time.perf_counter() - host_start
                last.record()
                pairs.append((first, last))
                read_start = time.perf_counter()
                for i in range(batch_size):
                    core = prediction[i : i + 1, :, 40:1640, 40:1640]
                    core_u8 = core.float()
                    core_u8.clamp_(0, 1).mul_(255.0).round_()
                    core_u8 = (
                        core_u8.to(torch.uint8)[0, [2, 1, 0], :, :].permute(1, 2, 0).contiguous()
                    )
                    cores.append(core_u8.cpu().numpy())
                    del core, core_u8
                readback += time.perf_counter() - read_start
                del prediction, tile
        torch.cuda.synchronize()
        return cores, {
            "wall_seconds": time.perf_counter() - started,
            "model_host_call_seconds": enqueue,
            "uint8_and_readback_host_seconds": readback,
            "model_stream_interval_seconds": sum(a.elapsed_time(b) for a, b in pairs) / 1000.0,
        }

    rows = []
    torch.cuda.reset_peak_memory_stats()
    for i in range(7):
        cores, timing = once()
        timing["phase"] = "first" if i == 0 else "warm"
        rows.append(timing)
        if i == 6:
            for j, core in enumerate(cores):
                if not cv2.imwrite(str(output / f"tile-{j}.png"), core):
                    raise RuntimeError("failed to retain tile output")
        del cores
        (output / "partial.json").write_text(json.dumps(rows, indent=2) + "\n")
    reference = json.loads(
        next(
            Path("logs/issue447/runs/single-off-warm/pipeline").rglob("_sr_batch/result.json")
        ).read_text()
    )["outputs"][0]["sr_image"]
    reference_image = cv2.imread(reference)
    if reference_image is None:
        raise FileNotFoundError(reference)
    checks = []
    for j, (x, y) in enumerate(positions):
        actual = cv2.imread(str(output / f"tile-{j}.png"))
        checks.append(
            pixel_difference(actual, reference_image[y * 4 : (y + 400) * 4, x * 4 : (x + 400) * 4])
        )
    return {
        "status": "completed",
        "kind": "compiled-tiles",
        "batch_size": batch_size,
        "initialization_wall_seconds": initialization,
        "rows": rows,
        "warm_median_wall_seconds": statistics.median(r["wall_seconds"] for r in rows[1:]),
        "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
        "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
        "reference_core_comparisons": checks,
        "runtime": runtime.metadata(),
        "limits": "two fixed interior tiles only; event intervals include stream idle/enqueue gaps, not pure kernel busy; first-call stream time includes compilation and is not GPU compute; no full-page/downstream acceptance",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kind",
        choices=("python-imports", "omr-serial", "omr-batch", "compiled-tiles1", "compiled-tiles2"),
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    if args.kind == "python-imports":
        result = imports(args.output)
    elif args.kind.startswith("omr-"):
        result = omr(args.output, args.kind == "omr-batch")
    else:
        result = compiled_tiles(args.output, int(args.kind[-1]))
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "result": str(args.output / "result.json")}))


if __name__ == "__main__":
    main()
