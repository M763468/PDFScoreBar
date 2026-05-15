#!/usr/bin/env python3
"""Regenerate Issue #36 v12 dense candidates and evaluate Issue #120 detector metrics.

This #149 wrapper is intentionally narrow:

    inventory -> dense raw candidates -> clef-mask-aware filter
      -> current CNN scoring -> #134 full-68 detector evaluator

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

DEFAULT_MODEL = Path(
    "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
)
DEFAULT_OUTPUT_ROOT = Path(
    "logs/issue120_e2e_recovery/stage_d_issue36_dense_candidate_validation"
)

TARGET_DETECTOR = {"tp": 3580, "fp": 0, "fn": 1}

GENERATION_PARAMS: dict[str, str] = {
    "band_source": "row_stats",
    "ink_threshold": "240",
    "min_ratio": "0.6",
    "min_height_ratio": "0.006",
    "min_width_ratio": "0.0",
    "probe_width": "4",
    "max_per_band": "80",
    "band_scan_line_ratio": "0.6",
    "band_scan_min_lines": "5",
}

FILTER_PARAMS: dict[str, str] = {
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
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def run_command(cmd: list[str]) -> None:
    print("+ " + " ".join(str(part) for part in cmd), flush=True)
    subprocess.run(cmd, check=True)


def add_param_args(cmd: list[str], params: dict[str, str]) -> None:
    for name, value in params.items():
        cmd.extend([f"--{name.replace('_', '-')}", value])


def candidate_root_summary(root: Path) -> dict[str, int | str]:
    files = sorted(root.rglob("pipeline2_no_peak_candidates.json"))
    total = 0
    unreadable = 0
    for path in files:
        try:
            payload = load_json(path)
        except Exception:  # noqa: BLE001
            unreadable += 1
            continue
        if isinstance(payload, list):
            total += len(payload)
    return {
        "root": str(root),
        "files": len(files),
        "total_candidates": total,
        "unreadable": unreadable,
    }


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
    if expected != 68 or evaluated != 68 or missing:
        raise SystemExit(
            "Incomplete Issue #120 full-68 evaluation contract: "
            f"expected_pages={expected} evaluated_pages={evaluated} missing_pages={len(missing)}"
        )


def validate_detector_target(eval_output_dir: Path) -> None:
    summary = detector_summary(eval_output_dir)
    if summary is None:
        raise SystemExit(f"Detector metrics not found under {eval_output_dir}")
    observed = {"tp": summary.get("tp"), "fp": summary.get("fp"), "fn": summary.get("fn")}
    if observed != TARGET_DETECTOR:
        raise SystemExit(f"Detector target mismatch: observed={observed} target={TARGET_DETECTOR}")


def build_route_provenance(args: argparse.Namespace) -> dict[str, Any]:
    generation_summary = (
        load_json(args.generation_summary) if args.generation_summary.exists() else None
    )
    filter_summary = load_json(args.filter_summary) if args.filter_summary.exists() else None
    score_stage_provenance = (
        load_json(args.eval_output_dir / "stage_b_provenance.json")
        if (args.eval_output_dir / "stage_b_provenance.json").exists()
        else None
    )
    eval_summary = detector_summary(args.eval_output_dir)

    clef_mask_resolution = None
    reason_counts = None
    if isinstance(filter_summary, dict):
        clef_mask_resolution = filter_summary.get("clef_mask_resolution")
        reason_counts = filter_summary.get("reason_counts")

    return {
        "schema_version": "issue120.issue36_dense_candidate_validation.v1",
        "status": "issue36_dense_candidate_current_validation_route",
        "issue": 149,
        "parent_issue": 120,
        "evaluated_stage": "post_cnn_scoring_detector_intermediate",
        "route": [
            "Issue #36 v12 bench inventory",
            "tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py",
            "tools/verification/gt_preparation/apply_candidate_filter_from_inventory.py "
            "with clef-mask-aware filtering",
            "tools/issue120/score_candidates_then_eval_full68.py",
            "tools/issue120/eval_full68_from_intermediates.py (#134 full-68 evaluator)",
        ],
        "inputs": {
            "inventory": str(args.inventory),
            "exclude": str(args.exclude),
            "image_root": str(args.image_root),
            "gt_root": str(args.gt_root),
            "model_path": str(args.model_path),
        },
        "outputs": {
            "output_root": str(args.output_root),
            "raw_candidates_root": str(args.raw_candidates_root),
            "filtered_candidates_root": str(args.filtered_candidates_root),
            "filter_suggestions_root": str(args.suggestions_root),
            "scoring_output_dir": str(args.scoring_output_dir),
            "eval_output_dir": str(args.eval_output_dir),
            "generation_summary": str(args.generation_summary),
            "filter_summary": str(args.filter_summary),
        },
        "candidate_root_summary": {
            "raw": candidate_root_summary(args.raw_candidates_root),
            "filtered": candidate_root_summary(args.filtered_candidates_root),
        },
        "generation_params": GENERATION_PARAMS,
        "filter_params": FILTER_PARAMS,
        "clef_mask_filtering": {
            "enabled": True,
            "resolution": clef_mask_resolution,
            "reason_counts": reason_counts,
            "summary_path": str(args.filter_summary),
        },
        "cnn_scoring": {
            "scorer": args.scorer,
            "cnn_apply_nms": args.pipeline_nms,
            "model_path": str(args.model_path),
            "score_threshold": args.score_threshold,
            "xdist_threshold": args.xdist_threshold,
            "stage_b_provenance": score_stage_provenance,
        },
        "detector_target": TARGET_DETECTOR,
        "detector_summary": eval_summary,
        "measure_count_summary": {
            "status": "not_run_in_issue149",
            "note": (
                "Detector metrics are evaluated here. "
                "Downstream measure-count validation remains separate."
            ),
        },
        "scope_guards": {
            "general_pipeline_defaults_changed": False,
            "nms_policy_owner": "#142",
            "full_slow_pipeline_owner": "#141",
            "generated_outputs_under_ignored_logs": str(args.output_root).startswith("logs/"),
        },
        "notes": [
            "This route integrates the recovered Issue #36 v12 dense candidate producer "
            "into current Issue #120 validation.",
            "It does not run the full slow HOMR/SR/OMR pipeline.",
            "It keeps detector metrics separate from downstream measure-count metrics.",
        ],
        "generation_summary": generation_summary,
        "filter_summary": filter_summary,
    }


def run_generation(args: argparse.Namespace) -> None:
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
    run_command(cmd)


def run_filter(args: argparse.Namespace) -> None:
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
    run_command(cmd)


def run_scoring_and_eval(args: argparse.Namespace) -> None:
    cmd = [
        sys.executable,
        "tools/issue120/score_candidates_then_eval_full68.py",
        "--scorer",
        args.scorer,
        "--clean-output",
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
    ]
    if args.scorer == "pipeline" and not args.pipeline_nms:
        cmd.append("--disable-pipeline-nms")
    run_command(cmd)


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
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--raw-candidates-root",
        type=Path,
        default=None,
        help="Defaults to <output-root>/probe_candidates_from_bench_v12.",
    )
    parser.add_argument(
        "--filtered-candidates-root",
        type=Path,
        default=None,
        help="Defaults to <output-root>/probe_candidates_filtered_v12.",
    )
    parser.add_argument(
        "--suggestions-root",
        type=Path,
        default=None,
        help="Defaults to <output-root>/filter_suggestions_v12.",
    )
    parser.add_argument(
        "--generation-summary",
        type=Path,
        default=None,
        help="Defaults to <output-root>/probe_generation_summary_v12_current.json.",
    )
    parser.add_argument(
        "--filter-summary",
        type=Path,
        default=None,
        help="Defaults to <output-root>/filter_apply_summary_v12_current.json.",
    )
    parser.add_argument(
        "--scoring-output-dir",
        type=Path,
        default=None,
        help="Defaults to <output-root>/scoring.",
    )
    parser.add_argument(
        "--eval-output-dir",
        type=Path,
        default=None,
        help="Defaults to <output-root>/eval.",
    )
    parser.add_argument(
        "--route-provenance",
        type=Path,
        default=None,
        help="Defaults to <output-root>/issue36_dense_candidate_route_provenance.json.",
    )
    parser.add_argument("--scorer", choices=["pipeline", "legacy"], default="pipeline")
    parser.add_argument(
        "--pipeline-nms",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Explicit CNN NMS setting for scorer=pipeline. "
            "Issue #120 reconstruction uses --no-pipeline-nms."
        ),
    )
    parser.add_argument("--score-threshold", type=float, default=0.1)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    parser.add_argument("--no-clean-output", action="store_true")
    parser.add_argument("--skip-generation", action="store_true")
    parser.add_argument("--skip-filter", action="store_true")
    parser.add_argument("--skip-scoring", action="store_true")
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
    args.suggestions_root = args.suggestions_root or args.output_root / "filter_suggestions_v12"
    args.generation_summary = (
        args.generation_summary or args.output_root / "probe_generation_summary_v12_current.json"
    )
    args.filter_summary = (
        args.filter_summary or args.output_root / "filter_apply_summary_v12_current.json"
    )
    args.scoring_output_dir = args.scoring_output_dir or args.output_root / "scoring"
    args.eval_output_dir = args.eval_output_dir or args.output_root / "eval"
    args.route_provenance = (
        args.route_provenance or args.output_root / "issue36_dense_candidate_route_provenance.json"
    )


def validate_inputs(args: argparse.Namespace) -> None:
    required = [args.inventory, args.exclude]
    if not args.skip_scoring:
        required.extend([args.image_root, args.gt_root, args.model_path])
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing required inputs:\n" + "\n".join(missing))


def main() -> None:
    args = build_parser().parse_args()
    resolve_default_paths(args)
    validate_inputs(args)

    if not args.no_clean_output:
        if not args.skip_generation:
            shutil.rmtree(args.raw_candidates_root, ignore_errors=True)
        if not args.skip_filter:
            shutil.rmtree(args.filtered_candidates_root, ignore_errors=True)
            shutil.rmtree(args.suggestions_root, ignore_errors=True)
        if not args.skip_scoring:
            shutil.rmtree(args.scoring_output_dir, ignore_errors=True)
            shutil.rmtree(args.eval_output_dir, ignore_errors=True)

    args.output_root.mkdir(parents=True, exist_ok=True)

    if not args.skip_generation:
        run_generation(args)
    if not args.skip_filter:
        run_filter(args)
    if not args.skip_scoring:
        run_scoring_and_eval(args)
        validate_complete_contract(args.eval_output_dir)
        attach_route_provenance(args)
        if args.require_detector_target:
            validate_detector_target(args.eval_output_dir)
        summary = detector_summary(args.eval_output_dir)
        print(f"Issue #36 dense candidate validation complete: {args.eval_output_dir}")
        if summary:
            print(
                "Detector: "
                f"TP={summary.get('tp')} FP={summary.get('fp')} FN={summary.get('fn')} "
                f"Pred={summary.get('pred')} GT={summary.get('gt')}"
            )
    else:
        write_json(args.route_provenance, build_route_provenance(args))
        print(f"Issue #36 dense candidate generation/filter complete: {args.output_root}")


if __name__ == "__main__":
    main()
