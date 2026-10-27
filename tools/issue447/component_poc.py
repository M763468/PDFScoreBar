"""Isolated SR batching screen and retained-input HOMR CPU diagnostics for #447."""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import os
import pstats
import resource
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")


def pixel_difference(actual, expected) -> dict:
    import numpy as np

    if actual.shape != expected.shape:
        return {"shape_equal": False}
    changed = 0
    maximum = 0
    for y in range(0, len(actual), 64):
        delta = np.abs(actual[y : y + 64].astype(np.int16) - expected[y : y + 64].astype(np.int16))
        changed += int(np.count_nonzero(delta))
        maximum = max(maximum, int(delta.max(initial=0)))
    return {"shape_equal": True, "changed_channel_values": changed, "max_abs_difference": maximum}


def batched_enhance(runtime, image_bgr, batch_size: int):
    """Same padding/FP16/uint8/CPU-stitch contract; batch only equal-shaped tiles."""
    import cv2
    import numpy as np

    torch = runtime.torch
    image = image_bgr.astype(np.float32)
    image /= 255.0
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(np.transpose(image, (2, 0, 1))).float().unsqueeze(0)
    tensor = tensor.to(runtime.device)
    if not runtime.fp32:
        tensor = tensor.half()
    if runtime.channels_last:
        tensor = tensor.contiguous(memory_format=torch.channels_last)
    _, _, height, width = tensor.shape
    output = np.empty((height * runtime.scale, width * runtime.scale, 3), dtype=np.uint8)
    tile = runtime._effective_tile(image_bgr)
    pending = []

    def flush():
        inputs = [tensor[:, :, a[4] : a[5], a[6] : a[7]] for a in pending]
        batch = torch.cat(inputs, dim=0) if len(inputs) > 1 else inputs[0]
        if runtime.channels_last:
            batch = batch.contiguous(memory_format=torch.channels_last)
        predicted = runtime.model(batch)
        for i, (y0, y1, x0, x1, py0, py1, px0, px1) in enumerate(pending):
            cy = (y0 - py0) * runtime.scale
            cx = (x0 - px0) * runtime.scale
            core = predicted[
                i : i + 1,
                :,
                cy : cy + (y1 - y0) * runtime.scale,
                cx : cx + (x1 - x0) * runtime.scale,
            ]
            core_u8 = core.float()
            core_u8.clamp_(0, 1).mul_(255.0).round_()
            core_u8 = core_u8.to(torch.uint8)
            core_u8 = core_u8[0, [2, 1, 0], :, :].permute(1, 2, 0).contiguous()
            output[
                y0 * runtime.scale : y1 * runtime.scale, x0 * runtime.scale : x1 * runtime.scale
            ] = core_u8.cpu().numpy()
        pending.clear()

    with torch.inference_mode():
        for y0 in range(0, height, tile):
            for x0 in range(0, width, tile):
                y1, x1 = min(y0 + tile, height), min(x0 + tile, width)
                item = (
                    y0,
                    y1,
                    x0,
                    x1,
                    max(y0 - runtime.tile_pad, 0),
                    min(y1 + runtime.tile_pad, height),
                    max(x0 - runtime.tile_pad, 0),
                    min(x1 + runtime.tile_pad, width),
                )
                shape = (item[5] - item[4], item[7] - item[6])
                if pending:
                    previous = pending[0]
                    if shape != (previous[5] - previous[4], previous[7] - previous[6]):
                        flush()
                pending.append(item)
                if len(pending) == batch_size:
                    flush()
        if pending:
            flush()
    return output


