import json
from pathlib import Path

from src.pipeline.output_profiles import (
    effective_output_profile,
    materialize_output_profile,
    normalize_output_profile,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def _make_internal_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "internal_run"
    image_path = run_dir / "inputs" / "images" / "page_001.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"not-a-real-png")

    _write_json(
        run_dir / "manifest.json",
        {
            "run_id": "run-a",
            "config": {"inputs": {"pdf_path": "score.pdf"}},
            "pages": [
                {
                    "page_id": "page_001",
                    "image_path": str(image_path),
                    "page_run": "page_001",
                    "barlines_json": "barlines.json",
                    "staff_mask": "staff.png",
                    "status": {"status": "included"},
                }
            ],
        },
    )
    _write_json(
        run_dir / "filters.json",
        {"pages": [{"page_id": "page_001", "status": "ok"}]},
    )
    _write_json(
        run_dir / "outputs" / "numbering_final.json",
        {"pages": [{"page_number": 1}]},
    )
    _write_json(
        run_dir / "outputs" / "page_001" / "numbering_final.json",
        {"pages": [{"page_number": 1, "systems": []}]},
    )
    (run_dir / "outputs" / "page_001" / "numbering_overlay.png").write_bytes(b"overlay")
    _write_json(
        run_dir / "intermediate" / "page_001" / "overrides_mmr.json",
        {"measure_overrides": [{"page": 0, "system": 0, "measure": 0, "skip": 1}]},
    )
    _write_json(
        run_dir / "intermediate" / "page_001" / "barlines_corrected.json",
        [{"bbox": [1, 2, 3, 4]}],
    )
    (run_dir / "pipeline.log").write_text("pipeline log\n")
    return run_dir


def test_profile_normalization_and_debug_flag():
    assert normalize_output_profile(" Review ") == "review"
    assert effective_output_profile("final", debug=True) == "debug"
    assert effective_output_profile("debug", debug=False) == "debug"


def test_final_profile_materializes_clean_final_directory(tmp_path: Path):
    run_dir = _make_internal_run(tmp_path)
    out_dir = tmp_path / "public"

    result = materialize_output_profile(run_dir, out_dir, profile="final")

    assert result == out_dir
    assert (out_dir / "run_summary.json").exists()
    assert (out_dir / "resolved_config.yaml").exists()
    assert json.loads((out_dir / "final" / "score_numbering.json").read_text()) == {
        "pages": [{"page_number": 1}]
    }
    assert not (out_dir / "review").exists()
    assert not (out_dir / "debug").exists()

    summary = json.loads((out_dir / "run_summary.json").read_text())
    assert summary["profile"] == {
        "selected": "final",
        "effective": "final",
        "debug_requested": False,
    }
    assert summary["final_overlay"]["status"] == "not_implemented_in_issue227"


def test_review_profile_creates_correction_handoff_and_preserves_user_corrections(
    tmp_path: Path,
):
    run_dir = _make_internal_run(tmp_path)
    out_dir = tmp_path / "public"
    corrections = out_dir / "review" / "corrections" / "measure_overrides.json"
    corrections.parent.mkdir(parents=True, exist_ok=True)
    corrections.write_text('{"measure_overrides": [{"user": true}]}')

    materialize_output_profile(run_dir, out_dir, profile="review")

    assert (out_dir / "final" / "score_numbering.json").exists()
    assert (out_dir / "review" / "manual_correction_input.json").exists()
    assert (out_dir / "review" / "pages" / "page_001" / "source.png").exists()
    assert (out_dir / "review" / "pages" / "page_001" / "review_overlay.png").exists()
    assert (out_dir / "review" / "pages" / "page_001" / "numbering_final.json").exists()
    assert (out_dir / "review" / "pages" / "page_001" / "barlines_review.json").exists()
    assert (out_dir / "review" / "pages" / "page_001" / "mmr_overrides.json").exists()
    assert json.loads(corrections.read_text()) == {"measure_overrides": [{"user": True}]}

    manual_input = json.loads((out_dir / "review" / "manual_correction_input.json").read_text())
    assert manual_input["schema"] == "pdfscorebar.manual_correction_input.v1"
    assert manual_input["correction_output"] == "review/corrections/measure_overrides.json"
    assert manual_input["pages"][0]["page_id"] == "page_001"


def test_debug_profile_materializes_debug_artifacts(tmp_path: Path):
    run_dir = _make_internal_run(tmp_path)
    out_dir = tmp_path / "public"

    materialize_output_profile(run_dir, out_dir, profile="debug")

    assert (out_dir / "final" / "score_numbering.json").exists()
    assert (out_dir / "review" / "manual_correction_input.json").exists()
    assert (out_dir / "debug" / "pipeline.log").read_text() == "pipeline log\n"
    assert (out_dir / "debug" / "manifest.json").exists()
    assert (out_dir / "debug" / "filters.json").exists()
    assert (out_dir / "debug" / "inputs" / "images" / "page_001.png").exists()
    assert (out_dir / "debug" / "intermediate" / "page_001" / "overrides_mmr.json").exists()
    assert (
        out_dir / "debug" / "legacy_current_layout" / "outputs" / "numbering_final.json"
    ).exists()
    assert (out_dir / "debug" / "artifact_index.json").exists()


def test_debug_flag_promotes_effective_profile(tmp_path: Path):
    run_dir = _make_internal_run(tmp_path)
    out_dir = tmp_path / "public"

    materialize_output_profile(run_dir, out_dir, profile="final", debug=True)

    summary = json.loads((out_dir / "run_summary.json").read_text())
    assert summary["profile"] == {
        "selected": "final",
        "effective": "debug",
        "debug_requested": True,
    }
    assert (out_dir / "debug" / "pipeline.log").exists()
