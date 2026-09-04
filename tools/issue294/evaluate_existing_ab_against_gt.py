#!/usr/bin/env python3
"""Evaluate existing Issue #294 A/B barline detections against ground truth.

This is a no-inference experiment helper.  It consumes an already completed
same-original A/B summary and evaluates the A and B HOMR producer detections
with the same barline metric implementation used by the accepted Issue #255
checkpoint.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from src.homr_eval_scripts.core.metrics import (
    BarlinePrediction,
    compute_metrics,
    load_ground_truth_boxes,
)

ACCEPTED_CHECKPOINT = "f431860d770c20d43f5d40f1e07ef33983c4c07b"
DEFAULT_IOU_THRESHOLD = 0.5


def _load_mapping(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON mapping: {path}")
    return payload


def _resolve_gt(ground_truth_root: Path, image: Path) -> tuple[Path, str]:
    stem = image.stem
    score = image.parent.name
    candidates = [
        ("historical_explicit_mapping", ground_truth_root / stem / "boxes_sorted.json"),
        ("ground_truth_dir_flat", ground_truth_root / f"{stem}.json"),
        ("score_scoped_boxes_sorted", ground_truth_root / score / stem / "boxes_sorted.json"),
        ("score_scoped_flat", ground_truth_root / score / f"{stem}.json"),
    ]
    existing = [(mode, path.resolve()) for mode, path in candidates if path.is_file()]
    if not existing:
        expected = "\n".join(f"  - {path}" for _, path in candidates)
        raise FileNotFoundError(f"No GT JSON found for {image}. Checked:\n{expected}")
    if len(existing) > 1:
        details = "\n".join(f"  - {mode}: {path}" for mode, path in existing)
        raise ValueError(
            f"Ambiguous GT JSON for {image}; pass a narrower --ground-truth-root:\n{details}"
        )
    return existing[0][1], existing[0][0]


def _detection_path(page: dict[str, Any], variant: str) -> Path:
    payload = page.get(variant)
    if not isinstance(payload, dict):
        raise ValueError(f"Page summary lacks {variant}")
    if variant == "A_pinned":
        artifacts = payload.get("artifacts")
    else:
        worker = payload.get("worker")
        if not isinstance(worker, dict):
            raise ValueError("Page summary lacks maintained worker payload")
        artifacts = worker.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts.get("detections"):
        raise ValueError(f"Page summary lacks {variant} detections")
    path = Path(str(artifacts["detections"]))
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.resolve()


def _load_predictions(path: Path) -> list[BarlinePrediction]:
    payload = _load_mapping(path)
    raw_predictions = payload.get("predictions")
    if not isinstance(raw_predictions, list):
        raise ValueError(f"Detection payload lacks predictions: {path}")
    predictions: list[BarlinePrediction] = []
    for index, item in enumerate(raw_predictions):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid prediction #{index} in {path}")
        orig_bbox = item.get("orig_bbox")
        pred_bbox = item.get("pred_bbox", orig_bbox)
        if not isinstance(orig_bbox, (list, tuple)) or len(orig_bbox) != 4:
            raise ValueError(f"Invalid orig_bbox #{index} in {path}: {orig_bbox!r}")
        if not isinstance(pred_bbox, (list, tuple)) or len(pred_bbox) != 4:
            raise ValueError(f"Invalid pred_bbox #{index} in {path}: {pred_bbox!r}")
        predictions.append(
            BarlinePrediction(
                pred_bbox=tuple(int(value) for value in pred_bbox),
                orig_bbox=tuple(int(value) for value in orig_bbox),
                system_index=int(item.get("system_index", -1)),
                staff_index=int(item.get("staff_index", -1)),
            )
        )
    return predictions


def _summarize_variant(
    detection: Path,
    ground_truth: list[tuple[int, int, int, int]],
    iou_threshold: float,
) -> dict[str, Any]:
    predictions = _load_predictions(detection)
    metrics, match_result = compute_metrics(predictions, ground_truth, iou_threshold)
    ious = [float(match.iou) for match in match_result.matches]
    soft_reasons = Counter(match.reason for match in match_result.soft_matches)
    return {
        "detections": str(detection),
        "pred": metrics.num_predictions,
        "gt": metrics.num_ground_truth,
        "tp": metrics.true_positives,
        "fp": metrics.false_positives,
        "fn": metrics.false_negatives,
        "precision": metrics.precision,
        "recall": metrics.recall,
        "f1": metrics.f1,
        "soft_match_count": len(match_result.soft_matches),
        "soft_match_reasons": dict(sorted(soft_reasons.items())),
        "matched_iou": {
            "count": len(ious),
            "mean": sum(ious) / len(ious) if ious else None,
            "min": min(ious) if ious else None,
            "max": max(ious) if ious else None,
        },
        "false_positive_indices": list(match_result.false_positive_indices),
        "false_negative_indices": list(match_result.false_negative_indices),
    }


def _metric_delta(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {
        "pred": int(b["pred"]) - int(a["pred"]),
        "tp": int(b["tp"]) - int(a["tp"]),
        "fp": int(b["fp"]) - int(a["fp"]),
        "fn": int(b["fn"]) - int(a["fn"]),
        "precision": float(b["precision"]) - float(a["precision"]),
        "recall": float(b["recall"]) - float(a["recall"]),
        "f1": float(b["f1"]) - float(a["f1"]),
    }


def _aggregate(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    gt = sum(int(row[variant]["gt"]) for row in rows)
    pred = sum(int(row[variant]["pred"]) for row in rows)
    tp = sum(int(row[variant]["tp"]) for row in rows)
    fp = sum(int(row[variant]["fp"]) for row in rows)
    fn = sum(int(row[variant]["fn"]) for row in rows)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "gt": gt,
        "pred": pred,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def run(
    summary_path: Path,
    ground_truth_root: Path,
    output: Path,
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
) -> dict[str, Any]:
    summary_path = summary_path.resolve()
    ground_truth_root = ground_truth_root.resolve()
    output = output.resolve()
    if not ground_truth_root.is_dir():
        raise FileNotFoundError(ground_truth_root)
    if output.exists():
        raise FileExistsError(output)

    summary = _load_mapping(summary_path)
    if summary.get("status") != "completed":
        raise ValueError(f"A/B summary is incomplete: {summary_path}")
    pages_payload = summary.get("pages")
    if not isinstance(pages_payload, list) or not pages_payload:
        raise ValueError("A/B summary has no pages")

    pages: list[dict[str, Any]] = []
    for raw_page in pages_payload:
        if not isinstance(raw_page, dict):
            raise ValueError("A/B summary contains invalid page entry")
        image_value = raw_page.get("image")
        if not isinstance(image_value, str):
            raise ValueError("A/B page lacks image")
        image = Path(image_value)
        gt_path, gt_mode = _resolve_gt(ground_truth_root, image)
        ground_truth = load_ground_truth_boxes(gt_path)
        a = _summarize_variant(_detection_path(raw_page, "A_pinned"), ground_truth, iou_threshold)
        b = _summarize_variant(
            _detection_path(raw_page, "B_maintained"), ground_truth, iou_threshold
        )
        pages.append(
            {
                "image": str(image),
                "ground_truth": {
                    "path": str(gt_path),
                    "resolution_mode": gt_mode,
                    "count": len(ground_truth),
                },
                "A_pinned": a,
                "B_maintained": b,
                "B_minus_A": _metric_delta(a, b),
                "B_improves_f1": float(b["f1"]) > float(a["f1"]),
                "B_improves_recall": float(b["recall"]) > float(a["recall"]),
                "B_improves_precision": float(b["precision"]) > float(a["precision"]),
            }
        )

    aggregate_a = _aggregate(pages, "A_pinned")
    aggregate_b = _aggregate(pages, "B_maintained")
    report = {
        "schema_version": "issue294.same_original_gt_detection_comparison.v1",
        "status": "completed",
        "scope": "standalone_homr_barline_producer_against_gt",
        "not_stage_e_final_cnn_metric": True,
        "summary": str(summary_path),
        "ground_truth_root": str(ground_truth_root),
        "evaluation_contract": {
            "issue255_accepted_checkpoint": ACCEPTED_CHECKPOINT,
            "iou_threshold": iou_threshold,
            "metric": "src.homr_eval_scripts.core.metrics.compute_metrics",
            "coordinate_space": "orig_bbox/original_page",
        },
        "pages": pages,
        "aggregate": {
            "A_pinned": aggregate_a,
            "B_maintained": aggregate_b,
            "B_minus_A": _metric_delta(aggregate_a, aggregate_b),
            "B_improves_f1": aggregate_b["f1"] > aggregate_a["f1"],
            "B_improves_recall": aggregate_b["recall"] > aggregate_a["recall"],
            "B_improves_precision": aggregate_b["precision"] > aggregate_a["precision"],
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--ground-truth-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iou-threshold", type=float, default=DEFAULT_IOU_THRESHOLD)
    args = parser.parse_args()
    try:
        report = run(
            args.summary,
            args.ground_truth_root,
            args.output,
            args.iou_threshold,
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
            {
                "status": "completed",
                "output": str(args.output.resolve()),
                "aggregate": report["aggregate"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
