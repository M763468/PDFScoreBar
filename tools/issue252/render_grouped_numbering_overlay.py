#!/usr/bin/env python3
"""Render Issue #252 grouping and numbering evidence directly on the score image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

from src.measure_numbering.pipeline import StaffExtractor

Box = tuple[int, int, int, int]

COLORS = {
    "raw_component": (190, 190, 190),
    "physical_component": (255, 0, 0),
    "connector_positive": (0, 160, 0),
    "connector_negative": (0, 0, 200),
    "system": (180, 0, 180),
    "cnn_barline": (255, 140, 0),
    "boundary": (0, 180, 180),
    "measure": (0, 120, 0),
    "target": (0, 0, 255),
    "nearby": (0, 140, 255),
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _bbox(value: Any) -> Box | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) < 4:
        return None
    return tuple(int(round(float(item))) for item in value[:4])  # type: ignore[return-value]


def _clip_box(box: Box, width: int, height: int) -> Box:
    x1, y1, x2, y2 = box
    return (
        max(0, min(width, min(x1, x2))),
        max(0, min(height, min(y1, y2))),
        max(0, min(width, max(x1, x2))),
        max(0, min(height, max(y1, y2))),
    )


def _raw_components(mask_path: Path, image_size: tuple[int, int]) -> list[Box]:
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(mask_path)
    target_width, target_height = image_size
    mask_height, mask_width = mask.shape[:2]
    _, binary = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    result = []
    scale_x = target_width / mask_width
    scale_y = target_height / mask_height
    for index in range(1, count):
        x = int(stats[index, cv2.CC_STAT_LEFT])
        y = int(stats[index, cv2.CC_STAT_TOP])
        width = int(stats[index, cv2.CC_STAT_WIDTH])
        height = int(stats[index, cv2.CC_STAT_HEIGHT])
        if width <= 1 or height <= 1:
            continue
        result.append(
            (
                int(round(x * scale_x)),
                int(round(y * scale_y)),
                int(round((x + width) * scale_x)),
                int(round((y + height) * scale_y)),
            )
        )
    return sorted(result, key=lambda box: (box[1], box[0]))


def _physical_components(mask_path: Path, image_size: tuple[int, int]) -> list[Box]:
    return [
        (staff.bbox.x1, staff.bbox.y1, staff.bbox.x2, staff.bbox.y2)
        for staff in StaffExtractor().extract(mask_path, image_size)
    ]


def _page(numbering: Any) -> Mapping[str, Any]:
    if not isinstance(numbering, Mapping):
        raise ValueError("Numbering payload must be an object")
    pages = numbering.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], Mapping):
        raise ValueError("Expected one-page numbering payload")
    return pages[0]


def _draw_box(
    canvas: np.ndarray,
    box: Box,
    color: tuple[int, int, int],
    *,
    thickness: int = 1,
    label: str | None = None,
) -> None:
    x1, y1, x2, y2 = box
    cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness)
    if label:
        cv2.putText(
            canvas,
            label,
            (x1 + 3, max(14, y1 - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            color,
            1,
            cv2.LINE_AA,
        )


def _draw_translucent_box(
    canvas: np.ndarray,
    box: Box,
    color: tuple[int, int, int],
    *,
    alpha: float,
) -> None:
    overlay = canvas.copy()
    x1, y1, x2, y2 = box
    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, cv2.FILLED)
    cv2.addWeighted(overlay, alpha, canvas, 1.0 - alpha, 0, canvas)


def _connector_roi(item: Mapping[str, Any]) -> Box | None:
    for group_name in ("symbols", "brace_dot"):
        group = item.get(group_name)
        if isinstance(group, Mapping):
            roi = _bbox(group.get("roi_xyxy"))
            if roi is not None:
                return roi
    return None


def _system_box(system: Mapping[str, Any]) -> Box | None:
    components = [
        box
        for item in system.get("staves", [])
        if isinstance(item, Mapping) and (box := _bbox(item.get("bbox"))) is not None
    ]
    if not components:
        return None
    return (
        min(box[0] for box in components),
        min(box[1] for box in components),
        max(box[2] for box in components),
        max(box[3] for box in components),
    )


def _legend(canvas: np.ndarray, title: str) -> np.ndarray:
    entries = [
        ("raw mask CC", COLORS["raw_component"]),
        ("interpreted band", COLORS["physical_component"]),
        ("connector +", COLORS["connector_positive"]),
        ("connector -", COLORS["connector_negative"]),
        ("final system", COLORS["system"]),
        ("CNN bbox", COLORS["cnn_barline"]),
        ("used boundary", COLORS["boundary"]),
        ("measure interval/no.", COLORS["measure"]),
        ("target FN", COLORS["target"]),
        ("upper matching bbox", COLORS["nearby"]),
    ]
    header_height = 88
    output = np.full((canvas.shape[0] + header_height, canvas.shape[1], 3), 255, dtype=np.uint8)
    output[header_height:] = canvas
    cv2.putText(
        output,
        title,
        (12, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (20, 20, 20),
        1,
        cv2.LINE_AA,
    )
    x = 12
    y = 48
    for text, color in entries:
        cv2.rectangle(output, (x, y - 10), (x + 14, y + 2), color, cv2.FILLED)
        cv2.putText(
            output,
            text,
            (x + 19, y + 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.36,
            (20, 20, 20),
            1,
            cv2.LINE_AA,
        )
        x += max(105, 25 + len(text) * 7)
        if x > output.shape[1] - 130:
            x = 12
            y += 22
    return output


def render_overlay(
    *,
    image_path: Path,
    staff_mask_path: Path,
    connector_evidence_path: Path,
    numbering_path: Path,
    cnn_barlines_path: Path,
    output_path: Path,
    target: Box,
    nearby: Box,
    label: str,
    crop: Box | None = None,
) -> dict[str, Any]:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)
    height, width = image.shape[:2]
    numbering = _load(numbering_path)
    page = _page(numbering)
    connector = _load(connector_evidence_path)
    cnn_barlines_raw = _load(cnn_barlines_path)
    if not isinstance(cnn_barlines_raw, list):
        raise ValueError("CNN barline payload must be a list")
    cnn_barlines = [box for value in cnn_barlines_raw if (box := _bbox(value)) is not None]

    raw_components = _raw_components(staff_mask_path, (width, height))
    physical_components = _physical_components(staff_mask_path, (width, height))
    canvas = image.copy()

    for box in raw_components:
        _draw_box(canvas, _clip_box(box, width, height), COLORS["raw_component"])
    for index, box in enumerate(physical_components):
        _draw_box(
            canvas,
            _clip_box(box, width, height),
            COLORS["physical_component"],
            thickness=2,
            label=f"C{index}",
        )

    connector_records = []
    if not isinstance(connector, Mapping):
        raise ValueError("Connector evidence must be an object")
    for item in connector.get("staff_pairs", []):
        if not isinstance(item, Mapping):
            continue
        pair = item.get("staff_pair")
        roi = _connector_roi(item)
        if roi is None:
            continue
        positive = item.get("left_connector_present") is True
        color = COLORS["connector_positive"] if positive else COLORS["connector_negative"]
        pair_label = (
            f"P{pair[0]}-{pair[1]} {'+' if positive else '-'}"
            if isinstance(pair, Sequence) and len(pair) == 2
            else f"P? {'+' if positive else '-'}"
        )
        _draw_box(canvas, _clip_box(roi, width, height), color, thickness=2, label=pair_label)
        connector_records.append(
            {
                "staff_pair": list(pair) if isinstance(pair, Sequence) else None,
                "positive": positive,
                "roi": list(roi),
            }
        )

    system_records = []
    for system_index, system in enumerate(page.get("systems", [])):
        if not isinstance(system, Mapping):
            continue
        system_box = _system_box(system)
        if system_box is None:
            continue
        _draw_box(
            canvas,
            _clip_box(system_box, width, height),
            COLORS["system"],
            thickness=3,
            label=f"S{system_index}",
        )

        measures = [item for item in system.get("measures", []) if isinstance(item, Mapping)]
        boundaries = set()
        for measure in measures:
            measure_box = _bbox(measure.get("bbox"))
            if measure_box is None:
                continue
            clipped_measure = _clip_box(measure_box, width, height)
            _draw_translucent_box(canvas, clipped_measure, COLORS["measure"], alpha=0.055)
            x1, y1, x2, _y2 = clipped_measure
            boundaries.update((x1, x2))
            cv2.putText(
                canvas,
                str(measure.get("number")),
                (int((x1 + x2) / 2), max(18, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                COLORS["measure"],
                1,
                cv2.LINE_AA,
            )
        for boundary_x in sorted(boundaries):
            cv2.line(
                canvas,
                (int(boundary_x), int(system_box[1])),
                (int(boundary_x), int(system_box[3])),
                COLORS["boundary"],
                2,
            )
        system_records.append(
            {
                "system_index": system_index,
                "bbox": list(system_box),
                "measure_count": len(measures),
                "boundaries_x": sorted(boundaries),
            }
        )

    for box in cnn_barlines:
        _draw_box(canvas, _clip_box(box, width, height), COLORS["cnn_barline"], thickness=1)

    _draw_box(canvas, _clip_box(target, width, height), COLORS["target"], thickness=4, label="target")
    _draw_box(canvas, _clip_box(nearby, width, height), COLORS["nearby"], thickness=3, label="upper")

    crop_box = _clip_box(crop or (0, 0, width, height), width, height)
    x1, y1, x2, y2 = crop_box
    cropped = canvas[y1:y2, x1:x2].copy()
    titled = _legend(
        cropped,
        f"Issue #252 grouped-numbering evidence | {label} | crop={crop_box}",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), titled):
        raise OSError(f"Could not write overlay: {output_path}")

    manifest = {
        "schema_version": "issue252.grouped_numbering_overlay.v1",
        "label": label,
        "image": str(image_path.resolve()),
        "staff_mask": str(staff_mask_path.resolve()),
        "connector_evidence": str(connector_evidence_path.resolve()),
        "numbering": str(numbering_path.resolve()),
        "cnn_barlines": str(cnn_barlines_path.resolve()),
        "output": str(output_path.resolve()),
        "crop": list(crop_box),
        "raw_staff_mask_connected_components": [list(box) for box in raw_components],
        "interpreted_physical_components": [list(box) for box in physical_components],
        "connector_pairs": connector_records,
        "systems": system_records,
        "cnn_barline_count": len(cnn_barlines),
        "target_bbox": list(target),
        "nearby_bbox": list(nearby),
        "serialized_staves_interpretation": "staff-mask connected components, not musical staff count",
    }
    manifest_path = output_path.with_suffix(".json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--staff-mask", type=Path, required=True)
    parser.add_argument("--connector-evidence", type=Path, required=True)
    parser.add_argument("--numbering", type=Path, required=True)
    parser.add_argument("--cnn-barlines", type=Path, required=True)
    parser.add_argument("--target-bbox", type=int, nargs=4, required=True)
    parser.add_argument("--nearby-bbox", type=int, nargs=4, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--crop", type=int, nargs=4)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = render_overlay(
        image_path=args.image,
        staff_mask_path=args.staff_mask,
        connector_evidence_path=args.connector_evidence,
        numbering_path=args.numbering,
        cnn_barlines_path=args.cnn_barlines,
        output_path=args.output,
        target=tuple(args.target_bbox),  # type: ignore[arg-type]
        nearby=tuple(args.nearby_bbox),  # type: ignore[arg-type]
        label=args.label,
        crop=tuple(args.crop) if args.crop is not None else None,  # type: ignore[arg-type]
    )
    print(json.dumps({"status": "completed", "output": manifest["output"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
