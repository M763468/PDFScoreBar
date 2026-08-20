#!/usr/bin/env python3
"""Attribute retained B/C support disagreements for Issue #274.

Retained-artifact analysis only. No HOMR/SR/OMR/dense/CNN/MMR execution.

Current-core thin recovery marks added/replaced predictions with system_index=-2.
This script separates B support evidence into primary vs thin-tagged provenance and
measures which source participates in the retained B/C support disagreements.

Important limitation: a thin-tagged prediction may have *replaced* a primary box,
so removing -2 records cannot reconstruct the exact pre-thin output. The analysis
therefore attributes retained evidence provenance; it does not claim causal
necessity of thin recovery when a replacement occurred.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from src.common import Box, barline_iou
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue274.analyze_x4_support_contract import (
    directional_support,
    load_json,
    norm_box,
    phase_a_slots,
    residual_critical_boxes,
    to_workspace,
)


def load_b_records(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    rows = payload.get("predictions", []) if isinstance(payload, dict) else []
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        bbox = row.get("orig_bbox") or row.get("bbox")
        if not isinstance(bbox, list) or len(bbox) < 4:
            continue
        result.append(
            {
                "box": norm_box(bbox),
                "system_index": int(row.get("system_index", -999)),
                "staff_index": int(row.get("staff_index", -999)),
            }
        )
    return result


def iou_supporters(
    query: Box, rows: list[dict[str, Any]], threshold: float
) -> list[dict[str, Any]]:
    return [row for row in rows if barline_iou(query, row["box"]) > threshold]


def has_iou(query: Box, boxes: list[Box], threshold: float) -> bool:
    return any(barline_iou(query, box) > threshold for box in boxes)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ab-report",
        type=Path,
        default=Path(
            "logs/issue274_homr_unification_analysis/stage_e_ab_01/issue274_homr_x4_stage_e_ab.json"
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
            "logs/issue274_homr_unification_analysis/disagreement_provenance_01/"
            "issue274_b_c_disagreement_provenance.json"
        ),
    )
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--iou-threshold", type=float, default=0.50)
    parser.add_argument("--directional-alpha", type=float, default=0.30)
    parser.add_argument("--slot-coverage", type=float, default=0.60)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    ab_path = to_workspace(args.ab_report, workspace)
    residual_path = to_workspace(args.residual_report, workspace)
    output_path = to_workspace(args.output, workspace)

    ab = load_json(ab_path)
    page_records = ab["hybrid_ab"]["pages"]
    if len(page_records) != 68:
        raise RuntimeError(f"Expected 68 retained pages, got {len(page_records)}")

    critical = residual_critical_boxes(residual_path if residual_path.is_file() else None)
    total = Counter()
    page_rows: list[dict[str, Any]] = []
    critical_rows: list[dict[str, Any]] = []

    for record in page_records:
        score = str(record["score"])
        page = str(record["page"])
        a_path = to_workspace(record["a_path"], workspace)
        b_path = to_workspace(record["b_current_x4_path"], workspace)
        c_path = to_workspace(record["c_pinned_x4_path"], workspace)
        omr_path = to_workspace(record["omr_path"], workspace)

        for path in (a_path, b_path, c_path, omr_path):
            if not path.is_file():
                raise FileNotFoundError(path)

        a_boxes = [norm_box(box) for box in load_json_boxes(a_path)]
        b_records = load_b_records(b_path)
        c_boxes = [norm_box(box) for box in load_json_boxes(c_path)]
        omr_boxes = [norm_box(box) for box in load_json_boxes(omr_path)]
        b_primary = [row["box"] for row in b_records if row["system_index"] != -2]
        b_thin = [row["box"] for row in b_records if row["system_index"] == -2]
        bands, unit_size, slot_source = phase_a_slots(a_boxes)

        page_counts = Counter()
        for query in a_boxes:
            supporters = iou_supporters(query, b_records, args.iou_threshold)
            primary_iou = any(row["system_index"] != -2 for row in supporters)
            thin_iou = any(row["system_index"] == -2 for row in supporters)
            b_support = bool(supporters)
            c_support = has_iou(query, c_boxes, args.iou_threshold)
            omr_support = has_iou(query, omr_boxes, args.iou_threshold)

            total["a_total"] += 1
            page_counts["a_total"] += 1
            total["b_thin_tagged_records"] += 0  # page record count is added below

            if b_support != c_support:
                total["producer_disagreement"] += 1
                page_counts["producer_disagreement"] += 1

                if b_support and not c_support:
                    total["b_true_c_false"] += 1
                    page_counts["b_true_c_false"] += 1
                    if primary_iou and thin_iou:
                        provenance = "primary_and_thin_iou"
                    elif primary_iou:
                        provenance = "primary_iou_only"
                    elif thin_iou:
                        provenance = "thin_iou_only"
                    else:
                        provenance = "unexpected_no_b_supporter"
                    total[f"b_true_c_false__{provenance}"] += 1
                    page_counts[f"b_true_c_false__{provenance}"] += 1
                else:
                    total["b_false_c_true"] += 1
                    page_counts["b_false_c_true"] += 1
                    primary_dir, primary_best = directional_support(
                        query,
                        b_primary,
                        bands=bands,
                        unit_size=unit_size,
                        xdist_unit_ratio=args.directional_alpha,
                        slot_coverage_threshold=args.slot_coverage,
                        fallback_vertical_coverage=0.60,
                    )
                    thin_dir, thin_best = directional_support(
                        query,
                        b_thin,
                        bands=bands,
                        unit_size=unit_size,
                        xdist_unit_ratio=args.directional_alpha,
                        slot_coverage_threshold=args.slot_coverage,
                        fallback_vertical_coverage=0.60,
                    )
                    if primary_dir and thin_dir:
                        provenance = "primary_and_thin_directional_without_iou"
                    elif primary_dir:
                        provenance = "primary_directional_without_iou"
                    elif thin_dir:
                        provenance = "thin_directional_without_iou"
                    else:
                        provenance = "no_directional_b_evidence"
                    total[f"b_false_c_true__{provenance}"] += 1
                    page_counts[f"b_false_c_true__{provenance}"] += 1

                    if (score, page, query) in critical:
                        critical_rows.append(
                            {
                                "score": score,
                                "page": page,
                                "baseline_box": list(query),
                                "direction": "B_false_C_true",
                                "provenance": provenance,
                                "primary_best": primary_best,
                                "thin_best": thin_best,
                            }
                        )

                if (score, page, query) in critical and b_support and not c_support:
                    critical_rows.append(
                        {
                            "score": score,
                            "page": page,
                            "baseline_box": list(query),
                            "direction": "B_true_C_false",
                            "primary_iou_support": primary_iou,
                            "thin_iou_support": thin_iou,
                            "supporters": [
                                {
                                    "box": list(row["box"]),
                                    "system_index": row["system_index"],
                                    "staff_index": row["staff_index"],
                                }
                                for row in supporters
                            ],
                        }
                    )

            keep_b = b_support or omr_support
            keep_c = c_support or omr_support
            if keep_b != keep_c:
                total["combined_keep_disagreement"] += 1
                page_counts["combined_keep_disagreement"] += 1

        thin_count = sum(row["system_index"] == -2 for row in b_records)
        primary_count = len(b_records) - thin_count
        total["b_records"] += len(b_records)
        total["b_primary_records"] += primary_count
        total["b_thin_records"] += thin_count
        page_rows.append(
            {
                "score": score,
                "page": page,
                "b_records": len(b_records),
                "b_primary_records": primary_count,
                "b_thin_records": thin_count,
                "slot_source": slot_source,
                "unit_size_px": unit_size,
                **dict(page_counts),
            }
        )

    if total["producer_disagreement"] != 149:
        raise RuntimeError(
            "Retained provenance analysis did not reproduce expected B/C producer disagreement: "
            f"{total['producer_disagreement']} != 149"
        )
    if total["combined_keep_disagreement"] != 90:
        raise RuntimeError(
            "Retained provenance analysis did not reproduce expected combined disagreement: "
            f"{total['combined_keep_disagreement']} != 90"
        )

    result = {
        "schema_version": "issue274.b_c_disagreement_provenance.v1",
        "status": "completed",
        "scope": {
            "pages": 68,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "dense_reexecuted": False,
            "cnn_reexecuted": False,
            "mmr_reexecuted": False,
        },
        "provenance_contract": {
            "thin_tag": "system_index == -2",
            "primary_tag": "system_index != -2",
            "caveat": (
                "A -2 record may be an additive thin candidate or a replacement of a primary box; "
                "retained output alone cannot distinguish those cases."
            ),
            "iou_threshold": args.iou_threshold,
            "directional_alpha_staff_space": args.directional_alpha,
            "slot_coverage": args.slot_coverage,
        },
        "summary": dict(total),
        "critical_cases": critical_rows,
        "pages": page_rows,
        "decision_rule": {
            "if_primary_dominates_b_true_c_false": (
                "B/C divergence is mainly pre-thin producer drift; do not tune thin policy to reproduce C."
            ),
            "if_thin_dominates": (
                "Thin recovery is a major producer divergence and needs a theory-first replacement/identity contract."
            ),
            "b_false_c_true_directional": (
                "Directional B evidence without IoU indicates geometry/support-contract interaction rather than missing evidence."
            ),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "summary": result["summary"],
                "output": str(output_path),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
