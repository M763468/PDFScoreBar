#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import shlex
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import cv2
import numpy as np

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo


from src.common.barline_evaluation import BarlineMatch, BarlineSoftMatch

REPO_ROOT = Path(__file__).resolve().parents[2]
if __name__ != "__main__":
    REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
_HOMR_CANDIDATES = (REPO_ROOT / "homr", REPO_ROOT / "external" / "homr")
HOMR_REPO = next((p for p in _HOMR_CANDIDATES if (p / "homr").exists()), _HOMR_CANDIDATES[1])
JST = ZoneInfo("Asia/Tokyo")

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

logger = logging.getLogger("homr_evaluator")

from src.homr_eval_scripts.core.metrics import (
    AggregateMetrics,
    BarlinePrediction,
    ImageMetrics,
)
from src.homr_eval_scripts.core.utils import ensure_dir, timestamp_jst


def save_debug_staff_overlay(
    image_path: Path,
    staff_mask: np.ndarray,
    output_path: Path,
) -> None:
    original = cv2.imread(str(image_path))
    if original is None:
        return

    # Create green overlay for staff lines
    overlay = original.copy()
    overlay[staff_mask > 0] = [0, 255, 0]  # BGR green

    # Alpha blend
    alpha = 0.3
    cv2.addWeighted(overlay, alpha, original, 1 - alpha, 0, original)

    cv2.imwrite(str(output_path), original)


def save_debug_mask_overlay(
    image_path: Path,
    notehead_mask: np.ndarray,
    output_path: Path,
) -> None:
    original = cv2.imread(str(image_path))
    if original is None:
        return

    # Create red overlay for mask
    # Mask is uint8 (0 or >0)
    # Resize already matches original shape

    overlay = original.copy()
    # Where mask is active, set to Red
    overlay[notehead_mask > 0] = [0, 0, 255]  # BGR

    # Alpha blend
    alpha = 0.5
    cv2.addWeighted(overlay, alpha, original, 1 - alpha, 0, original)

    cv2.imwrite(str(output_path), original)


def save_homr_results(
    image_path: Path,
    image_run_dir: Path,
    predictions: List[BarlinePrediction],
    notehead_mask: np.ndarray,
    staff_mask: np.ndarray,
) -> Path:
    """Saves Homr detection results (JSON and masks) to the specified directory."""
    ensure_dir(image_run_dir)
    stem = image_path.stem

    # Save masks
    cv2.imwrite(str(image_run_dir / f"{stem}_notehead_mask.png"), notehead_mask)
    cv2.imwrite(str(image_run_dir / f"{stem}_staff_mask.png"), staff_mask)

    # Save detections.json
    detections_path = image_run_dir / f"{stem}_detections.json"
    with detections_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "image": str(image_path),
                "predictions": [
                    {
                        "pred_bbox": pred.pred_bbox,
                        "orig_bbox": pred.orig_bbox,
                        "system_index": pred.system_index,
                        "staff_index": pred.staff_index,
                    }
                    for pred in predictions
                ],
            },
            fh,
            indent=2,
        )
    return detections_path


