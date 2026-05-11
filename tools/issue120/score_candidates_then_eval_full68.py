#!/usr/bin/env python3
"""Stage-B verifier for Issue #120: candidates -> CNN scoring -> full68 eval.

This tool copies canonical 68-page candidate intermediates into a fresh scoring
work directory, runs the current in-process CNN scoring implementation, then
invokes the #134 evaluator on the scored outputs.

It intentionally starts from `pipeline2_no_peak_candidates.json`; it does not
regenerate candidates from HOMR/OMR/SR/hybrid/probe sources.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.core.run_ids import build_probe_run_id_from_parts  # noqa: E402
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch  # noqa: E402
from tools.issue120.eval_full68_from_intermediates import (  # noqa: E402
    PageRecord,
    find_page_file,
    iter_manifest,
)


DEFAULT_MODEL = Path(
    "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def collect_images(image_root: Path, manifest: list[PageRecord]) -> list[Path]:
    images: list[Path] = []
    missing: list[str] = []
    for record in manifest:
        path = image_root / record.score / f"{record.page}.png"
        if not path.exists():
            missing.append(str(path))
        else:
            images.append(path)
    if missing:
        raise SystemExit("Missing canonical images:\n" + "\n".join(missing))
    return images


def copy_candidates(
    *,
    candidates_dir: Path,
    scoring_root: Path,
    manifest: list[PageRecord],
    candidates_file: str,
) -> list[dict[str, str]]:
    copied: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    for record in manifest:
        src = find_page_file(candidates_dir, record, candidates_file)
        if src is None:
            missing.append(asdict(record))
            continue
        run_id = build_probe_run_id_from_parts(record.score, record.page)
        dest_dir = scoring_root / run_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "pipeline2_no_peak_candidates.json"
        shutil.copy2(src, dest)
        copied.append({"score": record.score, "page": record.page, "src": str(src), "dest": str(dest)})
    if missing:
        write_json(scoring_root / "missing_candidate_pages.json", missing)
        raise SystemExit(
            f"Missing {len(missing)} candidate files. See {scoring_root / 'missing_candidate_pages.json'}"
        )
    write_json(scoring_root / "copied_candidates.json", copied)
    return copied


def build_provenance(args: argparse.Namespace, processed_pages: int) -> dict[str, Any]:
    return {
        "schema_version": "issue120.intermediate_provenance.v1",
        "status": "stage_b_candidate_to_cnn_scoring",
        "evaluated_stage": "post_cnn_scoring_detector_intermediate",
        "candidate_source_dir": str(args.candidates_dir),
        "scoring_output_dir": str(args.scoring_output_dir),
        "model_path": str(args.model_path),
        "bands_from": str(args.bands_from) if args.bands_from else None,
        "staff_mask_dir": str(args.staff_mask_dir) if args.staff_mask_dir else None,
        "processed_pages": processed_pages,
        "score_threshold": args.score_threshold,
        "staff_vov_threshold": args.staff_vov_threshold,
        "crop_recenter_on_bbox_ink": args.crop_recenter_on_bbox_ink,
        "crop_recenter_max_shift_unit_ratio": args.crop_recenter_max_shift_unit_ratio,
        "input_image_scale": args.input_image_scale,
        "notes": [
            "Stage B starts from existing candidates and reruns CNN scoring only.",
            "It does not regenerate candidates from HOMR/OMR/SR/hybrid/probe sources.",
        ],
    }


def run_eval(args: argparse.Namespace, provenance_path: Path) -> None:
    cmd = [
        sys.executable,
        "tools/issue120/eval_full68_from_intermediates.py",
        "--results-dir",
        str(args.scoring_output_dir),
        "--gt-root",
        str(args.gt_root),
        "--output-dir",
        str(args.eval_output_dir),
        "--score-threshold",
        str(args.score_threshold),
        "--xdist-threshold",
        str(args.xdist_threshold),
    ]
    subprocess.run(cmd, check=True)
    subprocess.run(
        [
            sys.executable,
            "tools/issue120/attach_eval_provenance.py",
            "--output-dir",
            str(args.eval_output_dir),
            "--results-dir",
            str(args.scoring_output_dir),
            "--provenance-json",
            str(provenance_path),
        ],
        check=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidates-dir",
        type=Path,
        default=Path("data/evaluation2/golden_baseline_eval2_bc23deb"),
        help="Root containing canonical 68-page pipeline2_no_peak_candidates.json files.",
    )
    parser.add_argument(
        "--image-root",
        type=Path,
        default=Path("data/evaluation2/images"),
        help="Root containing evaluation2 page images.",
    )
    parser.add_argument(
        "--gt-root",
        type=Path,
        default=Path("data/evaluation2/annotations"),
        help="Root containing evaluation2 GT annotations.",
    )
    parser.add_argument(
        "--scoring-output-dir",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/stage_b_candidate_scoring"),
        help="Work directory for copied candidates and newly scored outputs.",
    )
    parser.add_argument(
        "--eval-output-dir",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/stage_b_candidate_scoring_eval"),
        help="Output directory for canonical full68 evaluation results.",
    )
    parser.add_argument("--candidates-file", default="pipeline2_no_peak_candidates.json")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--bands-from", type=Path, default=None)
    parser.add_argument("--staff-mask-dir", type=Path, default=None)
    parser.add_argument("--score-threshold", type=float, default=0.1)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    parser.add_argument("--staff-vov-threshold", type=float, default=0.5)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--crop-recenter-on-bbox-ink", action="store_true", default=True)
    parser.add_argument("--no-crop-recenter-on-bbox-ink", dest="crop_recenter_on_bbox_ink", action="store_false")
    parser.add_argument("--crop-recenter-max-shift-unit-ratio", type=float, default=0.35)
    parser.add_argument("--input-image-scale", type=float, default=1.0)
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="Delete scoring/eval output directories before running.",
    )
    parser.add_argument(
        "--skip-scoring",
        action="store_true",
        help="Only run canonical evaluation against an existing scoring output directory.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    manifest = iter_manifest()

    if args.clean_output:
        shutil.rmtree(args.scoring_output_dir, ignore_errors=True)
        shutil.rmtree(args.eval_output_dir, ignore_errors=True)

    args.scoring_output_dir.mkdir(parents=True, exist_ok=True)
    args.eval_output_dir.mkdir(parents=True, exist_ok=True)

    images = collect_images(args.image_root, manifest)

    if not args.skip_scoring:
        if not args.model_path.exists():
            raise SystemExit(
                f"Model not found: {args.model_path}\n"
                "Provide --model-path or restore the expected CNN model artifact."
            )
        copy_candidates(
            candidates_dir=args.candidates_dir,
            scoring_root=args.scoring_output_dir,
            manifest=manifest,
            candidates_file=args.candidates_file,
        )
        processed_pages = run_cnn_scoring_batch(
            probe_output_root=args.scoring_output_dir,
            images=images,
            model_path=args.model_path,
            threshold=args.score_threshold,
            batch_size=args.batch_size,
            staff_mask_dir=args.staff_mask_dir,
            bands_from=args.bands_from,
            staff_vov_threshold=args.staff_vov_threshold,
            crop_recenter_on_bbox_ink=args.crop_recenter_on_bbox_ink,
            crop_recenter_max_shift_unit_ratio=args.crop_recenter_max_shift_unit_ratio,
            input_image_scale=args.input_image_scale,
        )
    else:
        processed_pages = 0

    provenance = build_provenance(args, processed_pages)
    provenance_path = args.eval_output_dir / "stage_b_provenance.json"
    write_json(provenance_path, provenance)
    run_eval(args, provenance_path)
    print(f"Stage-B evaluation complete: {args.eval_output_dir}")


if __name__ == "__main__":
    main()
