#!/usr/bin/env python3
"""Visualize Issue #372 late-raw detector residuals from corrected evidence.

Creates:
- one full-page overlay per page containing any hard FN/FP;
- one zoomed crop per residual;
- index.json with provenance and output paths.

Colors (OpenCV BGR):
- FN GT: red
- FN matching candidate: green
- FN matching final: blue
- FP prediction: cyan
- FP nearest GT: orange

This tool is retained-only and runs no detector/CNN/MMR inference.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2

SCHEMAS = {
    "issue372.late_raw_detector_residuals.v2",
    "issue372.late_raw_detector_residuals.v3",
}
FN_COLOR = (0, 0, 255)
CAND_COLOR = (0, 180, 0)
FINAL_COLOR = (255, 0, 0)
FP_COLOR = (255, 255, 0)
NEAR_COLOR = (0, 165, 255)
TEXT_COLOR = (255, 255, 255)
BG_COLOR = (0, 0, 0)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _validate_report(payload: Mapping[str, Any]) -> None:
    schema = payload.get("schema_version")
    if schema not in SCHEMAS:
        raise ValueError(
            f"Unsupported residual schema {schema!r}; expected one of {sorted(SCHEMAS)!r}. "
            "Regenerate the residual report with the current reporter instead "
            "of reusing the pre-fix v1 artifact."
        )
    if not isinstance(payload.get("false_negatives"), list):
        raise ValueError("Residual report lacks false_negatives list")
    if not isinstance(payload.get("false_positives"), list):
        raise ValueError("Residual report lacks false_positives list")
    for row in payload["false_negatives"]:
        if not isinstance(row, Mapping) or not isinstance(row.get("score"), str):
            raise ValueError(f"Invalid v2 FN row: {row!r}")
    for row in payload["false_positives"]:
        if (
            not isinstance(row, Mapping)
            or not isinstance(row.get("score_name"), str)
            or "cnn_score" not in row
        ):
            raise ValueError(f"Invalid v2 FP row: {row!r}")


def _find_image(image_root: Path, score: str, page: str) -> Path:
    score_dir = image_root / score
    if not score_dir.is_dir():
        raise FileNotFoundError(score_dir)
    for stem in (page, f"{page}_original", f"{page}_image"):
        for ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"):
            path = score_dir / f"{stem}{ext}"
            if path.is_file():
                return path
    matches = sorted(score_dir.glob(f"{page}.*"))
    if matches:
        return matches[0]
    raise FileNotFoundError(f"Image not found for {score}/{page} under {score_dir}")


def _draw_box(
    image: Any,
    box: Sequence[Any],
    color: tuple[int, int, int],
    *,
    thickness: int = 2,
    label: str | None = None,
) -> None:
    x1, y1, x2, y2 = (int(round(float(v))) for v in box[:4])
    cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
    if label:
        cv2.putText(
            image,
            label,
            (max(0, x1), max(15, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )


def _add_header(image: Any, lines: Sequence[str]) -> None:
    pad = 6
    line_h = 18
    header_h = pad * 2 + line_h * len(lines)
    overlay = image.copy()
    cv2.rectangle(
        overlay,
        (0, 0),
        (image.shape[1] - 1, header_h),
        BG_COLOR,
        -1,
    )
    image[:] = cv2.addWeighted(overlay, 0.45, image, 0.55, 0)
    for index, line in enumerate(lines):
        cv2.putText(
            image,
            line,
            (8, pad + (index + 1) * line_h - 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            TEXT_COLOR,
            1,
            cv2.LINE_AA,
        )


def _crop(
    image: Any,
    boxes: Sequence[Sequence[Any]],
    *,
    margin: int,
) -> tuple[Any, tuple[int, int, int, int]]:
    if not boxes:
        raise ValueError("crop requires at least one box")
    h, w = image.shape[:2]
    xs: list[int] = []
    ys: list[int] = []
    for box in boxes:
        x1, y1, x2, y2 = (int(round(float(v))) for v in box[:4])
        xs.extend((x1, x2))
        ys.extend((y1, y2))
    x1 = max(0, min(xs) - margin)
    y1 = max(0, min(ys) - margin)
    x2 = min(w, max(xs) + margin)
    y2 = min(h, max(ys) + margin)
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"Invalid crop rectangle {(x1, y1, x2, y2)}")
    return image[y1:y2, x1:x2].copy(), (x1, y1, x2, y2)


def _page_groups(payload: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, list[Mapping[str, Any]]]]:
    pages: dict[tuple[str, str], dict[str, list[Mapping[str, Any]]]] = {}
    for row in payload["false_negatives"]:
        key = (str(row["score"]), str(row["page"]))
        pages.setdefault(key, {"fn": [], "fp": []})["fn"].append(row)
    for row in payload["false_positives"]:
        key = (str(row["score_name"]), str(row["page"]))
        pages.setdefault(key, {"fn": [], "fp": []})["fp"].append(row)
    return pages


def run(args: argparse.Namespace) -> dict[str, Any]:
    report_path = args.residual_report.resolve()
    image_root = args.image_root.resolve()
    output_root = args.output_root.resolve()
    if not report_path.is_file():
        raise FileNotFoundError(report_path)
    if not image_root.is_dir():
        raise FileNotFoundError(image_root)
    if output_root.exists():
        raise FileExistsError(f"Output root must not already exist: {output_root}")

    payload = _load(report_path)
    if not isinstance(payload, Mapping):
        raise ValueError("Residual report must be a JSON object")
    _validate_report(payload)
    pages = _page_groups(payload)

    output_root.mkdir(parents=True)
    index: dict[str, Any] = {
        "schema_version": "issue372.late_raw_detector_residual_visualization.v1",
        "source_report": str(report_path),
        "source_schema": payload["schema_version"],
        "summary": payload.get("summary"),
        "pages": [],
    }

    for (score, page), rows in sorted(pages.items()):
        image_path = _find_image(image_root, score, page)
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"OpenCV failed to read {image_path}")

        page_root = output_root / score / page
        page_root.mkdir(parents=True)
        full = image.copy()

        for idx, row in enumerate(rows["fn"], 1):
            _draw_box(full, row["gt_bbox"], FN_COLOR, label=f"FN{idx}:GT")
            for cand_idx, box in enumerate(row.get("matching_candidates", []), 1):
                _draw_box(
                    full,
                    box,
                    CAND_COLOR,
                    thickness=1,
                    label=f"FN{idx}:C{cand_idx}",
                )
            for final_idx, detail in enumerate(row.get("matching_finals", []), 1):
                if isinstance(detail, Mapping) and detail.get("bbox"):
                    _draw_box(
                        full,
                        detail["bbox"],
                        FINAL_COLOR,
                        label=f"FN{idx}:F{final_idx}",
                    )

        for idx, row in enumerate(rows["fp"], 1):
            _draw_box(full, row["pred_bbox"], FP_COLOR, label=f"FP{idx}")
            nearest = row.get("nearest_gt")
            if isinstance(nearest, Mapping) and nearest.get("bbox"):
                _draw_box(
                    full,
                    nearest["bbox"],
                    NEAR_COLOR,
                    thickness=1,
                    label=f"FP{idx}:GT*",
                )

        _add_header(
            full,
            [
                f"{score}/{page}",
                f"FN={len(rows['fn'])} FP={len(rows['fp'])}",
                "red=FN GT green=candidate blue=final cyan=FP orange=nearest GT",
            ],
        )
        full_path = page_root / "full_page_overlay.png"
        if not cv2.imwrite(str(full_path), full):
            raise RuntimeError(f"Failed to write {full_path}")

        page_index: dict[str, Any] = {
            "score": score,
            "page": page,
            "image": str(image_path),
            "full_page_overlay": str(full_path.relative_to(output_root)),
            "residuals": [],
        }

        for idx, row in enumerate(rows["fn"], 1):
            work = image.copy()
            boxes: list[Sequence[Any]] = [row["gt_bbox"]]
            _draw_box(work, row["gt_bbox"], FN_COLOR, label="GT")
            for cand_idx, box in enumerate(row.get("matching_candidates", []), 1):
                boxes.append(box)
                _draw_box(work, box, CAND_COLOR, thickness=1, label=f"C{cand_idx}")
            for final_idx, detail in enumerate(row.get("matching_finals", []), 1):
                if isinstance(detail, Mapping) and detail.get("bbox"):
                    boxes.append(detail["bbox"])
                    _draw_box(work, detail["bbox"], FINAL_COLOR, label=f"F{final_idx}")
            crop, rect = _crop(work, boxes, margin=args.margin)
            _add_header(
                crop,
                [
                    f"FN{idx} {row['classification']}",
                    f"number_changed={row['page_number_values_changed_vs_current']}",
                ],
            )
            path = page_root / f"FN_{idx:02d}.png"
            if not cv2.imwrite(str(path), crop):
                raise RuntimeError(f"Failed to write {path}")
            page_index["residuals"].append(
                {
                    "kind": "FN",
                    "index": idx,
                    "bbox": row["gt_bbox"],
                    "classification": row["classification"],
                    "crop_rect": list(rect),
                    "path": str(path.relative_to(output_root)),
                }
            )

        for idx, row in enumerate(rows["fp"], 1):
            work = image.copy()
            boxes = [row["pred_bbox"]]
            _draw_box(work, row["pred_bbox"], FP_COLOR, label="PRED")
            nearest = row.get("nearest_gt")
            geometry = "no_gt"
            if isinstance(nearest, Mapping):
                geometry = str(nearest.get("geometry_class", "unknown"))
                if nearest.get("bbox"):
                    boxes.append(nearest["bbox"])
                    _draw_box(
                        work,
                        nearest["bbox"],
                        NEAR_COLOR,
                        thickness=1,
                        label="GT*",
                    )
            crop, rect = _crop(work, boxes, margin=args.margin)
            _add_header(
                crop,
                [
                    f"FP{idx} cnn={row['cnn_score']}",
                    f"geometry={geometry}",
                    f"number_changed={row['page_number_values_changed_vs_current']}",
                ],
            )
            path = page_root / f"FP_{idx:02d}.png"
            if not cv2.imwrite(str(path), crop):
                raise RuntimeError(f"Failed to write {path}")
            page_index["residuals"].append(
                {
                    "kind": "FP",
                    "index": idx,
                    "bbox": row["pred_bbox"],
                    "cnn_score": row["cnn_score"],
                    "geometry_class": geometry,
                    "crop_rect": list(rect),
                    "path": str(path.relative_to(output_root)),
                }
            )

        index["pages"].append(page_index)

    _write(output_root / "index.json", index)
    print(
        f"visualized_pages={len(index['pages'])} "
        f"fn={payload['summary']['fn_count']} "
        f"fp={payload['summary']['fp_count']}"
    )
    print(f"OUTPUT={output_root}")
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--residual-report", type=Path, required=True)
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--margin", type=int, default=140)
    args = parser.parse_args()
    if args.margin < 0:
        raise ValueError("--margin must be >= 0")
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())