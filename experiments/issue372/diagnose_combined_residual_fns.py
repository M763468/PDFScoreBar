#!/usr/bin/env python3
"""Inspect residual FNs in an Issue #372 combined retained counterfactual.

No inference or candidate regeneration. Reads the already-produced combined
aggregate probe output and evaluates the canonical current-unit matcher. For
each residual FN, report:
- whether a matching candidate exists before CNN/geometric filtering;
- best matching scored candidate and score;
- whether the same GT was present in the retained late-raw reference final;
- whether the GT passes frozen hybrid row bands.

Also report exact presence of the three page_021 blocking bboxes.
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

from experiments.issue372.run_retained_x4_gap_counterfactual import _host_path, _load_json
from src.common.barline_evaluation import (
    CENTER_ANCHOR_XDIST_UNIT_RATIO,
    greedy_barline_match,
    is_barline_match,
)
from src.common.barline_units import load_page_staff_units, require_page_staff_unit
from src.pipeline.probe_detector.bands import build_row_stats
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue120 import eval_full68_from_intermediates as full68_eval

VOV = 0.5
TARGET_SCORE = "Shostakovich-Sym5-Va"
TARGET_PAGE = "page_021"
TARGETS = [
    (1333, 798, 1340, 894),
    (1769, 798, 1778, 896),
    (2749, 802, 2756, 900),
]


def _norm(box: Sequence[Any]) -> tuple[int, int, int, int]:
    return tuple(int(round(float(v))) for v in box[:4])  # type: ignore[return-value]


def _find(root: Path, score: str, page: str, filename: str) -> Path:
    record = full68_eval.PageRecord(score=score, page=page)
    path = full68_eval.find_page_file(root, record, filename)
    if path is None or not path.is_file():
        raise FileNotFoundError(f"{score}/{page}: {filename} under {root}")
    return path


def _final_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    return [_norm(box) for box in full68_eval.boxes_from_candidates(_load_json(path))]


def _candidate_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    return [_norm(box) for box in full68_eval.boxes_from_candidates(_load_json(path))]


def _scored_rows(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected scored list: {path}")
    rows = []
    for item in payload:
        if isinstance(item, Mapping) and isinstance(item.get("bbox"), list):
            rows.append(
                {
                    "bbox": _norm(item["bbox"]),
                    "score": float(item.get("score", 0.0)),
                }
            )
    return rows


def _gt(path: Path) -> list[tuple[int, int, int, int]]:
    return [_norm(box) for box in full68_eval.boxes_from_gt(_load_json(path))]


def _matches(a: Sequence[int], b: Sequence[int], unit: float) -> bool:
    return is_barline_match(
        a,
        b,
        rule_name="center_anchor",
        vov_threshold=VOV,
        xdist_threshold=None,
        unit_size=unit,
        xdist_unit_ratio=CENTER_ANCHOR_XDIST_UNIT_RATIO,
    )


def _bands(boxes: Sequence[Sequence[Any]]) -> list[tuple[int, int]]:
    stats = build_row_stats(boxes, cluster_max_dist=None, min_row_count=1)
    return [(int(row["top"]), int(row["bottom"])) for row in stats]


def _max_vov(box: Sequence[int], bands: Sequence[tuple[int, int]]) -> float:
    y1, y2 = float(box[1]), float(box[3])
    h = max(1.0, y2 - y1)
    return max(
        (
            max(0.0, min(y2, float(by2)) - max(y1, float(by1))) / h
            for by1, by2 in bands
        ),
        default=0.0,
    )


def _inventory_record(path: Path, page: str) -> Mapping[str, Any]:
    payload = _load_json(path)
    rows = payload.get("records") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        raise ValueError(f"Invalid inventory: {path}")
    matches = [
        row for row in rows
        if isinstance(row, Mapping) and str(row.get("page")) == page
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one {page} record in {path}, got {len(matches)}")
    return matches[0]


def run(args: argparse.Namespace) -> dict[str, Any]:
    combined_report = _load_json(args.combined_report.resolve())
    late_report = _load_json(args.late_report.resolve())
    if not isinstance(combined_report, Mapping) or not isinstance(late_report, Mapping):
        raise ValueError("reports must be JSON objects")

    combined_root = Path(str(combined_report["aggregate_probe"]))
    late_root = Path(str(late_report["late_raw_x4"]["aggregate_probe"]))
    x4_root = args.x4_run_root.resolve()
    issue43_root = args.issue43_repo_root.resolve()
    gt_root = args.gt_root.resolve()
    units = load_page_staff_units(args.staff_units_json.resolve())
    threshold = float(combined_report["contract"]["cnn_threshold"])

    residuals: list[dict[str, Any]] = []
    target_presence: dict[str, bool] = {}
    total_fn = 0

    for score, pages in full68_eval.SCORES.items():
        inventory = x4_root / "inventories" / "control" / f"{score}.json"
        for page in pages:
            unit = float(require_page_staff_unit(units, score, page).unit_size)
            gt_boxes = _gt(gt_root / score / page / "boxes_sorted.json")

            final_path = _find(
                combined_root, score, page, "pipeline2_no_peak_filtered_cnn.json"
            )
            candidate_path = _find(
                combined_root, score, page, "pipeline2_no_peak_candidates.json"
            )
            scored_path = _find(
                combined_root, score, page, "pipeline2_no_peak_scored.json"
            )
            late_final_path = _find(
                late_root, score, page, "pipeline2_no_peak_filtered_cnn.json"
            )

            final_boxes = _final_boxes(final_path)
            candidates = _candidate_boxes(candidate_path)
            scored = _scored_rows(scored_path)
            late_final = _final_boxes(late_final_path)

            match = greedy_barline_match(
                final_boxes,
                gt_boxes,
                rule_name="center_anchor",
                vov_threshold=VOV,
                xdist_threshold=None,
                unit_size=unit,
                xdist_unit_ratio=CENTER_ANCHOR_XDIST_UNIT_RATIO,
            )
            total_fn += len(match.false_negative_indices)

            record = _inventory_record(inventory, page)
            hybrid_raw = Path(str(record["hybrid_predictions"]))
            hybrid = (
                hybrid_raw
                if hybrid_raw.is_file()
                else _host_path(hybrid_raw, issue43_root)
            )
            frozen_bands = _bands(load_json_boxes(hybrid))

            for idx in match.false_negative_indices:
                target = gt_boxes[idx]
                matching_candidates = [
                    box for box in candidates if _matches(box, target, unit)
                ]
                matching_scored = [
                    row for row in scored if _matches(row["bbox"], target, unit)
                ]
                matching_late = [
                    box for box in late_final if _matches(box, target, unit)
                ]
                residuals.append(
                    {
                        "score": score,
                        "page": page,
                        "gt_index": int(idx),
                        "gt_bbox": list(target),
                        "candidate_present": bool(matching_candidates),
                        "matching_candidates": [list(box) for box in matching_candidates],
                        "best_scored_score": max(
                            (float(row["score"]) for row in matching_scored),
                            default=None,
                        ),
                        "matching_scored": [
                            {"bbox": list(row["bbox"]), "score": row["score"]}
                            for row in matching_scored
                        ],
                        "present_in_late_final": bool(matching_late),
                        "late_final_matches": [list(box) for box in matching_late],
                        "frozen_band_max_vov": _max_vov(target, frozen_bands),
                        "passes_frozen_band": _max_vov(target, frozen_bands) >= VOV,
                    }
                )

            if score == TARGET_SCORE and page == TARGET_PAGE:
                final_set = set(final_boxes)
                target_presence = {
                    str(list(box)): box in final_set for box in TARGETS
                }

    report = {
        "schema_version": "issue372.combined_residual_fn.v1",
        "contract": {
            "retained_only": True,
            "inference_rerun": False,
            "matcher": "center_anchor current-unit",
            "cnn_threshold": threshold,
        },
        "summary": {
            "residual_fn": total_fn,
            "page021_target_presence_exact": target_presence,
            "candidate_present_count": sum(r["candidate_present"] for r in residuals),
            "present_in_late_final_count": sum(
                r["present_in_late_final"] for r in residuals
            ),
            "passes_frozen_band_count": sum(
                r["passes_frozen_band"] for r in residuals
            ),
        },
        "residuals": residuals,
    }

    out = args.output.resolve()
    if out.exists():
        raise FileExistsError(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("=== Issue #372 combined residual FNs ===")
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    print("\n=== residuals ===")
    for row in residuals:
        print(
            f"{row['score']}/{row['page']} gt={row['gt_bbox']} "
            f"candidate={row['candidate_present']} "
            f"best_score={row['best_scored_score']} "
            f"late_final={row['present_in_late_final']} "
            f"frozen_vov={row['frozen_band_max_vov']:.6f}"
        )
        if row["matching_scored"]:
            print("  scored=", row["matching_scored"])
    print("\n=== page_021 exact target presence ===")
    for box, present in target_presence.items():
        print(f"{box}: {present}")
    print(f"\nOUTPUT={out}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--combined-report", type=Path, required=True)
    parser.add_argument("--late-report", type=Path, required=True)
    parser.add_argument("--x4-run-root", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, required=True)
    parser.add_argument("--staff-units-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
