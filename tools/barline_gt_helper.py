#!/usr/bin/env python3
"""Interactive helper for curating barline ground truth from detector outputs."""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import cv2


BoxType = Tuple[int, int, int, int]


@dataclass
class AnnotatedBox:
    coords: BoxType
    source: str  # detected | manual | preload
    selected: bool = False
    identifier: str = ""

    def contains(self, x: int, y: int) -> bool:
        x1, y1, x2, y2 = self.coords
        return x1 <= x <= x2 and y1 <= y <= y2


@dataclass
class AnnotatorState:
    image: any
    display_image: any
    scale: float
    boxes: List[AnnotatedBox] = field(default_factory=list)
    manual_points: List[Tuple[int, int]] = field(default_factory=list)
    window_name: str = "Barline GT Helper"
    status_message: str = ""

    def reset_manual(self) -> None:
        self.manual_points.clear()


COLOR_PENDING = (0, 215, 255)  # gold
COLOR_SELECTED = (0, 200, 0)   # green
COLOR_PRELOAD = (255, 128, 0)  # blue-ish
COLOR_MANUAL_PENDING = (255, 255, 0)  # cyan


def load_detection_boxes(path: Path) -> Iterable[BoxType]:
    with path.open() as handle:
        payload = json.load(handle)
    if isinstance(payload, dict) and "predictions" in payload:
        records = payload["predictions"]
        for record in records:
            coords = record.get("barline_location") or record.get("orig_bbox")
            if not coords:
                continue
            yield tuple(int(v) for v in coords)
    else:
        for record in payload:
            coords = record.get("barline_location")
            if not coords:
                continue
            yield tuple(int(v) for v in coords)


def load_existing_gt(path: Path) -> List[BoxType]:
    if not path.exists():
        return []
    with path.open() as handle:
        payload = json.load(handle)
    boxes: List[BoxType] = []
    for record in payload:
        coords = record.get("barline_location")
        if coords and len(coords) == 4:
            boxes.append(tuple(int(v) for v in coords))
    return boxes


def prepare_state(args: argparse.Namespace) -> AnnotatorState:
    image = cv2.imread(str(args.image), cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f"Failed to load image: {args.image}")

    height, width = image.shape[:2]
    scale = 1.0
    display_image = image.copy()
    if width > args.max_width or height > args.max_height:
        scale_w = args.max_width / width
        scale_h = args.max_height / height
        scale = min(scale_w, scale_h)
        display_image = cv2.resize(image, (int(width * scale), int(height * scale)))

    boxes: List[AnnotatedBox] = []
    existing_gt = load_existing_gt(args.preload) if args.preload else []
    existing_map: Dict[BoxType, AnnotatedBox] = {}
    for idx, box in enumerate(existing_gt):
        annotated = AnnotatedBox(coords=box, source="preload", selected=True, identifier=f"G{idx}")
        boxes.append(annotated)
        existing_map[box] = annotated

    for idx, coords in enumerate(load_detection_boxes(args.detections)):
        identifier = f"D{idx}"
        selected = False
        if coords in existing_map:
            existing_map[coords].identifier = identifier
            continue
        boxes.append(AnnotatedBox(coords=coords, source="detected", selected=selected, identifier=identifier))

    boxes.sort(key=lambda b: (b.coords[0], b.coords[1]))
    return AnnotatorState(image=image, display_image=display_image, scale=scale, boxes=boxes)


