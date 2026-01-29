#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import List, Tuple

import cv2

Box = Tuple[int, int, int, int]


def load_gt_boxes(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    boxes = []
    for item in data:
        bbox = item.get("barline_location")
        if bbox and len(bbox) == 4:
            boxes.append(tuple(map(int, bbox)))
    return boxes


def put_text_block(img, lines, origin=(10, 20)):
    x, y = origin
    for line in lines:
        cv2.putText(img, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2, cv2.LINE_AA)
        y += 18


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--overlay", required=True)
    ap.add_argument("--gt", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--method", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    overlay = cv2.imread(args.overlay, cv2.IMREAD_COLOR)
    if overlay is None:
        raise SystemExit(f"Failed to load overlay: {args.overlay}")

    gt_boxes = load_gt_boxes(Path(args.gt))
    # add numeric callouts for first three GT boxes
    for i, (x1, y1, x2, y2) in enumerate(gt_boxes[:3], start=1):
        cx = int(round((x1 + x2) / 2))
        cy = int(round((y1 + y2) / 2))
        cv2.circle(overlay, (cx, cy), 10, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.putText(
            overlay,
            str(i),
            (cx - 5, cy + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )

    legend = [
        f"Method: {args.method} | Run: {args.run_id}",
        f"Base: {args.base}",
        f"Overlay: {args.overlay}",
        "Legend: Red=GT, Green=Pred",
    ]
    put_text_block(overlay, legend, origin=(10, 20))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), overlay)


if __name__ == "__main__":
    main()
