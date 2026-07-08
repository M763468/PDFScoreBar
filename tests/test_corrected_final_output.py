import json
from pathlib import Path

import pytest
from PIL import Image

from src.pipeline.review.final_output import (
    CorrectedFinalOutputError,
    materialize_corrected_final_outputs,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _setup_final_output_fixture(tmp_path: Path, *, output_name: str = "Corrected Score"):
    original_run = tmp_path / "original_run"
    review_dir = original_run / "review"
    page_dir = review_dir / "pages" / "page_001"
    page_dir.mkdir(parents=True)

    Image.new("RGB", (300, 200), "white").save(page_dir / "source.png")

    # Original review-package numbering intentionally starts at 1. The final
    # materializer must use the corrected rerun output below, not this file.
    _write_json(
        page_dir / "numbering_final.json",
        {
            "pages": [
                {
                    "page_number": 1,
                    "width": 300,
                    "height": 200,
                    "systems": [
                        {
                            "staves": [{"bbox": [80, 60, 260, 100]}],
                            "measures": [{"number": 1, "bbox": [90, 60, 160, 100]}],
                        }
                    ],
                    "empty_systems": [],
                }
            ]
        },
    )

    handoff_path = review_dir / "manual_correction_input.json"
    _write_json(
        handoff_path,
        {
            "schema_version": 1,
            "kind": "manual_correction_input",
            "output_name": output_name,
            "pages": [
                {
                    "page_id": "page_001",
                    "page_number": 1,
                    "source_image": "pages/page_001/source.png",
                    "numbering_final": "pages/page_001/numbering_final.json",
                    "correction_output": "corrections",
                }
            ],
        },
    )

    corrected_run = tmp_path / "corrected_run"
    _write_json(
        corrected_run / "outputs" / "page_001" / "numbering_final.json",
        {
            "pages": [
                {
                    "page_number": 1,
                    "width": 300,
                    "height": 200,
                    "systems": [
                        {
                            "staves": [{"bbox": [80, 60, 260, 100]}],
                            "measures": [
                                {"number": 42, "bbox": [90, 60, 160, 100]},
                                {"number": 43, "bbox": [160, 60, 240, 100]},
                            ],
                        }
                    ],
                    "empty_systems": [],
                }
            ]
        },
    )
    return handoff_path, corrected_run


def test_materialize_corrected_final_outputs_creates_clean_pdf_and_review_summary(tmp_path):
    handoff_path, corrected_run = _setup_final_output_fixture(tmp_path)

    summary = materialize_corrected_final_outputs(
        handoff_path=handoff_path,
        corrected_run_dir=corrected_run,
    )

    final_pdf = corrected_run / "final" / "Corrected_Score_score_numbered.pdf"
    assert final_pdf.exists()
    assert [path.name for path in (corrected_run / "final").iterdir()] == [final_pdf.name]
    assert summary["final_pdf"] == str(final_pdf)

    review_summary_path = corrected_run / "review" / "corrected_final_summary.json"
    assert review_summary_path.exists()
    review_summary = json.loads(review_summary_path.read_text(encoding="utf-8"))
    assert review_summary["summary_path"] == str(review_summary_path)
    assert review_summary["page_count"] == 1
    assert review_summary["pages"][0]["rendered_row_labels"] == 1
    assert review_summary["pages"][0]["row_labels"][0]["row_start_measure_number"] == 42
    assert review_summary["warnings"] == []


def test_materialize_corrected_final_outputs_uses_explicit_output_name(tmp_path):
    handoff_path, corrected_run = _setup_final_output_fixture(tmp_path, output_name="ignored")

    materialize_corrected_final_outputs(
        handoff_path=handoff_path,
        corrected_run_dir=corrected_run,
        output_name="custom score name",
    )

    assert (corrected_run / "final" / "custom_score_name_score_numbered.pdf").exists()


def test_materialize_corrected_final_outputs_rejects_absolute_package_paths(tmp_path):
    handoff_path, corrected_run = _setup_final_output_fixture(tmp_path)
    payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    payload["pages"][0]["source_image"] = str(tmp_path / "outside.png")
    handoff_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CorrectedFinalOutputError, match="package-relative"):
        materialize_corrected_final_outputs(
            handoff_path=handoff_path,
            corrected_run_dir=corrected_run,
        )


def test_materialize_corrected_final_outputs_requires_corrected_numbering(tmp_path):
    handoff_path, corrected_run = _setup_final_output_fixture(tmp_path)
    (corrected_run / "outputs" / "page_001" / "numbering_final.json").unlink()

    with pytest.raises(CorrectedFinalOutputError, match="corrected numbering_final"):
        materialize_corrected_final_outputs(
            handoff_path=handoff_path,
            corrected_run_dir=corrected_run,
        )
