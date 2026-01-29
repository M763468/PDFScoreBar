#!/usr/bin/env python3
"""Draw barline bounding boxes from a JSON file onto a score image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import cv2


def parse_color(color: str) -> tuple[int, int, int]:
    try:
        components = [int(v) for v in color.split(",")]
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise SystemExit(f"Invalid color specification: {color}") from exc
    if len(components) != 3:
        raise SystemExit("Color must contain exactly three comma separated integers")
    if not all(0 <= v <= 255 for v in components):
        raise SystemExit("Color components must be within [0, 255]")
    return tuple(components)


def iter_bboxes(json_path: Path) -> Iterable[tuple[list[int], int]]:
    with json_path.open() as handle:
        payload = json.load(handle)

    if isinstance(payload, dict) and "predictions" in payload:
        records = payload["predictions"]
    else:
        records = payload

    for record in records:
        if isinstance(record, list) and len(record) == 4:
            # Direct coordinate list [x1, y1, x2, y2]
            yield record, None
            continue

        # Dictionary format
        measure = record.get("measure_number")
        bbox = record.get("barline_location") or record.get("orig_bbox") or record.get("pred_bbox")

        if not bbox or len(bbox) != 4:
            continue
        yield bbox, measure


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path, help="Path to the original page image")
    parser.add_argument(
        "--boxes", required=True, type=Path, help="JSON file containing barline boxes"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="Destination for the rendered overlay"
    )
    parser.add_argument(
        "--color", default="0,0,255", help="Comma separated B,G,R color (default: red)"
    )
    parser.add_argument(
        "--thickness", type=int, default=2, help="Rectangle thickness in pixels (default: 2)"
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.65,
        help="Alpha blend value in [0,1]; 1.0 draws solid rectangles",
    )
    parser.add_argument(
        "--show-measure",
        action="store_true",
        help="Render measure numbers near each rectangle when available",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    base = cv2.imread(str(args.base), cv2.IMREAD_COLOR)
    if base is None:
        raise SystemExit(f"Failed to load base image: {args.base}")

    overlay = base.copy()
    color = parse_color(args.color)
    thickness = max(1, args.thickness)

    for bbox, measure in iter_bboxes(args.boxes):
        x1, y1, x2, y2 = map(int, bbox)
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, thickness)
        if args.show_measure and measure is not None:
            cv2.putText(
                overlay,
                str(measure),
                (x1, max(0, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                color,
                1,
                cv2.LINE_AA,
            )

    alpha = min(max(args.alpha, 0.0), 1.0)
    if alpha < 1.0:
        blended = cv2.addWeighted(overlay, alpha, base, 1.0 - alpha, 0.0)
    else:
        blended = overlay

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(args.output), blended):
        raise SystemExit(f"Failed to write overlay image: {args.output}")


if __name__ == "__main__":
    main()
