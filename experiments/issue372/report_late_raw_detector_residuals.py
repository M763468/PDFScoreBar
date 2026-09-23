#!/usr/bin/env python3
"""Report exact late-raw detector residuals and their numbering-value impact.

Retained-only: no detector/HOMR/CNN/MMR inference is run.

For the Issue #372 late-raw counterfactual this tool enumerates every legacy
fixed-12 hard FN/FP and records:
- exact GT/pred bbox;
- whether a matching pre-CNN candidate exists;
- matching CNN scores;
- greedy one-to-one competition details;
- exact FP identity overlap with current control;
- nearest GT geometry for each FP;
- whether the page's final user-visible numbering values changed vs current.

This makes the detector-vs-numbering abstraction boundary explicit.
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

from experiments.issue372.reassess_final_numbering_values import (
    _number_value_signature,
    _page_map,
)
from src.common import barline_iou
from src.common.barline_evaluation import (
    barline_vertical_overlap,
    center_distance_x,
    greedy_barline_match,
    is_barline_match,
)
from tools.issue120 import eval_full68_from_intermediates as full68_eval

THRESHOLD = 0.4965248107910156


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _norm(raw: Sequence[Any]) -> tuple[int, int, int, int]:
    return tuple(int(round(float(v))) for v in raw[:4])  # type: ignore[return-value]


def _match(pred: Sequence[int], gt: Sequence[int]) -> bool:
    return is_barline_match(
        pred,
        gt,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )


def _find(root: Path, record: full68_eval.PageRecord, filename: str) -> Path:
    path = full68_eval.find_page_file(root, record, filename)
    if path is None or not path.is_file():
        raise FileNotFoundError(
            f"{record.score}/{record.page}: {filename} under {root}"
        )
    return path


def _candidate_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    return [
        _norm(box)
        for box in full68_eval.boxes_from_candidates(_load(path))
    ]


def _final_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    return [
        _norm(box)
        for box in full68_eval.boxes_from_scored(
            _load(path),
            score_threshold=THRESHOLD,
        )
    ]


def _scored(path: Path) -> list[dict[str, Any]]:
    payload = _load(path)
    if not isinstance(payload, list):
        raise ValueError(f"scored payload must be a list: {path}")
    rows = []
    for row in payload:
        if isinstance(row, Mapping) and "bbox" in row:
            rows.append({
                "bbox": _norm(row["bbox"]),
                "score": float(row.get("score", 0.0)),
            })
    return rows


def _gt(root: Path, record: full68_eval.PageRecord) -> list[tuple[int, int, int, int]]:
    path = root / record.score / record.page / "boxes_sorted.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    return [
        _norm(box)
        for box in full68_eval.boxes_from_gt(_load(path))
    ]


def _page_artifacts(root: Path, record: full68_eval.PageRecord) -> dict[str, Any]:
    candidate_path = _find(root, record, "pipeline2_no_peak_candidates.json")
    scored_path = _find(root, record, "pipeline2_no_peak_scored.json")
    final_path = _find(root, record, "pipeline2_no_peak_filtered_cnn.json")
    return {
        "candidates": _candidate_boxes(candidate_path),
        "scored": _scored(scored_path),
        "finals": _final_boxes(final_path),
        "paths": {
            "candidates": str(candidate_path),
            "scored": str(scored_path),
            "final": str(final_path),
        },
    }


def _matching_scores(
    scored: Sequence[Mapping[str, Any]],
    gt: tuple[int, int, int, int],
) -> list[dict[str, Any]]:
    rows = [
        {
            "bbox": list(_norm(row["bbox"])),
            "score": float(row["score"]),
        }
        for row in scored
        if _match(_norm(row["bbox"]), gt)
    ]
    return sorted(rows, key=lambda row: row["score"], reverse=True)


def _assignment_map(result: Any) -> dict[int, int]:
    return {int(match.pred_index): int(match.gt_index) for match in result.matches}


def _matching_final_details(
    finals: Sequence[tuple[int, int, int, int]],
    gts: Sequence[tuple[int, int, int, int]],
    result: Any,
    gt_index: int,
) -> list[dict[str, Any]]:
    assigned = _assignment_map(result)
    rows = []
    for pred_index, box in enumerate(finals):
        if not _match(box, gts[gt_index]):
            continue
        assigned_gt = assigned.get(pred_index)
        matching_gt_indices = [
            idx for idx, gt in enumerate(gts) if _match(box, gt)
        ]
        rows.append({
            "pred_index": pred_index,
            "bbox": list(box),
            "assigned_gt_index": assigned_gt,
            "assigned_gt_bbox": (
                list(gts[assigned_gt]) if assigned_gt is not None else None
            ),
            "matching_gt_indices": matching_gt_indices,
            "matching_gt_bboxes": [list(gts[idx]) for idx in matching_gt_indices],
        })
    return rows


def _classify_fn(
    *,
    matching_candidates: Sequence[tuple[int, int, int, int]],
    matching_scores: Sequence[Mapping[str, Any]],
    matching_finals: Sequence[Mapping[str, Any]],
) -> str:
    if matching_finals:
        if any(len(row["matching_gt_indices"]) > 1 for row in matching_finals):
            return "greedy_competition_multi_gt_final"
        return "greedy_assignment_competition"
    if not matching_candidates:
        return "candidate_missing"
    if not matching_scores:
        return "candidate_not_scored"
    if max(float(row["score"]) for row in matching_scores) < THRESHOLD:
        return "cnn_threshold_rejection"
    return "post_score_filter_or_final_contract"


def _nearest_gt(
    pred: tuple[int, int, int, int],
    gts: Sequence[tuple[int, int, int, int]],
) -> dict[str, Any] | None:
    if not gts:
        return None
    ranked = sorted(
        gts,
        key=lambda gt: (
            center_distance_x(pred, gt),
            -barline_vertical_overlap(pred, gt),
        ),
    )
    gt = ranked[0]
    return {
        "bbox": list(gt),
        "xdist": float(center_distance_x(pred, gt)),
        "vov": float(barline_vertical_overlap(pred, gt)),
        "iou": float(barline_iou(pred, gt)),
        "strong_match": _match(pred, gt),
    }


def _page_number_change(
    current_pages: Mapping[tuple[str, str], Mapping[str, Any]],
    late_pages: Mapping[tuple[str, str], Mapping[str, Any]],
    key: tuple[str, str],
) -> dict[str, Any]:
    left = _number_value_signature(current_pages[key])
    right = _number_value_signature(late_pages[key])
    return {
        "changed": left != right,
        "current": left,
        "late_raw_x4": right,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    x4_run = args.x4_run_root.resolve()
    late_run = args.late_run_root.resolve()
    gt_root = args.gt_root.resolve()
    semantic_report_path = args.semantic_report.resolve()
    output = args.output.resolve()

    control_root = x4_run / "control" / "aggregate_probe_output"
    late_root = (
        late_run
        / "late_raw_route"
        / "dense_candidate_reconstruction"
        / "probe_rescue_candidates"
    )
    for required in (control_root, late_root, gt_root, semantic_report_path):
        if not required.exists():
            raise FileNotFoundError(required)

    semantic_report = _load(semantic_report_path)
    if not isinstance(semantic_report, Mapping):
        raise ValueError("semantic report must be object")
    current_pages = _page_map(semantic_report, "current_control")
    late_pages = _page_map(semantic_report, "late_raw_x4")

    fn_rows = []
    fp_rows = []
    control_fp_set: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    late_fp_set: set[tuple[str, str, tuple[int, int, int, int]]] = set()

    # First pass computes all control FP identities.
    cache: dict[tuple[str, str], dict[str, Any]] = {}
    for record in full68_eval.iter_manifest():
        key = (record.score, record.page)
        gts = _gt(gt_root, record)
        control = _page_artifacts(control_root, record)
        late = _page_artifacts(late_root, record)
        control_result = greedy_barline_match(
            control["finals"],
            gts,
            rule_name="center_anchor",
            vov_threshold=0.5,
            xdist_threshold=12.0,
        )
        late_result = greedy_barline_match(
            late["finals"],
            gts,
            rule_name="center_anchor",
            vov_threshold=0.5,
            xdist_threshold=12.0,
        )
        for pred_index in control_result.false_positive_indices:
            control_fp_set.add(
                (record.score, record.page, control["finals"][pred_index])
            )
        for pred_index in late_result.false_positive_indices:
            late_fp_set.add(
                (record.score, record.page, late["finals"][pred_index])
            )
        cache[key] = {
            "gts": gts,
            "control": control,
            "late": late,
            "control_result": control_result,
            "late_result": late_result,
        }

    for (score, page), payload in cache.items():
        gts = payload["gts"]
        late = payload["late"]
        late_result = payload["late_result"]
        number_change = _page_number_change(
            current_pages,
            late_pages,
            (score, page),
        )

        for gt_index in late_result.false_negative_indices:
            gt = gts[gt_index]
            candidates = [
                box for box in late["candidates"] if _match(box, gt)
            ]
            scores = _matching_scores(late["scored"], gt)
            finals = _matching_final_details(
                late["finals"],
                gts,
                late_result,
                gt_index,
            )
            fn_rows.append({
                "score": score,
                "page": page,
                "gt_bbox": list(gt),
                "classification": _classify_fn(
                    matching_candidates=candidates,
                    matching_scores=scores,
                    matching_finals=finals,
                ),
                "matching_candidates": [list(box) for box in candidates],
                "matching_scores": scores,
                "matching_finals": finals,
                "page_number_values_changed_vs_current": number_change["changed"],
            })

        for pred_index in late_result.false_positive_indices:
            pred = late["finals"][pred_index]
            fp_key = (score, page, pred)
            fp_rows.append({
                "score": score,
                "page": page,
                "pred_bbox": list(pred),
                "also_control_fp_exact": fp_key in control_fp_set,
                "nearest_gt": _nearest_gt(pred, gts),
                "score": max(
                    [
                        float(row["score"])
                        for row in late["scored"]
                        if _norm(row["bbox"]) == pred
                    ],
                    default=None,
                ),
                "page_number_values_changed_vs_current": number_change["changed"],
            })

    fn_classes: dict[str, int] = {}
    for row in fn_rows:
        fn_classes[row["classification"]] = fn_classes.get(row["classification"], 0) + 1

    result = {
        "schema_version": "issue372.late_raw_detector_residuals.v1",
        "contract": {
            "matcher": "legacy center_anchor, vov>=0.5, xdist<=12px",
            "cnn_threshold": THRESHOLD,
            "retained_only": True,
        },
        "summary": {
            "fn_count": len(fn_rows),
            "fp_count": len(fp_rows),
            "fn_classifications": dict(sorted(fn_classes.items())),
            "fp_exact_overlap_with_control_count": len(late_fp_set & control_fp_set),
            "fp_late_only_count": len(late_fp_set - control_fp_set),
            "fp_control_only_count": len(control_fp_set - late_fp_set),
            "residual_pages_with_number_value_change": sorted({
                (row["score"], row["page"])
                for row in [*fn_rows, *fp_rows]
                if row["page_number_values_changed_vs_current"]
            }),
        },
        "false_negatives": fn_rows,
        "false_positives": fp_rows,
    }
    _write(output, result)

    print("=== Issue #372 late-raw exact detector residuals ===")
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
    print("FN:")
    for row in fn_rows:
        print(
            f"{row['score']}/{row['page']} GT={row['gt_bbox']} "
            f"class={row['classification']} "
            f"number_changed={row['page_number_values_changed_vs_current']}"
        )
    print("FP:")
    for row in fp_rows:
        print(
            f"{row['score']}/{row['page']} pred={row['pred_bbox']} "
            f"control_fp={row['also_control_fp_exact']} "
            f"number_changed={row['page_number_values_changed_vs_current']}"
        )
    print(f"OUTPUT={output}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--x4-run-root", type=Path, required=True)
    parser.add_argument("--late-run-root", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, required=True)
    parser.add_argument("--semantic-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
