#!/usr/bin/env python3
"""Unified retained-artifact semantic + visual audit for Issue #372.

No detector/HOMR/SR/OMR/MMR/numbering inference is executed.

The audit compares the corrected current-control replay with the completed fresh
production full68 run across all 68 canonical pages, then automatically renders
only pages that have a *local* difference (detector boxes, topology, MMR
semantics, or within-page numbering progression). Pure continuation propagation
is classified separately and is not treated as an independent root page.

Each rendered page is a side-by-side image:
  LEFT  = corrected current control
  RIGHT = fresh production

Overlays include detector-only differences, final measure boxes/numbers, and
MMR skip annotations.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.issue372.run_fresh_downstream_semantic_replay import (
    _extract_boxes,
    _find_page_file,
)
from experiments.issue372.run_retained_x4_gap_counterfactual import _host_path
from tools.issue120 import eval_full68_from_intermediates as full68_eval

Box = tuple[int, int, int, int]


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _production_index(
    report: Mapping[str, Any],
    *,
    issue372_root: Path,
) -> tuple[
    dict[tuple[str, str], Mapping[str, Any]],
    dict[str, Path],
]:
    rows: dict[tuple[str, str], Mapping[str, Any]] = {}
    pipeline_runs: dict[str, Path] = {}
    for score_summary in report["score_summaries"]:
        score = str(score_summary["score"])
        pipeline_runs[score] = _host_path(
            str(score_summary["pipeline_run"]),
            issue372_root,
        )
        for page, row in score_summary["page_results"].items():
            rows[(score, str(page))] = row
    if len(rows) != 68:
        raise RuntimeError(f"Expected 68 production pages, got {len(rows)}")
    return rows, pipeline_runs


def _numbering_systems(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], Mapping):
        raise ValueError("Expected one-page numbering payload")
    result = []
    for system in pages[0].get("systems", []):
        if not isinstance(system, Mapping):
            continue
        measures = [m for m in system.get("measures", []) if isinstance(m, Mapping)]
        result.append(
            {
                "measure_count": len(measures),
                "numbers": [
                    m.get("number", m.get("measure_number"))
                    for m in measures
                ],
                "bboxes": [
                    [int(round(float(v))) for v in m["bbox"][:4]]
                    for m in measures
                    if isinstance(m.get("bbox"), list) and len(m["bbox"]) >= 4
                ],
            }
        )
    return result


def _counts(payload: Mapping[str, Any]) -> list[int]:
    return [int(system["measure_count"]) for system in _numbering_systems(payload)]


def _numbers(payload: Mapping[str, Any]) -> list[list[Any]]:
    return [list(system["numbers"]) for system in _numbering_systems(payload)]


def _flatten_numbers(payload: Mapping[str, Any]) -> list[int]:
    result = []
    for row in _numbers(payload):
        for value in row:
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            result.append(value)
    return result


def _normalized_number_progression(payload: Mapping[str, Any]) -> list[int]:
    values = _flatten_numbers(payload)
    if not values:
        return []
    start = values[0]
    return [value - start for value in values]


def _override_rows(path: Path, *, score_page_index: int) -> list[dict[str, int]]:
    payload = _load(path)
    rows = payload.get("measure_overrides", []) if isinstance(payload, Mapping) else []
    result = []
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        try:
            page = int(row["page"])
            system = int(row["system"])
            measure = int(row["measure"])
            skip = int(row["skip"])
        except (KeyError, TypeError, ValueError):
            continue
        if page == score_page_index:
            result.append(
                {"system": system, "measure": measure, "skip": skip}
            )
    return sorted(result, key=lambda row: (row["system"], row["measure"], row["skip"]))


def _measure_total(payload: Mapping[str, Any]) -> int:
    return sum(_counts(payload))


def _control_start(payload: Mapping[str, Any]) -> int:
    values = _flatten_numbers(payload)
    if not values:
        return 1
    return values[0]


def _control_next(payload: Mapping[str, Any], mmr: Sequence[Mapping[str, int]]) -> int:
    return _control_start(payload) + _measure_total(payload) + sum(int(row["skip"]) for row in mmr)


def _production_state(payload: Mapping[str, Any]) -> tuple[int, int, list[Any]]:
    metadata = payload.get("numbering_metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("Production final numbering lacks numbering_metadata")
    return (
        int(metadata["start_number"]),
        int(metadata["next_number"]),
        list(metadata.get("movement_boundaries", [])),
    )


def _boxes(path: Path) -> list[Box]:
    return sorted(_extract_boxes(_load(path)))


def _resolve_production_file(raw: Any, issue372_root: Path) -> Path:
    path = _host_path(str(raw), issue372_root)
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _page_artifacts(
    *,
    score: str,
    page: str,
    score_page_index: int,
    production_rows: Mapping[tuple[str, str], Mapping[str, Any]],
    production_runs: Mapping[str, Path],
    corrected_control_root: Path,
    x4_run_root: Path,
    issue372_root: Path,
) -> dict[str, Any]:
    key = (score, page)
    prod_row = production_rows[key]

    control_detector = _find_page_file(
        x4_run_root / "control" / "aggregate_probe_output",
        score,
        page,
        "pipeline2_no_peak_filtered_cnn.json",
    )
    production_detector = _resolve_production_file(prod_row["final_detector"], issue372_root)

    control_final = (
        corrected_control_root
        / "current_control_corrected"
        / score
        / page
        / "numbering_final_continued.json"
    )
    control_mmr = (
        corrected_control_root
        / "current_control_corrected"
        / score
        / page
        / "overrides_mmr.json"
    )
    production_final = _resolve_production_file(prod_row["final_numbering"], issue372_root)
    production_mmr = (
        production_runs[score]
        / "intermediate"
        / page
        / "overrides_mmr.json"
    )

    for path in (control_detector, production_detector, control_final, control_mmr, production_final, production_mmr):
        if not path.is_file():
            raise FileNotFoundError(path)

    control_final_payload = _load(control_final)
    production_final_payload = _load(production_final)
    control_mmr_rows = _override_rows(control_mmr, score_page_index=score_page_index)
    production_mmr_rows = _override_rows(production_mmr, score_page_index=score_page_index)

    control_start = _control_start(control_final_payload)
    control_next = _control_next(control_final_payload, control_mmr_rows)
    production_start, production_next, production_boundaries = _production_state(
        production_final_payload
    )

    control_boxes = _boxes(control_detector)
    production_boxes = _boxes(production_detector)

    control_set = set(control_boxes)
    production_set = set(production_boxes)

    topology_equal = _counts(control_final_payload) == _counts(production_final_payload)
    mmr_equal = control_mmr_rows == production_mmr_rows
    progression_equal = (
        _normalized_number_progression(control_final_payload)
        == _normalized_number_progression(production_final_payload)
    )
    detector_exact_equal = control_boxes == production_boxes
    start_delta = production_start - control_start
    next_delta = production_next - control_next

    local_semantic_difference = (
        not topology_equal
        or not mmr_equal
        or not progression_equal
    )
    detector_only_difference = (
        not detector_exact_equal and not local_semantic_difference
    )
    continuation_only = (
        not local_semantic_difference
        and start_delta != 0
        and start_delta == next_delta
    )

    return {
        "score": score,
        "page": page,
        "score_page_index": score_page_index,
        "detector_exact_equal": detector_exact_equal,
        "control_detector_count": len(control_boxes),
        "production_detector_count": len(production_boxes),
        "control_only_boxes": [list(box) for box in sorted(control_set - production_set)],
        "production_only_boxes": [list(box) for box in sorted(production_set - control_set)],
        "topology_equal": topology_equal,
        "control_measure_counts": _counts(control_final_payload),
        "production_measure_counts": _counts(production_final_payload),
        "mmr_equal": mmr_equal,
        "control_mmr": control_mmr_rows,
        "production_mmr": production_mmr_rows,
        "number_progression_equal": progression_equal,
        "control_number_sequences": _numbers(control_final_payload),
        "production_number_sequences": _numbers(production_final_payload),
        "control_start": control_start,
        "production_start": production_start,
        "start_delta": start_delta,
        "control_next": control_next,
        "production_next": production_next,
        "next_delta": next_delta,
        "production_movement_boundaries": production_boundaries,
        "local_semantic_difference": local_semantic_difference,
        "detector_only_difference": detector_only_difference,
        "continuation_only": continuation_only,
        "_control_boxes": control_boxes,
        "_production_boxes": production_boxes,
        "_control_final": control_final_payload,
        "_production_final": production_final_payload,
    }


def _font_scale(image: np.ndarray) -> float:
    return max(0.55, min(1.4, image.shape[1] / 2200.0))


def _draw_text(
    image: np.ndarray,
    text: str,
    origin: tuple[int, int],
    *,
    color: tuple[int, int, int],
    scale: float,
    thickness: int = 2,
) -> None:
    cv2.putText(
        image,
        text,
        origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (255, 255, 255),
        thickness + 3,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        text,
        origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def _draw_numbering(
    image: np.ndarray,
    payload: Mapping[str, Any],
    mmr_rows: Sequence[Mapping[str, int]],
) -> None:
    scale = _font_scale(image)
    mmr_map = {
        (int(row["system"]), int(row["measure"])): int(row["skip"])
        for row in mmr_rows
    }
    systems = _numbering_systems(payload)
    for sys_idx, system in enumerate(systems):
        for measure_idx, (number, bbox) in enumerate(
            zip(system["numbers"], system["bboxes"])
        ):
            x1, y1, x2, y2 = bbox
            skip = mmr_map.get((sys_idx, measure_idx))
            color = (0, 170, 0) if skip is None else (0, 110, 255)
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
            label = f"{number}"
            if skip is not None:
                label += f" (+{skip})"
            _draw_text(
                image,
                label,
                (max(0, x1), max(20, y1 - 6)),
                color=color,
                scale=scale,
                thickness=2,
            )
        if system["bboxes"]:
            first = system["bboxes"][0]
            _draw_text(
                image,
                f"S{sys_idx}",
                (8, max(20, first[1] + 28)),
                color=(180, 0, 180),
                scale=scale,
                thickness=2,
            )


def _draw_detector_diffs(
    image: np.ndarray,
    *,
    common: set[Box],
    unique: set[Box],
) -> None:
    for x1, y1, x2, y2 in common:
        cv2.rectangle(image, (x1, y1), (x2, y2), (120, 120, 120), 1)
    for x1, y1, x2, y2 in unique:
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 255), 4)


def _header(
    panel: np.ndarray,
    *,
    label: str,
    start: int,
    nxt: int,
    counts: Sequence[int],
    mmr_rows: Sequence[Mapping[str, int]],
    detector_count: int,
) -> np.ndarray:
    band_h = max(110, int(panel.shape[1] * 0.065))
    canvas = np.full((panel.shape[0] + band_h, panel.shape[1], 3), 255, dtype=np.uint8)
    canvas[band_h:] = panel
    scale = max(0.55, min(1.2, panel.shape[1] / 1800.0))
    _draw_text(
        canvas,
        f"{label}  start={start} next={nxt} detector={detector_count}",
        (12, int(band_h * 0.35)),
        color=(0, 0, 0),
        scale=scale,
        thickness=2,
    )
    _draw_text(
        canvas,
        f"measures={list(counts)}  MMR={[(r['system'], r['measure'], r['skip']) for r in mmr_rows]}",
        (12, int(band_h * 0.75)),
        color=(0, 0, 0),
        scale=max(0.45, scale * 0.75),
        thickness=1,
    )
    return canvas


def _resize_width(image: np.ndarray, max_width: int) -> np.ndarray:
    if image.shape[1] <= max_width:
        return image
    ratio = max_width / image.shape[1]
    return cv2.resize(
        image,
        (max_width, int(round(image.shape[0] * ratio))),
        interpolation=cv2.INTER_AREA,
    )


def _render_page(
    *,
    row: Mapping[str, Any],
    image_path: Path,
    output: Path,
) -> Path:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)

    control = image.copy()
    production = image.copy()
    control_boxes = set(row["_control_boxes"])
    production_boxes = set(row["_production_boxes"])
    common = control_boxes & production_boxes

    _draw_detector_diffs(
        control,
        common=common,
        unique=control_boxes - production_boxes,
    )
    _draw_detector_diffs(
        production,
        common=common,
        unique=production_boxes - control_boxes,
    )
    _draw_numbering(control, row["_control_final"], row["control_mmr"])
    _draw_numbering(production, row["_production_final"], row["production_mmr"])

    control = _header(
        control,
        label="CURRENT CONTROL",
        start=int(row["control_start"]),
        nxt=int(row["control_next"]),
        counts=row["control_measure_counts"],
        mmr_rows=row["control_mmr"],
        detector_count=int(row["control_detector_count"]),
    )
    production = _header(
        production,
        label="PRODUCTION FIX",
        start=int(row["production_start"]),
        nxt=int(row["production_next"]),
        counts=row["production_measure_counts"],
        mmr_rows=row["production_mmr"],
        detector_count=int(row["production_detector_count"]),
    )

    control = _resize_width(control, 1600)
    production = _resize_width(production, 1600)
    target_h = max(control.shape[0], production.shape[0])
    if control.shape[0] < target_h:
        control = cv2.copyMakeBorder(
            control, 0, target_h - control.shape[0], 0, 0,
            cv2.BORDER_CONSTANT, value=(255, 255, 255)
        )
    if production.shape[0] < target_h:
        production = cv2.copyMakeBorder(
            production, 0, target_h - production.shape[0], 0, 0,
            cv2.BORDER_CONSTANT, value=(255, 255, 255)
        )
    pair = np.hstack([control, production])
    output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output), pair)
    return output


def _contact_sheet(paths: Sequence[Path], output: Path) -> None:
    images = [cv2.imread(str(path), cv2.IMREAD_COLOR) for path in paths]
    images = [image for image in images if image is not None]
    if not images:
        return
    resized = [_resize_width(image, 2200) for image in images]
    width = max(image.shape[1] for image in resized)
    padded = []
    for image in resized:
        if image.shape[1] < width:
            image = cv2.copyMakeBorder(
                image, 0, 0, 0, width - image.shape[1],
                cv2.BORDER_CONSTANT, value=(255, 255, 255)
            )
        padded.append(image)
    sheet = np.vstack(padded)
    output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output), sheet)


def _public_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def run(args: argparse.Namespace) -> dict[str, Any]:
    issue372_root = args.issue372_repo_root.resolve()
    production_report = _load(args.production_report.resolve())
    production_rows, production_runs = _production_index(
        production_report,
        issue372_root=issue372_root,
    )

    corrected_root = args.corrected_control_root.resolve()
    x4_root = args.x4_run_root.resolve()
    image_root = args.image_root.resolve()
    output_root = args.output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"Output root must be new/empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for score, pages in full68_eval.SCORES.items():
        for score_page_index, page in enumerate(pages):
            rows.append(
                _page_artifacts(
                    score=score,
                    page=page,
                    score_page_index=score_page_index,
                    production_rows=production_rows,
                    production_runs=production_runs,
                    corrected_control_root=corrected_root,
                    x4_run_root=x4_root,
                    issue372_root=issue372_root,
                )
            )

    root_rows = [row for row in rows if row["local_semantic_difference"]]
    propagation_rows = [row for row in rows if row["continuation_only"]]
    unexplained_state_rows = [
        row for row in rows
        if not row["local_semantic_difference"]
        and not row["continuation_only"]
        and (row["start_delta"] != 0 or row["next_delta"] != 0)
    ]

    visual_paths = []
    for row in root_rows:
        score = str(row["score"])
        page = str(row["page"])
        image_path = image_root / score / f"{page}.png"
        safe = f"{score}__{page}".replace("/", "_")
        visual = output_root / "visuals" / f"{safe}.png"
        _render_page(row=row, image_path=image_path, output=visual)
        visual_paths.append(visual)
        row["visual"] = str(visual)

    contact_sheet = output_root / "visual_audit_contact_sheet.png"
    _contact_sheet(visual_paths, contact_sheet)

    result = {
        "schema_version": "issue372.retained_semantic_visual_audit.v1",
        "summary": {
            "page_count": len(rows),
            "local_semantic_root_page_count": len(root_rows),
            "continuation_only_page_count": len(propagation_rows),
            "unexplained_state_page_count": len(unexplained_state_rows),
            "detector_changed_page_count": sum(not row["detector_exact_equal"] for row in rows),
            "detector_only_changed_page_count": sum(row["detector_only_difference"] for row in rows),
            "topology_changed_page_count": sum(not row["topology_equal"] for row in rows),
            "mmr_changed_page_count": sum(not row["mmr_equal"] for row in rows),
            "number_progression_changed_page_count": sum(
                not row["number_progression_equal"] for row in rows
            ),
        },
        "root_pages": [_public_row(row) for row in root_rows],
        "continuation_only_pages": [_public_row(row) for row in propagation_rows],
        "unexplained_state_pages": [_public_row(row) for row in unexplained_state_rows],
        "all_pages": [_public_row(row) for row in rows],
        "visual_contact_sheet": str(contact_sheet),
    }
    report = output_root / "retained_semantic_visual_audit.json"
    _write(report, result)

    print("=== Issue #372 retained semantic + visual audit ===")
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
    print("\n=== local semantic root pages ===")
    for row in root_rows:
        print(
            f"{row['score']}/{row['page']} "
            f"detector_equal={row['detector_exact_equal']} "
            f"topology_equal={row['topology_equal']} "
            f"mmr_equal={row['mmr_equal']} "
            f"progression_equal={row['number_progression_equal']} "
            f"start_delta={row['start_delta']} next_delta={row['next_delta']} "
            f"visual={row.get('visual')}"
        )
    print("\n=== continuation-only pages ===")
    for row in propagation_rows:
        print(
            f"{row['score']}/{row['page']} "
            f"delta={row['start_delta']}"
        )
    print("\n=== unexplained state pages ===")
    for row in unexplained_state_rows:
        print(
            f"{row['score']}/{row['page']} "
            f"start_delta={row['start_delta']} next_delta={row['next_delta']}"
        )
    print(f"\nCONTACT_SHEET={contact_sheet}")
    print(f"OUTPUT={report}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-report", type=Path, required=True)
    parser.add_argument("--corrected-control-root", type=Path, required=True)
    parser.add_argument("--x4-run-root", type=Path, required=True)
    parser.add_argument("--issue372-repo-root", type=Path, required=True)
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    run(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
