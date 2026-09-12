#!/usr/bin/env python3
"""Diagnose retained Issue #294 page_052 system-grouping decisions.

Host-only retained-artifact analysis. This does not rerun detector, HOMR, SR, OMR,
CNN, OCR, MMR, or numbering. It reconstructs the staff-pair evidence consumed by
ConnectorAwareSystemBuilder and reports the exact reason each adjacent pair merges
or splits, plus cheap counterfactual threshold/absence semantics.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.connector_aware_builder import ConnectorAwareSystemBuilder
from src.measure_numbering.pipeline import MeasureNumberingPipeline, StaffExtractor
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
THRESHOLDS = (0.05, 0.04, 0.03, 0.02, 0.015, 0.01, 0.005)


def _staff_bbox(staff: Staff) -> list[int]:
    return [staff.bbox.x1, staff.bbox.y1, staff.bbox.x2, staff.bbox.y2]


def _load_staffs(mask_path: Path) -> tuple[list[Staff], tuple[int, int]]:
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(mask_path)
    height, width = mask.shape[:2]
    return StaffExtractor().extract(mask_path, (width, height)), (width, height)


def _assign_barlines(staves: list[Staff], boxes: list[tuple[int, int, int, int]]) -> None:
    builder = ConnectorAwareSystemBuilder()
    builder._assign_barlines_to_staves(staves, [Barline(bbox=BBox(*box)) for box in boxes])


def _evidence_max_vertical_density(evidence: Mapping[str, Any] | None) -> float:
    if not evidence:
        return 0.0
    values = (
        evidence.get("symbols_vertical_open_density", 0.0),
        evidence.get("brace_dot_vertical_open_density", 0.0),
    )
    return max(float(value or 0.0) for value in values)


def _pair_decision(
    *,
    gap: float,
    avg_height: float,
    aligned_count: int,
    explicit_evidence: bool,
    left_connector_present: bool,
) -> dict[str, Any]:
    builder = ConnectorAwareSystemBuilder()
    within_distance = gap <= avg_height * builder.DIVISI_DIST_RATIO
    within_rescue = gap <= avg_height * builder.CONNECTOR_RESCUE_DIST_RATIO

    if not within_distance and not (left_connector_present and within_rescue):
        decision = "split"
        reason = "distance"
    elif explicit_evidence and not left_connector_present:
        decision = "split"
        reason = "explicit_connector_absence"
    elif within_distance and aligned_count >= builder.MIN_ALIGN_COUNT:
        decision = "merge"
        reason = "distance_and_alignment"
    elif (
        left_connector_present
        and within_rescue
        and aligned_count >= builder.CONNECTOR_RESCUE_MIN_ALIGN_COUNT
    ):
        decision = "merge"
        reason = "connector_rescue"
    else:
        decision = "split"
        reason = "insufficient_alignment"

    return {
        "decision": decision,
        "reason": reason,
        "within_distance": within_distance,
        "within_connector_rescue_distance": within_rescue,
    }


def _threshold_decision(
    *,
    gap: float,
    avg_height: float,
    aligned_count: int,
    evidence: Mapping[str, Any] | None,
    threshold: float,
) -> dict[str, Any]:
    present = _evidence_max_vertical_density(evidence) >= threshold
    result = _pair_decision(
        gap=gap,
        avg_height=avg_height,
        aligned_count=aligned_count,
        explicit_evidence=True,
        left_connector_present=present,
    )
    result["threshold"] = threshold
    result["left_connector_present"] = present
    return result


def _unknown_absence_decision(
    *, gap: float, avg_height: float, aligned_count: int
) -> dict[str, Any]:
    """Counterfactual where a generated negative connector pair is treated as unknown."""
    return _pair_decision(
        gap=gap,
        avg_height=avg_height,
        aligned_count=aligned_count,
        explicit_evidence=False,
        left_connector_present=False,
    )


def _numbering_signature(variant: Mapping[str, Any]) -> list[dict[str, Any]]:
    pages = variant["numbering"]["pages"]
    return [
        {
            "system_index": system_index,
            "staff_count": int(system["staff_count"]),
            "measure_count": int(system["measure_count"]),
            "measure_numbers": [int(number) for number in system["measure_numbers"]],
        }
        for page in pages
        for system_index, system in enumerate(page["systems"])
    ]


def _variant_diagnostic(page: Mapping[str, Any], label: str) -> dict[str, Any]:
    variant = page["modes"]["candidate_native_geometry"]["variants"][label]
    staff_mask = _resolve_project_path(str(variant["staff_mask"]))
    staves, image_size = _load_staffs(staff_mask)
    final_boxes = _normalise_boxes(variant["final_barlines"])
    _assign_barlines(staves, final_boxes)

    support = _load_json(_resolve_project_path(str(page["fixed_inputs"]["support_result"])))
    connector_paths = {
        "symbols": _resolve_project_path(str(support["connector_symbols"])),
        "brace_dot": _resolve_project_path(str(support["connector_brace_dot"])),
    }

    pipeline = MeasureNumberingPipeline()
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
    pairs: list[dict[str, Any]] = []
    for index in range(len(staves) - 1):
        s1, s2 = staves[index], staves[index + 1]
        gap = float(s2.bbox.y1 - s1.bbox.y2)
        aligned_count = len(pipeline.builder._find_aligned_pairs(s1, s2))
        pair_evidence = connector_by_pair.get((index, index + 1))
        explicit = pair_evidence is not None
        left_present = pipeline.builder._has_left_connector_evidence(pair_evidence)
        current = _pair_decision(
            gap=gap,
            avg_height=avg_height,
            aligned_count=aligned_count,
            explicit_evidence=explicit,
            left_connector_present=left_present,
        )
        target_like = 1150 <= s1.bbox.y1 <= 1550 and 1500 <= s2.bbox.y1 <= 1900
        pairs.append(
            {
                "pair": [index, index + 1],
                "target_like_page052_pair": target_like,
                "staff_bboxes": [_staff_bbox(s1), _staff_bbox(s2)],
                "gap": gap,
                "avg_staff_height": avg_height,
                "gap_over_avg_height": gap / avg_height if avg_height else None,
                "aligned_barline_pair_count": aligned_count,
                "explicit_connector_evidence": explicit,
                "left_connector_present": left_present,
                "max_vertical_open_density": _evidence_max_vertical_density(pair_evidence),
                "connector_evidence": pair_evidence,
                "current_decision": current,
                "negative_as_unknown_counterfactual": (
                    _unknown_absence_decision(
                        gap=gap,
                        avg_height=avg_height,
                        aligned_count=aligned_count,
                    )
                    if explicit and not left_present
                    else None
                ),
                "threshold_counterfactuals": [
                    _threshold_decision(
                        gap=gap,
                        avg_height=avg_height,
                        aligned_count=aligned_count,
                        evidence=pair_evidence,
                        threshold=threshold,
                    )
                    for threshold in THRESHOLDS
                ]
                if explicit
                else [],
            }
        )

    return {
        "label": label,
        "staff_mask": str(staff_mask),
        "image_size_from_staff_mask": list(image_size),
        "raw_staff_count": len(staves),
        "raw_staff_bboxes": [_staff_bbox(staff) for staff in staves],
        "evidence_staff_count": len(evidence_staves),
        "evidence_staff_bboxes": [_staff_bbox(staff) for staff in evidence_staves],
        "connector_paths": {key: str(value) for key, value in connector_paths.items()},
        "connector_evidence_source": evidence.get("source"),
        "connector_density_threshold": evidence.get("connector_density_threshold"),
        "numbering_signature": _numbering_signature(variant),
        "pairs": pairs,
    }


def run(manifest_path: Path, output_path: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, Mapping) or manifest.get("status") != "completed":
        raise ValueError(f"Full68 manifest is not completed: {manifest_path}")
    summaries = _manifest_page_by_id(manifest)
    page_summary = summaries.get("page_052")
    if page_summary is None:
        raise RuntimeError("Full68 manifest lacks page_052")
    page = _matrix_for_summary(page_summary, _load_matrix_pages(manifest))

    payload = {
        "schema_version": "issue294.page052_grouping_diagnostic.v1",
        "status": "completed",
        "execution_contract": {
            "retained_artifacts_only": True,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_reexecuted": False,
            "cnn_reexecuted": False,
            "ocr_reexecuted": False,
            "mmr_reexecuted": False,
        },
        "page_id": "page_052",
        "score": page_summary["score"],
        "page_name": page_summary["page_name"],
        "variants": {label: _variant_diagnostic(page, label) for label in LABELS},
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
        / "logs/issue294/issue294_full68_refresh_02/page_052_grouping_diagnostic_01.json",
    )
    args = parser.parse_args()
    payload = run(args.full68_manifest, args.output)
    print(json.dumps({"status": payload["status"], "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
