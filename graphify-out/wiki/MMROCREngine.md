# MMROCREngine

> 22 nodes · cohesion 0.16

## Key Concepts

- **MMROCREngine** (64 connections) — `src/measure_numbering/mmr.py`
- **test_pipeline_numbering_mmr_provider.py** (10 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **.collect_one_bar_evidence()** (7 connections) — `src/measure_numbering/mmr.py`
- **._candidate_items()** (5 connections) — `src/measure_numbering/mmr.py`
- **ndarray** (5 connections)
- **.select_best_candidate()** (4 connections) — `src/measure_numbering/mmr.py`
- **test_run_mmr_batch_updates_default_engine_in_place()** (4 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **._extract_numeric_candidates()** (3 connections) — `src/measure_numbering/mmr.py`
- **._has_blacklisted_text()** (3 connections) — `src/measure_numbering/mmr.py`
- **.preprocess_variant()** (3 connections) — `src/measure_numbering/mmr.py`
- **.rotate_image()** (3 connections) — `src/measure_numbering/mmr.py`
- **CustomInjectedEngine** (3 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **ProviderOCR** (3 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **test_should_preserve_custom_injected_engine()** (3 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **test_should_preserve_default_engine_with_matching_provider_mode()** (3 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **test_should_replace_default_engine_without_provider_mode()** (3 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **.mask_hbar_candidates()** (2 connections) — `src/measure_numbering/mmr.py`
- **.merge_ocr_results()** (2 connections) — `src/measure_numbering/mmr.py`
- **test_should_replace_absent_engine()** (2 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **Return raw and merged OCR items so merges do not erase valid single digits.** (1 connections) — `src/measure_numbering/mmr.py`
- **Return OCR evidence for printed one-bar rest markers. MMR overrides represent…** (1 connections) — `src/measure_numbering/mmr.py`
- **Handles RapidOCR and post-processing for MMR number detection.** (1 connections) — `src/measure_numbering/mmr.py`

## Relationships

- [test_issue212_mmr_unmasked_fallback.py](test_issue212_mmr_unmasked_fallback.py.md) (13 shared connections)
- [run_mmr_batch](run_mmr_batch.md) (8 shared connections)
- [MMRClassifier](MMRClassifier.md) (6 shared connections)
- [object](object.md) (6 shared connections)
- [audit_positive_geometry_disagreements.py](audit_positive_geometry_disagreements.py.md) (4 shared connections)
- [TestMMROCRHeuristics](TestMMROCRHeuristics.md) (3 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (3 shared connections)
- [diagnose_ocr_frame_changed_pages.py](diagnose_ocr_frame_changed_pages.py.md) (3 shared connections)
- [get_nested](get_nested.md) (2 shared connections)
- [run_phase_c_mmr_regression.py](run_phase_c_mmr_regression.py.md) (2 shared connections)
- [run_original_geometry_graft.py](run_original_geometry_graft.py.md) (2 shared connections)
- [create_mmr_rapidocr](create_mmr_rapidocr.md) (2 shared connections)

## Source Files

- `src/measure_numbering/mmr.py`
- `tests/test_pipeline_numbering_mmr_provider.py`

## Audit Trail

- EXTRACTED: 82 (85%)
- INFERRED: 15 (15%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*