# pipeline/orchestrator.py

> 14 nodes · cohesion 0.20

## Key Concepts

- **pipeline/orchestrator.py** (47 connections) — `src/pipeline/orchestrator.py`
- **steps/numbering.py** (23 connections) — `src/pipeline/steps/numbering.py`
- **resolve_barlines_and_masks_config()** (9 connections) — `src/pipeline/detection/utils.py`
- **empty_numbering_payload()** (7 connections) — `src/pipeline/steps/numbering.py`
- **rebase_mmr_overrides_to_page_local()** (7 connections) — `src/pipeline/steps/numbering.py`
- **_ReviewPackageConfig** (6 connections) — `src/pipeline/orchestrator.py`
- **Any** (5 connections)
- **_is_default_mmr_ocr_engine()** (4 connections) — `src/pipeline/steps/numbering.py`
- **build_add_measure_numbers_cmd()** (3 connections) — `src/pipeline/steps/numbering.py`
- **Path** (3 connections)
- **Resolves paths based on configuration when detection is skipped.** (1 connections) — `src/pipeline/detection/utils.py`
- **Pipeline orchestration for end-to-end processing.** (1 connections) — `src/pipeline/orchestrator.py`
- **Numbering step helpers.** (1 connections) — `src/pipeline/steps/numbering.py`
- **Select one global override page at the MMR Phase B -> Phase C boundary. Phase B…** (1 connections) — `src/pipeline/steps/numbering.py`

## Relationships

- [run_mmr_batch](run_mmr_batch.md) (9 shared connections)
- [load_image](load_image.md) (8 shared connections)
- [MMROCREngine](MMROCREngine.md) (7 shared connections)
- [Staff](Staff.md) (6 shared connections)
- [get_nested](get_nested.md) (5 shared connections)
- [test_issue264_phase_a_connector_geometry.py](test_issue264_phase_a_connector_geometry.py.md) (5 shared connections)
- [.run](run.md) (5 shared connections)
- [pdf_to_images.py](pdf_to_images.py.md) (4 shared connections)
- [diagnose_phase_b_layout_divergence.py](diagnose_phase_b_layout_divergence.py.md) (3 shared connections)
- [load_json](load_json.md) (3 shared connections)
- [write_json](write_json.md) (3 shared connections)
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) (3 shared connections)

## Source Files

- `src/pipeline/detection/utils.py`
- `src/pipeline/orchestrator.py`
- `src/pipeline/steps/numbering.py`

## Audit Trail

- EXTRACTED: 96 (96%)
- INFERRED: 4 (4%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*