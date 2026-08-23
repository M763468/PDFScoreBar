# run_mmr_batch

> 41 nodes · cohesion 0.11

## Key Concepts

- **run_mmr_batch()** (25 connections) — `src/pipeline/steps/numbering.py`
- **create_mmr_rapidocr()** (24 connections) — `src/measure_numbering/rapidocr_provider.py`
- **collect_rapidocr_providers()** (17 connections) — `src/measure_numbering/rapidocr_provider.py`
- **eval_mmr_overrides.py** (15 connections) — `tools/issue94/eval_mmr_overrides.py`
- **rapidocr_provider.py** (13 connections) — `src/measure_numbering/rapidocr_provider.py`
- **normalize_rapidocr_provider()** (10 connections) — `src/measure_numbering/rapidocr_provider.py`
- **_build_summary()** (10 connections) — `tools/issue94/eval_mmr_overrides.py`
- **test_mmr_rapidocr_provider.py** (9 connections) — `tests/test_mmr_rapidocr_provider.py`
- **eval_all_mmr.py** (9 connections) — `tools/issue94/eval_all_mmr.py`
- **Any** (8 connections)
- **main()** (7 connections) — `tools/issue94/eval_mmr_overrides.py`
- **main()** (6 connections) — `tools/issue94/eval_all_mmr.py`
- **_load_json()** (6 connections) — `tools/issue94/eval_mmr_overrides.py`
- **_write_json()** (6 connections) — `tools/issue94/eval_mmr_overrides.py`
- **_index_overrides()** (5 connections) — `tools/issue94/eval_mmr_overrides.py`
- **_get_providers_from_obj()** (4 connections) — `src/measure_numbering/rapidocr_provider.py`
- **_DummySession** (4 connections) — `tests/test_mmr_rapidocr_provider.py`
- **_override_key()** (4 connections) — `tools/issue94/eval_mmr_overrides.py`
- **_measure_count()** (3 connections) — `tools/issue94/eval_mmr_overrides.py`
- **_normalise_overrides()** (3 connections) — `tools/issue94/eval_mmr_overrides.py`
- **_override_skip()** (3 connections) — `tools/issue94/eval_mmr_overrides.py`
- **parse_args()** (3 connections) — `tools/issue94/eval_mmr_overrides.py`
- **Path** (3 connections)
- **onnxruntime_has_cuda_provider()** (2 connections) — `src/measure_numbering/rapidocr_provider.py`
- **Any** (2 connections)
- *... and 16 more nodes in this community*

## Relationships

- [load_json](load_json.md) (10 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (9 shared connections)
- [write_json](write_json.md) (8 shared connections)
- [audit_positive_geometry_disagreements.py](audit_positive_geometry_disagreements.py.md) (6 shared connections)
- [run_original_geometry_graft.py](run_original_geometry_graft.py.md) (6 shared connections)
- [diagnose_ocr_frame_changed_pages.py](diagnose_ocr_frame_changed_pages.py.md) (5 shared connections)
- [MMROCREngine](MMROCREngine.md) (4 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (2 shared connections)
- [.run](run.md) (1 shared connections)
- [MMRProcessor](MMRProcessor.md) (1 shared connections)

## Source Files

- `src/measure_numbering/rapidocr_provider.py`
- `src/pipeline/steps/numbering.py`
- `tests/test_mmr_rapidocr_provider.py`
- `tools/issue94/eval_all_mmr.py`
- `tools/issue94/eval_mmr_overrides.py`

## Audit Trail

- EXTRACTED: 138 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*