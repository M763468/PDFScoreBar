#!/usr/bin/env python3
"""Validate Issue #120 by regenerating Issue #36 dense bands, then Issue53 candidates.

This is the #149 acceptance route:

    Issue36 inventory -> dense raw candidates -> clef-mask-aware filtered root
      -> candidate-root comparison against recovered historical roots
      -> use filtered root as `bands_from` for current Issue53 probe-rescue verifier
      -> current CNN scoring with explicit NMS setting
      -> #134 full-68 detector evaluator

The filtered Issue36 root is a recovered dense candidate / bands_from root. Directly
scoring it is useful as a diagnostic, but it is not the clean Issue #120 detector
reconstruction route because it has detector-side misses before CNN scoring.
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
DEFAULT_OUTPUT_ROOT = Path(
    "logs/issue120_e2e_recovery/stage_d_issue36_dense_candidate_validation"
)
DEFAULT_HISTORICAL_RAW = Path("logs/issue36_prep/probe_candidates_from_bench_v12")
DEFAULT_HISTORICAL_FILTERED = Path("logs/issue36_prep/probe_candidates_filtered_v12")
DEFAULT_HISTORICAL_SCORING_INPUT = Path(
    "logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12"
)
TARGET_DETECTOR = {"tp": 3580, "fp": 0, "fn": 1}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def run_command(cmd: list[str]) -> None:
    print("+ " + " ".join(str(part) for part in cmd), flush=True)
    subprocess.run(cmd, check=True)


def require_under_logs(path: Path, *, label: str) -> None:
    logs_root = PROJECT_ROOT.resolve() / "logs"
    try:
        path.resolve().relative_to(logs_root)
    except ValueError as exc:
        raise SystemExit(
            f"Error: {label} must be under logs/ per repository log-management policy. "
            f"Got: {path}"
        ) from exc


def candidate_root_summary(root: Path) -> dict[str, int | str | bool]:
    files = sorted(root.rglob("pipeline2_no_peak_candidates.json")) if root.exists() else []
    total = 0
    unreadable = 0
    for path in files:
        try:
            payload = load_json(path)
        except (json.JSONDecodeError, OSError):
            unreadable += 1
            continue
        if isinstance(payload, list):
            total += len(payload)
    return {
        "root": str(root),
        "exists": root.exists(),
        "files": len(files),
        "total_candidates": total,
        "unreadable": unreadable,
    }


def load_optional_json(path: Path) -> Any | None:
    return load_json(path) if path.exists() else None


def detector_summary(eval_output_dir: Path) -> dict[str, Any] | None:
    metrics_path = eval_output_dir / "detector_metrics.json"
    if metrics_path.exists():
        payload = load_json(metrics_path)
        if isinstance(payload, dict):
            return payload
    contract_path = eval_output_dir / "evaluation_contract.json"
    if contract_path.exists():
        payload = load_json(contract_path)
        if isinstance(payload, dict):
            summary = payload.get("detector_summary")
            if isinstance(summary, dict):
                return summary
    return None


def validate_complete_contract(eval_output_dir: Path) -> None:
    contract_path = eval_output_dir / "evaluation_contract.json"
    if not contract_path.exists():
        raise SystemExit(f"evaluation_contract.json not found: {contract_path}")
    contract = load_json(contract_path)
    expected = contract.get("expected_pages")
    evaluated = contract.get("evaluated_pages")
    missing = contract.get("missing_pages", [])
    expected_count = len(iter_manifest())
    if expected != expected_count or evaluated != expected_count or missing:
        raise SystemExit(
            "Incomplete Issue #120 full-68 evaluation contract: "
            f"expected_pages={expected} evaluated_pages={evaluated} "
            f"expected_count={expected_count} missing_pages={len(missing)}"
        )


def validate_detector_target(eval_output_dir: Path) -> None:
    summary = detector_summary(eval_output_dir)
    if summary is None:
        raise SystemExit(f"Detector metrics not found under {eval_output_dir}")
    observed = {"tp": summary.get("tp"), "fp": summary.get("fp"), "fn": summary.get("fn")}
    if observed != TARGET_DETECTOR:
        raise SystemExit(f"Detector target mismatch: observed={observed} target={TARGET_DETECTOR}")


def run_issue36_generation_filter_compare(args: argparse.Namespace) -> None:
    cmd = [
        sys.executable,
        "tools/issue120/run_issue36_dense_candidates_then_eval.py",
        "--inventory",
        str(args.inventory),
        "--exclude",
        str(args.exclude),
        "--historical-raw-candidates-root",
        str(args.historical_raw_candidates_root),
        "--historical-filtered-candidates-root",
        str(args.historical_filtered_candidates_root),
        "--historical-scoring-input-root",
        str(args.historical_scoring_input_root),
        "--image-root",
        str(args.image_root),
        "--gt-root",
        str(args.gt_root),
        "--model-path",
        str(args.model_path),
        "--output-root",
        str(args.output_root),
        "--raw-candidates-root",
        str(args.raw_candidates_root),
        "--filtered-candidates-root",
        str(args.filtered_candidates_root),
        "--skip-scoring",
        "--require-candidate-match",
    ]
    if args.no_clean_output:
        cmd.append("--no-clean-output")
    run_command(cmd)


def run_issue53_probe_rescue(args: argparse.Namespace) -> None:
    cmd = [
        sys.executable,
        "tools/issue120/run_issue53_probe_rescue_then_eval.py",
        "--image-root",
        str(args.image_root),
        "--gt-root",
        str(args.gt_root),
        "--bands-from",
        str(args.filtered_candidates_root),
        "--model-path",
        str(args.model_path),
        "--baseline-dir",
        str(args.baseline_dir),
        "--output-root",
        str(args.issue53_candidates_root),
        "--scoring-output-dir",
        str(args.scoring_output_dir),
        "--eval-output-dir",
        str(args.eval_output_dir),
        "--scorer",
        args.scorer,
        "--score-threshold",
        str(args.score_threshold),
        "--xdist-threshold",
        str(args.xdist_threshold),
    ]
    if args.scorer == "pipeline" and args.pipeline_nms:
        cmd.append("--pipeline-nms")
    if args.no_clean_output:
        cmd.append("--no-clean-output")
    run_command(cmd)


def build_route_provenance(args: argparse.Namespace) -> dict[str, Any]:
    issue36_provenance = load_optional_json(args.issue36_route_provenance)
    filter_summary = load_optional_json(args.filter_summary)
    issue53_provenance = load_optional_json(
        args.eval_output_dir / "issue53_probe_rescue_regen_provenance.json"
    )
    stage_b_provenance = load_optional_json(args.eval_output_dir / "stage_b_provenance.json")
    coverage_summary = load_optional_json(args.eval_output_dir / "candidate_coverage_summary.json")

    clef_mask_resolution = None
    reason_counts = None
    if isinstance(filter_summary, dict):
        clef_mask_resolution = filter_summary.get("clef_mask_resolution")
        reason_counts = filter_summary.get("reason_counts")

    return {
        "schema_version": "issue120.issue36_dense_bands_issue53_validation.v1",
        "status": "issue36_dense_bands_to_issue53_probe_rescue_current_validation",
        "issue": 149,
        "parent_issue": 120,
        "evaluated_stage": "post_cnn_scoring_detector_intermediate",
        "route": [
            "Issue #36 v12 bench inventory",
            "generate dense raw candidates with band_cluster_max_dist=25.0",
            "apply clef-mask-aware filter",
            "verify raw/filtered/scoring-input roots against recovered historical roots",
            "use regenerated filtered root as Issue53 probe-rescue bands_from",
            "score regenerated Issue53 probe-rescue candidates with current CNN scoring",
            "#134 full-68 detector evaluator",
        ],
        "inputs": {
            "inventory": str(args.inventory),
            "exclude": str(args.exclude),
            "image_root": str(args.image_root),
            "gt_root": str(args.gt_root),
            "model_path": str(args.model_path),
            "baseline_dir": str(args.baseline_dir),
            "historical_raw_candidates_root": str(args.historical_raw_candidates_root),
            "historical_filtered_candidates_root": str(args.historical_filtered_candidates_root),
            "historical_scoring_input_root": str(args.historical_scoring_input_root),
        },
        "outputs": {
            "output_root": str(args.output_root),
            "raw_candidates_root": str(args.raw_candidates_root),
            "filtered_candidates_root": str(args.filtered_candidates_root),
            "issue53_candidates_root": str(args.issue53_candidates_root),
            "scoring_output_dir": str(args.scoring_output_dir),
            "eval_output_dir": str(args.eval_output_dir),
            "route_provenance": str(args.route_provenance),
        },
        "candidate_root_summary": {
            "issue36_raw": candidate_root_summary(args.raw_candidates_root),
            "issue36_filtered_bands_from": candidate_root_summary(args.filtered_candidates_root),
            "issue53_regenerated_candidates": candidate_root_summary(args.issue53_candidates_root),
            "scoring_input": candidate_root_summary(args.scoring_output_dir),
        },
        "issue36_provenance": issue36_provenance,
        "clef_mask_filtering": {
            "enabled": True,
            "resolution": clef_mask_resolution,
            "reason_counts": reason_counts,
            "summary_path": str(args.filter_summary),
        },
        "issue53_probe_rescue": {
            "bands_from": str(args.filtered_candidates_root),
            "provenance": issue53_provenance,
            "candidate_coverage_summary": coverage_summary,
        },
        "cnn_scoring": {
            "scorer": args.scorer,
            "cnn_apply_nms": args.pipeline_nms,
            "model_path": str(args.model_path),
            "score_threshold": args.score_threshold,
            "xdist_threshold": args.xdist_threshold,
            "stage_b_provenance": stage_b_provenance,
        },
        "detector_target": TARGET_DETECTOR,
        "detector_summary": detector_summary(args.eval_output_dir),
        "measure_count_summary": {
            "status": "not_run_in_issue149",
            "note": (
                "Detector metrics are evaluated here. Downstream measure-count "
                "validation remains separate."
            ),
        },
        "scope_guards": {
            "general_pipeline_defaults_changed": False,
            "nms_policy_owner": "#142",
            "full_slow_pipeline_owner": "#141",
            "generated_outputs_under_ignored_logs": True,
            "direct_scoring_of_issue36_filtered_root_is_acceptance_route": False,
        },
        "notes": [
            "The Issue36 filtered root is verified as the recovered historical dense "
            "candidate/bands_from root.",
            "Direct scoring of that root has detector-side misses and is diagnostic only.",
            "The acceptance route uses the regenerated filtered root as bands_from for "
            "the current Issue53 probe-rescue verifier.",
        ],
    }


def attach_route_provenance(args: argparse.Namespace) -> None:
    provenance = build_route_provenance(args)
    write_json(args.route_provenance, provenance)
    run_command(
        [
            sys.executable,
            "tools/issue120/attach_eval_provenance.py",
            "--output-dir",
            str(args.eval_output_dir),
            "--results-dir",
            str(args.scoring_output_dir),
            "--provenance-json",
            str(args.route_provenance),
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("logs/issue36_prep/20260208_bench_inventory.json"),
    )
    parser.add_argument(
        "--exclude",
        type=Path,
        default=Path("logs/issue36_prep/excluded_pages_for_gt_prep.json"),
    )
    parser.add_argument("--image-root", type=Path, default=Path("data/evaluation2/images"))
    parser.add_argument("--gt-root", type=Path, default=Path("data/evaluation2/annotations"))
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--baseline-dir", type=Path, default=Path("data/evaluation2/golden_baseline_eval2_bc23deb"))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--historical-raw-candidates-root", type=Path, default=DEFAULT_HISTORICAL_RAW)
    parser.add_argument(
        "--historical-filtered-candidates-root",
        type=Path,
        default=DEFAULT_HISTORICAL_FILTERED,
    )
    parser.add_argument(
        "--historical-scoring-input-root",
        type=Path,
        default=DEFAULT_HISTORICAL_SCORING_INPUT,
    )
    parser.add_argument("--raw-candidates-root", type=Path, default=None)
    parser.add_argument("--filtered-candidates-root", type=Path, default=None)
    parser.add_argument("--issue53-candidates-root", type=Path, default=None)
    parser.add_argument("--scoring-output-dir", type=Path, default=None)
    parser.add_argument("--eval-output-dir", type=Path, default=None)
    parser.add_argument("--route-provenance", type=Path, default=None)
    parser.add_argument("--scorer", choices=["pipeline", "legacy"], default="pipeline")
    parser.add_argument(
        "--pipeline-nms",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Explicit CNN NMS setting. Issue #120 reconstruction uses --no-pipeline-nms.",
    )
    parser.add_argument("--score-threshold", type=float, default=0.1)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    parser.add_argument("--no-clean-output", action="store_true")
    parser.add_argument("--skip-issue36-regeneration", action="store_true")
    parser.add_argument(
        "--require-detector-target",
        action="store_true",
        help="Fail unless detector TP/FP/FN equals 3580/0/1.",
    )
    return parser


def resolve_default_paths(args: argparse.Namespace) -> None:
    args.raw_candidates_root = (
        args.raw_candidates_root or args.output_root / "probe_candidates_from_bench_v12"
    )
    args.filtered_candidates_root = (
        args.filtered_candidates_root or args.output_root / "probe_candidates_filtered_v12"
    )
    args.issue53_candidates_root = (
        args.issue53_candidates_root or args.output_root / "issue53_probe_rescue_candidates"
    )
    args.scoring_output_dir = args.scoring_output_dir or args.output_root / "scoring"
    args.eval_output_dir = args.eval_output_dir or args.output_root / "eval"
    args.route_provenance = (
        args.route_provenance or args.output_root / "issue36_dense_bands_issue53_route_provenance.json"
    )
    args.issue36_route_provenance = (
        args.output_root / "issue36_dense_candidate_route_provenance.json"
    )
    args.filter_summary = args.output_root / "filter_apply_summary_v12_current.json"


def validate_output_paths(args: argparse.Namespace) -> None:
    output_paths = {
        "output-root": args.output_root,
        "raw-candidates-root": args.raw_candidates_root,
        "filtered-candidates-root": args.filtered_candidates_root,
        "issue53-candidates-root": args.issue53_candidates_root,
        "scoring-output-dir": args.scoring_output_dir,
        "eval-output-dir": args.eval_output_dir,
        "route-provenance": args.route_provenance,
        "issue36-route-provenance": args.issue36_route_provenance,
        "filter-summary": args.filter_summary,
    }
    for label, path in output_paths.items():
        require_under_logs(path, label=label)


def validate_inputs(args: argparse.Namespace) -> None:
    required = [args.inventory, args.exclude, args.image_root, args.gt_root, args.model_path]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing required inputs:\n" + "\n".join(missing))
    validate_output_paths(args)


def main() -> None:
    args = build_parser().parse_args()
    resolve_default_paths(args)
    validate_inputs(args)

    if not args.no_clean_output:
        shutil.rmtree(args.issue53_candidates_root, ignore_errors=True)
        shutil.rmtree(args.scoring_output_dir, ignore_errors=True)
        shutil.rmtree(args.eval_output_dir, ignore_errors=True)

    args.output_root.mkdir(parents=True, exist_ok=True)

    if not args.skip_issue36_regeneration:
        run_issue36_generation_filter_compare(args)

    run_issue53_probe_rescue(args)
    validate_complete_contract(args.eval_output_dir)
    attach_route_provenance(args)
    if args.require_detector_target:
        validate_detector_target(args.eval_output_dir)

    summary = detector_summary(args.eval_output_dir)
    print(f"Issue36 dense bands -> Issue53 validation complete: {args.eval_output_dir}")
    if summary:
        print(
            "Detector: "
            f"TP={summary.get('tp')} FP={summary.get('fp')} FN={summary.get('fn')} "
            f"Pred={summary.get('pred')} GT={summary.get('gt')}"
        )


if __name__ == "__main__":
    main()
