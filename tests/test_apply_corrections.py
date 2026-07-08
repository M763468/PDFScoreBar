import json
import sys
import types
from pathlib import Path

sys.modules.setdefault("fitz", types.SimpleNamespace())

from unittest.mock import patch

import pytest

from src.pipeline.review.apply_corrections import apply_corrections_and_rerun


def _setup_review_package(tmp_path: Path) -> Path:
    run_dir = tmp_path / "original_run"
    review_dir = run_dir / "review"
    corrections_dir = review_dir / "corrections"

    corrections_dir.mkdir(parents=True, exist_ok=True)

    # Write a dummy manifest.json in run_dir
    manifest = {
        "config": {
            "inputs": {"pdf_path": "dummy.pdf"},
            "steps": {"numbering_base": True},
            "outputs": {"review": {"manual_correction_package": True}},
        }
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    # Write staging files in corrections dir
    (corrections_dir / "measure_construction_overrides.json").write_text(
        json.dumps({"schema_version": 1, "correction_type": "measure_construction", "items": []}),
        encoding="utf-8",
    )

    (corrections_dir / "barline_construction_overrides.json").write_text(
        json.dumps({"schema_version": 1, "correction_type": "barline_construction", "items": []}),
        encoding="utf-8",
    )

    # Write handoff file
    handoff_path = review_dir / "manual_correction_input.json"
    handoff = {
        "schema_version": 1,
        "pages": [
            {
                "page_id": "page_001",
                "page_number": 1,
                "source_image": "pages/page_001/source.png",
                "numbering_final": "pages/page_001/numbering_final.json",
                "correction_outputs": {
                    "mmr_measure_span": "corrections/mmr_measure_spans.json",
                    "measure_construction": "corrections/measure_construction_overrides.json",
                    "barline_construction": "corrections/barline_construction_overrides.json",
                },
            }
        ],
    }
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

    return handoff_path


@patch("src.pipeline.review.apply_corrections.run_pipeline")
def test_apply_corrections_and_rerun(mock_run_pipeline, tmp_path):
    handoff_path = _setup_review_package(tmp_path)

    new_run_dir = apply_corrections_and_rerun(
        handoff_path=handoff_path, run_id="corrected_run_123", dry_run=False
    )

    # Verify canonical files were generated
    review_dir = handoff_path.parent
    corrections_dir = review_dir / "corrections"
    assert (corrections_dir / "measure_overrides.json").exists()
    assert (corrections_dir / "barline_overrides.json").exists()

    # Verify new run dir and config
    assert new_run_dir.name == "corrected_run_123"
    assert new_run_dir.parent == tmp_path  # Default output root is package_root.parent.parent

    config_path = new_run_dir / "corrected_pipeline_config.json"
    assert config_path.exists()

    rerun_config = json.loads(config_path.read_text(encoding="utf-8"))
    assert rerun_config["inputs"]["measure_overrides"] == str(
        corrections_dir / "measure_overrides.json"
    )
    assert rerun_config["inputs"]["barline_overrides"] == str(
        corrections_dir / "barline_overrides.json"
    )

    assert rerun_config["steps"]["apply_measure_overrides"] is True
    assert rerun_config["steps"]["apply_barline_overrides"] is True
    assert rerun_config["outputs"]["review"]["manual_correction_package"] is False

    # Verify summary
    summary_path = new_run_dir / "review" / "correction_summary.json"
    assert summary_path.exists()

    # Verify run_pipeline was called
    mock_run_pipeline.assert_called_once_with(
        config_path=config_path, run_id="corrected_run_123", output_root=tmp_path, dry_run=False
    )


@patch("src.pipeline.review.apply_corrections.run_pipeline")
def test_apply_corrections_dry_run(mock_run_pipeline, tmp_path):
    handoff_path = _setup_review_package(tmp_path)

    new_run_dir = apply_corrections_and_rerun(
        handoff_path=handoff_path, run_id="corrected_run_dry", dry_run=True
    )

    config_path = new_run_dir / "corrected_pipeline_config.json"
    assert config_path.exists()
    mock_run_pipeline.assert_not_called()


def test_external_review_root_resolves_source_manifest(tmp_path):
    original_run = tmp_path / "runs" / "original_run"
    original_run.mkdir(parents=True)
    manifest = {"config": {"inputs": {}, "steps": {}, "outputs": {}}}
    (original_run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    public_review = tmp_path / "public_review"
    public_review.mkdir(parents=True)
    handoff_path = public_review / "manual_correction_input.json"
    handoff = {
        "schema_version": 1,
        "source_artifact_root": str(original_run),
        "source_manifest": "manifest.json",
        "pages": [
            {
                "page_id": "p1",
                "page_number": 1,
                "source_image": "a",
                "numbering_final": "b",
                "correction_output": "corrections",
            }
        ],
    }
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

    with patch("src.pipeline.review.apply_corrections.run_pipeline"):
        new_run_dir = apply_corrections_and_rerun(handoff_path, dry_run=True)
        # Verify it resolved manifest correctly from original_run
        config_path = new_run_dir / "corrected_pipeline_config.json"
        assert config_path.exists()


def test_custom_correction_outputs(tmp_path):
    run_dir = tmp_path / "original_run"
    review_dir = run_dir / "review"
    review_dir.mkdir(parents=True)

    (run_dir / "manifest.json").write_text(json.dumps({"config": {}}), encoding="utf-8")

    custom_dir = review_dir / "custom"
    custom_dir.mkdir()

    (custom_dir / "mmr.json").write_text(
        json.dumps(
            {
                "correction_type": "mmr_measure_span",
                "items": [
                    {
                        "op": "set_measure_span",
                        "page": 1,
                        "system": 1,
                        "measure": 1,
                        "measure_span": 2,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    (custom_dir / "measure.json").write_text(
        json.dumps(
            {
                "correction_type": "measure_construction",
                "items": [{"op": "force_measure", "page": 1, "system": 1, "interval": 2}],
            }
        ),
        encoding="utf-8",
    )

    (custom_dir / "barline.json").write_text(
        json.dumps(
            {
                "correction_type": "barline_construction",
                "items": [{"op": "add_barline", "page": 1, "bbox": [1, 2, 3, 4]}],
            }
        ),
        encoding="utf-8",
    )

    handoff_path = review_dir / "manual_correction_input.json"
    handoff = {
        "schema_version": 1,
        "pages": [
            {
                "page_id": "p1",
                "page_number": 1,
                "source_image": "a",
                "numbering_final": "b",
                "correction_outputs": {
                    "mmr_measure_span": "custom/mmr.json",
                    "measure_construction": "custom/measure.json",
                    "barline_construction": "custom/barline.json",
                },
            }
        ],
    }
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

    with patch("src.pipeline.review.apply_corrections.run_pipeline"):
        apply_corrections_and_rerun(handoff_path, dry_run=True)

    corrections_dir = review_dir / "corrections"
    measure_payload = json.loads(
        (corrections_dir / "measure_overrides.json").read_text(encoding="utf-8")
    )
    barline_payload = json.loads(
        (corrections_dir / "barline_overrides.json").read_text(encoding="utf-8")
    )

    assert len(measure_payload["measure_overrides"]) == 2
    assert len(barline_payload["barline_overrides"]) == 1


def test_malformed_manifest_and_config(tmp_path):
    run_dir = tmp_path / "original_run"
    review_dir = run_dir / "review"
    review_dir.mkdir(parents=True)

    handoff_path = review_dir / "manual_correction_input.json"
    handoff = {
        "schema_version": 1,
        "pages": [
            {
                "page_id": "p1",
                "page_number": 1,
                "source_image": "a",
                "numbering_final": "b",
                "correction_output": "corrections",
            }
        ],
    }
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

    # 1. Manifest is a list
    (run_dir / "manifest.json").write_text(json.dumps([]), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest.json must be a JSON object"):
        apply_corrections_and_rerun(handoff_path, overwrite=True)

    # 2. Config is not dict
    (run_dir / "manifest.json").write_text(json.dumps({"config": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="Source configuration must be a dictionary"):
        apply_corrections_and_rerun(handoff_path, overwrite=True)

    # 3. Explicit config is not dict
    config_path = run_dir / "config.json"
    config_path.write_text(json.dumps([]), encoding="utf-8")
    with pytest.raises(ValueError, match="Source configuration must be a dictionary"):
        apply_corrections_and_rerun(handoff_path, config_path=config_path, overwrite=True)


def test_rerun_config_sections_null(tmp_path):
    run_dir = tmp_path / "original_run"
    review_dir = run_dir / "review"
    review_dir.mkdir(parents=True)

    (run_dir / "manifest.json").write_text(
        json.dumps({"config": {"inputs": None, "steps": None, "outputs": None}}),
        encoding="utf-8",
    )

    handoff_path = review_dir / "manual_correction_input.json"
    handoff = {
        "schema_version": 1,
        "pages": [
            {
                "page_id": "p1",
                "page_number": 1,
                "source_image": "a",
                "numbering_final": "b",
                "correction_output": "corrections",
            }
        ],
    }
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

    with patch("src.pipeline.review.apply_corrections.run_pipeline"):
        new_run_dir = apply_corrections_and_rerun(handoff_path, dry_run=True)

    config_path = new_run_dir / "corrected_pipeline_config.json"
    rerun_config = json.loads(config_path.read_text(encoding="utf-8"))

    assert "measure_overrides" in rerun_config["inputs"]
    assert "barline_overrides" in rerun_config["inputs"]
    assert rerun_config["steps"]["apply_measure_overrides"] is True
    assert rerun_config["steps"]["apply_barline_overrides"] is True
    assert rerun_config["outputs"]["review"]["manual_correction_package"] is False
