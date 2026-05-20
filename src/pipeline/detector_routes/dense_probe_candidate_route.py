"""Dense probe-candidate detector route entrypoint.

This is a detector-level partial pipeline route:

    dense candidate/bands generation -> clef-mask-aware filtering
      -> probe-rescue candidate generation -> CNN scoring -> detector eval

It does not run slow HOMR/SR/OMR upstream generation and it does not run
downstream measure numbering.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.pipeline.detector_routes.dense_probe_candidate import (
    DenseProbeCandidateConfig,
    config_from_yaml,
    resolve_paths,
    run_dense_probe_candidate_route,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/detector_routes/issue120_dense_probe_candidate_route.yaml"),
        help="Route config YAML. All regular route inputs should be specified here.",
    )
    parser.add_argument(
        "--require-detector-target",
        action="store_true",
        help="Fail unless detector TP/FP/FN equals the configured Issue120 target.",
    )
    parser.add_argument(
        "--no-clean-output",
        action="store_true",
        help="Do not delete existing route artifacts before running.",
    )
    parser.add_argument(
        "--skip-issue36-regeneration",
        action="store_true",
        help="Reuse existing dense raw/filtered roots from the configured output root.",
    )
    parser.add_argument(
        "--skip-probe-rescue-regeneration",
        action="store_true",
        help="Reuse existing probe-rescue candidates from the configured output root.",
    )
    parser.add_argument(
        "--skip-existing-probe-rescue",
        action="store_true",
        help="Skip per-page probe-rescue candidate files that already exist.",
    )
    return parser


def apply_cli_overrides(
    config: DenseProbeCandidateConfig, args: argparse.Namespace
) -> DenseProbeCandidateConfig:
    values = config.__dict__.copy()
    if args.require_detector_target:
        values["require_detector_target"] = True
    if args.no_clean_output:
        values["no_clean_output"] = True
    if args.skip_issue36_regeneration:
        values["skip_issue36_regeneration"] = True
    if args.skip_probe_rescue_regeneration:
        values["skip_probe_rescue_regeneration"] = True
    if args.skip_existing_probe_rescue:
        values["skip_existing_probe_rescue"] = True
    return DenseProbeCandidateConfig(**values)


def main() -> None:
    args = build_parser().parse_args()
    config = apply_cli_overrides(config_from_yaml(args.config), args)
    summary = run_dense_probe_candidate_route(config)
    paths = resolve_paths(config)
    print(f"Dense probe-candidate route complete: {paths.eval_output_dir}")
    if summary:
        print(
            "Detector: "
            f"TP={summary.get('tp')} FP={summary.get('fp')} FN={summary.get('fn')} "
            f"Pred={summary.get('pred')} GT={summary.get('gt')}"
        )


if __name__ == "__main__":
    main()