def write_profile(profiler: cProfile.Profile, output: Path) -> None:
    profiler.dump_stats(str(output / "cpu.prof"))
    for sort in ("cumulative", "tottime"):
        stream = io.StringIO()
        stats = pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats(sort)
        stats.print_stats(80)
        (output / f"cpu-{sort}.txt").write_text(stream.getvalue())
    stats = pstats.Stats(profiler)
    records = [
        {
            "file": file,
            "line": line,
            "function": function,
            "primitive_calls": values[0],
            "calls": values[1],
            "self_seconds": values[2],
            "cumulative_seconds": values[3],
        }
        for (file, line, function), values in stats.stats.items()
    ]
    (output / "cpu-functions.json").write_text(json.dumps(records, indent=2) + "\n")


def sr_screen(config: dict, output: Path) -> dict:
    import cv2
    import numpy as np

    from src.pipeline.detection.current_sr_runtime import CurrentX4SRRuntime

    if config["detection"]["sr_compile_mode"] is not None:
        raise ValueError("This bounded screening experiment fixes eager mode for both variants")
    image = cv2.imread("data/evaluation2/images/Shostakovich-Sym5-Va/page_013.png")
    if image is None:
        raise FileNotFoundError("representative original image")
    initialized = time.perf_counter()
    runtime = CurrentX4SRRuntime(compile_mode=None)
    initialization = time.perf_counter() - initialized
    torch = runtime.torch
    samples = []
    last = {}
    for phase, kind in [
        ("first", "A"),
        ("first", "B"),
        ("warm", "A"),
        ("warm", "B"),
        ("warm", "B"),
        ("warm", "A"),
    ]:
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        actual = runtime.enhance(image) if kind == "A" else batched_enhance(runtime, image, 2)
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        samples.append(
            {
                "phase": phase,
                "variant": kind,
                "wall_seconds": elapsed,
                "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
                "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
            }
        )
        if kind in last:
            del last[kind]
        last[kind] = actual
        (output / "partial.json").write_text(json.dumps(samples, indent=2) + "\n")
    reference_result = next(
        Path("logs/issue447/runs/single-off-warm/pipeline").rglob("_sr_batch/result.json")
    )
    reference_path = json.loads(reference_result.read_text())["outputs"][0]["sr_image"]
    reference = cv2.imread(reference_path)
    if reference is None:
        raise FileNotFoundError(reference_path)
    comparisons = {
        "batch2_vs_batch1": pixel_difference(last["B"], last["A"]),
        "eager_vs_retained_compiled": pixel_difference(last["A"], reference),
    }
    del reference
    for kind in ("A", "B"):
        if not cv2.imwrite(str(output / f"variant-{kind}.png"), last[kind]):
            raise RuntimeError("failed to retain screening output")
    del last
    warm_a = np.median(
        [s["wall_seconds"] for s in samples if s["phase"] == "warm" and s["variant"] == "A"]
    )
    warm_b = np.median(
        [s["wall_seconds"] for s in samples if s["phase"] == "warm" and s["variant"] == "B"]
    )
    profiler = cProfile.Profile()
    profiler.enable()
    profiled = runtime.enhance(image)
    torch.cuda.synchronize()
    profiler.disable()
    del profiled
    write_profile(profiler, output)
    return {
        "status": "completed",
        "scope": "eager component screen only; not production E2E",
        "initialization_wall_seconds": initialization,
        "samples": samples,
        "median_speedup_A_over_B": float(warm_a / warm_b),
        "pixel_comparisons": comparisons,
        "runtime": runtime.metadata(),
        "advance_gates": {
            "speedup_at_least_1_05": bool(warm_a / warm_b >= 1.05),
            "reserved_at_most_6GiB": all(
                s["peak_reserved_bytes"] <= 6 * 2**30 for s in samples if s["variant"] == "B"
            ),
            "identical_pixels_A_B": comparisons["batch2_vs_batch1"].get("changed_channel_values")
            == 0,
        },
    }


