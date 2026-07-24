#!/usr/bin/env python3
"""Trace one verified fresh detector target through hybrid and probe candidate stages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

from src.pipeline.core.config import load_yaml
from src.pipeline.detection.config import get_probe_kwargs
from src.pipeline.probe_detector import detect_probe_scan
from src.pipeline.probe_detector.bands import build_row_stats
from src.pipeline.steps.candidate_filters import filter_probe_candidates, trim_box_to_ink
from src.pipeline.steps.hybrid_consensus import apply_hybrid_consensus_filter, load_json_boxes
from src.pipeline.steps.probe_scan import (
    _extract_candidate_postprocess_cfg,
    _resolve_scale_aware_probe_kwargs,
)
from tools.issue252.probe_boundary import (
    Box,
    artifact_record,
    classify_first_loss,
    load_json,
    normalize_box,
    sha256,
    split_tall_existing_boxes,
    stage_summary,
    target_metrics,
    validate_fresh_contract_payload,
    write_json,
)

DEFAULT_SWEEP = (0.0, 0.01, 0.05, 0.10, 0.25, 0.50, 0.75)


def _detection_config(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = load_yaml(path)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("detection"), Mapping):
        raise ValueError(f"Missing detection mapping: {path}")
    cfg = dict(payload["detection"])
    resolved = {
        "band_source": cfg.get("band_source", "row_stats"),
        "band_cluster_max_dist": cfg.get("band_cluster_max_dist"),
        "band_min_row_count": int(cfg.get("band_min_row_count", 1)),
        "ink_threshold": int(cfg.get("ink_threshold", 180)),
        "min_ratio": float(cfg.get("min_ratio", 0.85)),
        "min_height_ratio": float(cfg.get("min_height_ratio", 0.012)),
        "min_width_ratio": float(cfg.get("min_width_ratio", 0.0)),
        "vertical_closing": int(cfg.get("vertical_closing", 4)),
        "enable_heuristic_filters": bool(cfg.get("enable_heuristic_filters", False)),
        "candidate_filter_kwargs": dict(cfg.get("candidate_filter_kwargs") or {}),
    }
    return cfg, resolved


def _load_mask(
    path: Path | None,
    image: np.ndarray,
    *,
    label: str,
    allow_zero_fallback: bool,
) -> tuple[np.ndarray, str]:
    if path is None:
        if not allow_zero_fallback:
            raise ValueError(
                f"{label} is required unless --allow-zero-{label.replace('_', '-')} is supplied"
            )
        return np.zeros(image.shape[:2], dtype=np.uint8), "explicit_zero_fallback"
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(path)
    if mask.shape[:2] != image.shape[:2]:
        mask = cv2.resize(
            mask,
            (image.shape[1], image.shape[0]),
            interpolation=cv2.INTER_NEAREST,
        )
    return mask, "artifact"


def _scale_box(box: Box, scale: float) -> Box:
    return normalize_box([float(value) * scale for value in box])


def _validate_probe_geometry(
    source_image: np.ndarray,
    probe_image: np.ndarray,
    input_image_scale: float,
) -> None:
    if input_image_scale <= 0:
        raise ValueError("input_image_scale must be positive")
    source_h, source_w = source_image.shape[:2]
    probe_h, probe_w = probe_image.shape[:2]
    expected_w = int(round(source_w * input_image_scale))
    expected_h = int(round(source_h * input_image_scale))
    if abs(probe_w - expected_w) > 2 or abs(probe_h - expected_h) > 2:
        raise ValueError(
            "Probe image dimensions do not match input_image_scale: "
            f"source={source_w}x{source_h} probe={probe_w}x{probe_h} "
            f"scale={input_image_scale}"
        )


def _paper_side_context_ratio(
    image: np.ndarray,
    box: Box,
    *,
    paper_threshold: int,
    width_ratio: float,
) -> float:
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    x1, y1, x2, y2 = box
    x_lo, x_hi = max(0, min(x1, x2)), min(width, max(x1, x2))
    y_lo, y_hi = max(0, min(y1, y2)), min(height, max(y1, y2))
    if x_hi <= x_lo or y_hi <= y_lo or width_ratio <= 0:
        return 0.0
    candidate_width = max(1, x_hi - x_lo)
    context_width = max(1, int(round(candidate_width * width_ratio)))
    strips = []
    left_lo = max(0, x_lo - context_width)
    right_hi = min(width, x_hi + context_width)
    if left_lo < x_lo:
        strips.append(gray[y_lo:y_hi, left_lo:x_lo])
    if x_hi < right_hi:
        strips.append(gray[y_lo:y_hi, x_hi:right_hi])
    bright = sum(int((strip > paper_threshold).sum()) for strip in strips)
    total = sum(int(strip.size) for strip in strips)
    return float(bright) / float(max(1, total))


def _apply_candidate_filter(
    *,
    candidates: list[Box],
    image: np.ndarray,
    existing_boxes: list[Box],
    staff_mask: np.ndarray | None,
    clef_mask: np.ndarray,
    filter_kwargs: Mapping[str, Any],
    experimental_side_context_width_ratio: float,
) -> tuple[list[Box], list[dict[str, Any]]]:
    if experimental_side_context_width_ratio <= 0:
        return filter_probe_candidates(
            candidates=candidates,
            image=image,
            existing_boxes=existing_boxes,
            staff_mask=staff_mask,
            clef_mask=clef_mask,
            **dict(filter_kwargs),
        )

    kwargs = dict(filter_kwargs)
    minimum = float(kwargs.get("min_paper_overlap_ratio", 0.6))
    paper_threshold = int(kwargs.get("paper_threshold", 200))
    kwargs["min_paper_overlap_ratio"] = 0.0
    kept, dropped = filter_probe_candidates(
        candidates=candidates,
        image=image,
        existing_boxes=existing_boxes,
        staff_mask=staff_mask,
        clef_mask=clef_mask,
        **kwargs,
    )
    final = []
    for box in kept:
        ratio = _paper_side_context_ratio(
            image,
            box,
            paper_threshold=paper_threshold,
            width_ratio=experimental_side_context_width_ratio,
        )
        if ratio < minimum:
            dropped.append(
                {
                    "bbox": box,
                    "reasons": ["low_paper_overlap"],
                    "experimental_paper_side_context_ratio": ratio,
                }
            )
        else:
            final.append(box)
    return final, dropped


def _run_variant(
    *,
    name: str,
    image: np.ndarray,
    staff_mask: np.ndarray,
    clef_mask: np.ndarray,
    existing_boxes: list[Box],
    cfg: Mapping[str, Any],
    resolved: Mapping[str, Any],
    output_root: Path,
    disable_suppression: bool,
    vertical_iou: float,
    targets: Mapping[str, Box],
    accepted_iou: float,
    experimental_side_context_width_ratio: float,
) -> dict[str, Any]:
    row_stats = build_row_stats(
        existing_boxes,
        cluster_max_dist=resolved["band_cluster_max_dist"],
        min_row_count=int(resolved["band_min_row_count"]),
    )
    kwargs = get_probe_kwargs(dict(cfg))
    kwargs["scan_disable_existing_suppression"] = disable_suppression
    kwargs["scan_existing_min_vertical_iou"] = vertical_iou
    kwargs = _resolve_scale_aware_probe_kwargs(kwargs, existing_boxes)
    kwargs, post_cfg = _extract_candidate_postprocess_cfg(kwargs, existing_boxes)
    if post_cfg:
        raise ValueError("Optional probe postprocess pseudo-keys are not supported by this trace")
    band_source = str(kwargs.pop("band_source", resolved["band_source"]))
    debug_png = output_root / name / "probe_debug.png"
    raw = [
        normalize_box(box)
        for box in detect_probe_scan(
            base_img=image,
            staff_mask=staff_mask,
            existing_boxes=existing_boxes,
            row_stats=row_stats,
            band_source=band_source,
            band_cluster_max_dist=resolved["band_cluster_max_dist"],
            band_min_row_count=int(resolved["band_min_row_count"]),
            ink_threshold=int(resolved["ink_threshold"]),
            min_ratio=float(resolved["min_ratio"]),
            vertical_closing=int(resolved["vertical_closing"]),
            debug_path=debug_png,
            **kwargs,
        )
    ]

    height, width = image.shape[:2]
    min_h = int(height * float(resolved["min_height_ratio"]))
    min_w = int(width * float(resolved["min_width_ratio"]))
    size_filtered = [
        box for box in raw if abs(box[3] - box[1]) >= min_h and abs(box[2] - box[0]) >= min_w
    ]
    if resolved["enable_heuristic_filters"]:
        heuristic_filtered, dropped = _apply_candidate_filter(
            candidates=size_filtered,
            image=image,
            existing_boxes=existing_boxes,
            staff_mask=staff_mask if band_source == "staff_mask" else None,
            clef_mask=clef_mask,
            filter_kwargs=dict(resolved["candidate_filter_kwargs"]),
            experimental_side_context_width_ratio=experimental_side_context_width_ratio,
        )
    else:
        heuristic_filtered, dropped = list(size_filtered), []
    trimmed = [
        normalize_box(trim_box_to_ink(image, box, ink_threshold=int(resolved["ink_threshold"])))
        for box in heuristic_filtered
    ]
    trimmed = [
        box for box in trimmed if abs(box[3] - box[1]) >= min_h and abs(box[2] - box[0]) >= min_w
    ]
    final = sorted(
        {
            *(
                box
                for box in existing_boxes
                if abs(box[3] - box[1]) >= min_h and abs(box[2] - box[0]) >= min_w
            ),
            *trimmed,
        }
    )
    stages = {
        "raw": raw,
        "size_filtered": size_filtered,
        "heuristic_filtered": heuristic_filtered,
        "trimmed": trimmed,
        "final": final,
    }
    stage_paths = {}
    for stage_name, stage_boxes in stages.items():
        stage_path = output_root / name / f"{stage_name}_candidates.json"
        write_json(stage_path, [list(box) for box in stage_boxes])
        stage_paths[stage_name] = str(stage_path)

    result = {
        "name": name,
        "disable_existing_suppression": disable_suppression,
        "vertical_iou": vertical_iou,
        "band_source": band_source,
        "experimental_paper_side_context_width_ratio": experimental_side_context_width_ratio,
        "row_stats": row_stats,
        "counts": {key: len(value) for key, value in stages.items()},
        "counts_existing": len(existing_boxes),
        "counts_dropped": len(dropped),
        "targets": {
            target_name: stage_summary(
                reference=reference,
                stages=stages,
                dropped=dropped,
                debug_json=debug_png.with_suffix(".json"),
                row_stats=row_stats,
                accepted_iou=accepted_iou,
            )
            for target_name, reference in targets.items()
        },
        "paths": {
            "debug_png": str(debug_png),
            "debug_json": str(debug_png.with_suffix(".json")),
            "stage_candidates": stage_paths,
        },
    }
    write_json(output_root / name / "variant_report.json", result)
    return result


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    contract_payload = load_json(args.input_contract)
    if not isinstance(contract_payload, Mapping):
        raise ValueError(f"Expected object contract: {args.input_contract}")
    contract = validate_fresh_contract_payload(contract_payload)

    source_image = cv2.imread(str(args.image), cv2.IMREAD_COLOR)
    if source_image is None:
        raise FileNotFoundError(args.image)
    actual_image_sha = sha256(args.image)
    if actual_image_sha != args.expected_image_sha256:
        raise ValueError(
            f"Image SHA-256 mismatch: expected={args.expected_image_sha256} actual={actual_image_sha}"
        )

    probe_image_path = args.probe_image or args.image
    probe_image = cv2.imread(str(probe_image_path), cv2.IMREAD_COLOR)
    if probe_image is None:
        raise FileNotFoundError(probe_image_path)
    input_image_scale = float(args.input_image_scale)
    _validate_probe_geometry(source_image, probe_image, input_image_scale)

    cfg, resolved = _detection_config(args.config)
    paths = {
        "fresh_baseline": args.fresh_baseline,
        "current_sr": args.current_sr,
        "current_omr": args.current_omr,
        "hybrid": args.hybrid,
    }
    boxes = {
        name: [normalize_box(box) for box in load_json_boxes(path)] for name, path in paths.items()
    }
    regenerated = [
        normalize_box(box)
        for box in apply_hybrid_consensus_filter(
            baseline_boxes=boxes["fresh_baseline"],
            sr_boxes=boxes["current_sr"],
            omr_boxes=boxes["current_omr"],
            iou_thresh=args.consensus_iou,
        )
    ]
    if sorted(regenerated) != sorted(boxes["hybrid"]):
        raise ValueError("Saved hybrid is not reproduced from the supplied source artifacts")

    staff_mask, staff_mask_source = _load_mask(
        args.staff_mask,
        probe_image,
        label="staff_mask",
        allow_zero_fallback=args.allow_zero_staff_mask,
    )
    clef_mask, clef_mask_source = _load_mask(
        args.clef_mask,
        probe_image,
        label="clef_mask",
        allow_zero_fallback=args.allow_zero_clef_mask,
    )
    scaled_existing = [_scale_box(box, input_image_scale) for box in boxes["hybrid"]]
    existing = split_tall_existing_boxes(
        probe_image,
        scaled_existing,
        ink_threshold=int(resolved["ink_threshold"]),
    )
    targets = {
        "missing": normalize_box(args.missing_reference),
        "nearby": normalize_box(args.nearby_reference),
    }
    probe_targets = {
        name: _scale_box(reference, input_image_scale) for name, reference in targets.items()
    }
    source_trace = {
        target_name: {
            source_name: target_metrics(reference, source, accepted_iou=args.accepted_iou)
            for source_name, source in boxes.items()
        }
        for target_name, reference in targets.items()
    }

    variants = {
        "suppression_default": _run_variant(
            name="suppression_default",
            image=probe_image,
            staff_mask=staff_mask,
            clef_mask=clef_mask,
            existing_boxes=existing,
            cfg=cfg,
            resolved=resolved,
            output_root=args.output_root,
            disable_suppression=False,
            vertical_iou=0.0,
            targets=probe_targets,
            accepted_iou=args.accepted_iou,
            experimental_side_context_width_ratio=args.experimental_paper_side_context_width_ratio,
        ),
        "suppression_off": _run_variant(
            name="suppression_off",
            image=probe_image,
            staff_mask=staff_mask,
            clef_mask=clef_mask,
            existing_boxes=existing,
            cfg=cfg,
            resolved=resolved,
            output_root=args.output_root,
            disable_suppression=True,
            vertical_iou=0.0,
            targets=probe_targets,
            accepted_iou=args.accepted_iou,
            experimental_side_context_width_ratio=args.experimental_paper_side_context_width_ratio,
        ),
    }
    for value in args.vertical_iou_sweep:
        if value <= 0:
            continue
        name = f"vertical_iou_{value:g}".replace(".", "p")
        variants[name] = _run_variant(
            name=name,
            image=probe_image,
            staff_mask=staff_mask,
            clef_mask=clef_mask,
            existing_boxes=existing,
            cfg=cfg,
            resolved=resolved,
            output_root=args.output_root,
            disable_suppression=False,
            vertical_iou=float(value),
            targets=probe_targets,
            accepted_iou=args.accepted_iou,
            experimental_side_context_width_ratio=args.experimental_paper_side_context_width_ratio,
        )

    report = {
        "schema_version": "issue252.probe_boundary.v4",
        "status": "completed",
        "score": args.score,
        "page": args.page,
        "targets": {name: list(box) for name, box in targets.items()},
        "probe_targets": {name: list(box) for name, box in probe_targets.items()},
        "coordinate_space": {
            "source": "original_image_pixels",
            "probe": "probe_image_pixels",
            "probe_input_scale": input_image_scale,
            "stage_candidate_files": "probe_image_pixels",
            "source_trace": "original_image_pixels",
        },
        "detector_input_contract": contract,
        "artifacts": {
            "input_contract": artifact_record(args.input_contract),
            "config": artifact_record(args.config),
            "image": artifact_record(args.image),
            "probe_image": artifact_record(probe_image_path),
            **{name: artifact_record(path) for name, path in paths.items()},
            **({"staff_mask": artifact_record(args.staff_mask)} if args.staff_mask else {}),
            **({"clef_mask": artifact_record(args.clef_mask)} if args.clef_mask else {}),
        },
        "mask_sources": {
            "staff_mask": staff_mask_source,
            "clef_mask": clef_mask_source,
        },
        "resolved_detection_config": resolved,
        "consensus_reproduction": {
            "saved_count": len(boxes["hybrid"]),
            "regenerated_count": len(regenerated),
            "semantic_equal": True,
        },
        "source_trace": source_trace,
        "existing_boxes_after_seed_split": len(existing),
        "variants": variants,
        "classification": classify_first_loss(source_trace=source_trace, variants=variants),
        "experimental_paper_side_context_width_ratio": (
            args.experimental_paper_side_context_width_ratio
        ),
        "production_default_changed": False,
        "high_cost_inference_executed": False,
    }
    write_json(args.output_root / "probe_boundary_report.json", report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-contract", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/dense_full_pipeline.yaml"))
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--probe-image", type=Path)
    parser.add_argument("--input-image-scale", type=float, default=1.0)
    parser.add_argument("--expected-image-sha256", required=True)
    parser.add_argument("--fresh-baseline", type=Path, required=True)
    parser.add_argument("--current-sr", type=Path, required=True)
    parser.add_argument("--current-omr", type=Path, required=True)
    parser.add_argument("--hybrid", type=Path, required=True)
    parser.add_argument("--staff-mask", type=Path)
    parser.add_argument("--clef-mask", type=Path)
    parser.add_argument("--allow-zero-staff-mask", action="store_true")
    parser.add_argument("--allow-zero-clef-mask", action="store_true")
    parser.add_argument("--score", required=True)
    parser.add_argument("--page", required=True)
    parser.add_argument("--missing-reference", nargs=4, type=int, required=True)
    parser.add_argument("--nearby-reference", nargs=4, type=int, required=True)
    parser.add_argument("--accepted-iou", type=float, default=0.5)
    parser.add_argument("--experimental-paper-side-context-width-ratio", type=float, default=0.0)
    parser.add_argument("--consensus-iou", type=float, default=0.5)
    parser.add_argument("--vertical-iou-sweep", nargs="+", type=float, default=DEFAULT_SWEEP)
    parser.add_argument("--output-root", type=Path, default=Path("logs/issue252_probe_boundary"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = build_report(args)
    except Exception as error:  # noqa: BLE001
        failure = {
            "schema_version": "issue252.probe_boundary.v4",
            "status": "failed",
            "error_type": type(error).__name__,
            "error": str(error),
        }
        write_json(args.output_root / "probe_boundary_report.json", failure)
        print(json.dumps(failure), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "classification": report["classification"],
                "output": str(args.output_root / "probe_boundary_report.json"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
