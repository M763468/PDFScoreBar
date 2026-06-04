#!/usr/bin/env python3
"""Run Stage E detector contract evaluation from a full-pipeline output root.

The Stage E runner writes full-pipeline scored files and reconstructed candidate
files in separate production-oriented artifact trees. This wrapper materializes
an evaluator-compatible ``eval_inputs`` tree from those artifacts, then delegates
metric calculation and contract writing to ``eval_full68_from_intermediates.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

import eval_full68_from_intermediates as full68_eval  # noqa: E402

EXPECTED_DETECTOR_METRICS: dict[str, int | float] = {
    "page_count": 68,
    "expected_page_count": 68,
    "gt": 3581,
    "pred": 3600,
    "tp": 3580,
    "fp": 0,
    "fn": 1,
    "fn_det": 0,
    "fn_cnn": 1,
    "precision": 1.0,
    "recall": 0.9997207483943032,
}


class MissingStageEArtifactError(RuntimeError):
    """Raised when the Stage E run root does not contain required artifacts."""


def _stage_e_run_root(args: argparse.Namespace) -> Path:
    if args.run_root is not None:
        return args.run_root
    return args.output_root / "stage_e_full_pipeline"


def _default_eval_inputs_dir(run_root: Path, args: argparse.Namespace) -> Path:
    return args.eval_inputs_dir or run_root / "eval_inputs"


def _default_eval_output_dir(run_root: Path, args: argparse.Namespace) -> Path:
    return args.eval_output_dir or run_root / "eval_detector"


def _selected_records(args: argparse.Namespace) -> list[full68_eval.PageRecord]:
    records = full68_eval.iter_manifest()
    if args.page_limit is None:
        return records
    if args.page_limit <= 0:
        raise ValueError("--page-limit must be positive when provided")
    return records[: args.page_limit]


def _candidate_paths(root: Path, record: full68_eval.PageRecord, filename: str) -> list[Path]:
    return [
        root
        / "intermediate"
        / "probe_scan"
        / f"eval2_images_{record.score}_{record.page}"
        / filename,
        root
        / "dense_candidate_reconstruction"
        / "probe_candidates_from_inventory"
        / record.score
        / record.page
        / filename,
        root
        / "dense_candidate_reconstruction"
        / "probe_candidates_filtered"
        / record.score
        / record.page
        / filename,
        root
        / "dense_candidate_reconstruction"
        / "probe_rescue_candidates"
        / record.score
        / record.page
        / filename,
    ]


def _scored_paths(root: Path, record: full68_eval.PageRecord, filename: str) -> list[Path]:
    return [
        root
        / "intermediate"
        / "probe_scan"
        / f"eval2_images_{record.score}_{record.page}"
        / filename,
        root
        / "intermediate"
        / "probe_scan"
        / f"eval2_{record.score}_{record.page}"
        / filename,
    ]


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _materialize_file(src: Path, dst: Path, *, mode: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if mode == "copy":
        shutil.copy2(src, dst)
    elif mode == "symlink":
        dst.symlink_to(src.resolve())
    elif mode == "hardlink":
        os.link(src, dst)
    else:
        raise ValueError(f"Unknown link mode: {mode}")


def _prepare_eval_inputs(args: argparse.Namespace) -> tuple[Path, list[dict[str, Any]]]:
    run_root = _stage_e_run_root(args)
    if not run_root.exists():
        raise MissingStageEArtifactError(f"Stage E run root not found: {run_root}")

    eval_inputs_dir = _default_eval_inputs_dir(run_root, args)
    if eval_inputs_dir.exists():
        shutil.rmtree(eval_inputs_dir)
    eval_inputs_dir.mkdir(parents=True, exist_ok=True)

    selected_records = _selected_records(args)
    records: list[dict[str, Any]] = []
    missing: list[str] = []
    for record in selected_records:
        scored_src = _first_existing(_scored_paths(run_root, record, args.scored_file))
        candidates_src = _first_existing(_candidate_paths(run_root, record, args.candidates_file))
        page_dir = eval_inputs_dir / f"eval2_{record.score}_{record.page}"

        if scored_src is None:
            missing.append(
                f"missing scored file for {record.score}/{record.page}: {args.scored_file}"
            )
        else:
            _materialize_file(
                scored_src,
                page_dir / args.scored_file,
                mode=args.link_mode,
            )

        if candidates_src is None:
            message = (
                f"missing candidates file for {record.score}/{record.page}: "
                f"{args.candidates_file}"
            )
            if args.allow_missing_candidates:
                records.append(
                    {
                        "score": record.score,
                        "page": record.page,
                        "scored_source": str(scored_src) if scored_src else None,
                        "candidates_source": None,
                        "candidates_status": "missing_allowed",
                        "eval_input_dir": str(page_dir),
                    }
                )
                continue
            missing.append(message)
        else:
            _materialize_file(
                candidates_src,
                page_dir / args.candidates_file,
                mode=args.link_mode,
            )

        records.append(
            {
                "score": record.score,
                "page": record.page,
                "scored_source": str(scored_src) if scored_src else None,
                "candidates_source": str(candidates_src) if candidates_src else None,
                "candidates_status": "present" if candidates_src else "missing",
                "eval_input_dir": str(page_dir),
            }
        )

    manifest_path = eval_inputs_dir / "input_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "tools.issue120.stage_e_eval_inputs.v1",
                "stage_e_run_root": str(run_root),
                "link_mode": args.link_mode,
                "scored_file": args.scored_file,
                "candidates_file": args.candidates_file,
                "selected_page_count": len(selected_records),
                "canonical_page_count": len(full68_eval.iter_manifest()),
                "page_count": len(records),
                "records": records,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    if missing:
        missing_path = eval_inputs_dir / "missing_stage_e_artifacts.json"
        missing_path.write_text(
            json.dumps(missing, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        raise MissingStageEArtifactError(
            f"Missing {len(missing)} Stage E artifact(s). See {missing_path}"
        )

    return eval_inputs_dir, records


def _build_eval_args(
    args: argparse.Namespace, eval_inputs_dir: Path, eval_output_dir: Path
) -> argparse.Namespace:
    return argparse.Namespace(
        results_dir=str(eval_inputs_dir),
        gt_root=str(args.gt_root),
        output_dir=str(eval_output_dir),
        scored_file=args.scored_file,
        candidates_file=args.candidates_file,
        score_threshold=args.score_threshold,
        rule_name=args.rule_name,
        vov_threshold=args.vov_threshold,
        xdist_threshold=args.xdist_threshold,
        allow_partial=args.allow_partial,
        measure_summary_json=args.measure_summary_json,
    )


def _metric_matches(actual: int | float | None, expected: int | float) -> bool:
    if actual is None:
        return False
    if isinstance(expected, float):
        return abs(float(actual) - expected) <= 1e-12
    return int(actual) == expected


def _canonical_mismatches(
    summary: full68_eval.DetectorSummary,
) -> dict[str, dict[str, int | float | None]]:
    payload = asdict(summary)
    mismatches: dict[str, dict[str, int | float | None]] = {}
    for key, expected in EXPECTED_DETECTOR_METRICS.items():
        actual = payload.get(key)
        if not _metric_matches(actual, expected):
            mismatches[key] = {"expected": expected, "actual": actual}
    return mismatches


def _print_summary(
    *,
    run_root: Path,
    eval_inputs_dir: Path,
    eval_output_dir: Path,
    contract: full68_eval.EvaluationContract,
    mismatches: dict[str, dict[str, int | float | None]],
) -> None:
    summary = contract.detector_summary
    print("Stage E contract evaluation")
    print(f"Stage E run root: {run_root}")
    print(f"Eval inputs: {eval_inputs_dir}")
    print(f"Contract outputs: {eval_output_dir}")
    print(f"Pages: {summary.page_count}/{summary.expected_page_count}")
    print(
        "Detector: "
        f"GT={summary.gt} Pred={summary.pred} TP={summary.tp} FP={summary.fp} "
        f"FN={summary.fn} FN_det={summary.fn_det} FN_cnn={summary.fn_cnn} "
        f"Precision={full68_eval.format_metric(summary.precision)} "
        f"Recall={full68_eval.format_metric(summary.recall)}"
    )
    if mismatches:
        print("Canonical detector target: NOT MET")
        for key, values in mismatches.items():
            print(f"  {key}: expected={values['expected']} actual={values['actual']}")
    else:
        print("Canonical detector target: MET")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("logs/issue120_e2e_recovery"),
        help="Output root passed to run_stage_e_full_pipeline.py.",
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        default=None,
        help="Explicit Stage E run root. Defaults to <output-root>/stage_e_full_pipeline.",
    )
    parser.add_argument(
        "--eval-inputs-dir",
        type=Path,
        default=None,
        help="Evaluator-compatible input directory. Defaults under the Stage E run root.",
    )
    parser.add_argument(
        "--eval-output-dir",
        type=Path,
        default=None,
        help="Contract output directory. Defaults to <run-root>/eval_detector.",
    )
    parser.add_argument(
        "--page-limit",
        type=int,
        default=None,
        help="Evaluate only the first N canonical pages. Use with --allow-partial for smoke tests.",
    )
    parser.add_argument("--gt-root", type=Path, default=Path("data/evaluation2/annotations"))
    parser.add_argument("--scored-file", default="pipeline2_no_peak_scored.json")
    parser.add_argument("--candidates-file", default="pipeline2_no_peak_candidates.json")
    parser.add_argument("--score-threshold", type=float, default=0.1)
    parser.add_argument(
        "--rule-name", default="center_anchor", choices=["center_anchor", "baseline_iou"]
    )
    parser.add_argument("--vov-threshold", type=float, default=0.5)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    parser.add_argument(
        "--link-mode",
        choices=["copy", "symlink", "hardlink"],
        default="copy",
        help="How to materialize evaluator inputs. Copy is the portable default.",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Pass through to eval_full68_from_intermediates.py for incomplete page sets.",
    )
    parser.add_argument(
        "--allow-missing-candidates",
        action="store_true",
        help="Permit contract evaluation without candidate files; fn_det/fn_cnn may be null.",
    )
    parser.add_argument(
        "--allow-target-mismatch",
        action="store_true",
        help="Write outputs and exit 0 even when canonical detector metrics differ.",
    )
    parser.add_argument(
        "--measure-summary-json",
        type=Path,
        default=None,
        help="Optional downstream measure-count summary JSON to attach to the contract.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.page_limit is not None and not args.allow_partial:
        raise SystemExit("--page-limit is intended for smoke tests and requires --allow-partial")
    run_root = _stage_e_run_root(args)
    eval_inputs_dir, _records = _prepare_eval_inputs(args)
    eval_output_dir = _default_eval_output_dir(run_root, args)
    contract = full68_eval.evaluate(_build_eval_args(args, eval_inputs_dir, eval_output_dir))
    mismatches = _canonical_mismatches(contract.detector_summary)
    _print_summary(
        run_root=run_root,
        eval_inputs_dir=eval_inputs_dir,
        eval_output_dir=eval_output_dir,
        contract=contract,
        mismatches=mismatches,
    )
    if mismatches and not args.allow_target_mismatch:
        raise SystemExit("Canonical Stage E detector target was not met.")


if __name__ == "__main__":
    main()
