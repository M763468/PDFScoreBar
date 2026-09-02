#!/usr/bin/env python3
"""Run an immutable upstream HOMR source commit as a detector-material candidate.

This Issue #294 experiment intentionally stops before Transformer parsing and
MusicXML generation.  The Stage-E baseline is consumed downstream for barline,
staff and clef geometry; current-x4 HOMR remains the connector-semantic source.
The worker therefore measures the maintained upstream SegNet/barline path while
keeping the original-page coordinate contract used by PDFScoreBar.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TARGET_PIXELS = 3.5 * 1000 * 1000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True, stderr=subprocess.PIPE
    ).strip()


def _shape(path: Path) -> list[int] | None:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None
    return [int(image.shape[1]), int(image.shape[0])]


def _processing_config(cls: type[Any], *, use_gpu: bool) -> Any:
    values: dict[str, Any] = {
        "enable_debug": False,
        "enable_cache": True,
        "write_staff_positions": False,
        "read_staff_positions": False,
        "selected_staff": -1,
        "use_gpu_inference": use_gpu,
        "transformer_use_gpu": False,
        "segnet_use_gpu": use_gpu,
        "coreml_encoder": False,
        "title_detection": False,
    }
    signature = inspect.signature(cls)
    kwargs = {name: values[name] for name in signature.parameters if name in values}
    missing = [
        name
        for name, parameter in signature.parameters.items()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        and name not in kwargs
    ]
    if missing:
        raise TypeError(f"Unsupported latest ProcessingConfig fields: {missing}; {signature}")
    return cls(**kwargs)


def _download_segnet(download_weights: Any, *, use_gpu: bool) -> None:
    signature = inspect.signature(download_weights)
    names = set(signature.parameters)
    if {"segnet_use_gpu", "transformer_use_gpu"}.issubset(names):
        kwargs: dict[str, Any] = {
            "segnet_use_gpu": use_gpu,
            "transformer_use_gpu": False,
        }
        if "coreml_encoder" in names:
            kwargs["coreml_encoder"] = False
        download_weights(**kwargs)
        return
    if "use_gpu_inference" in names or len(signature.parameters) == 1:
        download_weights(use_gpu)
        return
    if not signature.parameters:
        download_weights()
        return
    raise TypeError(f"Unsupported latest download_weights signature: {signature}")


def _make_proxy(image: Path, image_run_dir: Path) -> tuple[Path, float, float, np.ndarray]:
    original = cv2.imread(str(image))
    if original is None:
        raise FileNotFoundError(image)
    height, width = original.shape[:2]
    pixels = height * width
    if pixels <= TARGET_PIXELS * 1.5:
        return image, 1.0, 1.0, original
    scale = (pixels / TARGET_PIXELS) ** 0.5
    proxy_width = int(width / scale)
    proxy_height = int(height / scale)
    proxy = cv2.resize(original, (proxy_width, proxy_height))
    proxy_path = image_run_dir / f"{image.stem}_proxy.png"
    if not cv2.imwrite(str(proxy_path), proxy):
        raise RuntimeError(f"Failed to write proxy: {proxy_path}")
    return proxy_path, width / proxy_width, height / proxy_height, original


def _map_predictions(
    bar_line_boxes: list[Any],
    inference_image: Path,
    seg_shape: tuple[int, int],
    proxy_scale_x: float,
    proxy_scale_y: float,
) -> list[Any]:
    from src.homr_eval_scripts.core.heuristics import compute_transform_info
    from src.homr_eval_scripts.core.metrics import BarlinePrediction
    from src.homr_eval_scripts.core.utils import map_pred_to_orig

    transform = compute_transform_info(inference_image, seg_shape)
    mapped: list[Any] = []
    for barline_box in bar_line_boxes:
        raw = barline_box.to_bounding_box().box
        pred_bbox = tuple(int(value) for value in raw)
        x1, y1, x2, y2 = map_pred_to_orig(pred_bbox, transform)
        if proxy_scale_x != 1.0 or proxy_scale_y != 1.0:
            x1 = int(round(x1 * proxy_scale_x))
            y1 = int(round(y1 * proxy_scale_y))
            x2 = int(round(x2 * proxy_scale_x))
            y2 = int(round(y2 * proxy_scale_y))
        mapped.append(
            BarlinePrediction(
                pred_bbox=pred_bbox,
                orig_bbox=(x1, y1, x2, y2),
                system_index=-1,
                staff_index=-1,
            )
        )
    return mapped


def _postprocess(
    image: Path,
    original: np.ndarray,
    predictions: list[Any],
    notehead_mask: np.ndarray,
    staff_mask: np.ndarray,
) -> list[Any]:
    from src.common.thin_barline_finder import ThinBarlineConfig, detect_thin_vertical_runs
    from src.homr_eval_scripts.core.heuristics import filter_detections_by_notehead_proximity
    from src.homr_eval_scripts.core.metrics import BarlinePrediction
    from src.homr_eval_scripts.core.utils import STEM_CONTEXT_HEURISTICS

    thin_config = ThinBarlineConfig(
        min_height=18,
        max_height=800,
        max_width=30,
        pixel_threshold=235,
        max_intensity_std=120.0,
        max_intensity_std_relaxed=150.0,
    )
    gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
    extras = detect_thin_vertical_runs(
        image,
        [prediction.orig_bbox for prediction in predictions],
        config=thin_config,
        grayscale_image=gray,
    )

    def centre(box: tuple[int, int, int, int]) -> tuple[float, float]:
        return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)

    for box_raw in extras:
        box = tuple(int(value) for value in box_raw)
        cx_extra, cy_extra = centre(box)
        extra_height = max(box[3] - box[1], 1)
        replaced = False
        for index, prediction in enumerate(predictions):
            existing = prediction.orig_bbox
            cx_existing, cy_existing = centre(existing)
            if abs(cx_existing - cx_extra) > 2:
                continue
            top = max(existing[1], box[1])
            bottom = min(existing[3], box[3])
            overlap = max(0, bottom - top)
            existing_height = max(existing[3] - existing[1], 1)
            overlap_fraction = overlap / float(max(existing_height, extra_height))
            if overlap_fraction >= 0.6 or abs(cy_existing - cy_extra) <= max(
                existing_height, extra_height
            ):
                if extra_height >= existing_height:
                    predictions[index] = BarlinePrediction(
                        pred_bbox=box,
                        orig_bbox=box,
                        system_index=-2,
                        staff_index=-1,
                    )
                replaced = True
                break
        if not replaced:
            predictions.append(
                BarlinePrediction(
                    pred_bbox=box,
                    orig_bbox=box,
                    system_index=-2,
                    staff_index=-1,
                )
            )

    cfg = STEM_CONTEXT_HEURISTICS
    filtered, _rejected = filter_detections_by_notehead_proximity(
        predictions,
        notehead_mask,
        cfg["notehead_proximity_threshold_px"],
        cfg["min_overlap_px"],
        cfg["max_height_px"],
        cfg["max_width_px"],
        staff_mask,
        cfg["min_staff_crossings"],
        cfg["staff_crossing_enabled"],
    )
    return filtered


def run(
    image: Path,
    homr_source: Path,
    expected_commit: str,
    output_root: Path,
    result_path: Path,
) -> dict[str, Any]:
    started = time.perf_counter()
    image = image.resolve()
    homr_source = homr_source.resolve()
    output_root = output_root.resolve()
    result_path = result_path.resolve()
    if not image.is_file():
        raise FileNotFoundError(image)
    if not (homr_source / "homr").is_dir():
        raise FileNotFoundError(homr_source / "homr")
    actual_commit = _git_head(homr_source)
    if actual_commit != expected_commit:
        raise RuntimeError(f"Latest HOMR checkout mismatch: expected={expected_commit} actual={actual_commit}")
    if output_root.exists():
        raise FileExistsError(output_root)
    if result_path.exists():
        raise FileExistsError(result_path)

    import homr
    import homr.main as homr_main
    import onnxruntime as ort
    import torch
    from homr.segmentation import config as segnet_config
    from homr.transformer.configs import Config
    from src.homr_eval_scripts.core.heuristics import detect_staffs_with_barlines
    from src.homr_eval_scripts.core.reporting import save_homr_results
    from src.homr_eval_scripts.core.utils import DEFAULT_TUNING

    imported_homr = Path(str(homr.__file__)).resolve()
    if homr_source not in imported_homr.parents:
        raise RuntimeError(f"Expected HOMR import from {homr_source}, got {imported_homr}")

    use_gpu = bool(torch.cuda.is_available())
    sessions: list[dict[str, Any]] = []
    original_session = ort.InferenceSession

    def recorded_session(path_or_bytes: Any, *args: Any, **kwargs: Any) -> Any:
        session = original_session(path_or_bytes, *args, **kwargs)
        sessions.append(
            {
                "model": str(path_or_bytes),
                "requested_providers": repr(kwargs.get("providers")),
                "active_providers": list(session.get_providers()),
            }
        )
        return session

    ort.InferenceSession = recorded_session
    stem = image.stem
    image_run_dir = output_root / "batch" / stem
    image_run_dir.mkdir(parents=True, exist_ok=False)
    try:
        config = _processing_config(homr_main.ProcessingConfig, use_gpu=use_gpu)
        _download_segnet(homr_main.download_weights, use_gpu=use_gpu)
        inference_image, proxy_x, proxy_y, original = _make_proxy(image, image_run_dir)
        detector_started = time.perf_counter()
        (
            _multi_staffs,
            _preprocessed,
            _debug,
            _title_future,
            bar_line_boxes,
            notehead_mask,
            staff_mask,
        ) = detect_staffs_with_barlines(
            str(inference_image), config, DEFAULT_TUNING.copy(), use_gpu
        )
        detector_core_sec = time.perf_counter() - detector_started

        seg_shape = tuple(int(value) for value in staff_mask.shape[:2])
        mapped = _map_predictions(bar_line_boxes, inference_image, seg_shape, proxy_x, proxy_y)
        height, width = original.shape[:2]
        notehead_resized = cv2.resize(
            (notehead_mask * 255).astype(np.uint8),
            (width, height),
            interpolation=cv2.INTER_NEAREST,
        )
        staff_resized = cv2.resize(
            (staff_mask * 255).astype(np.uint8),
            (width, height),
            interpolation=cv2.INTER_NEAREST,
        )
        mapped = _postprocess(image, original, mapped, notehead_resized, staff_resized)
        detection = save_homr_results(
            image, image_run_dir, mapped, notehead_resized, staff_resized
        )
    finally:
        ort.InferenceSession = original_session

    segnet = Path(segnet_config.segnet_path_onnx_fp16 if use_gpu else segnet_config.segnet_path_onnx)
    transformer = Config().filepaths
    payload = {
        "schema_version": "issue294.latest_detector_material.v1",
        "status": "completed",
        "scope": "detector_material_only_pre_transformer",
        "historical_detector_artifact_runtime_input": False,
        "image": str(image),
        "homr": {
            "source": str(homr_source),
            "commit": actual_commit,
            "module": str(imported_homr),
        },
        "runtime": {
            "python": sys.executable,
            "python_version": platform.python_version(),
            "numpy_version": np.__version__,
            "opencv_version": cv2.__version__,
            "onnxruntime_version": ort.__version__,
            "torch_version": torch.__version__,
            "cuda": use_gpu,
        },
        "models": {
            "segnet": {
                "path": str(segnet),
                "sha256": sha256(segnet) if segnet.is_file() else None,
                "executed": True,
            },
            "transformer_encoder": {
                "path": str(Path(transformer.encoder_path_fp16)),
                "executed": False,
            },
            "transformer_decoder": {
                "path": str(Path(transformer.decoder_path_fp16)),
                "executed": False,
            },
        },
        "onnx_sessions": sessions,
        "timings_sec": {
            "detector_core": detector_core_sec,
            "worker_total": time.perf_counter() - started,
        },
        "artifacts": {
            "detections": str(detection),
            "staff_mask": str(image_run_dir / f"{stem}_staff_mask.png"),
            "notehead_mask": str(image_run_dir / f"{stem}_notehead_mask.png"),
            "proxy": str(inference_image) if inference_image != image else None,
        },
        "coordinate_checks": {
            "original_shape_wh": [int(original.shape[1]), int(original.shape[0])],
            "staff_mask_shape_wh": _shape(image_run_dir / f"{stem}_staff_mask.png"),
            "notehead_mask_shape_wh": _shape(image_run_dir / f"{stem}_notehead_mask.png"),
        },
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--homr-source", type=Path, required=True)
    parser.add_argument("--homr-commit", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = run(
            args.image,
            args.homr_source,
            args.homr_commit,
            args.output_root,
            args.result,
        )
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {"status": "completed", "result": str(args.result.resolve()), "scope": payload["scope"]},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
