#!/usr/bin/env python3
"""Validate the full-68 canonical and retained-baseline inventory before inference."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from tools.issue245.run_fresh_upstream_full68_probe import (
    DEFAULT_HISTORICAL_RUN_DATE,
    DEFAULT_MAIN_REPO,
    EXPECTED_PAGE_COUNT,
    IMAGE_ROOT_REL,
    build_inventory,
    discover_canonical_images,
)
from tools.issue245.run_pdfscore_evaluator_ref_probe import load_records

EXPECTED_HISTORICAL_DETECTION_COUNT = 4381


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--main-repo-root",
        type=Path,
        default=Path(os.environ.get("ISSUE245_MAIN_REPO_ROOT", DEFAULT_MAIN_REPO)),
    )
    parser.add_argument(
        "--historical-run-date",
        default=DEFAULT_HISTORICAL_RUN_DATE,
    )
    parser.add_argument("--expected-pages", type=int, default=EXPECTED_PAGE_COUNT)
    args, _unknown = parser.parse_known_args()

    main_repo = args.main_repo_root.expanduser().resolve()
    image_root = main_repo / IMAGE_ROOT_REL
    images = discover_canonical_images(image_root)
    if len(images) != args.expected_pages:
        raise RuntimeError(
            f"Expected {args.expected_pages} canonical images, found {len(images)}"
        )

    inventory = build_inventory(main_repo, images, args.historical_run_date)
    historical_count = sum(
        len(load_records(Path(str(item["historical_detection"]))))
        for item in inventory
    )
    if historical_count != EXPECTED_HISTORICAL_DETECTION_COUNT:
        raise RuntimeError(
            "Retained baseline count mismatch: "
            f"expected={EXPECTED_HISTORICAL_DETECTION_COUNT} actual={historical_count}"
        )

    print(
        json.dumps(
            {
                "status": "validated",
                "canonical_pages": len(images),
                "historical_pages": len(inventory),
                "historical_detection_count": historical_count,
                "historical_run_date": args.historical_run_date,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
