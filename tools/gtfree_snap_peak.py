#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

Box = Tuple[int, int, int, int]


def load_boxes(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    if isinstance(data, dict) and "predictions" in data:
        records = data["predictions"]
    else:
        records = data
    boxes = []
    for rec in records:
        if isinstance(rec, list) and len(rec) == 4:
            boxes.append(tuple(map(int, rec)))
            continue
        if isinstance(rec, dict):
            bbox = rec.get("orig_bbox") or rec.get("pred_bbox") or rec.get("barline_location")
            if bbox and len(bbox) == 4:
                boxes.append(tuple(map(int, bbox)))
    return boxes


def snap_boxes_to_peaks(base: np.ndarray, boxes: List[Box], window: int) -> List[Box]:
    gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    ink = 255 - gray
    col_sum = ink.sum(axis=0).astype(np.float32)
    h, w = gray.shape[:2]
    snapped = []
    for x1, y1, x2, y2 in boxes:
        cx = int(round((x1 + x2) / 2))
        lo = max(0, cx - window)
        hi = min(w - 1, cx + window)
        if hi <= lo:
            peak = cx
        else:
            peak = int(np.argmax(col_sum[lo:hi + 1]) + lo)
        width = max(1, x2 - x1)
        half = max(1, width // 2)
        snapped.append((peak - half, y1, peak + half, y2))
    snapped.sort(key=lambda b: b[0])
    deduped = []
    for b in snapped:
        if not deduped or b[0] - deduped[-1][0] >= 2:
            deduped.append(b)
    return deduped


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--window", type=int, default=6)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    base = cv2.imread(str(args.base), cv2.IMREAD_COLOR)
    if base is None:
        raise SystemExit(f"Failed to load base image: {args.base}")
    boxes = load_boxes(args.pred)
    snapped = snap_boxes_to_peaks(base, boxes, args.window)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapped, indent=2))


if __name__ == "__main__":
    main()
