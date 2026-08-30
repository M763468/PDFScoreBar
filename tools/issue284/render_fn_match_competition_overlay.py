#!/usr/bin/env python3
"""Render Issue #284 raw-GT-slot competition on the original score images.

This is an investigation/review helper. It consumes the retained
``issue284.fn_match_competition.v1`` report and visualizes why a raw GT slot can
be counted as an FN even when a nearby physical barline prediction exists and
is assigned to another GT slot.

The tool does not rerun detection and does not modify any artifacts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

Box = tuple[int, int, int, int]

COLORS = {
    "target_gt": (0, 0, 255),
    "competing_gt": (0, 165, 255),
    "accepted_pred": (0, 170, 0),
    "current_pred": (255, 120, 0),
    "text": (20, 20, 20),
}


def _box(value: Any) -> Box | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) < 4:
        return None
    return tuple(int(round(float(item))) for item in value[:4])  # type: ignore[return-value]


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _draw_box(
    canvas: np.ndarray,
    box: Box,
    color: tuple[int, int, int],
    label: str,
    *,
    thickness: int = 3,
) -> None:
    x1, y1, x2, y2 = box
    cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness)
    cv2.putText(
        canvas,
        label,
        (x1 + 4, max(18, y1 - 5)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        color,
        1,
        cv2.LINE_AA,
    )


def _assignment_boxes(
    assignment: Mapping[str, Any],
) -> tuple[list[Box], list[tuple[int, Box]], list[dict[str, Any]]]:
    predictions: list[Box] = []
    assigned_gt: list[tuple[int, Box]] = []
    records: list[dict[str, Any]] = []
    for item in assignment.get("matching_predictions", []):
        if not isinstance(item, Mapping):
            continue
        pred = item.get("prediction")
        pred_box = _box(pred.get("box")) if isinstance(pred, Mapping) else None
        gt_box = _box(item.get("assigned_gt_box"))
        gt_index_raw = item.get("assigned_gt_index")
        gt_index = int(gt_index_raw) if gt_index_raw is not None else -1
        if pred_box is not None:
            predictions.append(pred_box)
        if gt_box is not None:
            assigned_gt.append((gt_index, gt_box))
        records.append(
            {
                "pred_index": item.get("pred_index"),
                "prediction": list(pred_box) if pred_box else None,
                "assigned_gt_index": gt_index_raw,
                "assigned_gt_box": list(gt_box) if gt_box else None,
                "assigned_to_target": item.get("assigned_to_target"),
                "status": item.get("status"),
            }
        )
    return predictions, assigned_gt, records


def _union_crop(
    boxes: list[Box],
    width: int,
    height: int,
    *,
    pad_x: int,
    pad_y: int,
    min_width: int = 520,
    min_height: int = 360,
) -> Box:
    x1 = min(box[0] for box in boxes)
    y1 = min(box[1] for box in boxes)
    x2 = max(box[2] for box in boxes)
    y2 = max(box[3] for box in boxes)

    x1 -= pad_x
    x2 += pad_x
    y1 -= pad_y
    y2 += pad_y

    if x2 - x1 < min_width:
        extra = min_width - (x2 - x1)
        x1 -= extra // 2
        x2 += extra - extra // 2
    if y2 - y1 < min_height:
        extra = min_height - (y2 - y1)
        y1 -= extra // 2
        y2 += extra - extra // 2

    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(width, x2)
    y2 = min(height, y2)
    return x1, y1, x2, y2


def _header(
    image: np.ndarray,
    *,
    title: str,
    lines: list[str],
) -> np.ndarray:
    header_h = 100 + 22 * len(lines)
    output = np.full(
        (image.shape[0] + header_h, image.shape[1], 3),
        255,
        dtype=np.uint8,
    )
    output[header_h:] = image
    cv2.putText(
        output,
        title,
        (12, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        COLORS["text"],
        1,
        cv2.LINE_AA,
    )
    legend = [
        ("target raw GT slot", COLORS["target_gt"]),
        ("competing/assigned GT", COLORS["competing_gt"]),
        ("accepted prediction", COLORS["accepted_pred"]),
        ("current prediction", COLORS["current_pred"]),
    ]
    x = 12
    y = 52
    for text, color in legend:
        cv2.rectangle(output, (x, y - 11), (x + 14, y + 2), color, cv2.FILLED)
        cv2.putText(
            output,
            text,
            (x + 20, y + 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            COLORS["text"],
            1,
            cv2.LINE_AA,
        )
        x += 165
    y = 78
    for line in lines:
        cv2.putText(
            output,
            line,
            (12, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            COLORS["text"],
            1,
            cv2.LINE_AA,
        )
        y += 22
    return output


def _letterbox(image: np.ndarray, width: int = 900, height: int = 520) -> np.ndarray:
    scale = min(width / image.shape[1], height / image.shape[0])
    resized = cv2.resize(
        image,
        (
            max(1, int(round(image.shape[1] * scale))),
            max(1, int(round(image.shape[0] * scale))),
        ),
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
    )
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    x = (width - resized.shape[1]) // 2
    y = (height - resized.shape[0]) // 2
    canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--image-root",
        type=Path,
        default=Path("data/evaluation2/images"),
        help="Root containing <score>/<page>.png",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pad-x", type=int, default=180)
    parser.add_argument("--pad-y", type=int, default=110)
    args = parser.parse_args()

    report = _load(args.report)
    if not isinstance(report, Mapping) or report.get("schema_version") != (
        "issue284.fn_match_competition.v1"
    ):
        raise ValueError("Expected issue284.fn_match_competition.v1 report")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[dict[str, Any]] = []
    sheet_tiles: list[np.ndarray] = []

    for ordinal, item in enumerate(report.get("false_negatives", []), start=1):
        if not isinstance(item, Mapping):
            continue
        score = str(item["score"])
        page = str(item["page"])
        gt_index = int(item["gt_index"])
        target = _box(item.get("gt_box"))
        if target is None:
            raise ValueError(f"Missing target GT box: {score}/{page} gt={gt_index}")

        image_path = args.image_root / score / f"{page}.png"
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(image_path)

        accepted = item.get("accepted_assignment")
        current = item.get("current_assignment")
        if not isinstance(accepted, Mapping) or not isinstance(current, Mapping):
            raise ValueError(f"Missing assignment evidence: {score}/{page} gt={gt_index}")

        accepted_preds, accepted_gts, accepted_records = _assignment_boxes(accepted)
        current_preds, current_gts, current_records = _assignment_boxes(current)

        all_boxes = [target, *accepted_preds, *current_preds]
        all_boxes.extend(box for _idx, box in accepted_gts)
        all_boxes.extend(box for _idx, box in current_gts)
        crop = _union_crop(
            all_boxes,
            image.shape[1],
            image.shape[0],
            pad_x=args.pad_x,
            pad_y=args.pad_y,
        )

        canvas = image.copy()
        competitor_gts: dict[tuple[int, Box], None] = {}
        for idx, box in [*accepted_gts, *current_gts]:
            if idx != gt_index or box != target:
                competitor_gts[(idx, box)] = None

        for idx, box in competitor_gts:
            _draw_box(canvas, box, COLORS["competing_gt"], f"GT {idx}", thickness=3)
        _draw_box(canvas, target, COLORS["target_gt"], f"TARGET GT {gt_index}", thickness=4)

        for record in accepted_records:
            pred = _box(record.get("prediction"))
            if pred is not None:
                label = f"A pred {record.get('pred_index')}"
                _draw_box(canvas, pred, COLORS["accepted_pred"], label, thickness=2)

        for record in current_records:
            pred = _box(record.get("prediction"))
            if pred is not None:
                assigned = record.get("assigned_gt_index")
                label = f"C pred {record.get('pred_index')} -> GT {assigned}"
                _draw_box(canvas, pred, COLORS["current_pred"], label, thickness=2)

        x1, y1, x2, y2 = crop
        crop_image = canvas[y1:y2, x1:x2].copy()
        classification = str(item.get("classification"))
        first_div = item.get("first_target_match_set_divergence")
        divergence = (
            str(first_div.get("stage"))
            if isinstance(first_div, Mapping) and first_div.get("stage")
            else "none"
        )
        annotated = _header(
            crop_image,
            title=(
                f"Issue #284 raw-slot match review | {score}/{page} | "
                f"GT {gt_index} | {classification}"
            ),
            lines=[
                f"current reason: {current.get('reason')}",
                f"accepted FN={accepted.get('is_false_negative')} | "
                f"current FN={current.get('is_false_negative')} | first match-set divergence={divergence}",
                f"crop={crop}",
            ],
        )

        filename = (
            f"{ordinal:02d}_{score}_{page}_gt{gt_index}_{classification}.png"
            .replace("/", "_")
            .replace(" ", "_")
        )
        output_path = args.output_dir / filename
        if not cv2.imwrite(str(output_path), annotated):
            raise OSError(output_path)

        sheet_tiles.append(_letterbox(annotated))
        rendered.append(
            {
                "classification": classification,
                "score": score,
                "page": page,
                "gt_index": gt_index,
                "gt_box": list(target),
                "image": str(image_path.resolve()),
                "crop": list(crop),
                "accepted": accepted_records,
                "current": current_records,
                "output": str(output_path.resolve()),
            }
        )

    if not sheet_tiles:
        raise RuntimeError("Report did not contain any false-negative records")

    columns = 2
    rows = (len(sheet_tiles) + columns - 1) // columns
    blank = np.full_like(sheet_tiles[0], 255)
    while len(sheet_tiles) < rows * columns:
        sheet_tiles.append(blank.copy())
    row_images = [
        np.hstack(sheet_tiles[index : index + columns])
        for index in range(0, len(sheet_tiles), columns)
    ]
    sheet = np.vstack(row_images)
    sheet_path = args.output_dir / "issue284_fn_match_competition_contact_sheet.png"
    if not cv2.imwrite(str(sheet_path), sheet):
        raise OSError(sheet_path)

    manifest = {
        "schema_version": "issue284.fn_match_competition_overlay.v1",
        "report": str(args.report.resolve()),
        "image_root": str(args.image_root.resolve()),
        "case_count": len(rendered),
        "contact_sheet": str(sheet_path.resolve()),
        "cases": rendered,
    }
    manifest_path = args.output_dir / "issue284_fn_match_competition_overlay.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
