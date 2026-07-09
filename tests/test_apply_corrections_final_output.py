import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

sys.modules.setdefault("fitz", types.SimpleNamespace())

from src.pipeline.review.apply_corrections import apply_corrections_and_rerun


def _setup_review_package(tmp_path: Path) -> Path:
    run_dir = tmp_path / "original_run"
    review_dir = run_dir / "review"
    corrections_dir = review_dir / "corrections"
    corrections_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "config": {
                    "inputs": {"pdf_path": "dummy.pdf"},
                    "steps": {"numbering_base": True},
                    "outputs": {"review": {"manual_correction_package": True}},
                }
            }
        ),
        encoding="utf-8",
    )

    (corrections_dir / "measure_construction_overrides.json").write_text(
        json.dumps({"schema_version": 1, "correction_type": "measure_construction", "items": []}),
        encoding="utf-8",
    )
    (corrections_dir / "barline_construction_overrides.json").write_text(
        json.dumps({"schema_version": 1, "correction_type": "barline_construction", "items": []}),
        encoding="utf-8",
    )

    handoff_path = review_dir / "manual_correction_input.json"
    handoff_path.write_text(
        json.dumps(
            {
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
        ),
        encoding="utf-8",
    )
    return handoff_path


@patch("src.pipeline.review.apply_corrections.materialize_corrected_final_outputs")
@patch("src.pipeline.review.apply_corrections.run_pipeline")
def test_apply_corrections_can_generate_corrected_final_pdf(
    mock_run_pipeline,
    mock_materialize_final,
    tmp_path,
):
    handoff_path = _setup_review_package(tmp_path)
    mock_materialize_final.return_value = {
        "final_pdf": str(tmp_path / "corrected_run_123" / "final" / "custom_score_numbered.pdf"),
        "summary_path": str(
            tmp_path / "corrected_run_123" / "review" / "corrected_final_summary.json"
        ),
    }

    new_run_dir = apply_corrections_and_rerun(
        handoff_path=handoff_path,
        run_id="corrected_run_123",
        dry_run=False,
        generate_final_pdf=True,
        output_name="custom",
    )

    mock_run_pipeline.assert_called_once()
    mock_materialize_final.assert_called_once_with(
        handoff_path=handoff_path.resolve(),
        corrected_run_dir=new_run_dir,
        final_root=new_run_dir / "final",
        review_root=new_run_dir / "review",
        output_name="custom",
    )

    summary = json.loads(
        (new_run_dir / "review" / "correction_summary.json").read_text(encoding="utf-8")
    )
    assert summary["generate_final_pdf"] is True
    assert summary["final_pdf"].endswith("custom_score_numbered.pdf")
    assert summary["corrected_final_summary"].endswith("corrected_final_summary.json")

    back_summary = json.loads(
        (handoff_path.parent / "corrections" / "apply_summary.json").read_text(encoding="utf-8")
    )
    assert back_summary["final_pdf"] == summary["final_pdf"]


@patch("src.pipeline.review.apply_corrections.materialize_corrected_final_outputs")
@patch("src.pipeline.review.apply_corrections.run_pipeline")
def test_apply_corrections_dry_run_does_not_generate_final_pdf(
    mock_run_pipeline,
    mock_materialize_final,
    tmp_path,
):
    handoff_path = _setup_review_package(tmp_path)

    apply_corrections_and_rerun(
        handoff_path=handoff_path,
        run_id="corrected_run_dry",
        dry_run=True,
        generate_final_pdf=True,
        output_name="custom",
    )

    mock_run_pipeline.assert_not_called()
    mock_materialize_final.assert_not_called()
