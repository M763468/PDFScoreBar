#!/usr/bin/env python3
"""Run two Issue #252 candidate sets through CNN, grouping, MMR, and final numbering."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Mapping

import cv2
import torch

from src.measure_numbering.mmr import MMRClassifier, MMROCREngine
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.serialization import score_to_dict
from src.measure_numbering.types import Score
from src.pipeline.core.config import load_yaml
from src.pipeline.steps.cnn_scoring import (
    MEAN,
    STD,
    GPUNormalize,
    _load_model,
    _resolve_model_path,
    _score_directory,
)
from src.pipeline.steps.numbering import run_mmr_batch
from tools.issue252.audit_grouped_semantic_impact import (
    _route_evidence,
    compare_grouped_final_numbering,
    normalize_isolated_mmr_overrides,
)
from tools.issue252.render_grouped_numbering_overlay import render_overlay

Box = tuple[int, int, int, int]


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _config(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = load_yaml(path)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Config must be a mapping: {path}")
    detection = payload.get("detection")
    mmr = payload.get("mmr")
    if not isinstance(detection, Mapping):
        raise ValueError(f"Config must contain detection mapping: {path}")
    if not isinstance(mmr, Mapping):
        raise ValueError(f"Config must contain mmr mapping: {path}")
    return dict(detection), dict(mmr)


def _read_image_size(path: Path) -> tuple[int, int]:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(path)
    height, width = image.shape[:2]
    return width, height


def _validate_image_contract(
    *,
    cnn_image: Path,
    numbering_image: Path,
    cnn_input_image_scale: float,
) -> dict[str, Any]:
    if cnn_input_image_scale <= 0:
        raise ValueError("cnn_input_image_scale must be positive")
    cnn_width, cnn_height = _read_image_size(cnn_image)
    numbering_width, numbering_height = _read_image_size(numbering_image)
    expected_width = int(round(cnn_width / cnn_input_image_scale))
    expected_height = int(round(cnn_height / cnn_input_image_scale))
    if abs(expected_width - numbering_width) > 2 or abs(expected_height - numbering_height) > 2:
        raise ValueError(
            "CNN and numbering image coordinate contract mismatch: "
            f"cnn={cnn_width}x{cnn_height} scale={cnn_input_image_scale} "
            f"expected_numbering={expected_width}x{expected_height} "
            f"actual_numbering={numbering_width}x{numbering_height}"
        )
    return {
        "cnn_image_size": [cnn_width, cnn_height],
        "numbering_image_size": [numbering_width, numbering_height],
        "cnn_input_image_scale": cnn_input_image_scale,
        "cnn_output_coordinate_space": "numbering_image_pixels",
    }


def _validate_cnn_staff_mask_contract(
    *,
    cnn_staff_mask: Path | None,
    numbering_image: Path,
    bands_from: Path | None,
) -> dict[str, Any]:
    if cnn_staff_mask is None and bands_from is None:
        raise ValueError("Provide --cnn-staff-mask or --cnn-bands-from")
    if cnn_staff_mask is None:
        return {
            "source": "bands_from",
            "path": str(bands_from.resolve()) if bands_from is not None else None,
        }
    mask = cv2.imread(str(cnn_staff_mask), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(cnn_staff_mask)
    numbering_width, numbering_height = _read_image_size(numbering_image)
    mask_height, mask_width = mask.shape[:2]
    if (mask_width, mask_height) != (numbering_width, numbering_height):
        raise ValueError(
            "CNN staff mask must use the post-downscale/original coordinate space: "
            f"mask={mask_width}x{mask_height} numbering={numbering_width}x{numbering_height}"
        )
    return {
        "source": "staff_mask",
        "path": str(cnn_staff_mask.resolve()),
        "size": [mask_width, mask_height],
    }


def _score_candidates(
    *,
    label: str,
    candidates_path: Path,
    cnn_image_path: Path,
    cnn_staff_mask_path: Path | None,
    output_root: Path,
    detection: Mapping[str, Any],
    model: torch.nn.Module,
    gpu_norm: GPUNormalize,
    device: torch.device,
    bands_from: Path | None,
    score_name: str | None,
    input_image_scale: float,
) -> Path:
    run_dir = output_root / label / "cnn"
    run_dir.mkdir(parents=True, exist_ok=True)
    staged_candidates = run_dir / "pipeline2_no_peak_candidates.json"
    shutil.copy2(candidates_path, staged_candidates)

    success = _score_directory(
        run_dir=run_dir,
        image_path=cnn_image_path,
        model=model,
        gpu_norm=gpu_norm,
        threshold=float(detection.get("cnn_threshold", 0.1)),
        device=device,
        batch_size=int(detection.get("cnn_batch_size", 64)),
        staff_mask_path=None if bands_from is not None else cnn_staff_mask_path,
        bands_from=bands_from,
        current_score_name=score_name,
        staff_vov_threshold=float(detection.get("staff_vov_threshold", 0.5)),
        crop_recenter_on_bbox_ink=bool(detection.get("crop_recenter_on_bbox_ink", False)),
        crop_recenter_max_shift_unit_ratio=float(
            detection.get("crop_recenter_max_shift_unit_ratio", 0.35)
        ),
        input_image_scale=input_image_scale,
        apply_nms_enabled=bool(detection.get("cnn_apply_nms", False)),
    )
    if not success:
        raise RuntimeError(f"CNN scoring failed for {label}")
    return run_dir / "pipeline2_no_peak_filtered_cnn.json"


def _connector_mask_paths(
    *,
    symbol_mask_path: Path | None,
    brace_dot_mask_path: Path | None,
) -> dict[str, Path] | None:
    result = {}
    if symbol_mask_path is not None:
        result["symbols"] = symbol_mask_path
    if brace_dot_mask_path is not None:
        result["brace_dot"] = brace_dot_mask_path
    return result or None


def _number_route(
    *,
    label: str,
    barlines_path: Path,
    numbering_image_path: Path,
    numbering_staff_mask_path: Path,
    symbol_mask_path: Path | None,
    brace_dot_mask_path: Path | None,
    output_root: Path,
    page_number: int,
    start_number: int,
    mmr_model_path: Path,
    mmr_device: torch.device,
    enable_rotation_tta: bool,
    mmr_threshold: float,
    mmr_rescue_threshold: float,
    rapidocr_provider: str,
    classifier: MMRClassifier,
    ocr_engine: MMROCREngine,
) -> dict[str, Path]:
    route_root = output_root / label / "numbering"
    route_root.mkdir(parents=True, exist_ok=True)
    image = cv2.imread(str(numbering_image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(numbering_image_path)
    height, width = image.shape[:2]
    barline_boxes = _load(barlines_path)
    if not isinstance(barline_boxes, list):
        raise ValueError(f"Expected barline list: {barlines_path}")

    connector_paths = _connector_mask_paths(
        symbol_mask_path=symbol_mask_path,
        brace_dot_mask_path=brace_dot_mask_path,
    )
    pipeline = MeasureNumberingPipeline()
    base_connector_evidence = route_root / "connector_evidence_base.json"
    base_page = pipeline.process_page(
        barline_boxes,
        numbering_staff_mask_path,
        (width, height),
        page_number=page_number,
        image=image,
        connector_mask_paths=connector_paths,
        connector_evidence_output_path=base_connector_evidence,
    )
    base_score = Score()
    base_score.pages.append(base_page)
    pipeline.numberer.number_score(base_score, start_number=start_number)
    base_path = route_root / "numbering_base.json"
    base_payload = score_to_dict(base_score)
    _write(base_path, base_payload)

    raw_overrides_path = route_root / "overrides_mmr_raw.json"
    run_mmr_batch(
        pages_data=[base_payload],
        image_paths=[numbering_image_path],
        output_paths=[raw_overrides_path],
        model_path=mmr_model_path,
        device=mmr_device,
        enable_rotation_tta=enable_rotation_tta,
        threshold=mmr_threshold,
        rescue_threshold=mmr_rescue_threshold,
        classifier=classifier,
        ocr_engine=ocr_engine,
        rapidocr_provider=rapidocr_provider,
    )
    raw_overrides_payload = _load(raw_overrides_path)
    raw_overrides, local_overrides = normalize_isolated_mmr_overrides(
        raw_overrides_payload,
        serialized_page_number=page_number,
    )
    local_overrides_path = route_root / "overrides_mmr_local_page_index.json"
    _write(
        local_overrides_path,
        {
            "schema_version": "issue252.isolated_mmr_overrides.v1",
            "serialized_page_number": page_number,
            "source_page_key": page_number - 1,
            "local_score_page_index": 0,
            "measure_overrides": local_overrides,
        },
    )

    final_connector_evidence = route_root / "connector_evidence_final.json"
    final_page = pipeline.process_page(
        barline_boxes,
        numbering_staff_mask_path,
        (width, height),
        page_number=page_number,
        image=image,
        connector_mask_paths=connector_paths,
        connector_evidence_output_path=final_connector_evidence,
    )
    final_score = Score()
    final_score.pages.append(final_page)
    pipeline.numberer.number_score(
        final_score,
        start_number=start_number,
        overrides=local_overrides,
    )
    final_path = route_root / "numbering_final.json"
    final_payload = score_to_dict(final_score)
    _write(final_path, final_payload)

    contract_path = route_root / "numbering_execution_contract.json"
    _write(
        contract_path,
        {
            "schema_version": "issue252.numbering_execution_contract.v1",
            "serialized_page_number": page_number,
            "isolated_score_page_index": 0,
            "raw_mmr_override_count": len(raw_overrides),
            "local_mmr_override_count": len(local_overrides),
            "base_equals_final": base_payload == final_payload,
            "connector_mask_source": (
                "explicit_proxy_masks" if connector_paths is not None else "page_image_ink"
            ),
        },
    )
    return {
        "barlines": barlines_path,
        "connector_evidence_base": base_connector_evidence,
        "numbering_base": base_path,
        "overrides_mmr_raw": raw_overrides_path,
        "overrides_mmr_local": local_overrides_path,
        "connector_evidence_final": final_connector_evidence,
        "numbering_final": final_path,
        "execution_contract": contract_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/dense_full_pipeline.yaml"))
    parser.add_argument("--default-candidates", type=Path, required=True)
    parser.add_argument("--candidate-candidates", type=Path, required=True)
    parser.add_argument("--cnn-image", type=Path, required=True)
    parser.add_argument("--numbering-image", type=Path, required=True)
    parser.add_argument("--cnn-staff-mask", type=Path)
    parser.add_argument("--numbering-staff-mask", type=Path, required=True)
    parser.add_argument("--symbol-mask", type=Path)
    parser.add_argument("--brace-dot-mask", type=Path)
    parser.add_argument("--allow-page-image-connector-fallback", action="store_true")
    parser.add_argument("--cnn-bands-from", type=Path)
    parser.add_argument("--score-name")
    parser.add_argument("--cnn-input-image-scale", type=float, default=1.0)
    parser.add_argument("--page-number", type=int, required=True)
    parser.add_argument("--start-number", type=int, default=1)
    parser.add_argument("--target-bbox", type=int, nargs=4, required=True)
    parser.add_argument("--nearby-bbox", type=int, nargs=4, required=True)
    parser.add_argument("--x-tolerance", type=float, default=12.0)
    parser.add_argument("--overlay-crop", type=int, nargs=4)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("logs/issue252_grouped_final_numbering_comparison"),
    )
    args = parser.parse_args()

    if (
        args.symbol_mask is None
        and args.brace_dot_mask is None
        and not args.allow_page_image_connector_fallback
    ):
        raise ValueError(
            "Provide --symbol-mask/--brace-dot-mask, or explicitly allow "
            "--allow-page-image-connector-fallback"
        )

    coordinate_contract = _validate_image_contract(
        cnn_image=args.cnn_image,
        numbering_image=args.numbering_image,
        cnn_input_image_scale=args.cnn_input_image_scale,
    )
    coordinate_contract["cnn_staff_filter"] = _validate_cnn_staff_mask_contract(
        cnn_staff_mask=args.cnn_staff_mask,
        numbering_image=args.numbering_image,
        bands_from=args.cnn_bands_from,
    )
    detection, mmr = _config(args.config)
    cnn_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    cnn_model_path = _resolve_model_path(detection.get("cnn_model_path"))
    cnn_model = _load_model(cnn_model_path, cnn_device)
    gpu_norm = GPUNormalize(MEAN, STD).to(cnn_device)

    mmr_model_raw = mmr.get("model_path")
    if not mmr_model_raw:
        raise ValueError("mmr.model_path is required")
    mmr_model_path = Path(str(mmr_model_raw))
    mmr_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    enable_rotation_tta = bool(mmr.get("enable_rotation_tta", False))
    mmr_threshold = float(mmr.get("threshold", 0.5))
    mmr_rescue_threshold = float(mmr.get("rescue_threshold", 0.1))
    rapidocr_provider = str(mmr.get("rapidocr_provider", "auto"))
    classifier = MMRClassifier(mmr_model_path, mmr_device)
    ocr_engine = MMROCREngine(enable_rotation_tta=enable_rotation_tta)

    candidate_inputs = {
        "default": args.default_candidates,
        "candidate": args.candidate_candidates,
    }
    route_artifacts: dict[str, dict[str, Path]] = {}
    for label, candidates_path in candidate_inputs.items():
        cnn_barlines = _score_candidates(
            label=label,
            candidates_path=candidates_path,
            cnn_image_path=args.cnn_image,
            cnn_staff_mask_path=args.cnn_staff_mask,
            output_root=args.output_root,
            detection=detection,
            model=cnn_model,
            gpu_norm=gpu_norm,
            device=cnn_device,
            bands_from=args.cnn_bands_from,
            score_name=args.score_name,
            input_image_scale=args.cnn_input_image_scale,
        )
        route_artifacts[label] = _number_route(
            label=label,
            barlines_path=cnn_barlines,
            numbering_image_path=args.numbering_image,
            numbering_staff_mask_path=args.numbering_staff_mask,
            symbol_mask_path=args.symbol_mask,
            brace_dot_mask_path=args.brace_dot_mask,
            output_root=args.output_root,
            page_number=args.page_number,
            start_number=args.start_number,
            mmr_model_path=mmr_model_path,
            mmr_device=mmr_device,
            enable_rotation_tta=enable_rotation_tta,
            mmr_threshold=mmr_threshold,
            mmr_rescue_threshold=mmr_rescue_threshold,
            rapidocr_provider=rapidocr_provider,
            classifier=classifier,
            ocr_engine=ocr_engine,
        )

    target: Box = tuple(args.target_bbox)  # type: ignore[assignment]
    default_final = _load(route_artifacts["default"]["numbering_final"])
    candidate_final = _load(route_artifacts["candidate"]["numbering_final"])
    default_connector = _load(route_artifacts["default"]["connector_evidence_final"])
    candidate_connector = _load(route_artifacts["candidate"]["connector_evidence_final"])
    default_evidence = _route_evidence(
        default_final,
        default_connector,
        page_number=args.page_number,
        target=target,
        x_tolerance=args.x_tolerance,
    )
    candidate_evidence = _route_evidence(
        candidate_final,
        candidate_connector,
        page_number=args.page_number,
        target=target,
        x_tolerance=args.x_tolerance,
    )
    connector_evidence_equal = default_connector == candidate_connector

    overlay_paths = {}
    crop = tuple(args.overlay_crop) if args.overlay_crop is not None else None
    for label in ("default", "candidate"):
        overlay_path = args.output_root / label / "numbering" / "grouped_numbering_overlay.png"
        render_overlay(
            image_path=args.numbering_image,
            staff_mask_path=args.numbering_staff_mask,
            connector_evidence_path=route_artifacts[label]["connector_evidence_final"],
            numbering_path=route_artifacts[label]["numbering_final"],
            cnn_barlines_path=route_artifacts[label]["barlines"],
            output_path=overlay_path,
            target=target,
            nearby=tuple(args.nearby_bbox),  # type: ignore[arg-type]
            label=label,
            crop=crop,
        )
        overlay_paths[label] = overlay_path

    audit = {
        "schema_version": "issue252.grouped_final_numbering_comparison.v3",
        "status": "completed",
        "config": str(args.config.resolve()),
        "target_bbox": list(target),
        "nearby_bbox": list(args.nearby_bbox),
        "page_number": args.page_number,
        "start_number": args.start_number,
        "x_tolerance": args.x_tolerance,
        "coordinate_contract": coordinate_contract,
        "route_artifacts": {
            label: {
                **{name: str(path.resolve()) for name, path in artifacts.items()},
                "overlay": str(overlay_paths[label].resolve()),
            }
            for label, artifacts in route_artifacts.items()
        },
        "execution_contract": {
            "cnn": "src.pipeline.steps.cnn_scoring._score_directory",
            "cnn_image": str(args.cnn_image.resolve()),
            "numbering_image": str(args.numbering_image.resolve()),
            "cnn_bands_from": (
                str(args.cnn_bands_from.resolve()) if args.cnn_bands_from is not None else None
            ),
            "cnn_input_image_scale": args.cnn_input_image_scale,
            "system_grouping": "MeasureNumberingPipeline/ConnectorAwareSystemBuilder",
            "connector_evidence": (
                "explicit_proxy_masks"
                if args.symbol_mask is not None or args.brace_dot_mask is not None
                else "page_image_ink"
            ),
            "mmr": "src.pipeline.steps.numbering.run_mmr_batch",
            "mmr_override_page_key_remapped_to_isolated_index_zero": True,
            "final_numbering": "MeasureNumberer.number_score with remapped MMR overrides",
            "serialized_staves_are_mask_components_not_musical_staff_count": True,
            "same_x_alone_is_not_grouping_evidence": True,
            "page_wide_geometry_is_a_promotion_gate": True,
        },
        **compare_grouped_final_numbering(
            default_evidence,
            candidate_evidence,
            connector_evidence_equal=connector_evidence_equal,
        ),
    }
    audit_path = args.output_root / "grouped_final_numbering_comparison.json"
    _write(audit_path, audit)
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(audit_path),
                "classification": audit["classification"],
                "overlays": {key: str(value) for key, value in overlay_paths.items()},
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
