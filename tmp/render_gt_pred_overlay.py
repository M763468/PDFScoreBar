#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import cv2


def load_boxes(path: Path, key_candidates=("barline_location", "orig_bbox", "pred_bbox")):
    with path.open() as f:
        data = json.load(f)
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
            bbox = None
            for k in key_candidates:
                if rec.get(k):
                    bbox = rec.get(k)
                    break
            if bbox and len(bbox) == 4:
                boxes.append(tuple(map(int, bbox)))
    return boxes


def draw_boxes(img, boxes, color, thickness):
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--gt", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--gt-color", default="0,0,255")  # BGR red
    ap.add_argument("--pred-color", default="0,255,0")
    ap.add_argument("--alpha", type=float, default=0.65)
    ap.add_argument("--thickness", type=int, default=2)
    args = ap.parse_args()
    base = cv2.imread(args.base, cv2.IMREAD_COLOR)
    if base is None:
        raise SystemExit(f"Failed to load base image: {args.base}")
    gt_boxes = load_boxes(Path(args.gt))
    pred_boxes = load_boxes(Path(args.pred))
    overlay = base.copy()
    gt_color = tuple(int(c) for c in args.gt_color.split(","))
    pred_color = tuple(int(c) for c in args.pred_color.split(","))
    draw_boxes(overlay, gt_boxes, gt_color, args.thickness)
    draw_boxes(overlay, pred_boxes, pred_color, args.thickness)
    alpha = min(max(args.alpha, 0.0), 1.0)
    blended = cv2.addWeighted(overlay, alpha, base, 1.0 - alpha, 0.0)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(out), blended):
        raise SystemExit(f"Failed to write output: {out}")


if __name__ == "__main__":
    main()
