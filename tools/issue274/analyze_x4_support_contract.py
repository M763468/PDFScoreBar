#!/usr/bin/env python3
"""Analyze a staff-slot-aware x4 HOMR support contract for Issue #274.

This is retained-artifact analysis only. It does not rerun HOMR, SR, OMR-DLN,
dense probe generation, or CNN inference.

The experiment treats the original-image baseline (A) as the authoritative
barline geometry and x4 HOMR (B/C) as evidence providers. Instead of symmetric
IoU, it tests a directional relation:

- x centres must be close in staff-relative units; and
- the Phase-A staff slots occupied by A must be a subset of those occupied by
  the x4 evidence box.

One long/common x4 evidence box may therefore support multiple per-staff A
barlines without forcing those A barlines to collapse into one entity.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from src.common import Box, barline_iou
from src.pipeline.probe_detector.bands import build_row_stats
from src.pipeline.steps.hybrid_consensus import load_json_boxes


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def to_workspace(path_value: str | Path, workspace: Path) -> Path:
    text = str(path_value)
    if text.startswith("/workspace/"):
        return workspace / text[len("/workspace/") :]
    marker = "/ws_PDFScoreBar/"
    if marker in text:
        return workspace / text.split(marker, 1)[1]
    path = Path(text)
    return path if path.is_absolute() else workspace / path


def norm_box(values: Iterable[Any]) -> Box:
    vals = list(values)
    if len(vals) < 4:
        raise ValueError(f"Expected 4 box values, got {vals!r}")
    return tuple(int(round(float(v))) for v in vals[:4])  # type: ignore[return-value]


def centre_x(box: Box) -> float:
    return (box[0] + box[2]) / 2.0


def box_height(box: Box) -> float:
    return max(1.0, float(abs(box[3] - box[1])))


def vertical_coverage_of_query(query: Box, evidence: Box) -> float:
    overlap = max(0.0, min(query[3], evidence[3]) - max(query[1], evidence[1]))
    return overlap / box_height(query)


def robust_unit_from_boxes(boxes: list[Box]) -> float:
    heights = sorted(box_height(box) for box in boxes if box_height(box) > 0)
    if not heights:
        return 40.0
    if len(heights) >= 8:
        lo = int(len(heights) * 0.20)
        hi = max(lo + 1, int(math.ceil(len(heights) * 0.80)))
        heights = heights[lo:hi]
    return max(1.0, statistics.median(heights) / 4.0)


def phase_a_slots(boxes: list[Box]) -> tuple[list[tuple[int, int]], float, str]:
    """Derive Phase-A staff rows from the already-retained A baseline boxes."""
    row_stats = build_row_stats(boxes)
    bands = [
        (int(round(row["top"])), int(round(row["bottom"])))
        for row in row_stats
        if row["bottom"] > row["top"]
    ]
    if bands:
        heights = [max(1, bottom - top) for top, bottom in bands]
        return bands, max(1.0, statistics.median(heights) / 4.0), "row_stats"
    return [], robust_unit_from_boxes(boxes), "bbox_height_fallback"


def slot_signature(
    box: Box,
    bands: list[tuple[int, int]],
    *,
    coverage_threshold: float,
) -> tuple[int, ...]:
    slots: list[int] = []
    for index, (top, bottom) in enumerate(bands):
        band_height = max(1.0, float(bottom - top))
        overlap = max(0.0, min(box[3], bottom) - max(box[1], top))
        if overlap / band_height >= coverage_threshold:
            slots.append(index)
    return tuple(slots)


def has_iou_support(query: Box, refs: list[Box], threshold: float) -> bool:
    return any(barline_iou(query, ref) > threshold for ref in refs)


def directional_support(
    query: Box,
    refs: list[Box],
    *,
    bands: list[tuple[int, int]],
    unit_size: float,
    xdist_unit_ratio: float,
    slot_coverage_threshold: float,
    fallback_vertical_coverage: float,
) -> tuple[bool, dict[str, Any] | None]:
    query_slots = slot_signature(
        query,
        bands,
        coverage_threshold=slot_coverage_threshold,
    )
    best: dict[str, Any] | None = None

    for ref in refs:
        xdist_px = abs(centre_x(query) - centre_x(ref))
        xdist_units = xdist_px / max(unit_size, 1e-9)
        if xdist_units > xdist_unit_ratio:
            continue

        ref_slots = slot_signature(
            ref,
            bands,
            coverage_threshold=slot_coverage_threshold,
        )
        vertical_coverage = vertical_coverage_of_query(query, ref)

        if query_slots:
            supported = set(query_slots).issubset(ref_slots)
            mode = "staff_slot_subset"
        else:
            supported = vertical_coverage >= fallback_vertical_coverage
            mode = "bbox_vertical_coverage_fallback"

        candidate = {
            "evidence_box": list(ref),
            "xdist_px": xdist_px,
            "xdist_units": xdist_units,
            "query_slots": list(query_slots),
            "evidence_slots": list(ref_slots),
            "query_vertical_coverage": vertical_coverage,
            "mode": mode,
            "supported": supported,
        }

        rank = (
            1 if supported else 0,
            len(set(query_slots).intersection(ref_slots)),
            vertical_coverage,
            -xdist_units,
        )
        if best is None:
            best = candidate
        else:
            best_rank = (
                1 if best["supported"] else 0,
                len(set(best["query_slots"]).intersection(best["evidence_slots"])),
                best["query_vertical_coverage"],
                -best["xdist_units"],
            )
            if rank > best_rank:
                best = candidate

    return bool(best and best["supported"]), best


def same_x_disjoint_slot_hazards(
    boxes: list[Box],
    *,
    bands: list[tuple[int, int]],
    unit_size: float,
    slot_coverage_threshold: float,
    xdist_unit_ratio: float,
) -> list[dict[str, Any]]:
    signatures = [
        slot_signature(box, bands, coverage_threshold=slot_coverage_threshold)
        for box in boxes
    ]
    hazards: list[dict[str, Any]] = []
    for i in range(len(boxes)):
        if not signatures[i]:
            continue
        for j in range(i + 1, len(boxes)):
            if not signatures[j]:
                continue
            xdist_units = abs(centre_x(boxes[i]) - centre_x(boxes[j])) / max(
                unit_size, 1e-9
            )
            if xdist_units > xdist_unit_ratio:
                continue
            if set(signatures[i]).isdisjoint(signatures[j]):
                hazards.append(
                    {
                        "i": i,
                        "j": j,
                        "box_i": list(boxes[i]),
                        "box_j": list(boxes[j]),
                        "slots_i": list(signatures[i]),
                        "slots_j": list(signatures[j]),
                        "xdist_units": xdist_units,
                    }
                )
    return hazards


def parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def residual_critical_boxes(path: Path | None) -> set[tuple[str, str, Box]]:
    if path is None or not path.is_file():
        return set()
    data = load_json(path)
    result: set[tuple[str, str, Box]] = set()
    for page in data.get("pages", []):
        score = str(page.get("score"))
        page_name = str(page.get("page"))
        for residual in page.get("residuals", []):
            for row in residual.get("source_support", []):
                baseline = row.get("baseline_box")
                if isinstance(baseline, list) and len(baseline) >= 4:
                    result.add((score, page_name, norm_box(baseline)))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ab-report",
        type=Path,
        default=Path(
            "logs/issue274_homr_unification_analysis/stage_e_ab_01/"
            "issue274_homr_x4_stage_e_ab.json"
        ),
    )
    parser.add_argument(
        "--residual-report",
        type=Path,
        default=Path(
            "logs/issue274_homr_unification_analysis/stage_e_ab_01/"
            "residual_trace_01/issue274_homr_x4_stage_e_residual_trace.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "logs/issue274_homr_unification_analysis/support_contract_01/"
            "issue274_x4_support_contract_analysis.json"
        ),
    )
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--xdist-unit-ratios", default="0.15,0.20,0.25,0.30,0.35")
    parser.add_argument("--slot-coverage-thresholds", default="0.50,0.60,0.70")
    parser.add_argument("--fallback-vertical-coverage", type=float, default=0.60)
    parser.add_argument("--current-iou-threshold", type=float, default=0.50)
    parser.add_argument(
        "--hazard-xdist-unit-ratio",
        type=float,
        default=0.15,
        help="Diagnostic same-x proximity only; not a production threshold.",
    )
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    ab_path = to_workspace(args.ab_report, workspace)
    residual_path = to_workspace(args.residual_report, workspace)
    output_path = to_workspace(args.output, workspace)

    ab = load_json(ab_path)
    page_records = ab["hybrid_ab"]["pages"]
    if len(page_records) != 68:
        raise RuntimeError(f"Expected 68 retained A/B/C pages, got {len(page_records)}")

    critical = residual_critical_boxes(
        residual_path if residual_path.is_file() else None
    )
    pages: list[dict[str, Any]] = []

    for record in page_records:
        score = str(record["score"])
        page = str(record["page"])
        a_path = to_workspace(record["a_path"], workspace)
        b_path = to_workspace(record["b_current_x4_path"], workspace)
        c_path = to_workspace(record["c_pinned_x4_path"], workspace)
        omr_path = to_workspace(record["omr_path"], workspace)

        missing = [
            str(path)
            for path in (a_path, b_path, c_path, omr_path)
            if not path.is_file()
        ]
        if missing:
            raise FileNotFoundError(
                f"Missing retained artifacts for {score}/{page}: {missing}"
            )

        a_boxes = list(load_json_boxes(a_path))
        b_boxes = list(load_json_boxes(b_path))
        c_boxes = list(load_json_boxes(c_path))
        omr_boxes = list(load_json_boxes(omr_path))
        bands, unit_size, slot_source = phase_a_slots(a_boxes)
        pages.append(
            {
                "score": score,
                "page": page,
                "a": a_boxes,
                "b": b_boxes,
                "c": c_boxes,
                "omr": omr_boxes,
                "bands": bands,
                "unit_size": unit_size,
                "slot_source": slot_source,
            }
        )

    current_counts = Counter()
    for item in pages:
        for baseline in item["a"]:
            b_support = has_iou_support(
                baseline, item["b"], args.current_iou_threshold
            )
            c_support = has_iou_support(
                baseline, item["c"], args.current_iou_threshold
            )
            omr_support = has_iou_support(
                baseline, item["omr"], args.current_iou_threshold
            )
            current_counts["baseline_total"] += 1
            current_counts["b_supported"] += int(b_support)
            current_counts["c_supported"] += int(c_support)
            current_counts["producer_disagreement"] += int(b_support != c_support)
            current_counts["combined_keep_disagreement"] += int(
                (b_support or omr_support) != (c_support or omr_support)
            )

    grid: list[dict[str, Any]] = []
    for alpha in parse_float_list(args.xdist_unit_ratios):
        for gamma in parse_float_list(args.slot_coverage_thresholds):
            counts = Counter()
            page_summaries: list[dict[str, Any]] = []
            critical_rows: list[dict[str, Any]] = []

            for item in pages:
                b_set: set[int] = set()
                c_set: set[int] = set()
                omr_set: set[int] = set()

                for index, baseline in enumerate(item["a"]):
                    b_support, b_best = directional_support(
                        baseline,
                        item["b"],
                        bands=item["bands"],
                        unit_size=item["unit_size"],
                        xdist_unit_ratio=alpha,
                        slot_coverage_threshold=gamma,
                        fallback_vertical_coverage=args.fallback_vertical_coverage,
                    )
                    c_support, c_best = directional_support(
                        baseline,
                        item["c"],
                        bands=item["bands"],
                        unit_size=item["unit_size"],
                        xdist_unit_ratio=alpha,
                        slot_coverage_threshold=gamma,
                        fallback_vertical_coverage=args.fallback_vertical_coverage,
                    )
                    omr_support = has_iou_support(
                        baseline, item["omr"], args.current_iou_threshold
                    )

                    if b_support:
                        b_set.add(index)
                    if c_support:
                        c_set.add(index)
                    if omr_support:
                        omr_set.add(index)

                    counts["baseline_total"] += 1
                    counts["b_supported"] += int(b_support)
                    counts["c_supported"] += int(c_support)
                    counts["producer_disagreement"] += int(b_support != c_support)
                    counts["combined_keep_disagreement"] += int(
                        (b_support or omr_support) != (c_support or omr_support)
                    )

                    key = (item["score"], item["page"], baseline)
                    if key in critical:
                        critical_rows.append(
                            {
                                "score": item["score"],
                                "page": item["page"],
                                "baseline_box": list(baseline),
                                "b_support": b_support,
                                "c_support": c_support,
                                "omr_iou_support": omr_support,
                                "b_best": b_best,
                                "c_best": c_best,
                            }
                        )

                hazards = same_x_disjoint_slot_hazards(
                    item["a"],
                    bands=item["bands"],
                    unit_size=item["unit_size"],
                    slot_coverage_threshold=gamma,
                    xdist_unit_ratio=args.hazard_xdist_unit_ratio,
                )
                counts["same_x_disjoint_slot_hazard_pairs"] += len(hazards)
                counts["pages_with_same_x_disjoint_slot_hazard"] += int(bool(hazards))
                counts["slot_fallback_pages"] += int(not item["bands"])

                page_summaries.append(
                    {
                        "score": item["score"],
                        "page": item["page"],
                        "slot_source": item["slot_source"],
                        "staff_slot_count": len(item["bands"]),
                        "unit_size_px": item["unit_size"],
                        "a_count": len(item["a"]),
                        "b_count": len(item["b"]),
                        "c_count": len(item["c"]),
                        "producer_disagreement_a": len(b_set.symmetric_difference(c_set)),
                        "combined_keep_disagreement_a": len(
                            (b_set | omr_set).symmetric_difference(c_set | omr_set)
                        ),
                        "same_x_disjoint_slot_hazard_count": len(hazards),
                        "same_x_disjoint_slot_hazards": hazards[:20],
                    }
                )

            grid.append(
                {
                    "alpha_xdist_unit_ratio": alpha,
                    "gamma_slot_coverage": gamma,
                    "summary": dict(counts),
                    "critical_cases": critical_rows,
                    "pages": page_summaries,
                }
            )

    result = {
        "schema_version": "issue274.x4_support_contract_analysis.v1",
        "status": "completed",
        "scope": {
            "page_count": len(pages),
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "dense_reexecuted": False,
            "cnn_reexecuted": False,
        },
        "contract_under_test": {
            "authoritative_geometry": "A original-image baseline candidate",
            "x4_role": "evidence provider, not topology owner",
            "slot_source": "Phase-A row geometry derived from retained A boxes",
            "staff_unit": "median Phase-A row height / 4",
            "x_distance": "abs(cx_A-cx_E) / staff_space",
            "slot_relation": "slots(A) subset_of slots(E)",
            "one_evidence_can_support_multiple_A": True,
            "omr_policy": f"held at current IoU>{args.current_iou_threshold}",
        },
        "historical_calibration_context": {
            "center_anchor_xdist_px": 12,
            "historical_unit_px_approx": 40,
            "center_anchor_xdist_units_approx": 0.30,
            "historical_vertical_overlap_examples": [0.5, 0.6],
            "note": "Historical values seed the normalized grid; they are not acceptance criteria.",
        },
        "current_iou_contract": {
            "iou_threshold": args.current_iou_threshold,
            "summary": dict(current_counts),
        },
        "grid": grid,
        "grid_signature": {
            f"alpha={cell['alpha_xdist_unit_ratio']:.3f},gamma={cell['gamma_slot_coverage']:.3f}": {
                "producer_disagreement": cell["summary"].get("producer_disagreement", 0),
                "combined_keep_disagreement": cell["summary"].get(
                    "combined_keep_disagreement", 0
                ),
                "same_x_disjoint_slot_hazard_pairs": cell["summary"].get(
                    "same_x_disjoint_slot_hazard_pairs", 0
                ),
                "slot_fallback_pages": cell["summary"].get("slot_fallback_pages", 0),
            }
            for cell in grid
        },
        "decision_rule": {
            "do_not_select_by": "closest reproduction of pinned C or single best evaluation2 score",
            "look_for": [
                "stable decisions across neighbouring normalized thresholds",
                "same-x different-staff multiplicity preserved",
                "reduced B/C producer sensitivity",
                "few or no pages requiring slot fallback",
            ],
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "scope": result["scope"],
                "current_iou": result["current_iou_contract"]["summary"],
                "grid_signature": result["grid_signature"],
                "output": str(output_path),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