def draw(state: AnnotatorState) -> None:
    canvas = state.display_image.copy()
    for box in state.boxes:
        x1, y1, x2, y2 = box.coords
        x1d = int(x1 * state.scale)
        y1d = int(y1 * state.scale)
        x2d = int(x2 * state.scale)
        y2d = int(y2 * state.scale)

        if box.selected:
            color = COLOR_SELECTED
        elif box.source == "preload":
            color = COLOR_PRELOAD
        elif box.source == "manual":
            color = COLOR_MANUAL_PENDING
        else:
            color = COLOR_PENDING

        cv2.rectangle(canvas, (x1d, y1d), (x2d, y2d), color, 2)
        label = box.identifier or "?"
        cv2.putText(canvas, label, (x1d, max(0, y1d - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    if state.manual_points:
        pt1 = state.manual_points[0]
        cv2.circle(canvas, pt1, 4, (128, 255, 255), -1)

    if state.status_message:
        cv2.putText(
            canvas,
            state.status_message,
            (10, canvas.shape[0] - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

    cv2.imshow(state.window_name, canvas)


def toggle_box(state: AnnotatorState, x: int, y: int) -> None:
    original_x = int(x / state.scale)
    original_y = int(y / state.scale)
    hit_box: Optional[AnnotatedBox] = None
    min_area = math.inf
    for box in state.boxes:
        if box.contains(original_x, original_y):
            area = (box.coords[2] - box.coords[0]) * (box.coords[3] - box.coords[1])
            if area < min_area:
                min_area = area
                hit_box = box
    if hit_box:
        hit_box.selected = not hit_box.selected
        state.status_message = f"Toggled {hit_box.identifier or hit_box.source} -> {'selected' if hit_box.selected else 'skipped'}"
    else:
        state.status_message = "Click again to add manual barline."
        state.manual_points = [(original_x, original_y)]


def add_manual_box(state: AnnotatorState, x: int, y: int) -> None:
    if not state.manual_points:
        return
    pt1 = state.manual_points[0]
    pt2 = (int(x / state.scale), int(y / state.scale))
    x_min = min(pt1[0], pt2[0])
    x_max = max(pt1[0], pt2[0])
    y_min = min(pt1[1], pt2[1])
    y_max = max(pt1[1], pt2[1])
    if y_max - y_min < 2:
        state.status_message = "Manual box too small; cancelled."
        state.reset_manual()
        return
    rect_half = max(1, (x_max - x_min) // 2 or 3)
    center = (pt1[0] + pt2[0]) // 2
    box = AnnotatedBox(
        coords=(center - rect_half, y_min, center + rect_half, y_max),
        source="manual",
        selected=True,
        identifier=f"M{sum(1 for b in state.boxes if b.source == 'manual')}",
    )
    state.boxes.append(box)
    state.boxes.sort(key=lambda b: (b.coords[0], b.coords[1]))
    state.status_message = f"Added manual box {box.identifier}"
    state.reset_manual()


def save_selected(state: AnnotatorState, output_path: Path) -> None:
    selected_boxes = [box for box in state.boxes if box.selected]
    if not selected_boxes:
        state.status_message = "No boxes selected; skipped save."
        return
    selected_boxes.sort(key=lambda b: (b.coords[0], b.coords[1]))

    payload = []
    for idx, box in enumerate(selected_boxes, start=1):
        payload.append(
            {
                "measure_number": idx,
                "number_location": [0, 0, 0, 0],
                "barline_location": list(box.coords),
            }
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as handle:
        json.dump(payload, handle, indent=2)
    state.status_message = f"Saved {len(payload)} boxes -> {output_path}"


def mouse_handler(event, x, y, flags, param) -> None:
    state: AnnotatorState = param

    if event == cv2.EVENT_LBUTTONDOWN:
        if state.manual_points:
            add_manual_box(state, x, y)
        else:
            toggle_box(state, x, y)
        draw(state)


def run_gui(state: AnnotatorState, output_path: Path) -> None:
    cv2.namedWindow(state.window_name, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(state.window_name, mouse_handler, param=state)
    state.status_message = (
        "[click] toggle box    [s] save    [c] clear selection    [q] quit    [u] undo manual"
    )
    draw(state)

    while True:
        key = cv2.waitKey(50) & 0xFF
        if key == ord("q"):
            break
        if key == ord("s"):
            save_selected(state, output_path)
            draw(state)
        elif key == ord("c"):
            for box in state.boxes:
                box.selected = box.source == "preload"
            state.status_message = "Selection cleared (preload retained)."
            draw(state)
        elif key == ord("u"):
            manual_boxes = [box for box in state.boxes if box.source == "manual"]
            if manual_boxes:
                removed = manual_boxes[-1]
                state.boxes.remove(removed)
                state.status_message = f"Removed manual box {removed.identifier}"
            else:
                state.status_message = "No manual boxes to remove."
            state.reset_manual()
            draw(state)

    cv2.destroyAllWindows()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path, help="Score page image")
    parser.add_argument("--detections", required=True, type=Path, help="Detector JSON with predictions")
    parser.add_argument("--output", required=True, type=Path, help="Destination JSON for curated GT")
    parser.add_argument("--preload", type=Path, help="Optional existing GT to pre-select / merge")
    parser.add_argument("--max-width", type=int, default=1400, help="Maximum display width")
    parser.add_argument("--max-height", type=int, default=900, help="Maximum display height")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    state = prepare_state(args)
    run_gui(state, args.output)


if __name__ == "__main__":
    main()
