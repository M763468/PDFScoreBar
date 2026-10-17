from __future__ import annotations

import hashlib
from pathlib import Path

import fitz
import pytest

from src.pdf_to_images import render_pdf_to_memory
from src.pipeline.utils.images import resolve_source_page_references


def _pdf(path: Path, pages: int = 4) -> None:
    document = fitz.open()
    for _ in range(pages):
        document.new_page()
    document.save(path)
    document.close()


def test_direct_pdf_selection_retains_physical_source_pages(tmp_path: Path) -> None:
    pdf = tmp_path / "score.pdf"
    _pdf(pdf)
    source_sha256 = hashlib.sha256(pdf.read_bytes()).hexdigest()
    config = {
        "steps": {"pdf_to_images": True},
        "inputs": {"pdf_path": str(pdf), "pdf_to_images": {"pages": "3,1,4"}},
    }
    references = resolve_source_page_references(
        config,
        [Path("page_001.png"), Path("page_003.png"), Path("page_004.png")],
        rendered_this_run=True,
        rendered_source_sha256=source_sha256,
        rendered_source_pages=[0, 2, 3],
    )
    assert [item["source_page"] for item in references if item is not None] == [0, 2, 3]
    assert all(item["kind"] == "direct_pdf_render" for item in references if item)
    assert all(item["source_document"]["sha256"] == source_sha256 for item in references if item)


def test_external_or_reordered_images_have_unknown_source_page() -> None:
    config = {
        "steps": {"pdf_to_images": False},
        "inputs": {"pdf_to_images": {"output_dir": "/external"}},
    }
    assert resolve_source_page_references(config, [Path("page_099.png"), Path("page_001.png")]) == [
        None,
        None,
    ]


def test_skipped_pdf_render_does_not_claim_direct_provenance(tmp_path: Path) -> None:
    pdf = tmp_path / "score.pdf"
    _pdf(pdf)
    config = {
        "steps": {"pdf_to_images": True},
        "inputs": {"pdf_path": str(pdf), "pdf_to_images": {"pages": "1"}},
    }
    assert resolve_source_page_references(
        config, [Path("page_001.png")], rendered_this_run=False
    ) == [None]


def test_direct_pdf_render_requires_render_step_identity(tmp_path: Path) -> None:
    pdf = tmp_path / "score.pdf"
    _pdf(pdf)
    config = {
        "steps": {"pdf_to_images": True},
        "inputs": {"pdf_path": str(pdf), "pdf_to_images": {"pages": "1"}},
    }
    with pytest.raises(ValueError, match="verified rendered source SHA-256"):
        resolve_source_page_references(
            config,
            [Path("page_001.png")],
            rendered_this_run=True,
            rendered_source_pages=[0],
        )


def test_direct_pdf_render_rejects_stale_or_reordered_page_stems(tmp_path: Path) -> None:
    pdf = tmp_path / "score.pdf"
    _pdf(pdf)
    source_sha256 = hashlib.sha256(pdf.read_bytes()).hexdigest()
    config = {
        "steps": {"pdf_to_images": True},
        "inputs": {"pdf_path": str(pdf), "pdf_to_images": {"pages": "1,3"}},
    }
    with pytest.raises(ValueError, match="physical page selection"):
        resolve_source_page_references(
            config,
            [Path("page_003.png"), Path("page_001.png")],
            rendered_this_run=True,
            rendered_source_sha256=source_sha256,
            rendered_source_pages=[0, 2],
        )


def test_direct_pdf_provenance_does_not_rehash_mutated_source_path(tmp_path: Path) -> None:
    pdf = tmp_path / "score.pdf"
    _pdf(pdf, pages=2)
    rendered_sha256 = hashlib.sha256(pdf.read_bytes()).hexdigest()

    replacement = tmp_path / "replacement.pdf"
    _pdf(replacement, pages=3)
    pdf.write_bytes(replacement.read_bytes())
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() != rendered_sha256

    config = {
        "steps": {"pdf_to_images": True},
        "inputs": {"pdf_path": str(pdf), "pdf_to_images": {"pages": "1"}},
    }
    references = resolve_source_page_references(
        config,
        [Path("page_001.png")],
        rendered_this_run=True,
        rendered_source_sha256=rendered_sha256,
        rendered_source_pages=[0],
    )
    assert references[0] is not None
    assert references[0]["source_document"]["sha256"] == rendered_sha256


