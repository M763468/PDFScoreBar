#!/usr/bin/env python3
"""Issue #372 retained-only detector regression comparison.

Compare the accepted Issue #296 D27 full68 summary against an already-saved
current-production detector output tree.  No HOMR/SR/CNN inference is run.

The script deliberately evaluates the current output under both:
- the historical D27 center-anchor matcher (vov>=0.5, xdist<=12px), and
- the current normalized matcher (vov>=0.5, xdist<=0.5*page unit_size).

This separates matcher-contract effects from producer/candidate/CNN effects and
classifies each newly missing GT as candidate-generation ("detector") vs CNN
rejection at the final detector boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image

from src.common.barline_evaluation import (
    CENTER_ANCHOR_XDIST_UNIT_RATIO,
    barline_vertical_overlap,
    center_distance_x,
    greedy_barline_match,
    is_barline_match,
)
from src.common.barline_units import (
    PageStaffUnit,
    load_page_staff_units,
    require_page_staff_unit,
    validate_coordinate_dimensions,
)
from tools.issue120 import eval_full68_from_intermediates as full68_eval

DEFAULT_D27_SUMMARY = (
    ROOT
    / "logs/issue296/diagnostic_27_current_candidate_aligned/full68/clean_full68_summary.json"
)
DEFAULT_GT_ROOT = ROOT / "data/evaluation2/annotations"
DEFAULT_IMAGE_ROOT = ROOT / "data/evaluation2/images"
DEFAULT_STAFF_UNITS = ROOT / "data/evaluation2/staff_units.json"
DEFAULT_OUTPUT = ROOT / "logs/issue372/retained_detector_comparison.json"
DEFAULT_THRESHOLD = 0.4965248107910156


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def _normalize_box(box: Sequence[Any]) -> tuple[int, int, int, int]:
    if len(box) < 4:
        raise ValueError(f"Invalid box: {box!r}")
    return tuple(int(round(float(value))) for value in box[:4])  # type: ignore[return-value]


def _box_key(score: str, page: str, box: Sequence[Any]) -> tuple[str, str, tuple[int, int, int, int]]:
    return score, page, _normalize_box(box)


def _matched_gt_indices(result: Any) -> set[int]:
    return {int(item.gt_index) for item in result.matches}


def _has_match(
    boxes: Iterable[tuple[int, int, int, int]],
    gt: tuple[int, int, int, int],
    *,
    unit_size: float | None,
    legacy: bool,
) -> bool:
    return any(
        is_barline_match(
            box,
            gt,
            rule_name="center_anchor",
            vov_threshold=0.5,
            xdist_threshold=12.0 if legacy else None,
            unit_size=None if legacy else unit_size,
            xdist_unit_ratio=CENTER_ANCHOR_XDIST_UNIT_RATIO,
        )
        for box in boxes
    )


def _nearest_box(
    boxes: Sequence[tuple[int, int, int, int]],
    gt: tuple[int, int, int, int],
) -> dict[str, Any] | None:
    if not boxes:
        return None
    ranked = sorted(
        boxes,
        key=lambda box: (
            -barline_vertical_overlap(box, gt),
            center_distance_x(box, gt),
        ),
    )
    box = ranked[0]
    return {
        "bbox": list(box),
        "vov": barline_vertical_overlap(box, gt),
        "xdist": center_distance_x(box, gt),
    }


def _load_page_inputs(
    *,
    current_root: Path,
    gt_root: Path,
    record: full68_eval.PageRecord,
    scored_file: str,
    candidates_file: str,
    threshold: float,
) -> tuple[
    list[tuple[int, int, int, int]],
    list[tuple[int, int, int, int]],
    list[tuple[int, int, int, int]],
    Path,
    Path | None,
]:
    gt_path = gt_root / record.score / record.page / "boxes_sorted.json"
    scored_path = full68_eval.find_page_file(current_root, record, scored_file)
    candidates_path = full68_eval.find_page_file(current_root, record, candidates_file)
    if not gt_path.is_file():
        raise FileNotFoundError(gt_path)
    if scored_path is None:
        raise FileNotFoundError(
            f"Missing {scored_file} for {record.score}/{record.page} under {current_root}"
        )
    gts = full68_eval.boxes_from_gt(_load_json(gt_path))
    preds = full68_eval.boxes_from_scored(_load_json(scored_path), score_threshold=threshold)
    candidates: list[tuple[int, int, int, int]] = []
    if candidates_path is not None and candidates_path.is_file():
        candidates = full68_eval.boxes_from_candidates(_load_json(candidates_path))
    return gts, preds, candidates, scored_path, candidates_path


def _evaluate_page(
    preds: Sequence[tuple[int, int, int, int]],
    gts: Sequence[tuple[int, int, int, int]],
    candidates: Sequence[tuple[int, int, int, int]],
    *,
    unit_size: float | None,
    legacy: bool,
) -> tuple[Any, dict[str, int]]:
    result = greedy_barline_match(
        preds,
        gts,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0 if legacy else None,
        unit_size=None if legacy else unit_size,
        xdist_unit_ratio=CENTER_ANCHOR_XDIST_UNIT_RATIO,
    )
    fn_det = 0
    fn_cnn = 0
    for gt_index in result.false_negative_indices:
        gt = gts[gt_index]
        if _has_match(candidates, gt, unit_size=unit_size, legacy=legacy):
            fn_cnn += 1
        else:
            fn_det += 1
    return result, {
        "gt": len(gts),
        "pred": len(preds),
        "candidate_count": len(candidates),
        "tp": len(result.matches),
        "hard_fp": len(result.false_positive_indices),
        "fn": len(result.false_negative_indices),
        "fn_det": fn_det,
        "fn_cnn": fn_cnn,
        "soft": len(result.soft_matches),
    }


def _aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    fields = ("gt", "pred", "candidate_count", "tp", "hard_fp", "fn", "fn_det", "fn_cnn", "soft")
    return {field: sum(int(row[field]) for row in rows) for field in fields}


def _d27_page_metrics(summary: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, int]]:
    result: dict[tuple[str, str], dict[str, int]] = {}
    pages = summary.get("pages")
    if not isinstance(pages, list):
        raise ValueError("D27 summary lacks pages[]")
    for row in pages:
        if not isinstance(row, Mapping):
            continue
        key = (str(row["score"]), str(row["page"]))
        result[key] = {
            "gt": int(row["gt_count"]),
            "pred": int(row["clean_accepted"]),
            "tp": int(row["clean_tp"]),
            "hard_fp": int(row["clean_hard_fp"]),
            "fn": int(row["clean_fn"]),
            "soft": int(row["clean_soft"]),
        }
    return result


def _d27_residual_sets(
    summary: Mapping[str, Any],
) -> tuple[
    set[tuple[str, str, tuple[int, int, int, int]]],
    set[tuple[str, str, tuple[int, int, int, int]]],
]:
    fns: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    fps: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    for row in summary.get("residuals", []):
        if not isinstance(row, Mapping):
            continue
        kind = row.get("kind")
        key = _box_key(str(row["score"]), str(row["page"]), row["bbox"])
        if kind == "clean_fn":
            fns.add(key)
        elif kind == "clean_hard_fp":
            fps.add(key)
    return fns, fps


def run(args: argparse.Namespace) -> dict[str, Any]:
    d27_summary_path = args.d27_summary.resolve()
    current_root = args.current_root.resolve()
    gt_root = args.gt_root.resolve()
    image_root = args.image_root.resolve()
    staff_units_path = args.staff_units_json.resolve()
    output = args.output.resolve()

    for required in (d27_summary_path, gt_root, image_root, staff_units_path):
        if not required.exists():
            raise FileNotFoundError(required)
    if not current_root.is_dir():
        raise FileNotFoundError(current_root)

    d27 = _load_json(d27_summary_path)
    if not isinstance(d27, Mapping):
        raise ValueError("D27 summary must be a JSON object")
    d27_threshold = float(d27.get("threshold", args.threshold))
    if abs(d27_threshold - args.threshold) > 1e-12:
        raise ValueError(
            f"Threshold mismatch: D27={d27_threshold} requested={args.threshold}"
        )

    units = load_page_staff_units(staff_units_path)
    d27_pages = _d27_page_metrics(d27)
    d27_fns, d27_fps = _d27_residual_sets(d27)

    current_legacy_rows: list[dict[str, Any]] = []
    current_unit_rows: list[dict[str, Any]] = []
    current_legacy_fn_records: dict[
        tuple[str, str, tuple[int, int, int, int]], dict[str, Any]
    ] = {}
    current_unit_fn_keys: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    current_legacy_fp_keys: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    matcher_changed_pages: list[dict[str, Any]] = []
    page_deltas_vs_d27: list[dict[str, Any]] = []
    input_files: list[dict[str, Any]] = []

    for record in full68_eval.iter_manifest():
        page_unit: PageStaffUnit = require_page_staff_unit(units, record.score, record.page)
        image_path = image_root / record.score / f"{record.page}.png"
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        with Image.open(image_path) as image:
            validate_coordinate_dimensions(
                page_unit,
                width=image.width,
                height=image.height,
                page=f"{record.score}/{record.page}",
            )

        gts, preds, candidates, scored_path, candidates_path = _load_page_inputs(
            current_root=current_root,
            gt_root=gt_root,
            record=record,
            scored_file=args.scored_file,
            candidates_file=args.candidates_file,
            threshold=args.threshold,
        )
        legacy_result, legacy_metrics = _evaluate_page(
            preds,
            gts,
            candidates,
            unit_size=page_unit.unit_size,
            legacy=True,
        )
        unit_result, unit_metrics = _evaluate_page(
            preds,
            gts,
            candidates,
            unit_size=page_unit.unit_size,
            legacy=False,
        )
        legacy_row = {"score": record.score, "page": record.page, **legacy_metrics}
        unit_row = {"score": record.score, "page": record.page, **unit_metrics}
        current_legacy_rows.append(legacy_row)
        current_unit_rows.append(unit_row)

        input_files.append(
            {
                "score": record.score,
                "page": record.page,
                "scored": str(scored_path),
                "scored_sha256": _sha256(scored_path),
                "candidates": str(candidates_path) if candidates_path else None,
                "candidates_sha256": (
                    _sha256(candidates_path)
                    if candidates_path is not None and candidates_path.is_file()
                    else None
                ),
            }
        )

        if any(
            legacy_metrics[field] != unit_metrics[field]
            for field in ("tp", "hard_fp", "fn", "fn_det", "fn_cnn", "soft")
        ):
            matcher_changed_pages.append(
                {
                    "score": record.score,
                    "page": record.page,
                    "legacy_fixed12": legacy_metrics,
                    "current_unit": unit_metrics,
                }
            )

        d27_page = d27_pages.get((record.score, record.page))
        if d27_page is None:
            raise ValueError(f"D27 summary missing page {record.score}/{record.page}")
        if any(
            legacy_metrics[field] != d27_page[field]
            for field in ("gt", "pred", "tp", "hard_fp", "fn", "soft")
        ):
            page_deltas_vs_d27.append(
                {
                    "score": record.score,
                    "page": record.page,
                    "d27": d27_page,
                    "current_legacy_fixed12": legacy_metrics,
                    "delta": {
                        field: legacy_metrics[field] - d27_page[field]
                        for field in ("pred", "tp", "hard_fp", "fn", "soft")
                    },
                }
            )

        legacy_matched = _matched_gt_indices(legacy_result)
        unit_matched = _matched_gt_indices(unit_result)
        for gt_index, gt in enumerate(gts):
            key = (record.score, record.page, gt)
            if gt_index not in unit_matched:
                current_unit_fn_keys.add(key)
            if gt_index in legacy_matched:
                continue
            candidate_present = _has_match(
                candidates,
                gt,
                unit_size=page_unit.unit_size,
                legacy=True,
            )
            current_legacy_fn_records[key] = {
                "score": record.score,
                "page": record.page,
                "gt_bbox": list(gt),
                "stage": "cnn" if candidate_present else "detector",
                "candidate_match_present": candidate_present,
                "matched_under_current_unit": gt_index in unit_matched,
                "unit_size": page_unit.unit_size,
                "legacy_xdist_limit": 12.0,
                "current_xdist_limit": (
                    page_unit.unit_size * CENTER_ANCHOR_XDIST_UNIT_RATIO
                ),
                "nearest_candidate": _nearest_box(candidates, gt),
                "nearest_final_prediction": _nearest_box(preds, gt),
            }

        for pred_index in legacy_result.false_positive_indices:
            current_legacy_fp_keys.add(
                (record.score, record.page, preds[pred_index])
            )

    current_legacy_fn_keys = set(current_legacy_fn_records)
    new_fns = current_legacy_fn_keys - d27_fns
    recovered_d27_fns = d27_fns - current_legacy_fn_keys
    persistent_d27_fns = d27_fns & current_legacy_fn_keys
    new_fps = current_legacy_fp_keys - d27_fps
    removed_d27_fps = d27_fps - current_legacy_fp_keys

    new_fn_records = [current_legacy_fn_records[key] for key in sorted(new_fns)]
    new_fn_stage_counts = Counter(row["stage"] for row in new_fn_records)
    new_fn_page_counts = Counter(f"{row['score']}/{row['page']}" for row in new_fn_records)

    d27_clean = d27.get("clean")
    if not isinstance(d27_clean, Mapping):
        raise ValueError("D27 summary lacks clean aggregate")

    result = {
        "schema_version": "issue372.retained_detector_comparison.v1",
        "provenance": {
            "source_commit": _git_head(),
            "d27_summary": str(d27_summary_path),
            "d27_summary_sha256": _sha256(d27_summary_path),
            "current_root": str(current_root),
            "gt_root": str(gt_root),
            "image_root": str(image_root),
            "staff_units_json": str(staff_units_path),
            "staff_units_sha256": _sha256(staff_units_path),
            "score_threshold": args.threshold,
            "scored_file": args.scored_file,
            "candidates_file": args.candidates_file,
        },
        "d27_accepted_legacy_fixed12": {
            "aggregate": dict(d27_clean),
            "fn_residual_count": len(d27_fns),
            "hard_fp_residual_count": len(d27_fps),
        },
        "current_saved_output": {
            "legacy_fixed12": _aggregate(current_legacy_rows),
            "current_unit": _aggregate(current_unit_rows),
        },
        "matcher_effect": {
            "aggregate_equal": _aggregate(current_legacy_rows) == _aggregate(current_unit_rows),
            "changed_page_count": len(matcher_changed_pages),
            "changed_pages": matcher_changed_pages,
            "legacy_only_fn_count": len(current_legacy_fn_keys - current_unit_fn_keys),
            "unit_only_fn_count": len(current_unit_fn_keys - current_legacy_fn_keys),
        },
        "d27_to_current_legacy_fixed12": {
            "changed_page_count": len(page_deltas_vs_d27),
            "changed_pages": page_deltas_vs_d27,
            "new_fn_count": len(new_fns),
            "new_fn_stage_counts": dict(sorted(new_fn_stage_counts.items())),
            "new_fn_page_counts": dict(sorted(new_fn_page_counts.items())),
            "new_fns": new_fn_records,
            "persistent_d27_fns": [
                {"score": score, "page": page, "gt_bbox": list(box)}
                for score, page, box in sorted(persistent_d27_fns)
            ],
            "recovered_d27_fns": [
                {"score": score, "page": page, "gt_bbox": list(box)}
                for score, page, box in sorted(recovered_d27_fns)
            ],
            "new_hard_fp_count_exact_bbox": len(new_fps),
            "new_hard_fps_exact_bbox": [
                {"score": score, "page": page, "bbox": list(box)}
                for score, page, box in sorted(new_fps)
            ],
            "removed_d27_hard_fps_exact_bbox": [
                {"score": score, "page": page, "bbox": list(box)}
                for score, page, box in sorted(removed_d27_fps)
            ],
        },
        "input_files": input_files,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("=== Issue #372 retained detector comparison ===")
    print(f"D27 legacy:       {dict(d27_clean)}")
    print(f"current legacy:   {result['current_saved_output']['legacy_fixed12']}")
    print(f"current unit:     {result['current_saved_output']['current_unit']}")
    print(
        "matcher changed pages: "
        f"{result['matcher_effect']['changed_page_count']} "
        f"(aggregate_equal={result['matcher_effect']['aggregate_equal']})"
    )
    print(
        "new FN vs D27: "
        f"{len(new_fns)} stages={dict(sorted(new_fn_stage_counts.items()))}"
    )
    print(f"new hard FP exact-bbox vs D27: {len(new_fps)}")
    print(f"OUTPUT={output}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--d27-summary", type=Path, default=DEFAULT_D27_SUMMARY)
    parser.add_argument("--current-root", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, default=DEFAULT_GT_ROOT)
    parser.add_argument("--image-root", type=Path, default=DEFAULT_IMAGE_ROOT)
    parser.add_argument("--staff-units-json", type=Path, default=DEFAULT_STAFF_UNITS)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument(
        "--scored-file",
        default="pipeline2_no_peak_filtered_cnn.json",
        help="Current saved final detector file; filtered output may be boxes or scored rows.",
    )
    parser.add_argument(
        "--candidates-file",
        default="pipeline2_no_peak_candidates.json",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())