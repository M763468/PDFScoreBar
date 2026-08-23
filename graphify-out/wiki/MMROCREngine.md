# MMROCREngine

> 39 nodes · cohesion 0.09

## Key Concepts

- **MMROCREngine** (64 connections) — `src/measure_numbering/mmr.py`
- **TestMMROCRHeuristics** (16 connections) — `tests/test_mmr_ocr_heuristics.py`
- **test_pipeline_numbering_mmr_provider.py** (10 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **_should_replace_mmr_ocr_engine()** (9 connections) — `src/pipeline/steps/numbering.py`
- **_box()** (8 connections) — `tests/test_mmr_ocr_heuristics.py`
- **.collect_one_bar_evidence()** (7 connections) — `src/measure_numbering/mmr.py`
- **._candidate_items()** (5 connections) — `src/measure_numbering/mmr.py`
- **ndarray** (5 connections)
- **test_mmr_ocr_heuristics.py** (5 connections) — `tests/test_mmr_ocr_heuristics.py`
- **.select_best_candidate()** (4 connections) — `src/measure_numbering/mmr.py`
- **test_run_mmr_batch_updates_default_engine_in_place()** (4 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **._extract_numeric_candidates()** (3 connections) — `src/measure_numbering/mmr.py`
- **._has_blacklisted_text()** (3 connections) — `src/measure_numbering/mmr.py`
- **.preprocess_variant()** (3 connections) — `src/measure_numbering/mmr.py`
- **.rotate_image()** (3 connections) — `src/measure_numbering/mmr.py`
- **.setUp()** (3 connections) — `tests/test_mmr_ocr_heuristics.py`
- **CustomInjectedEngine** (3 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **ProviderOCR** (3 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **test_should_preserve_custom_injected_engine()** (3 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **test_should_preserve_default_engine_with_matching_provider_mode()** (3 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **test_should_replace_default_engine_without_provider_mode()** (3 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **.mask_hbar_candidates()** (2 connections) — `src/measure_numbering/mmr.py`
- **.merge_ocr_results()** (2 connections) — `src/measure_numbering/mmr.py`
- **.test_attached_digit_in_blacklisted_text_is_rejected()** (2 connections) — `tests/test_mmr_ocr_heuristics.py`
- **.test_blacklisted_text_without_digits_is_rejected()** (2 connections) — `tests/test_mmr_ocr_heuristics.py`
- *... and 14 more nodes in this community*

## Relationships

- [MMRProcessor](MMRProcessor.md) (14 shared connections)
- [test_issue212_mmr_unmasked_fallback.py](test_issue212_mmr_unmasked_fallback.py.md) (13 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (7 shared connections)
- [MMRClassifier](MMRClassifier.md) (4 shared connections)
- [run_mmr_batch](run_mmr_batch.md) (4 shared connections)
- [audit_positive_geometry_disagreements.py](audit_positive_geometry_disagreements.py.md) (4 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (3 shared connections)
- [diagnose_ocr_frame_changed_pages.py](diagnose_ocr_frame_changed_pages.py.md) (3 shared connections)
- [load_json](load_json.md) (2 shared connections)
- [run_original_geometry_graft.py](run_original_geometry_graft.py.md) (2 shared connections)
- [write_json](write_json.md) (2 shared connections)
- [.run](run.md) (1 shared connections)

## Source Files

- `src/measure_numbering/mmr.py`
- `src/pipeline/steps/numbering.py`
- `tests/test_mmr_ocr_heuristics.py`
- `tests/test_pipeline_numbering_mmr_provider.py`

## Audit Trail

- EXTRACTED: 111 (87%)
- INFERRED: 17 (13%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*