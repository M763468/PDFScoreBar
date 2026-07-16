#!/usr/bin/env python3
"""Recompute Issue #245 mixed-route comparisons with the hybrid JSON schema.

The preparation step writes hybrid files as top-level box arrays. The evaluator probe
loader only accepts ``{"predictions": ...}`` payloads, so using it directly can
silently report zero-versus-zero equality. This validator reads hybrid boxes through
the production consensus loader, recomputes all 68 comparisons, and rejects empty or
incomplete evidence.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterable, Sequence

from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue245.run_pdfscore_evaluator_ref_probe import compare_records

DEFAULT_MAIN_REPO = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
DEFAULT_REPORT = Path(
    "logs/issue245_accuracy_first_mixed_route/accuracy_first_mixed_route_report.json"
)
EXPECTED_PAGES = 68
EXPECTED_HISTORICAL_HYBRID_COUNT = 3312


def resolve_repo_path(main_repo: Path, raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else main_repo / path


def records_from_boxes(boxes: Iterable[Sequence[int]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, value in enumerate(boxes):
        if len(value) != 4:
            continue
        x1, y1, x2, y2 = (float(part) for part in value)
        records.append(
            {
                "index": index,
                "box": [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)],
                "system_index": None,
                "staff_index": None,
            }
        )
    return records


def load_hybrid_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Hybrid JSON is missing: {path}")
    return records_from_boxes(load_json_boxes(path))


def aggregate_comparisons(pages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "pages": len(pages),
        "pages_semantic_equal": sum(
            bool(page["comparison"]["semantic_equal"]) for page in pages
        ),
        "pages_different": sum(
            not bool(page["comparison"]["semantic_equal"]) for page in pages
        ),
        "historical_count": sum(page["comparison"]["left"]["count"] for page in pages),
        "mixed_count": sum(page["comparison"]["right"]["count"] for page in pages),
        "matched_count": sum(page["comparison"]["matched_count"] for page in pages),
        "historical_only_count": sum(
            page["comparison"]["left_only"]["count"] for page in pages
        ),
        "mixed_only_count": sum(
            page["comparison"]["right_only"]["count"] for page in pages
        ),
        "differing_pages": [
            f"{page['score']}/{page['page']}"
            for page in pages
            if not page["comparison"]["semantic_equal"]
        ],
    }


def validate_report(main_repo: Path, report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    pages = report.get("pages")
    if not isinstance(pages, list) or len(pages) != EXPECTED_PAGES:
        raise RuntimeError(
            f"Expected {EXPECTED_PAGES} prepared pages, found "
            f"{len(pages) if isinstance(pages, list) else 'invalid'}"
        )

    validated_pages: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict):
            raise ValueError("Prepared page result must be an object")
        historical_path = resolve_repo_path(main_repo, str(page["historical_hybrid"]))
        mixed_path = resolve_repo_path(main_repo, str(page["mixed_hybrid"]))
        comparison = compare_records(
            load_hybrid_records(historical_path),
            load_hybrid_records(mixed_path),
        )
        validated = dict(page)
        validated["comparison"] = comparison
        validated_pages.append(validated)

    aggregate = aggregate_comparisons(validated_pages)
    if aggregate["historical_count"] != EXPECTED_HISTORICAL_HYBRID_COUNT:
        raise RuntimeError(
            "Historical hybrid count does not match the accepted full-68 inventory: "
            f"expected={EXPECTED_HISTORICAL_HYBRID_COUNT} "
            f"actual={aggregate['historical_count']}"
        )
    if aggregate["mixed_count"] <= 0:
        raise RuntimeError("Mixed hybrid comparison produced no boxes")

    page_001 = next(
        page
        for page in validated_pages
        if page["score"] == "Va_Prokofiev_Symphony1" and page["page"] == "page_001"
    )
    report.update(
        {
            "status": "completed",
            "comparison_validation": {
                "status": "validated",
                "loader": "src.pipeline.steps.hybrid_consensus.load_json_boxes",
                "expected_pages": EXPECTED_PAGES,
                "expected_historical_hybrid_count": EXPECTED_HISTORICAL_HYBRID_COUNT,
                "zero_vs_zero_comparison_rejected": True,
            },
            "aggregate_comparison_to_historical_hybrid": aggregate,
            "page_001_comparison_to_historical_hybrid": page_001,
            "pages": validated_pages,
        }
    )
    report.pop("error_type", None)
    report.pop("error", None)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--main-repo-root",
        type=Path,
        default=Path(os.environ.get("ISSUE245_MAIN_REPO_ROOT", DEFAULT_MAIN_REPO)),
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    main_repo = args.main_repo_root.expanduser().resolve()
    report_path = resolve_repo_path(main_repo, args.report)
    try:
        report = validate_report(main_repo, report_path)
    except Exception as error:
        original = json.loads(report_path.read_text(encoding="utf-8"))
        original.update(
            {
                "status": "failed",
                "comparison_validation": {
                    "status": "failed",
                    "zero_vs_zero_comparison_rejected": True,
                },
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
        report_path.write_text(
            json.dumps(original, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Report: {report_path}")
        return 1

    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
