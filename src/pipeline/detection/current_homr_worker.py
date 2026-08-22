"""Run current HOMR on one precomputed x4 image for connector semantics."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from src.pipeline.perf_trace import set_context, span


def _load_request(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Current-HOMR request must be a mapping")
    return dict(payload)


def _resize_mask_to_image_size(mask: np.ndarray, image_size: tuple[int, int]) -> np.ndarray:
    """Restore an SR-space HOMR mask to the original page-image coordinates."""
    target_width, target_height = image_size
    if mask.ndim != 2:
        raise ValueError(f"Current-HOMR mask must be 2-D, got shape {mask.shape}")
    if mask.shape == (target_height, target_width):
        return mask
    return cv2.resize(
        mask,
        (target_width, target_height),
        interpolation=cv2.INTER_NEAREST,
    )


def run(request_path: Path, result_path: Path) -> Path:
    request = _load_request(request_path)
    det_cfg = request.get("detection")
    if not isinstance(det_cfg, Mapping):
        raise ValueError("Current-HOMR request lacks detection settings")

    image = Path(str(request["image"])).resolve()
    sr_image = Path(str(request["sr_image"])).resolve()
    output_root = Path(str(request["output_root"])).resolve()
    if not image.is_file():
        raise FileNotFoundError(image)
    if not sr_image.is_file():
        raise FileNotFoundError(sr_image)

    original_image = cv2.imread(str(image), cv2.IMREAD_GRAYSCALE)
    if original_image is None:
        raise RuntimeError(f"Failed to read current-HOMR source image: {image}")
    image_size = (int(original_image.shape[1]), int(original_image.shape[0]))

    sr_scale = int(det_cfg.get("sr_scale", 2))
    if sr_scale != 4:
        raise ValueError(f"Verified Stage E current HOMR requires sr_scale=4, got {sr_scale}")

    # Load current HOMR only after the Real-ESRGAN process has exited. Compatibility
    # is applied to the callable/class objects held by their consumers so import-time
    # bindings in predictor/heuristics do not bypass the shared boundary.
    with span("current_homr_worker.heavy_imports_cuda_init"):
        import torch

    import homr.main as homr_main
    from homr.music_xml_generator import XmlGeneratorArguments
    from src.common.connector_artifacts import connector_mask_paths
    from src.homr_eval_scripts.core import heuristics as homr_heuristics
    from src.homr_eval_scripts.core import predictor as homr_predictor
    from src.homr_eval_scripts.core.metrics import BarlinePrediction
    from src.homr_eval_scripts.core.reporting import save_homr_results
    from src.homr_eval_scripts.core.utils import DEFAULT_TUNING
    from src.pipeline.detection.connector_artifacts import install_homr_connector_artifact_capture
    from src.pipeline.detection.homr_profile_compat import (
        build_processing_config_compat,
        install_current_homr_consumer_compat,
    )

    use_gpu_inference = torch.cuda.is_available()
    homr_api_compat = install_current_homr_consumer_compat(
        homr_main,
        homr_predictor,
        homr_heuristics,
        use_gpu_inference=use_gpu_inference,
    )

    HomrPredictor = homr_predictor.HomrPredictor
    install_homr_connector_artifact_capture(HomrPredictor)

    config = build_processing_config_compat(
        homr_main.ProcessingConfig,
        enable_debug=bool(det_cfg.get("enable_debug", False)),
        enable_cache=bool(det_cfg.get("enable_cache", True)),
        write_staff_positions=bool(det_cfg.get("write_staff_positions", False)),
        use_gpu_inference=use_gpu_inference,
    )
    tuning = DEFAULT_TUNING.copy()
    tuning.update(
        {
            "barline_min_height_factor": det_cfg.get("barline_min_height_factor", 1.0),
            "barline_max_width_factor": det_cfg.get("barline_max_width_factor", 1.0),
        }
    )
    with span("current_homr_worker.predictor_model_initialization"):
        predictor = HomrPredictor(config, tuning, use_gpu_inference=use_gpu_inference)
    xml_args = XmlGeneratorArguments(False, None, None)

    stem = image.stem
    image_run_dir = output_root / "batch" / stem
    image_run_dir.mkdir(parents=True, exist_ok=True)
    try:
        with span("current_homr_worker.synchronized_prediction", cuda=True):
            predictions, _, _, _, notehead_mask, staff_mask, _, _ = predictor.predict(
                sr_image,
                xml_args,
                sr_scale=sr_scale,
                image_run_dir=image_run_dir,
            )
        metrics_predictions = [
            BarlinePrediction(
                pred_bbox=prediction.pred_bbox,
                orig_bbox=tuple(int(round(coord / sr_scale)) for coord in prediction.orig_bbox),
                system_index=prediction.system_index,
                staff_index=prediction.staff_index,
            )
            for prediction in predictions
        ]
        with span("current_homr_worker.artifact_generation_resizing_serialization"):
            save_homr_results(
                image,
                image_run_dir,
                metrics_predictions,
                _resize_mask_to_image_size(notehead_mask, image_size),
                _resize_mask_to_image_size(staff_mask, image_size),
            )
    finally:
        predictor.cleanup()

    detection = image_run_dir / f"{stem}_detections.json"
    staff = image_run_dir / f"{stem}_staff_mask.png"
    missing = [str(path) for path in (detection, staff) if not path.is_file()]
    if missing:
        raise FileNotFoundError("Current HOMR artifacts missing: " + ", ".join(missing))

    connector_paths = connector_mask_paths(image_run_dir, stem)
    connector_complete = all(path.is_file() for path in connector_paths.values())
    payload = {
        "schema_version": "pipeline.current_homr_on_x4.v1",
        "status": "completed",
        "image": str(image),
        "sr_image": str(sr_image),
        "sr_scale": 4,
        "current_sr_detection": str(detection),
        "staff_mask": str(staff),
        "connector_complete": connector_complete,
        "connector_symbols": (
            str(connector_paths["symbols"]) if connector_paths["symbols"].is_file() else None
        ),
        "connector_brace_dot": (
            str(connector_paths["brace_dot"]) if connector_paths["brace_dot"].is_file() else None
        ),
        "homr_api_compat": homr_api_compat,
        "historical_detector_artifact_runtime_input": False,
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
    set_context(process_role="current_homr_worker")
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
