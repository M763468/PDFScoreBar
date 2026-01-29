#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

Box = Tuple[int, int, int, int]


def load_homr_boxes(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    preds = []
    for entry in data.get("predictions", []):
        bbox = entry.get("orig_bbox") or entry.get("pred_bbox")
        if bbox and len(bbox) == 4:
            preds.append(tuple(map(int, bbox)))
    return preds


def load_omr_boxes(path: Path) -> List[Box]:
    data = json.loads(path.read_text())
    return [tuple(map(int, box)) for box in data]


def union_boxes(a: Sequence[Box], b: Sequence[Box]) -> List[Box]:
    seen = set(a)
    merged = list(a)
    for box in b:
        if box not in seen:
            merged.append(box)
            seen.add(box)
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build union(homr, omr-dln) inputs for Phase 4 filter checks."
    )
    parser.add_argument(
        "--homr-json", type=Path, required=True, help="Homr detections JSON with predictions."
    )
    parser.add_argument(
        "--omr-json", type=Path, required=True, help="OMR-DLN predictions JSON (list of boxes)."
    )
    parser.add_argument("--output-json", type=Path, required=True, help="Output union JSON path.")
    args = parser.parse_args()

    homr_boxes = load_homr_boxes(args.homr_json)
    omr_boxes = load_omr_boxes(args.omr_json)
    union = union_boxes(homr_boxes, omr_boxes)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(union, indent=2))


if __name__ == "__main__":
    main()
