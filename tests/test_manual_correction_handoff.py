import json
from pathlib import Path

import pytest

from src.pipeline.review.manual_correction_handoff import (
    ManualCorrectionHandoffError,
    build_manual_gui_config,
    canonicalize_manual_correction_outputs,
    validate_manual_correction_handoff,
)


def _write_json(path: Path, payload: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload or {}, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str = "placeholder") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _review_package(tmp_path: Path, *, include_strict: bool = True) -> tuple[Path, dict]:
    review_root = tmp_path / "output" / "review"
    page_root = review_root / "pages" / "page_003"
    _write_text(page_root / "source.png")
    _write_json(page_root / "numbering_final.json")
    if include_strict:
        _write_text(page_root / "review_overlay.png")
        _write_json(page_root / "mmr_overrides.json")
        _write_json(page_root / "barlines_review.json")

    page = {
        "page_id": "page_003",
        "page_number": 3,
        "source_image": "pages/page_003/source.png",
        "numbering_final": "pages/page_003/numbering_final.json",
        "correction_output": "corrections",
    }
    if include_strict:
        page.update(
            {
                "review_overlay": "pages/page_003/review_overlay.png",
                "mmr_overrides": "pages/page_003/mmr_overrides.json",
                "barlines_review": "pages/page_003/barlines_review.json",
            }
        )

    handoff = {
        "schema_version": 1,
        "kind": "manual_correction_input",
        "pages": [page],
    }
    handoff_path = review_root / "manual_correction_input.json"
    _write_json(handoff_path, handoff)
    return handoff_path, handoff


def test_build_manual_gui_config_maps_handoff_to_current_gui_config(tmp_path):
    handoff_path, handoff = _review_package(tmp_path)

    config = build_manual_gui_config(
        handoff,
        handoff_path=handoff_path,
        mode="issue229_smoke_strict",
        require_existing_artifacts=True,
    )

    assert config["source"] == "manual_correction_input"
    assert config["pages"] == [
        {
            "name": "page_003",
            "page": 2,
            "source_page_number": 3,
            "image": "pages/page_003/source.png",
            "numbering": "pages/page_003/numbering_final.json",
            "manual_outputs": {
                "mmr_measure_span": "corrections/mmr_measure_spans.json",
                "measure_construction": "corrections/measure_construction_overrides.json",
                "barline_construction": "corrections/barline_construction_overrides.json",
            },
            "mmr": "pages/page_003/mmr_overrides.json",
            "barlines": "pages/page_003/barlines_review.json",
            "review_overlay": "pages/page_003/review_overlay.png",
        }
    ]
    assert "_staging" not in json.dumps(config)


def test_handoff_base_mode_allows_missing_optional_review_evidence(tmp_path):
    handoff_path, handoff = _review_package(tmp_path, include_strict=False)

    normalized = validate_manual_correction_handoff(
        handoff,
        handoff_path=handoff_path,
        mode="base_v1",
        require_existing_artifacts=True,
    )

    assert normalized["pages"][0]["gui_page_index_zero_based"] == 2
    assert "mmr_overrides" not in normalized["pages"][0]


def test_handoff_strict_mode_requires_review_evidence(tmp_path):
    handoff_path, handoff = _review_package(tmp_path, include_strict=False)

    with pytest.raises(ManualCorrectionHandoffError, match="required in strict mode"):
        validate_manual_correction_handoff(
            handoff,
            handoff_path=handoff_path,
            mode="issue229_smoke_strict",
        )


def test_handoff_rejects_package_escape_paths(tmp_path):
    handoff_path, handoff = _review_package(tmp_path)
    handoff["pages"][0]["source_image"] = "../logs/unrelated/source.png"

    with pytest.raises(ManualCorrectionHandoffError, match="inside the review package"):
        validate_manual_correction_handoff(handoff, handoff_path=handoff_path)


def test_handoff_rejects_non_positive_page_number(tmp_path):
    handoff_path, handoff = _review_package(tmp_path)
    handoff["pages"][0]["page_number"] = 0

    with pytest.raises(ManualCorrectionHandoffError, match="page_number must be >= 1"):
        validate_manual_correction_handoff(handoff, handoff_path=handoff_path)


