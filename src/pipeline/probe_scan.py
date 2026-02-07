"""In-process probe candidate generation for the detection pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import cv2
except ImportError:  # pragma: no cover - optional in minimal test env
    cv2 = None  # type: ignore[assignment]

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional in minimal test env
    np = None  # type: ignore[assignment]

from src.pipeline.io import ensure_dir

logger = logging.getLogger(__name__)


def _detect_probe_scan(*args: Any, **kwargs: Any) -> List[Tuple[int, int, int, int]]:
    # Lazy import to keep module import lightweight for tests and dry-run paths.
    from tools.run_gt_rebuild_hybrid_eval import detect_probe_scan

    return detect_probe_scan(*args, **kwargs)


def _parse_boxes(payload: Any) -> List[Tuple[int, int, int, int]]:
    if isinstance(payload, dict) and "predictions" in payload:
        payload = payload["predictions"]

    boxes: List[Tuple[int, int, int, int]] = []
    if not isinstance(payload, list):
        return boxes

    for item in payload:
        if isinstance(item, dict):
            bbox = item.get("bbox", item.get("pred_bbox"))
        elif isinstance(item, list):
            bbox = item
        else:
            bbox = None
        if isinstance(bbox, list) and len(bbox) == 4:
            boxes.append(tuple(int(v) for v in bbox))
    return boxes


def _load_bands_for_image(
    *,
    bands_from: Optional[Path],
    current_score_name: str,
    stem: str,
) -> List[Tuple[int, int, int, int]]:
    if not bands_from:
        return []

    if bands_from.is_file():
        return _parse_boxes(json.loads(bands_from.read_text()))

    run_subdir = f"eval2_{current_score_name}_{stem}"
    candidates = [
        bands_from / run_subdir / "pipeline2_no_peak_scored.json",
        bands_from / f"{stem}.json",
        bands_from / "hybrid_results" / f"{stem}_hybrid.json",
        bands_from / f"{run_subdir}_scored.json",
    ]
    for path in candidates:
        if path.exists():
            return _parse_boxes(json.loads(path.read_text()))
    return []


def _build_staff_mask_map(staff_mask_dir: Optional[Path]) -> Dict[str, Path]:
    staff_mask_map: Dict[str, Path] = {}
    if not staff_mask_dir or not staff_mask_dir.exists():
        return staff_mask_map
    for path in staff_mask_dir.rglob("*_debug_3_staff.png"):
        stem_key = path.name.replace("_proxy_debug_3_staff.png", "").replace(
            "_debug_3_staff.png", ""
        )
        staff_mask_map[stem_key] = path
    return staff_mask_map


def run_probe_scan_batch(
    *,
    images: Iterable[Path],
    output_root: Path,
    bands_from: Optional[Path],
    staff_mask_dir: Optional[Path],
    ink_threshold: int,
    min_ratio: float,
    min_height_ratio: float,
    min_width_ratio: Optional[float] = None,
    score_name: Optional[str] = None,
    band_min_row_count: int = 1,
    vertical_closing: int = 0,
    skip_existing: bool = False,
) -> int:
    """Generate probe candidates for all pages in-process.

    Output format and file names are kept compatible with the former tool script.
    """
    if cv2 is None or np is None:
        raise ImportError("run_probe_scan_batch requires opencv-python and numpy.")

    ensure_dir(output_root)
    staff_mask_map = _build_staff_mask_map(staff_mask_dir)

    processed = 0
    for img_path in images:
        stem = img_path.stem
        current_score_name = score_name or img_path.parent.name
        run_id = f"eval2_{current_score_name}_{stem}"
        run_dir = output_root / run_id
        ensure_dir(run_dir)
        out_path = run_dir / "pipeline2_no_peak_candidates.json"

        if skip_existing and out_path.exists():
            processed += 1
            continue

        img = cv2.imread(str(img_path))
        if img is None:
            logger.warning("Failed to load image: %s", img_path)
            continue

        staff_mask = np.zeros(img.shape[:2], dtype=np.uint8)
        band_source = "row_stats"
        mask_path = staff_mask_map.get(stem)
        if mask_path:
            loaded_mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            if loaded_mask is not None:
                if loaded_mask.shape[:2] != img.shape[:2]:
                    loaded_mask = cv2.resize(
                        loaded_mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST
                    )
                staff_mask = loaded_mask
                band_source = "staff_mask"

        existing_boxes = _load_bands_for_image(
            bands_from=bands_from,
            current_score_name=current_score_name,
            stem=stem,
        )

        candidates = _detect_probe_scan(
            base_img=img,
            staff_mask=staff_mask,
            existing_boxes=existing_boxes,
            band_source=band_source,
            band_min_row_count=band_min_row_count,
            scan_x_peak_rescue=True,
            scan_rightmost_rescue=True,
            divisi_rescue=True,
            scan_x_peak_rescue_mode="topbottom",
            probe_width=4,
            ink_threshold=ink_threshold,
            min_ratio=min_ratio,
            scan_x_peak_ratio_min=0.0,
            scan_rightmost_min_ratio=0.0,
            max_per_band=100,
            scan_center_on_peak=True,
            vertical_closing=vertical_closing,
        )

        img_h, img_w = img.shape[:2]
        min_height_px = int(img_h * min_height_ratio)
        min_width_px = int(img_w * min_width_ratio) if min_width_ratio is not None else 0

        filtered_candidates: List[Tuple[int, int, int, int]] = []
        for c in candidates:
            h = abs(c[3] - c[1])
            w = abs(c[2] - c[0])
            if h >= min_height_px and w >= min_width_px:
                filtered_candidates.append(tuple(int(v) for v in c))

        final_set = set()
        for b in existing_boxes:
            h = abs(b[3] - b[1])
            w = abs(b[2] - b[0])
            if h >= min_height_px and w >= min_width_px:
                final_set.add(tuple(int(v) for v in b))
        for c in filtered_candidates:
            final_set.add(tuple(int(v) for v in c))

        final_list = sorted(final_set)
        out_path.write_text(json.dumps(final_list, indent=2))
        processed += 1

    return processed
