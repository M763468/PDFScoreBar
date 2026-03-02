"""Filtering helpers for blank/staff checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2  # type: ignore

from src.pipeline.config import get_nested


def get_user_exclude_indices(config: Dict[str, Any]) -> set[int]:
    filters = get_nested(config, "filters", default={}) or {}
    exclude = filters.get("user_exclude", []) or []
    if isinstance(exclude, list):
        return {int(item) for item in exclude}
    return set()


def is_blank_page(
    image_path: Path, config: Dict[str, Any]
) -> Tuple[Optional[bool], Dict[str, float]]:
    blank_cfg = get_nested(config, "filters", "blank_page_config", default={}) or {}
    pixel_threshold = int(blank_cfg.get("pixel_threshold", 245))
    max_ink_ratio = float(blank_cfg.get("max_ink_ratio", 0.003))
    max_stddev = float(blank_cfg.get("max_stddev", 12.0))

    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None, {}
    ink_ratio = float((image < pixel_threshold).mean())
    stddev = float(image.std())
    is_blank = ink_ratio <= max_ink_ratio and stddev <= max_stddev
    return is_blank, {"ink_ratio": ink_ratio, "stddev": stddev}


def staff_detect_failed(
    mask_path: Path, config: Dict[str, Any]
) -> Tuple[Optional[bool], Dict[str, float]]:
    staff_cfg = get_nested(config, "filters", "staff_detect_config", default={}) or {}
    min_nonzero_ratio = float(staff_cfg.get("min_nonzero_ratio", 0.001))
    if not mask_path.exists():
        return None, {"reason": "missing"}
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return None, {"reason": "unreadable"}
    nonzero_ratio = float((mask > 0).mean())
    failed = nonzero_ratio < min_nonzero_ratio
    return failed, {"nonzero_ratio": nonzero_ratio}


def filter_by_staff_overlap(
    candidates: Sequence[Any],
    bands: Sequence[Tuple[int, int]],
    vov_threshold: float = 0.5,
) -> List[Any]:
    """Return candidates that have at least vov_threshold vertical overlap with at least one band."""
    if not bands:
        return list(candidates)

    out = []
    for cand in candidates:
        if isinstance(cand, dict) and "bbox" in cand:
            box = cand["bbox"]
        else:
            box = cand

        if len(box) != 4:
            out.append(cand)
            continue

        y1, y2 = box[1], box[3]
        h = max(1, y2 - y1)
        max_vov = 0.0
        for by1, by2 in bands:
            overlap = min(y2, by2) - max(y1, by1)
            vov = max(0, overlap) / float(h)
            max_vov = max(max_vov, vov)

        if max_vov >= vov_threshold:
            out.append(cand)
    return out


def resolve_page_filters(
    config: Dict[str, Any],
    page_ids: Sequence[str],
    images: Sequence[Path],
    resolved: Sequence[Dict[str, str]],
    exclude_indices: set[int],
) -> List[Dict[str, Any]]:
    filters = get_nested(config, "filters", default={}) or {}

    def _manual_flag(filter_value: Any, page_index: int) -> Optional[bool]:
        if isinstance(filter_value, list):
            return page_index in {int(x) for x in filter_value}
        if isinstance(filter_value, bool):
            return filter_value
        return None

    blank_filter = filters.get("blank_page", "auto")
    staff_filter = filters.get("staff_detect", "auto")
    statuses: List[Dict[str, Any]] = []
    for idx, (page_id, image_path, resolved_item) in enumerate(
        zip(page_ids, images, resolved), start=1
    ):
        blank_manual = _manual_flag(blank_filter, idx)
        if (
            blank_manual is None
            and isinstance(blank_filter, str)
            and blank_filter.lower() == "auto"
        ):
            blank_value, blank_metrics = is_blank_page(image_path, config)
        else:
            blank_value, blank_metrics = blank_manual, {}

        staff_manual = _manual_flag(staff_filter, idx)
        if (
            staff_manual is None
            and isinstance(staff_filter, str)
            and staff_filter.lower() == "auto"
        ):
            staff_value, staff_metrics = staff_detect_failed(
                Path(resolved_item["staff_mask"]), config
            )
        else:
            staff_value, staff_metrics = staff_manual, {}

        statuses.append(
            {
                "page_index": idx,
                "page_id": page_id,
                "excluded_by_user": idx in exclude_indices,
                "blank_page": blank_value if blank_value is not None else "unknown",
                "blank_metrics": blank_metrics,
                "staff_detect_failed": staff_value if staff_value is not None else "unknown",
                "staff_metrics": staff_metrics,
            }
        )
    return statuses
