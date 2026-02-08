"""Debug rendering helpers for probe detection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import cv2
import numpy as np


def _draw_relative_band_rect(
    crop: np.ndarray,
    band: Any,
    cy1: int,
    cy2: int,
    color: tuple[int, int, int],
) -> None:
    if not band:
        return
    y1, y2 = band
    y1 = max(cy1, int(y1)) - cy1
    y2 = min(cy2, int(y2)) - cy1
    cv2.rectangle(crop, (0, y1), (crop.shape[1] - 1, y2), color, 1)


def _draw_crop_band_overlays(crop: np.ndarray, rec: Dict[str, Any], cy1: int, cy2: int) -> None:
    _draw_relative_band_rect(crop, rec.get("pred_band"), cy1, cy2, (0, 255, 0))
    _draw_relative_band_rect(crop, rec.get("band"), cy1, cy2, (255, 0, 0))
    _draw_relative_band_rect(crop, rec.get("ext_band"), cy1, cy2, (0, 0, 255))
    _draw_relative_band_rect(crop, rec.get("scan_base_band"), cy1, cy2, (0, 255, 255))
    _draw_relative_band_rect(crop, rec.get("scan_band"), cy1, cy2, (0, 165, 255))
    _draw_relative_band_rect(crop, rec.get("scan_ext_band"), cy1, cy2, (128, 0, 255))


def _draw_crop_labels(
    crop: np.ndarray,
    rec: Dict[str, Any],
    *,
    extend_top_max_ratio: float,
    extend_bottom_max_ratio: float,
) -> None:
    ratio = rec.get("ratio")
    top_ratio = rec.get("top_ratio")
    bottom_ratio = rec.get("bottom_ratio")
    ext_ratio = rec.get("extended_ratio")
    scan_row_ratio_mean = rec.get("scan_row_ratio_mean")
    scan_row_ratio_max = rec.get("scan_row_ratio_max")
    scan_row_ratio_lines = rec.get("scan_row_ratio_lines")
    scan_top_h = rec.get("scan_top_h")
    scan_bottom_h = rec.get("scan_bottom_h")
    label = (
        f"{rec.get('status', '')} r={ratio:.2f} ext={ext_ratio:.2f}"
        if ratio is not None and ext_ratio is not None
        else rec.get("status", "")
    )
    cv2.putText(crop, label, (2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    if top_ratio is not None:
        cv2.putText(
            crop,
            f"top={top_ratio:.2f} <{extend_top_max_ratio:.2f}",
            (2, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 255, 0),
            1,
        )
    if bottom_ratio is not None:
        cv2.putText(
            crop,
            f"bot={bottom_ratio:.2f} <{extend_bottom_max_ratio:.2f}",
            (2, 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 0, 255),
            1,
        )
    if scan_row_ratio_mean is not None and scan_row_ratio_max is not None:
        cv2.putText(
            crop,
            f"row_mean={scan_row_ratio_mean:.2f} row_max={scan_row_ratio_max:.2f} lines={scan_row_ratio_lines}",
            (2, 56),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (0, 0, 0),
            1,
        )
    if scan_top_h is not None or scan_bottom_h is not None:
        cv2.putText(
            crop,
            f"top_h={scan_top_h} bot_h={scan_bottom_h}",
            (2, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (0, 0, 0),
            1,
        )


def write_debug_output(
    *,
    base_img: np.ndarray,
    bands: Sequence[Tuple[int, int]],
    debug_records: List[Dict[str, Any]],
    debug_path: Path,
    width: int,
    params: Dict[str, Any],
    divisi_map: Dict[int, Dict[str, bool]],
    extend_top_max_ratio: float,
    extend_bottom_max_ratio: float,
) -> None:
    h, w = base_img.shape[:2]
    overlay = base_img.copy()
    mask_overlay = overlay.copy()
    for y1, y2 in bands:
        cv2.rectangle(mask_overlay, (0, y1), (w - 1, y2), (255, 255, 0), -1)
    overlay = cv2.addWeighted(mask_overlay, 0.2, overlay, 0.8, 0.0)
    for rec in debug_records:
        col = rec.get("col")
        if col is None:
            continue
        color = (0, 255, 0) if rec["status"] == "accepted" else (0, 0, 255)
        cv2.line(overlay, (int(col), 0), (int(col), h - 1), color, 1)
    debug_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(debug_path), overlay)
    debug_json = debug_path.with_suffix(".json")
    debug_json.write_text(
        json.dumps(
            {
                "params": params,
                "bands": bands,
                "divisi_map": divisi_map,
                "records": debug_records,
            },
            indent=2,
        )
    )
    crop_dir = debug_path.parent / "endbar_debug_crops"
    crop_dir.mkdir(parents=True, exist_ok=True)
    for idx, rec in enumerate(debug_records):
        col = rec.get("col")
        if col is None:
            continue
        ext_band = rec.get("ext_band")
        if ext_band:
            cy1, cy2 = ext_band
        else:
            cy1, cy2 = rec.get("band", [0, h - 1])
        cx1 = max(0, int(col) - width * 6)
        cx2 = min(w - 1, int(col) + width * 6)
        cy1 = max(0, int(cy1))
        cy2 = min(h - 1, int(cy2))
        crop = base_img[cy1 : cy2 + 1, cx1 : cx2 + 1].copy()
        if crop.size == 0:
            continue
        _draw_crop_band_overlays(crop, rec, cy1, cy2)
        cv2.line(crop, (int(col - cx1), 0), (int(col - cx1), crop.shape[0] - 1), (0, 0, 255), 1)
        _draw_crop_labels(
            crop,
            rec,
            extend_top_max_ratio=extend_top_max_ratio,
            extend_bottom_max_ratio=extend_bottom_max_ratio,
        )
        name = f"{idx:04d}_{rec.get('status', 'status')}_col{col}.png"
        cv2.imwrite(str(crop_dir / name), crop)
