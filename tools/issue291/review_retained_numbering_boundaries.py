#!/usr/bin/env python3
"""Review Issue #291 GT-debt cases against retained final numbering artifacts.

This is a temporary, read-only investigation helper.  It does not run detector,
SR, HOMR, MMR, or numbering and does not modify canonical GT.  It searches a
local retained-artifact tree for ``numbering_final.json`` files and overlays
final measure geometry on the original score image for two contract cases:

* P1 #12 (Va__Prokofiev_Symphony5/page_007), where visual review found that
  both suspicious GT boxes are not barlines;
* a genuine semantic double-bar control on
  Sibelius-Violin_Concerto-Viola/page_004 around x~=2717/2726.

The purpose is to distinguish detector-vs-GT scoring from downstream logical
measure boundaries before changing canonical GT.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class ReviewCase:
    case_id: str
    score: str
    page: str
    mode: str
    target_x: float
    x_tolerance: float
    gt_indices: tuple[int, ...] = ()
    semantic_type: str | None = None


CASES = (
    ReviewCase(
        case_id="p1_12_false_gt",
        score="Va__Prokofiev_Symphony5",
        page="page_007",
        mode="indices",
        target_x=668.5,
        x_tolerance=24.0,
        gt_indices=(0, 1),
    ),
    ReviewCase(
        case_id="p3_double_control",
        score="Sibelius-Violin_Concerto-Viola",
        page="page_004",
        mode="semantic_pair",
        target_x=2721.5,
        x_tolerance=36.0,
        semantic_type="double_barline",
    ),
)

COLORS = {
    "gt_a": (0, 0, 255),
    "gt_b": (255, 0, 0),
    "measure": (0, 150, 0),
    "boundary": (180, 80, 0),
    "text": (20, 20, 20),
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def box(value: Any) -> Box | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) < 4:
        return None
    return tuple(int(round(float(item))) for item in value[:4])  # type: ignore[return-value]


def gt_box(item: Any) -> Box | None:
    if isinstance(item, Mapping):
        for key in ("barline_location", "bbox", "box"):
            result = box(item.get(key))
            if result is not None:
                return result
    return box(item)


def gt_type(item: Any) -> str:
    if not isinstance(item, Mapping):
        return "barline"
    return str(item.get("barline_type") or item.get("type") or "barline")


def center_x(item: Box) -> float:
    return (item[0] + item[2]) / 2.0


def y_overlap_over_min(a: Box, b: Box) -> float:
    overlap = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    min_h = max(1, min(a[3] - a[1], b[3] - b[1]))
    return overlap / min_h


def select_gt(case: ReviewCase, payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError(f"GT must be a list for {case.case_id}")

    if case.mode == "indices":
        selected: list[dict[str, Any]] = []
        for index in case.gt_indices:
            if index >= len(payload):
                raise IndexError(f"GT index {index} missing for {case.case_id}")
            bbox = gt_box(payload[index])
            if bbox is None:
                raise ValueError(f"GT index {index} has no bbox for {case.case_id}")
            selected.append({"index": index, "type": gt_type(payload[index]), "bbox": bbox})
        return selected

    if case.mode != "semantic_pair" or case.semantic_type is None:
        raise ValueError(f"Unsupported review mode: {case.mode}")

    candidates: list[dict[str, Any]] = []
    for index, item in enumerate(payload):
        if gt_type(item) != case.semantic_type:
            continue
        bbox = gt_box(item)
        if bbox is None or abs(center_x(bbox) - case.target_x) > case.x_tolerance:
            continue
        candidates.append({"index": index, "type": gt_type(item), "bbox": bbox})

    best: tuple[float, dict[str, Any], dict[str, Any]] | None = None
    for i, first in enumerate(candidates):
        for second in candidates[i + 1 :]:
            a = first["bbox"]
            b = second["bbox"]
            dx = abs(center_x(a) - center_x(b))
            if not 2.0 <= dx <= 20.0:
                continue
            yov = y_overlap_over_min(a, b)
            if yov < 0.7:
                continue
            score = abs(((center_x(a) + center_x(b)) / 2.0) - case.target_x) + abs(dx - 9.0)
            if best is None or score < best[0]:
                best = (score, first, second)
    if best is None:
        raise RuntimeError(
            f"Could not locate {case.semantic_type} pair near x={case.target_x} for {case.case_id}"
        )
    return [best[1], best[2]]


def one_page_numbering(path: Path) -> Mapping[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Numbering payload is not an object: {path}")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], Mapping):
        raise ValueError(f"Expected one-page numbering payload: {path}")
    return pages[0]


def measure_rows(page: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    systems = page.get("systems", [])
    if not isinstance(systems, list):
        return rows
    for system_index, system in enumerate(systems):
        if not isinstance(system, Mapping):
            continue
        measures = system.get("measures", [])
        if not isinstance(measures, list):
            continue
        for measure_index, measure in enumerate(measures):
            if not isinstance(measure, Mapping):
                continue
            bbox = box(measure.get("bbox"))
            if bbox is None:
                continue
            rows.append(
                {
                    "system_index": system_index,
                    "measure_index": measure_index,
                    "number": measure.get("number"),
                    "bbox": bbox,
                }
            )
    return rows


def discover_numbering(search_root: Path, case: ReviewCase) -> list[Path]:
    found = []
    for path in search_root.rglob("numbering_final.json"):
        text = path.as_posix()
        if case.score not in text:
            continue
        if f"/{case.page}/numbering_final.json" not in text:
            continue
        found.append(path)
    return sorted(found, key=lambda item: (item.stat().st_mtime_ns, item.as_posix()), reverse=True)


def target_measure_rows(rows: list[dict[str, Any]], gt_rows: list[dict[str, Any]], case: ReviewCase) -> list[dict[str, Any]]:
    if not gt_rows:
        return []
    min_y = min(row["bbox"][1] for row in gt_rows)
    max_y = max(row["bbox"][3] for row in gt_rows)
    selected = []
    for row in rows:
        bbox = row["bbox"]
        y_overlap = max(0, min(bbox[3], max_y) - max(bbox[1], min_y))
        near_x = bbox[0] <= case.target_x + 180 and bbox[2] >= case.target_x - 180
        if y_overlap > 0 and near_x:
            selected.append(row)
    return selected


def render_case(
    *,
    image_path: Path,
    numbering_path: Path,
    gt_rows: list[dict[str, Any]],
    case: ReviewCase,
    output_path: Path,
) -> dict[str, Any]:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)
    page = one_page_numbering(numbering_path)
    rows = measure_rows(page)
    target_rows = target_measure_rows(rows, gt_rows, case)

    canvas = image.copy()
    for row in target_rows:
        x1, y1, x2, y2 = row["bbox"]
        cv2.rectangle(canvas, (x1, y1), (x2, y2), COLORS["measure"], 2)
        cv2.putText(
            canvas,
            f"m{row['number']} s{row['system_index']}",
            (max(0, x1 + 4), max(18, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            COLORS["measure"],
            1,
            cv2.LINE_AA,
        )
        for x in (x1, x2):
            if abs(x - case.target_x) <= case.x_tolerance:
                cv2.line(canvas, (x, y1), (x, y2), COLORS["boundary"], 2)

    for ordinal, row in enumerate(gt_rows):
        x1, y1, x2, y2 = row["bbox"]
        color = COLORS["gt_a"] if ordinal == 0 else COLORS["gt_b"]
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 3)

    x1 = max(0, min(row["bbox"][0] for row in gt_rows) - 260)
    x2 = min(image.shape[1], max(row["bbox"][2] for row in gt_rows) + 420)
    y1 = max(0, min(row["bbox"][1] for row in gt_rows) - 180)
    y2 = min(image.shape[0], max(row["bbox"][3] for row in gt_rows) + 180)
    crop = canvas[y1:y2, x1:x2]

    header = np.full((92, crop.shape[1], 3), 255, dtype=np.uint8)
    cv2.putText(
        header,
        f"Issue #291 | {case.case_id} | {case.score}/{case.page}",
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        COLORS["text"],
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        header,
        "red/blue=canonical GT | green=final measures | brown=final boundary near target x",
        (10, 49),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        COLORS["text"],
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        header,
        f"numbering={numbering_path}",
        (10, 73),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.34,
        COLORS["text"],
        1,
        cv2.LINE_AA,
    )
    rendered = np.vstack([header, crop])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), rendered):
        raise OSError(output_path)

    near_edges = []
    for row in target_rows:
        for side, value in (("left", row["bbox"][0]), ("right", row["bbox"][2])):
            if abs(value - case.target_x) <= case.x_tolerance:
                near_edges.append(
                    {
                        "system_index": row["system_index"],
                        "measure_index": row["measure_index"],
                        "number": row["number"],
                        "side": side,
                        "x": value,
                    }
                )

    return {
        "numbering_final": str(numbering_path.resolve()),
        "overlay": str(output_path.resolve()),
        "target_measure_rows": [
            {**row, "bbox": list(row["bbox"])} for row in target_rows
        ],
        "measure_edges_near_target_x": near_edges,
    }


def letterbox(image: np.ndarray, width: int = 960, height: int = 560) -> np.ndarray:
    scale = min(width / image.shape[1], height / image.shape[0])
    resized = cv2.resize(
        image,
        (max(1, int(round(image.shape[1] * scale))), max(1, int(round(image.shape[0] * scale)))),
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
    )
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    x = (width - resized.shape[1]) // 2
    y = (height - resized.shape[0]) // 2
    canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-root", type=Path, default=Path("logs"))
    parser.add_argument("--gt-root", type=Path, default=Path("data/evaluation2/annotations"))
    parser.add_argument("--image-root", type=Path, default=Path("data/evaluation2/images"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--max-artifacts-per-case",
        type=int,
        default=12,
        help="Render newest matching retained numbering artifacts per case.",
    )
    args = parser.parse_args()

    if args.max_artifacts_per_case < 1:
        raise ValueError("--max-artifacts-per-case must be >= 1")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_cases = []
    sheet_tiles: list[np.ndarray] = []

    for case in CASES:
        gt_path = args.gt_root / case.score / case.page / "boxes_sorted.json"
        image_path = args.image_root / case.score / f"{case.page}.png"
        gt_rows = select_gt(case, load_json(gt_path))
        artifacts = discover_numbering(args.search_root, case)
        rendered = []
        for artifact_index, numbering_path in enumerate(
            artifacts[: args.max_artifacts_per_case], start=1
        ):
            output_path = (
                args.output_dir
                / case.case_id
                / f"{artifact_index:02d}_{numbering_path.parent.parent.parent.name}.png"
            )
            result = render_case(
                image_path=image_path,
                numbering_path=numbering_path,
                gt_rows=gt_rows,
                case=case,
                output_path=output_path,
            )
            rendered.append(result)
            loaded = cv2.imread(str(output_path), cv2.IMREAD_COLOR)
            if loaded is not None:
                sheet_tiles.append(letterbox(loaded))

        report_cases.append(
            {
                "case_id": case.case_id,
                "score": case.score,
                "page": case.page,
                "target_x": case.target_x,
                "x_tolerance": case.x_tolerance,
                "gt_file": str(gt_path.resolve()),
                "gt": [
                    {**row, "bbox": list(row["bbox"])} for row in gt_rows
                ],
                "retained_numbering_candidates_found": len(artifacts),
                "retained_numbering_candidates_rendered": len(rendered),
                "artifacts": rendered,
            }
        )

    contact_sheet = None
    if sheet_tiles:
        columns = 2
        rows = (len(sheet_tiles) + columns - 1) // columns
        blank = np.full_like(sheet_tiles[0], 255)
        while len(sheet_tiles) < rows * columns:
            sheet_tiles.append(blank.copy())
        sheet = np.vstack(
            [
                np.hstack(sheet_tiles[index : index + columns])
                for index in range(0, len(sheet_tiles), columns)
            ]
        )
        sheet_path = args.output_dir / "issue291_retained_numbering_contact_sheet.png"
        if not cv2.imwrite(str(sheet_path), sheet):
            raise OSError(sheet_path)
        contact_sheet = str(sheet_path.resolve())

    report = {
        "schema_version": "issue291.retained_numbering_boundary_review.v1",
        "search_root": str(args.search_root.resolve()),
        "contact_sheet": contact_sheet,
        "cases": report_cases,
    }
    output = args.output_dir / "issue291_retained_numbering_boundary_review.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))

    if any(case["retained_numbering_candidates_found"] == 0 for case in report_cases):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
