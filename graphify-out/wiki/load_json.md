# load_json

> 53 nodes · cohesion 0.09

## Key Concepts

- **load_json()** (41 connections) — `src/pipeline/utils/io.py`
- **run_full68_mmr_reuse.py** (31 connections) — `tools/issue274/run_full68_mmr_reuse.py`
- **write_json()** (30 connections) — `src/pipeline/utils/io.py`
- **create_mmr_rapidocr()** (24 connections) — `src/measure_numbering/rapidocr_provider.py`
- **run_representative_mmr_reuse.py** (21 connections) — `tools/issue274/run_representative_mmr_reuse.py`
- **main()** (19 connections) — `tools/issue274/run_full68_mmr_reuse.py`
- **collect_rapidocr_providers()** (17 connections) — `src/measure_numbering/rapidocr_provider.py`
- **providers_include_cuda()** (15 connections) — `src/measure_numbering/rapidocr_provider.py`
- **rapidocr_provider.py** (13 connections) — `src/measure_numbering/rapidocr_provider.py`
- **build_mmr_support()** (13 connections) — `src/pipeline/mmr_support_reuse.py`
- **main()** (13 connections) — `tools/issue274/run_representative_mmr_reuse.py`
- **normalise_overrides()** (11 connections) — `tools/issue264/run_phase_c_mmr_regression.py`
- **validate_mmr_support_mapping.py** (11 connections) — `tools/issue274/validate_mmr_support_mapping.py`
- **_visible_path()** (10 connections) — `tools/issue274/validate_mmr_support_mapping.py`
- **test_mmr_rapidocr_provider.py** (9 connections) — `tests/test_mmr_rapidocr_provider.py`
- **_preflight()** (7 connections) — `tools/issue274/run_full68_mmr_reuse.py`
- **Any** (7 connections)
- **_semantic()** (7 connections) — `tools/issue274/run_full68_mmr_reuse.py`
- **_write_failure_report()** (6 connections) — `tools/issue274/run_full68_mmr_reuse.py`
- **main()** (6 connections) — `tools/issue274/validate_mmr_support_mapping.py`
- **_compare_accepted()** (5 connections) — `tools/issue274/run_full68_mmr_reuse.py`
- **_retained_performance()** (5 connections) — `tools/issue274/run_full68_mmr_reuse.py`
- **_get_providers_from_obj()** (4 connections) — `src/measure_numbering/rapidocr_provider.py`
- **Path** (4 connections)
- **write_manifest()** (4 connections) — `src/pipeline/utils/io.py`
- *... and 28 more nodes in this community*

## Relationships

- [run_phase_c_mmr_regression.py](run_phase_c_mmr_regression.py.md) (28 shared connections)
- [run_original_geometry_graft.py](run_original_geometry_graft.py.md) (17 shared connections)
- [phase_b_page001_acceptance.py](phase_b_page001_acceptance.py.md) (12 shared connections)
- [mmr_support_reuse.py](mmr_support_reuse.py.md) (11 shared connections)
- [audit_positive_geometry_disagreements.py](audit_positive_geometry_disagreements.py.md) (9 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (8 shared connections)
- [MMRProcessor](MMRProcessor.md) (8 shared connections)
- [diagnose_ocr_frame_changed_pages.py](diagnose_ocr_frame_changed_pages.py.md) (7 shared connections)
- [run_mmr_batch](run_mmr_batch.md) (7 shared connections)
- [.run](run.md) (7 shared connections)
- [eval_mmr_overrides.py](eval_mmr_overrides.py.md) (5 shared connections)
- [Staff](Staff.md) (4 shared connections)

## Source Files

- `src/measure_numbering/rapidocr_provider.py`
- `src/pipeline/mmr_support_reuse.py`
- `src/pipeline/utils/io.py`
- `tests/test_mmr_rapidocr_provider.py`
- `tools/issue264/run_phase_c_mmr_regression.py`
- `tools/issue274/run_full68_mmr_reuse.py`
- `tools/issue274/run_representative_mmr_reuse.py`
- `tools/issue274/validate_mmr_support_mapping.py`

## Audit Trail

- EXTRACTED: 259 (100%)
- INFERRED: 1 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*