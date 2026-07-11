#!/usr/bin/env python3
"""Score and evaluate Issue #244 hybrid-prediction/staff-mask cross variants."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch
from tools.issue244.compare_full68_route_artifacts import (
    canonical_records,
    resolve_path,
)

CROSS_ROOT = Path("logs/issue244_full_regression/hybrid_mask_cross")
REPORT = Path("logs/issue244_full_regression/full68_hybrid_mask_cross_cnn_report.json")
MODEL_PATH = Path(
    "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/"
    "cnn_classifier_best.pth"
)
HISTORICAL_EVAL = Path(
    "logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector/"
    "evaluation_contract.json"
)
CURRENT_EVAL = Path(
    "logs/issue244_full_regression/detector_eval/evaluation_contract.json"
)
VARIANTS = (
    "C_historical_pred_current_mask",
    "D_current_pred_historical_mask",
)


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def detector_summary(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    summary = payload.get("detector_summary")
    if not isinstance(summary, dict):
        raise ValueError(f"No detector_summary in {path}")
    return summary


def score_variant(label: str, images: list[Path], *, reuse: bool) -> Path:
    variant_root = CROSS_ROOT / label
    dense_root = variant_root / "dense_candidate_reconstruction"
    candidates_root = dense_root / "probe_rescue_candidates"
    bands_root = dense_root / "probe_candidates_filtered"
    scored_root = variant_root / "cnn_scored"
    eval_root = variant_root / "cnn_eval"

    if not reuse:
        if not candidates_root.exists() or not bands_root.exists():
            raise FileNotFoundError(
                f"Cross candidate artifacts are missing for {label}. "
                "Run run_full68_hybrid_mask_cross.sh first."
            )
        shutil.rmtree(scored_root, ignore_errors=True)
        shutil.copytree(candidates_root, scored_root)
        processed = run_cnn_scoring_batch(
            probe_output_root=scored_root,
            images=images,
            model_path=MODEL_PATH,
            threshold=0.1,
            crop_recenter_on_bbox_ink=True,
            input_image_scale=1.0,
            bands_from=bands_root,
            staff_vov_threshold=0.5,
            apply_nms_enabled=False,
        )
        if processed != len(images):
            raise RuntimeError(
                f"CNN scoring processed {processed}/{len(images)} pages for {label}"
            )

    scored_files = list(scored_root.glob("*/pipeline2_no_peak_scored.json"))
    if len(scored_files) != len(images):
        raise RuntimeError(
            f"Expected {len(images)} scored files for {label}, got {len(scored_files)}"
        )

    shutil.rmtree(eval_root, ignore_errors=True)
    subprocess.run(
        [
            sys.executable,
            "tools/issue120/eval_full68_from_intermediates.py",
            "--results-dir",
            str(scored_root),
            "--output-dir",
            str(eval_root),
            "--score-threshold",
            "0.1",
            "--xdist-threshold",
            "12.0",
        ],
        check=True,
    )
    return eval_root / "evaluation_contract.json"


def summary_distance(
    summary: dict[str, Any], historical: dict[str, Any]
) -> dict[str, int]:
    return {
        "tp_delta": int(summary["tp"]) - int(historical["tp"]),
        "fp_delta": int(summary["fp"]) - int(historical["fp"]),
        "fn_delta": int(summary["fn"]) - int(historical["fn"]),
        "fn_det_delta": int(summary["fn_det"]) - int(historical["fn_det"]),
        "fn_cnn_delta": int(summary["fn_cnn"]) - int(historical["fn_cnn"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reuse-scored",
        action="store_true",
        help="Reuse existing C/D CNN scored artifacts and only rerun evaluation.",
    )
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()

    records = canonical_records()
    images = [resolve_path(str(record["image"])) for record in records]
    missing_images = [str(path) for path in images if not path.exists()]
    if missing_images:
        raise FileNotFoundError(
            "Missing canonical images:\n" + "\n".join(missing_images)
        )

    historical = detector_summary(HISTORICAL_EVAL)
    current = detector_summary(CURRENT_EVAL)
    summaries: dict[str, dict[str, Any]] = {
        "A_historical": historical,
        "B_current": current,
    }

    eval_paths: dict[str, str] = {
        "A_historical": str(HISTORICAL_EVAL),
        "B_current": str(CURRENT_EVAL),
    }
    for label in VARIANTS:
        eval_path = score_variant(label, images, reuse=args.reuse_scored)
        eval_paths[label] = str(eval_path)
        summaries[label] = detector_summary(eval_path)

    cross_ranking = sorted(
        VARIANTS,
        key=lambda label: (
            int(summaries[label]["fn"]),
            int(summaries[label]["fp"]),
            -int(summaries[label]["tp"]),
        ),
    )
    report = {
        "schema": "issue244.full68_hybrid_mask_cross_cnn.v1",
        "page_count": len(images),
        "model_path": str(MODEL_PATH),
        "cnn_contract": {
            "threshold": 0.1,
            "crop_recenter_on_bbox_ink": True,
            "input_image_scale": 1.0,
            "staff_vov_threshold": 0.5,
            "apply_nms_enabled": False,
            "bands_source": "variant probe_candidates_filtered",
            "candidate_source": "variant probe_rescue_candidates",
        },
        "evaluation_paths": eval_paths,
        "summaries": summaries,
        "differences_from_A_historical": {
            label: summary_distance(summary, historical)
            for label, summary in summaries.items()
            if label != "A_historical"
        },
        "cross_variant_ranking": cross_ranking,
        "preferred_cross_variant": cross_ranking[0],
        "note": (
            "Candidate symmetric difference is diagnostic only. Final selection must "
            "use detector TP/FP/FN after CNN scoring."
        ),
    }
    write_json(args.report, report)

    print("Issue #244 cross-variant CNN evaluation")
    for label, summary in summaries.items():
        print(
            f"  {label}: GT={summary['gt']} Pred={summary['pred']} "
            f"TP={summary['tp']} FP={summary['fp']} FN={summary['fn']} "
            f"FN_det={summary['fn_det']} FN_cnn={summary['fn_cnn']}"
        )
    print(f"Preferred cross variant: {cross_ranking[0]}")
    print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
