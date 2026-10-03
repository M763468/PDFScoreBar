import json

import pytest

from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.types import Barline, BBox, Page, Score, Staff, System
from src.pipeline.review.apply_corrections import (
    _load_movement_boundary_input,
    apply_corrections_and_rerun,
)


def _handoff(tmp_path, *, movement_path="corrections/movement_boundaries.json"):
    handoff_path = tmp_path / "review" / "manual_correction_input.json"
    handoff_path.parent.mkdir(parents=True)
    (handoff_path.parent / "corrections").mkdir()
    handoff_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "movement_boundary_resolved_output": movement_path,
                "pages": [
                    {
                        "page_id": "p1",
                        "page_number": 1,
                        "source_image": "page.png",
                        "numbering_final": "numbering.json",
                        "correction_output": "corrections",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return handoff_path


def test_finalized_package_movement_output_is_authoritative(tmp_path):
    handoff_path = _handoff(tmp_path)
    movement_path = handoff_path.parent / "corrections" / "movement_boundaries.json"
    movement_path.write_text(
        json.dumps(
            {
                "schema_version": "issue268.movement_boundaries.v1",
                "boundaries": [
                    {
                        "page": 0,
                        "system": 1,
                        "reset_number": 1,
                        "source": "reviewed_candidate",
                        "provenance": {"kind": "movement_boundary_review"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload, consumed_path, digest = _load_movement_boundary_input(
        normalized_handoff={
            "movement_boundary_resolved_output": "corrections/movement_boundaries.json"
        },
        package_root=handoff_path.parent,
        source_config={"inputs": {"movement_boundaries": {"boundaries": []}}},
    )

    assert payload["boundaries"][0]["system"] == 1
    assert consumed_path == movement_path
    assert digest and len(digest) == 64


def test_missing_reviewed_movement_output_uses_source_config(tmp_path):
    handoff_path = _handoff(tmp_path)
    source = {
        "schema_version": "issue268.movement_boundaries.v1",
        "boundaries": [
            {
                "page": 0,
                "system": 0,
                "reset_number": 1,
                "source": "configured",
                "provenance": {"kind": "source"},
            }
        ],
    }

    payload, consumed_path, digest = _load_movement_boundary_input(
        normalized_handoff={
            "movement_boundary_resolved_output": "corrections/movement_boundaries.json"
        },
        package_root=handoff_path.parent,
        source_config={"inputs": {"movement_boundaries": source}},
    )

    assert payload["boundaries"][0]["source"] == "configured"
    assert consumed_path is None
    assert digest is None


def test_review_artifact_cannot_substitute_unresolved_candidates(tmp_path):
    handoff_path = _handoff(tmp_path)
    movement_path = handoff_path.parent / "corrections" / "movement_boundaries.json"
    movement_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "correction_type": "movement_boundary",
                "items": [{"op": "boundary", "page": 0, "system": 1}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported movement boundary schema_version"):
        _load_movement_boundary_input(
            normalized_handoff={
                "movement_boundary_resolved_output": "corrections/movement_boundaries.json"
            },
            package_root=handoff_path.parent,
            source_config={"inputs": {"movement_boundaries": {"boundaries": []}}},
        )


def test_stale_resolved_output_is_rejected_after_saved_review_changes(tmp_path):
    handoff_path = _handoff(tmp_path)
    evidence = {"schema_version": "issue333.movement_boundary_evidence.v1", "candidates": []}
    review = {
        "schema_version": 1,
        "correction_type": "movement_boundary",
        "items": [{"op": "boundary", "page": 0, "system": 1}],
    }
    (handoff_path.parent / "movement_boundary_evidence.json").write_text(
        json.dumps(evidence), encoding="utf-8"
    )
    (handoff_path.parent / "corrections" / "movement_boundaries_review.json").write_text(
        json.dumps(review), encoding="utf-8"
    )
    (handoff_path.parent / "corrections" / "movement_boundaries.json").write_text(
        json.dumps({"schema_version": "issue268.movement_boundaries.v1", "boundaries": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="stale; export the current saved review"):
        _load_movement_boundary_input(
            normalized_handoff={
                "movement_boundary_evidence": "movement_boundary_evidence.json",
                "movement_boundary_resolved_output": "corrections/movement_boundaries.json",
                "pages": [
                    {
                        "manual_outputs": {
                            "movement_boundary": "corrections/movement_boundaries_review.json"
                        }
                    }
                ],
            },
            package_root=handoff_path.parent,
            source_config={"inputs": {"movement_boundaries": {"boundaries": []}}},
        )


def test_saved_movement_decisions_require_finalized_export(tmp_path):
    handoff_path = _handoff(tmp_path)
    evidence = {"schema_version": "issue333.movement_boundary_evidence.v1", "candidates": []}
    review = {
        "schema_version": 1,
        "correction_type": "movement_boundary",
        "items": [{"op": "boundary", "page": 0, "system": 1}],
    }
    (handoff_path.parent / "movement_boundary_evidence.json").write_text(
        json.dumps(evidence), encoding="utf-8"
    )
    (handoff_path.parent / "corrections" / "movement_boundaries_review.json").write_text(
        json.dumps(review), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="saved but not finalized"):
        _load_movement_boundary_input(
            normalized_handoff={
                "movement_boundary_evidence": "movement_boundary_evidence.json",
                "movement_boundary_resolved_output": "corrections/movement_boundaries.json",
                "pages": [
                    {
                        "manual_outputs": {
                            "movement_boundary": "corrections/movement_boundaries_review.json"
                        }
                    }
                ],
            },
            package_root=handoff_path.parent,
            source_config={"inputs": {"movement_boundaries": {"boundaries": []}}},
        )


def test_empty_reviewed_output_removes_source_reset_from_corrected_numbering(tmp_path):
    handoff_path = _handoff(tmp_path)
    evidence = {"schema_version": "issue333.movement_boundary_evidence.v1", "candidates": []}
    review = {"schema_version": 1, "correction_type": "movement_boundary", "items": []}
    evidence_path = handoff_path.parent / "movement_boundary_evidence.json"
    review_path = handoff_path.parent / "corrections" / "movement_boundaries_review.json"
    resolved_path = handoff_path.parent / "corrections" / "movement_boundaries.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    review_path.write_text(json.dumps(review), encoding="utf-8")
    resolved_path.write_text(
        json.dumps({"schema_version": "issue268.movement_boundaries.v1", "boundaries": []}),
        encoding="utf-8",
    )
    source_boundaries = {
        "schema_version": "issue268.movement_boundaries.v1",
        "boundaries": [
            {
                "page": 0,
                "system": 1,
                "reset_number": 1,
                "source": "source-run",
                "provenance": {"kind": "source"},
            }
        ],
    }

    reviewed, consumed_path, _ = _load_movement_boundary_input(
        normalized_handoff={
            "movement_boundary_evidence": "movement_boundary_evidence.json",
            "movement_boundary_resolved_output": "corrections/movement_boundaries.json",
            "pages": [
                {
                    "manual_outputs": {
                        "movement_boundary": "corrections/movement_boundaries_review.json"
                    }
                }
            ],
        },
        package_root=handoff_path.parent,
        source_config={"inputs": {"movement_boundaries": source_boundaries}},
    )
    assert consumed_path == resolved_path

    def numbered(boundaries):
        page = Page(page_number=1)
        for _ in range(2):
            staff = Staff(bbox=BBox(0, 100, 1000, 200))
            for x in [0, 300, 500]:
                staff.barlines.append(Barline(bbox=BBox(x, 100, x + 2, 200)))
            page.systems.append(System(staves=[staff]))
        score = Score()
        score.pages.append(page)
        resets = {(0, item["system"]): item["reset_number"] for item in boundaries}
        MeasureNumberer().number_score(score, start_number=10, boundary_resets=resets)
        return [measure.number for system in score.pages[0].systems for measure in system.measures]

    assert numbered(reviewed["boundaries"]) == [10, 11, 12, 13]
    assert numbered(source_boundaries["boundaries"]) == [10, 11, 1, 2]


def test_run_id_must_be_a_single_path_component(tmp_path):
    handoff_path = tmp_path / "review" / "manual_correction_input.json"
    handoff_path.parent.mkdir()
    source_run = tmp_path / "source"
    source_run.mkdir()
    (source_run / "manifest.json").write_text(
        json.dumps({"config": {"inputs": {}, "steps": {}, "outputs": {}}}),
        encoding="utf-8",
    )
    handoff_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_manifest": str(source_run / "manifest.json"),
                "pages": [
                    {
                        "page_id": "p1",
                        "page_number": 1,
                        "source_image": "page.png",
                        "numbering_final": "numbering.json",
                        "correction_output": "corrections",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="single safe path component"):
        apply_corrections_and_rerun(handoff_path, run_id="../escape")


def test_corrected_run_collision_is_rejected_before_overrides_are_written(tmp_path):
    handoff_path = tmp_path / "review" / "manual_correction_input.json"
    handoff_path.parent.mkdir()
    source_run = tmp_path / "source"
    source_run.mkdir()
    (source_run / "manifest.json").write_text(
        json.dumps({"config": {"inputs": {}, "steps": {}, "outputs": {}}}),
        encoding="utf-8",
    )
    handoff_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_manifest": str(source_run / "manifest.json"),
                "pages": [
                    {
                        "page_id": "p1",
                        "page_number": 1,
                        "source_image": "page.png",
                        "numbering_final": "numbering.json",
                        "correction_output": "corrections",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    occupied = tmp_path / "corrected_exists"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to reuse or overwrite"):
        apply_corrections_and_rerun(handoff_path, run_id="corrected_exists", overwrite=True)

    assert sorted(p.name for p in handoff_path.parent.iterdir()) == ["manual_correction_input.json"]
    assert (occupied / "keep.txt").read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize(
    "boundaries",
    [
        [],
        [
            {
                "page": 0,
                "system": 0,
                "reset_number": 1,
                "source": "reviewed_candidate",
                "provenance": {"kind": "movement_boundary_review"},
            }
        ],
    ],
)
def test_retained_config_records_exact_reviewed_movement_input(tmp_path, boundaries):
    handoff = _handoff(tmp_path)
    source = {
        "schema_version": "issue268.movement_boundaries.v1",
        "boundaries": [
            {
                "page": 0,
                "system": 1,
                "reset_number": 1,
                "source": "configured",
                "provenance": {"kind": "source"},
            }
        ],
    }
    reviewed = {"schema_version": "issue268.movement_boundaries.v1", "boundaries": boundaries}
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {"config": {"inputs": {"movement_boundaries": source}, "steps": {}, "outputs": {}}}
        )
    )
    (handoff.parent / "corrections/movement_boundaries.json").write_text(json.dumps(reviewed))
    run = apply_corrections_and_rerun(
        handoff, output_root=tmp_path / "runs", run_id="exact_reviewed", dry_run=True
    )
    config = json.loads((run / "corrected_pipeline_config.json").read_text())
    assert config["inputs"]["movement_boundaries"] == reviewed
    assert source != reviewed
