# run_mmr_batch

> 58 nodes · cohesion 0.07

## Key Concepts

- **run_mmr_batch()** (25 connections) — `src/pipeline/steps/numbering.py`
- **create_mmr_rapidocr()** (24 connections) — `src/measure_numbering/rapidocr_provider.py`
- **steps/numbering.py** (23 connections) — `src/pipeline/steps/numbering.py`
- **collect_rapidocr_providers()** (17 connections) — `src/measure_numbering/rapidocr_provider.py`
- **eval_mmr_overrides.py** (15 connections) — `tools/issue94/eval_mmr_overrides.py`
- **rapidocr_provider.py** (13 connections) — `src/measure_numbering/rapidocr_provider.py`
- **normalize_rapidocr_provider()** (10 connections) — `src/measure_numbering/rapidocr_provider.py`
- **test_pipeline_numbering_mmr_provider.py** (10 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **_build_summary()** (10 connections) — `tools/issue94/eval_mmr_overrides.py`
- **_should_replace_mmr_ocr_engine()** (9 connections) — `src/pipeline/steps/numbering.py`
- **test_mmr_rapidocr_provider.py** (9 connections) — `tests/test_mmr_rapidocr_provider.py`
- **eval_all_mmr.py** (9 connections) — `tools/issue94/eval_all_mmr.py`
- **Any** (8 connections)
- **rebase_mmr_overrides_to_page_local()** (7 connections) — `src/pipeline/steps/numbering.py`
- **main()** (7 connections) — `tools/issue94/eval_mmr_overrides.py`
- **main()** (6 connections) — `tools/issue94/eval_all_mmr.py`
- **_load_json()** (6 connections) — `tools/issue94/eval_mmr_overrides.py`
- **_write_json()** (6 connections) — `tools/issue94/eval_mmr_overrides.py`
- **Any** (5 connections)
- **_index_overrides()** (5 connections) — `tools/issue94/eval_mmr_overrides.py`
- **_get_providers_from_obj()** (4 connections) — `src/measure_numbering/rapidocr_provider.py`
- **_is_default_mmr_ocr_engine()** (4 connections) — `src/pipeline/steps/numbering.py`
- **_DummySession** (4 connections) — `tests/test_mmr_rapidocr_provider.py`
- **test_run_mmr_batch_updates_default_engine_in_place()** (4 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **_override_key()** (4 connections) — `tools/issue94/eval_mmr_overrides.py`
- *... and 33 more nodes in this community*

## Relationships

- [load_json](load_json.md) (17 shared connections)
- [MMROCREngine](MMROCREngine.md) (8 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (8 shared connections)
- [audit_positive_geometry_disagreements.py](audit_positive_geometry_disagreements.py.md) (6 shared connections)
- [run_original_geometry_graft.py](run_original_geometry_graft.py.md) (6 shared connections)
- [diagnose_ocr_frame_changed_pages.py](diagnose_ocr_frame_changed_pages.py.md) (5 shared connections)
- [run_phase_c_mmr_regression.py](run_phase_c_mmr_regression.py.md) (3 shared connections)
- [current_support_worker.py](current_support_worker.py.md) (3 shared connections)
- [MMRProcessor](MMRProcessor.md) (3 shared connections)
- [Staff](Staff.md) (3 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (3 shared connections)
- [get_nested](get_nested.md) (2 shared connections)

## Source Files

- `src/measure_numbering/rapidocr_provider.py`
- `src/pipeline/steps/numbering.py`
- `tests/test_mmr_rapidocr_provider.py`
- `tests/test_pipeline_numbering_mmr_provider.py`
- `tools/issue94/eval_all_mmr.py`
- `tools/issue94/eval_mmr_overrides.py`

## Audit Trail

- EXTRACTED: 187 (98%)
- INFERRED: 3 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*