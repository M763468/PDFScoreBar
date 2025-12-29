#!/usr/bin/env python3
"""Render overlays for remaining FN targets with detector predictions."""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import cv2


REPO_ROOT = Path(__file__).resolve().parents[1]


Box = Tuple[int, int, int, int]


@dataclass(frozen=True)
class PagePaths:
    name: str
    image: Path
    homr_json: Path
    omr_json: Path
    hybrid_json: Path


def load_boxes(path: Path) -> List[Box]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    records = data.get("predictions") if isinstance(data, dict) and "predictions" in data else data
    boxes: List[Box] = []
    for record in records:
        if isinstance(record, list) and len(record) == 4:
            boxes.append(tuple(map(int, record)))
            continue
        if isinstance(record, dict):
            bbox = record.get("barline_location") or record.get("orig_bbox") or record.get("pred_bbox")
            if bbox and len(bbox) == 4:
                boxes.append(tuple(map(int, bbox)))
    return boxes


def load_remaining_fn_targets(
    recheck_csv: Path, classification_csv: Path
) -> Dict[str, Dict[int, Box]]:
    remaining: Dict[str, set[int]] = {}
    with recheck_csv.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("status") != "remaining_miss":
                continue
            page = row["page"]
            gt_index = int(row["gt_index"])
            remaining.setdefault(page, set()).add(gt_index)

    targets: Dict[str, Dict[int, Box]] = {}
    with classification_csv.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            page = row["page"]
            gt_index = int(row["gt_index"])
            if page not in remaining or gt_index not in remaining[page]:
                continue
            bbox = json.loads(row["gt_bbox"])
            targets.setdefault(page, {})[gt_index] = tuple(map(int, bbox))
    return targets


def get_page_paths(page: str) -> Optional[PagePaths]:
    eval_image = REPO_ROOT / "data/evaluation/images" / f"{page}.png"
    train_image = REPO_ROOT / "data/training/images" / f"{page}.png"
    image = eval_image if eval_image.exists() else train_image
    if not image.exists():
        return None
    homr_json = (
        REPO_ROOT
        / "logs/phase5b_homr_recall/homr_factor_1p0"
        / page
        / f"{page}_detections.json"
    )
    omr_json = (
        REPO_ROOT
        / "logs/phase5b/b1_1/omrdln_sweep/20251221T123707/omr_dln/conf_0p5"
        / page
        / "predictions.json"
    )
    hybrid_json = REPO_ROOT / "logs/phase5b_promiscuous_union_eval" / f"{page}_hybrid_preds.json"
    return PagePaths(name=page, image=image, homr_json=homr_json, omr_json=omr_json, hybrid_json=hybrid_json)


def draw_boxes(base: "cv2.Mat", boxes: Iterable[Box], color: Tuple[int, int, int], thickness: int) -> None:
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(base, (x1, y1), (x2, y2), color, thickness)


def draw_legend(base: "cv2.Mat", legend_items: List[Tuple[str, Tuple[int, int, int]]]) -> None:
    x0, y0 = 12, 12
    line_h = 18
    box_w = 310
    box_h = 14 + line_h * len(legend_items)
    cv2.rectangle(base, (x0 - 6, y0 - 10), (x0 + box_w, y0 + box_h), (255, 255, 255), -1)
    cv2.rectangle(base, (x0 - 6, y0 - 10), (x0 + box_w, y0 + box_h), (0, 0, 0), 1)
    for idx, (label, color) in enumerate(legend_items):
        y = y0 + idx * line_h
        cv2.rectangle(base, (x0, y), (x0 + 12, y + 12), color, -1)
        cv2.rectangle(base, (x0, y), (x0 + 12, y + 12), (0, 0, 0), 1)
        cv2.putText(base, label, (x0 + 20, y + 11), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "logs/phase6_detector_miss/remaining_fn_overlays",
        help="Root directory for overlay outputs",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Optional run id (defaults to timestamp)",
    )
    parser.add_argument(
        "--pages",
        type=str,
        default=None,
        help="Comma-separated pages to render (default: pages with remaining FN targets)",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    recheck_csv = REPO_ROOT / "logs/phase6_detector_miss/gt_fix_review_full/near_hit_recheck/near_hit_recheck.csv"
    classification_csv = REPO_ROOT / "logs/phase6_detector_miss/detector_miss_classification.csv"

    targets = load_remaining_fn_targets(recheck_csv, classification_csv)
    if args.pages:
        pages = [p.strip() for p in args.pages.split(",") if p.strip()]
    else:
        pages = sorted(targets.keys())

    run_id = args.run_id or cv2.getTickCount()
    output_root = args.output_root / str(run_id)
    output_root.mkdir(parents=True, exist_ok=True)

    legend_items = [
        ("FN targets (remaining_miss)", (255, 0, 255)),
        ("homr raw detections", (0, 0, 255)),
        ("omr-dln raw detections", (0, 255, 0)),
        ("hybrid (promiscuous_union)", (255, 255, 0)),
    ]

    readme = [
        "# Remaining FN overlay legend",
        "",
        "- FN targets (remaining_miss): magenta",
        "- homr raw detections: red",
        "- omr-dln raw detections: green",
        "- hybrid (promiscuous_union): cyan",
        "",
        "Two overlays per page:",
        "- *_combined.png: all layers above",
        "- *_fn_only.png: FN targets only",
    ]
    (output_root / "README.md").write_text("\n".join(readme) + "\n")

    for page in pages:
        page_paths = get_page_paths(page)
        if not page_paths:
            print(f"[skip] image missing for {page}")
            continue
        base = cv2.imread(str(page_paths.image), cv2.IMREAD_COLOR)
        if base is None:
            print(f"[skip] failed to load image: {page_paths.image}")
            continue

        fn_targets = list((targets.get(page) or {}).values())
        homr_boxes = load_boxes(page_paths.homr_json)
        omr_boxes = load_boxes(page_paths.omr_json)
        hybrid_boxes = load_boxes(page_paths.hybrid_json)

        combined = base.copy()
        draw_boxes(combined, homr_boxes, (0, 0, 255), 2)
        draw_boxes(combined, omr_boxes, (0, 255, 0), 2)
        draw_boxes(combined, hybrid_boxes, (255, 255, 0), 2)
        draw_boxes(combined, fn_targets, (255, 0, 255), 3)
        draw_legend(combined, legend_items)
        cv2.imwrite(str(output_root / f"{page}_combined.png"), combined)

        fn_only = base.copy()
        draw_boxes(fn_only, fn_targets, (255, 0, 255), 3)
        draw_legend(fn_only, [legend_items[0]])
        cv2.imwrite(str(output_root / f"{page}_fn_only.png"), fn_only)


if __name__ == "__main__":
    main()
