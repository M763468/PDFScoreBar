"""Run current HOMR on one precomputed x4 image for connector semantics."""

from __future__ import annotations

import argparse
import json
import traceback
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import cv2
import numpy as np


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


def _publish_empty_detections(detection: Path) -> None:
    """Replace a non-score page's detections with none; keep the originals for audit."""

    payload = json.loads(detection.read_text(encoding="utf-8"))
    discarded = detection.with_name(detection.stem + "_discarded.json")
    discarded.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    payload["predictions"] = []
    detection.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class CurrentHomrEmptyResultError(RuntimeError):
    """HOMR returned an empty result for a page that is not a verified non-score page."""


def _classify_page_content(
    *,
    image: Path,
    stem: str,
    image_run_dir: Path,
    empty_records: list[dict[str, Any]],
    prediction_count: int,
    connector_present: Mapping[str, bool],
) -> tuple[str, dict[str, Any] | None, Path | None]:
    """Decide whether an empty HOMR result is a cover/blank page (#532).

    A normal HOMR result is a score page and keeps the connector-pair contract. An
    empty result is accepted as a non-score page only when HOMR's own staff
    segmentation shows no staff evidence; otherwise the page fails explicitly so a
    score page is never published as an empty page.
    """

    from src.common.connector_artifacts import write_non_score_page_marker
    from src.homr_runtime.empty_detection import (
        NON_SCORE_PAGE,
        classification_thresholds,
        classify_empty_detection,
    )

    if not empty_records:
        return "score", None, None
    if len(empty_records) != 1:
        raise CurrentHomrEmptyResultError(
            f"Current HOMR reported {len(empty_records)} empty results for one page: {image}"
        )
    record = empty_records[0]
    evidence = record.get("evidence")
    classification = classify_empty_detection(evidence)
    empty_detection = {
        "homr_reason": record.get("reason"),
        "classification": classification,
        "evidence": evidence,
        "thresholds": classification_thresholds(),
    }
    if classification != NON_SCORE_PAGE:
        if evidence:
            details = (
                f"inner staff fraction={float(evidence['inner_staff_mask_fraction']):.5f}, "
                f"widest staff row={float(evidence['inner_max_row_staff_fraction']):.4f}, "
                f"inner staff fragments={int(evidence['inner_staff_fragment_count'])}, "
                f"noteheads={int(evidence['notehead_count'])}"
            )
        else:
            details = "no segmentation evidence was recorded"
        raise CurrentHomrEmptyResultError(
            f"Current HOMR returned an empty result ({record.get('reason')}) for {image}, "
            f"but the page is not a verified non-score page ({classification}: {details}). "
            "It is not published as an empty cover/blank page; check the input page "
            "and HOMR staff/notehead detection."
        )
    # HOMR's post-processing still proposes a few vertical-line candidates on a page
    # without staves (scan edges, text). A non-score page publishes no barlines, so
    # they are discarded by the caller and only counted here.
    empty_detection["discarded_barline_predictions"] = int(prediction_count)
    present = sorted(name for name, exists in connector_present.items() if exists)
    if present:
        raise CurrentHomrEmptyResultError(
            f"Current HOMR classified {image} as a non-score page but published "
            f"connector artifacts: {present}"
        )
    marker = write_non_score_page_marker(
        image_run_dir,
        stem,
        image=image,
        reason=str(record.get("reason")),
        evidence=evidence or {},
        thresholds=empty_detection["thresholds"],
    )
    return NON_SCORE_PAGE, empty_detection, marker


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
    import torch

    import homr.main as homr_main
    from homr.music_xml_generator import XmlGeneratorArguments
    from src.common.connector_artifacts import (
        connector_mask_paths,
        invalidate_non_score_page_marker,
    )
    from src.homr_runtime import heuristics as homr_heuristics
    from src.homr_runtime import predictor as homr_predictor
    from src.homr_runtime.api_compat import (
        build_processing_config_compat,
        install_current_homr_consumer_compat,
    )
    from src.homr_runtime.empty_detection import capture_empty_detections
    from src.homr_runtime.reporting import save_homr_results
    from src.homr_runtime.types import DEFAULT_TUNING, BarlinePrediction
    from src.pipeline.detection.connector_artifacts import install_homr_connector_artifact_capture

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
    predictor = HomrPredictor(config, tuning, use_gpu_inference=use_gpu_inference)
    xml_args = XmlGeneratorArguments(False, None, None)

    stem = image.stem
    image_run_dir = output_root / "batch" / stem
    image_run_dir.mkdir(parents=True, exist_ok=True)
    invalidate_non_score_page_marker(image_run_dir, stem)
    try:
        with capture_empty_detections() as empty_records:
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
    connector_present = {name: path.is_file() for name, path in connector_paths.items()}
    connector_complete = all(connector_present.values())
    page_content, empty_detection, non_score_marker = _classify_page_content(
        image=image,
        stem=stem,
        image_run_dir=image_run_dir,
        empty_records=empty_records,
        prediction_count=len(metrics_predictions),
        connector_present=connector_present,
    )
    if page_content == "non_score_page":
        _publish_empty_detections(detection)
    payload = {
        "schema_version": "pipeline.current_homr_on_x4.v1",
        "status": "completed",
        "image": str(image),
        "sr_image": str(sr_image),
        "sr_scale": 4,
        "current_sr_detection": str(detection),
        "staff_mask": str(staff),
        "page_content": page_content,
        "empty_detection": empty_detection,
        "non_score_page_marker": str(non_score_marker) if non_score_marker else None,
        "connector_complete": connector_complete,
        "connector_present": connector_present,
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
    try:
        result = run(args.request, args.result)
    except Exception as error:  # noqa: BLE001
        traceback.print_exc()
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "traceback": traceback.format_exc(),
                },
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"status": "completed", "result": str(result)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
