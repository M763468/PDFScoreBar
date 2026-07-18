#!/usr/bin/env python3
"""Trace one reference barline through saved fresh detector artifacts.

This tool does not run HOMR, SR, OMR-DLN, probe detection, or CNN. It reads a
completed fresh score run and identifies the first saved layer where the target
geometry is no longer represented.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from src.common import barline_iou
from src.pipeline.core.run_ids import build_probe_run_id_from_parts
from src.pipeline.steps.hybrid_consensus import load_json_boxes

Box = tuple[int, int, int, int]


def normalize_box(value: Sequence[Any]) -> Box:
    if len(value) < 4:
        raise ValueError(f"Invalid bbox: {value}")
    return tuple(int(round(float(item))) for item in value[:4])  # type: ignore[return-value]


def load_scored_boxes(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected scored list: {path}")
    records: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            bbox = item.get("bbox", item.get("pred_bbox"))
            if bbox is None:
                continue
            records.append(
                {
                    "bbox": normalize_box(bbox),
                    "score": float(item["score"]) if item.get("score") is not None else None,
                }
            )
        elif isinstance(item, (list, tuple)) and len(item) >= 4:
            records.append({"bbox": normalize_box(item), "score": None})
    return records


def first_existing(paths: Iterable[Path]) -> Path | None:
    return next((path for path in paths if path.is_file()), None)


def layer_paths(
    *, hybrid_output_dir: Path, probe_output_root: Path, score: str, page: str
) -> dict[str, Path | None]:
    probe_run_id = build_probe_run_id_from_parts(score, page)
    probe_dirs = (
        probe_output_root / probe_run_id,
        probe_output_root / score / page,
        probe_output_root / f"eval2_{score}_{page}",
    )
    return {
        "baseline_homr": first_existing(
            (
                hybrid_output_dir / "baseline" / "batch" / page / f"{page}_detections.json",
                hybrid_output_dir / "baseline" / page / f"{page}_detections.json",
            )
        ),
        "sr_homr": first_existing(
            (
                hybrid_output_dir / "sr" / "batch" / page / f"{page}_detections.json",
                hybrid_output_dir / "sr" / page / f"{page}_detections.json",
            )
        ),
        "omr_dln": first_existing(
            (
                hybrid_output_dir / "omr_sr" / page / "predictions.json",
                hybrid_output_dir / "omr" / page / "predictions.json",
            )
        ),
        "hybrid": first_existing(
            (
                hybrid_output_dir / "hybrid_results" / f"{page}_hybrid.json",
                hybrid_output_dir / f"{page}_hybrid.json",
            )
        ),
        "probe_candidates": first_existing(
            directory / "pipeline2_no_peak_candidates.json" for directory in probe_dirs
        ),
        "cnn_scored": first_existing(
            directory / "pipeline2_no_peak_scored.json" for directory in probe_dirs
        ),
    }


def bbox_metrics(reference: Box, box: Box) -> dict[str, Any]:
    ref_x = (reference[0] + reference[2]) / 2.0
    ref_y = (reference[1] + reference[3]) / 2.0
    box_x = (box[0] + box[2]) / 2.0
    box_y = (box[1] + box[3]) / 2.0
    vertical_overlap = max(0, min(reference[3], box[3]) - max(reference[1], box[1]))
    return {
        "bbox": list(box),
        "iou": float(barline_iou(reference, box)),
        "x_center_distance": abs(ref_x - box_x),
        "y_center_distance": abs(ref_y - box_y),
        "vertical_overlap_px": vertical_overlap,
        "reference_center_y_inside": box[1] <= ref_y <= box[3],
    }


def summarize_boxes(
    *, reference: Box, boxes: Iterable[Box], accepted_iou: float, x_tolerance: float
) -> dict[str, Any]:
    metrics = [bbox_metrics(reference, box) for box in boxes]
    ranked = sorted(
        metrics,
        key=lambda item: (
            -item["iou"],
            item["x_center_distance"],
            item["y_center_distance"],
            item["bbox"],
        ),
    )
    best = ranked[0] if ranked else None
    x_aligned = sorted(
        (item for item in metrics if item["x_center_distance"] <= x_tolerance),
        key=lambda item: (
            item["y_center_distance"],
            -item["vertical_overlap_px"],
            item["bbox"],
        ),
    )[:10]
    same_vertical_region = sorted(
        (item for item in metrics if item["vertical_overlap_px"] > 0),
        key=lambda item: (
            item["x_center_distance"],
            -item["vertical_overlap_px"],
            item["bbox"],
        ),
    )[:10]
    return {
        "count": len(metrics),
        "accepted": bool(best is not None and best["iou"] > accepted_iou),
        "best_match": best,
        "x_aligned_nearest": x_aligned,
        "vertical_region_nearest": same_vertical_region,
    }


def summarize_layer(
    *,
    name: str,
    path: Path | None,
    reference: Box,
    accepted_iou: float,
    x_tolerance: float,
    score_threshold: float,
) -> dict[str, Any]:
    if path is None:
        return {"name": name, "path": None, "status": "missing_artifact"}
    if name == "cnn_scored":
        records = load_scored_boxes(path)
        summary = summarize_boxes(
            reference=reference,
            boxes=[item["bbox"] for item in records],
            accepted_iou=accepted_iou,
            x_tolerance=x_tolerance,
        )
        score_by_box = {item["bbox"]: item["score"] for item in records}
        best = summary["best_match"]
        best_score = score_by_box.get(normalize_box(best["bbox"])) if best else None
        summary.update(
            {
                "name": name,
                "path": str(path),
                "status": "loaded",
                "best_score": best_score,
                "cnn_accepted": bool(
                    summary["accepted"]
                    and best_score is not None
                    and best_score >= score_threshold
                ),
            }
        )
        return summary

    boxes = [normalize_box(box) for box in load_json_boxes(path)]
    summary = summarize_boxes(
        reference=reference,
        boxes=boxes,
        accepted_iou=accepted_iou,
        x_tolerance=x_tolerance,
    )
    summary.update({"name": name, "path": str(path), "status": "loaded"})
    return summary


def classify(layers: dict[str, dict[str, Any]]) -> str:
    sources = [layers[name] for name in ("baseline_homr", "sr_homr", "omr_dln")]
    source_supported = any(item.get("accepted", False) for item in sources)
    hybrid_supported = layers["hybrid"].get("accepted", False)
    probe_supported = layers["probe_candidates"].get("accepted", False)
    scored_supported = layers["cnn_scored"].get("accepted", False)
    cnn_accepted = layers["cnn_scored"].get("cnn_accepted", False)

    if not source_supported:
        return "absent_from_all_upstream_detectors"
    if not hybrid_supported:
        return "lost_in_hybrid_consensus"
    if not probe_supported:
        return "lost_in_probe_generation_or_postprocess"
    if not scored_supported:
        return "lost_before_or_during_cnn_scoring"
    if not cnn_accepted:
        return "cnn_rejected"
    return "accepted"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    reference = normalize_box(args.reference)
    paths = layer_paths(
        hybrid_output_dir=args.hybrid_output_dir,
        probe_output_root=args.probe_output_root,
        score=args.score,
        page=args.page,
    )
    layers = {
        name: summarize_layer(
            name=name,
            path=path,
            reference=reference,
            accepted_iou=args.accepted_iou,
            x_tolerance=args.x_tolerance,
            score_threshold=args.score_threshold,
        )
        for name, path in paths.items()
    }
    return {
        "schema_version": "issue245.fresh_detector_layer_trace.v1",
        "score": args.score,
        "page": args.page,
        "reference": list(reference),
        "hybrid_output_dir": str(args.hybrid_output_dir),
        "probe_output_root": str(args.probe_output_root),
        "accepted_iou": args.accepted_iou,
        "x_tolerance": args.x_tolerance,
        "score_threshold": args.score_threshold,
        "classification": classify(layers),
        "layers": layers,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hybrid-output-dir", type=Path, required=True)
    parser.add_argument("--probe-output-root", type=Path, required=True)
    parser.add_argument("--score", required=True)
    parser.add_argument("--page", required=True)
    parser.add_argument("--reference", nargs=4, type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--accepted-iou", type=float, default=0.5)
    parser.add_argument("--x-tolerance", type=float, default=12.0)
    parser.add_argument("--score-threshold", type=float, default=0.1)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = build_report(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"classification": report["classification"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
