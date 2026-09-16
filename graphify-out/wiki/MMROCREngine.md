# MMROCREngine

> God node · 68 connections · `src/measure_numbering/mmr.py`

**Community:** [Community 2](Community_2.md)

## Connections by Relation

### calls
- run_mmr_batch() `EXTRACTED`
- run() `EXTRACTED`
- run_legacy() `EXTRACTED`
- [main()](main%28%29.md) `EXTRACTED`
- [main()](main%28%29.md) `EXTRACTED`
- run() `EXTRACTED`
- [main()](main%28%29.md) `EXTRACTED`
- run_h2_matrix() `EXTRACTED`
- _representative_report() `EXTRACTED`
- .run_mmr_batch_detection() `EXTRACTED`
- run_mmr_batch() `EXTRACTED`
- test_collect_one_bar_evidence_ignores_one_merged_into_multidigit() `EXTRACTED`
- test_collect_one_bar_evidence_keeps_single_one_and_ignores_eleven() `EXTRACTED`
- test_one_bar_veto_targets_marginal_cnn_negative_ocr_score_only() `EXTRACTED`
- test_run_mmr_batch_updates_default_engine_in_place() `EXTRACTED`
- .collect_one_bar_evidence() `EXTRACTED`
- .select_best_candidate() `EXTRACTED`
- .collect_one_bar_evidence() `EXTRACTED`
- .select_best_candidate() `EXTRACTED`
- .collect_one_bar_evidence() `EXTRACTED`

### contains
- mmr.py `EXTRACTED`

### imports
- pipeline/orchestrator.py `EXTRACTED`
- run_grouped_final_numbering_comparison.py `EXTRACTED`
- audit_positive_geometry_disagreements.py `EXTRACTED`
- run_full68_mmr_reuse.py `EXTRACTED`
- run_original_geometry_graft.py `EXTRACTED`
- steps/numbering.py `EXTRACTED`
- diagnose_ocr_frame_changed_pages.py `EXTRACTED`
- run_representative_mmr_reuse.py `EXTRACTED`
- test_issue212_mmr_unmasked_fallback.py `EXTRACTED`
- test_issue213_mmr_one_bar_veto.py `EXTRACTED`
- test_pipeline_numbering_mmr_provider.py `EXTRACTED`
- test_mmr_ocr_heuristics.py `EXTRACTED`

### method
- .collect_one_bar_evidence() `EXTRACTED`
- ._candidate_items() `EXTRACTED`
- ._hbar_mask_geometry() `EXTRACTED`
- ._preprocess_geometry() `EXTRACTED`
- .preprocess_variant() `EXTRACTED`
- .select_best_candidate() `EXTRACTED`
- .mask_hbar_candidates() `EXTRACTED`
- .rotate_image() `EXTRACTED`
- ._has_blacklisted_text() `EXTRACTED`
- ._extract_numeric_candidates() `EXTRACTED`
- .merge_ocr_results() `EXTRACTED`
- .__init__() `EXTRACTED`

### rationale_for
- Handles RapidOCR and post-processing for MMR number detection. `EXTRACTED`

### references
- _number_route() `EXTRACTED`
- .__init__() `EXTRACTED`

### uses
- PipelineOrchestrator `INFERRED`
- TestMMROCRHeuristics `INFERRED`
- _TargetedHarness `INFERRED`
- MaskedEmptyUnmaskedNumberOCR `INFERRED`
- _RecordingRapidOCR `INFERRED`
- CurrentEmptyLeftWideNumberOCR `INFERRED`
- OneEvidencePerVariantOCR `INFERRED`
- _TargetedRetryOCR `INFERRED`
- MaskedNumberUnmaskedDifferentNumberOCR `INFERRED`
- RaisesOnEmptyCropOCR `INFERRED`
- _ReviewPackageConfig `INFERRED`
- CurrentEmptyLeftWideLowScoreOCR `INFERRED`
- MaskedEmptyUnmaskedLowScoreOCR `INFERRED`
- CustomInjectedEngine `INFERRED`
- ProviderOCR `INFERRED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*