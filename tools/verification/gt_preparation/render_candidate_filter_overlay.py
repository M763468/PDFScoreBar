#!/usr/bin/env python3
"""Render candidate filter overlay (all/keep/drop) on source image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2


def _load_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    payload = json.loads(path.read_text())
    records: Any = payload
    if isinstance(payload, dict):
        if "drop_suggested" in payload and "keep" in payload:
            # suggestion json format
            boxes: list[tuple[int, int, int, int]] = []
            for item in payload["drop_suggested"] + payload["keep"]:
                if isinstance(item, dict) and "bbox" in item and len(item["bbox"]) == 4:
                    boxes.append(tuple(int(v) for v in item["bbox"]))
            return boxes
        if "predictions" in payload:
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--all-candidates", type=Path, required=True)
    parser.add_argument("--keep-candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    img = cv2.imread(str(args.image))
    if img is None:
        raise FileNotFoundError(f"failed to load image: {args.image}")

    all_boxes = _load_boxes(args.all_candidates)
    keep_boxes = _load_boxes(args.keep_candidates)
    keep_set = set(keep_boxes)
    drop_boxes = [b for b in all_boxes if b not in keep_set]

    overlay = img.copy()

    # all candidates (thin gray)
    for x1, y1, x2, y2 in all_boxes:
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (150, 150, 150), 1)

    # keep (green)
    for x1, y1, x2, y2 in keep_boxes:
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 200, 0), 2)

    # drop (red)
    for x1, y1, x2, y2 in drop_boxes:
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), 2)

    # legend
    cv2.rectangle(overlay, (20, 20), (560, 96), (255, 255, 255), -1)
    cv2.putText(
        overlay,
        f"all={len(all_boxes)} keep={len(keep_boxes)} drop={len(drop_boxes)}",
        (30, 48),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (20, 20, 20),
        2,
    )
    cv2.putText(
        overlay,
        "green=keep, red=drop_suggested, gray=all",
        (30, 78),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (20, 20, 20),
        2,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(args.output), overlay):
        raise RuntimeError(f"failed to write output: {args.output}")
    print(str(args.output))


if __name__ == "__main__":
    main()
