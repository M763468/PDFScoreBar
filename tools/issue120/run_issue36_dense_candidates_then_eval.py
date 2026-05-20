#!/usr/bin/env python3
"""Diagnostic direct-score wrapper for Issue #36 dense candidates.

This is retained as a compatibility/diagnostic wrapper for #149/#151.  The
accepted production-style detector route is
``python -m src.pipeline.detector_routes.dense_probe_candidate_route`` and uses
the Issue36 filtered root as probe-rescue ``bands_from`` before scoring.

This direct-score wrapper is intentionally narrow:

    inventory -> dense raw candidates -> clef-mask-aware filter
      -> candidate-root comparison gates -> current CNN scoring
      -> #134 full-68 detector evaluator

It does not change general pipeline defaults and does not run the full slow
HOMR/SR/OMR pipeline.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue120.eval_full68_from_intermediates import iter_manifest  # noqa: E402

DEFAULT_MODEL = Path(
    "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
)
DEFAULT_OUTPUT_ROOT = Path("logs/issue120_e2e_recovery/stage_d_issue36_dense_candidate_validation")
DEFAULT_HISTORICAL_RAW = Path("logs/issue36_prep/probe_candidates_from_bench_v12")
DEFAULT_HISTORICAL_FILTERED = Path("logs/issue36_prep/probe_candidates_filtered_v12")
DEFAULT_HISTORICAL_SCORING_INPUT = Path(
    "logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12"
)
TARGET_DETECTOR = {"tp": 3580, "fp": 0, "fn": 1}

GENERATION_PARAMS = {
    "band_source": "row_stats",
    "band_cluster_max_dist": "25.0",
    "ink_threshold": "240",
    "min_ratio": "0.6",
    "min_height_ratio": "0.006",
    "min_width_ratio": "0.0",
    "probe_width": "4",
    "max_per_band": "80",
    "band_scan_line_ratio": "0.6",
    "band_scan_min_lines": "5",
}

FILTER_PARAMS = {
    "left_margin_ratio": "0.12",
    "clef_left_ratio": "0.25",
    "min_height_median_ratio": "0.6",
    "ink_threshold": "180",
    "min_ink_ratio": "0.18",
    "paper_threshold": "200",
    "min_paper_overlap_ratio": "0.6",
    "min_staff_overlap_ratio": "0.02",
}


def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def run(cmd: list[str]) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def add_param_args(cmd: list[str], params: dict[str, str]) -> None:
    for key, value in params.items():
        cmd.extend([f"--{key.replace('_', '-')}", value])


def candidate_root_summary(root: Path) -> dict[str, int | str | bool]:
    files = sorted(root.rglob("pipeline2_no_peak_candidates.json")) if root.exists() else []
    total_candidates = 0
    unreadable = 0
    for path in files:
        try:
            payload = load_json(path)
        except (json.JSONDecodeError, OSError):
            unreadable += 1
            continue
        if isinstance(payload, list):
            total_candidates += len(payload)
    return {
        "root": str(root),
        "exists": root.exists(),
        "files": len(files),
        "total_candidates": total_candidates,
        "unreadable": unreadable,
    }


def load_optional_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return load_json(path)


def detector_summary(eval_dir: Path) -> dict[str, Any] | None:
    for name in ["detector_metrics.json", "evaluation_contract.json"]:
        path = eval_dir / name
        if not path.exists():
            continue
        payload = load_json(path)
        if name == "evaluation_contract.json":
            return payload.get("detector_summary")
        return payload
    return None


def build_generation_command(args: argparse.Namespace) -> list[str]:
    cmd = [
        sys.executable,
        "tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py",
        "--inventory",
        str(args.inventory),
        "--exclude",
        str(args.exclude),
        "--output-root",
        str(args.raw_candidates_root),
        "--summary-out",
        str(args.generation_summary),
    ]
    add_param_args(cmd, GENERATION_PARAMS)
    return cmd


def build_filter_command(args: argparse.Namespace) -> list[str]:
    cmd = [
        sys.executable,
        "tools/verification/gt_preparation/apply_candidate_filter_from_inventory.py",
        "--inventory",
        str(args.inventory),
        "--exclude",
        str(args.exclude),
        "--candidates-root",
        str(args.raw_candidates_root),
        "--output-root",
        str(args.filtered_candidates_root),
        "--suggestions-root",
        str(args.suggestions_root),
        "--summary-out",
        str(args.filter_summary),
    ]
    add_param_args(cmd, FILTER_PARAMS)
    return cmd


def build_compare_command(*, left: Path, right: Path, output_dir: Path) -> list[str]:
    return [
        sys.executable,
        "tools/issue120/compare_filter_candidate_deltas.py",
        "--historical-dir",
        str(left),
        "--repro-dir",
        str(right),
        "--output-dir",
        str(output_dir),
    ]


def build_score_command(args: argparse.Namespace) -> list[str]:
    cmd = [
        sys.executable,
        "tools/issue120/score_candidates_then_eval_full68.py",
        "--scorer",
        args.scorer,
        "--candidates-dir",
        str(args.filtered_candidates_root),
        "--image-root",
        str(args.image_root),
        "--gt-root",
        str(args.gt_root),
        "--model-path",
        str(args.model_path),
        "--scoring-output-dir",
        str(args.scoring_output_dir),
        "--eval-output-dir",
        str(args.eval_output_dir),
        "--score-threshold",
        str(args.score_threshold),
        "--xdist-threshold",
        str(args.xdist_threshold),
        "--bands-from",
        str(args.filtered_candidates_root),
    ]
    if args.clean_output:
        cmd.append("--clean-output")
    if args.scorer == "pipeline" and not args.pipeline_nms:
        cmd.append("--disable-pipeline-nms")
    return cmd


def comparison_summary(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = load_json(path)
    return payload.get("summary", payload)


def assert_candidate_match(summary: dict[str, Any] | None, *, label: str) -> None:
    if summary is None:
        raise RuntimeError(f"{label} comparison summary missing")
    checks = {
        "missing_historical_pages": summary.get("missing_historical_pages"),
        "missing_repro_pages": summary.get("missing_repro_pages"),
        "mismatch_pages": summary.get("mismatch_pages"),
        "total_extra_in_repro": summary.get("total_extra_in_repro"),
        "total_missing_from_repro": summary.get("total_missing_from_repro"),
    }
    if any(value != 0 for value in checks.values()):
        raise RuntimeError(f"{label} candidate-root mismatch: {checks}")


def validate_complete_contract(eval_dir: Path) -> None:
    contract_path = eval_dir / "evaluation_contract.json"
    if not contract_path.exists():
        raise FileNotFoundError(f"evaluation_contract.json not found: {contract_path}")
    contract = load_json(contract_path)
    expected = contract.get("expected_pages")
    evaluated = contract.get("evaluated_pages")
    missing = contract.get("missing_pages", [])
    expected_count = len(iter_manifest())
    if expected != expected_count or evaluated != expected_count or missing:
        raise RuntimeError(
            "Incomplete Issue #120 full-68 evaluation contract: "
            f"expected_pages={expected} evaluated_pages={evaluated} "
            f"expected_count={expected_count} missing_pages={len(missing)}"
        )


def validate_detector_target(eval_dir: Path) -> None:
    summary = detector_summary(eval_dir)
    if summary is None:
        raise FileNotFoundError(f"Detector metrics not found under {eval_dir}")
    observed = {"tp": summary.get("tp"), "fp": summary.get("fp"), "fn": summary.get("fn")}
    if observed != TARGET_DETECTOR:
        raise RuntimeError(f"Detector target mismatch: observed={observed} target={TARGET_DETECTOR}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path("logs/issue36_prep/20260208_bench_inventory.json"))
    parser.add_argument("--exclude", type=Path, default=Path("logs/issue36_prep/excluded_pages_for_gt_prep.json"))
    parser.add_argument("--image-root", type=Path, default=Path("data/evaluation2/images"))
    parser.add_argument("--gt-root", type=Path, default=Path("data/evaluation2/annotations"))
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--historical-raw-candidates-root", type=Path, default=DEFAULT_HISTORICAL_RAW)
    parser.add_argument("--historical-filtered-candidates-root", type=Path, default=DEFAULT_HISTORICAL_FILTERED)
    parser.add_argument("--historical-scoring-input-root", type=Path, default=DEFAULT_HISTORICAL_SCORING_INPUT)
    parser.add_argument("--score-threshold", type=float, default=0.1)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    parser.add_argument("--scorer", choices=["pipeline", "legacy"], default="pipeline")
    parser.add_argument("--no-pipeline-nms", dest="pipeline_nms", action="store_false", default=True)
    parser.add_argument("--require-candidate-match", action="store_true")
    parser.add_argument("--require-detector-target", action="store_true")
    parser.add_argument("--no-clean-output", dest="clean_output", action="store_false", default=True)
    args = parser.parse_args()

    root = args.output_root
    args.raw_candidates_root = root / "probe_candidates_from_bench_v12"
    args.filtered_candidates_root = root / "probe_candidates_filtered_v12"
    args.suggestions_root = root / "filter_suggestions_v12"
    args.generation_summary = root / "probe_generation_summary_v12_current.json"
    args.filter_summary = root / "filter_apply_summary_v12_current.json"
    args.raw_compare_output_dir = root / "raw_delta"
    args.filtered_compare_output_dir = root / "filtered_delta"
    args.scoring_input_compare_output_dir = root / "scoring_input_delta"
    args.scoring_output_dir = root / "direct_scoring"
    args.eval_output_dir = root / "direct_eval"
    args.provenance_path = root / "issue36_dense_candidates_direct_score_provenance.json"

    if args.clean_output:
        shutil.rmtree(args.output_root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)

    run(build_generation_command(args))
    run(build_filter_command(args))

    comparisons = {}
    compare_specs = [
        ("raw", args.historical_raw_candidates_root, args.raw_candidates_root, args.raw_compare_output_dir),
        (
            "filtered",
            args.historical_filtered_candidates_root,
            args.filtered_candidates_root,
            args.filtered_compare_output_dir,
        ),
        (
            "historical_scoring_input",
            args.historical_scoring_input_root,
            args.filtered_candidates_root,
            args.scoring_input_compare_output_dir,
        ),
    ]
    for label, left, right, output_dir in compare_specs:
        if not left.exists():
            print(f"Skipping {label} comparison: historical root not found: {left}")
            comparisons[label] = None
            continue
        run(build_compare_command(left=left, right=right, output_dir=output_dir))
        comparisons[label] = comparison_summary(output_dir / "filter_candidate_delta_summary.json")

    if args.require_candidate_match:
        for label in ["raw", "filtered", "historical_scoring_input"]:
            assert_candidate_match(comparisons.get(label), label=label)

    run(build_score_command(args))
    validate_complete_contract(args.eval_output_dir)

    if args.require_detector_target:
        validate_detector_target(args.eval_output_dir)

    provenance = {
        "schema_version": "pipeline.detector_routes.issue36_dense_candidates_direct_score.v1",
        "status": "diagnostic_direct_score_not_acceptance_route",
        "issue": 149,
        "parent_issue": 120,
        "pipeline_scope": {
            "level": "detector_level_partial_route",
            "includes": [
                "Issue36 dense candidate generation",
                "clef-mask-aware filtering",
                "direct CNN scoring of filtered candidates",
                "canonical detector evaluation",
            ],
            "excludes": [
                "probe-rescue candidate regeneration",
                "full HOMR/SR/OMR upstream generation",
                "downstream measure numbering",
            ],
        },
        "inputs": {
            "inventory": str(args.inventory),
            "exclude": str(args.exclude),
            "image_root": str(args.image_root),
            "gt_root": str(args.gt_root),
            "model_path": str(args.model_path),
            "historical_raw_candidates_root": str(args.historical_raw_candidates_root),
            "historical_filtered_candidates_root": str(args.historical_filtered_candidates_root),
            "historical_scoring_input_root": str(args.historical_scoring_input_root),
        },
        "outputs": {
            "raw_candidates_root": str(args.raw_candidates_root),
            "filtered_candidates_root": str(args.filtered_candidates_root),
            "scoring_output_dir": str(args.scoring_output_dir),
            "eval_output_dir": str(args.eval_output_dir),
        },
        "candidate_root_summary": {
            "raw": candidate_root_summary(args.raw_candidates_root),
            "filtered": candidate_root_summary(args.filtered_candidates_root),
            "scoring_input": candidate_root_summary(args.scoring_output_dir),
        },
        "comparisons": comparisons,
        "generation_params": GENERATION_PARAMS,
        "filter_params": FILTER_PARAMS,
        "generation_summary": load_optional_json(args.generation_summary),
        "filter_summary": load_optional_json(args.filter_summary),
        "cnn_scoring": {
            "scorer": args.scorer,
            "cnn_apply_nms": args.pipeline_nms,
            "score_threshold": args.score_threshold,
            "xdist_threshold": args.xdist_threshold,
        },
        "detector_target": TARGET_DETECTOR,
        "detector_summary": detector_summary(args.eval_output_dir),
        "scope_guards": {
            "accepted_route": False,
            "direct_scoring_of_issue36_filtered_root_is_diagnostic_only": True,
            "accepted_route_uses_probe_rescue_candidate_generation": True,
            "full_slow_pipeline_owner": "#141",
            "nms_policy_owner": "#142",
            "measure_count_metrics_not_in_scope": True,
        },
    }
    write_json(args.provenance_path, provenance)
    print(f"Wrote provenance: {args.provenance_path}")

    summary = detector_summary(args.eval_output_dir)
    print(f"Issue36 dense direct-score diagnostic complete: {args.eval_output_dir}")
    if summary:
        print(
            "Detector: "
            f"TP={summary.get('tp')} FP={summary.get('fp')} FN={summary.get('fn')} "
            f"Pred={summary.get('pred')} GT={summary.get('gt')}"
        )


if __name__ == "__main__":
    main()
