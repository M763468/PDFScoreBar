#!/usr/bin/env python3
"""Normalize and evaluate the saved Issue #245 Stage E detector output.

This tool is intended to run inside the same repository-mounted container that
produced the Stage E output.  It does not rerun detector inference.  It:

1. discovers the 68 saved ``pipeline2_no_peak_scored.json`` files;
2. maps them to the canonical Issue #120 full-68 score/page manifest;
3. creates the layout expected by ``eval_full68_from_intermediates``; and
4. evaluates the saved scored/candidate outputs against current GT.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

from tools.issue120.eval_full68_from_intermediates import SCORES, evaluate, format_metric

EXPECTED_PAGES = 68
SCORED_FILE = "pipeline2_no_peak_scored.json"
CANDIDATES_FILE = "pipeline2_no_peak_candidates.json"


def normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def canonical_pages() -> list[tuple[str, str]]:
    return [(score, page) for score, pages in SCORES.items() for page in pages]


def prepare_normalized_tree(*, run_root: Path, normalized_root: Path) -> int:
    scored_paths = sorted(run_root.rglob(SCORED_FILE))
    if len(scored_paths) != EXPECTED_PAGES:
        preview = "\n".join(str(path) for path in scored_paths[:30])
        raise RuntimeError(
            f"Expected {EXPECTED_PAGES} scored files under {run_root}, "
            f"found {len(scored_paths)}.\n{preview}"
        )

    if normalized_root.exists():
        shutil.rmtree(normalized_root)
    normalized_root.mkdir(parents=True)

    mapped = 0
    errors: list[str] = []
    for score, page in canonical_pages():
        token = normalize_token(f"{score}_{page}")
        matches = [
            path
            for path in scored_paths
            if token in normalize_token(str(path.relative_to(run_root)))
        ]
        if len(matches) != 1:
            errors.append(
                f"{score}/{page}: expected one scored match, found {len(matches)}: "
                + ", ".join(str(path) for path in matches)
            )
            continue

        scored_source = matches[0]
        candidates_source = scored_source.parent / CANDIDATES_FILE
        if not candidates_source.is_file():
            errors.append(
                f"{score}/{page}: missing candidates sibling: {candidates_source}"
            )
            continue

        destination = normalized_root / score / page
        destination.mkdir(parents=True, exist_ok=True)
        for source in (scored_source, candidates_source):
            target = destination / source.name
            target.symlink_to(os.path.relpath(source, target.parent))
        mapped += 1

    if errors:
        raise RuntimeError("Failed to normalize Stage E output:\n" + "\n".join(errors))
    if mapped != EXPECTED_PAGES:
        raise RuntimeError(f"Expected {EXPECTED_PAGES} mapped pages, found {mapped}")
    return mapped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-root",
        type=Path,
        default=Path("logs/issue245_accuracy_first_stage_e/stage_e_full_pipeline"),
    )
    parser.add_argument(
        "--normalized-root",
        type=Path,
        default=Path("logs/issue245_accuracy_first_stage_e/eval_input_normalized"),
    )
    parser.add_argument(
        "--gt-root", type=Path, default=Path("data/evaluation2/annotations")
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "logs/issue245_accuracy_first_stage_e/stage_e_full_pipeline/eval_detector"
        ),
    )
    args = parser.parse_args()

    run_root = args.run_root.resolve()
    normalized_root = args.normalized_root.resolve()
    gt_root = args.gt_root.resolve()
    output_dir = args.output_dir.resolve()

    mapped = prepare_normalized_tree(
        run_root=run_root,
        normalized_root=normalized_root,
    )
    if output_dir.exists():
        shutil.rmtree(output_dir)

    contract = evaluate(
        SimpleNamespace(
            results_dir=str(normalized_root),
            gt_root=str(gt_root),
            output_dir=str(output_dir),
            scored_file=SCORED_FILE,
            candidates_file=CANDIDATES_FILE,
            score_threshold=0.1,
            rule_name="center_anchor",
            vov_threshold=0.5,
            xdist_threshold=12.0,
            allow_partial=False,
            measure_summary_json=None,
        )
    )
    summary = contract.detector_summary
    print(f"Normalized pages: {mapped}/{EXPECTED_PAGES}")
    print(f"Pages: {summary.page_count}/{summary.expected_page_count}")
    print(
        "Detector: "
        f"GT={summary.gt} Pred={summary.pred} TP={summary.tp} "
        f"FP={summary.fp} FN={summary.fn} "
        f"FN_det={summary.fn_det} FN_cnn={summary.fn_cnn} "
        f"Precision={format_metric(summary.precision)} "
        f"Recall={format_metric(summary.recall)}"
    )
    print(f"Wrote: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
