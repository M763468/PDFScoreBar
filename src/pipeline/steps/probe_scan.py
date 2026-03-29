"""In-process probe candidate generation for the detection pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from tqdm import tqdm

try:
    import cv2
except ImportError:  # pragma: no cover - optional in minimal test env
    cv2 = None  # type: ignore[assignment]

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional in minimal test env
    np = None  # type: ignore[assignment]

from src.pipeline.core.run_ids import build_probe_run_id, build_probe_run_id_from_parts
from src.pipeline.steps.candidate_filters import filter_probe_candidates, trim_box_to_ink
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from src.pipeline.utils.images import load_image
from src.pipeline.utils.io import ensure_dir
from src.pipeline.utils.wide_split_utils import split_wide_candidates

logger = logging.getLogger(__name__)

try:
    from src.pipeline.probe_detector import detect_probe_scan
except ImportError:  # pragma: no cover - optional in minimal test env
    detect_probe_scan = None  # type: ignore[assignment]


def _estimate_unit_size_from_existing_boxes(
    existing_boxes: Sequence[Tuple[int, int, int, int]],
) -> float | None:
    heights = [abs(b[3] - b[1]) for b in existing_boxes if abs(b[3] - b[1]) > 0]
    if not heights:
        return None
    # Barline bbox height is roughly one staff height; unit_size ~= staff_height / 4.
    return (
        max(1.0, float(np.median(heights)) / 4.0) if np is not None else max(1.0, heights[0] / 4.0)
    )


def _resolve_scale_aware_probe_kwargs(
    kwargs: Dict[str, Any],
    existing_boxes: Sequence[Tuple[int, int, int, int]],
) -> Dict[str, Any]:
    """Translate batch-only ratio knobs into detect_probe_scan kwargs.

    Supported pseudo keys (removed before detect_probe_scan call):
    - min_peak_distance_unit_ratio
    - x_merge_tol_unit_ratio
    """
    resolved = dict(kwargs)
    unit_size = _estimate_unit_size_from_existing_boxes(existing_boxes)
    if unit_size is None:
        resolved.pop("min_peak_distance_unit_ratio", None)
        resolved.pop("x_merge_tol_unit_ratio", None)
        return resolved

    if "min_peak_distance_unit_ratio" in resolved and "min_peak_distance" not in resolved:
        ratio = float(resolved.pop("min_peak_distance_unit_ratio"))
        resolved["min_peak_distance"] = max(1, int(round(unit_size * ratio)))
    else:
        resolved.pop("min_peak_distance_unit_ratio", None)

    if "x_merge_tol_unit_ratio" in resolved and "x_merge_tol" not in resolved:
        ratio = float(resolved.pop("x_merge_tol_unit_ratio"))
        resolved["x_merge_tol"] = max(1, int(round(unit_size * ratio)))
    else:
        resolved.pop("x_merge_tol_unit_ratio", None)

    return resolved


def _parse_bool_like(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _extract_candidate_postprocess_cfg(
    kwargs: Dict[str, Any],
    existing_boxes: Sequence[Tuple[int, int, int, int]],
) -> tuple[Dict[str, Any], Dict[str, Any] | None]:
    """Extract batch-only candidate postprocess pseudo keys from kwargs."""
    resolved = dict(kwargs)
    unit_size = _estimate_unit_size_from_existing_boxes(existing_boxes)
    pseudo_keys = (
        "post_emit_unit_normalized_box",
        "post_norm_width_unit_ratio",
        "post_norm_height_unit_ratio",
        "post_apply_if_width_gt_unit_ratio",
        "post_apply_if_height_gt_unit_ratio",
        "post_vertical_min_height_unit_ratio",
        "post_vertical_min_aspect_ratio",
        "post_split_wide_candidates",
        "post_split_min_width_unit_ratio",
        "post_split_box_width_unit_ratio",
        "post_split_peak_distance_unit_ratio",
        "post_split_peak_prominence_ratio",
    )
    enabled = _parse_bool_like(resolved.pop("post_emit_unit_normalized_box", False))
    split_enabled = _parse_bool_like(resolved.pop("post_split_wide_candidates", False))

    if not (enabled or split_enabled) or unit_size is None:
        for key in pseudo_keys[1:]:
            resolved.pop(key, None)
        return resolved, None

    cfg = {
        "unit_size": float(unit_size),
        "post_emit_unit_normalized_box": enabled,
        "split_wide_candidates": split_enabled,
        "norm_width_px": max(
            2, int(round(float(resolved.pop("post_norm_width_unit_ratio", 1.0)) * unit_size))
        ),
        "norm_height_px": max(
            4, int(round(float(resolved.pop("post_norm_height_unit_ratio", 4.0)) * unit_size))
        ),
        "apply_if_width_gt_px": max(
            1, int(round(float(resolved.pop("post_apply_if_width_gt_unit_ratio", 1.2)) * unit_size))
        ),
        "apply_if_height_gt_px": max(
            1,
            int(round(float(resolved.pop("post_apply_if_height_gt_unit_ratio", 4.6)) * unit_size)),
        ),
        "vertical_min_height_px": max(
            1,
            int(round(float(resolved.pop("post_vertical_min_height_unit_ratio", 2.5)) * unit_size)),
        ),
        "vertical_min_aspect_ratio": float(resolved.pop("post_vertical_min_aspect_ratio", 3.0)),
        "split_min_width_unit_ratio": float(resolved.pop("post_split_min_width_unit_ratio", 1.5)),
        "split_box_width_unit_ratio": float(resolved.pop("post_split_box_width_unit_ratio", 0.8)),
        "split_peak_distance_unit_ratio": float(
            resolved.pop("post_split_peak_distance_unit_ratio", 0.5)
        ),
        "split_peak_prominence_ratio": float(
            resolved.pop("post_split_peak_prominence_ratio", 0.15)
        ),
    }
    return resolved, cfg


def _clip_box(
    box: Tuple[int, int, int, int],
    img_w: int,
    img_h: int,
) -> Tuple[int, int, int, int] | None:
    x1, y1, x2, y2 = box
    x1 = max(0, min(img_w - 1, int(round(x1))))
    x2 = max(0, min(img_w, int(round(x2))))
    y1 = max(0, min(img_h - 1, int(round(y1))))
    y2 = max(0, min(img_h, int(round(y2))))
    if x2 <= x1:
        x2 = min(img_w, x1 + 1)
    if y2 <= y1:
        y2 = min(img_h, y1 + 1)
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


def _augment_unit_normalized_boxes(
    boxes: Sequence[Tuple[int, int, int, int]],
    img_w: int,
    img_h: int,
    cfg: Dict[str, Any] | None,
) -> List[Tuple[int, int, int, int]]:
    """Emit additional normalized vertical boxes to reduce bbox shape mismatch.

    This is intentionally additive and optional (default OFF) to preserve baseline behavior.
    """
    if not cfg:
        return []

    out: List[Tuple[int, int, int, int]] = []
    norm_w = int(cfg["norm_width_px"])
    norm_h = int(cfg["norm_height_px"])
    apply_w_gt = int(cfg["apply_if_width_gt_px"])
    apply_h_gt = int(cfg["apply_if_height_gt_px"])
    min_h = int(cfg["vertical_min_height_px"])
    min_aspect = float(cfg["vertical_min_aspect_ratio"])

    for b in boxes:
        x1, y1, x2, y2 = b
        w = abs(x2 - x1)
        h = abs(y2 - y1)
        if h < min_h:
            continue
        if w <= 0 or h / max(1, w) < min_aspect:
            continue
        if w <= apply_w_gt and h <= apply_h_gt:
            continue

        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        new_w = norm_w if w > apply_w_gt else w
        new_h = norm_h if h > apply_h_gt else h
        nb = _clip_box(
            (
                int(round(cx - new_w / 2.0)),
                int(round(cy - new_h / 2.0)),
                int(round(cx + new_w / 2.0)),
                int(round(cy + new_h / 2.0)),
            ),
            img_w,
            img_h,
        )
        if nb is not None and nb != b:
            out.append(nb)
    return out


def _load_bands_for_image(
    *,
    bands_from: Optional[Path],
    current_score_name: str,
    stem: str,
) -> List[Tuple[int, int, int, int]]:
    if not bands_from:
        return []

    if bands_from.is_file():
        return load_json_boxes(bands_from)

    run_subdir = build_probe_run_id_from_parts(current_score_name, stem)
    candidates = [
        bands_from / current_score_name / stem / "pipeline2_no_peak_candidates.json",
        bands_from / current_score_name / stem / "pipeline2_no_peak_scored.json",
        bands_from / run_subdir / "pipeline2_no_peak_scored.json",
        bands_from / f"{stem}.json",
        bands_from / "hybrid_results" / f"{stem}_hybrid.json",
        bands_from / f"{run_subdir}_scored.json",
    ]
    for path in candidates:
        if path.exists():
            return load_json_boxes(path)
    return []


def _build_staff_mask_map(staff_mask_dir: Optional[Path]) -> Dict[str, Path]:
    staff_mask_map: Dict[str, Path] = {}
    if not staff_mask_dir or not staff_mask_dir.exists():
        return staff_mask_map
    
    # Support both legacy Homr tool debug patterns and the new in-process filename pattern
    patterns = ["*_debug_3_staff.png", "*_staff_mask.png"]
    for pattern in patterns:
        for path in staff_mask_dir.rglob(pattern):
            stem_key = path.name.replace("_proxy_debug_3_staff.png", "").replace(
                "_debug_3_staff.png", ""
            ).replace("_staff_mask.png", "")
            if stem_key not in staff_mask_map:
                staff_mask_map[stem_key] = path
    return staff_mask_map


def _build_clef_mask_map(clef_mask_dir: Optional[Path]) -> Dict[str, Path]:
    clef_mask_map: Dict[str, Path] = {}
    if not clef_mask_dir or not clef_mask_dir.exists():
        return clef_mask_map

    # Support both legacy Homr tool debug patterns and the new in-process filename pattern
    patterns = ["*_debug_2_clefs.png", "*_clef_mask.png", "*_clefs_keys_mask.png"]
    for pattern in patterns:
        for path in clef_mask_dir.rglob(pattern):
            stem_key = (
                path.name.replace("_proxy_debug_2_clefs.png", "")
                .replace("_debug_2_clefs.png", "")
                .replace("_clef_mask.png", "")
                .replace("_clefs_keys_mask.png", "")
            )
            if stem_key not in clef_mask_map:
                clef_mask_map[stem_key] = path
    return clef_mask_map


def run_probe_scan_batch(
    *,
    images: Iterable[Path],
    output_root: Path,
    bands_from: Optional[Path],
    staff_mask_dir: Optional[Path],
    clef_mask_dir: Optional[Path] = None,
    ink_threshold: int,
    min_ratio: float = 0.50,
    min_height_ratio: float = 0.012,
    min_width_ratio: Optional[float] = 0.0001,
    score_name: Optional[str] = None,
    band_cluster_max_dist: Optional[float] = None,
    band_min_row_count: int = 1,
    vertical_closing: int = 4,
    detect_probe_kwargs: Optional[Dict[str, Any]] = None,
    probe_row_filter_mode: Optional[str] = None,
    probe_endpoint_x_scale: Optional[float] = None,
    probe_endpoint_y_scale: Optional[float] = None,
    skip_existing: bool = False,
    input_image_scale: float = 1.0,
    in_memory_images: Dict[str, Any] | None = None,
    enable_heuristic_filters: bool = False,
    candidate_filter_kwargs: Optional[Dict[str, Any]] = None,
) -> int:
    """Generate probe candidates for all pages in-process.

    Output format and file names are kept compatible with the former tool script.
    """
    if cv2 is None or np is None:
        raise ImportError("run_probe_scan_batch requires opencv-python and numpy.")
    if detect_probe_scan is None:
        raise ImportError("run_probe_scan_batch requires src.pipeline.probe_detector dependencies.")

    ensure_dir(output_root)
    staff_mask_map = _build_staff_mask_map(staff_mask_dir)
    clef_mask_map = _build_clef_mask_map(clef_mask_dir)

    if probe_row_filter_mode is not None:
        logger.warning(
            "probe_row_filter_mode=%s is currently not applied by run_probe_scan_batch.",
            probe_row_filter_mode,
        )
    if probe_endpoint_x_scale is not None or probe_endpoint_y_scale is not None:
        logger.warning(
            "probe_endpoint_x_scale/probe_endpoint_y_scale are currently not applied by run_probe_scan_batch."
        )

    kwargs = {
        "scan_x_peak_rescue": True,
        "scan_rightmost_rescue": True,
        "scan_gap_rescue": True,
        "scan_gap_threshold_ratio": 1.8,
        "scan_gap_rescue_min_ratio": 0.0,
        "scan_gap_margin_ratio": 0.1,
        "divisi_rescue": True,
        "scan_x_peak_rescue_mode": "topbottom",
        "probe_width": 4,
        "scan_x_peak_ratio_min": 0.0,
        "scan_rightmost_min_ratio": 0.0,
        "max_per_band": 100,
        "scan_center_on_peak": True,
    }
    if detect_probe_kwargs:
        kwargs.update(detect_probe_kwargs)

    processed = 0
    for img_path in tqdm(images, desc="Probe Scan", unit="page"):
        stem = img_path.stem
        current_score_name = score_name or img_path.parent.name
        run_id = build_probe_run_id(img_path, score_name=current_score_name)
        run_dir = output_root / run_id
        ensure_dir(run_dir)
        out_path = run_dir / "pipeline2_no_peak_candidates.json"

        if skip_existing and out_path.exists():
            processed += 1
            continue

        img = load_image(img_path, in_memory_images=in_memory_images)
        if img is None:
            logger.warning("Failed to load image: %s", img_path)
            continue

        staff_mask = np.zeros(img.shape[:2], dtype=np.uint8)
        clef_mask = np.zeros(img.shape[:2], dtype=np.uint8)
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

        clef_path = clef_mask_map.get(stem)
        if clef_path:
            loaded_clef = cv2.imread(str(clef_path), cv2.IMREAD_GRAYSCALE)
            if loaded_clef is not None:
                if loaded_clef.shape[:2] != img.shape[:2]:
                    loaded_clef = cv2.resize(
                        loaded_clef, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST
                    )
                clef_mask = loaded_clef

        existing_boxes = _load_bands_for_image(
            bands_from=bands_from,
            current_score_name=current_score_name,
            stem=stem,
        )

        # Rescale existing boxes to match image resolution if using SR
        if input_image_scale > 1.0:
            existing_boxes = [
                tuple(int(round(v * input_image_scale)) for v in b) for b in existing_boxes
            ]

        page_kwargs = _resolve_scale_aware_probe_kwargs(kwargs, existing_boxes)
        page_kwargs, post_cfg = _extract_candidate_postprocess_cfg(page_kwargs, existing_boxes)
        if page_kwargs is not kwargs and (
            "min_peak_distance" in page_kwargs or "x_merge_tol" in page_kwargs
        ):
            logger.info(
                "Probe scan scale-aware params for %s/%s: min_peak_distance=%s x_merge_tol=%s",
                current_score_name,
                stem,
                page_kwargs.get("min_peak_distance"),
                page_kwargs.get("x_merge_tol"),
            )

        effective_band_source = page_kwargs.pop("band_source", band_source)
        candidates = detect_probe_scan(
            base_img=img,
            staff_mask=staff_mask,
            existing_boxes=existing_boxes,
            band_source=effective_band_source,
            band_cluster_max_dist=band_cluster_max_dist,
            band_min_row_count=band_min_row_count,
            ink_threshold=ink_threshold,
            min_ratio=min_ratio,
            vertical_closing=vertical_closing,
            **page_kwargs,
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

        if enable_heuristic_filters:
            filter_kwargs = candidate_filter_kwargs or {}
            real_staff_mask = staff_mask if band_source == "staff_mask" else None
            filtered_candidates, dropped = filter_probe_candidates(
                candidates=filtered_candidates,
                image=img,
                existing_boxes=existing_boxes,
                staff_mask=real_staff_mask,
                clef_mask=clef_mask,
                **filter_kwargs,
            )
            if dropped:
                logger.debug(f"Heuristic filter dropped {len(dropped)} candidates for {stem}")

        # Final tightening of boxes to actual ink extent to improve VOV for evaluation
        filtered_candidates = [
            trim_box_to_ink(img, b, ink_threshold=ink_threshold) for b in filtered_candidates
        ]

        final_set = set()
        for sb in existing_boxes:
            # sb is already scaled to SR space if needed
            h = abs(sb[3] - sb[1])
            w = abs(sb[2] - sb[0])
            if h >= min_height_px and w >= min_width_px:
                final_set.add(tuple(int(v) for v in sb))
        for c in filtered_candidates:
            final_set.add(tuple(int(v) for v in c))

        if post_cfg:
            if post_cfg.get("post_emit_unit_normalized_box"):
                for nb in _augment_unit_normalized_boxes(
                    list(final_set),
                    img_w=img_w,
                    img_h=img_h,
                    cfg=post_cfg,
                ):
                    final_set.add(tuple(int(v) for v in nb))

            if post_cfg.get("split_wide_candidates"):
                print(f"DEBUG: Attempting to split {len(final_set)} candidates...")
                split_boxes, stats = split_wide_candidates(
                    boxes=list(final_set),
                    img=img,
                    min_split_width_unit_ratio=float(
                        post_cfg.get("split_min_width_unit_ratio", 1.5)
                    ),
                    split_box_width_unit_ratio=float(
                        post_cfg.get("split_box_width_unit_ratio", 0.8)
                    ),
                    split_peak_distance_unit_ratio=float(
                        post_cfg.get("split_peak_distance_unit_ratio", 0.5)
                    ),
                    peak_prominence_ratio=float(post_cfg.get("split_peak_prominence_ratio", 0.15)),
                    require_exactly_two_peaks=False,
                    recenter_single_peak=False,
                    emit_merged_two_peak_box=False,
                    keep_original_when_not_split=False,
                )
                print(f"DEBUG: Split stats: {stats}")
                for sb in split_boxes:
                    final_set.add(tuple(int(v) for v in sb))

        final_list = sorted(final_set)
        out_path.write_text(json.dumps(final_list, indent=2))
        processed += 1

    return processed
