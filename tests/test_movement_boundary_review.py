from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.pipeline.review.movement_boundary_review import (
    MovementBoundaryReviewError,
    attach_movement_boundary_evidence,
    validate_movement_boundary_review,
    write_resolved_movement_boundaries,
)
from src.pipeline.steps.numbering import load_movement_boundary_payload


def _candidate(page: int, system: int, *, candidate_id: str | None = None) -> dict:
    return {
        "id": candidate_id or f"page:{page}:system:{system}",
        "page": page,
        "system": system,
        "state": "ambiguous_review_required",
        "signals": [
            {
                "kind": "system_layout",
                "artifact": "intermediate/numbering_base.json",
                "raw": {
                    "matched_rules": ["relative_indent"],
                    "indent_page_ratio": 0.03,
                },
            }
        ],
        "references": {
            "page_id": f"page_{page + 1:03d}",
            "image": f"inputs/page_{page + 1:03d}.png",
        },
        "provenance": {"review": None},
    }


def _evidence(*candidates: dict) -> dict:
    return {
        "schema_version": "issue333.movement_boundary_evidence.v1",
        "source_document": {
            "sha256": "a" * 64,
            "page_order": "ordered_pipeline_input",
        },
        "input_artifacts": {
            "numbering_base": {
                "path": "intermediate/numbering_base.json",
                "sha256": "b" * 64,
            }
        },
        "producer": {
            "name": "fixture",
            "version": "2",
            "source_commit": "abc123",
            "parameters": {},
        },
        "candidates": list(candidates),
    }


def _review(*items: dict) -> dict:
    return {
        "schema_version": 1,
        "correction_type": "movement_boundary",
        "items": list(items),
    }


