# Community 122

> 21 nodes · cohesion 0.20

## Key Concepts

- **pdf_to_images.py** (12 connections) — `src/pdf_to_images.py`
- **render_pdf_to_memory()** (12 connections) — `src/pdf_to_images.py`
- **._run_pdf_to_images()** (12 connections) — `src/pipeline/orchestrator.py`
- **render_pdf()** (8 connections) — `src/pdf_to_images.py`
- **save_image()** (7 connections) — `src/pdf_to_images.py`
- **PdfConversionError** (6 connections) — `src/pdf_to_images.py`
- **normalise_pages()** (5 connections) — `src/pdf_to_images.py`
- **parse_args()** (5 connections) — `src/pdf_to_images.py`
- **pixmap_to_array()** (5 connections) — `src/pdf_to_images.py`
- **test_pdf_to_images_progress.py** (5 connections) — `tests/test_pdf_to_images_progress.py`
- **main()** (4 connections) — `src/pdf_to_images.py`
- **ndarray** (4 connections)
- **Path** (3 connections)
- **resize_image()** (3 connections) — `src/pdf_to_images.py`
- **test_pdf_to_images_cli_requires_explicit_input_and_output_paths()** (2 connections) — `tests/test_pdf_to_images_progress.py`
- **test_render_pdf_to_memory_reports_each_completed_page()** (2 connections) — `tests/test_pdf_to_images_progress.py`
- **Pixmap** (1 connections)
- **Namespace** (1 connections)
- **RuntimeError** (1 connections)
- **Raised when a page cannot be rendered or saved.** (1 connections) — `src/pdf_to_images.py`
- **Step 1: Convert PDF to images in-process and retain exact source identity.** (1 connections) — `src/pipeline/orchestrator.py`

## Relationships

- [Community 21](Community_21.md) (9 shared connections)
- [Community 166](Community_166.md) (3 shared connections)
- [Community 164](Community_164.md) (2 shared connections)
- [Community 154](Community_154.md) (1 shared connections)
- [Community 144](Community_144.md) (1 shared connections)
- [Community 12](Community_12.md) (1 shared connections)
- [Community 112](Community_112.md) (1 shared connections)

## Source Files

- `src/pdf_to_images.py`
- `src/pipeline/orchestrator.py`
- `tests/test_pdf_to_images_progress.py`

## Audit Trail

- EXTRACTED: 59 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*