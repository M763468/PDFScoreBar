#!/usr/bin/env python3
"""GT relabel support script (human-in-the-loop).

This script helps prepare enlarged crops with overlays and provides a
JSON-based edit workflow for GT corrections. It does NOT perform any
automatic relabeling and never overwrites original GT files.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

Box = Tuple[int, int, int, int]


DEFAULT_PAGE_CONFIG = {
    "page_10": {
        "gt": "data/training/annotations/page_010/fn_only.json",
        "image": "data/training/images/page_10.png",
        "baseline": "logs/hybrid_generalization/page_10_hybrid_test/baseline/page_10/page_10/page_10_detections.json",
        "sr": "logs/hybrid_generalization/page_10_hybrid_test/sr/page_10/page_10/page_10_detections.json",
        "omr": "logs/hybrid_generalization/page_10_hybrid_test/omr_sr/predictions.json",
    },
    "page_15": {
        "gt": "data/training/annotations/page_015/fn_only.json",
        "image": "data/training/images/page_15.png",
        "baseline": "logs/hybrid_generalization/page_15_hybrid_test/baseline/page_15/page_15/page_15_detections.json",
        "sr": "logs/hybrid_generalization/page_15_hybrid_test/sr/page_15/page_15/page_15_detections.json",
        "omr": "logs/hybrid_generalization/page_15_hybrid_test/omr_sr/predictions.json",
    },
    "page_001": {
        "gt": "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/fn_only.json",
        "image": "data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png",
        "baseline": "logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_001/baseline/page_001/page_001/page_001_detections.json",
        "sr": "logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_001/sr/page_001/page_001/page_001_detections.json",
        "omr": "logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_001/omr_sr/predictions.json",
    },
    "page_004": {
        "gt": "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/fn_only.json",
        "image": "data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png",
        "baseline": "logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_004/baseline/page_004/page_004/page_004_detections.json",
        "sr": "logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_004/sr/page_004/page_004/page_004_detections.json",
        "omr": "logs/hybrid_generalization/phase4b_cv_prokofiev_va_page_004/omr_sr/predictions.json",
    },
}


@dataclass
class Candidate:
    page: str
    gt_index: int
    category: str
    near_hit_classification: str
    note: str


@dataclass
class CropMeta:
    page: str
    gt_index: int
    scale: int
    crop_box: Box
    orig_gt_bbox: Box
    scaled_gt_bbox: Box
    status: str
    edited_bbox: Box
    delta: Dict[str, int]
    nearby_detections: List[Box]


def read_json(path: Path):
    return json.loads(path.read_text())


def load_boxes(path: Path) -> List[Box]:
    if not path.exists():
        return []
    data = read_json(path)
    if isinstance(data, dict) and "predictions" in data:
        boxes: List[Box] = []
        for pred in data["predictions"]:
            bbox = pred.get("orig_bbox", pred.get("pred_bbox"))
            if bbox:
                boxes.append(tuple(int(v) for v in bbox))
        return boxes
    if isinstance(data, list):
        if not data:
            return []
        if isinstance(data[0], dict) and "barline_location" in data[0]:
            return [tuple(int(v) for v in item["barline_location"]) for item in data]
        return [tuple(int(v) for v in item) for item in data]
    return []


def load_candidates(path: Path) -> List[Candidate]:
    candidates = []
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            candidates.append(
                Candidate(
                    page=row["page"],
                    gt_index=int(row["gt_index"]),
                    category=row.get("coarse_category", row.get("category", "")),
                    near_hit_classification=row.get("near_hit_classification", ""),
                    note=row.get("note", ""),
                )
            )
    return candidates


def load_page_config(path: Optional[Path]) -> Dict[str, Dict[str, str]]:
    if path is None:
        return DEFAULT_PAGE_CONFIG
    data = read_json(path)
    return data


def bbox_center(b: Box) -> Tuple[float, float]:
    x1, y1, x2, y2 = b
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def intersect(a: Box, b: Box) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def near_hit(gt: Box, det: Box, tol_x: int, tol_y: int) -> bool:
    cx_gt, cy_gt = bbox_center(gt)
    cx_det, cy_det = bbox_center(det)
    if abs(cx_det - cx_gt) > tol_x:
        return False
    if det[3] < gt[1] - tol_y or det[1] > gt[3] + tol_y:
        return False
    return True


def scale_box(box: Box, crop_box: Box, scale: int) -> Box:
    x1, y1, x2, y2 = box
    cx1, cy1, _, _ = crop_box
    sx1 = (x1 - cx1) * scale
    sy1 = (y1 - cy1) * scale
    sx2 = (x2 - cx1) * scale
    sy2 = (y2 - cy1) * scale
    return (int(sx1), int(sy1), int(sx2), int(sy2))


def unscale_box(box: Box, crop_box: Box, scale: int) -> Box:
    x1, y1, x2, y2 = box
    cx1, cy1, _, _ = crop_box
    ox1 = round(x1 / scale + cx1)
    oy1 = round(y1 / scale + cy1)
    ox2 = round(x2 / scale + cx1)
    oy2 = round(y2 / scale + cy1)
    return (int(ox1), int(oy1), int(ox2), int(oy2))


def clamp_box(box: Box, width: int, height: int) -> Box:
    x1, y1, x2, y2 = box
    x1 = max(0, min(x1, width - 1))
    x2 = max(0, min(x2, width - 1))
    y1 = max(0, min(y1, height - 1))
    y2 = max(0, min(y2, height - 1))
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return (x1, y1, x2, y2)


def write_crop_and_template(
    candidate: Candidate,
    gt_bbox: Box,
    image_path: Path,
    detections: List[Box],
    out_root: Path,
    scale: int,
    margin_x: int,
    margin_y: int,
    tol_x: int,
    tol_y: int,
    resize_method: str,
) -> None:
    img = Image.open(image_path).convert("RGB")
    x1, y1, x2, y2 = gt_bbox
    crop_box = (
        max(0, x1 - margin_x),
        max(0, y1 - margin_y),
        min(img.width, x2 + margin_x),
        min(img.height, y2 + margin_y),
    )
    crop = img.crop(crop_box)

    if resize_method == "nearest":
        resample = Image.NEAREST
    elif resize_method == "bicubic":
        resample = Image.BICUBIC
    else:
        resample = Image.LANCZOS

    scaled = crop.resize((crop.width * scale, crop.height * scale), resample=resample)
    draw = ImageDraw.Draw(scaled)

    gt_scaled = scale_box(gt_bbox, crop_box, scale)
    draw.rectangle(gt_scaled, outline=(255, 0, 255), width=3)

    nearby = []
    for det in detections:
        if intersect(det, crop_box) or near_hit(gt_bbox, det, tol_x, tol_y):
            det_scaled = scale_box(det, crop_box, scale)
            draw.rectangle(det_scaled, outline=(0, 255, 0), width=2)
            nearby.append(det)

    out_dir = out_root / candidate.page / f"fn_{candidate.gt_index:03d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    image_out = out_dir / f"crop_x{scale}.png"
    scaled.save(image_out)

    template = CropMeta(
        page=candidate.page,
        gt_index=candidate.gt_index,
        scale=scale,
        crop_box=crop_box,
        orig_gt_bbox=gt_bbox,
        scaled_gt_bbox=gt_scaled,
        status="unchanged",
        edited_bbox=gt_scaled,
        delta={"dx": 0, "dy": 0, "dtop": 0, "dbottom": 0},
        nearby_detections=nearby,
    )

    template_payload = template.__dict__.copy()
    template_payload.update(
        {
            "coarse_category": candidate.category,
            "near_hit_classification": candidate.near_hit_classification,
            "note": candidate.note,
        }
    )

    template_path = out_dir / "edit_template.json"
    template_path.write_text(json.dumps(template_payload, indent=2))


def apply_delta(box: Box, delta: Dict[str, int]) -> Box:
    dx = int(delta.get("dx", 0))
    dy = int(delta.get("dy", 0))
    dtop = int(delta.get("dtop", 0))
    dbottom = int(delta.get("dbottom", 0))
    x1, y1, x2, y2 = box
    x1 += dx
    x2 += dx
    y1 += dy + dtop
    y2 += dy + dbottom
    return (x1, y1, x2, y2)


def load_gt_entries(path: Path) -> List[Dict]:
    data = read_json(path)
    if not isinstance(data, list):
        raise ValueError(f"Unexpected GT format: {path}")
    return data


def prepare(args: argparse.Namespace) -> None:
    candidates = load_candidates(Path(args.candidates))
    if args.limit is not None:
        candidates = candidates[: args.limit]
    page_config = load_page_config(Path(args.page_config) if args.page_config else None)
    out_root = Path(args.out_root)

    for candidate in candidates:
        if candidate.page not in page_config:
            raise ValueError(f"Missing page config for {candidate.page}")
        cfg = page_config[candidate.page]
        gt_entries = load_gt_entries(Path(cfg["gt"]))
        gt_bbox = tuple(gt_entries[candidate.gt_index]["barline_location"])  # type: ignore

        detections = []
        detections += load_boxes(Path(cfg.get("baseline", "")))
        detections += load_boxes(Path(cfg.get("sr", "")))
        detections += load_boxes(Path(cfg.get("omr", "")))

        write_crop_and_template(
            candidate=candidate,
            gt_bbox=tuple(int(v) for v in gt_bbox),
            image_path=Path(cfg["image"]),
            detections=detections,
            out_root=out_root,
            scale=args.scale,
            margin_x=args.margin_x,
            margin_y=args.margin_y,
            tol_x=args.tol_x,
            tol_y=args.tol_y,
            resize_method=args.resize_method,
        )


def apply_edits(args: argparse.Namespace) -> None:
    candidates = load_candidates(Path(args.candidates))
    page_config = load_page_config(Path(args.page_config) if args.page_config else None)
    out_root = Path(args.out_root)
    corrected_root = Path(args.corrected_root)
    corrected_root.mkdir(parents=True, exist_ok=True)

    summary_rows = []

    for candidate in candidates:
        if candidate.page not in page_config:
            raise ValueError(f"Missing page config for {candidate.page}")
        cfg = page_config[candidate.page]
        gt_path = Path(cfg["gt"])
        gt_entries = load_gt_entries(gt_path)
        image_path = Path(cfg["image"])
        image_size = None
        if image_path.exists():
            with Image.open(image_path) as img:
                image_size = img.size

        edit_path = out_root / candidate.page / f"fn_{candidate.gt_index:03d}" / "edit_template.json"
        if not edit_path.exists():
            raise FileNotFoundError(f"Missing edit template: {edit_path}")
        meta = read_json(edit_path)

        status = meta.get("status", "unchanged")
        orig_bbox = tuple(meta["orig_gt_bbox"])
        crop_box = tuple(meta["crop_box"])
        scale = int(meta["scale"])

        if status == "invalid":
            gt_entries[candidate.gt_index]["barline_location"] = [0, 0, 0, 0]
            gt_entries[candidate.gt_index]["invalid_gt"] = True
            summary_rows.append(
                {
                    "page": candidate.page,
                    "gt_index": candidate.gt_index,
                    "status": "invalid",
                    "old_bbox": orig_bbox,
                    "new_bbox": [0, 0, 0, 0],
                }
            )
        else:
            edited_bbox = meta.get("edited_bbox")
            if status == "edited" and edited_bbox:
                scaled_bbox = tuple(int(v) for v in edited_bbox)
            else:
                scaled_bbox = tuple(int(v) for v in meta["scaled_gt_bbox"])
                scaled_bbox = apply_delta(scaled_bbox, meta.get("delta", {}))

            new_bbox = unscale_box(scaled_bbox, crop_box, scale)
            if image_size is not None:
                new_bbox = clamp_box(new_bbox, width=image_size[0], height=image_size[1])

            gt_entries[candidate.gt_index]["barline_location"] = list(new_bbox)
            summary_rows.append(
                {
                    "page": candidate.page,
                    "gt_index": candidate.gt_index,
                    "status": "adjusted" if tuple(new_bbox) != tuple(orig_bbox) else "unchanged",
                    "old_bbox": orig_bbox,
                    "new_bbox": new_bbox,
                }
            )

        out_page_dir = corrected_root / candidate.page
        out_page_dir.mkdir(parents=True, exist_ok=True)
        corrected_path = out_page_dir / "fn_only_corrected.json"
        corrected_path.write_text(json.dumps(gt_entries, indent=2))

    summary_path = corrected_root / "diff_summary.csv"
    with summary_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["page", "gt_index", "status", "old_bbox", "new_bbox"])
        writer.writeheader()
        writer.writerows(summary_rows)


def near_hit_check(args: argparse.Namespace) -> None:
    candidates = load_candidates(Path(args.candidates))
    page_config = load_page_config(Path(args.page_config) if args.page_config else None)
    corrected_root = Path(args.corrected_root)
    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    results = []
    remaining = 0
    resolved = 0

    for candidate in candidates:
        cfg = page_config[candidate.page]
        corrected_path = corrected_root / candidate.page / "fn_only_corrected.json"
        if not corrected_path.exists():
            raise FileNotFoundError(f"Missing corrected GT: {corrected_path}")
        gt_entries = load_gt_entries(corrected_path)
        gt_entry = gt_entries[candidate.gt_index]
        if gt_entry.get("invalid_gt"):
            results.append(
                {
                    "page": candidate.page,
                    "gt_index": candidate.gt_index,
                    "status": "invalid",
                }
            )
            continue
        gt_bbox = tuple(gt_entry["barline_location"])

        detections = []
        detections += load_boxes(Path(cfg.get("baseline", "")))
        detections += load_boxes(Path(cfg.get("sr", "")))
        detections += load_boxes(Path(cfg.get("omr", "")))

        hit = any(near_hit(gt_bbox, det, args.tol_x, args.tol_y) for det in detections)
        if hit:
            resolved += 1
            status = "resolved"
        else:
            remaining += 1
            status = "remaining_miss"
        results.append({"page": candidate.page, "gt_index": candidate.gt_index, "status": status})

    results_path = out_root / "near_hit_recheck.csv"
    with results_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["page", "gt_index", "status"])
        writer.writeheader()
        writer.writerows(results)

    summary_path = out_root / "near_hit_recheck_summary.json"
    summary = {"resolved": resolved, "remaining_miss": remaining, "total": resolved + remaining}
    summary_path.write_text(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="GT relabel support (human-in-the-loop)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="Generate enlarged crops and edit templates")
    prepare_parser.add_argument("--candidates", required=True)
    prepare_parser.add_argument("--page-config", default=None)
    prepare_parser.add_argument("--out-root", default="logs/phase6_detector_miss/gt_fix_review")
    prepare_parser.add_argument("--scale", type=int, default=4)
    prepare_parser.add_argument("--margin-x", type=int, default=40)
    prepare_parser.add_argument("--margin-y", type=int, default=120)
    prepare_parser.add_argument("--tol-x", type=int, default=12)
    prepare_parser.add_argument("--tol-y", type=int, default=8)
    prepare_parser.add_argument("--resize-method", choices=["nearest", "bicubic", "lanczos"], default="nearest")
    prepare_parser.add_argument("--limit", type=int, default=None, help="Limit number of candidates for a quick smoke test")
    prepare_parser.set_defaults(func=prepare)

    apply_parser = subparsers.add_parser("apply", help="Apply edited templates to generate corrected GT")
    apply_parser.add_argument("--candidates", required=True)
    apply_parser.add_argument("--page-config", default=None)
    apply_parser.add_argument("--out-root", default="logs/phase6_detector_miss/gt_fix_review")
    apply_parser.add_argument("--corrected-root", default="logs/phase6_detector_miss/gt_fix_review/gt_corrected")
    apply_parser.set_defaults(func=apply_edits)

    check_parser = subparsers.add_parser("near-hit", help="Re-run near-hit check on corrected GT")
    check_parser.add_argument("--candidates", required=True)
    check_parser.add_argument("--page-config", default=None)
    check_parser.add_argument("--corrected-root", default="logs/phase6_detector_miss/gt_fix_review/gt_corrected")
    check_parser.add_argument("--out-root", default="logs/phase6_detector_miss/gt_fix_review/near_hit_recheck")
    check_parser.add_argument("--tol-x", type=int, default=12)
    check_parser.add_argument("--tol-y", type=int, default=8)
    check_parser.set_defaults(func=near_hit_check)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
