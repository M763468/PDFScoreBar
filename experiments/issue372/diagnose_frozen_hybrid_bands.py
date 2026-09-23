#!/usr/bin/env python3
"""Diagnose frozen pre-expansion row geometry for Issue #372.

Retained-only diagnostic. No HOMR, probe scan, CNN inference, or full pipeline rerun.

Compare the current CNN geometric-filter bands (rebuilt from post-expansion
filtered candidates) with bands rebuilt only from the pre-expansion current
hybrid boxes. The key questions are:

1. Do the three Shostakovich-Sym5-Va/page_021 blocking barlines pass when row
   geometry is frozen before probe expansion?
2. Would the retained late-raw x4 promotions still pass the same frozen bands?
3. How does canonical GT vertical-band coverage change across full68?

This does not propose a production threshold. It tests the boundary: generated
probe candidates may be classified, but should not be allowed to redefine the
row geometry used to geometrically filter themselves.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.issue372.run_retained_x4_gap_counterfactual import (
    _host_path,
    _load_json,
)
from src.pipeline.probe_detector.bands import build_row_stats
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue120 import eval_full68_from_intermediates as full68_eval

TARGET_SCORE = "Shostakovich-Sym5-Va"
TARGET_PAGE = "page_021"
TARGETS = [
    (1333, 798, 1340, 894),
    (1769, 798, 1778, 896),
    (2749, 802, 2756, 900),
]
VOV_THRESHOLD = 0.5


def _norm(box: Sequence[Any]) -> tuple[int, int, int, int]:
    return tuple(int(round(float(v))) for v in box[:4])  # type: ignore[return-value]


def _bands(boxes: Sequence[Sequence[Any]]) -> list[tuple[int, int]]:
    stats = build_row_stats(boxes, cluster_max_dist=None, min_row_count=1)
    return [(int(row["top"]), int(row["bottom"])) for row in stats]


def _max_vov(box: Sequence[int], bands: Sequence[tuple[int, int]]) -> float:
    y1, y2 = float(box[1]), float(box[3])
    h = max(1.0, y2 - y1)
    best = 0.0
    for by1, by2 in bands:
        overlap = max(0.0, min(y2, float(by2)) - max(y1, float(by1)))
        best = max(best, overlap / h)
    return best


def _load_inventory_record(path: Path, *, page: str) -> Mapping[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("records"), list):
        raise ValueError(f"Invalid inventory: {path}")
    rows = [
        row
        for row in payload["records"]
        if isinstance(row, Mapping) and str(row.get("page")) == page
    ]
    if len(rows) != 1:
        raise ValueError(f"Expected one {page} record in {path}, got {len(rows)}")
    return rows[0]


def _candidate_path(root: Path, score: str, page: str) -> Path:
    direct = root / score / page / "pipeline2_no_peak_candidates.json"
    if direct.is_file():
        return direct
    record = full68_eval.PageRecord(score=score, page=page)
    path = full68_eval.find_page_file(root, record, "pipeline2_no_peak_candidates.json")
    if path is None or not path.is_file():
        raise FileNotFoundError(f"{score}/{page}: candidates under {root}")
    return path


def _candidate_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    return [_norm(box) for box in full68_eval.boxes_from_candidates(_load_json(path))]


def _gt_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    return [_norm(box) for box in full68_eval.boxes_from_gt(_load_json(path))]


def run(args: argparse.Namespace) -> dict[str, Any]:
    x4_run = args.x4_run_root.resolve()
    issue43_root = args.issue43_repo_root.resolve()
    late_report_path = args.late_report.resolve()
    gt_root = args.gt_root.resolve()
    output = args.output.resolve()

    current_filtered_root = x4_run / "control" / "aggregate_filtered_candidates"
    if not current_filtered_root.is_dir():
        raise FileNotFoundError(current_filtered_root)

    late_report = _load_json(late_report_path)
    if not isinstance(late_report, Mapping):
        raise ValueError(f"Invalid late report: {late_report_path}")
    promotion_summary = late_report.get("promotion_summary")
    if not isinstance(promotion_summary, Mapping) or not isinstance(
        promotion_summary.get("per_page"), list
    ):
        raise ValueError(f"Late report lacks promotion_summary.per_page: {late_report_path}")

    promotions_by_page: dict[tuple[str, str], list[tuple[int, int, int, int]]] = {}
    for row in promotion_summary["per_page"]:
        if not isinstance(row, Mapping):
            continue
        key = (str(row["score"]), str(row["page"]))
        promotions_by_page[key] = [
            _norm(box) for box in row.get("promoted_boxes", [])
        ]

    totals = {
        "gt_total": 0,
        "gt_pass_current_filtered_bands": 0,
        "gt_pass_frozen_hybrid_bands": 0,
        "promoted_total": 0,
        "promoted_pass_current_filtered_bands": 0,
        "promoted_pass_frozen_hybrid_bands": 0,
    }
    pages: list[dict[str, Any]] = []

    for score, page_names in full68_eval.SCORES.items():
        inventory = x4_run / "inventories" / "control" / f"{score}.json"
        if not inventory.is_file():
            raise FileNotFoundError(inventory)

        for page in page_names:
            record = _load_inventory_record(inventory, page=page)

            hybrid_raw = Path(str(record["hybrid_predictions"]))
            hybrid_path = (
                hybrid_raw
                if hybrid_raw.is_file()
                else _host_path(hybrid_raw, issue43_root)
            )
            if not hybrid_path.is_file():
                raise FileNotFoundError(hybrid_path)

            hybrid_boxes = [_norm(box) for box in load_json_boxes(hybrid_path)]
            frozen_bands = _bands(hybrid_boxes)

            filtered_path = _candidate_path(current_filtered_root, score, page)
            filtered_boxes = _candidate_boxes(filtered_path)
            current_bands = _bands(filtered_boxes)

            gt_path = gt_root / score / page / "boxes_sorted.json"
            if not gt_path.is_file():
                raise FileNotFoundError(gt_path)
            gt = _gt_boxes(gt_path)

            promoted = promotions_by_page.get((score, page), [])

            gt_current = [_max_vov(box, current_bands) for box in gt]
            gt_frozen = [_max_vov(box, frozen_bands) for box in gt]
            promoted_current = [_max_vov(box, current_bands) for box in promoted]
            promoted_frozen = [_max_vov(box, frozen_bands) for box in promoted]

            totals["gt_total"] += len(gt)
            totals["gt_pass_current_filtered_bands"] += sum(
                value >= VOV_THRESHOLD for value in gt_current
            )
            totals["gt_pass_frozen_hybrid_bands"] += sum(
                value >= VOV_THRESHOLD for value in gt_frozen
            )
            totals["promoted_total"] += len(promoted)
            totals["promoted_pass_current_filtered_bands"] += sum(
                value >= VOV_THRESHOLD for value in promoted_current
            )
            totals["promoted_pass_frozen_hybrid_bands"] += sum(
                value >= VOV_THRESHOLD for value in promoted_frozen
            )

            page_result: dict[str, Any] = {
                "score": score,
                "page": page,
                "hybrid_path": str(hybrid_path),
                "filtered_path": str(filtered_path),
                "frozen_hybrid_bands": frozen_bands,
                "current_filtered_bands": current_bands,
                "gt_count": len(gt),
                "gt_fail_current": sum(value < VOV_THRESHOLD for value in gt_current),
                "gt_fail_frozen": sum(value < VOV_THRESHOLD for value in gt_frozen),
                "promoted_count": len(promoted),
                "promoted_fail_current": sum(
                    value < VOV_THRESHOLD for value in promoted_current
                ),
                "promoted_fail_frozen": sum(
                    value < VOV_THRESHOLD for value in promoted_frozen
                ),
            }

            if score == TARGET_SCORE and page == TARGET_PAGE:
                page_result["target_barlines"] = [
                    {
                        "bbox": list(box),
                        "current_filtered_band_max_vov": _max_vov(box, current_bands),
                        "frozen_hybrid_band_max_vov": _max_vov(box, frozen_bands),
                        "passes_current": _max_vov(box, current_bands) >= VOV_THRESHOLD,
                        "passes_frozen": _max_vov(box, frozen_bands) >= VOV_THRESHOLD,
                    }
                    for box in TARGETS
                ]
                page_result["nearby_current_bands"] = [
                    list(band)
                    for band in current_bands
                    if band[1] >= 700 and band[0] <= 950
                ]
                page_result["nearby_frozen_bands"] = [
                    list(band)
                    for band in frozen_bands
                    if band[1] >= 700 and band[0] <= 950
                ]

            pages.append(page_result)

    if len(pages) != 68:
        raise RuntimeError(f"Expected 68 pages, got {len(pages)}")

    target_page = next(
        row for row in pages
        if row["score"] == TARGET_SCORE and row["page"] == TARGET_PAGE
    )

    promotion_fail_frozen = [
        row for row in pages if int(row["promoted_fail_frozen"]) > 0
    ]
    gt_regressions = [
        row for row in pages
        if int(row["gt_fail_frozen"]) > int(row["gt_fail_current"])
    ]
    gt_improvements = [
        row for row in pages
        if int(row["gt_fail_frozen"]) < int(row["gt_fail_current"])
    ]

    report = {
        "schema_version": "issue372.frozen_hybrid_band_diagnostic.v1",
        "contract": {
            "retained_only": True,
            "inference_rerun": False,
            "production_change": False,
            "vov_threshold": VOV_THRESHOLD,
            "band_builder": "build_row_stats(cluster_max_dist=None,min_row_count=1)",
            "current_band_source": "post-expansion filtered candidates",
            "frozen_band_source": "pre-expansion current hybrid predictions",
        },
        "inputs": {
            "x4_run_root": str(x4_run),
            "issue43_repo_root": str(issue43_root),
            "late_report": str(late_report_path),
            "gt_root": str(gt_root),
        },
        "summary": {
            **totals,
            "pages_with_promoted_fail_frozen": len(promotion_fail_frozen),
            "pages_with_more_gt_band_failures_under_frozen": len(gt_regressions),
            "pages_with_fewer_gt_band_failures_under_frozen": len(gt_improvements),
        },
        "page021": target_page,
        "promotion_fail_frozen_pages": promotion_fail_frozen,
        "gt_regression_pages": gt_regressions,
        "gt_improvement_pages": gt_improvements,
        "pages": pages,
    }

    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("=== Issue #372 frozen hybrid-band diagnostic ===")
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    print("\n=== page_021 ===")
    print("current bands:", target_page["nearby_current_bands"])
    print("frozen bands :", target_page["nearby_frozen_bands"])
    for row in target_page["target_barlines"]:
        print(
            f"{row['bbox']} current_vov={row['current_filtered_band_max_vov']:.6f} "
            f"current_pass={row['passes_current']} "
            f"frozen_vov={row['frozen_hybrid_band_max_vov']:.6f} "
            f"frozen_pass={row['passes_frozen']}"
        )

    print("\n=== promoted boxes failing frozen bands ===")
    if not promotion_fail_frozen:
        print("none")
    else:
        for row in promotion_fail_frozen:
            print(
                f"{row['score']}/{row['page']} "
                f"promoted={row['promoted_count']} "
                f"fail_frozen={row['promoted_fail_frozen']} "
                f"fail_current={row['promoted_fail_current']}"
            )

    print("\n=== pages with more GT band failures under frozen bands ===")
    if not gt_regressions:
        print("none")
    else:
        for row in gt_regressions:
            print(
                f"{row['score']}/{row['page']} "
                f"current_fail={row['gt_fail_current']} frozen_fail={row['gt_fail_frozen']}"
            )

    print(f"\nOUTPUT={output}")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--x4-run-root", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument("--late-report", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    run(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
