import json
from pathlib import Path

from src.pipeline.steps.numbering import load_movement_boundary_payload

FIXTURE = (
    Path(__file__).parent / "fixtures" / "movement_boundaries" / "issue333_representative.json"
)


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_issue333_representative_fixture_covers_required_boundary_shapes() -> None:
    fixture = _load_fixture()
    boundaries = fixture["boundaries"]
    negatives = fixture["reviewed_negatives"]

    assert fixture["coordinate_system"] == {
        "page": "zero-based source PDF page",
        "system": "zero-based system in fresh current-pipeline numbering_base artifact",
    }
    assert any(item["placement"] == "page_start" for item in boundaries)
    assert any(item["placement"] == "mid_page" for item in boundaries)
    assert (
        len([item for item in boundaries if item["score"] == "prokofiev1" and item["page"] == 3])
        == 2
    )

    reasons = {item["reason"] for item in negatives}
    assert "ordinary_page_continuation" in reasons
    assert "multi_page_movement_continuation" in reasons
    assert "strong_whitespace_without_movement" in reasons
    assert "heading_like_tempo_change_without_movement" in reasons
    assert "end_like_barline_without_following_reset" in reasons


def test_issue333_fixture_boundaries_are_valid_issue268_manual_inputs() -> None:
    fixture = _load_fixture()
    for score in {item["score"] for item in fixture["boundaries"]}:
        resolved = {
            "schema_version": "issue268.movement_boundaries.v1",
            "boundaries": [
                {
                    "page": item["page"],
                    "system": item["system"],
                    "reset_number": 1,
                    "source": "manual",
                    "provenance": {
                        "kind": "issue333_representative_fixture",
                        "score": score,
                        "movement": item["movement"],
                    },
                }
                for item in fixture["boundaries"]
                if item["score"] == score
            ],
        }
        assert load_movement_boundary_payload(resolved) == resolved


def test_issue333_fixture_has_no_measure_level_boundary() -> None:
    fixture = _load_fixture()
    assert all("measure" not in boundary for boundary in fixture["boundaries"])
