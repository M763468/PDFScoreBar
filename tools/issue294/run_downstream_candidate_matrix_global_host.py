#!/usr/bin/env python3
"""Run the Issue #294 downstream matrix for one canonical full-68 global page ID.

The #274 risk IDs (for example ``page_045``) are global evaluation IDs, not
physical page numbers within the representative Shostakovich score.  Resolve the
requested ID through the retained canonical 68-page index before delegating to
the existing Issue #294 downstream matrix host.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue294 import run_downstream_candidate_matrix_host as matrix_host
from tools.issue294 import run_same_original_ab_host as base

GLOBAL_PAGE_RE = re.compile(r"^page_(\d{3})$")


def _resolve_global_page(page_id: str) -> dict[str, Any]:
    match = GLOBAL_PAGE_RE.fullmatch(page_id)
    if match is None:
        raise ValueError(f"Expected global page ID page_001..page_068, got {page_id!r}")
    number = int(match.group(1))
    if not 1 <= number <= 68:
        raise ValueError(f"Global page ID out of range: {page_id}")

    # Import lazily: build_page_specs() consumes the operator-local retained
    # legacy page index under logs/, which is intentionally not a tracked file.
    from tools.issue264.run_phase_c_mmr_regression import build_page_specs

    specs = build_page_specs()
    by_id = {spec.page_id: spec for spec in specs}
    if len(by_id) != 68 or set(by_id) != {f"page_{index:03d}" for index in range(1, 69)}:
        raise RuntimeError("Canonical evaluation mapping is not the unique page_001..page_068 set")
    spec = by_id[page_id]
    if not spec.image.is_file():
        raise FileNotFoundError(spec.image)

    physical = spec.page_name.removeprefix("page_")
    if not physical.isdigit() or len(physical) != 3:
        raise RuntimeError(f"Unexpected physical page name for {page_id}: {spec.page_name}")
    return {
        "global_page_id": page_id,
        "global_index": int(spec.global_index),
        "score": str(spec.score),
        "page_name": str(spec.page_name),
        "physical_page": physical,
        "image": str(spec.image.resolve()),
        "image_stem": str(spec.image_stem),
    }


def run(
    *,
    run_tag: str,
    global_page: str,
    latest_commit: str | None,
    resolve_only: bool,
) -> dict[str, Any]:
    mapping = _resolve_global_page(global_page)
    if resolve_only:
        return {"status": "completed", "mapping": mapping, "matrix": None}

    # The existing same-original host intentionally accepts only an explicitly
    # allowed physical page within one SCORE.  Patch those two experiment-only
    # selectors for this one process after canonical mapping has been resolved.
    previous_score = base.SCORE
    previous_allowed = base.ALLOWED_PAGES
    base.SCORE = str(mapping["score"])
    base.ALLOWED_PAGES = {str(mapping["physical_page"])}
    try:
        result = matrix_host.run(
            run_tag,
            [str(mapping["physical_page"])],
            latest_commit,
        )
    finally:
        base.SCORE = previous_score
        base.ALLOWED_PAGES = previous_allowed

    return {"status": "completed", "mapping": mapping, "matrix": result}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag")
    parser.add_argument("--global-page", required=True)
    parser.add_argument("--latest-homr-commit")
    parser.add_argument(
        "--resolve-only",
        action="store_true",
        help="Resolve and validate the global ID without running HOMR/SR/OMR/CNN work.",
    )
    args = parser.parse_args()
    try:
        if not args.resolve_only and not args.run_tag:
            parser.error("--run-tag is required unless --resolve-only")
        payload = run(
            run_tag=args.run_tag or "resolve-only",
            global_page=args.global_page,
            latest_commit=args.latest_homr_commit,
            resolve_only=args.resolve_only,
        )
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