def test_export_covers_accepted_rejected_and_manual_boundary(tmp_path: Path) -> None:
    evidence = _evidence(_candidate(0, 1), _candidate(0, 2))
    review = _review(
        {
            "op": "boundary",
            "page": 0,
            "system": 1,
            "reason": "movement heading confirmed",
        },
        {
            "op": "no_boundary",
            "page": 0,
            "system": 2,
            "reason": "ordinary continuation",
        },
        {
            "op": "boundary",
            "page": 0,
            "system": 4,
            "reason": "missed by candidate producer",
        },
    )
    evidence_path = tmp_path / "movement_boundary_evidence.json"
    review_path = tmp_path / "corrections" / "movement_boundaries_review.json"
    output_path = tmp_path / "corrections" / "movement_boundaries.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    review_path.parent.mkdir(parents=True)
    review_path.write_text(
        json.dumps(review, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    resolved = write_resolved_movement_boundaries(
        evidence_path=evidence_path,
        review_path=review_path,
        output_path=output_path,
        evidence_artifact="movement_boundary_evidence.json",
    )

    assert resolved["schema_version"] == "issue268.movement_boundaries.v1"
    assert [(item["page"], item["system"]) for item in resolved["boundaries"]] == [
        (0, 1),
        (0, 4),
    ]
    accepted, manual = resolved["boundaries"]
    assert accepted["source"] == "reviewed_candidate"
    assert accepted["provenance"]["review"]["action"] == "accepted_candidate"
    assert accepted["provenance"]["evidence"]["candidate_id"] == "page:0:system:1"
    assert manual["source"] == "manual"
    assert manual["provenance"]["review"]["action"] == "manual_boundary"
    assert manual["provenance"]["evidence"]["candidate_id"] is None

    # The rejected candidate remains in review staging but never reaches the
    # resolved payload consumed by the existing #268 numbering path.
    assert json.loads(review_path.read_text(encoding="utf-8"))["items"][1]["op"] == "no_boundary"
    assert load_movement_boundary_payload(output_path) == resolved


def test_export_rejects_unresolved_review_required_candidate(tmp_path: Path) -> None:
    evidence_path = tmp_path / "movement_boundary_evidence.json"
    review_path = tmp_path / "corrections" / "movement_boundaries_review.json"
    output_path = tmp_path / "corrections" / "movement_boundaries.json"
    evidence_path.write_text(
        json.dumps(_evidence(_candidate(0, 1), _candidate(0, 2)), indent=2) + "\n",
        encoding="utf-8",
    )
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(
        json.dumps(
            _review(
                {
                    "op": "boundary",
                    "page": 0,
                    "system": 1,
                    "reason": "confirmed",
                }
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        MovementBoundaryReviewError,
        match=r"review-required candidates remain unresolved: \(page=0, system=2\)",
    ):
        write_resolved_movement_boundaries(
            evidence_path=evidence_path,
            review_path=review_path,
            output_path=output_path,
            evidence_artifact="movement_boundary_evidence.json",
        )

    assert not output_path.exists()


def test_candidate_absence_cannot_be_reviewed_as_no_boundary() -> None:
    evidence = _evidence(_candidate(0, 1))

    with pytest.raises(MovementBoundaryReviewError, match="candidate absence"):
        validate_movement_boundary_review(
            _review(
                {
                    "op": "no_boundary",
                    "page": 0,
                    "system": 4,
                    "reason": "not proposed",
                }
            ),
            evidence=evidence,
        )


def test_write_resolved_payload_binds_exact_evidence_bytes(tmp_path: Path) -> None:
    evidence_path = tmp_path / "movement_boundary_evidence.json"
    review_path = tmp_path / "corrections" / "movement_boundaries_review.json"
    output_path = tmp_path / "corrections" / "movement_boundaries.json"
    evidence_bytes = (
        json.dumps(_evidence(_candidate(0, 1)), indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    evidence_path.write_bytes(evidence_bytes)
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(
        json.dumps(
            _review(
                {
                    "op": "boundary",
                    "page": 0,
                    "system": 1,
                    "reason": "confirmed",
                }
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    resolved = write_resolved_movement_boundaries(
        evidence_path=evidence_path,
        review_path=review_path,
        output_path=output_path,
        evidence_artifact="movement_boundary_evidence.json",
    )

    assert output_path.exists()
    assert (
        resolved["boundaries"][0]["provenance"]["evidence"]["sha256"]
        == hashlib.sha256(evidence_bytes).hexdigest()
    )


def test_attach_movement_evidence_keeps_review_package_local(tmp_path: Path) -> None:
    review_root = tmp_path / "review"
    handoff_path = review_root / "manual_correction_input.json"
    handoff_path.parent.mkdir(parents=True)
    handoff_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "manual_correction_input",
                "pages": [
                    {
                        "page_id": "page_001",
                        "page_number": 1,
                        "source_image": "pages/page_001/source.png",
                        "numbering_final": "pages/page_001/numbering_final.json",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    source_evidence = tmp_path / "producer" / "evidence.json"
    source_evidence.parent.mkdir()
    source_evidence.write_text(
        json.dumps(_evidence(_candidate(0, 1)), indent=2) + "\n",
        encoding="utf-8",
    )

    updated = attach_movement_boundary_evidence(
        handoff_path=handoff_path,
        evidence_path=source_evidence,
    )

    assert updated["movement_boundary_evidence"] == "movement_boundary_evidence.json"
    assert updated["movement_boundary_resolved_output"] == "corrections/movement_boundaries.json"
    attached = review_root / "movement_boundary_evidence.json"
    attached_payload = json.loads(attached.read_text(encoding="utf-8"))
    assert attached_payload == _evidence(_candidate(0, 1))


def test_attach_rejects_candidate_page_absent_from_review_package(tmp_path: Path) -> None:
    review_root = tmp_path / "review"
    handoff_path = review_root / "manual_correction_input.json"
    handoff_path.parent.mkdir(parents=True)
    handoff_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "manual_correction_input",
                "pages": [{"page_id": "page_001", "page_number": 1}],
            }
        ),
        encoding="utf-8",
    )
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps(_evidence(_candidate(1, 0))),
        encoding="utf-8",
    )

    with pytest.raises(MovementBoundaryReviewError, match="absent from the review package"):
        attach_movement_boundary_evidence(
            handoff_path=handoff_path,
            evidence_path=evidence_path,
        )


def test_attach_persists_synthesized_candidate_ids(tmp_path: Path) -> None:
    review_root = tmp_path / "review"
    handoff_path = review_root / "manual_correction_input.json"
    handoff_path.parent.mkdir(parents=True)
    handoff_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "manual_correction_input",
                "pages": [
                    {
                        "page_id": "page_001",
                        "page_number": 1,
                        "source_image": "pages/page_001/source.png",
                        "numbering_final": "pages/page_001/numbering_final.json",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    evidence = _evidence(_candidate(0, 0))
    evidence["candidates"][0].pop("id")
    source_evidence = tmp_path / "producer" / "evidence.json"
    source_evidence.parent.mkdir()
    source_evidence.write_text(
        json.dumps(evidence, indent=2) + "\n",
        encoding="utf-8",
    )

    attach_movement_boundary_evidence(
        handoff_path=handoff_path,
        evidence_path=source_evidence,
    )

    attached_payload = json.loads(
        (review_root / "movement_boundary_evidence.json").read_text(encoding="utf-8")
    )
    assert attached_payload["candidates"][0]["id"] == "page:0:system:0"
