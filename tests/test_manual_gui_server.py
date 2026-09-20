import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.gt_relabel_gui.server import (
    _manual_handoff_config,
    _manual_output_for,
    _page_config_for,
)


def _write_json(path: Path, payload: object | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload or {}, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str = "placeholder") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _strict_review_handoff(tmp_path: Path) -> Path:
    review_root = tmp_path / "source_run" / "review"
    page_root = review_root / "pages" / "page_001"

    _write_text(page_root / "source.png")
    _write_json(page_root / "numbering_final.json")
    _write_text(page_root / "review_overlay.png")
    _write_json(page_root / "mmr_overrides.json")
    _write_json(page_root / "barlines_review.json")

    handoff_path = review_root / "manual_correction_input.json"
    _write_json(
        handoff_path,
        {
            "schema_version": 1,
            "kind": "manual_correction_input",
            "pages": [
                {
                    "page_id": "page_001",
                    "page_number": 1,
                    "source_image": "pages/page_001/source.png",
                    "numbering_final": "pages/page_001/numbering_final.json",
                    "review_overlay": "pages/page_001/review_overlay.png",
                    "mmr_overrides": "pages/page_001/mmr_overrides.json",
                    "barlines_review": "pages/page_001/barlines_review.json",
                    "correction_output": "corrections",
                }
            ],
        },
    )
    return handoff_path


def test_manual_output_for_uses_page_local_manual_outputs_by_page_index():
    server = SimpleNamespace(
        gt_config=[
            {
                "name": "page_001",
                "page": 0,
                "manual_outputs": {
                    "mmr_measure_span": "pages/page_001/corrections/mmr.json",
                },
            },
            {
                "name": "page_003",
                "page": 2,
                "manual_outputs": {
                    "mmr_measure_span": "corrections/mmr_measure_spans.json",
                    "barline_construction": "corrections/barline_construction_overrides.json",
                },
            },
        ]
    )

    assert _page_config_for(server, 2)["name"] == "page_003"
    assert _manual_output_for(server, "mmr_measure_span", 2) == "corrections/mmr_measure_spans.json"
    assert (
        _manual_output_for(server, "barline_construction", "2")
        == "corrections/barline_construction_overrides.json"
    )


def test_manual_output_for_matches_page_name_and_rejects_missing_outputs():
    server = SimpleNamespace(
        gt_config=[
            {"name": "page_003", "page_index": 2},
            {
                "name": "page_004",
                "page_index": 3,
                "manual_outputs": {
                    "measure_construction": "corrections/measure_construction_overrides.json",
                },
            },
        ]
    )

    assert _page_config_for(server, "page_004")["page_index"] == 3
    assert (
        _manual_output_for(server, "measure_construction", "page_004")
        == "corrections/measure_construction_overrides.json"
    )
    assert _manual_output_for(server, "measure_construction", "page_003") is None
    assert _manual_output_for(server, "mmr_measure_span", "page_004") is None
    assert _manual_output_for(server, "mmr_measure_span", "missing") is None


def test_manual_handoff_config_uses_strict_review_package_root(tmp_path):
    handoff_path = _strict_review_handoff(tmp_path)

    root, pages = _manual_handoff_config(handoff_path)

    assert root == handoff_path.parent.resolve()
    assert pages == [
        {
            "name": "page_001",
            "page": 0,
            "source_page_number": 1,
            "image": "pages/page_001/source.png",
            "numbering": "pages/page_001/numbering_final.json",
            "manual_outputs": {
                "mmr_measure_span": "corrections/mmr_measure_spans.json",
                "measure_construction": "corrections/measure_construction_overrides.json",
                "barline_construction": "corrections/barline_construction_overrides.json",
            },
            "mmr": "pages/page_001/mmr_overrides.json",
            "barlines": "pages/page_001/barlines_review.json",
            "review_overlay": "pages/page_001/review_overlay.png",
        }
    ]


def test_manual_handoff_config_rejects_missing_strict_artifact(tmp_path):
    handoff_path = _strict_review_handoff(tmp_path)
    (handoff_path.parent / "pages" / "page_001" / "barlines_review.json").unlink()

    with pytest.raises(ValueError, match="does not exist"):
        _manual_handoff_config(handoff_path)
