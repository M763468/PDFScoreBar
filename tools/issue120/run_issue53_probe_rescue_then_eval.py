#!/usr/bin/env python3
"""Regenerate the Issue #53/#57 probe-rescue candidate layer and evaluate it.

This is the preferred Stage-C candidate-regeneration path for #136.  It mirrors
the historical PR #57 experiment script:

    experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py

but uses the current #134/#136 evaluation wrappers and records the result as a
separate, explicit regeneration attempt.
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
from src.pipeline.steps.probe_scan import run_probe_scan_batch  # noqa: E402


DEFAULT_BANDS_FROM = Path("logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12")
DEFAULT_MODEL = Path(
    "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def canonical_images(image_root: Path) -> list[Path]:
    images: list[Path] = []
    missing: list[str] = []
    for record in iter_manifest():
        path = image_root / record.score / f"{record.page}.png"
        if path.exists():
            images.append(path)
        else:
            missing.append(str(path))
    if missing:
        raise SystemExit("Missing canonical images:\n" + "\n".join(missing))
    return images


def run_probe_regeneration(args: argparse.Namespace) -> int:
    detect_probe_kwargs = {
        "scan_gap_rescue": True,
        "scan_gap_threshold_ratio": 1.5,
        "scan_gap_rescue_min_ratio": 0.3,
        "scan_x_peak_rescue": True,
        "scan_rightmost_rescue": True,
        "divisi_rescue": True,
        "scan_center_on_peak": True,
        "max_per_band": 100,
    }
    images = canonical_images(args.image_root)
    return run_probe_scan_batch(
        images=images,
        output_root=args.output_root,
        bands_from=args.bands_from,
        staff_mask_dir=None,
        clef_mask_dir=None,
        ink_threshold=180,
        min_ratio=0.85,
        min_height_ratio=0.012,
        min_width_ratio=0.0001,
        detect_probe_kwargs=detect_probe_kwargs,
        skip_existing=False,
        enable_heuristic_filters=False,
        disable_seed_splitting=args.disable_seed_splitting,
    )


def run_command(cmd: list[str]) -> None:
    print("+ " + " ".join(str(part) for part in cmd), flush=True)
    subprocess.run(cmd, check=True)


def run_candidate_comparison(args: argparse.Namespace) -> None:
    run_command(
        [
            sys.executable,
            "tools/issue120/compare_candidate_coverage.py",
            "--baseline-dir",
            str(args.baseline_dir),
            "--candidate-dir",
            str(args.output_root),
            "--output-dir",
            str(args.eval_output_dir),
        ]
    )


def run_stage_b_eval(args: argparse.Namespace) -> None:
    cmd = [
        sys.executable,
        "tools/issue120/score_candidates_then_eval_full68.py",
        "--scorer",
        args.scorer,
        "--clean-output",
        "--candidates-dir",
        str(args.output_root),
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
    if args.bands_from:
        cmd.extend(["--bands-from", str(args.bands_from)])
    run_command(cmd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-root", type=Path, default=Path("data/evaluation2/images"))
    parser.add_argument("--gt-root", type=Path, default=Path("data/evaluation2/annotations"))
    parser.add_argument("--bands-from", type=Path, default=DEFAULT_BANDS_FROM)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--baseline-dir", type=Path, default=Path("data/evaluation2/golden_baseline_eval2_bc23deb"))
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/stage_c_issue53_probe_rescue_candidates"),
    )
    parser.add_argument(
        "--scoring-output-dir",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/stage_c_issue53_probe_rescue_scoring"),
    )
    parser.add_argument(
        "--eval-output-dir",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/stage_c_issue53_probe_rescue_eval"),
    )
    parser.add_argument("--scorer", choices=["pipeline", "legacy"], default="pipeline")
    parser.add_argument("--pipeline-nms", action="store_true", default=False)
    parser.add_argument("--score-threshold", type=float, default=0.1)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    parser.add_argument("--disable-seed-splitting", action="store_true")
    parser.add_argument("--skip-probe-regeneration", action="store_true")
    parser.add_argument("--coverage-only", action="store_true")
    parser.add_argument("--no-clean-output", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    required = [args.image_root, args.gt_root, args.bands_from, args.model_path]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing required inputs:\n" + "\n".join(missing))

    if not args.no_clean_output:
        shutil.rmtree(args.output_root, ignore_errors=True)
        shutil.rmtree(args.scoring_output_dir, ignore_errors=True)
        shutil.rmtree(args.eval_output_dir, ignore_errors=True)

    args.output_root.mkdir(parents=True, exist_ok=True)
    args.eval_output_dir.mkdir(parents=True, exist_ok=True)

    provenance = {
        "schema_version": "issue120.issue53_probe_rescue_regen.v1",
        "historical_source": "PR #57 experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py",
        "output_root": str(args.output_root),
        "bands_from": str(args.bands_from),
        "model_path": str(args.model_path),
        "probe_params": {
            "ink_threshold": 180,
            "min_ratio": 0.85,
            "min_height_ratio": 0.012,
            "scan_gap_threshold_ratio": 1.5,
            "scan_gap_rescue_min_ratio": 0.3,
            "max_per_band": 100,
            "disable_seed_splitting": args.disable_seed_splitting,
        },
        "scorer": args.scorer,
        "pipeline_nms": args.pipeline_nms,
    }
    write_json(args.eval_output_dir / "issue53_probe_rescue_regen_provenance.json", provenance)

    if not args.skip_probe_regeneration:
        processed = run_probe_regeneration(args)
        print(f"Issue53-style probe regeneration processed pages: {processed}")

    if args.coverage_only:
        run_candidate_comparison(args)
        return

    # `run_stage_b_eval` uses --clean-output and recreates eval_output_dir.
    # Write candidate coverage after evaluation so the diagnostic artifact is
    # not deleted before downstream Stage-D drift summaries read it.
    run_stage_b_eval(args)
    run_candidate_comparison(args)
    print(f"Issue53-style Stage-C evaluation complete: {args.eval_output_dir}")


if __name__ == "__main__":
    main()