def test_handoff_uses_explicit_correction_outputs_without_staging_suffix(tmp_path):
    handoff_path, handoff = _review_package(tmp_path)
    handoff["pages"][0].pop("correction_output")
    handoff["pages"][0]["correction_outputs"] = {
        "mmr_measure_span": "corrections/custom_mmr.json",
        "measure_construction": "corrections/custom_measure.json",
        "barline_construction": "corrections/custom_barline.json",
    }

    config = build_manual_gui_config(handoff, handoff_path=handoff_path)

    assert config["pages"][0]["manual_outputs"] == handoff["pages"][0]["correction_outputs"]
    assert all("_staging" not in key for key in config["pages"][0]["manual_outputs"])


def test_canonicalize_manual_correction_outputs_writes_pipeline_payloads(tmp_path):
    corrections = tmp_path / "review" / "corrections"
    _write_json(
        corrections / "measure_construction_overrides.json",
        {
            "schema_version": 1,
            "correction_type": "measure_construction",
            "items": [
                {
                    "op": "force_measure",
                    "page": 2,
                    "system": 1,
                    "interval": 4,
                    "reason": "manual measure construction",
                }
            ],
        },
    )
    _write_json(
        corrections / "mmr_measure_spans.json",
        {
            "schema_version": 1,
            "correction_type": "mmr_measure_span",
            "items": [
                {
                    "op": "set_measure_span",
                    "page": 2,
                    "system": 1,
                    "measure": 5,
                    "measure_span": 4,
                    "reason": "manual MMR span",
                }
            ],
        },
    )
    _write_json(
        corrections / "barline_construction_overrides.json",
        {
            "schema_version": 1,
            "correction_type": "barline_construction",
            "items": [
                {
                    "op": "add_barline",
                    "page": 2,
                    "bbox": [10, 20, 12, 100],
                    "reason": "manual barline",
                }
            ],
        },
    )

    outputs = canonicalize_manual_correction_outputs(corrections)

    assert outputs == {
        "measure_overrides": corrections / "measure_overrides.json",
        "barline_overrides": corrections / "barline_overrides.json",
    }
    measure_payload = json.loads((corrections / "measure_overrides.json").read_text())
    assert measure_payload["measure_overrides"] == [
        {
            "page": 2,
            "system": 1,
            "measure": 4,
            "force_measure": True,
            "comment": "manual measure construction",
            "source": "manual:measure_construction",
        },
        {
            "page": 2,
            "system": 1,
            "measure": 5,
            "skip": 3,
            "comment": "manual MMR span",
            "source": "manual:mmr_measure_span",
        },
    ]
    assert measure_payload["overrides"] == measure_payload["measure_overrides"]

    barline_payload = json.loads((corrections / "barline_overrides.json").read_text())
    assert barline_payload == {
        "barline_overrides": [
            {
                "page": 2,
                "op": "add",
                "bbox": [10, 20, 12, 100],
                "comment": "manual barline",
                "source": "manual:barline_construction",
            }
        ]
    }


def test_canonicalize_refuses_to_overwrite_existing_outputs(tmp_path):
    corrections = tmp_path / "review" / "corrections"
    _write_json(corrections / "mmr_measure_spans.json", {"correction_type": "mmr_measure_span"})
    _write_json(corrections / "measure_overrides.json", {"measure_overrides": []})

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        canonicalize_manual_correction_outputs(corrections)


def test_canonicalize_requires_existing_corrections_directory(tmp_path):
    missing = tmp_path / "missing_corrections"

    with pytest.raises(FileNotFoundError, match="Corrections directory"):
        canonicalize_manual_correction_outputs(missing)


def test_canonicalize_allows_explicit_overwrite(tmp_path):
    corrections = tmp_path / "review" / "corrections"
    _write_json(corrections / "mmr_measure_spans.json", {"correction_type": "mmr_measure_span"})
    _write_json(corrections / "measure_overrides.json", {"measure_overrides": []})
    _write_json(corrections / "barline_overrides.json", {"barline_overrides": []})

    outputs = canonicalize_manual_correction_outputs(corrections, overwrite=True)

    assert outputs["measure_overrides"].exists()
    assert outputs["barline_overrides"].exists()
