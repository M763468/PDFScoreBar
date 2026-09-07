#!/usr/bin/env python3
"""Evaluate a connector-positive Issue #294 grouping candidate on retained full68 data.

The experiment-only candidate changes one grouping rule:

* explicit connector absence remains a hard split;
* explicit connector presence may merge adjacent staves inside the normal
  DIVISI_DIST_RATIO even when aligned HOMR barline pairs are absent;
* near-threshold connector rescue outside the normal distance keeps the
  existing aligned-barline requirement.

No detector, HOMR, SR, OMR, CNN, OCR, or MMR inference is rerun.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.connector_aware_builder import ConnectorAwareSystemBuilder
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.types import Staff, System
from tools.issue294.audit_full68_retained_semantics import (
    _load_json,
    _load_matrix_pages,
    _manifest_page_by_id,
    _matrix_for_summary,
    _resolve_project_path,
)

LABELS = ("A_pinned", "B_b377", "C_latest")


class ConnectorPositiveWithinDistanceBuilder(ConnectorAwareSystemBuilder):
    """Experiment-only builder making positive connector evidence authoritative nearby."""

    def _group_by_geometry(
        self,
        staves: List[Staff],
        image: Optional[np.ndarray],
        connector_evidence: Optional[Dict[Any, Any]] = None,
    ) -> List[System]:
        if not staves:
            return []

        connector_by_pair = self._normalize_connector_evidence(connector_evidence)
        parent = list(range(len(staves)))

        def find(index: int) -> int:
            if parent[index] != index:
                parent[index] = find(parent[index])
            return parent[index]

        def union(left: int, right: int) -> None:
            root_left = find(left)
            root_right = find(right)
            if root_left != root_right:
                parent[root_right] = root_left

        global_heights = [staff.bbox.height for staff in staves]
        avg_height = sum(global_heights) / len(global_heights) if global_heights else 100.0

        for index in range(len(staves) - 1):
            s1 = staves[index]
            s2 = staves[index + 1]
            gap = s2.bbox.y1 - s1.bbox.y2
            within_distance = gap <= avg_height * self.DIVISI_DIST_RATIO
            within_rescue = gap <= avg_height * self.CONNECTOR_RESCUE_DIST_RATIO

            aligned_pairs = self._find_aligned_pairs(s1, s2)
            pair_evidence = connector_by_pair.get((index, index + 1))
            explicit = pair_evidence is not None
            left_present = self._has_left_connector_evidence(pair_evidence)

            if not within_distance and not (left_present and within_rescue):
                continue

            if explicit and not left_present:
                continue

            # Candidate change: an explicit positive system-start connector plus
            # normal staff proximity is sufficient evidence of one system.
            if left_present and within_distance:
                union(index, index + 1)
                continue

            if image is not None:
                aligned_connection = self._check_aligned_connection(
                    s1, s2, aligned_pairs, image
                )
                if aligned_connection and within_distance:
                    union(index, index + 1)
                    continue
                if (
                    left_present
                    and within_rescue
                    and len(aligned_pairs) >= self.CONNECTOR_RESCUE_MIN_ALIGN_COUNT
                ):
                    union(index, index + 1)
                    continue

            if image is None:
                if within_distance and len(aligned_pairs) >= self.MIN_ALIGN_COUNT:
                    union(index, index + 1)
                elif (
                    left_present
                    and within_rescue
                    and len(aligned_pairs) >= self.CONNECTOR_RESCUE_MIN_ALIGN_COUNT
                ):
                    union(index, index + 1)

        groups: Dict[int, List[Staff]] = {}
        for index in range(len(staves)):
            groups.setdefault(find(index), []).append(staves[index])

        return [
            System(staves=groups[root])
            for root in sorted(groups, key=lambda key: groups[key][0].bbox.y1)
        ]


def _semantic_signature_from_numbering(numbering: Mapping[str, Any]) -> list[dict[str, Any]]:
    pages = numbering.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Numbering signature lacks pages")
    return [
        {
            "staff_count": int(system["staff_count"]),
            "measure_count": int(system["measure_count"]),
            "measure_numbers": [int(number) for number in system["measure_numbers"]],
        }
        for page in pages
        for system in page["systems"]
    ]


def _semantic_signature_from_score(score: Any) -> list[dict[str, Any]]:
    return [
        {
            "staff_count": len(system.staves),
            "measure_count": len(system.measures),
            "measure_numbers": [int(measure.number) for measure in system.measures],
        }
        for page in score.pages
        for system in page.systems
    ]


def _nonempty(signature: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in signature if int(item["measure_count"]) > 0]


def _numbers(signature: list[dict[str, Any]]) -> list[int]:
    return [
        int(number)
        for system in signature
        for number in system["measure_numbers"]
    ]


def _comparison(
    left: list[dict[str, Any]], right: list[dict[str, Any]]
) -> dict[str, Any]:
    left_nonempty = _nonempty(left)
    right_nonempty = _nonempty(right)
    return {
        "raw_system_signature_equal": left == right,
        "nonempty_system_signature_equal": left_nonempty == right_nonempty,
        "total_measures_equal": sum(int(item["measure_count"]) for item in left)
        == sum(int(item["measure_count"]) for item in right),
        "numbering_equal": _numbers(left) == _numbers(right),
    }


def _page_image_size(page: Mapping[str, Any]) -> tuple[int, int]:
    image_path = _resolve_project_path(str(page["image"]))
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(image_path)
    height, width = image.shape[:2]
    return width, height


def _run_numbering(
    *,
    variant: Mapping[str, Any],
    support: Mapping[str, Any],
    image_size: tuple[int, int],
    candidate: bool,
) -> list[dict[str, Any]]:
    pipeline = MeasureNumberingPipeline()
    if candidate:
        pipeline.builder = ConnectorPositiveWithinDistanceBuilder()

    staff_mask = _resolve_project_path(str(variant["staff_mask"]))
    score = pipeline.run_sequential(
        [
            {
                "barlines": variant["final_barlines"],
                "staff_mask": str(staff_mask),
                "image_size": image_size,
                "page_number": 1,
                "connector_mask_paths": {
                    "symbols": str(
                        _resolve_project_path(str(support["connector_symbols"]))
                    ),
                    "brace_dot": str(
                        _resolve_project_path(str(support["connector_brace_dot"]))
                    ),
                },
            }
        ]
    )
    return _semantic_signature_from_score(score)


def run(manifest_path: Path, output_path: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, Mapping) or manifest.get("status") != "completed":
        raise ValueError(f"Full68 manifest is not completed: {manifest_path}")

    summaries = _manifest_page_by_id(manifest)
    matrix_pages = _load_matrix_pages(manifest)
    pages: dict[str, Any] = {}
    reconstruction_mismatches: list[dict[str, str]] = []
    changed_pages = {label: [] for label in LABELS}
    candidate_bc_mismatch_pages: list[str] = []

    for page_id, summary in summaries.items():
        page = _matrix_for_summary(summary, matrix_pages)
        image_size = _page_image_size(page)
        support = _load_json(
            _resolve_project_path(str(page["fixed_inputs"]["support_result"]))
        )
        native = page["modes"]["candidate_native_geometry"]["variants"]

        page_result: dict[str, Any] = {
            "score": summary["score"],
            "page_name": summary["page_name"],
            "variants": {},
        }

        for label in LABELS:
            variant = native[label]
            retained = _semantic_signature_from_numbering(variant["numbering"])
            current = _run_numbering(
                variant=variant,
                support=support,
                image_size=image_size,
                candidate=False,
            )
            candidate_signature = _run_numbering(
                variant=variant,
                support=support,
                image_size=image_size,
                candidate=True,
            )

            if current != retained:
                reconstruction_mismatches.append(
                    {"page_id": page_id, "label": label}
                )
            if candidate_signature != current:
                changed_pages[label].append(page_id)

            page_result["variants"][label] = {
                "retained": retained,
                "current_reconstructed": current,
                "candidate": candidate_signature,
                "current_matches_retained": current == retained,
                "candidate_vs_current": _comparison(current, candidate_signature),
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
            page_id == "page_052"
            or any(page_id in values for values in changed_pages.values())
        ):
            pages[page_id] = page_result

    payload = {
        "schema_version": "issue294.connector_positive_grouping_candidate.v1",
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
        },
        "current_reconstruction": {
            "exact_all_pages_all_labels": not reconstruction_mismatches,
            "mismatches": reconstruction_mismatches,
        },
        "candidate_changed_pages": changed_pages,
        "candidate_B_C_exact_all_pages": not candidate_bc_mismatch_pages,
        "candidate_B_C_mismatch_pages": candidate_bc_mismatch_pages,
        "pages": pages,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--full68-manifest",
        type=Path,
        default=PROJECT_ROOT
        / "logs/issue294/issue294_full68_refresh_02/full68_host.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT
        / "logs/issue294/issue294_full68_refresh_02/"
        "connector_positive_grouping_candidate_01.json",
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
                "candidate_B_C_exact_all_pages": payload[
                    "candidate_B_C_exact_all_pages"
                ],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
