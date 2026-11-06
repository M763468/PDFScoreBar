import json
from pathlib import Path

import fitz
import numpy as np
import pytest
from PIL import Image

from src.pipeline.review.final_output import (
    CorrectedFinalOutputError,
    _draw_row_start_labels,
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
                    "page_size_points": [72, 48],
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


def test_final_pdf_summary_uses_physical_page_without_changing_correction_numbering(tmp_path):
    handoff, corrected_run = _setup_final_output_fixture(tmp_path)
    payload = json.loads(handoff.read_text())
    payload["pages"][0]["source_page_number"] = 3
    _write_json(handoff, payload)
    summary = materialize_corrected_final_outputs(
        handoff_path=handoff, corrected_run_dir=corrected_run
    )
    assert summary["pages"][0]["page_number"] == 3
    assert summary["pages"][0]["row_labels"][0]["page_number"] == 3
    assert summary["pages"][0]["row_labels"][0]["row_start_measure_number"] == 42
    assert json.loads(handoff.read_text())["pages"][0]["page_number"] == 1


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
    with fitz.open(final_pdf) as document:
        assert document.page_count == 1
        assert document[0].rect.width == pytest.approx(72)
        assert document[0].rect.height == pytest.approx(48)


def test_materialize_corrected_final_outputs_uses_cross_page_final_numbers_for_row_labels(
    tmp_path,
):
    handoff_path, corrected_run = _setup_final_output_fixture(tmp_path)
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))

    for page_number, first_measure_number in ((2, 44), (3, 1)):
        page_id = f"page_{page_number:03d}"
        source_path = handoff_path.parent / "pages" / page_id / "source.png"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (300, 200), "white").save(source_path)
        _write_json(
            corrected_run / "outputs" / page_id / "numbering_final.json",
            {
                "pages": [
                    {
                        "page_number": page_number,
                        "width": 300,
                        "height": 200,
                        "systems": [
                            {
                                "staves": [{"bbox": [80, 60, 260, 100]}],
                                "measures": [
                                    {
                                        "number": first_measure_number,
                                        "bbox": [90, 60, 160, 100],
                                    }
                                ],
                            }
                        ],
                        "empty_systems": [],
                    }
                ]
            },
        )
        handoff["pages"].append(
            {
                "page_id": page_id,
                "page_number": page_number,
                "source_image": f"pages/{page_id}/source.png",
                "numbering_final": f"pages/{page_id}/numbering_final.json",
                "correction_output": "corrections",
            }
        )
    handoff_path.write_text(json.dumps(handoff, indent=2), encoding="utf-8")

    materialize_corrected_final_outputs(
        handoff_path=handoff_path,
        corrected_run_dir=corrected_run,
    )

    summary = json.loads(
        (corrected_run / "review" / "corrected_final_summary.json").read_text(encoding="utf-8")
    )
    assert [page["row_labels"][0]["row_start_measure_number"] for page in summary["pages"]] == [
        42,
        44,
        1,
    ]


def test_materialize_corrected_final_outputs_uses_explicit_output_name(tmp_path):
    handoff_path, corrected_run = _setup_final_output_fixture(tmp_path, output_name="ignored")

    materialize_corrected_final_outputs(
        handoff_path=handoff_path,
        corrected_run_dir=corrected_run,
        output_name="custom score name",
    )

    assert (corrected_run / "final" / "custom_score_name_score_numbered.pdf").exists()


@pytest.mark.parametrize(
    ("handoff_fields", "explicit_name", "expected_name"),
    [
        ({"source_pdf": "/input/My Orchestra Score.pdf"}, None, "My_Orchestra_Score"),
        ({"source_pdf": "/input/楽章協会 第九.pdf"}, None, "楽章協会_第九"),
        ({"input_pdf": r"C:\\scores\\piece_score_numbered.pdf"}, None, "piece"),
        ({}, "../outside/score", "corrected"),
        ({}, None, "corrected"),
    ],
)
def test_materialize_corrected_final_outputs_uses_safe_source_name_or_fallback(
    tmp_path, handoff_fields, explicit_name, expected_name
):
    handoff_path, corrected_run = _setup_final_output_fixture(tmp_path)
    payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    payload.pop("output_name", None)
    payload.update(handoff_fields)
    handoff_path.write_text(json.dumps(payload), encoding="utf-8")

    summary = materialize_corrected_final_outputs(
        handoff_path=handoff_path,
        corrected_run_dir=corrected_run,
        output_name=explicit_name,
    )

    assert Path(summary["final_pdf"]).name == f"{expected_name}_score_numbered.pdf"
    assert Path(summary["final_pdf"]).resolve().is_relative_to((corrected_run / "final").resolve())


def test_materialize_corrected_final_outputs_bounds_long_multibyte_source_name(tmp_path):
    long_cjk_stem = "楽" * 79  # 237 UTF-8 bytes; + ".pdf" is 241 bytes (valid on 255-byte fs)
    handoff_path, corrected_run = _setup_final_output_fixture(
        tmp_path,
        output_name=f"{long_cjk_stem}.pdf",
    )

    summary = materialize_corrected_final_outputs(
        handoff_path=handoff_path,
        corrected_run_dir=corrected_run,
    )

    final_pdf = Path(summary["final_pdf"])
    assert final_pdf.is_file()
    assert final_pdf.name.endswith("_score_numbered.pdf")
    assert len(final_pdf.name.encode("utf-8")) <= 255
    assert len(summary["output_name"].encode("utf-8")) <= 200


