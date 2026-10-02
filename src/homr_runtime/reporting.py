"""Persist HOMR predictions and optional debug masks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import cv2
import numpy as np

from .types import BarlinePrediction
from .utils import ensure_dir


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
