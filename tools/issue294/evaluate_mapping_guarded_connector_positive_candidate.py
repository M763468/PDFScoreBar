#!/usr/bin/env python3
"""Evaluate a mapping-guarded connector-positive Issue #294 grouping candidate.

This retained-artifact-only experiment combines two generic changes without touching
production source:

1. explicit positive connector evidence may merge nearby staves without HOMR
   barline alignment; and
2. current-HOMR semantic staff ROIs are used only when their ordered staff mapping
   is geometrically consistent with the numbering geometry.  Otherwise connector
   evidence is measured directly against the numbering geometry, matching the
   existing count-mismatch fallback contract.

No detector, HOMR, SR, OMR, CNN, OCR, or MMR inference is rerun.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.types import Staff
from tools.issue294.audit_full68_retained_semantics import (
    _load_json,
    _load_matrix_pages,
    _manifest_page_by_id,
    _matrix_for_summary,
    _resolve_project_path,
)
from tools.issue294.evaluate_connector_positive_grouping_candidate import (
    LABELS,
    ConnectorPositiveWithinDistanceBuilder,
    _comparison,
    _page_image_size,
    _semantic_signature_from_numbering,
    _semantic_signature_from_score,
)


def _vertical_iou(left: Staff, right: Staff) -> float:
    intersection = max(
        0,
        min(left.bbox.y2, right.bbox.y2) - max(left.bbox.y1, right.bbox.y1),
    )
    union = max(left.bbox.y2, right.bbox.y2) - min(left.bbox.y1, right.bbox.y1)
    return float(intersection / union) if union > 0 else 0.0


def _best_index(source: Staff, candidates: list[Staff]) -> tuple[int | None, float]:
    if not candidates:
        return None, 0.0
    scored = [
        (_vertical_iou(source, candidate), index) for index, candidate in enumerate(candidates)
    ]
    best_iou, best_index = max(scored, key=lambda item: (item[0], -item[1]))
    return best_index, best_iou


def _identity_mapping_reliable(geometry_staves: list[Staff], evidence_staves: list[Staff]) -> bool:
    """Require positive-overlap reciprocal identity correspondence for every staff.

    No numeric tuning threshold is introduced: each same-index pair must overlap,
    and each side must choose the other as its best vertical-IoU correspondence.
    """

    if len(geometry_staves) != len(evidence_staves) or not geometry_staves:
        return False

    for index, (geometry, evidence) in enumerate(zip(geometry_staves, evidence_staves)):
        if _vertical_iou(geometry, evidence) <= 0.0:
            return False
        geometry_best, _ = _best_index(geometry, evidence_staves)
        evidence_best, _ = _best_index(evidence, geometry_staves)
        if geometry_best != index or evidence_best != index:
            return False
    return True


class MappingGuardedConnectorPositivePipeline(MeasureNumberingPipeline):
    """Experiment-only pipeline guarding semantic-staff index transfer."""

    def __init__(self) -> None:
        super().__init__()
        self.builder = ConnectorPositiveWithinDistanceBuilder()
        self.last_evidence_geometry_mode = "unresolved"

    def _connector_evidence_staves(
        self,
        geometry_staves: list[Staff],
        staff_mask_path: Path,
        image_size: tuple[int, int],
        connector_mask_paths: Optional[Mapping[str, Path | str]],
    ) -> list[Staff]:
        semantic_staves = super()._connector_evidence_staves(
            geometry_staves,
            staff_mask_path,
            image_size,
            connector_mask_paths,
        )
        if semantic_staves is geometry_staves:
            self.last_evidence_geometry_mode = "geometry_existing_fallback"
            return geometry_staves
        if not _identity_mapping_reliable(geometry_staves, semantic_staves):
            self.last_evidence_geometry_mode = "geometry_mapping_guard_fallback"
            return geometry_staves
        self.last_evidence_geometry_mode = "semantic_identity_mapped"
        return semantic_staves


def _run_current_numbering(
    *,
    variant: Mapping[str, Any],
    support: Mapping[str, Any],
    image_size: tuple[int, int],
) -> list[dict[str, Any]]:
    pipeline = MeasureNumberingPipeline()
    staff_mask = _resolve_project_path(str(variant["staff_mask"]))
    score = pipeline.run_sequential(
        [
            {
                "barlines": variant["final_barlines"],
                "staff_mask": str(staff_mask),
                "image_size": image_size,
                "page_number": 1,
                "connector_mask_paths": {
                    "symbols": str(_resolve_project_path(str(support["connector_symbols"]))),
                    "brace_dot": str(_resolve_project_path(str(support["connector_brace_dot"]))),
                },
            }
        ]
    )
    return _semantic_signature_from_score(score)


def _run_candidate_numbering(
    *,
    variant: Mapping[str, Any],
    support: Mapping[str, Any],
    image_size: tuple[int, int],
) -> tuple[list[dict[str, Any]], str]:
    pipeline = MappingGuardedConnectorPositivePipeline()
    staff_mask = _resolve_project_path(str(variant["staff_mask"]))
    score = pipeline.run_sequential(
        [
            {
                "barlines": variant["final_barlines"],
                "staff_mask": str(staff_mask),
                "image_size": image_size,
                "page_number": 1,
                "connector_mask_paths": {
                    "symbols": str(_resolve_project_path(str(support["connector_symbols"]))),
                    "brace_dot": str(_resolve_project_path(str(support["connector_brace_dot"]))),
                },
            }
        ]
    )
    return _semantic_signature_from_score(score), pipeline.last_evidence_geometry_mode


def run(manifest_path: Path, output_path: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, Mapping) or manifest.get("status") != "completed":
        raise ValueError(f"Full68 manifest is not completed: {manifest_path}")

    summaries = _manifest_page_by_id(manifest)
    matrix_pages = _load_matrix_pages(manifest)
    reconstruction_mismatches: list[dict[str, str]] = []
    changed_pages = {label: [] for label in LABELS}
    mapping_fallback_pages = {label: [] for label in LABELS}
    candidate_bc_mismatch_pages: list[str] = []
    pages: dict[str, Any] = {}

    for page_id, summary in summaries.items():
        page = _matrix_for_summary(summary, matrix_pages)
        image_size = _page_image_size(page)
        support = _load_json(_resolve_project_path(str(page["fixed_inputs"]["support_result"])))
        native = page["modes"]["candidate_native_geometry"]["variants"]
        page_result: dict[str, Any] = {
            "score": summary["score"],
            "page_name": summary["page_name"],
            "variants": {},
        }

        for label in LABELS:
            variant = native[label]
            retained = _semantic_signature_from_numbering(variant["numbering"])
            current = _run_current_numbering(
                variant=variant,
                support=support,
                image_size=image_size,
            )
            candidate, mapping_mode = _run_candidate_numbering(
                variant=variant,
                support=support,
                image_size=image_size,
            )

            if current != retained:
                reconstruction_mismatches.append({"page_id": page_id, "label": label})
            if candidate != current:
                changed_pages[label].append(page_id)
            if mapping_mode == "geometry_mapping_guard_fallback":
                mapping_fallback_pages[label].append(page_id)

            page_result["variants"][label] = {
                "retained": retained,
                "current_reconstructed": current,
                "candidate": candidate,
                "mapping_mode": mapping_mode,
                "current_matches_retained": current == retained,
                "candidate_vs_current": _comparison(current, candidate),
            }

        b_candidate = page_result["variants"]["B_b377"]["candidate"]
        c_candidate = page_result["variants"]["C_latest"]["candidate"]
        if b_candidate != c_candidate:
            candidate_bc_mismatch_pages.append(page_id)

        page_result["candidate_B_vs_A"] = _comparison(
            page_result["variants"]["A_pinned"]["candidate"],
            b_candidate,
        )
        page_result["candidate_C_vs_A"] = _comparison(
            page_result["variants"]["A_pinned"]["candidate"],
            c_candidate,
        )
        page_result["candidate_B_vs_C"] = _comparison(b_candidate, c_candidate)

        if (
            page_id in {"page_052", "page_067"}
            or any(page_id in values for values in changed_pages.values())
            or any(page_id in values for values in mapping_fallback_pages.values())
        ):
            pages[page_id] = page_result

    payload = {
        "schema_version": "issue294.mapping_guarded_connector_positive_candidate.v1",
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
            "numbering_reconstructed": True,
        },
        "candidate_rule": {
            "explicit_connector_absence_remains_hard_split": True,
            "explicit_connector_presence_within_normal_distance_merges_without_alignment": True,
            "near_threshold_rescue_keeps_existing_alignment_requirement": True,
            "semantic_staff_evidence_requires_reciprocal_identity_vertical_iou": True,
            "mapping_mismatch_falls_back_to_numbering_geometry": True,
            "new_numeric_mapping_threshold": False,
        },
        "current_reconstruction": {
            "exact_all_pages_all_labels": not reconstruction_mismatches,
            "mismatches": reconstruction_mismatches,
        },
        "candidate_changed_pages": changed_pages,
        "mapping_guard_fallback_pages": mapping_fallback_pages,
        "candidate_B_C_exact_all_pages": not candidate_bc_mismatch_pages,
        "candidate_B_C_mismatch_pages": candidate_bc_mismatch_pages,
        "pages": pages,
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
        default=PROJECT_ROOT / "logs/issue294/issue294_full68_refresh_02/"
        "mapping_guarded_connector_positive_candidate_01.json",
    )
    args = parser.parse_args()
    payload = run(args.full68_manifest, args.output)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "current_reconstruction_exact": payload["current_reconstruction"][
                    "exact_all_pages_all_labels"
                ],
                "candidate_changed_pages": payload["candidate_changed_pages"],
                "mapping_guard_fallback_pages": payload["mapping_guard_fallback_pages"],
                "candidate_B_C_exact_all_pages": payload["candidate_B_C_exact_all_pages"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
