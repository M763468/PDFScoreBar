# run_mmr_batch

> 23 nodes · cohesion 0.15

## Key Concepts

- **run_mmr_batch()** (25 connections) — `src/pipeline/steps/numbering.py`
- **steps/numbering.py** (23 connections) — `src/pipeline/steps/numbering.py`
- **test_pipeline_numbering_mmr_provider.py** (10 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **_should_replace_mmr_ocr_engine()** (9 connections) — `src/pipeline/steps/numbering.py`
- **empty_numbering_payload()** (7 connections) — `src/pipeline/steps/numbering.py`
- **rebase_mmr_overrides_to_page_local()** (7 connections) — `src/pipeline/steps/numbering.py`
- **load_image_size()** (6 connections) — `src/pipeline/utils/images.py`
- **Any** (5 connections)
- **_is_default_mmr_ocr_engine()** (4 connections) — `src/pipeline/steps/numbering.py`
- **ndarray** (4 connections)
- **test_run_mmr_batch_updates_default_engine_in_place()** (4 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **build_add_measure_numbers_cmd()** (3 connections) — `src/pipeline/steps/numbering.py`
- **Path** (3 connections)
- **CustomInjectedEngine** (3 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **ProviderOCR** (3 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **test_should_preserve_custom_injected_engine()** (3 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **test_should_preserve_default_engine_with_matching_provider_mode()** (3 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **test_should_replace_default_engine_without_provider_mode()** (3 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **test_should_replace_absent_engine()** (2 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **device** (1 connections)
- **Numbering step helpers.** (1 connections) — `src/pipeline/steps/numbering.py`
- **Runs MMR detection in-process for a batch of pages.** (1 connections) — `src/pipeline/steps/numbering.py`
- **Select one global override page at the MMR Phase B -> Phase C boundary. Phase B…** (1 connections) — `src/pipeline/steps/numbering.py`

## Relationships

- [eval_mmr_overrides.py](eval_mmr_overrides.py.md) (9 shared connections)
- [MMROCREngine](MMROCREngine.md) (8 shared connections)
- [load_json](load_json.md) (7 shared connections)
- [.run](run.md) (5 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (4 shared connections)
- [images.py](images.py.md) (4 shared connections)
- [current_support_worker.py](current_support_worker.py.md) (3 shared connections)
- [MMRProcessor](MMRProcessor.md) (3 shared connections)
- [Staff](Staff.md) (3 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (3 shared connections)
- [run_original_geometry_graft.py](run_original_geometry_graft.py.md) (2 shared connections)
- [cnn_scoring.py](cnn_scoring.py.md) (2 shared connections)

## Source Files

- `src/pipeline/steps/numbering.py`
- `src/pipeline/utils/images.py`
- `tests/test_pipeline_numbering_mmr_provider.py`

## Audit Trail

- EXTRACTED: 90 (98%)
- INFERRED: 2 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*