def test_materialize_corrected_final_outputs_uses_page_uniform_label_size(tmp_path):
    handoff_path, corrected_run = _setup_final_output_fixture(tmp_path)
    _write_json(
        corrected_run / "outputs" / "page_001" / "numbering_final.json",
        {
            "pages": [
                {
                    "page_number": 1,
                    "width": 300,
                    "height": 260,
                    "systems": [
                        {
                            "staves": [{"bbox": [80, 60, 260, 100]}],
                            "measures": [{"number": 42, "bbox": [90, 60, 160, 100]}],
                        },
                        {
                            "staves": [{"bbox": [80, 140, 260, 230]}],
                            "measures": [{"number": 47, "bbox": [90, 140, 160, 230]}],
                        },
                    ],
                    "empty_systems": [],
                }
            ]
        },
    )

    materialize_corrected_final_outputs(
        handoff_path=handoff_path,
        corrected_run_dir=corrected_run,
    )

    review_summary_path = corrected_run / "review" / "corrected_final_summary.json"
    review_summary = json.loads(review_summary_path.read_text(encoding="utf-8"))
    row_labels = review_summary["pages"][0]["row_labels"]
    assert [label["row_start_measure_number"] for label in row_labels] == [42, 47]
    assert len({label["label_font_size"] for label in row_labels}) == 1


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


def test_row_labels_use_one_physical_size_and_stay_near_printed_staff_line():
    image = Image.new("RGB", (1000, 1000), "white")
    pixels = np.asarray(image).copy()
    for top in (200, 600):
        for line in range(5):
            y = top + line * 12
            pixels[y : y + 2, 200:950] = 0
    # A note above the first staff inflates its detected bbox; the second is tight.
    pixels[120:130, 400:420] = 0
    records = [
        {
            "row_start_measure_number": 1,
            "row_bbox": [200, 120, 950, 400],
            "top_staff_bbox": [200, 120, 950, 250],
        },
        {
            "row_start_measure_number": 123,
            "row_bbox": [200, 600, 950, 800],
            "top_staff_bbox": [200, 598, 950, 650],
        },
    ]
    source = Image.fromarray(pixels)

    output = _draw_row_start_labels(source, records, pixels_per_point=2.0)

    assert {record["label_font_size"] for record in records} == {18}
    assert {record["label_anchor"] for record in records} == {"staff_lines"}
    assert {record["placement"] for record in records} == {"primary_left_gutter"}
    gaps = [top - record["label_bbox"][3] for record, top in zip(records, (200, 600), strict=True)]
    assert max(gaps) - min(gaps) <= 1
    assert all(0 < gap <= 8 for gap in gaps)
    assert all(record["label_bbox"][2] < 200 for record in records)
    # Clear-space placement must not paint over printed score ink.
    assert (np.asarray(output)[pixels.min(axis=2) == 0] == 0).all()


def test_row_label_moves_to_clear_space_without_erasing_score_ink():
    pixels = np.full((600, 600, 3), 255, dtype=np.uint8)
    for line in range(5):
        y = 300 + line * 12
        pixels[y : y + 2, 200:580] = 0
    pixels[270:298, 165:198] = 0  # Printed ink occupies the preferred slot.
    records = [
        {
            "row_start_measure_number": 7,
            "row_bbox": [200, 300, 580, 350],
            "top_staff_bbox": [200, 300, 580, 350],
        }
    ]

    output = _draw_row_start_labels(Image.fromarray(pixels), records, pixels_per_point=2.0)

    assert records[0]["placement"] == "nearby_clear_space"
    assert (np.asarray(output)[pixels.min(axis=2) == 0] == 0).all()


def test_row_label_without_clear_space_fails_instead_of_erasing_score_ink():
    # Ink covers the whole search area around the slot, but the rest of the page is blank.
    pixels = np.full((600, 600, 3), 255, dtype=np.uint8)
    pixels[200:350, 100:300] = 0
    source = Image.fromarray(pixels)
    records = [
        {
            "page_id": "page_001",
            "row_id": "row_001",
            "row_start_measure_number": 7,
            "row_bbox": [200, 300, 580, 350],
            "top_staff_bbox": [200, 300, 580, 350],
        }
    ]

    with pytest.raises(CorrectedFinalOutputError, match=r"page_001: no safe 9pt .* label 7"):
        _draw_row_start_labels(source, records, pixels_per_point=2.0)

    assert np.array_equal(np.asarray(source), pixels)


def test_materialize_corrected_final_outputs_writes_no_pdf_without_safe_label_placement(tmp_path):
    handoff_path, corrected_run = _setup_final_output_fixture(tmp_path)
    source_image = tmp_path / "original_run" / "review" / "pages" / "page_001" / "source.png"
    Image.new("RGB", (300, 200), "black").save(source_image)
    final_root = tmp_path / "final"

    with pytest.raises(CorrectedFinalOutputError, match="no safe"):
        materialize_corrected_final_outputs(
            handoff_path=handoff_path,
            corrected_run_dir=corrected_run,
            final_root=final_root,
            review_root=tmp_path / "review",
        )

    assert not list(final_root.glob("*.pdf"))
