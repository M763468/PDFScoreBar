#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import cv2


def load_boxes(path: Path):
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
            bbox = rec.get("pred_bbox") or rec.get("orig_bbox") or rec.get("barline_location")
            if bbox and len(bbox) == 4:
                boxes.append(tuple(map(int, bbox)))
    return boxes


def draw_boxes(img, boxes, color, thickness):
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)


def put_text_block(img, lines, origin=(10, 20), color=(0, 0, 0)):
    x, y = origin
    for line in lines:
        cv2.putText(img, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2, cv2.LINE_AA)
        y += 18


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--legend", required=True)
    ap.add_argument("--pred-color", default="0,255,0")  # BGR green
    ap.add_argument("--staff-color", default="255,0,0")  # BGR blue
    ap.add_argument("--alpha", type=float, default=0.65)
    ap.add_argument("--thickness", type=int, default=2)
    args = ap.parse_args()

    base = cv2.imread(args.base, cv2.IMREAD_COLOR)
    if base is None:
        raise SystemExit(f"Failed to load base image: {args.base}")
    pred_boxes = load_boxes(Path(args.pred))

    overlay = base.copy()
    pred_color = tuple(int(c) for c in args.pred_color.split(","))
    staff_color = tuple(int(c) for c in args.staff_color.split(","))
    draw_boxes(overlay, pred_boxes, pred_color, args.thickness)
    # staff bounds = full image frame
    h, w = base.shape[:2]
    cv2.rectangle(overlay, (0, 0), (w - 1, h - 1), staff_color, 2)

    alpha = min(max(args.alpha, 0.0), 1.0)
    blended = cv2.addWeighted(overlay, alpha, base, 1.0 - alpha, 0.0)

    lines = [
        args.legend,
        f"base: {args.base}",
        f"pred: {args.pred}",
    ]
    put_text_block(blended, lines, origin=(10, 20), color=(0, 0, 0))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(out), blended):
        raise SystemExit(f"Failed to write output: {out}")


if __name__ == "__main__":
    main()
