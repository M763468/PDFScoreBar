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
            for key in key_candidates:
                if rec.get(key):
                    bbox = rec.get(key)
                    break
            if bbox and len(bbox) == 4:
                boxes.append(tuple(map(int, bbox)))
    return boxes


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
    ap.add_argument("--dot-color", default="0,255,0")
    ap.add_argument("--radius", type=int, default=2)
    args = ap.parse_args()

    base = cv2.imread(args.base, cv2.IMREAD_COLOR)
    if base is None:
        raise SystemExit(f"Failed to load base image: {args.base}")
    h, w = base.shape[:2]
    boxes = load_boxes(Path(args.pred))
    color = tuple(int(c) for c in args.dot_color.split(","))

    q_counts = {"q1": 0, "q2": 0, "q3": 0, "q4": 0}
    for x1, y1, x2, y2 in boxes:
        cx = int(round((x1 + x2) / 2))
        cy = int(round((y1 + y2) / 2))
        cv2.circle(base, (cx, cy), args.radius, color, -1, cv2.LINE_AA)
        if cx < w / 2 and cy < h / 2:
            q_counts["q1"] += 1
        elif cx >= w / 2 and cy < h / 2:
            q_counts["q2"] += 1
        elif cx < w / 2 and cy >= h / 2:
            q_counts["q3"] += 1
        else:
            q_counts["q4"] += 1

    lines = [
        args.legend,
        f"base: {args.base}",
        f"pred: {args.pred}",
        f"counts: q1={q_counts['q1']} q2={q_counts['q2']} q3={q_counts['q3']} q4={q_counts['q4']}",
    ]
    put_text_block(base, lines, origin=(10, 20), color=(0, 0, 0))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(out), base):
        raise SystemExit(f"Failed to write output: {out}")

    print(json.dumps({"width": w, "height": h, "quadrants": q_counts}))


if __name__ == "__main__":
    main()
