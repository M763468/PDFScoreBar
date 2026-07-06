import json
from pathlib import Path

import pytest

from src.pipeline.review.manual_correction_handoff import (
    build_manual_gui_config,
    validate_manual_correction_handoff,
)
from src.pipeline.review.manual_correction_materializer import (
    ManualCorrectionMaterializerError,
    materialize_manual_correction_review_package,
)


def _write_json(path: Path, payload: object | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload or {}, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str = "placeholder") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fake_run_root(
    tmp_path: Path,
    *,
    barlines_outside: Path | None = None,
    barlines_payload: object | None = None,
    page_id: str = "page_001",
) -> Path:
    run_root = tmp_path / "source_run"
    _write_text(run_root / "inputs" / "images" / f"{page_id}.png")
    _write_json(run_root / "outputs" / page_id / "numbering_final.json")
    _write_text(run_root / "outputs" / page_id / "numbering_overlay.png")
    _write_json(run_root / "intermediate" / page_id / "overrides_mmr.json")
    detector_output = run_root / "intermediate" / "probe_scan" / page_id / "filtered.json"
    _write_json(detector_output, barlines_payload or {"boxes": [{"bbox": [1, 2, 3, 4]}]})

    barlines_json = barlines_outside if barlines_outside is not None else detector_output
    _write_json(
        run_root / "manifest.json",
        {
            "run_id": "source_run",
            "pages": [
                {
                    "page_id": page_id,
                    "image_path": str(run_root / "inputs" / "images" / f"{page_id}.png"),
                    "barlines_json": str(barlines_json),
                    "status": {"page_index": 1},
                }
            ],
        },
    )
    return run_root


def test_materializes_review_package_from_manifest_resolved_barlines(tmp_path):
    run_root = _fake_run_root(tmp_path)
    review_root = tmp_path / "review"

    handoff = materialize_manual_correction_review_package(
        run_root=run_root,
        review_root=review_root,
        pages=["page_001"],
        source_pipeline_command="make run-pipeline CONFIG=smoke.yaml",
    )

    page = handoff["pages"][0]
    assert page["barlines_review"] == "pages/page_001/barlines_review.json"
    assert page["barlines_review_source"] == "intermediate/probe_scan/page_001/filtered.json"
    assert page["barlines_review_source_kind"] == "manifest_resolved_detector_output"
    assert page["barlines_review_source_manifest_field"] == "barlines_json"

    copied_barlines = json.loads(
        (review_root / "pages" / "page_001" / "barlines_review.json").read_text()
    )
    assert copied_barlines == [{"bbox": [1, 2, 3, 4]}]
    assert (review_root / "corrections").is_dir()

    handoff_on_disk = json.loads((review_root / "manual_correction_input.json").read_text())
    assert handoff_on_disk["source_pipeline_command"] == "make run-pipeline CONFIG=smoke.yaml"
    assert handoff_on_disk["pages"][0]["barlines_review_source"] == page["barlines_review_source"]


def test_materialized_handoff_validates_and_builds_page_local_gui_config(tmp_path):
    run_root = _fake_run_root(tmp_path)
    review_root = tmp_path / "review"

    materialize_manual_correction_review_package(run_root=run_root, review_root=review_root)
    handoff_path = review_root / "manual_correction_input.json"
    payload = json.loads(handoff_path.read_text())

    validated = validate_manual_correction_handoff(
        payload,
        handoff_path=handoff_path,
        mode="issue229_smoke_strict",
        require_existing_artifacts=True,
    )
    config = build_manual_gui_config(
        validated,
        handoff_path=handoff_path,
        mode="issue229_smoke_strict",
        require_existing_artifacts=True,
    )

    assert config["pages"][0]["page"] == 0
    assert config["pages"][0]["manual_outputs"] == {
        "mmr_measure_span": "corrections/mmr_measure_spans.json",
        "measure_construction": "corrections/measure_construction_overrides.json",
        "barline_construction": "corrections/barline_construction_overrides.json",
    }


def test_materializer_errors_when_manifest_has_no_barlines_source(tmp_path):
    run_root = _fake_run_root(tmp_path)
    manifest_path = run_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["pages"][0].pop("barlines_json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ManualCorrectionMaterializerError) as exc_info:
        materialize_manual_correction_review_package(
            run_root=run_root,
            review_root=tmp_path / "review",
        )

    message = str(exc_info.value)
    assert "page_001" in message
    assert str(run_root.resolve()) in message
    assert str((run_root / "manifest.json").resolve()) in message
    assert "barlines_json" in message
    assert "barlines_review.json" in message


def test_materializer_normalizes_predictions_barlines_source(tmp_path):
    run_root = _fake_run_root(
        tmp_path,
        barlines_payload={"predictions": [{"bbox": [1, 2, 3, 4]}]},
    )
    review_root = tmp_path / "review"

    materialize_manual_correction_review_package(run_root=run_root, review_root=review_root)

    copied_barlines = json.loads(
        (review_root / "pages" / "page_001" / "barlines_review.json").read_text()
    )
    assert copied_barlines == [{"bbox": [1, 2, 3, 4]}]


def test_materializer_preserves_top_level_list_barlines_source(tmp_path):
    run_root = _fake_run_root(tmp_path, barlines_payload=[{"bbox": [1, 2, 3, 4]}])
    review_root = tmp_path / "review"

    materialize_manual_correction_review_package(run_root=run_root, review_root=review_root)

    copied_barlines = json.loads(
        (review_root / "pages" / "page_001" / "barlines_review.json").read_text()
    )
    assert copied_barlines == [{"bbox": [1, 2, 3, 4]}]


def test_materializer_errors_when_barlines_source_has_no_records(tmp_path):
    run_root = _fake_run_root(tmp_path, barlines_payload={"metadata": {}})

    with pytest.raises(ManualCorrectionMaterializerError, match="no predictions or boxes list"):
        materialize_manual_correction_review_package(
            run_root=run_root,
            review_root=tmp_path / "review",
        )


def test_materializer_rejects_invalid_page_id(tmp_path):
    run_root = _fake_run_root(tmp_path)
    manifest_path = run_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["pages"][0]["page_id"] = "../page_001"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ManualCorrectionMaterializerError) as exc_info:
        materialize_manual_correction_review_package(
            run_root=run_root,
            review_root=tmp_path / "review",
        )

    message = str(exc_info.value)
    assert "page_id" in message
    assert "invalid characters" in message


def test_materializer_rejects_run_root_external_barlines_artifact(tmp_path):
    outside = tmp_path / "old_run" / "filtered.json"
    _write_json(outside, {"boxes": []})
    run_root = _fake_run_root(tmp_path, barlines_outside=outside)

    with pytest.raises(ManualCorrectionMaterializerError, match="outside the current pipeline run"):
        materialize_manual_correction_review_package(
            run_root=run_root,
            review_root=tmp_path / "review",
        )
