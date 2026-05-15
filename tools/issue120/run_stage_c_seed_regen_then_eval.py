#!/usr/bin/env python3
"""Stage-C verifier for Issue #120: seed/candidate regeneration -> scoring -> eval.

This wrapper keeps Stage C explicit:

1. validate the historical log/model dependencies used by
   tools/repro_accuracy/reproduce_clean_seed_v12.py;
2. optionally run that seed/candidate regeneration script;
3. validate regenerated candidate coverage before scoring;
4. run the Stage-B verifier on the regenerated candidates;
5. evaluate with the canonical #134 full-68 evaluator.

Stage C still does not regenerate the slow upstream HOMR/OMR/SR artifacts. It
starts from existing historical logs under logs/hybrid_generalization and checks
whether the current seed/probe regeneration path can reproduce candidates that
score to the historical detector target.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from tools.issue120.eval_full68_from_intermediates import find_page_file, iter_manifest

DEFAULT_INVENTORY = Path("logs/issue36_prep/20260208_bench_inventory.json")
DEFAULT_RUN_ROOT = Path("logs/hybrid_generalization/verify_fixed_v10")
DEFAULT_REGEN_OUTPUT = Path("logs/repro_v12_recovery_final")
DEFAULT_REGEN_CANDIDATES = DEFAULT_REGEN_OUTPUT / "probe_candidates_filtered_v12"
DEFAULT_MODEL = Path(
    "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
)

SCORE_TO_RUN = {
    "Shostakovich-Festival_Overture_Va": "20260324_121505",
    "Shostakovich-Sym5-Va": "20260330_034727",
    "Sibelius-Violin_Concerto-Viola": "20260330_042631",
    "Va_Prokofiev_Symphony1": "20260330_044952",
    "Va__Prokofiev_Symphony5": "20260330_095914",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def validate_inputs(args: argparse.Namespace) -> list[str]:
    missing: list[str] = []
    required_paths = [
        args.model_path,
        args.image_root,
        args.gt_root,
    ]
    if args.skip_regeneration:
        required_paths.append(args.regenerated_candidates_dir)
    else:
        required_paths.extend([args.inventory_path, args.run_root])

    for path in required_paths:
        if not path.exists():
            missing.append(str(path))

    if not args.skip_regeneration and args.run_root.exists():
        for score_name, run_id in SCORE_TO_RUN.items():
            run_dir = args.run_root / run_id
            if not run_dir.exists():
                missing.append(f"{run_dir}  # {score_name}")

    return missing


def run_command(cmd: list[str]) -> None:
    print("+ " + " ".join(str(part) for part in cmd), flush=True)
    subprocess.run(cmd, check=True)


def run_regeneration(args: argparse.Namespace) -> None:
    run_command(
        [
            sys.executable,
            "tools/repro_accuracy/reproduce_clean_seed_v12.py",
            "--inventory-path",
            str(args.inventory_path),
            "--run-root",
            str(args.run_root),
            "--output-root",
            str(args.regen_output_dir),
        ]
    )


def validate_candidate_coverage(args: argparse.Namespace) -> dict[str, Any]:
    manifest = iter_manifest()
    missing_pages: list[dict[str, str]] = []
    empty_pages: list[dict[str, str]] = []
    page_counts: list[dict[str, Any]] = []
    total_candidates = 0

    for record in manifest:
        path = find_page_file(
            args.regenerated_candidates_dir,
            record,
            "pipeline2_no_peak_candidates.json",
        )
        if path is None:
            missing_pages.append({"score": record.score, "page": record.page})
            continue

        payload = load_json(path)
        count = len(payload) if isinstance(payload, list) else 0
        total_candidates += count
        item = {
            "score": record.score,
            "page": record.page,
            "path": str(path),
            "candidate_count": count,
        }
        page_counts.append(item)
        if count == 0:
            empty_pages.append(item)

    report = {
        "schema_version": "issue120.stage_c.candidate_coverage.v1",
        "regenerated_candidates_dir": str(args.regenerated_candidates_dir),
        "expected_pages": len(manifest),
        "present_pages": len(page_counts),
        "missing_pages": missing_pages,
        "empty_pages": empty_pages,
        "total_candidates": total_candidates,
        "page_counts": page_counts,
    }
    write_json(args.stage_c_eval_dir / "stage_c_candidate_coverage.json", report)
    return report


def assert_candidate_coverage(args: argparse.Namespace, report: dict[str, Any]) -> None:
    missing_count = len(report["missing_pages"])
    present_pages = report["present_pages"]
    total_candidates = report["total_candidates"]
    expected_pages = report["expected_pages"]

    if missing_count:
        raise SystemExit(
            f"Stage C candidate coverage failed: {missing_count} missing pages. "
            f"See {args.stage_c_eval_dir / 'stage_c_candidate_coverage.json'}"
        )
    if present_pages != expected_pages:
        raise SystemExit(
            f"Stage C candidate coverage failed: {present_pages}/{expected_pages} pages present. "
            f"See {args.stage_c_eval_dir / 'stage_c_candidate_coverage.json'}"
        )
    if total_candidates < args.min_total_candidates:
        raise SystemExit(
            f"Stage C candidate coverage failed: only {total_candidates} total candidates; "
            f"minimum is {args.min_total_candidates}. "
            f"See {args.stage_c_eval_dir / 'stage_c_candidate_coverage.json'}"
        )


def build_stage_b_cmd(args: argparse.Namespace) -> list[str]:
    cmd = [
        sys.executable,
        "tools/issue120/score_candidates_then_eval_full68.py",
        "--scorer",
        args.scorer,
        "--clean-output",
        "--candidates-dir",
        str(args.regenerated_candidates_dir),
        "--image-root",
        str(args.image_root),
        "--gt-root",
        str(args.gt_root),
        "--model-path",
        str(args.model_path),
        "--scoring-output-dir",
        str(args.stage_c_scoring_dir),
        "--eval-output-dir",
        str(args.stage_c_eval_dir),
        "--score-threshold",
        str(args.score_threshold),
        "--xdist-threshold",
        str(args.xdist_threshold),
    ]
    if args.scorer == "pipeline" and not args.pipeline_nms:
        cmd.append("--disable-pipeline-nms")
    if args.bands_from:
        cmd.extend(["--bands-from", str(args.bands_from)])
    return cmd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-path", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--regen-output-dir", type=Path, default=DEFAULT_REGEN_OUTPUT)
    parser.add_argument("--regenerated-candidates-dir", type=Path, default=DEFAULT_REGEN_CANDIDATES)
    parser.add_argument("--image-root", type=Path, default=Path("data/evaluation2/images"))
    parser.add_argument("--gt-root", type=Path, default=Path("data/evaluation2/annotations"))
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL)
    parser.add_argument(
        "--stage-c-scoring-dir",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/stage_c_seed_regen_scoring"),
    )
    parser.add_argument(
        "--stage-c-eval-dir",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/stage_c_seed_regen_eval"),
    )
    parser.add_argument("--scorer", choices=["pipeline", "legacy"], default="pipeline")
    parser.add_argument("--pipeline-nms", action="store_true", default=False)
    parser.add_argument("--score-threshold", type=float, default=0.1)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    parser.add_argument("--bands-from", type=Path, default=None)
    parser.add_argument(
        "--min-total-candidates",
        type=int,
        default=3000,
        help="Fail before scoring if regenerated candidates are implausibly sparse.",
    )
    parser.add_argument(
        "--skip-regeneration",
        action="store_true",
        help="Skip reproduce_clean_seed_v12.py and only evaluate existing regenerated candidates.",
    )
    parser.add_argument(
        "--no-clean-regen-output",
        action="store_true",
        help="Do not delete the regeneration output directory before running regeneration.",
    )
    parser.add_argument(
        "--coverage-only",
        action="store_true",
        help="Validate regenerated candidate coverage and stop before scoring.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate required historical inputs; do not run regeneration or evaluation.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    missing = validate_inputs(args)
    report = {
        "schema_version": "issue120.stage_c.validation.v1",
        "inventory_path": str(args.inventory_path),
        "run_root": str(args.run_root),
        "regen_output_dir": str(args.regen_output_dir),
        "regenerated_candidates_dir": str(args.regenerated_candidates_dir),
        "model_path": str(args.model_path),
        "score_to_run": SCORE_TO_RUN,
        "missing": missing,
        "skip_regeneration": args.skip_regeneration,
        "scorer": args.scorer,
        "pipeline_nms": args.pipeline_nms,
    }
    write_json(args.stage_c_eval_dir / "stage_c_input_validation.json", report)

    if missing:
        print("Missing required Stage-C inputs:")
        for item in missing:
            print(f"  - {item}")
        print(f"Validation report: {args.stage_c_eval_dir / 'stage_c_input_validation.json'}")
        raise SystemExit(2)

    print("Stage-C input validation passed.")
    if args.validate_only:
        return

    if not args.skip_regeneration:
        if args.regen_output_dir.exists() and not args.no_clean_regen_output:
            shutil.rmtree(args.regen_output_dir)
        run_regeneration(args)

    if not args.regenerated_candidates_dir.exists():
        raise SystemExit(f"Regenerated candidates not found: {args.regenerated_candidates_dir}")

    coverage = validate_candidate_coverage(args)
    print(
        "Stage-C candidate coverage: "
        f"pages={coverage['present_pages']}/{coverage['expected_pages']} "
        f"total_candidates={coverage['total_candidates']} "
        f"missing={len(coverage['missing_pages'])} "
        f"empty={len(coverage['empty_pages'])}"
    )
    assert_candidate_coverage(args, coverage)
    if args.coverage_only:
        return

    run_command(build_stage_b_cmd(args))
    print(f"Stage-C evaluation complete: {args.stage_c_eval_dir}")


if __name__ == "__main__":
    main()
