#!/usr/bin/env python3
"""Generate probe-scan candidates from hybrid bench inventory records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.probe_detector import detect_probe_scan


def _load_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    payload = json.loads(path.read_text())
    records: Any = payload
    if isinstance(payload, dict) and "predictions" in payload:
        records = payload["predictions"]

    boxes: list[tuple[int, int, int, int]] = []
    if not isinstance(records, list):
        return boxes

    for item in records:
        if isinstance(item, list) and len(item) == 4:
            boxes.append(tuple(int(v) for v in item))
            continue
        if isinstance(item, dict):
            bbox = item.get("bbox", item.get("pred_bbox"))
            if bbox and len(bbox) == 4:
                boxes.append(tuple(int(v) for v in bbox))
    return boxes


def _normalize_name(name: str) -> tuple[str, str]:
    # "Score/page_001" -> ("Score", "page_001")
    if "/" in name:
        score, page = name.split("/", 1)
        return score, page
    raise ValueError(f"Invalid record name: {name}")


def _run_one(
    *,
    record: dict[str, Any],
    output_root: Path,
    ink_threshold: int,
    min_ratio: float,
    min_height_ratio: float,
    min_width_ratio: float,
) -> dict[str, Any]:
    score = record["score"]
    page = record["page"]
    image_path = Path(record["image"])
    staff_mask_path = Path(record["staff_mask"])
    existing_path = Path(record["hybrid_predictions"])

    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Failed to load image: {image_path}")

    staff_mask = cv2.imread(str(staff_mask_path), cv2.IMREAD_GRAYSCALE)
    if staff_mask is None:
        raise FileNotFoundError(f"Failed to load staff mask: {staff_mask_path}")
    if staff_mask.shape[:2] != image.shape[:2]:
        staff_mask = cv2.resize(
            staff_mask, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_NEAREST
        )

    existing_boxes = _load_boxes(existing_path)

    # Keep defaults aligned with current src.pipeline.probe_scan.run_probe_scan_batch.
    candidates = detect_probe_scan(
        base_img=image,
        staff_mask=staff_mask,
        existing_boxes=existing_boxes,
        band_source="staff_mask",
        band_min_row_count=1,
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
        vertical_closing=0,
    )

    img_h, img_w = image.shape[:2]
    min_h_px = int(img_h * min_height_ratio)
    min_w_px = int(img_w * min_width_ratio)

    filtered: list[tuple[int, int, int, int]] = []
    for c in candidates:
        h = abs(c[3] - c[1])
        w = abs(c[2] - c[0])
        if h >= min_h_px and w >= min_w_px:
            filtered.append(tuple(int(v) for v in c))

    merged = set()
    for b in existing_boxes:
        h = abs(b[3] - b[1])
        w = abs(b[2] - b[0])
        if h >= min_h_px and w >= min_w_px:
            merged.add(tuple(int(v) for v in b))
    for c in filtered:
        merged.add(c)

    final_list = sorted(merged)

    out_dir = output_root / score / page
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "pipeline2_no_peak_candidates.json"
    out_path.write_text(json.dumps(final_list, indent=2))

    return {
        "score": score,
        "page": page,
        "image": str(image_path),
        "staff_mask": str(staff_mask_path),
        "existing_boxes_path": str(existing_path),
        "existing_count": len(existing_boxes),
        "generated_count": len(candidates),
        "final_count": len(final_list),
        "output": str(out_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--exclude", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    parser.add_argument("--ink-threshold", type=int, default=230)
    parser.add_argument("--min-ratio", type=float, default=0.7)
    parser.add_argument("--min-height-ratio", type=float, default=0.012)
    parser.add_argument("--min-width-ratio", type=float, default=0.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    inventory_obj = json.loads(args.inventory.read_text())
    records = inventory_obj.get("records", [])
    if not isinstance(records, list):
        raise ValueError("Invalid inventory format: records must be a list")

    exclude_obj = json.loads(args.exclude.read_text())
    excluded_pages = {
        (x["score"], x["page"]) for x in exclude_obj.get("excluded_pages", []) if "score" in x
    }

    results: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for rec in records:
        key = (rec.get("score"), rec.get("page"))
        if key in excluded_pages:
            skipped.append({"score": key[0], "page": key[1], "reason": "excluded"})
            continue
        try:
            result = _run_one(
                record=rec,
                output_root=args.output_root,
                ink_threshold=args.ink_threshold,
                min_ratio=args.min_ratio,
                min_height_ratio=args.min_height_ratio,
                min_width_ratio=args.min_width_ratio,
            )
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {"score": str(rec.get("score")), "page": str(rec.get("page")), "error": str(exc)}
            )

    summary = {
        "inventory": str(args.inventory),
        "exclude": str(args.exclude),
        "output_root": str(args.output_root),
        "config": {
            "ink_threshold": args.ink_threshold,
            "min_ratio": args.min_ratio,
            "min_height_ratio": args.min_height_ratio,
            "min_width_ratio": args.min_width_ratio,
        },
        "processed": len(results),
        "skipped": len(skipped),
        "errors": len(errors),
        "results": results,
        "skipped_pages": skipped,
        "error_details": errors,
    }

    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2))
    print(json.dumps({"processed": len(results), "skipped": len(skipped), "errors": len(errors)}))


if __name__ == "__main__":
    main()
