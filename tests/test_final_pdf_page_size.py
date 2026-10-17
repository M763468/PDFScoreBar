"""Physical PDF dimensions are a separate contract from embedded image pixels."""

import json

import fitz
import pytest
from PIL import Image

from src.pipeline.review.final_output import (
    CorrectedFinalOutputError,
    materialize_corrected_final_outputs,
)


def _package(tmp_path, specs):
    pages = []
    for index, (pixels, points) in enumerate(specs, 1):
        page_id = f"page_{index:03d}"
        image = tmp_path / f"{page_id}.png"
        Image.new("RGB", pixels, "white").save(image)
        numbering = tmp_path / "outputs" / page_id / "numbering_final.json"
        numbering.parent.mkdir(parents=True)
        numbering.write_text(json.dumps({"pages": [{"systems": []}]}))
        page = {"page_id": page_id, "source_image": image.name}
        if points is not None:
            page["page_size_points"] = points
        pages.append(page)
    handoff = tmp_path / "handoff.json"
    handoff.write_text(json.dumps({"pages": pages}))
    return handoff


@pytest.mark.parametrize("dpi", [300, 360])
def test_letter_pdf_has_letter_size_without_png_dpi_metadata(tmp_path, dpi):
    handoff = _package(tmp_path, [((int(8.5 * dpi), 11 * dpi), [612, 792])])
    with Image.open(tmp_path / "page_001.png") as image:
        assert "dpi" not in image.info
    summary = materialize_corrected_final_outputs(handoff_path=handoff, corrected_run_dir=tmp_path)
    with fitz.open(summary["final_pdf"]) as pdf:
        assert tuple(pdf[0].mediabox) == pytest.approx((0, 0, 612, 792))


def test_mixed_sizes_and_resized_images_keep_each_source_page_size(tmp_path):
    sizes = [[612, 792], [841.89, 595.28], [320, 460]]
    handoff = _package(tmp_path, [((510, 660), points) for points in sizes])
    summary = materialize_corrected_final_outputs(handoff_path=handoff, corrected_run_dir=tmp_path)
    with fitz.open(summary["final_pdf"]) as pdf:
        assert len(pdf) == len(sizes)
        for page, size in zip(pdf, sizes, strict=True):
            assert (page.rect.width, page.rect.height) == pytest.approx(size)


@pytest.mark.parametrize("points", [[0, 792], [-1, 792], [float("nan"), 792], [612], "letter"])
def test_invalid_explicit_page_size_is_rejected(tmp_path, points):
    handoff = _package(tmp_path, [((100, 100), points)])
    with pytest.raises(CorrectedFinalOutputError, match="page_size_points"):
        materialize_corrected_final_outputs(handoff_path=handoff, corrected_run_dir=tmp_path)


def test_legacy_package_uses_image_dpi_when_available(tmp_path):
    handoff = _package(tmp_path, [((600, 300), None)])
    image_path = tmp_path / "page_001.png"
    Image.new("RGB", (600, 300), "white").save(image_path, dpi=(150, 150))
    with Image.open(image_path) as image:
        x_dpi, y_dpi = image.info["dpi"]
    summary = materialize_corrected_final_outputs(handoff_path=handoff, corrected_run_dir=tmp_path)
    with fitz.open(summary["final_pdf"]) as pdf:
        assert (pdf[0].rect.width, pdf[0].rect.height) == pytest.approx(
            (600 * 72 / x_dpi, 300 * 72 / y_dpi)
        )


def test_legacy_package_without_size_reports_default_dpi_assumption(tmp_path):
    handoff = _package(tmp_path, [((600, 300), None)])
    summary = materialize_corrected_final_outputs(handoff_path=handoff, corrected_run_dir=tmp_path)
    with fitz.open(summary["final_pdf"]) as pdf:
        assert (pdf[0].rect.width, pdf[0].rect.height) == pytest.approx((144, 72))
    assert any("300 DPI" in warning for warning in summary["warnings"])