def homr_profile(output: Path) -> dict:
    from src.pipeline.detection.current_homr_worker import run

    reference_root = Path("logs/issue447/runs/single-off-warm/pipeline")
    original = next(reference_root.rglob("current_homr_request.json"))
    request = json.loads(original.read_text())
    request["output_root"] = str((output / "homr").resolve())
    request_path = output / "request.json"
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    profiler = cProfile.Profile()
    started = time.perf_counter()
    cpu_started = resource.getrusage(resource.RUSAGE_SELF)
    profiler.runcall(run, request_path, output / "homr-result.json")
    elapsed = time.perf_counter() - started
    cpu_end = resource.getrusage(resource.RUSAGE_SELF)
    write_profile(profiler, output)
    return {
        "status": "completed",
        "scope": "current x4 HOMR retained-input CPU profile; not E2E stage time",
        "profiled_wall_seconds": elapsed,
        "cpu_seconds": cpu_end.ru_utime
        + cpu_end.ru_stime
        - cpu_started.ru_utime
        - cpu_started.ru_stime,
        "reference_request": str(original),
        "result": str(output / "homr-result.json"),
    }


def omr_profile(output: Path) -> dict:
    from src.pipeline.detection.omr_dln_worker import run

    reference_root = Path("logs/issue447/runs/single-off-warm/pipeline")
    reference = json.loads(next(reference_root.rglob("_sr_batch/result.json")).read_text())[
        "outputs"
    ][0]
    profiler = cProfile.Profile()
    started = time.perf_counter()
    profiler.runcall(
        run,
        [Path(reference["image"])],
        output_dir=output / "omr",
        precomputed_sr=Path(reference["sr_image"]),
    )
    elapsed = time.perf_counter() - started
    write_profile(profiler, output)
    old = json.loads(next(reference_root.rglob("omr_sr/page_013/predictions.json")).read_text())
    new = json.loads((output / "omr/page_013/predictions.json").read_text())
    return {
        "status": "completed",
        "scope": "retained-input OMR component CPU profile; not an E2E stage duration",
        "profiled_wall_seconds": elapsed,
        "ordered_predictions_equal": old == new,
    }


def model_wall(output: Path, kind: str) -> dict:
    """Monotonic call spans independent of cProfile's call graph accounting."""
    import cv2

    events = []
    model_devices = []

    def measure(name, function, *args, **kwargs):
        start, cpu = time.perf_counter(), time.process_time()
        try:
            return function(*args, **kwargs)
        finally:
            end = time.perf_counter()
            events.append(
                {
                    "name": name,
                    "start_monotonic": start,
                    "end_monotonic": end,
                    "wall_seconds": end - start,
                    "cpu_seconds": time.process_time() - cpu,
                }
            )

    def wrap(owner, attribute, name):
        original = getattr(owner, attribute)
        setattr(owner, attribute, lambda *a, **k: measure(name, original, *a, **k))

    started = time.perf_counter()
    import_started = time.perf_counter()
    import onnxruntime as ort
    import torch

    if kind == "homr-wall":
        from src.pipeline.detection.current_homr_worker import run
    else:
        import ultralytics

        from src.pipeline.detection.omr_dln_worker import run
    events.append(
        {
            "name": "runtime_imports",
            "wall_seconds": time.perf_counter() - import_started,
            "start_monotonic": import_started,
            "end_monotonic": time.perf_counter(),
        }
    )
    for attribute in ("imread", "imwrite"):
        wrap(cv2, attribute, "cv2." + attribute)
    for attribute in ("__init__", "run", "run_with_iobinding"):
        wrap(ort.InferenceSession, attribute, "onnx_session." + attribute)
    reference_root = Path("logs/issue447/runs/single-off-warm/pipeline")
    if kind == "homr-wall":
        from src.homr_runtime.predictor import HomrPredictor

        wrap(HomrPredictor, "predict", "homr.predict")
        request = json.loads(next(reference_root.rglob("current_homr_request.json")).read_text())
        request["output_root"] = str((output / "homr").resolve())
        request_path = output / "request.json"
        request_path.write_text(json.dumps(request, indent=2) + "\n")
        measure("worker.run", run, request_path, output / "homr-result.json")
    else:
        original_yolo = measure("yolo.class_resolution", getattr, ultralytics, "YOLO")

        def load_yolo(*args, **kwargs):
            model = measure("yolo.model_load", original_yolo, *args, **kwargs)
            original_predict = model.predict

            def predict(*a, **k):
                result = measure("yolo.first_predict_including_setup", original_predict, *a, **k)
                model_devices.append(
                    {
                        "model_device": str(model.device),
                        "predictor_device": str(model.predictor.device),
                    }
                )
                return result

            model.predict = predict
            return model

        ultralytics.YOLO = load_yolo
        reference = json.loads(next(reference_root.rglob("_sr_batch/result.json")).read_text())[
            "outputs"
        ][0]
        measure(
            "worker.run",
            run,
            [Path(reference["image"])],
            output_dir=output / "omr",
            precomputed_sr=Path(reference["sr_image"]),
        )
    torch.cuda.synchronize()
    return {
        "status": "completed",
        "scope": "diagnostic monotonic host call spans; nested and not additive; ONNX I/O binding work may complete in later calls",
        "wall_seconds_including_imports": time.perf_counter() - started,
        "model_devices": model_devices,
        "events": events,
    }


