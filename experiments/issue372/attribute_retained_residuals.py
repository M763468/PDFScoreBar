#!/usr/bin/env python3
"""Attribute Issue #372 residual FN/FP against retained D27 and x4-gap runs.

This is retained-only. It reruns no HOMR, SR, OMR-DLN, dense reconstruction, or
CNN inference. The accepted D27 run is evaluated directly from its retained
candidate/scored/final JSONs, avoiding dependency on an external summary file.

For residual FNs, report source coverage and matching candidate scores across:
D27, current control, and x4-gap fallback.

For residual FPs, compare exact final/candidate identity and score across the
same three variants, plus proximity to retained HOMR/hybrid source boxes.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.issue372.trace_retained_hybrid_components import (
    _component_summary,
    _d27_inventory,
    _inventory_records,
    _source_paths,
)
from src.common import barline_iou
from src.common.barline_evaluation import (
    barline_vertical_overlap,
    center_distance_x,
    greedy_barline_match,
    is_barline_match,
)
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue120 import eval_full68_from_intermediates as full68_eval

EXPECTED_D27 = {"gt": 3567, "pred": 3610, "tp": 3565, "fp": 1, "fn": 2}
DEFAULT_THRESHOLD = 0.4965248107910156


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _norm_box(raw: Sequence[Any]) -> tuple[int, int, int, int]:
    return tuple(int(round(float(v))) for v in raw[:4])  # type: ignore[return-value]


def _legacy_match(box: Sequence[int], gt: Sequence[int]) -> bool:
    return is_barline_match(
        box,
        gt,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )


def _find_page_file(root: Path, record: full68_eval.PageRecord, filename: str) -> Path:
    path = full68_eval.find_page_file(root, record, filename)
    if path is not None and path.is_file():
        return path

    token = f"eval2_{record.score}_{record.page}"
    hits = [
        candidate
        for candidate in root.rglob(filename)
        if token in candidate.parent.name or token in str(candidate.parent)
    ]
    if len(hits) != 1:
        raise FileNotFoundError(
            f"Expected one {filename} for {record.score}/{record.page} under "
            f"{root}; matches={len(hits)}"
        )
    return hits[0]


def _d27_probe_root(d27_run_root: Path, score: str) -> Path:
    root = (
        d27_run_root
        / "runs"
        / score
        / "intermediate"
        / "dense_full_pipeline_route"
        / "dense_candidate_reconstruction"
        / "probe_rescue_candidates"
    )
    if not root.is_dir():
        raise FileNotFoundError(root)
    return root


def _scored_rows(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Scored payload must be a list: {path}")
    rows: list[dict[str, Any]] = []
    for raw in payload:
        if not isinstance(raw, Mapping) or "bbox" not in raw:
            continue
        rows.append(
            {
                "bbox": list(_norm_box(raw["bbox"])),
                "score": float(raw.get("score", 0.0)),
            }
        )
    return rows


def _page_artifacts(root: Path, record: full68_eval.PageRecord) -> dict[str, Any]:
    candidates_path = _find_page_file(root, record, "pipeline2_no_peak_candidates.json")
    scored_path = _find_page_file(root, record, "pipeline2_no_peak_scored.json")
    final_path = _find_page_file(root, record, "pipeline2_no_peak_filtered_cnn.json")
    candidates = [
        _norm_box(box)
        for box in full68_eval.boxes_from_candidates(_load_json(candidates_path))
    ]
    finals = [
        _norm_box(box)
        for box in full68_eval.boxes_from_scored(
            _load_json(final_path),
            score_threshold=DEFAULT_THRESHOLD,
        )
    ]
    return {
        "candidates_path": str(candidates_path),
        "scored_path": str(scored_path),
        "final_path": str(final_path),
        "candidates": candidates,
        "scored": _scored_rows(scored_path),
        "finals": finals,
    }


def _score_rows_matching_gt(
    scored: Sequence[Mapping[str, Any]],
    gt: tuple[int, int, int, int],
) -> list[dict[str, Any]]:
    rows = [
        {"bbox": list(_norm_box(row["bbox"])), "score": float(row["score"])}
        for row in scored
        if _legacy_match(_norm_box(row["bbox"]), gt)
    ]
    return sorted(rows, key=lambda row: row["score"], reverse=True)


def _scores_for_exact(
    scored: Sequence[Mapping[str, Any]],
    box: tuple[int, int, int, int],
) -> list[float]:
    return sorted(
        [
            float(row["score"])
            for row in scored
            if _norm_box(row["bbox"]) == box
        ],
        reverse=True,
    )


def _source_relation(path: Path, box: tuple[int, int, int, int]) -> dict[str, Any]:
    boxes = [_norm_box(raw) for raw in load_json_boxes(path)]
    if not boxes:
        return {
            "path": str(path),
            "box_count": 0,
            "exact": False,
            "best_iou": 0.0,
            "best_iou_bbox": None,
            "best_vov": 0.0,
            "best_xdist": None,
        }
    best_iou_box = max(boxes, key=lambda candidate: barline_iou(candidate, box))
    best_geo_box = min(
        boxes,
        key=lambda candidate: (
            -barline_vertical_overlap(candidate, box),
            center_distance_x(candidate, box),
        ),
    )
    return {
        "path": str(path),
        "box_count": len(boxes),
        "exact": box in set(boxes),
        "best_iou": float(barline_iou(best_iou_box, box)),
        "best_iou_bbox": list(best_iou_box),
        "best_vov": float(barline_vertical_overlap(best_geo_box, box)),
        "best_xdist": float(center_distance_x(best_geo_box, box)),
        "best_geometry_bbox": list(best_geo_box),
    }


def _evaluate(
    finals: Sequence[tuple[int, int, int, int]],
    gts: Sequence[tuple[int, int, int, int]],
) -> Any:
    return greedy_barline_match(
        finals,
        gts,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )


def _aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    fields = ("gt", "pred", "tp", "fp", "fn")
    return {field: sum(int(row[field]) for row in rows) for field in fields}


def _variant_metrics(
    artifacts: Mapping[str, Any],
    gts: Sequence[tuple[int, int, int, int]],
) -> tuple[Any, dict[str, int]]:
    result = _evaluate(artifacts["finals"], gts)
    return result, {
        "gt": len(gts),
        "pred": len(artifacts["finals"]),
        "tp": len(result.matches),
        "fp": len(result.false_positive_indices),
        "fn": len(result.false_negative_indices),
    }


def _gt_source_trace(paths: Mapping[str, Path], gt: tuple[int, int, int, int]) -> dict[str, Any]:
    return {
        name: {
            key: value
            for key, value in _component_summary(path, gt).items()
            if not key.startswith("_")
        }
        for name, path in paths.items()
        if name in {"baseline", "sr", "omr", "hybrid"}
    }


def _current_source_paths(
    record: Mapping[str, Any],
    *,
    score: str,
    page: str,
    issue43_repo_root: Path,
    fallback_record: Mapping[str, Any],
) -> tuple[dict[str, Path], Path]:
    paths = _source_paths(
        record,
        score=score,
        page=page,
        repo_root=issue43_repo_root,
    )
    fallback_hybrid = Path(str(fallback_record["hybrid_predictions"])).resolve()
    if not fallback_hybrid.is_file():
        raise FileNotFoundError(fallback_hybrid)
    return paths, fallback_hybrid


def _classify_fp(
    box: tuple[int, int, int, int],
    *,
    d27: Mapping[str, Any],
    control: Mapping[str, Any],
    fallback: Mapping[str, Any],
    threshold: float,
) -> str:
    d27_candidates = set(d27["candidates"])
    control_candidates = set(control["candidates"])
    control_finals = set(control["finals"])
    d27_finals = set(d27["finals"])

    if box in control_finals:
        return "preexisting_control_final_fp"
    if box not in control_candidates:
        return "fallback_candidate_only"
    if box in d27_finals:
        return "also_d27_final_but_matching_assignment_changed"
    if box in d27_candidates:
        d27_scores = _scores_for_exact(d27["scored"], box)
        control_scores = _scores_for_exact(control["scored"], box)
        if d27_scores and control_scores:
            if max(d27_scores) < threshold <= max(control_scores):
                return "same_candidate_crossed_threshold_d27_to_current"
            return "same_candidate_scoring_or_filter_difference"
        return "same_candidate_present_d27"
    if box in control_candidates:
        return "current_candidate_not_d27_candidate"
    return "unclassified"


def run(args: argparse.Namespace) -> dict[str, Any]:
    d27_run_root = args.d27_run_root.resolve()
    run_root = args.run_root.resolve()
    d27_repo_root = args.d27_repo_root.resolve()
    issue43_repo_root = args.issue43_repo_root.resolve()
    gt_root = args.gt_root.resolve()
    output = args.output.resolve()
    threshold = float(args.threshold)

    for required in (d27_run_root, run_root, d27_repo_root, issue43_repo_root, gt_root):
        if not required.exists():
            raise FileNotFoundError(required)

    control_root = run_root / "control" / "aggregate_probe_output"
    fallback_root = run_root / "x4_gap_fallback" / "aggregate_probe_output"
    for root in (control_root, fallback_root):
        if not root.is_dir():
            raise FileNotFoundError(root)

    d27_inventory_cache: dict[str, dict[tuple[str, str], Mapping[str, Any]]] = {}
    control_inventory_cache: dict[str, dict[tuple[str, str], Mapping[str, Any]]] = {}
    fallback_inventory_cache: dict[str, dict[tuple[str, str], Mapping[str, Any]]] = {}

    page_rows: list[dict[str, Any]] = []
    d27_aggregate_rows: list[dict[str, int]] = []
    control_aggregate_rows: list[dict[str, int]] = []
    fallback_aggregate_rows: list[dict[str, int]] = []

    fallback_fn_rows: list[dict[str, Any]] = []
    fallback_fp_rows: list[dict[str, Any]] = []
    control_fp_keys: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    fallback_fp_keys: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    d27_fp_keys: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    control_fn_keys: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    fallback_fn_keys: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    d27_fn_keys: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    fp_class_counts: Counter[str] = Counter()

    for record in full68_eval.iter_manifest():
        score, page = record.score, record.page
        gt_path = gt_root / score / page / "boxes_sorted.json"
        if not gt_path.is_file():
            raise FileNotFoundError(gt_path)
        gts = [
            _norm_box(box)
            for box in full68_eval.boxes_from_gt(_load_json(gt_path))
        ]

        d27_root = _d27_probe_root(d27_run_root, score)
        d27 = _page_artifacts(d27_root, record)
        control = _page_artifacts(control_root, record)
        fallback = _page_artifacts(fallback_root, record)

        d27_result, d27_metrics = _variant_metrics(d27, gts)
        control_result, control_metrics = _variant_metrics(control, gts)
        fallback_result, fallback_metrics = _variant_metrics(fallback, gts)
        d27_aggregate_rows.append(d27_metrics)
        control_aggregate_rows.append(control_metrics)
        fallback_aggregate_rows.append(fallback_metrics)

        page_rows.append(
            {
                "score": score,
                "page": page,
                "d27": d27_metrics,
                "control": control_metrics,
                "fallback": fallback_metrics,
            }
        )

        if score not in d27_inventory_cache:
            d27_inventory_cache[score] = _inventory_records(
                _d27_inventory(d27_run_root, score)
            )
            control_inventory_cache[score] = _inventory_records(
                run_root / "inventories" / "control" / f"{score}.json"
            )
            fallback_inventory_cache[score] = _inventory_records(
                run_root / "inventories" / "x4_gap_fallback" / f"{score}.json"
            )

        key = (score, page)
        d27_record = d27_inventory_cache[score][key]
        control_record = control_inventory_cache[score][key]
        fallback_record = fallback_inventory_cache[score][key]
        d27_sources = _source_paths(
            d27_record,
            score=score,
            page=page,
            repo_root=d27_repo_root,
        )
        current_sources, fallback_hybrid = _current_source_paths(
            control_record,
            score=score,
            page=page,
            issue43_repo_root=issue43_repo_root,
            fallback_record=fallback_record,
        )

        for gt_index in d27_result.false_negative_indices:
            d27_fn_keys.add((score, page, gts[gt_index]))
        for gt_index in control_result.false_negative_indices:
            control_fn_keys.add((score, page, gts[gt_index]))
        for gt_index in fallback_result.false_negative_indices:
            gt = gts[gt_index]
            residual_key = (score, page, gt)
            fallback_fn_keys.add(residual_key)
            matching_candidates = [
                box for box in fallback["candidates"] if _legacy_match(box, gt)
            ]
            fallback_fn_rows.append(
                {
                    "score": score,
                    "page": page,
                    "gt_bbox": list(gt),
                    "also_fn_in_d27": residual_key in d27_fn_keys,
                    "also_fn_in_control": residual_key in control_fn_keys,
                    "candidate_match_count": len(matching_candidates),
                    "d27": {
                        "matching_candidates": [
                            list(box)
                            for box in d27["candidates"]
                            if _legacy_match(box, gt)
                        ],
                        "matching_scores": _score_rows_matching_gt(d27["scored"], gt),
                        "final_covers_gt": any(
                            _legacy_match(box, gt) for box in d27["finals"]
                        ),
                        "source": _gt_source_trace(d27_sources, gt),
                    },
                    "control": {
                        "matching_candidates": [
                            list(box)
                            for box in control["candidates"]
                            if _legacy_match(box, gt)
                        ],
                        "matching_scores": _score_rows_matching_gt(control["scored"], gt),
                        "final_covers_gt": any(
                            _legacy_match(box, gt) for box in control["finals"]
                        ),
                        "source": _gt_source_trace(current_sources, gt),
                    },
                    "fallback": {
                        "matching_candidates": [list(box) for box in matching_candidates],
                        "matching_scores": _score_rows_matching_gt(fallback["scored"], gt),
                        "final_covers_gt": False,
                        "hybrid": {
                            key: value
                            for key, value in _component_summary(fallback_hybrid, gt).items()
                            if not key.startswith("_")
                        },
                    },
                }
            )

        for name, result, artifacts, target in (
            ("d27", d27_result, d27, d27_fp_keys),
            ("control", control_result, control, control_fp_keys),
            ("fallback", fallback_result, fallback, fallback_fp_keys),
        ):
            for pred_index in result.false_positive_indices:
                box = artifacts["finals"][pred_index]
                target.add((score, page, box))

        for pred_index in fallback_result.false_positive_indices:
            box = fallback["finals"][pred_index]
            residual_key = (score, page, box)
            classification = _classify_fp(
                box,
                d27=d27,
                control=control,
                fallback=fallback,
                threshold=threshold,
            )
            fp_class_counts[classification] += 1
            fallback_fp_rows.append(
                {
                    "score": score,
                    "page": page,
                    "bbox": list(box),
                    "classification": classification,
                    "also_fp_in_control": residual_key in control_fp_keys,
                    "also_fp_in_d27": residual_key in d27_fp_keys,
                    "exact_identity": {
                        "d27_candidate": box in set(d27["candidates"]),
                        "d27_final": box in set(d27["finals"]),
                        "control_candidate": box in set(control["candidates"]),
                        "control_final": box in set(control["finals"]),
                        "fallback_candidate": box in set(fallback["candidates"]),
                        "fallback_final": True,
                    },
                    "scores": {
                        "d27": _scores_for_exact(d27["scored"], box),
                        "control": _scores_for_exact(control["scored"], box),
                        "fallback": _scores_for_exact(fallback["scored"], box),
                    },
                    "source_relation": {
                        "d27_baseline": _source_relation(d27_sources["baseline"], box),
                        "d27_x4": _source_relation(d27_sources["sr"], box),
                        "d27_hybrid": _source_relation(d27_sources["hybrid"], box),
                        "current_baseline": _source_relation(
                            current_sources["baseline"], box
                        ),
                        "current_x4": _source_relation(current_sources["sr"], box),
                        "current_hybrid": _source_relation(
                            current_sources["hybrid"], box
                        ),
                        "fallback_hybrid": _source_relation(fallback_hybrid, box),
                    },
                }
            )

    d27_aggregate = _aggregate(d27_aggregate_rows)
    control_aggregate = _aggregate(control_aggregate_rows)
    fallback_aggregate = _aggregate(fallback_aggregate_rows)
    d27_gate = d27_aggregate == EXPECTED_D27

    # Membership booleans above are filled while pages are traversed, so recompute
    # the final cross-variant residual relations once all pages have been seen.
    for row in fallback_fn_rows:
        key = (row["score"], row["page"], _norm_box(row["gt_bbox"]))
        row["also_fn_in_d27"] = key in d27_fn_keys
        row["also_fn_in_control"] = key in control_fn_keys
    for row in fallback_fp_rows:
        key = (row["score"], row["page"], _norm_box(row["bbox"]))
        row["also_fp_in_control"] = key in control_fp_keys
        row["also_fp_in_d27"] = key in d27_fp_keys

    result = {
        "schema_version": "issue372.retained_residual_attribution.v1",
        "contract": {
            "retained_only": True,
            "matcher": "center_anchor, vov>=0.5, fixed xdist<=12px",
            "threshold": threshold,
            "d27_expected": EXPECTED_D27,
            "d27_reproduced": d27_gate,
        },
        "aggregate": {
            "d27": d27_aggregate,
            "control": control_aggregate,
            "fallback": fallback_aggregate,
        },
        "residual_sets": {
            "fn": {
                "d27_count": len(d27_fn_keys),
                "control_count": len(control_fn_keys),
                "fallback_count": len(fallback_fn_keys),
                "fallback_also_d27_count": len(fallback_fn_keys & d27_fn_keys),
                "fallback_new_vs_d27_count": len(fallback_fn_keys - d27_fn_keys),
                "control_recovered_by_fallback_count": len(
                    control_fn_keys - fallback_fn_keys
                ),
            },
            "fp": {
                "d27_count": len(d27_fp_keys),
                "control_count": len(control_fp_keys),
                "fallback_count": len(fallback_fp_keys),
                "control_fallback_exact_overlap_count": len(
                    control_fp_keys & fallback_fp_keys
                ),
                "fallback_new_vs_control_count": len(
                    fallback_fp_keys - control_fp_keys
                ),
                "fallback_removed_vs_control_count": len(
                    control_fp_keys - fallback_fp_keys
                ),
                "fallback_new_vs_d27_count": len(fallback_fp_keys - d27_fp_keys),
            },
        },
        "fallback_fn_rows": fallback_fn_rows,
        "fallback_fp_classification_counts": dict(sorted(fp_class_counts.items())),
        "fallback_fp_rows": fallback_fp_rows,
        "page_metrics": page_rows,
    }
    _write_json(output, result)

    print("=== Issue #372 retained residual attribution ===")
    print(f"d27_reproduced={d27_gate} aggregate={d27_aggregate}")
    print(f"control={control_aggregate}")
    print(f"fallback={fallback_aggregate}")
    print(f"FN sets={result['residual_sets']['fn']}")
    print(f"FP sets={result['residual_sets']['fp']}")
    print(
        "FP classifications="
        f"{dict(sorted(fp_class_counts.items()))}"
    )
    print(f"OUTPUT={output}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--d27-run-root", type=Path, required=True)
    parser.add_argument("--d27-repo-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument(
        "--gt-root",
        type=Path,
        default=ROOT / "data/evaluation2/annotations",
    )
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
