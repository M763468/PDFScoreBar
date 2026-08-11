"""Run current HOMR on one precomputed x4 image for connector semantics."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _load_request(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Current-HOMR request must be a mapping")
    return dict(payload)


def _build_processing_config(
    processing_config_cls: type[Any],
    *,
    enable_debug: bool,
    enable_cache: bool,
    write_staff_positions: bool,
    use_gpu_inference: bool,
) -> Any:
    """Match the maintained evaluator's ProcessingConfig compatibility branch."""
    args = (
        enable_debug,
        enable_cache,
        write_staff_positions,
        False,
        -1,
    )
    if hasattr(processing_config_cls, "use_gpu_inference"):
        return processing_config_cls(*args, use_gpu_inference)
    return processing_config_cls(*args)


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

    sr_scale = int(det_cfg.get("sr_scale", 2))
    if sr_scale != 4:
        raise ValueError(f"Verified Stage E current HOMR requires sr_scale=4, got {sr_scale}")

    # Load and patch current HOMR only after the Real-ESRGAN process has exited.
    import torch

    from homr.main import ProcessingConfig
    from homr.music_xml_generator import XmlGeneratorArguments
    from src.common.connector_artifacts import connector_mask_paths
    from src.homr_eval_scripts.core.metrics import BarlinePrediction
    from src.homr_eval_scripts.core.predictor import HomrPredictor
    from src.homr_eval_scripts.core.reporting import save_homr_results
    from src.homr_eval_scripts.core.utils import DEFAULT_TUNING
    from src.pipeline.detection.connector_artifacts import install_homr_connector_artifact_capture

    install_homr_connector_artifact_capture(HomrPredictor)

    use_gpu_inference = torch.cuda.is_available()
    config = _build_processing_config(
        ProcessingConfig,
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
    predictor = HomrPredictor(config, tuning, use_gpu_inference=use_gpu_inference)
    xml_args = XmlGeneratorArguments(False, None, None)

    stem = image.stem
    image_run_dir = output_root / "batch" / stem
    image_run_dir.mkdir(parents=True, exist_ok=True)
    try:
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
        save_homr_results(
            image,
            image_run_dir,
            metrics_predictions,
            notehead_mask,
            staff_mask,
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
