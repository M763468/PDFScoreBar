# create_mmr_rapidocr

> 25 nodes · cohesion 0.14

## Key Concepts

- **create_mmr_rapidocr()** (24 connections) — `src/measure_numbering/rapidocr_provider.py`
- **run_representative_mmr_reuse.py** (21 connections) — `tools/issue274/run_representative_mmr_reuse.py`
- **collect_rapidocr_providers()** (17 connections) — `src/measure_numbering/rapidocr_provider.py`
- **providers_include_cuda()** (15 connections) — `src/measure_numbering/rapidocr_provider.py`
- **rapidocr_provider.py** (13 connections) — `src/measure_numbering/rapidocr_provider.py`
- **main()** (13 connections) — `tools/issue274/run_representative_mmr_reuse.py`
- **test_mmr_rapidocr_provider.py** (9 connections) — `tests/test_mmr_rapidocr_provider.py`
- **_get_providers_from_obj()** (4 connections) — `src/measure_numbering/rapidocr_provider.py`
- **_DummySession** (4 connections) — `tests/test_mmr_rapidocr_provider.py`
- **_compact()** (3 connections) — `tools/issue274/run_representative_mmr_reuse.py`
- **onnxruntime_has_cuda_provider()** (2 connections) — `src/measure_numbering/rapidocr_provider.py`
- **Any** (2 connections)
- **_DummyRapidOCR** (2 connections) — `tests/test_mmr_rapidocr_provider.py`
- **.__init__()** (2 connections) — `tests/test_mmr_rapidocr_provider.py`
- **.get_providers()** (2 connections) — `tests/test_mmr_rapidocr_provider.py`
- **test_auto_keeps_default_constructor_when_cuda_provider_is_unavailable()** (2 connections) — `tests/test_mmr_rapidocr_provider.py`
- **test_auto_uses_cuda_kwargs_when_cuda_provider_is_available()** (2 connections) — `tests/test_mmr_rapidocr_provider.py`
- **test_cpu_mode_keeps_default_constructor_even_when_cuda_is_available()** (2 connections) — `tests/test_mmr_rapidocr_provider.py`
- **test_cuda_mode_warns_when_cuda_provider_is_not_confirmed()** (2 connections) — `tests/test_mmr_rapidocr_provider.py`
- **test_normalize_rapidocr_provider_rejects_unknown_mode()** (2 connections) — `tests/test_mmr_rapidocr_provider.py`
- **RapidOCR** (1 connections)
- **RapidOCR provider selection helpers for MMR OCR.** (1 connections) — `src/measure_numbering/rapidocr_provider.py`
- **.__init__()** (1 connections) — `tests/test_mmr_rapidocr_provider.py`
- **_install_import_stubs()** (1 connections) — `tests/test_mmr_rapidocr_provider.py`
- **Run the Issue #274 12-page production MMR gate from retained artifacts only.** (1 connections) — `tools/issue274/run_representative_mmr_reuse.py`

## Relationships

- [run_phase_c_mmr_regression.py](run_phase_c_mmr_regression.py.md) (17 shared connections)
- [audit_positive_geometry_disagreements.py](audit_positive_geometry_disagreements.py.md) (9 shared connections)
- [run_mmr_batch](run_mmr_batch.md) (7 shared connections)
- [diagnose_ocr_frame_changed_pages.py](diagnose_ocr_frame_changed_pages.py.md) (7 shared connections)
- [run_original_geometry_graft.py](run_original_geometry_graft.py.md) (6 shared connections)
- [mmr_support_reuse.py](mmr_support_reuse.py.md) (6 shared connections)
- [load_json](load_json.md) (4 shared connections)
- [MMRClassifier](MMRClassifier.md) (3 shared connections)
- [MMROCREngine](MMROCREngine.md) (2 shared connections)
- [MMRProcessor](MMRProcessor.md) (2 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (1 shared connections)

## Source Files

- `src/measure_numbering/rapidocr_provider.py`
- `tests/test_mmr_rapidocr_provider.py`
- `tools/issue274/run_representative_mmr_reuse.py`

## Audit Trail

- EXTRACTED: 105 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*