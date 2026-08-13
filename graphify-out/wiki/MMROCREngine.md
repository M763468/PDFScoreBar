# MMROCREngine

> 28 nodes · cohesion 0.13

## Key Concepts

- **MMROCREngine** (51 connections) — `src/measure_numbering/mmr.py`
- **test_pipeline_numbering_mmr_provider.py** (10 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **_should_replace_mmr_ocr_engine()** (9 connections) — `src/pipeline/steps/numbering.py`
- **MaskedNumberUnmaskedDifferentNumberOCR** (9 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **.collect_one_bar_evidence()** (6 connections) — `src/measure_numbering/mmr.py`
- **._candidate_items()** (5 connections) — `src/measure_numbering/mmr.py`
- **.select_best_candidate()** (4 connections) — `src/measure_numbering/mmr.py`
- **ndarray** (4 connections)
- **test_run_mmr_batch_updates_default_engine_in_place()** (4 connections) — `tests/test_pipeline_numbering_mmr_provider.py`
- **._extract_numeric_candidates()** (3 connections) — `src/measure_numbering/mmr.py`
- **._has_blacklisted_text()** (3 connections) — `src/measure_numbering/mmr.py`
- **.preprocess_variant()** (3 connections) — `src/measure_numbering/mmr.py`
- **.rotate_image()** (3 connections) — `src/measure_numbering/mmr.py`
- **.collect_one_bar_evidence()** (3 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **.select_best_candidate()** (3 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
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
- *... and 3 more nodes in this community*

## Relationships

- [test_issue212_mmr_unmasked_fallback.py](test_issue212_mmr_unmasked_fallback.py.md) (11 shared connections)
- [object](object.md) (10 shared connections)
- [steps/numbering.py](steps-numbering.py.md) (9 shared connections)
- [MMRProcessor](MMRProcessor.md) (7 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (4 shared connections)
- [TestMMROCRHeuristics](TestMMROCRHeuristics.md) (3 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (2 shared connections)
- [.run](run.md) (1 shared connections)
- [PipelineOrchestrator](PipelineOrchestrator.md) (1 shared connections)

## Source Files

- `src/measure_numbering/mmr.py`
- `src/pipeline/steps/numbering.py`
- `tests/test_issue212_mmr_unmasked_fallback.py`
- `tests/test_pipeline_numbering_mmr_provider.py`

## Audit Trail

- EXTRACTED: 81 (84%)
- INFERRED: 16 (16%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*