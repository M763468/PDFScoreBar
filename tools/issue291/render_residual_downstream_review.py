#!/usr/bin/env python3
"""Render Issue #291 residual FP/FN cases with final numbering context.

This read-only review helper combines four evidence layers on the original
evaluation2 score image:

1. corrected canonical GT,
2. retained final Stage-E predictions,
3. the known corrected-GT FP/FN residuals, and
4. retained ``numbering_final.json`` measure geometry and serialized numbers.

The tool does not rerun detector, grouping, MMR, or numbering inference and does
not modify canonical data. It is intended for local merge review of Issue #291.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

from src.common.barline_evaluation import greedy_barline_match

PROJECT_ROOT = Path(__file__).resolve().parents[2]
Box = tuple[int, int, int, int]

COLORS = {
    "gt": (180, 0, 180),
    "pred": (0, 150, 0),
    "fp": (0, 0, 255),
    "fn": (255, 90, 0),
    "measure": (0, 170, 220),
    "text": (20, 20, 20),
}


@dataclass(frozen=True)
class ResidualCase:
    case_id: str
    kind: str
    score: str
    page: str
    boxes: tuple[Box, ...]
    note: str


CASES: tuple[ResidualCase, ...] = (
    ResidualCase(
        case_id="fp_prokofiev5_p007",
        kind="fp",
        score="Va__Prokofiev_Symphony5",
        page="page_007",
        boxes=((665, 908, 669, 1018), (668, 908, 672, 1018)),
        note="time-signature-stroke predictions; inspect whether numbering creates a pre-measure",
    ),
    ResidualCase(
        case_id="fp_prokofiev5_p015",
        kind="fp",
        score="Va__Prokofiev_Symphony5",
        page="page_015",
        boxes=((580, 4005, 584, 4115),),
        note="known extra barline candidate; inspect the resulting measure split",
    ),
    ResidualCase(
        case_id="fn_sibelius_p004",
        kind="fn",
        score="Sibelius-Violin_Concerto-Viola",
        page="page_004",
        boxes=((2713, 3166, 2720, 3274),),
        note="double-barline-region FN; inspect the retained logical boundary and numbering",
    ),
    ResidualCase(
        case_id="fn_prokofiev1_p004",
        kind="fn",
        score="Va_Prokofiev_Symphony1",
        page="page_004",
        boxes=((2715, 2481, 2720, 2582),),
        note="greedy-assignment residual; inspect the retained measure topology",
    ),
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_box(value: Any) -> Box | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) < 4:
        return None
    return tuple(int(round(float(item))) for item in value[:4])  # type: ignore[return-value]


def boxes_from_gt(payload: Any) -> list[Box]:
    if not isinstance(payload, list):
        raise ValueError("GT payload must be a list")
    boxes: list[Box] = []
    for item in payload:
        if isinstance(item, list):
            parsed = normalize_box(item)
        elif isinstance(item, Mapping):
            parsed = None
            for key in ("barline_location", "box", "bbox"):
                if key in item:
                    parsed = normalize_box(item[key])
                    break
        else:
            parsed = None
        if parsed is not None:
            boxes.append(parsed)
    return boxes


def boxes_from_predictions(payload: Any) -> list[Box]:
    if not isinstance(payload, list):
        raise ValueError("Prediction payload must be a list")
    boxes: list[Box] = []
    for item in payload:
        if isinstance(item, list):
            parsed = normalize_box(item)
        elif isinstance(item, Mapping):
            parsed = normalize_box(item.get("bbox"))
        else:
            parsed = None
        if parsed is not None:
            boxes.append(parsed)
    return boxes


def one_page_numbering(payload: Any, path: Path) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"Numbering payload is not an object: {path}")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], Mapping):
        raise ValueError(f"Expected one-page numbering payload: {path}")
    return pages[0]


def resolve_recorded_path(
    raw: object,
    *,
    roots: Sequence[Path],
    project_root: Path = PROJECT_ROOT,
) -> Path:
    recorded = Path(str(raw))
    candidates: list[Path] = [recorded]

    if recorded.is_absolute():
        try:
            candidates.append(project_root / recorded.relative_to(Path("/workspace")))
        except ValueError:
            pass

    for root in roots:
        root = root.resolve(strict=False)
        for index, part in enumerate(recorded.parts):
            if part == root.name:
                candidates.append(root.joinpath(*recorded.parts[index + 1 :]))

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            return resolved

    attempted = ", ".join(str(item) for item in seen)
    raise FileNotFoundError(f"Recorded artifact not found; recorded={recorded}; tried={attempted}")


def prediction_map_from_manifest(manifest_path: Path) -> dict[tuple[str, str], Path]:
    manifest = load_json(manifest_path)
    if not isinstance(manifest, Mapping):
        raise ValueError(f"Manifest is not an object: {manifest_path}")

    page_map: dict[tuple[str, str], Path] = {}
    for raw_page in manifest.get("pages", []):
        if not isinstance(raw_page, Mapping):
            continue
        stem = Path(str(raw_page.get("image_path", ""))).stem
        split_at = stem.rfind("_page_")
        if split_at < 0:
            continue
        score = stem[:split_at]
        page = f"page_{stem[split_at + 6 :]}"
        barlines_json = raw_page.get("barlines_json")
        if not barlines_json:
            continue
        page_map[(score, page)] = resolve_recorded_path(
            barlines_json,
            roots=(manifest_path.parent,),
        )
    return page_map


def case_artifact_map_from_root(
    root: Path,
    *,
    filename: str,
    artifact_name: str,
) -> dict[tuple[str, str], Path]:
    root = root.resolve()
    candidates = sorted(root.rglob(filename))
    page_map: dict[tuple[str, str], Path] = {}
    for case in CASES:
        matched = [
            path
            for path in candidates
            if case.score in path.as_posix() and case.page in path.as_posix()
        ]
        if len(matched) == 1:
            page_map[(case.score, case.page)] = matched[0]
        elif not matched:
            raise FileNotFoundError(
                f"No {artifact_name} for {case.score}/{case.page} under {root}"
            )
        else:
            options = "\n".join(str(path) for path in matched)
            raise RuntimeError(
                f"Ambiguous {artifact_name} files for {case.score}/{case.page}:\n{options}"
            )
    return page_map


def prediction_map_from_root(root: Path) -> dict[tuple[str, str], Path]:
    return case_artifact_map_from_root(
        root,
        filename="pipeline2_no_peak_filtered_cnn.json",
        artifact_name="filtered-CNN artifact",
    )


def numbering_map_from_root(root: Path) -> dict[tuple[str, str], Path]:
    return case_artifact_map_from_root(
        root,
        filename="numbering_final.json",
        artifact_name="numbering_final artifact",
    )


def numbering_map_from_variant(variant_root: Path) -> dict[tuple[str, str], Path]:
    variant_root = variant_root.resolve()
    summary_path = variant_root / "variant_summary.json"
    summary = load_json(summary_path)
    if not isinstance(summary, Mapping) or summary.get("status") != "completed":
        raise RuntimeError(f"Variant is not completed: {summary_path}")

    page_map: dict[tuple[str, str], Path] = {}
    for score_entry in summary.get("scores", []):
        if not isinstance(score_entry, Mapping):
            continue
        score = str(score_entry.get("score"))
        artifacts = score_entry.get("page_artifacts")
        if not isinstance(artifacts, Mapping):
            continue
        for page, raw in artifacts.items():
            if not isinstance(raw, Mapping) or not raw.get("numbering_final"):
                continue
            page_map[(score, str(page))] = resolve_recorded_path(
                raw["numbering_final"],
                roots=(variant_root,),
            )
    return page_map


def system_measure_records(numbering_page: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    systems = numbering_page.get("systems", [])
    if not isinstance(systems, list):
        return records
    for system_index, system in enumerate(systems):
        if not isinstance(system, Mapping):
            continue
        measures = system.get("measures", [])
        if not isinstance(measures, list):
            continue
        for measure_index, measure in enumerate(measures):
            if not isinstance(measure, Mapping):
                continue
            bbox = normalize_box(measure.get("bbox"))
            if bbox is None:
                continue
            records.append(
                {
                    "system_index": system_index,
                    "measure_index": measure_index,
                    "number": measure.get("number", measure.get("measure_number")),
                    "bbox": bbox,
                }
            )
    return records


def relevant_system_indices(
    records: Sequence[Mapping[str, Any]], targets: Sequence[Box]
) -> set[int]:
    target_centers_y = [(box[1] + box[3]) / 2.0 for box in targets]
    system_ranges: dict[int, tuple[int, int]] = {}
    for record in records:
        bbox = normalize_box(record.get("bbox"))
        if bbox is None:
            continue
        system_index = int(record["system_index"])
        if system_index not in system_ranges:
            system_ranges[system_index] = (bbox[1], bbox[3])
        else:
            lo, hi = system_ranges[system_index]
            system_ranges[system_index] = (min(lo, bbox[1]), max(hi, bbox[3]))

    selected = {
        system_index
        for system_index, (lo, hi) in system_ranges.items()
        if any(lo <= center_y <= hi for center_y in target_centers_y)
    }
    if selected or not system_ranges:
        return selected

    target_y = sum(target_centers_y) / len(target_centers_y)
    nearest = min(
        system_ranges,
        key=lambda index: min(
            abs(target_y - system_ranges[index][0]),
            abs(target_y - system_ranges[index][1]),
        ),
    )
    return {nearest}


def union_crop(
    boxes: Sequence[Box],
    *,
    image_width: int,
    image_height: int,
    pad_x: int,
    pad_y: int,
) -> Box:
    if not boxes:
        raise ValueError("At least one box is required for a crop")
    x1 = max(0, min(box[0] for box in boxes) - pad_x)
    y1 = max(0, min(box[1] for box in boxes) - pad_y)
    x2 = min(image_width, max(box[2] for box in boxes) + pad_x)
    y2 = min(image_height, max(box[3] for box in boxes) + pad_y)
    return x1, y1, x2, y2


def intersects(a: Box, b: Box) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def draw_box(
    canvas: np.ndarray,
    bbox: Box,
    color: tuple[int, int, int],
    label: str | None = None,
    *,
    thickness: int = 2,
) -> None:
    x1, y1, x2, y2 = bbox
    cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness)
    if label:
        cv2.putText(
            canvas,
            label,
            (x1 + 4, max(18, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            color,
            max(1, thickness - 1),
            cv2.LINE_AA,
        )


def render_case(
    *,
    case: ResidualCase,
    image_path: Path,
    gt_path: Path,
    prediction_path: Path,
    numbering_path: Path,
    output_path: Path,
    pad_x: int,
    pad_y: int,
) -> dict[str, Any]:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)

    gts = boxes_from_gt(load_json(gt_path))
    preds = boxes_from_predictions(load_json(prediction_path))
    match = greedy_barline_match(
        preds,
        gts,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )
    actual_fp = [preds[index] for index in match.false_positive_indices]
    actual_fn = [gts[index] for index in match.false_negative_indices]

    expected_actual = actual_fp if case.kind == "fp" else actual_fn
    missing_expected = [bbox for bbox in case.boxes if bbox not in expected_actual]
    if missing_expected:
        raise RuntimeError(
            f"{case.case_id}: expected {case.kind.upper()} residual(s) not reproduced: "
            f"{missing_expected}; actual={expected_actual}"
        )

    numbering_page = one_page_numbering(load_json(numbering_path), numbering_path)
    measures = system_measure_records(numbering_page)
    selected_systems = relevant_system_indices(measures, case.boxes)
    selected_measures = [
        record for record in measures if int(record["system_index"]) in selected_systems
    ]

    crop_boxes: list[Box] = [*case.boxes]
    for record in selected_measures:
        bbox = normalize_box(record["bbox"])
        if bbox is not None:
            crop_boxes.append(bbox)
    crop = union_crop(
        crop_boxes,
        image_width=image.shape[1],
        image_height=image.shape[0],
        pad_x=pad_x,
        pad_y=pad_y,
    )

    canvas = image.copy()

    for record in selected_measures:
        bbox = normalize_box(record["bbox"])
        if bbox is None:
            continue
        draw_box(
            canvas,
            bbox,
            COLORS["measure"],
            f"M{record['number']}",
            thickness=2,
        )

    for bbox in gts:
        if intersects(bbox, crop):
            draw_box(canvas, bbox, COLORS["gt"], thickness=1)

    for bbox in preds:
        if intersects(bbox, crop):
            draw_box(canvas, bbox, COLORS["pred"], thickness=1)

    residual_color = COLORS[case.kind]
    for ordinal, bbox in enumerate(case.boxes, start=1):
        draw_box(
            canvas,
            bbox,
            residual_color,
            f"{case.kind.upper()} {ordinal}",
            thickness=4,
        )

    x1, y1, x2, y2 = crop
    cropped = canvas[y1:y2, x1:x2].copy()
    header_height = 112
    output = np.full(
        (cropped.shape[0] + header_height, cropped.shape[1], 3),
        255,
        dtype=np.uint8,
    )
    output[header_height:] = cropped

    lines = [
        f"Issue #291 residual review | {case.case_id}",
        f"{case.score}/{case.page} | page FP={len(actual_fp)} FN={len(actual_fn)} "
        f"| selected systems={sorted(selected_systems)}",
        case.note,
        "legend: GT=magenta pred=green residual=red(FP)/blue(FN) final measures=yellow",
    ]
    y = 24
    for index, line in enumerate(lines):
        cv2.putText(
            output,
            line,
            (12, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55 if index == 0 else 0.44,
            COLORS["text"],
            1,
            cv2.LINE_AA,
        )
        y += 26

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), output):
        raise OSError(output_path)

    return {
        "case_id": case.case_id,
        "kind": case.kind,
        "score": case.score,
        "page": case.page,
        "expected_residual_boxes": [list(box) for box in case.boxes],
        "actual_fp_boxes": [list(box) for box in actual_fp],
        "actual_fn_boxes": [list(box) for box in actual_fn],
        "image": str(image_path.resolve()),
        "gt": str(gt_path.resolve()),
        "predictions": str(prediction_path.resolve()),
        "numbering_final": str(numbering_path.resolve()),
        "crop": list(crop),
        "selected_system_indices": sorted(selected_systems),
        "selected_measures": [
            {
                **{key: value for key, value in record.items() if key != "bbox"},
                "bbox": list(record["bbox"]),
            }
            for record in selected_measures
        ],
        "output": str(output_path.resolve()),
    }


def letterbox(image: np.ndarray, width: int = 1200, height: int = 650) -> np.ndarray:
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
    prediction_group = parser.add_mutually_exclusive_group(required=True)
    prediction_group.add_argument(
        "--prediction-manifest",
        type=Path,
        help="Pipeline manifest whose barlines_json points to final filtered-CNN artifacts",
    )
    prediction_group.add_argument(
        "--prediction-root",
        type=Path,
        help="One retained Stage-E run root containing pipeline2_no_peak_filtered_cnn.json",
    )
    numbering_group = parser.add_mutually_exclusive_group(required=True)
    numbering_group.add_argument(
        "--variant",
        type=Path,
        help="Completed retained full68 variant root containing variant_summary.json",
    )
    numbering_group.add_argument(
        "--numbering-root",
        type=Path,
        help="One retained full68 output root containing numbering_final.json files",
    )
    parser.add_argument(
        "--image-root",
        type=Path,
        default=Path("data/evaluation2/images"),
    )
    parser.add_argument(
        "--gt-root",
        type=Path,
        default=Path("data/evaluation2/annotations"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("logs/issue291/residual_downstream_review"),
    )
    parser.add_argument("--pad-x", type=int, default=80)
    parser.add_argument("--pad-y", type=int, default=70)
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Optional case id to render; repeat as needed. Default renders all four page cases.",
    )
    args = parser.parse_args()

    if args.prediction_manifest:
        prediction_map = prediction_map_from_manifest(args.prediction_manifest.resolve())
        prediction_source = str(args.prediction_manifest.resolve())
    else:
        prediction_map = prediction_map_from_root(args.prediction_root.resolve())
        prediction_source = str(args.prediction_root.resolve())

    if args.variant:
        numbering_map = numbering_map_from_variant(args.variant)
        numbering_source = str(args.variant.resolve())
    else:
        numbering_map = numbering_map_from_root(args.numbering_root.resolve())
        numbering_source = str(args.numbering_root.resolve())

    requested = set(args.case)
    known_ids = {case.case_id for case in CASES}
    unknown = requested - known_ids
    if unknown:
        raise ValueError("Unknown case id(s): " + ", ".join(sorted(unknown)))

    selected_cases = [case for case in CASES if not requested or case.case_id in requested]
    rendered: list[dict[str, Any]] = []
    tiles: list[np.ndarray] = []

    for ordinal, case in enumerate(selected_cases, start=1):
        key = (case.score, case.page)
        if key not in prediction_map:
            raise KeyError(f"Missing prediction artifact for {case.score}/{case.page}")
        if key not in numbering_map:
            raise KeyError(f"Missing numbering_final artifact for {case.score}/{case.page}")

        image_path = args.image_root / case.score / f"{case.page}.png"
        gt_path = args.gt_root / case.score / case.page / "boxes_sorted.json"
        output_path = args.output_dir / f"{ordinal:02d}_{case.case_id}.png"
        record = render_case(
            case=case,
            image_path=image_path,
            gt_path=gt_path,
            prediction_path=prediction_map[key],
            numbering_path=numbering_map[key],
            output_path=output_path,
            pad_x=args.pad_x,
            pad_y=args.pad_y,
        )
        rendered.append(record)
        image = cv2.imread(str(output_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(output_path)
        tiles.append(letterbox(image))

    if not tiles:
        raise RuntimeError("No residual cases rendered")

    columns = 2
    rows = (len(tiles) + columns - 1) // columns
    blank = np.full_like(tiles[0], 255)
    while len(tiles) < rows * columns:
        tiles.append(blank.copy())
    sheet_rows = [
        np.hstack(tiles[index : index + columns]) for index in range(0, len(tiles), columns)
    ]
    sheet = np.vstack(sheet_rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sheet_path = args.output_dir / "issue291_residual_downstream_contact_sheet.png"
    if not cv2.imwrite(str(sheet_path), sheet):
        raise OSError(sheet_path)

    payload = {
        "schema_version": "issue291.residual_downstream_review.v1",
        "prediction_source": prediction_source,
        "numbering_source": numbering_source,
        "image_root": str(args.image_root.resolve()),
        "gt_root": str(args.gt_root.resolve()),
        "case_count": len(rendered),
        "residual_box_count": sum(len(case.boxes) for case in selected_cases),
        "contact_sheet": str(sheet_path.resolve()),
        "cases": rendered,
    }
    manifest_path = args.output_dir / "issue291_residual_downstream_review.json"
    manifest_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
