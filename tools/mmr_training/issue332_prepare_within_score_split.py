#!/usr/bin/env python3
"""Prepare the primary deterministic within-score grouped split for Issue #332."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.mmr_training.issue332.geometry_training import (
    DEFAULT_EXCLUDED_TAGS,
    DEFAULT_SPLIT_SEED,
    WITHIN_SCORE_SPLIT_MODE,
    prepare_split_contract,
    sha256_file,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--acceptance-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=DEFAULT_SPLIT_SEED)
    parser.add_argument("--validation-ratio", type=float, default=0.125)
    parser.add_argument("--test-ratio", type=float, default=0.125)
    parser.add_argument("--excluded-tag", action="append", default=list(DEFAULT_EXCLUDED_TAGS))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    _eligible, contract = prepare_split_contract(
        manifest_path=args.manifest,
        split_path=args.output,
        acceptance_manifest_path=args.acceptance_manifest,
        excluded_tags=args.excluded_tag,
        seed=args.seed,
        validation_ratio=args.validation_ratio,
        test_ratio=args.test_ratio,
        group_level="page",
        fallback_group_level="system",
        split_mode=WITHIN_SCORE_SPLIT_MODE,
    )
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "split_sha256": sha256_file(args.output),
                "split_mode": contract["split_mode"],
                "counts": contract["counts"],
                "score_coverage": contract["score_coverage"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
