from __future__ import annotations

import pytest

from src.pipeline.movement_boundary_candidates import build_movement_boundary_evidence
from src.pipeline.steps.numbering import load_movement_boundary_payload

SOURCE = {"sha256": "a" * 64, "page_order": "ordered_pipeline_input"}
NUMBERING_ARTIFACT = "intermediate/numbering_base.json"
NUMBERING_SHA256 = "b" * 64


def _system(left: int, top: int, right: int = 900, bottom: int | None = None) -> dict:
    return {
        "staves": [{"bbox": [left, top, right, bottom or top + 50]}],
        "measures": [],
    }


def _build(numbering: dict, **kwargs) -> dict:
    return build_movement_boundary_evidence(
        numbering,
        source_document=kwargs.pop("source_document", SOURCE),
        producer_source_commit="abc123",
        numbering_artifact=NUMBERING_ARTIFACT,
        numbering_artifact_sha256=NUMBERING_SHA256,
        **kwargs,
    )


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
    result = _build(
        numbering,
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
    )

    assert result["schema_version"] == "issue333.movement_boundary_evidence.v1"
    assert result["input_artifacts"]["numbering_base"] == {
        "path": NUMBERING_ARTIFACT,
        "sha256": NUMBERING_SHA256,
    }
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
    assert candidate["signals"][0]["raw"]["geometry_representation"] == "all_staff_union"
    assert "confidence" not in candidate


def test_geometry_producer_uses_all_staff_union_for_system_spacing() -> None:
    numbering = {
        "pages": [
            {
                "width": 1000,
                "height": 1400,
                "systems": [
                    {"staves": [{"bbox": [100, 100, 900, 150]}, {"bbox": [110, 260, 910, 310]}]},
                    {"staves": [{"bbox": [150, 500, 900, 550]}, {"bbox": [160, 660, 910, 710]}]},
                ],
            }
        ]
    }
    result = _build(numbering)
    assert result["producer"]["version"] == "2"
    raw = result["candidates"][1]["signals"][0]["raw"]
    assert raw["system_bbox"] == [150.0, 500.0, 910.0, 710.0]
    assert raw["geometry_representation"] == "all_staff_union"


def test_page_id_is_not_used_as_source_page_provenance() -> None:
    result = _build(
        {"pages": [{"width": 1000, "height": 1000, "systems": [_system(100, 100)]}]},
        manifest_pages=[
            {
                "page_id": "page_042",
                "image_path": "external/reordered.png",
                "source_reference": {"kind": "external_mapping", "source_page": 42},
            }
        ],
    )
    assert result["candidates"][0]["references"] == {
        "page_id": "page_042",
        "image": "external/reordered.png",
    }


def test_direct_source_reference_must_match_top_level_digest() -> None:
    numbering = {"pages": [{"width": 1000, "height": 1000, "systems": [_system(100, 100)]}]}
    valid = {
        "page_id": "page_001",
        "source_reference": {
            "kind": "direct_pdf_render",
            "source_page": 0,
            "source_document": {"sha256": "a" * 64},
        },
    }
    evidence = _build(numbering, manifest_pages=[valid])
    assert evidence["candidates"][0]["references"]["source_page"] == 0
    assert evidence["candidates"][0]["references"]["source_reference"] == valid["source_reference"]

    for source_reference in (
        {
            "kind": "direct_pdf_render",
            "source_page": 0,
            "source_document": {"sha256": "b" * 64},
        },
        {"kind": "direct_pdf_render", "source_page": 0, "source_document": {}},
        {
            "kind": "direct_pdf_render",
            "source_page": True,
            "source_document": {"sha256": "a" * 64},
        },
    ):
        with pytest.raises(ValueError, match="direct_pdf_render"):
            _build(
                numbering,
                manifest_pages=[{"page_id": "page_001", "source_reference": source_reference}],
            )


def test_evidence_is_not_accepted_as_resolved_consumer_input() -> None:
    evidence = _build({"pages": [{"width": 1000, "height": 1000, "systems": [_system(100, 100)]}]})
    with pytest.raises(ValueError, match="Unsupported movement boundary schema_version"):
        load_movement_boundary_payload(evidence)


def test_numbering_artifact_digest_is_retained_without_candidates() -> None:
    result = _build({"pages": [{"width": 1000, "height": 1000, "systems": []}]})
    assert result["candidates"] == []
    assert result["input_artifacts"]["numbering_base"] == {
        "path": NUMBERING_ARTIFACT,
        "sha256": NUMBERING_SHA256,
    }


def test_manifest_alignment_and_source_digest_are_validated() -> None:
    numbering = {"pages": [{"width": 1000, "height": 1000, "systems": []}]}
    with pytest.raises(ValueError, match="manifest page count"):
        _build(numbering, manifest_pages=[])
    with pytest.raises(ValueError, match="sha256"):
        _build(numbering, source_document={"sha256": "not-a-digest"})


def test_numbering_artifact_digest_is_required_and_validated() -> None:
    numbering = {"pages": [{"width": 1000, "height": 1000, "systems": []}]}
    with pytest.raises(ValueError, match="numbering_artifact must be non-empty"):
        build_movement_boundary_evidence(
            numbering,
            source_document=SOURCE,
            producer_source_commit="abc123",
            numbering_artifact="",
            numbering_artifact_sha256=NUMBERING_SHA256,
        )
    with pytest.raises(ValueError, match="numbering_artifact_sha256"):
        build_movement_boundary_evidence(
            numbering,
            source_document=SOURCE,
            producer_source_commit="abc123",
            numbering_artifact=NUMBERING_ARTIFACT,
            numbering_artifact_sha256="not-a-digest",
        )
