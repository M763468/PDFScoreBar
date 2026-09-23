#!/usr/bin/env python3
"""Check whether late-raw recovered current FNs survive frozen hybrid bands.

Retained-only Issue #372 diagnostic. No inference or detector regeneration.

For the canonical full68/current-unit matcher:
1. identify GT barlines that are FN in current control output;
2. identify which of those are present in retained late-raw final output;
3. test the matching late-raw final predictions against row bands built only
   from the pre-expansion current hybrid predictions.

This directly tests compatibility between the 27-FN late-raw recovery path and
the proposed "freeze row geometry before probe expansion" boundary.
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
from src.common.barline_evaluation import (
    CENTER_ANCHOR_XDIST_UNIT_RATIO,
    greedy_barline_match,
    is_barline_match,
)
from src.common.barline_units import load_page_staff_units, require_page_staff_unit
from src.pipeline.probe_detector.bands import build_row_stats
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue120 import eval_full68_from_intermediates as full68_eval

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


def _page_file(root: Path, score: str, page: str, filename: str) -> Path:
    direct = root / score / page / filename
    if direct.is_file():
        return direct
    record = full68_eval.PageRecord(score=score, page=page)
    resolved = full68_eval.find_page_file(root, record, filename)
    if resolved is None or not resolved.is_file():
        raise FileNotFoundError(f"{score}/{page}: {filename} under {root}")
    return resolved


def _scored_boxes(path: Path, threshold: float) -> list[tuple[int, int, int, int]]:
    return [
        _norm(box)
        for box in full68_eval.boxes_from_scored(_load_json(path), score_threshold=threshold)
    ]


def _gt_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    return [_norm(box) for box in full68_eval.boxes_from_gt(_load_json(path))]


def _matches(
    pred: Sequence[int],
    gt: Sequence[int],
    *,
    unit_size: float,
) -> bool:
    return is_barline_match(
        pred,
        gt,
        rule_name="center_anchor",
        vov_threshold=VOV_THRESHOLD,
        xdist_threshold=None,
        unit_size=unit_size,
        xdist_unit_ratio=CENTER_ANCHOR_XDIST_UNIT_RATIO,
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    x4_run = args.x4_run_root.resolve()
    issue43_root = args.issue43_repo_root.resolve()
    late_report_path = args.late_report.resolve()
    gt_root = args.gt_root.resolve()
    staff_units_path = args.staff_units_json.resolve()
    output = args.output.resolve()

    current_root = x4_run / "control" / "aggregate_probe_output"
    if not current_root.is_dir():
        raise FileNotFoundError(current_root)

    late_report = _load_json(late_report_path)
    if not isinstance(late_report, Mapping):
        raise ValueError(f"Invalid late report: {late_report_path}")
    late = late_report.get("late_raw_x4")
    contract = late_report.get("contract")
    if not isinstance(late, Mapping) or not isinstance(contract, Mapping):
        raise ValueError(f"Late report lacks late_raw_x4/contract: {late_report_path}")

    late_root = Path(str(late["aggregate_probe"]))
    if not late_root.is_dir():
        raise FileNotFoundError(late_root)
    threshold = float(contract["cnn_threshold"])

    units = load_page_staff_units(staff_units_path)

    recovered_rows: list[dict[str, Any]] = []
    totals = {
        "current_fn": 0,
        "current_fn_recovered_by_late": 0,
        "recovered_with_matching_late_pred_passing_frozen_band": 0,
        "recovered_without_matching_late_pred_passing_frozen_band": 0,
    }

    for score, pages in full68_eval.SCORES.items():
        inventory = x4_run / "inventories" / "control" / f"{score}.json"
        if not inventory.is_file():
            raise FileNotFoundError(inventory)

        for page in pages:
            gt_path = gt_root / score / page / "boxes_sorted.json"
            if not gt_path.is_file():
                raise FileNotFoundError(gt_path)
            gt = _gt_boxes(gt_path)

            current_path = _page_file(
                current_root, score, page, "pipeline2_no_peak_filtered_cnn.json"
            )
            late_path = _page_file(
                late_root, score, page, "pipeline2_no_peak_filtered_cnn.json"
            )
            current_preds = _scored_boxes(current_path, threshold)
            late_preds = _scored_boxes(late_path, threshold)

            page_unit = require_page_staff_unit(units, score, page)
            unit_size = float(page_unit.unit_size)

            current_match = greedy_barline_match(
                current_preds,
                gt,
                rule_name="center_anchor",
                vov_threshold=VOV_THRESHOLD,
                xdist_threshold=None,
                unit_size=unit_size,
                xdist_unit_ratio=CENTER_ANCHOR_XDIST_UNIT_RATIO,
            )
            current_fn_indices = list(current_match.false_negative_indices)
            totals["current_fn"] += len(current_fn_indices)

            record = _load_inventory_record(inventory, page=page)
            hybrid_raw = Path(str(record["hybrid_predictions"]))
            hybrid_path = (
                hybrid_raw if hybrid_raw.is_file() else _host_path(hybrid_raw, issue43_root)
            )
            if not hybrid_path.is_file():
                raise FileNotFoundError(hybrid_path)
            frozen_bands = _bands([_norm(box) for box in load_json_boxes(hybrid_path)])

            for gt_index in current_fn_indices:
                target = gt[gt_index]
                matching_late = [
                    pred
                    for pred in late_preds
                    if _matches(pred, target, unit_size=unit_size)
                ]
                if not matching_late:
                    continue

                totals["current_fn_recovered_by_late"] += 1
                pred_vovs = [_max_vov(pred, frozen_bands) for pred in matching_late]
                passes = any(vov >= VOV_THRESHOLD for vov in pred_vovs)
                if passes:
                    totals[
                        "recovered_with_matching_late_pred_passing_frozen_band"
                    ] += 1
                else:
                    totals[
                        "recovered_without_matching_late_pred_passing_frozen_band"
                    ] += 1

                recovered_rows.append(
                    {
                        "score": score,
                        "page": page,
                        "gt_index": int(gt_index),
                        "gt_bbox": list(target),
                        "gt_frozen_band_max_vov": _max_vov(target, frozen_bands),
                        "matching_late_predictions": [
                            {
                                "bbox": list(pred),
                                "frozen_band_max_vov": vov,
                                "passes_frozen_band": vov >= VOV_THRESHOLD,
                            }
                            for pred, vov in zip(matching_late, pred_vovs)
                        ],
                        "has_matching_late_prediction_passing_frozen_band": passes,
                    }
                )

    failures = [
        row
        for row in recovered_rows
        if not row["has_matching_late_prediction_passing_frozen_band"]
    ]

    report = {
        "schema_version": "issue372.late_recovery_frozen_band_compat.v1",
        "contract": {
            "retained_only": True,
            "inference_rerun": False,
            "matcher": "center_anchor current-unit",
            "vov_threshold": VOV_THRESHOLD,
            "xdist_unit_ratio": CENTER_ANCHOR_XDIST_UNIT_RATIO,
            "frozen_band_source": "pre-expansion current hybrid predictions",
            "cnn_threshold": threshold,
        },
        "inputs": {
            "current_root": str(current_root),
            "late_root": str(late_root),
            "late_report": str(late_report_path),
            "gt_root": str(gt_root),
            "staff_units_json": str(staff_units_path),
        },
        "summary": totals,
        "failures": failures,
        "recovered": recovered_rows,
    }

    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("=== Issue #372 late recovery vs frozen bands ===")
    print(json.dumps(totals, indent=2, ensure_ascii=False))
    print("\n=== recovered rows failing frozen bands ===")
    if not failures:
        print("none")
    else:
        for row in failures:
            print(
                f"{row['score']}/{row['page']} gt={row['gt_bbox']} "
                f"gt_vov={row['gt_frozen_band_max_vov']:.6f} "
                f"late={row['matching_late_predictions']}"
            )

    print("\n=== recovered rows ===")
    for row in recovered_rows:
        best = max(
            pred["frozen_band_max_vov"]
            for pred in row["matching_late_predictions"]
        )
        print(
            f"{row['score']}/{row['page']} gt={row['gt_bbox']} "
            f"gt_vov={row['gt_frozen_band_max_vov']:.6f} "
            f"best_late_pred_vov={best:.6f}"
        )

    print(f"\nOUTPUT={output}")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--x4-run-root", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument("--late-report", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, required=True)
    parser.add_argument("--staff-units-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    run(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
