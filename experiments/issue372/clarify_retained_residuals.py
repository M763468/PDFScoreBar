#!/usr/bin/env python3
"""Clarify Issue #372 remaining residuals after the x4-gap counterfactual.

Authoritative D27 FN/FP identities come from the retained Issue #296 raw
clean_full68_summary.json. The Issue #274 producer run is not treated as D27
CNN output.

For each fallback FN, distinguish:
- no candidate;
- CNN-threshold rejection;
- post-score filtering;
- final prediction exists but greedy one-to-one matching competition leaves the
  GT unmatched (notably merged physical double-barline strokes).

For FP, compare exact D27/control/fallback residual identities and trace whether
fallback-only/removed FP boxes first appear at raw, filtered, rescue, or final.
No inference is run.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.barline_evaluation import greedy_barline_match, is_barline_match
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue120 import eval_full68_from_intermediates as full68_eval

EXPECTED_D27 = {
    "pages": 68,
    "gt": 3567,
    "tp": 3565,
    "hard_fp": 1,
    "fn": 2,
    "soft": 44,
}
DEFAULT_THRESHOLD = 0.4965248107910156


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _norm(raw: Sequence[Any]) -> tuple[int, int, int, int]:
    return tuple(int(round(float(v))) for v in raw[:4])  # type: ignore[return-value]


def _match(box: Sequence[int], gt: Sequence[int]) -> bool:
    return is_barline_match(
        box,
        gt,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )


def _page_file(root: Path, record: full68_eval.PageRecord, filename: str) -> Path:
    path = full68_eval.find_page_file(root, record, filename)
    if path is None or not path.is_file():
        raise FileNotFoundError(
            f"Missing {filename} for {record.score}/{record.page} under {root}"
        )
    return path


def _boxes(path: Path, *, scored_threshold: float | None = None) -> list[tuple[int, int, int, int]]:
    payload = _load_json(path)
    if scored_threshold is None:
        return [_norm(box) for box in full68_eval.boxes_from_candidates(payload)]
    return [
        _norm(box)
        for box in full68_eval.boxes_from_scored(
            payload,
            score_threshold=scored_threshold,
        )
    ]


def _scored(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Scored payload must be list: {path}")
    rows = []
    for item in payload:
        if isinstance(item, Mapping) and "bbox" in item:
            rows.append({"bbox": _norm(item["bbox"]), "score": float(item.get("score", 0.0))})
    return rows


def _load_variant(root: Path, record: full68_eval.PageRecord) -> dict[str, Any]:
    candidates_path = _page_file(root, record, "pipeline2_no_peak_candidates.json")
    scored_path = _page_file(root, record, "pipeline2_no_peak_scored.json")
    final_path = _page_file(root, record, "pipeline2_no_peak_filtered_cnn.json")
    return {
        "candidates_path": str(candidates_path),
        "scored_path": str(scored_path),
        "final_path": str(final_path),
        "candidates": _boxes(candidates_path),
        "scored": _scored(scored_path),
        "finals": _boxes(final_path, scored_threshold=DEFAULT_THRESHOLD),
    }


def _gt_boxes(gt_root: Path, record: full68_eval.PageRecord) -> list[tuple[int, int, int, int]]:
    path = gt_root / record.score / record.page / "boxes_sorted.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    return [_norm(box) for box in full68_eval.boxes_from_gt(_load_json(path))]


def _evaluate(finals: Sequence[tuple[int, int, int, int]], gts: Sequence[tuple[int, int, int, int]]) -> Any:
    return greedy_barline_match(
        finals,
        gts,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )


def _residual_sets_from_d27(summary: Mapping[str, Any]) -> tuple[
    set[tuple[str, str, tuple[int, int, int, int]]],
    set[tuple[str, str, tuple[int, int, int, int]]],
]:
    fns: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    fps: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    for row in summary.get("residuals", []):
        if not isinstance(row, Mapping):
            continue
        key = (str(row["score"]), str(row["page"]), _norm(row["bbox"]))
        if row.get("kind") == "clean_fn":
            fns.add(key)
        elif row.get("kind") == "clean_hard_fp":
            fps.add(key)
    return fns, fps


def _matching_scores(scored: Sequence[Mapping[str, Any]], gt: tuple[int, int, int, int]) -> list[dict[str, Any]]:
    rows = [
        {"bbox": list(_norm(row["bbox"])), "score": float(row["score"])}
        for row in scored
        if _match(_norm(row["bbox"]), gt)
    ]
    return sorted(rows, key=lambda row: row["score"], reverse=True)


def _exact_score(scored: Sequence[Mapping[str, Any]], box: tuple[int, int, int, int]) -> list[float]:
    return sorted(
        [float(row["score"]) for row in scored if _norm(row["bbox"]) == box],
        reverse=True,
    )


def _matching_final_details(
    finals: Sequence[tuple[int, int, int, int]],
    gts: Sequence[tuple[int, int, int, int]],
    result: Any,
    gt_index: int,
) -> list[dict[str, Any]]:
    assignment = {int(match.pred_index): int(match.gt_index) for match in result.matches}
    rows: list[dict[str, Any]] = []
    for pred_index, box in enumerate(finals):
        if not _match(box, gts[gt_index]):
            continue
        assigned_index = assignment.get(pred_index)
        rows.append(
            {
                "pred_index": pred_index,
                "bbox": list(box),
                "assigned_gt_index": assigned_index,
                "assigned_gt_bbox": (
                    list(gts[assigned_index]) if assigned_index is not None else None
                ),
                "all_matching_gt_indices": [
                    index for index, gt in enumerate(gts) if _match(box, gt)
                ],
                "all_matching_gt_bboxes": [
                    list(gt) for gt in gts if _match(box, gt)
                ],
            }
        )
    return rows


def _classify_fn(
    *,
    gt: tuple[int, int, int, int],
    candidates: Sequence[tuple[int, int, int, int]],
    scored: Sequence[Mapping[str, Any]],
    matching_finals: Sequence[Mapping[str, Any]],
    threshold: float,
) -> str:
    matching_candidates = [box for box in candidates if _match(box, gt)]
    if not matching_candidates:
        return "candidate_missing"
    if matching_finals:
        if any(len(row["all_matching_gt_indices"]) > 1 for row in matching_finals):
            return "greedy_competition_merged_multi_gt_final"
        return "greedy_assignment_competition"
    scores = _matching_scores(scored, gt)
    if not scores:
        return "candidate_not_scored"
    if max(float(row["score"]) for row in scores) < threshold:
        return "cnn_threshold_rejection"
    return "post_score_filter_or_final_contract"


def _root_stage(run_root: Path, variant: str, stage: str) -> Path:
    name = {
        "raw": "aggregate_raw_candidates",
        "filtered": "aggregate_filtered_candidates",
        "rescue": "aggregate_probe_output",
    }[stage]
    root = run_root / variant / name
    if not root.is_dir():
        raise FileNotFoundError(root)
    return root


def _exact_stage_presence(
    run_root: Path,
    variant: str,
    record: full68_eval.PageRecord,
    box: tuple[int, int, int, int],
) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for stage in ("raw", "filtered", "rescue"):
        root = _root_stage(run_root, variant, stage)
        path = _page_file(root, record, "pipeline2_no_peak_candidates.json")
        result[stage] = box in set(_boxes(path))
    return result


def _load_hybrid_from_inventory(run_root: Path, variant: str, score: str, page: str) -> Path:
    path = run_root / "inventories" / variant / f"{score}.json"
    payload = _load_json(path)
    for row in payload.get("records", []):
        if isinstance(row, Mapping) and str(row.get("page")) == page:
            hybrid = Path(str(row["hybrid_predictions"])).resolve()
            if not hybrid.is_file():
                raise FileNotFoundError(hybrid)
            return hybrid
    raise KeyError(f"Inventory record missing for {score}/{page}")


def _nearest_promoted(
    control_hybrid: Path,
    fallback_hybrid: Path,
    box: tuple[int, int, int, int],
) -> dict[str, Any] | None:
    control = {_norm(raw) for raw in load_json_boxes(control_hybrid)}
    fallback = {_norm(raw) for raw in load_json_boxes(fallback_hybrid)}
    promoted = list(fallback - control)
    if not promoted:
        return None
    promoted.sort(
        key=lambda candidate: (
            abs((candidate[0] + candidate[2]) - (box[0] + box[2])),
            abs((candidate[1] + candidate[3]) - (box[1] + box[3])),
        )
    )
    nearest = promoted[0]
    return {"bbox": list(nearest), "exact": nearest == box}


def run(args: argparse.Namespace) -> dict[str, Any]:
    d27_summary_path = args.d27_summary.resolve()
    run_root = args.run_root.resolve()
    gt_root = args.gt_root.resolve()
    output = args.output.resolve()
    threshold = float(args.threshold)

    for path in (d27_summary_path, run_root, gt_root):
        if not path.exists():
            raise FileNotFoundError(path)

    d27 = _load_json(d27_summary_path)
    if not isinstance(d27, Mapping):
        raise ValueError("D27 summary must be a JSON object")
    clean = d27.get("clean")
    if not isinstance(clean, Mapping):
        raise ValueError("D27 raw summary lacks clean aggregate")
    d27_clean = {key: int(clean[key]) for key in EXPECTED_D27}
    d27_gate = d27_clean == EXPECTED_D27
    d27_fns, d27_fps = _residual_sets_from_d27(d27)

    control_root = _root_stage(run_root, "control", "rescue")
    fallback_root = _root_stage(run_root, "x4_gap_fallback", "rescue")

    control_fn: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    fallback_fn: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    control_fp: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    fallback_fp: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    fn_rows: list[dict[str, Any]] = []
    page_cache: dict[tuple[str, str], dict[str, Any]] = {}

    for record in full68_eval.iter_manifest():
        gts = _gt_boxes(gt_root, record)
        control = _load_variant(control_root, record)
        fallback = _load_variant(fallback_root, record)
        control_result = _evaluate(control["finals"], gts)
        fallback_result = _evaluate(fallback["finals"], gts)
        page_cache[(record.score, record.page)] = {
            "record": record,
            "gts": gts,
            "control": control,
            "fallback": fallback,
            "control_result": control_result,
            "fallback_result": fallback_result,
        }

        for idx in control_result.false_negative_indices:
            control_fn.add((record.score, record.page, gts[idx]))
        for idx in fallback_result.false_negative_indices:
            gt = gts[idx]
            key = (record.score, record.page, gt)
            fallback_fn.add(key)
            final_details = _matching_final_details(
                fallback["finals"], gts, fallback_result, idx
            )
            classification = _classify_fn(
                gt=gt,
                candidates=fallback["candidates"],
                scored=fallback["scored"],
                matching_finals=final_details,
                threshold=threshold,
            )
            fn_rows.append(
                {
                    "score": record.score,
                    "page": record.page,
                    "gt_index": idx,
                    "gt_bbox": list(gt),
                    "classification": classification,
                    "also_d27_fn": key in d27_fns,
                    "matching_candidates": [
                        list(box) for box in fallback["candidates"] if _match(box, gt)
                    ],
                    "matching_scores": _matching_scores(fallback["scored"], gt),
                    "matching_finals": final_details,
                }
            )

        for pred_index in control_result.false_positive_indices:
            control_fp.add((record.score, record.page, control["finals"][pred_index]))
        for pred_index in fallback_result.false_positive_indices:
            fallback_fp.add((record.score, record.page, fallback["finals"][pred_index]))

    # D27 membership is authoritative only after the whole residual set is loaded.
    for row in fn_rows:
        key = (row["score"], row["page"], _norm(row["gt_bbox"]))
        row["also_d27_fn"] = key in d27_fns

    fp_rows: list[dict[str, Any]] = []
    fp_class_counts: Counter[str] = Counter()
    union_fp = sorted(control_fp | fallback_fp)
    for score, page, box in union_fp:
        cache = page_cache[(score, page)]
        record = cache["record"]
        control = cache["control"]
        fallback = cache["fallback"]
        in_control = (score, page, box) in control_fp
        in_fallback = (score, page, box) in fallback_fp
        in_d27 = (score, page, box) in d27_fps
        if in_control and in_fallback:
            classification = "shared_control_fallback_fp"
        elif in_fallback:
            classification = "fallback_only_fp"
        else:
            classification = "control_only_fp"
        fp_class_counts[classification] += 1

        control_hybrid = _load_hybrid_from_inventory(
            run_root, "control", score, page
        )
        fallback_hybrid = _load_hybrid_from_inventory(
            run_root, "x4_gap_fallback", score, page
        )
        fp_rows.append(
            {
                "score": score,
                "page": page,
                "bbox": list(box),
                "classification": classification,
                "also_d27_fp": in_d27,
                "control_score": _exact_score(control["scored"], box),
                "fallback_score": _exact_score(fallback["scored"], box),
                "control_stage_presence": _exact_stage_presence(
                    run_root, "control", record, box
                ),
                "fallback_stage_presence": _exact_stage_presence(
                    run_root, "x4_gap_fallback", record, box
                ),
                "nearest_promoted_x4_gap": _nearest_promoted(
                    control_hybrid, fallback_hybrid, box
                ),
            }
        )

    fn_counts = Counter(row["classification"] for row in fn_rows)
    result = {
        "schema_version": "issue372.retained_residual_details.v1",
        "d27_contract": {
            "summary": str(d27_summary_path),
            "expected": EXPECTED_D27,
            "actual": d27_clean,
            "reproduced": d27_gate,
            "fn_count": len(d27_fns),
            "fp_count": len(d27_fps),
        },
        "residual_sets": {
            "fn": {
                "d27_count": len(d27_fns),
                "control_count": len(control_fn),
                "fallback_count": len(fallback_fn),
                "fallback_new_vs_d27_count": len(fallback_fn - d27_fns),
                "fallback_persistent_d27_count": len(fallback_fn & d27_fns),
                "d27_recovered_by_fallback_count": len(d27_fns - fallback_fn),
                "classifications": dict(sorted(fn_counts.items())),
            },
            "fp": {
                "d27_count": len(d27_fps),
                "control_count": len(control_fp),
                "fallback_count": len(fallback_fp),
                "control_fallback_overlap_count": len(control_fp & fallback_fp),
                "fallback_only_count": len(fallback_fp - control_fp),
                "control_only_count": len(control_fp - fallback_fp),
                "fallback_overlap_d27_count": len(fallback_fp & d27_fps),
                "classifications": dict(sorted(fp_class_counts.items())),
            },
        },
        "fallback_fn_rows": fn_rows,
        "fp_union_rows": fp_rows,
        "d27_residuals": {
            "fn": [
                {"score": score, "page": page, "bbox": list(box)}
                for score, page, box in sorted(d27_fns)
            ],
            "fp": [
                {"score": score, "page": page, "bbox": list(box)}
                for score, page, box in sorted(d27_fps)
            ],
        },
    }
    _write_json(output, result)

    print("=== Issue #372 retained residual details ===")
    print(f"d27_reproduced={d27_gate} actual={d27_clean}")
    print(f"FN={result['residual_sets']['fn']}")
    print(f"FP={result['residual_sets']['fp']}")
    print(f"OUTPUT={output}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--d27-summary", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
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
