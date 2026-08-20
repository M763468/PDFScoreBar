#!/usr/bin/env python3
"""Render retained Stage-E structural residual crops for Issue #274.

The current JSON proves a 2->1 matching-capacity collapse on three pages, but box
coordinates alone do not establish the musical/visual identity class. In
particular, close boxes may represent separate staff/system segments, parallel
barline strokes, or another local structure. This diagnostic renders the original
page image with only the retained local GT/hybrid/raw boxes needed to classify that
structure visually.

No detector stage is rerun.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2

from src.common import Box
from src.common.barline_evaluation import is_barline_match

DEFAULT_INPUT = Path(
    "logs/issue274_homr_unification_analysis/stage_e_multiplicity_provenance_01/"
    "issue274_stage_e_multiplicity_and_mask_provenance.json"
)
DEFAULT_OUTPUT_ROOT = Path(
    "logs/issue274_homr_unification_analysis/stage_e_structural_identity_crops_01"
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def to_workspace(value: str | Path, workspace: Path) -> Path:
    text = str(value)
    if text.startswith("/workspace/"):
        return workspace / text[len("/workspace/") :]
    marker = "/ws_PDFScoreBar/"
    if marker in text:
        return workspace / text.split(marker, 1)[1]
    path = Path(text)
    return path if path.is_absolute() else workspace / path


def norm_box(values: Sequence[Any]) -> Box:
    return tuple(int(round(float(value))) for value in values[:4])  # type: ignore[return-value]


def load_boxes(path: Path) -> list[Box]:
    payload = load_json(path)
    records: Any = payload
    if isinstance(payload, Mapping):
        for key in ("predictions", "boxes", "detections"):
            if isinstance(payload.get(key), list):
                records = payload[key]
                break
    if not isinstance(records, list):
        return []
    result: list[Box] = []
    for item in records:
        if isinstance(item, (list, tuple)) and len(item) >= 4:
            result.append(norm_box(item))
            continue
        if not isinstance(item, Mapping):
            continue
        for key in ("orig_bbox", "bbox", "pred_bbox", "barline_location"):
            value = item.get(key)
            if isinstance(value, (list, tuple)) and len(value) >= 4:
                result.append(norm_box(value))
                break
    return result


def matches_any(box: Box, gt_boxes: list[Box]) -> bool:
    return any(
        is_barline_match(
            box,
            gt,
            rule_name="center_anchor",
            vov_threshold=0.5,
            xdist_threshold=12.0,
        )
        for gt in gt_boxes
    )


def draw_boxes(
    image,
    boxes: list[Box],
    *,
    color: tuple[int, int, int],
    prefix: str,
    origin: tuple[int, int],
    thickness: int = 2,
) -> None:
    ox, oy = origin
    for index, (x1, y1, x2, y2) in enumerate(boxes):
        p1 = (x1 - ox, y1 - oy)
        p2 = (x2 - ox, y2 - oy)
        cv2.rectangle(image, p1, p2, color, thickness)
        cv2.putText(
            image,
            f"{prefix}{index}",
            (p1[0] + 3, max(15, p1[1] - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )


def label_panel(image, text: str) -> None:
    cv2.rectangle(image, (0, 0), (image.shape[1], 26), (255, 255, 255), -1)
    cv2.putText(
        image,
        text,
        (8, 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 0, 0),
        1,
        cv2.LINE_AA,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--pad-x", type=int, default=140)
    parser.add_argument("--pad-y", type=int, default=100)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    input_path = to_workspace(args.input, workspace)
    output_root = to_workspace(args.output_root, workspace)
    output_root.mkdir(parents=True, exist_ok=True)
    audit = load_json(input_path)
    report_pages: list[dict[str, Any]] = []

    for page in audit.get("pages", []):
        targets = [
            target
            for target in page.get("targets", [])
            if target.get("first_candidate_capacity_divergence") == "raw_first_pass"
        ]
        if not targets:
            continue
        score = str(page["score"])
        page_name = str(page["page"])
        control_meta = page["mask_provenance"]["control"]
        candidate_meta = page["mask_provenance"]["candidate"]
        image_path = to_workspace(control_meta["image"], workspace)
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)
        control_hybrid = load_boxes(to_workspace(control_meta["hybrid_predictions"], workspace))
        candidate_hybrid = load_boxes(to_workspace(candidate_meta["hybrid_predictions"], workspace))

        gt_boxes: list[Box] = []
        control_raw: list[Box] = []
        candidate_raw: list[Box] = []
        for target in targets:
            control_component = target["variants"]["control"]["raw_first_pass"]["target_component"]
            candidate_component = target["variants"]["candidate"]["raw_first_pass"][
                "target_component"
            ]
            gt_boxes.extend(norm_box(box) for box in control_component["component_gt_bboxes"])
            control_raw.extend(norm_box(row["bbox"]) for row in control_component["predictions"])
            candidate_raw.extend(
                norm_box(row["bbox"]) for row in candidate_component["predictions"]
            )
        gt_boxes = sorted(set(gt_boxes))
        control_raw = sorted(set(control_raw))
        candidate_raw = sorted(set(candidate_raw))
        control_hybrid_local = sorted(box for box in control_hybrid if matches_any(box, gt_boxes))
        candidate_hybrid_local = sorted(
            box for box in candidate_hybrid if matches_any(box, gt_boxes)
        )

        all_boxes = [*gt_boxes, *control_raw, *candidate_raw]
        if not all_boxes:
            continue
        x1 = max(0, min(box[0] for box in all_boxes) - args.pad_x)
        y1 = max(0, min(box[1] for box in all_boxes) - args.pad_y)
        x2 = min(image.shape[1], max(box[2] for box in all_boxes) + args.pad_x)
        y2 = min(image.shape[0], max(box[3] for box in all_boxes) + args.pad_y)
        base = image[y1:y2, x1:x2].copy()

        original = base.copy()
        label_panel(original, "original crop")

        control = base.copy()
        draw_boxes(control, gt_boxes, color=(0, 160, 0), prefix="G", origin=(x1, y1), thickness=2)
        draw_boxes(
            control,
            control_hybrid_local,
            color=(0, 140, 255),
            prefix="H",
            origin=(x1, y1),
            thickness=2,
        )
        draw_boxes(
            control,
            control_raw,
            color=(255, 80, 0),
            prefix="R",
            origin=(x1, y1),
            thickness=1,
        )
        label_panel(control, "control: GT green / hybrid orange / raw blue")

        candidate = base.copy()
        draw_boxes(candidate, gt_boxes, color=(0, 160, 0), prefix="G", origin=(x1, y1), thickness=2)
        draw_boxes(
            candidate,
            candidate_hybrid_local,
            color=(0, 140, 255),
            prefix="H",
            origin=(x1, y1),
            thickness=2,
        )
        draw_boxes(
            candidate,
            candidate_raw,
            color=(0, 0, 220),
            prefix="R",
            origin=(x1, y1),
            thickness=1,
        )
        label_panel(candidate, "B candidate: GT green / hybrid orange / raw red")

        panel = cv2.hconcat([original, control, candidate])
        out_path = output_root / f"{score}__{page_name}__structural_identity.png"
        cv2.imwrite(str(out_path), panel)
        report_pages.append(
            {
                "score": score,
                "page": page_name,
                "image": str(image_path),
                "crop_bbox": [x1, y1, x2, y2],
                "gt_boxes": [list(box) for box in gt_boxes],
                "control_hybrid_local": [list(box) for box in control_hybrid_local],
                "candidate_hybrid_local": [list(box) for box in candidate_hybrid_local],
                "control_raw_local": [list(box) for box in control_raw],
                "candidate_raw_local": [list(box) for box in candidate_raw],
                "output": str(out_path),
            }
        )

    report = {
        "schema_version": "issue274.stage_e_structural_identity_crops.v1",
        "status": "completed",
        "scope": {
            "page_count": len(report_pages),
            "detector_reexecuted": False,
            "homr_reexecuted": False,
        },
        "legend": {
            "gt": "green",
            "hybrid": "orange",
            "control_raw": "blue",
            "candidate_raw": "red",
        },
        "interpretation_guardrail": (
            "Use the crop to classify the physical/musical multiplicity. Do not infer staff-slot, "
            "system-slot, or double-stroke identity from coordinates alone."
        ),
        "pages": report_pages,
    }
    report_path = output_root / "issue274_stage_e_structural_identity_crops.json"
    write_json(report_path, report)
    print(
        json.dumps({"status": "completed", "report": str(report_path), "pages": len(report_pages)})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
