from __future__ import annotations

import hashlib
from pathlib import Path

import fitz

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
    config = {
        "steps": {"pdf_to_images": True},
        "inputs": {"pdf_path": str(pdf), "pdf_to_images": {"pages": "3,1,4"}},
    }
    references = resolve_source_page_references(
        config,
        [Path("page_001.png"), Path("page_003.png"), Path("page_004.png")],
    )
    assert [item["source_page"] for item in references if item is not None] == [0, 2, 3]
    assert all(item["kind"] == "direct_pdf_render" for item in references if item)
    assert all(
        item["source_document"]["sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()
        for item in references
        if item
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
