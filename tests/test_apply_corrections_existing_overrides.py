import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

sys.modules.setdefault("fitz", types.SimpleNamespace())

from src.pipeline.review.apply_corrections import apply_corrections_and_rerun


def test_apply_corrections_carries_forward_existing_override_inputs(tmp_path: Path):
    run_dir = tmp_path / "original_run"
    review_dir = run_dir / "review"
    corrections_dir = review_dir / "corrections"
    existing_dir = tmp_path / "existing"
    review_dir.mkdir(parents=True)
    corrections_dir.mkdir()
    existing_dir.mkdir()

    existing_measure_path = existing_dir / "measure_overrides.json"
    existing_measure_path.write_text(
        json.dumps(
            {
                "measure_overrides": [
                    {
                        "page": 1,
                        "system": 1,
                        "measure": 1,
                        "skip": 2,
                        "source": "manual:existing",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    existing_barline_path = existing_dir / "barline_overrides.json"
    existing_barline_path.write_text(
        json.dumps(
            {
                "barline_overrides": [
                    {
                        "page": 1,
                        "op": "remove",
                        "bbox": [10, 20, 30, 40],
                        "source": "manual:existing",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "config": {
                    "inputs": {
                        "measure_overrides": str(existing_measure_path),
                        "barline_overrides": str(existing_barline_path),
                    },
                    "steps": {"mmr_overrides": True},
                    "outputs": {},
                }
            }
        ),
        encoding="utf-8",
    )

    (corrections_dir / "measure_construction_overrides.json").write_text(
        json.dumps(
            {
                "correction_type": "measure_construction",
                "items": [
                    {
                        "op": "force_measure",
                        "page": 2,
                        "system": 1,
                        "interval": 3,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (corrections_dir / "barline_construction_overrides.json").write_text(
        json.dumps(
            {
                "correction_type": "barline_construction",
                "items": [
                    {
                        "op": "add_barline",
                        "page": 2,
                        "bbox": [11, 21, 31, 41],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    handoff_path = review_dir / "manual_correction_input.json"
    handoff = {
        "schema_version": 1,
        "pages": [
            {
                "page_id": "page_001",
                "page_number": 1,
                "source_image": "pages/page_001/source.png",
                "numbering_final": "pages/page_001/numbering_final.json",
                "correction_output": "corrections",
            }
        ],
    }
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

    with patch("src.pipeline.review.apply_corrections.run_pipeline"):
        new_run_dir = apply_corrections_and_rerun(handoff_path, dry_run=True)

    measure_payload = json.loads(
        (corrections_dir / "measure_overrides.json").read_text(encoding="utf-8")
    )
    barline_payload = json.loads(
        (corrections_dir / "barline_overrides.json").read_text(encoding="utf-8")
    )
    rerun_config = json.loads(
        (new_run_dir / "corrected_pipeline_config.json").read_text(encoding="utf-8")
    )

    assert len(measure_payload["measure_overrides"]) == 2
    assert measure_payload["measure_overrides"][0]["source"] == "manual:existing"
    assert measure_payload["measure_overrides"][1]["source"] == "manual:measure_construction"
    assert len(barline_payload["barline_overrides"]) == 2
    assert barline_payload["barline_overrides"][0]["source"] == "manual:existing"
    assert barline_payload["barline_overrides"][1]["source"] == "manual:barline_construction"
    assert rerun_config["inputs"]["measure_overrides"] == str(
        corrections_dir / "measure_overrides.json"
    )
    assert rerun_config["inputs"]["barline_overrides"] == str(
        corrections_dir / "barline_overrides.json"
    )


def test_apply_corrections_carries_forward_same_path_existing_override_inputs(
    tmp_path: Path,
):
    run_dir = tmp_path / "original_run"
    review_dir = run_dir / "review"
    corrections_dir = review_dir / "corrections"
    review_dir.mkdir(parents=True)
    corrections_dir.mkdir()

    measure_override_path = corrections_dir / "measure_overrides.json"
    measure_override_path.write_text(
        json.dumps(
            {
                "measure_overrides": [
                    {
                        "page": 1,
                        "system": 1,
                        "measure": 1,
                        "skip": 2,
                        "source": "manual:existing_same_path",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    barline_override_path = corrections_dir / "barline_overrides.json"
    barline_override_path.write_text(
        json.dumps(
            {
                "barline_overrides": [
                    {
                        "page": 1,
                        "op": "remove",
                        "bbox": [10, 20, 30, 40],
                        "source": "manual:existing_same_path",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "config": {
                    "inputs": {
                        "measure_overrides": str(measure_override_path),
                        "barline_overrides": str(barline_override_path),
                    },
                    "steps": {"mmr_overrides": True},
                    "outputs": {},
                }
            }
        ),
        encoding="utf-8",
    )

    (corrections_dir / "measure_construction_overrides.json").write_text(
        json.dumps(
            {
                "correction_type": "measure_construction",
                "items": [
                    {
                        "op": "force_measure",
                        "page": 2,
                        "system": 1,
                        "interval": 3,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (corrections_dir / "barline_construction_overrides.json").write_text(
        json.dumps(
            {
                "correction_type": "barline_construction",
                "items": [
                    {
                        "op": "add_barline",
                        "page": 2,
                        "bbox": [11, 21, 31, 41],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    handoff_path = review_dir / "manual_correction_input.json"
    handoff = {
        "schema_version": 1,
        "pages": [
            {
                "page_id": "page_001",
                "page_number": 1,
                "source_image": "pages/page_001/source.png",
                "numbering_final": "pages/page_001/numbering_final.json",
                "correction_output": "corrections",
            }
        ],
    }
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

    with patch("src.pipeline.review.apply_corrections.run_pipeline"):
        apply_corrections_and_rerun(handoff_path, overwrite=True, dry_run=True)

    measure_payload = json.loads(measure_override_path.read_text(encoding="utf-8"))
    barline_payload = json.loads(barline_override_path.read_text(encoding="utf-8"))

    assert len(measure_payload["measure_overrides"]) == 2
    assert measure_payload["measure_overrides"][0]["source"] == "manual:existing_same_path"
    assert measure_payload["measure_overrides"][1]["source"] == "manual:measure_construction"
    assert len(barline_payload["barline_overrides"]) == 2
    assert barline_payload["barline_overrides"][0]["source"] == "manual:existing_same_path"
    assert barline_payload["barline_overrides"][1]["source"] == "manual:barline_construction"
