#!/usr/bin/env python3
"""Temporary retained-artifact analysis for Issue #284 FN match competition.

This script is read-only. It does not run the pipeline or load GPU models. It
re-evaluates the accepted/current Stage E outputs and explains why each current
FN remains unmatched even when a final prediction satisfies the center-anchor
rule. The file is intentionally temporary and must be removed before PR.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.barline_evaluation import (  # noqa: E402
    barline_iou,
    barline_vertical_overlap,
    center_distance_x,
    get_barline_match_rank,
    is_barline_match,
)
from tools.issue120.eval_full68_from_intermediates import (  # noqa: E402
    SCORES,
    boxes_from_candidates,
    boxes_from_scored,
)
from tools.issue284.diagnose_stage_e_fn_regression import (  # noqa: E402
    RULE_NAME,
    SCORE_THRESHOLD,
    VOV_THRESHOLD,
    XDIST_THRESHOLD,
    evaluate_run,
    load_json,
)

STAGES = (
    "dense_raw",
    "dense_filtered",
    "probe_rescue_candidates",
    "pipeline_candidates",
    "final_predictions",
)


def matches(pred: tuple[int, int, int, int], gt: tuple[int, int, int, int]) -> bool:
    return is_barline_match(
        pred,
        gt,
        rule_name=RULE_NAME,
        vov_threshold=VOV_THRESHOLD,
        xdist_threshold=XDIST_THRESHOLD,
    )


def metrics(pred: tuple[int, int, int, int], gt: tuple[int, int, int, int]) -> dict[str, Any]:
    return {
        "box": list(pred),
        "vov": barline_vertical_overlap(pred, gt),
        "xdist": center_distance_x(pred, gt),
        "iou": barline_iou(pred, gt),
        "rank": list(get_barline_match_rank(pred, gt, RULE_NAME)),
    }


def stage_boxes(page_data: dict[str, Any], stage: str) -> list[tuple[int, int, int, int]]:
    if stage == "dense_raw":
        path = page_data["reconstruction"]["dense_raw"]
        return boxes_from_candidates(load_json(path)) if path and path.is_file() else []
    if stage == "dense_filtered":
        path = page_data["reconstruction"]["dense_filtered"]
        return boxes_from_candidates(load_json(path)) if path and path.is_file() else []
    if stage == "probe_rescue_candidates":
        path = page_data["reconstruction"]["probe_rescue_candidates"]
        return boxes_from_candidates(load_json(path)) if path and path.is_file() else []
    if stage == "pipeline_candidates":
        path = page_data["candidates_path"]
        return boxes_from_candidates(load_json(path)) if path.is_file() else []
    if stage == "final_predictions":
        path = page_data["final_path"]
        return boxes_from_scored(load_json(path), score_threshold=SCORE_THRESHOLD) if path.is_file() else []
    raise ValueError(stage)


def target_match_set(page_data: dict[str, Any], gt: tuple[int, int, int, int], stage: str) -> dict[str, Any]:
    boxes = stage_boxes(page_data, stage)
    rows = [metrics(box, gt) for box in boxes if matches(box, gt)]
    rows.sort(key=lambda row: (row["xdist"], -row["vov"], -row["iou"], row["box"]))
    return {
        "stage": stage,
        "total_boxes": len(boxes),
        "matching_count": len(rows),
        "exact_gt_geometry_count": sum(row["box"] == list(gt) for row in rows),
        "matching": rows,
    }


def page_match_summary(page_data: dict[str, Any]) -> dict[str, Any]:
    matched = page_data["matched"]
    pred_count = len(page_data["pred"])
    tp = len(matched.matches)
    fp = len(matched.false_positive_indices)
    soft = len(matched.soft_matches)
    return {
        "gt": len(page_data["gt"]),
        "pred": pred_count,
        "tp": tp,
        "fp": fp,
        "fn": len(matched.false_negative_indices),
        "soft": soft,
        "accounting_ok": pred_count == tp + fp + soft,
        "false_negative_indices": list(matched.false_negative_indices),
        "soft_matches": [
            {
                "pred_index": item.pred_index,
                "gt_index": item.gt_index,
                "reason": item.reason,
                "iou": item.iou,
                "xdist": item.x_distance,
                "vov": item.vertical_overlap,
            }
            for item in matched.soft_matches
        ],
    }


def explain_assignment(page_data: dict[str, Any], gt_idx: int) -> dict[str, Any]:
    gt = page_data["gt"][gt_idx]
    pred = page_data["pred"]
    matched = page_data["matched"]
    by_pred = {item.pred_index: item for item in matched.matches}
    soft_by_pred = {item.pred_index: item for item in matched.soft_matches}

    matching_pred_indices = [idx for idx, box in enumerate(pred) if matches(box, gt)]
    rows: list[dict[str, Any]] = []
    for pred_idx in matching_pred_indices:
        box = pred[pred_idx]
        row: dict[str, Any] = {
            "pred_index": pred_idx,
            "target_gt_index": gt_idx,
            "target_gt_box": list(gt),
            "prediction": metrics(box, gt),
            "status": "unaccounted",
        }
        assigned = by_pred.get(pred_idx)
        if assigned is not None:
            assigned_gt = page_data["gt"][assigned.gt_index]
            row.update(
                {
                    "status": "assigned",
                    "assigned_gt_index": assigned.gt_index,
                    "assigned_gt_box": list(assigned_gt),
                    "assigned_metrics": metrics(box, assigned_gt),
                    "assigned_to_target": assigned.gt_index == gt_idx,
                }
            )
        else:
            soft = soft_by_pred.get(pred_idx)
            if soft is not None:
                row.update(
                    {
                        "status": "soft",
                        "soft_reason": soft.reason,
                        "soft_gt_index": soft.gt_index,
                    }
                )
            elif pred_idx in matched.false_positive_indices:
                row["status"] = "false_positive"
        rows.append(row)

    rows.sort(
        key=lambda row: (
            row["prediction"]["xdist"],
            -row["prediction"]["vov"],
            -row["prediction"]["iou"],
            row["pred_index"],
        )
    )

    if gt_idx not in matched.false_negative_indices:
        reason = "target_is_matched"
    elif not rows:
        reason = "no_final_prediction_matches_target"
    elif all(row["status"] == "assigned" and not row.get("assigned_to_target") for row in rows):
        reason = "all_matching_predictions_assigned_to_other_gt"
    else:
        reason = "matching_prediction_exists_but_target_unmatched_other"

    return {
        "gt_index": gt_idx,
        "gt_box": list(gt),
        "is_false_negative": gt_idx in matched.false_negative_indices,
        "matching_prediction_count": len(rows),
        "reason": reason,
        "matching_predictions": rows,
    }


def first_match_set_divergence(
    accepted_page: dict[str, Any],
    current_page: dict[str, Any],
    gt: tuple[int, int, int, int],
) -> dict[str, Any] | None:
    for stage in STAGES:
        a = target_match_set(accepted_page, gt, stage)
        c = target_match_set(current_page, gt, stage)
        a_boxes = [row["box"] for row in a["matching"]]
        c_boxes = [row["box"] for row in c["matching"]]
        if a_boxes != c_boxes:
            return {
                "stage": stage,
                "accepted_matching_count": a["matching_count"],
                "current_matching_count": c["matching_count"],
                "accepted_matching_boxes": a_boxes,
                "current_matching_boxes": c_boxes,
            }
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-root", type=Path, required=True)
    parser.add_argument("--current-root", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("logs/issue284/issue284_fn_match_competition.json"),
    )
    args = parser.parse_args()

    accepted = evaluate_run(args.accepted_root.resolve())
    current = evaluate_run(args.current_root.resolve())
    accepted_pages = accepted["_pages"]
    current_pages = current["_pages"]

    items: list[dict[str, Any]] = []
    seen_pages: set[tuple[str, str]] = set()
    page_summaries: list[dict[str, Any]] = []

    for score, pages in SCORES.items():
        for page in pages:
            key = (score, page)
            apage = accepted_pages.get(key)
            cpage = current_pages.get(key)
            if apage is None or cpage is None:
                continue
            accepted_fn = set(apage["matched"].false_negative_indices)
            for gt_idx in cpage["matched"].false_negative_indices:
                gt = cpage["gt"][gt_idx]
                accepted_gt = apage["gt"][gt_idx] if gt_idx < len(apage["gt"]) else None
                classification = (
                    "accepted_residual"
                    if accepted_gt == gt and gt_idx in accepted_fn
                    else "regression"
                )
                item = {
                    "classification": classification,
                    "score": score,
                    "page": page,
                    "gt_index": gt_idx,
                    "gt_box": list(gt),
                    "first_target_match_set_divergence": first_match_set_divergence(apage, cpage, gt),
                    "accepted_assignment": explain_assignment(apage, gt_idx),
                    "current_assignment": explain_assignment(cpage, gt_idx),
                    "stages": {
                        stage: {
                            "accepted": target_match_set(apage, gt, stage),
                            "current": target_match_set(cpage, gt, stage),
                        }
                        for stage in STAGES
                    },
                }
                items.append(item)
                if key not in seen_pages:
                    seen_pages.add(key)
                    page_summaries.append(
                        {
                            "score": score,
                            "page": page,
                            "accepted": page_match_summary(apage),
                            "current": page_match_summary(cpage),
                        }
                    )

    payload = {
        "schema_version": "issue284.fn_match_competition.v1",
        "read_only": True,
        "evaluation_contract": {
            "score_threshold": SCORE_THRESHOLD,
            "rule_name": RULE_NAME,
            "vov_threshold": VOV_THRESHOLD,
            "xdist_threshold": XDIST_THRESHOLD,
        },
        "classification_counts": {
            "current_fn": len(items),
            "accepted_residual": sum(item["classification"] == "accepted_residual" for item in items),
            "regression": sum(item["classification"] == "regression" for item in items),
        },
        "page_summaries": page_summaries,
        "false_negatives": items,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    compact = {
        "classification_counts": payload["classification_counts"],
        "pages": [
            {
                "score": row["score"],
                "page": row["page"],
                "accepted": {key: row["accepted"][key] for key in ("pred", "tp", "fp", "fn", "soft")},
                "current": {key: row["current"][key] for key in ("pred", "tp", "fp", "fn", "soft")},
            }
            for row in page_summaries
        ],
        "false_negatives": [
            {
                "classification": item["classification"],
                "score": item["score"],
                "page": item["page"],
                "gt_index": item["gt_index"],
                "accepted_reason": item["accepted_assignment"]["reason"],
                "current_reason": item["current_assignment"]["reason"],
                "current_matching_prediction_count": item["current_assignment"]["matching_prediction_count"],
                "first_target_match_set_divergence": item["first_target_match_set_divergence"],
            }
            for item in items
        ],
        "output": str(args.output),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
