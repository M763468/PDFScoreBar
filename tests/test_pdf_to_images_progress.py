from pathlib import Path

import fitz

from src.pdf_to_images import parse_args, render_pdf_to_memory


def test_render_pdf_to_memory_reports_each_completed_page():
    document = fitz.open()
    try:
        document.new_page(width=100, height=100)
        document.new_page(width=100, height=100)
        source_bytes = document.tobytes()
    finally:
        document.close()

    progress = []
    rendered = render_pdf_to_memory(
        Path("unused.pdf"),
        dpi=72.0,
        pages=[0, 1],
        source_bytes=source_bytes,
        on_page_rendered=lambda completed, source_page_index: progress.append(
            (completed, source_page_index)
        ),
    )

    assert [page_index for page_index, _image in rendered] == [0, 1]
    assert progress == [(1, 0), (2, 1)]


def test_pdf_to_images_cli_requires_explicit_input_and_output_paths():
    import pytest

    with pytest.raises(SystemExit):
        parse_args([])

    args = parse_args(["--pdf", "score.pdf", "--output-dir", "artifacts/rendered"])
    assert args.pdf == Path("score.pdf")
    assert args.output_dir == Path("artifacts/rendered")
