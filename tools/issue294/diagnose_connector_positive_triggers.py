#!/usr/bin/env python3
"""Diagnose every retained full68 pair affected by the Issue #294 connector-positive rule.

This is retained-artifact-only analysis.  It does not rerun detector, HOMR, SR, OMR,
CNN, OCR, MMR, or numbering.  The goal is to distinguish the desired page_052 B/C
recovery from any unsafe trigger (currently page_067 A) before considering a
production grouping change.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.connector_aware_builder import ConnectorAwareSystemBuilder
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.types import Barline, BBox, Staff
from tools.issue294.audit_full68_retained_semantics import (
    _load_json,
    _load_matrix_pages,
    _manifest_page_by_id,
    _matrix_for_summary,
    _normalise_boxes,
    _resolve_project_path,
)

LABELS = ("A_pinned", "B_b377", "C_latest")


def _bbox(staff: Staff) -> list[int]:
    return [staff.bbox.x1, staff.bbox.y1, staff.bbox.x2, staff.bbox.y2]


def _vertical_iou(left: Staff, right: Staff) -> float:
    intersection = max(0, min(left.bbox.y2, right.bbox.y2) - max(left.bbox.y1, right.bbox.y1))
    union = max(left.bbox.y2, right.bbox.y2) - min(left.bbox.y1, right.bbox.y1)
    return float(intersection / union) if union > 0 else 0.0


def _staff_mapping_metrics(
    geometry_staves: list[Staff], evidence_staves: list[Staff], pair_index: int
) -> dict[str, Any]:
    target_indices = [pair_index, pair_index + 1]
    same_index_ious: list[float | None] = []
    best_indices: list[int | None] = []
    best_ious: list[float] = []
    center_deltas: list[float | None] = []

    for geometry_index in target_indices:
        geometry = geometry_staves[geometry_index]
        if geometry_index < len(evidence_staves):
            evidence = evidence_staves[geometry_index]
            same_index_ious.append(_vertical_iou(geometry, evidence))
            scale = max(1.0, (geometry.bbox.height + evidence.bbox.height) / 2.0)
            center_deltas.append(abs(geometry.bbox.center[1] - evidence.bbox.center[1]) / scale)
        else:
            same_index_ious.append(None)
            center_deltas.append(None)

        if evidence_staves:
            scored = [
                (_vertical_iou(geometry, evidence), index)
                for index, evidence in enumerate(evidence_staves)
            ]
            best_iou, best_index = max(scored, key=lambda item: (item[0], -item[1]))
            best_indices.append(best_index)
            best_ious.append(best_iou)
        else:
            best_indices.append(None)
            best_ious.append(0.0)

    return {
        "geometry_staff_count": len(geometry_staves),
        "evidence_staff_count": len(evidence_staves),
        "same_index_vertical_iou": same_index_ious,
        "same_index_center_y_delta_over_mean_height": center_deltas,
        "best_evidence_indices_by_vertical_iou": best_indices,
        "best_vertical_iou": best_ious,
        "same_index_is_best_for_pair": best_indices == target_indices,
    }


def _is_relaxed_trigger(
    *, gap: float, avg_height: float, aligned_count: int, left_connector_present: bool
) -> bool:
    builder = ConnectorAwareSystemBuilder()
    within_distance = gap <= avg_height * builder.DIVISI_DIST_RATIO
    return bool(
        left_connector_present and within_distance and aligned_count < builder.MIN_ALIGN_COUNT
    )


def _assigned_x_centers(staff: Staff) -> list[float]:
    return sorted((bar.bbox.x1 + bar.bbox.x2) / 2.0 for bar in staff.barlines)


def _nearest_cross_staff_x_delta(left: Staff, right: Staff) -> float | None:
    left_x = _assigned_x_centers(left)
    right_x = _assigned_x_centers(right)
    if not left_x or not right_x:
        return None
    return float(min(abs(a - b) for a in left_x for b in right_x))


def _variant_triggers(
    page: Mapping[str, Any], label: str, image_size: tuple[int, int]
) -> list[dict[str, Any]]:
    variant = page["modes"]["candidate_native_geometry"]["variants"][label]
    staff_mask = _resolve_project_path(str(variant["staff_mask"]))
    pipeline = MeasureNumberingPipeline()
    staves = pipeline.extractor.extract(staff_mask, image_size)

    final_boxes = _normalise_boxes(variant["final_barlines"])
    pipeline.builder._assign_barlines_to_staves(
        staves,
        [Barline(bbox=BBox(*box)) for box in final_boxes],
    )

    support = _load_json(_resolve_project_path(str(page["fixed_inputs"]["support_result"])))
    connector_paths = {
        "symbols": _resolve_project_path(str(support["connector_symbols"])),
        "brace_dot": _resolve_project_path(str(support["connector_brace_dot"])),
    }
    evidence_staves = pipeline._connector_evidence_staves(
        staves,
        staff_mask,
        image_size,
        connector_paths,
    )
    evidence = pipeline.connector_extractor.extract_from_mask_maps(
        evidence_staves,
        image_size,
        connector_mask_paths=connector_paths,
    )
    connector_by_pair = pipeline.builder._normalize_connector_evidence(evidence)

    avg_height = sum(staff.bbox.height for staff in staves) / max(1, len(staves))
    result: list[dict[str, Any]] = []
    for index in range(len(staves) - 1):
        left = staves[index]
        right = staves[index + 1]
        gap = float(right.bbox.y1 - left.bbox.y2)
        aligned_count = len(pipeline.builder._find_aligned_pairs(left, right))
        pair_evidence = connector_by_pair.get((index, index + 1))
        left_present = pipeline.builder._has_left_connector_evidence(pair_evidence)
        if not _is_relaxed_trigger(
            gap=gap,
            avg_height=avg_height,
            aligned_count=aligned_count,
            left_connector_present=left_present,
        ):
            continue

        result.append(
            {
                "pair": [index, index + 1],
                "geometry_staff_bboxes": [_bbox(left), _bbox(right)],
                "evidence_staff_bboxes": (
                    [_bbox(evidence_staves[index]), _bbox(evidence_staves[index + 1])]
                    if index + 1 < len(evidence_staves)
                    else None
                ),
                "gap": gap,
                "avg_staff_height": avg_height,
                "gap_over_avg_height": gap / avg_height if avg_height else None,
                "aligned_barline_pair_count": aligned_count,
                "assigned_barline_counts": [len(left.barlines), len(right.barlines)],
                "assigned_barline_x_centers": [
                    _assigned_x_centers(left),
                    _assigned_x_centers(right),
                ],
                "nearest_cross_staff_x_delta": _nearest_cross_staff_x_delta(left, right),
                "connector_evidence": pair_evidence,
                "staff_index_mapping": _staff_mapping_metrics(staves, evidence_staves, index),
            }
        )
    return result


def _image_size(page: Mapping[str, Any]) -> tuple[int, int]:
    import cv2

    path = _resolve_project_path(str(page["image"]))
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(path)
    height, width = image.shape[:2]
    return width, height


def run(manifest_path: Path, output_path: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, Mapping) or manifest.get("status") != "completed":
        raise ValueError(f"Full68 manifest is not completed: {manifest_path}")

    summaries = _manifest_page_by_id(manifest)
    matrix_pages = _load_matrix_pages(manifest)
    triggers: list[dict[str, Any]] = []
    by_label = {label: [] for label in LABELS}

    for page_id, summary in summaries.items():
        page = _matrix_for_summary(summary, matrix_pages)
        image_size = _image_size(page)
        for label in LABELS:
            records = _variant_triggers(page, label, image_size)
            if not records:
                continue
            by_label[label].append(page_id)
            for record in records:
                triggers.append(
                    {
                        "page_id": page_id,
                        "score": summary["score"],
                        "page_name": summary["page_name"],
                        "label": label,
                        **record,
                    }
                )

    payload = {
        "schema_version": "issue294.connector_positive_trigger_diagnostic.v1",
        "status": "completed",
        "execution_contract": {
            "retained_artifacts_only": True,
            "production_code_modified": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_reexecuted": False,
            "cnn_reexecuted": False,
            "ocr_reexecuted": False,
            "mmr_reexecuted": False,
            "numbering_reexecuted": False,
        },
        "trigger_count": len(triggers),
        "trigger_pages_by_label": by_label,
        "triggers": triggers,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--full68-manifest",
        type=Path,
        default=PROJECT_ROOT / "logs/issue294/issue294_full68_refresh_02/full68_host.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT
        / "logs/issue294/issue294_full68_refresh_02/connector_positive_trigger_diagnostic_01.json",
    )
    args = parser.parse_args()
    payload = run(args.full68_manifest, args.output)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "trigger_count": payload["trigger_count"],
                "trigger_pages_by_label": payload["trigger_pages_by_label"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
