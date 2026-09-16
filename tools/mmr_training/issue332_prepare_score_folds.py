#!/usr/bin/env python3
"""Prepare deterministic cyclic score-level folds for Issue #332."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.mmr_training.issue332.geometry_training import (
    DEFAULT_EXCLUDED_TAGS,
    DEFAULT_SPLIT_SEED,
    prepare_score_level_folds,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--acceptance-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=DEFAULT_SPLIT_SEED)
    parser.add_argument(
        "--training-profile", choices=("historical", "current"), default="historical"
    )
    parser.add_argument("--excluded-tag", action="append", default=list(DEFAULT_EXCLUDED_TAGS))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    folds = prepare_score_level_folds(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        acceptance_manifest_path=args.acceptance_manifest,
        excluded_tags=args.excluded_tag,
        seed=args.seed,
        training_profile=args.training_profile,
    )
    print(
        json.dumps(
            [
                {
                    "fold_id": fold["fold_id"],
                    "test_score": fold["test_score"],
                    "validation_score": fold["validation_score"],
                    "train_scores": fold["train_scores"],
                    "counts": fold["counts"],
                    "fold_payload_sha256": fold["provenance"]["fold_payload_sha256"],
                }
                for fold in folds
            ],
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
