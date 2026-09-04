#!/usr/bin/env python3
"""Temporary Issue #296 audit of a clean-model veto cascade.

Diagnostic-only. Delete before PR preparation.

This does NOT fuse production and clean probabilities. Production acceptance is
kept as the first-stage set; the corrected-label clean model is evaluated only
as a second-stage veto. The script searches the full68 control-accepted set for
an actual score margin before any verifier threshold is proposed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

import tools.issue296.evaluate_clean_full68 as base

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CKPT = ROOT / "logs/cnn_barline_classification/issue296_clean_lineage_v7/cnn_classifier_best.pth"
OUT = ROOT / "logs/issue296/diagnostic_11_clean_veto_margin"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CKPT)
    args = parser.parse_args()
    checkpoint = args.checkpoint
    if not checkpoint.is_file():
        raise FileNotFoundError(checkpoint)
    if not base.RUN_ROOT.is_dir():
        raise FileNotFoundError(base.RUN_ROOT)

    OUT.mkdir(parents=True, exist_ok=True)
    model = base.get_model(checkpoint, "resnet18")
    gpu_norm = base.GPUNormalize(base.MEAN, base.STD).to(base.DEVICE)

    scored_paths = sorted(
        base.RUN_ROOT.glob(
            "runs/*/intermediate/dense_full_pipeline_route/"
            "dense_candidate_reconstruction/probe_rescue_candidates/"
            "eval2_*/pipeline2_no_peak_scored.json"
        )
    )
    if len(scored_paths) != 68:
        raise RuntimeError(f"expected 68 retained scored pages, got {len(scored_paths)}")

    pages = []
    hard_fp_scores = []
    low_rows = []
    all_control_scores = []
    target_score = None
    p007_scores = []

    for page_idx, scored_path in enumerate(scored_paths, 1):
        score, page = base.parse_context(scored_path)
        _, accepted_path = base.retained_paths(score, page)
        image = cv2.imread(str(base.IMAGE_ROOT / score / f"{page}.png"))
        if image is None:
            raise FileNotFoundError(base.IMAGE_ROOT / score / f"{page}.png")

        candidates = base.extract_boxes(base.load_json(scored_path))
        control = base.extract_boxes(base.load_json(accepted_path))
        truths = base.gt_boxes(score, page)
        clean_scores = base.score_boxes(image, candidates, model, gpu_norm)

        score_by_box = {}
        for box, value in zip(candidates, clean_scores):
            score_by_box.setdefault(box, value)
        missing = [box for box in control if box not in score_by_box]
        if missing:
            raise RuntimeError(f"control boxes missing from scored candidates for {score}/{page}: {missing}")
        control_scores = [float(score_by_box[box]) for box in control]
        all_control_scores.extend(control_scores)

        control_eval = base.evaluate(control, truths)
        hard_indices = set(control_eval.false_positive_indices)
        for idx, (box, value) in enumerate(zip(control, control_scores)):
            is_target = score == base.TARGET_SCORE and page == base.TARGET_PAGE and box == base.TARGET
            is_p007 = score == base.TARGET_SCORE and page == "page_007" and box in base.P007
            if idx in hard_indices:
                hard_fp_scores.append({
                    "score": score,
                    "page": page,
                    "bbox": list(box),
                    "clean_score": value,
                    "target": is_target,
                    "p007_known_fp": is_p007,
                })
            if is_target:
                target_score = value
            if is_p007:
                p007_scores.append(value)
            if value <= 0.01:
                low_rows.append({
                    "score": score,
                    "page": page,
                    "bbox": list(box),
                    "clean_score": value,
                    "control_hard_fp": idx in hard_indices,
                    "target": is_target,
                    "p007_known_fp": is_p007,
                })

        pages.append({
            "score": score,
            "page": page,
            "truths": truths,
            "control": control,
            "control_scores": control_scores,
            "p3_pairs": base.p3_pairs_for_page(score, page),
        })
        print(f"[{page_idx:02d}/68] {score}/{page}: control={len(control)}")

    if target_score is None or len(p007_scores) != 2:
        raise RuntimeError(f"known FP score preflight failed: target={target_score}, p007={p007_scores}")

    # The decision only changes when the threshold reaches one of the scores of
    # a currently accepted candidate. Restrict to <=0.1 because the clean-only
    # full68 audit already showed regressions at 0.1; this is a veto-margin audit,
    # not a broad threshold optimization.
    thresholds = sorted({0.0, *[s for s in all_control_scores if s <= 0.1]})
    rows = []
    expected = base.EXPECTED_CONTROL

    for threshold in thresholds:
        tp = hard_fp = fn = soft = 0
        p3_complete = 0
        target_present = False
        p007_present = 0
        for rec in pages:
            cascade = [
                box
                for box, value in zip(rec["control"], rec["control_scores"])
                if value > threshold
            ]
            ev = base.evaluate(cascade, rec["truths"])
            tp += len(ev.matches)
            hard_fp += len(ev.false_positive_indices)
            fn += len(ev.false_negative_indices)
            soft += len(ev.soft_matches)

            if rec["score"] == base.TARGET_SCORE and rec["page"] == base.TARGET_PAGE:
                target_present = base.TARGET in cascade
            if rec["score"] == base.TARGET_SCORE and rec["page"] == "page_007":
                p007_present = sum(1 for box in base.P007 if box in cascade)

            for pair in rec["p3_pairs"]:
                a = tuple(pair["a"])
                b = tuple(pair["b"])
                if base.matches_any(cascade, a) and base.matches_any(cascade, b):
                    p3_complete += 1

        safe = (
            not target_present
            and tp == expected["tp"]
            and fn == expected["fn"]
            and hard_fp <= 2
            and p3_complete == 51
        )
        rows.append({
            "threshold": threshold,
            "tp": tp,
            "hard_fp": hard_fp,
            "fn": fn,
            "soft": soft,
            "p3_complete_pairs": p3_complete,
            "target_present": target_present,
            "p007_present_count": p007_present,
            "safe_target_veto": safe,
            "zero_hard_fp_without_regression": safe and hard_fp == 0,
        })

    safe_rows = [r for r in rows if r["safe_target_veto"]]
    zero_rows = [r for r in rows if r["zero_hard_fp_without_regression"]]
    regression_rows = [
        r for r in rows
        if r["tp"] < expected["tp"] or r["fn"] > expected["fn"] or r["p3_complete_pairs"] < 51
    ]

    hard_fp_scores.sort(key=lambda r: r["clean_score"])
    low_rows.sort(key=lambda r: r["clean_score"])
    payload = {
        "schema_version": "issue296.clean_veto_margin.v1",
        "checkpoint": str(checkpoint),
        "decision_form": "production_accept AND clean_score > verifier_threshold",
        "probability_fusion": False,
        "expected_control": expected,
        "target_clean_score": target_score,
        "p007_clean_scores": sorted(p007_scores),
        "control_hard_fp_clean_scores": hard_fp_scores,
        "safe_threshold_exists": bool(safe_rows),
        "safe_threshold_min": safe_rows[0]["threshold"] if safe_rows else None,
        "safe_threshold_max": safe_rows[-1]["threshold"] if safe_rows else None,
        "zero_hard_fp_threshold_exists": bool(zero_rows),
        "zero_hard_fp_threshold_min": zero_rows[0]["threshold"] if zero_rows else None,
        "zero_hard_fp_threshold_max": zero_rows[-1]["threshold"] if zero_rows else None,
        "first_regression_threshold": regression_rows[0]["threshold"] if regression_rows else None,
        "low_score_control_candidates_le_0p01": low_rows,
        "threshold_rows": rows,
        "notes": {
            "diagnostic_only": True,
            "no_threshold_selected_for_production": True,
            "no_old_clean_probability_average": True,
            "cascade_can_only_remove_first_stage_acceptances": True,
        },
    }
    out = OUT / "clean_veto_margin.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "target_clean_score": target_score,
        "control_hard_fp_clean_scores": hard_fp_scores,
        "safe_threshold_exists": payload["safe_threshold_exists"],
        "safe_threshold_min": payload["safe_threshold_min"],
        "safe_threshold_max": payload["safe_threshold_max"],
        "zero_hard_fp_threshold_exists": payload["zero_hard_fp_threshold_exists"],
        "zero_hard_fp_threshold_min": payload["zero_hard_fp_threshold_min"],
        "zero_hard_fp_threshold_max": payload["zero_hard_fp_threshold_max"],
        "first_regression_threshold": payload["first_regression_threshold"],
        "low_score_candidate_count": len(low_rows),
        "result": str(out),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
