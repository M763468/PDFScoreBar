#!/usr/bin/env python3
"""Compare probe detector outputs between src and legacy tools implementation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.probe_detector import detect_probe_scan as src_detect_probe_scan
from src.pipeline.probe_detector.bands import build_row_stats
from tools.run_gt_rebuild_hybrid_eval import detect_probe_scan as tools_detect_probe_scan


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _normalize_boxes(boxes: Any) -> list[tuple[int, int, int, int]]:
    return sorted([tuple(int(v) for v in b) for b in boxes])


def run_parity_check(
    *,
    image_path: Path,
    staff_mask_path: Path,
    existing_boxes_path: Path,
) -> Dict[str, Any]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Failed to load image: {image_path}")

    staff_mask = cv2.imread(str(staff_mask_path), cv2.IMREAD_GRAYSCALE)
    if staff_mask is None:
        raise FileNotFoundError(f"Failed to load staff mask: {staff_mask_path}")

    existing_boxes = _load_json(existing_boxes_path)
    row_stats = build_row_stats(existing_boxes, 25.0, 1)

    cases: Dict[str, Dict[str, Any]] = {
        "baseline_staffmask_dense": {
            "band_source": "staff_mask",
            "band_min_row_count": 1,
            "ink_threshold": 230,
            "min_ratio": 0.0,
            "vertical_closing": 0,
            "scan_x_peak_rescue": True,
            "scan_rightmost_rescue": True,
            "divisi_rescue": True,
            "scan_x_peak_rescue_mode": "topbottom",
            "probe_width": 4,
            "scan_x_peak_ratio_min": 0.0,
            "scan_rightmost_min_ratio": 0.0,
            "max_per_band": 100,
            "scan_center_on_peak": True,
        },
        "rescue_off_custom_width": {
            "band_source": "staff_mask",
            "band_min_row_count": 1,
            "ink_threshold": 230,
            "min_ratio": 0.7,
            "vertical_closing": 0,
            "scan_x_peak_rescue": False,
            "scan_rightmost_rescue": False,
            "divisi_rescue": False,
            "probe_width": 6,
            "max_per_band": 100,
            "scan_center_on_peak": True,
        },
        "row_stats_mode": {
            "band_source": "row_stats",
            "row_stats": row_stats,
            "band_min_row_count": 1,
            "ink_threshold": 230,
            "min_ratio": 0.7,
            "vertical_closing": 0,
            "scan_x_peak_rescue": True,
            "scan_rightmost_rescue": True,
            "divisi_rescue": True,
            "scan_x_peak_rescue_mode": "topbottom",
            "probe_width": 4,
            "scan_x_peak_ratio_min": 0.0,
            "scan_rightmost_min_ratio": 0.0,
            "max_per_band": 100,
            "scan_center_on_peak": True,
        },
    }

    result: Dict[str, Any] = {
        "inputs": {
            "image": str(image_path),
            "staff_mask": str(staff_mask_path),
            "existing_boxes": str(existing_boxes_path),
            "row_stats_len": len(row_stats),
        },
        "cases": {},
    }

    for case_name, kwargs in cases.items():
        src_boxes = _normalize_boxes(
            src_detect_probe_scan(
                base_img=image,
                staff_mask=staff_mask,
                existing_boxes=existing_boxes,
                **kwargs,
            )
        )
        tools_boxes = _normalize_boxes(
            tools_detect_probe_scan(
                base_img=image,
                staff_mask=staff_mask,
                existing_boxes=existing_boxes,
                **kwargs,
            )
        )
        result["cases"][case_name] = {
            "src_count": len(src_boxes),
            "tools_count": len(tools_boxes),
            "exact_match": src_boxes == tools_boxes,
        }

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True, help="Input score image path")
    parser.add_argument("--staff-mask", type=Path, required=True, help="Staff mask image path")
    parser.add_argument(
        "--existing-boxes", type=Path, required=True, help="Existing boxes JSON path"
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output JSON path (e.g. logs/issue34_smoke/<run>/parity_summary.json)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        result = run_parity_check(
            image_path=args.image,
            staff_mask_path=args.staff_mask,
            existing_boxes_path=args.existing_boxes,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
    except (FileNotFoundError, PermissionError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
