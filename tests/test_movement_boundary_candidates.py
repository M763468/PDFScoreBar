from __future__ import annotations

import pytest

from src.pipeline.movement_boundary_candidates import build_movement_boundary_evidence
from src.pipeline.steps.numbering import load_movement_boundary_payload

SOURCE = {"sha256": "a" * 64, "page_order": "ordered_pipeline_input"}


def _system(left: int, top: int, right: int = 900, bottom: int | None = None) -> dict:
    return {
        "staves": [{"bbox": [left, top, right, bottom or top + 50]}],
        "measures": [],
    }


def test_geometry_producer_separates_initial_state_and_review_candidates() -> None:
    numbering = {
        "pages": [
            {
                "width": 1000,
                "height": 1400,
                "systems": [
                    _system(100, 100),
                    _system(100, 300),
                    _system(130, 700),
                    _system(100, 900),
                ],
            }
        ]
    }
    result = build_movement_boundary_evidence(
        numbering,
        source_document=SOURCE,
        producer_source_commit="abc123",
        manifest_pages=[
            {
                "page_id": "page_003",
                "image_path": "inputs/page_003.png",
                "source_reference": {
                    "kind": "direct_pdf_render",
                    "source_page": 2,
                    "source_document": {"sha256": "a" * 64},
                },
            }
        ],
        numbering_artifact="intermediate/numbering_base.json",
    )

    assert result["schema_version"] == "issue333.movement_boundary_evidence.v1"
    assert [(item["system"], item["state"]) for item in result["candidates"]] == [
        (0, "no_boundary"),
        (2, "ambiguous_review_required"),
    ]
    candidate = result["candidates"][1]
    assert candidate["page"] == 0
    assert candidate["references"] == {
        "page_id": "page_003",
        "source_page": 2,
        "source_reference": {
            "kind": "direct_pdf_render",
            "source_page": 2,
            "source_document": {"sha256": "a" * 64},
        },
        "image": "inputs/page_003.png",
    }
    assert candidate["signals"][0]["raw"]["matched_rules"] == [
        "relative_indent",
        "whitespace_outlier",
    ]
    assert "confidence" not in candidate


def test_page_id_is_not_used_as_source_page_provenance() -> None:
    result = build_movement_boundary_evidence(
        {"pages": [{"width": 1000, "height": 1000, "systems": [_system(100, 100)]}]},
        source_document=SOURCE,
        producer_source_commit="abc123",
        manifest_pages=[{"page_id": "page_042", "image_path": "external/reordered.png"}],
    )
    assert result["candidates"][0]["references"] == {
        "page_id": "page_042",
        "image": "external/reordered.png",
    }


def test_evidence_is_not_accepted_as_resolved_consumer_input() -> None:
    evidence = build_movement_boundary_evidence(
        {"pages": [{"width": 1000, "height": 1000, "systems": [_system(100, 100)]}]},
        source_document=SOURCE,
        producer_source_commit="abc123",
    )
    with pytest.raises(ValueError, match="Unsupported movement boundary schema_version"):
        load_movement_boundary_payload(evidence)


def test_manifest_alignment_and_source_digest_are_validated() -> None:
    numbering = {"pages": [{"width": 1000, "height": 1000, "systems": []}]}
    with pytest.raises(ValueError, match="manifest page count"):
        build_movement_boundary_evidence(
            numbering,
            source_document=SOURCE,
            producer_source_commit="abc123",
            manifest_pages=[],
        )
    with pytest.raises(ValueError, match="sha256"):
        build_movement_boundary_evidence(
            numbering,
            source_document={"sha256": "not-a-digest"},
            producer_source_commit="abc123",
        )
