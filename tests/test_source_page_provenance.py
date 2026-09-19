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
    assert all(
        item["source_document"]["sha256"] == source_sha256 for item in references if item
    )


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
