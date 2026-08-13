# create_mmr_rapidocr

> 21 nodes · cohesion 0.15

## Key Concepts

- **create_mmr_rapidocr()** (12 connections) — `src/measure_numbering/rapidocr_provider.py`
- **rapidocr_provider.py** (10 connections) — `src/measure_numbering/rapidocr_provider.py`
- **test_mmr_rapidocr_provider.py** (9 connections) — `tests/test_mmr_rapidocr_provider.py`
- **collect_rapidocr_providers()** (4 connections) — `src/measure_numbering/rapidocr_provider.py`
- **_get_providers_from_obj()** (4 connections) — `src/measure_numbering/rapidocr_provider.py`
- **_DummySession** (4 connections) — `tests/test_mmr_rapidocr_provider.py`
- **onnxruntime_has_cuda_provider()** (2 connections) — `src/measure_numbering/rapidocr_provider.py`
- **providers_include_cuda()** (2 connections) — `src/measure_numbering/rapidocr_provider.py`
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

## Relationships

- [steps/numbering.py](steps-numbering.py.md) (7 shared connections)

## Source Files

- `src/measure_numbering/rapidocr_provider.py`
- `tests/test_mmr_rapidocr_provider.py`

## Audit Trail

- EXTRACTED: 37 (97%)
- INFERRED: 1 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*