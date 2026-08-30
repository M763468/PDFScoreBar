"""Generate verified current-x4 SR images with one Real-ESRGAN model lifetime."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import cv2

from src.pipeline.perf_trace import set_context, span
from src.pipeline.utils.images import load_image


def _load_request(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Current-SR batch request must be a mapping")
    return dict(payload)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _items(request: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = request.get("items")
    if not isinstance(raw, list) or not raw:
        raise ValueError("Current-SR batch request requires a non-empty items list")
    items: list[dict[str, Any]] = []
    seen_images: set[Path] = set()
    seen_outputs: set[Path] = set()
    for value in raw:
        if not isinstance(value, Mapping):
            raise ValueError("Current-SR batch item must be a mapping")
        image = Path(str(value["image"])).resolve()
        output = Path(str(value["output"])).resolve()
        if image in seen_images:
            raise ValueError(f"Duplicate current-SR batch image: {image}")
        if output in seen_outputs:
            raise ValueError(f"Duplicate current-SR batch output: {output}")
        if not image.is_file():
            raise FileNotFoundError(image)
        seen_images.add(image)
        seen_outputs.add(output)
        items.append({"image": image, "output": output})
    return items


def run(request_path: Path, result_path: Path) -> Path:
    request = _load_request(request_path)
    det_cfg = request.get("detection")
    if not isinstance(det_cfg, Mapping):
        raise ValueError("Current-SR batch request lacks detection settings")

    sr_scale = int(det_cfg.get("sr_scale", 2))
    if sr_scale != 4:
        raise ValueError(f"Verified Stage E current SR requires sr_scale=4, got {sr_scale}")

    items = _items(request)
    set_context(process_role="current_sr_batch_worker")

    # This is the performance-gate boundary for the dedicated SR worker. Start
    # before the heavy runtime import/model setup so batch_wall_sec represents
    # the whole SR phase rather than only per-page enhancement after init.
    started_batch = time.perf_counter()

    # Heavy Real-ESRGAN/basicSR/torch imports occur only in this disposable SR
    # process and only once for the whole page batch.
    started_runtime_import = time.perf_counter()
    from src.pipeline.detection.current_sr_runtime import CurrentX4SRRuntime

    runtime_import_wall_sec = time.perf_counter() - started_runtime_import
    started_model_initialization = time.perf_counter()
    with span("sr_batch.model_initialization", cuda=True):
        runtime = CurrentX4SRRuntime(
            tile=det_cfg.get("sr_tile", -1),
            tile_pad=int(det_cfg.get("sr_tile_pad", 10)),
            fp32=bool(det_cfg.get("sr_fp32", False)),
            channels_last=bool(det_cfg.get("sr_channels_last", True)),
            compile_mode=det_cfg.get("sr_compile_mode"),
        )
    model_initialization_wall_sec = time.perf_counter() - started_model_initialization

    torch = runtime.torch
    torch.cuda.reset_peak_memory_stats()
    outputs: list[dict[str, Any]] = []

    for item in items:
        image = item["image"]
        output = item["output"]
        set_context(page=image.name)
        started_page = time.perf_counter()

        with span("sr_worker.image_read_preprocess"):
            image_bgr = load_image(image, None)
        original_h, original_w = image_bgr.shape[:2]

        with span("sr_worker.realesrgan_total", cuda=True):
            with span("sr_worker.synchronized_enhance", cuda=True):
                upscaled = runtime.enhance(image_bgr)

        expected_shape = (original_h * 4, original_w * 4, 3)
        if upscaled.shape != expected_shape:
            raise ValueError(
                f"Current x4 SR shape mismatch for {image}: "
                f"expected={expected_shape}, actual={upscaled.shape}"
            )

        output.parent.mkdir(parents=True, exist_ok=True)
        with span("sr_worker.image_write"):
            if not cv2.imwrite(str(output), upscaled):
                raise RuntimeError(f"Failed to write current x4 SR image: {output}")
        with span("sr_worker.sha256"):
            sr_sha256 = _sha256(output)

        outputs.append(
            {
                "image": str(image),
                "sr_scale": 4,
                "sr_image": str(output),
                "sr_sha256": sr_sha256,
                "shape": list(upscaled.shape),
                "page_wall_sec": time.perf_counter() - started_page,
                "historical_detector_artifact_runtime_input": False,
            }
        )
        del upscaled, image_bgr

    torch.cuda.synchronize()
    payload = {
        "schema_version": "pipeline.current_x4_sr_batch.v1",
        "status": "completed",
        "sr_scale": 4,
        "page_count": len(outputs),
        "outputs": outputs,
        "runtime": runtime.metadata(),
        "batch_wall_sec": time.perf_counter() - started_batch,
        "batch_wall_scope": "runtime_import_model_init_and_page_processing",
        "runtime_import_wall_sec": runtime_import_wall_sec,
        "model_initialization_wall_sec": model_initialization_wall_sec,
        "peak_cuda_allocated_bytes": int(torch.cuda.max_memory_allocated()),
        "peak_cuda_reserved_bytes": int(torch.cuda.max_memory_reserved()),
        "historical_detector_artifact_runtime_input": False,
        "memory_boundary": "dedicated_sr_batch_process",
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.request, args.result)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"status": "completed", "result": str(result)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