def source_parallel(output: Path) -> dict:
    """Two disposable source workers only; retained SR, no shared model lifetime."""
    reference = Path("logs/issue447/runs/multi-off-warm/pipeline")
    available_kib = next(
        int(line.split()[1])
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )
    if available_kib < 14 * 2**20:
        raise RuntimeError("source-parallel requires 14 GiB available host RAM before launch")
    jobs = []
    started = time.perf_counter()
    for page in ("page_012", "page_014"):
        original = (
            reference
            / "hybrid_output/pipeline/source_page_workers/Shostakovich-Sym5-Va"
            / page
            / "request.json"
        )
        request = json.loads(original.read_text())
        request["baseline_output"] = str((output / "baseline").resolve())
        request["support_output"] = str((output / "current_support").resolve())
        path = output / f"request-{page}.json"
        path.write_text(json.dumps(request, indent=2) + "\n")
        command = [
            sys.executable,
            "-m",
            "src.pipeline.detection.maintained_source_page_worker",
            "--request",
            str(path),
            "--result",
            str(output / f"result-{page}.json"),
        ]
        stream = (output / f"worker-{page}.log").open("w")
        jobs.append(
            (page, subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT), stream)
        )
    results = []
    for page, process, stream in jobs:
        code = process.wait()
        stream.close()
        results.append({"page": page, "exit_code": code})
    return {
        "status": "completed" if all(r["exit_code"] == 0 for r in results) else "failed",
        "scope": "two-page source-generation component; not E2E or final numbering/correction acceptance",
        "pages": results,
        "component_wall_seconds": time.perf_counter() - started,
        "baseline": "retained sequential page_012 and page_014 from multi-off-warm; sampled residency has 0.2 second endpoint uncertainty",
        "limit": "dedicated Docker memory ceiling 16 GiB; source/SR weights/thresholds unchanged",
    }


def main() -> None:
    import yaml

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kind",
        choices=(
            "sr-screen",
            "homr-profile",
            "omr-profile",
            "source-parallel",
            "homr-wall",
            "omr-wall",
        ),
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    config = yaml.safe_load(args.config.read_text())
    if args.kind == "sr-screen":
        result = sr_screen(config, args.output)
    elif args.kind == "homr-profile":
        result = homr_profile(args.output)
    elif args.kind == "omr-profile":
        result = omr_profile(args.output)
    elif args.kind in {"homr-wall", "omr-wall"}:
        result = model_wall(args.output, args.kind)
    else:
        result = source_parallel(args.output)
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps({"status": result["status"], "result": str(args.output / "result.json")}),
        flush=True,
    )
    if result["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
