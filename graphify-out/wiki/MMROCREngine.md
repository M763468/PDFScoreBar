# MMROCREngine

> God node · 68 connections · `src/measure_numbering/mmr.py`

**Community:** [Community 172](Community_172.md)

## Connections by Relation

### calls
- run_mmr_batch() `EXTRACTED`
- run() `EXTRACTED`
- run_legacy() `EXTRACTED`
- main() `EXTRACTED`
- main() `EXTRACTED`
- run() `EXTRACTED`
- main() `EXTRACTED`
- run_h2_matrix() `EXTRACTED`
- _representative_report() `EXTRACTED`
- run_mmr_batch_detection() `EXTRACTED`
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
- audit_positive_geometry_disagreements.py `EXTRACTED`
- steps/numbering.py `EXTRACTED`
- run_grouped_final_numbering_comparison.py `EXTRACTED`
- run_full68_mmr_reuse.py `EXTRACTED`
- run_original_geometry_graft.py `EXTRACTED`
- diagnose_ocr_frame_changed_pages.py `EXTRACTED`
- run_representative_mmr_reuse.py `EXTRACTED`
- test_issue212_mmr_unmasked_fallback.py `EXTRACTED`
- numbering_phases.py `EXTRACTED`
- test_issue213_mmr_one_bar_veto.py `EXTRACTED`
- test_pipeline_numbering_mmr_provider.py `EXTRACTED`
- test_mmr_ocr_heuristics.py `EXTRACTED`

### method
- .collect_one_bar_evidence() `EXTRACTED`
- ._candidate_items() `EXTRACTED`
- ._hbar_mask_geometry() `EXTRACTED`
- .mask_hbar_candidates_calibrated() `EXTRACTED`
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
- TestMMROCRHeuristics `INFERRED`
- _TargetedHarness `INFERRED`
- MaskedEmptyUnmaskedNumberOCR `INFERRED`
- _TargetedRetryOCR `INFERRED`
- _RecordingRapidOCR `INFERRED`
- CurrentEmptyLeftWideNumberOCR `INFERRED`
- OneEvidencePerVariantOCR `INFERRED`
- NumberingPhaseServices `INFERRED`
- MaskedNumberUnmaskedDifferentNumberOCR `INFERRED`
- RaisesOnEmptyCropOCR `INFERRED`
- CurrentEmptyLeftWideLowScoreOCR `INFERRED`
- MaskedEmptyUnmaskedLowScoreOCR `INFERRED`
- CustomInjectedEngine `INFERRED`
- ProviderOCR `INFERRED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*