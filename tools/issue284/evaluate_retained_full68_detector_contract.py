"""Evaluate retained Issue #284 full-68 runs at the final Stage E detector boundary.

Unlike ``compare_full68_variants.py``'s upstream hybrid comparison, this tool
reads the post-dense-reconstruction/post-probe/post-CNN
``pipeline2_no_peak_scored.json`` artifacts and evaluates them with the accepted
Issue #255 detector contract:

GT=3580, Pred=3600, TP=3579, FP=1, FN=1, FN_det=0, FN_cnn=1.

No inference is performed; only retained artifacts are read.
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

from src.common.barline_evaluation import greedy_barline_match
from src.pipeline.core.run_ids import build_probe_run_id_from_parts
from tools.issue120.eval_full68_from_intermediates import (
    SCORES,
    boxes_from_candidates,
    boxes_from_gt,
    boxes_from_scored,
    has_candidate_for_gt,
)

SCORE_THRESHOLD = 0.1
RULE_NAME = "center_anchor"
VOV_THRESHOLD = 0.5
XDIST_THRESHOLD = 12.0
ACCEPTED = {
    "gt": 3580,
    "pred": 3600,
    "tp": 3579,
    "fp": 1,
    "fn": 1,
    "fn_det": 0,
    "fn_cnn": 1,
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def score_map(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["score"]): item for item in summary.get("scores", [])}


def detector_dir(summary: dict[str, Any], score: str, page: str) -> Path:
    score_item = score_map(summary)[score]
    pipeline_run = Path(str(score_item["pipeline_run"]))
    run_id = build_probe_run_id_from_parts(score, page)
    return (
        pipeline_run
        / "intermediate"
        / "dense_full_pipeline_route"
        / "dense_candidate_reconstruction"
        / "probe_rescue_candidates"
        / run_id
    )


def evaluate_variant(root: Path) -> dict[str, Any]:
    summary_path = root / "variant_summary.json"
    summary = load_json(summary_path)
    if summary.get("status") != "completed" or summary.get("canonical_page_count") != 68:
        raise RuntimeError(f"Variant is not a completed canonical full68 run: {summary_path}")

    page_rows: list[dict[str, Any]] = []
    totals = {key: 0 for key in ACCEPTED}
    selected_by_page: dict[tuple[str, str], list[tuple[int, int, int, int]]] = {}

    for score, pages in SCORES.items():
        for page in pages:
            run_dir = detector_dir(summary, score, page)
            scored_path = run_dir / "pipeline2_no_peak_scored.json"
            candidates_path = run_dir / "pipeline2_no_peak_candidates.json"
            gt_path = PROJECT_ROOT / "data/evaluation2/annotations" / score / page / "boxes_sorted.json"
            for path in (scored_path, candidates_path, gt_path):
                if not path.is_file():
                    raise FileNotFoundError(path)

            gt = boxes_from_gt(load_json(gt_path))
            pred = boxes_from_scored(load_json(scored_path), score_threshold=SCORE_THRESHOLD)
            candidates = boxes_from_candidates(load_json(candidates_path))
            selected_by_page[(score, page)] = pred

            matched = greedy_barline_match(
                pred,
                gt,
                rule_name=RULE_NAME,
                vov_threshold=VOV_THRESHOLD,
                xdist_threshold=XDIST_THRESHOLD,
            )
            fn_det = 0
            fn_cnn = 0
            for gt_index in matched.false_negative_indices:
                if has_candidate_for_gt(
                    candidates,
                    gt[gt_index],
                    rule_name=RULE_NAME,
                    vov_threshold=VOV_THRESHOLD,
                    xdist_threshold=XDIST_THRESHOLD,
                ):
                    fn_cnn += 1
                else:
                    fn_det += 1

            row = {
                "score": score,
                "page": page,
                "gt": len(gt),
                "pred": len(pred),
                "tp": len(matched.matches),
                "fp": len(matched.false_positive_indices),
                "fn": len(matched.false_negative_indices),
                "fn_det": fn_det,
                "fn_cnn": fn_cnn,
                "scored": str(scored_path),
                "candidates": str(candidates_path),
            }
            page_rows.append(row)
            for key in totals:
                totals[key] += int(row[key])

    totals["precision"] = totals["tp"] / (totals["tp"] + totals["fp"])
    totals["recall"] = totals["tp"] / (totals["tp"] + totals["fn"])
    target_mismatches = {
        key: {"accepted": expected, "actual": totals[key]}
        for key, expected in ACCEPTED.items()
        if totals[key] != expected
    }
    return {
        "root": str(root),
        "git_commit": summary.get("git_commit"),
        "metrics": totals,
        "accepted_target_met": not target_mismatches,
        "target_mismatches": target_mismatches,
        "pages": page_rows,
        "selected_by_page": selected_by_page,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    control = evaluate_variant(args.control.resolve())
    candidate = evaluate_variant(args.candidate.resolve())

    exact_pages = 0
    changed_pages: list[dict[str, Any]] = []
    for score, pages in SCORES.items():
        for page in pages:
            key = (score, page)
            control_boxes = control["selected_by_page"][key]
            candidate_boxes = candidate["selected_by_page"][key]
            if control_boxes == candidate_boxes:
                exact_pages += 1
            else:
                changed_pages.append(
                    {
                        "score": score,
                        "page": page,
                        "control_count": len(control_boxes),
                        "candidate_count": len(candidate_boxes),
                    }
                )

    # Internal-only structures are not JSON serializable and are no longer needed.
    control.pop("selected_by_page")
    candidate.pop("selected_by_page")

    payload = {
        "schema_version": "issue284.retained_full68_final_detector_contract.v1",
        "evaluation_contract": {
            "score_threshold": SCORE_THRESHOLD,
            "rule_name": RULE_NAME,
            "vov_threshold": VOV_THRESHOLD,
            "xdist_threshold": XDIST_THRESHOLD,
            "accepted": ACCEPTED,
        },
        "control": control,
        "candidate": candidate,
        "final_detector_exact_pages": exact_pages,
        "final_detector_changed_pages": changed_pages,
        "gate": {
            "control_accepted_target_met": control["accepted_target_met"],
            "candidate_accepted_target_met": candidate["accepted_target_met"],
            "candidate_preserves_control_exactly": exact_pages == 68,
        },
    }
    payload["gate"]["passed"] = all(payload["gate"].values())

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    compact = {
        "control_metrics": control["metrics"],
        "candidate_metrics": candidate["metrics"],
        "control_accepted_target_met": control["accepted_target_met"],
        "candidate_accepted_target_met": candidate["accepted_target_met"],
        "final_detector_exact_pages": exact_pages,
        "final_detector_changed_page_count": len(changed_pages),
        "gate": payload["gate"],
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0 if payload["gate"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
