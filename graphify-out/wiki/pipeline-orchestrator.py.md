# pipeline/orchestrator.py

> 20 nodes · cohesion 0.19

## Key Concepts

- **pipeline/orchestrator.py** (47 connections) — `src/pipeline/orchestrator.py`
- **pdf_to_images.py** (10 connections) — `src/pdf_to_images.py`
- **render_pdf_to_memory()** (8 connections) — `src/pdf_to_images.py`
- **save_image()** (7 connections) — `src/pdf_to_images.py`
- **PdfConversionError** (6 connections) — `src/pdf_to_images.py`
- **render_pdf()** (6 connections) — `src/pdf_to_images.py`
- **pixmap_to_array()** (5 connections) — `src/pdf_to_images.py`
- **apply_barline_overrides()** (5 connections) — `src/pipeline/steps/barlines.py`
- **main()** (4 connections) — `src/pdf_to_images.py`
- **normalise_pages()** (4 connections) — `src/pdf_to_images.py`
- **ndarray** (4 connections)
- **parse_args()** (3 connections) — `src/pdf_to_images.py`
- **Path** (3 connections)
- **resize_image()** (3 connections) — `src/pdf_to_images.py`
- **Any** (2 connections)
- **Pixmap** (1 connections)
- **Namespace** (1 connections)
- **RuntimeError** (1 connections)
- **Raised when a page cannot be rendered or saved.** (1 connections) — `src/pdf_to_images.py`
- **Pipeline orchestration for end-to-end processing.** (1 connections) — `src/pipeline/orchestrator.py`

## Relationships

- [get_nested](get_nested.md) (6 shared connections)
- [.run](run.md) (5 shared connections)
- [diagnose_phase_b_layout_divergence.py](diagnose_phase_b_layout_divergence.py.md) (4 shared connections)
- [run_mmr_batch](run_mmr_batch.md) (4 shared connections)
- [images.py](images.py.md) (3 shared connections)
- [build_manifest](build_manifest.md) (2 shared connections)
- [materialize_manual_correction_review_package](materialize_manual_correction_review_package.md) (2 shared connections)
- [phase_b_page001_acceptance.py](phase_b_page001_acceptance.py.md) (2 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (2 shared connections)
- [load_json](load_json.md) (2 shared connections)
- [Score](Score.md) (2 shared connections)
- [MMRProcessor](MMRProcessor.md) (2 shared connections)

## Source Files

- `src/pdf_to_images.py`
- `src/pipeline/orchestrator.py`
- `src/pipeline/steps/barlines.py`

## Audit Trail

- EXTRACTED: 85 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*