def draw_overlay(
    original_image_path: Path,
    predictions: Sequence[BarlinePrediction],
    output_path: Path,
    *,
    matches: Optional[Sequence[BarlineMatch]] = None,
    soft_matches: Optional[Sequence[BarlineSoftMatch]] = None,
    rejected_detections: Optional[Sequence[BarlinePrediction]] = None,
    added_detections: Optional[Sequence[BarlinePrediction]] = None,
    false_positive_indices: Optional[Sequence[int]] = None,
    thickness: int = 2,
) -> None:
    image = cv2.imread(str(original_image_path))
    if image is None:
        raise RuntimeError(f"Failed to read image for overlay: {original_image_path}")
    matched_pred_indices = {m.pred_index for m in matches} if matches else set()
    soft_lookup = {sm.pred_index: sm for sm in soft_matches} if soft_matches else {}
    fp_indices = set(false_positive_indices or [])

    for idx, pred in enumerate(predictions):
        x1, y1, x2, y2 = pred.orig_bbox
        if idx in matched_pred_indices:
            color = (0, 255, 0)
            label = f"TP#{idx}"
        elif idx in soft_lookup:
            reason = soft_lookup[idx].reason
            marker = "dup" if reason == "duplicate" else "rep"
            color = (255, 165, 0)
            label = f"OK#{idx}:{marker}"
        elif fp_indices:
            color = (0, 0, 255)
            label = f"FP#{idx}"
        else:
            color = (0, 0, 255)
            label = f"P#{idx}"

        cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
        cv2.putText(
            image,
            label,
            (x1, max(12, y1 - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1,
            cv2.LINE_AA,
        )

    if rejected_detections:
        for pred in rejected_detections:
            x1, y1, x2, y2 = pred.orig_bbox
            color = (128, 0, 128)  # Purple for rejected stems
            label = "REJECTED_STEM"
            cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
            cv2.putText(
                image,
                label,
                (x1, max(12, y1 - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                color,
                1,
                cv2.LINE_AA,
            )

    if added_detections:
        for pred in added_detections:
            x1, y1, x2, y2 = pred.orig_bbox
            color = (255, 0, 0)  # Blue for end-barline recovery
            label = "END_RECOVERED"
            cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness + 1)
            cv2.putText(
                image,
                label,
                (x1, max(12, y1 - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                color,
                1,
                cv2.LINE_AA,
            )

    ensure_dir(output_path.parent)
    if not cv2.imwrite(str(output_path), image):
        raise RuntimeError(f"Failed to write overlay image: {output_path}")


def write_metrics_json(
    run_dir: Path,
    run_id: str,
    per_image: Sequence[ImageMetrics],
    aggregate: AggregateMetrics,
    extra: Dict[str, Any],
) -> Path:
    payload = {
        "run_id": run_id,
        "timestamp": timestamp_jst(),
        "images": [
            {
                **asdict(metric),
                "matches": [asdict(match) for match in metric.matches],
                "soft_matches": [asdict(sm) for sm in metric.soft_matches],
            }
            for metric in per_image
        ],
        "aggregate": asdict(aggregate),
        "extra": extra,
    }
    path = run_dir / "metrics.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    return path


def write_metrics_csv(
    run_dir: Path, per_image: Sequence[ImageMetrics], aggregate: AggregateMetrics
) -> Path:
    path = run_dir / "metrics.csv"
    fieldnames = [
        "image",
        "num_predictions",
        "num_ground_truth",
        "true_positives",
        "false_positives",
        "false_negatives",
        "precision",
        "recall",
        "f1",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for metric in per_image:
            row = {key: getattr(metric, key) for key in fieldnames}
            writer.writerow(row)
        writer.writerow(
            {
                "image": "aggregate",
                "num_predictions": "-",
                "num_ground_truth": "-",
                "true_positives": aggregate.true_positives,
                "false_positives": aggregate.false_positives,
                "false_negatives": aggregate.false_negatives,
                "precision": aggregate.precision,
                "recall": aggregate.recall,
                "f1": aggregate.f1,
            }
        )
    return path


def write_run_config(
    run_dir: Path,
    run_id: str,
    args: argparse.Namespace,
    git_meta: Dict[str, Optional[str]],
    images: Sequence[Path],
    command_args: Sequence[str],
) -> Path:
    payload = {
        "run_id": run_id,
        "timestamp": timestamp_jst(),
        "command": " ".join(shlex.quote(str(arg)) for arg in command_args),
        "docker_tag": args.docker_tag,
        "git": git_meta,
        "images": [str(path) for path in images],
        "parameters": {
            "iou_threshold": args.iou_threshold,
            "cache": args.cache,
            "write_staff_positions": args.write_staff_positions,
            "timeout": args.timeout,
            "barline_min_height_factor": args.barline_min_height_factor,
            "barline_max_width_factor": args.barline_max_width_factor,
        },
    }
    path = run_dir / "run_config.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    return path


def write_readme(
    run_dir: Path,
    run_id: str,
    per_image: Sequence[ImageMetrics],
    aggregate: AggregateMetrics,
    args: argparse.Namespace,
    ground_truth_summary: Dict[str, Optional[Path]],
) -> Path:
    lines = [
        f"# homr Evaluation Run {run_id}",
        "",
        f"- Timestamp: {timestamp_jst()}",
        f"- Images: {len(per_image)}",
        f"- IoU threshold: {args.iou_threshold}",
        "",
        "## Aggregate Metrics",
        "",
        f"- True Positives: {aggregate.true_positives}",
        f"- False Positives: {aggregate.false_positives}",
        f"- False Negatives: {aggregate.false_negatives}",
        f"- Precision: {aggregate.precision:.4f}",
        f"- Recall: {aggregate.recall:.4f}",
        f"- F1: {aggregate.f1:.4f}",
        "",
        "## Per-image Metrics",
        "",
    ]
    for metric in per_image:
        gt_path = ground_truth_summary.get(metric.image)
        lines.extend(
            [
                f"### {metric.image}",
                f"- Ground truth: {gt_path if gt_path else 'None'}",
                f"- Predictions: {metric.num_predictions}",
                f"- Ground truth boxes: {metric.num_ground_truth}",
                f"- TP/FP/FN: {metric.true_positives}/{metric.false_positives}/{metric.false_negatives}",
                f"- Precision: {metric.precision:.4f}",
                f"- Recall: {metric.recall:.4f}",
                f"- F1: {metric.f1:.4f}",
                "",
            ]
        )
    readme_path = run_dir / "README.md"
    with readme_path.open("w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return readme_path


def write_compare_md(
    run_dir: Path,
    per_image: Sequence[ImageMetrics],
    aggregate: AggregateMetrics,
    baseline_path: Optional[Path],
) -> Path:
    compare_path = run_dir / "compare.md"
    if not baseline_path or not baseline_path.exists():
        with compare_path.open("w", encoding="utf-8") as fh:
            fh.write(
                "# Comparison\n\nBaseline metrics not provided; cannot generate comparison table.\n"
            )
        return compare_path

    with baseline_path.open("r", encoding="utf-8") as fh:
        baseline = json.load(fh)

    baseline_images = {item["image"]: item for item in baseline.get("images", [])}
    baseline_agg = baseline.get("aggregate", {})

    lines = ["# Comparison", ""]
    lines.append(
        "| Image | Precision (baseline → homr) | Recall (baseline → homr) | F1 (baseline → homr) |"
    )
    lines.append("| --- | --- | --- | --- |")
    for metric in per_image:
        base = baseline_images.get(metric.image, {})
        lines.append(
            f"| {metric.image} | {base.get('precision', 'n/a')} → {metric.precision:.4f} | "
            f"{base.get('recall', 'n/a')} → {metric.recall:.4f} | {base.get('f1', 'n/a')} → {metric.f1:.4f} |"
        )

    lines.append("")
    lines.append("## Aggregate")
    lines.append("")
    lines.append(
        "| Metric | Baseline | homr |\n| --- | --- | --- |\n"
        f"| Precision | {baseline_agg.get('precision', 'n/a')} | {aggregate.precision:.4f} |\n"
        f"| Recall | {baseline_agg.get('recall', 'n/a')} | {aggregate.recall:.4f} |\n"
        f"| F1 | {baseline_agg.get('f1', 'n/a')} | {aggregate.f1:.4f} |"
    )

    with compare_path.open("w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    return compare_path


def write_run_sh(run_dir: Path, command_args: Sequence[str]) -> Path:
    path = run_dir / "run.sh"
    with path.open("w", encoding="utf-8") as fh:
        fh.write("#!/usr/bin/env bash\n")
        fh.write("set -euo pipefail\n")
        fh.write('cd "$(dirname "${BASH_SOURCE[0]}")/../.."\n')
        fh.write(
            "python src/homr/homr_evaluator.py "
            + " ".join(shlex.quote(arg) for arg in command_args[1:])
            + "\n"
        )
    os.chmod(path, 0o755)
    return path