def test_renderer_uses_provenance_bound_source_bytes(tmp_path: Path) -> None:
    pdf = tmp_path / "score.pdf"
    _pdf(pdf, pages=2)
    source_bytes = pdf.read_bytes()

    replacement = tmp_path / "replacement.pdf"
    _pdf(replacement, pages=1)
    pdf.write_bytes(replacement.read_bytes())

    rendered = render_pdf_to_memory(
        pdf,
        dpi=72.0,
        pages=[1],
        source_bytes=source_bytes,
    )

    assert len(rendered) == 1
    assert rendered[0][0] == 1


@pytest.mark.parametrize("dpi", [300, 360])
@pytest.mark.parametrize("resize", [{}, {"target_width": 510, "target_height": 660}])
def test_rendered_source_geometry_survives_public_review_and_correction(tmp_path, dpi, resize):
    import json

    from PIL import Image

    from src.pipeline.engine_executor import PipelineJobExecutor
    from src.pipeline.orchestrator import PipelineOrchestrator
    from src.pipeline.review.final_output import materialize_corrected_final_outputs
    from src.pipeline.review.manual_correction_materializer import (
        materialize_manual_correction_review_package,
    )

    source = tmp_path / "input.pdf"
    with fitz.open() as pdf:
        pdf.new_page(width=612, height=792)
        pdf.new_page(width=100, height=100)  # Intentionally unselected.
        last = pdf.new_page(width=595.28, height=841.89)
        last.set_cropbox(fitz.Rect(10, 20, 585.28, 821.89))
        last.set_rotation(90)
        expected = [(pdf[i].rect.width, pdf[i].rect.height) for i in (0, 2)]
        pdf.save(source)

    config = {
        "inputs": {
            "pdf_path": str(source),
            "pdf_to_images": {"dpi": dpi, "pages": "3,1", **resize},
        },
        "steps": {"pdf_to_images": True},
        "outputs": {"review": {"manual_correction_package": True}},
    }
    run = tmp_path / "run"
    orchestrator = PipelineOrchestrator(config, "geometry", run)
    source_sha, selected, sizes = orchestrator._run_pdf_to_images()
    images = sorted((run / "inputs/images").glob("*.png"))
    references = resolve_source_page_references(
        config,
        images,
        rendered_this_run=True,
        rendered_source_sha256=source_sha,
        rendered_source_pages=selected,
        rendered_page_sizes_points=sizes,
    )
    manifest_pages = []
    for index, (image, reference) in enumerate(zip(images, references, strict=True)):
        assert reference["page_size_points"] == pytest.approx(expected[index])
        with Image.open(image) as png:
            assert "dpi" not in png.info
        page_id = image.stem
        numbering = run / "outputs" / page_id / "numbering_final.json"
        numbering.parent.mkdir(parents=True)
        numbering.write_text(
            json.dumps(
                {
                    "pages": [
                        {
                            "systems": [
                                {
                                    "staves": [{"bbox": [50, 50, 250, 90]}],
                                    "measures": [{"bbox": [50, 50, 250, 90], "number": 42 + index}],
                                }
                            ]
                        }
                    ]
                }
            )
        )
        barlines = run / "intermediate" / page_id / "barlines.json"
        barlines.parent.mkdir(parents=True)
        barlines.write_text(json.dumps({"boxes": [{"bbox": [50, 50, 50, 90]}]}))
        manifest_pages.append(
            {
                "page_id": page_id,
                "image_path": str(image),
                "barlines_json": str(barlines),
                "source_reference": reference,
            }
        )
    (run / "manifest.json").write_text(json.dumps({"config": config, "pages": manifest_pages}))
    private_review = run / ".review_work"
    materialize_manual_correction_review_package(run_root=run, review_root=private_review)
    public = tmp_path / "public_review"
    PipelineJobExecutor._copy_review(private_review, public, source_job_id="geometry")
    handoff = public / "manual_correction_input.json"
    payload = json.loads(handoff.read_text())
    assert "source_manifest" not in payload
    assert "source_artifact_root" not in payload
    source.unlink()  # Correction output must not depend on the original PDF.
    summary = materialize_corrected_final_outputs(handoff_path=handoff, corrected_run_dir=run)
    assert summary["warnings"] == []
    with fitz.open(summary["final_pdf"]) as pdf:
        for page, size in zip(pdf, expected, strict=True):
            assert (page.rect.width, page.rect.height) == pytest.approx(size)
    assert [p["row_labels"][0]["row_start_measure_number"] for p in summary["pages"]] == [42, 43]
