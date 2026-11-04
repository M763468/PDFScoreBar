# MMRProcessor

> God node · 68 connections · `src/measure_numbering/mmr.py`

**Community:** [Community 0](Community_0.md)

## Connections by Relation

### calls
- run_mmr_batch() `EXTRACTED`
- run() `EXTRACTED`
- run_legacy() `EXTRACTED`
- run() `EXTRACTED`
- main() `EXTRACTED`
- run_h2_matrix() `EXTRACTED`
- _processor() `EXTRACTED`
- run_mmr_batch() `EXTRACTED`
- test_ocr_candidate_scoring_receives_processed_dimensions() `EXTRACTED`
- test_detect_number_uses_best_scored_variant_not_first_valid_variant() `EXTRACTED`
- test_detect_number_preserves_three_value_contract() `EXTRACTED`
- test_detect_number_uses_max_one_bar_evidence_across_variants_not_sum() `EXTRACTED`
- test_one_bar_veto_targets_marginal_cnn_negative_ocr_score_only() `EXTRACTED`
- main() `EXTRACTED`
- test_count_one_bar_evidence_is_compatible_with_minimal_injected_ocr() `EXTRACTED`
- .test_narrow_measure_keeps_valid_staff_reading_in_masked_and_fallback_paths() `EXTRACTED`
- .test_narrow_measure_tie_preserves_admissible_leader() `EXTRACTED`
- .test_staff_majority_is_primary_even_when_minority_score_is_higher() `EXTRACTED`
- .test_staff_tie_only_compares_leaders_and_preserves_low_cnn_policy() `EXTRACTED`
- .test_staff_tie_prefers_spatial_score_without_staff_order_bias() `EXTRACTED`

### contains
- mmr.py `EXTRACTED`

### imports
- audit_positive_geometry_disagreements.py `EXTRACTED`
- steps/numbering.py `EXTRACTED`
- test_issue274_mmr_support_reuse.py `EXTRACTED`
- diagnose_ocr_frame_changed_pages.py `EXTRACTED`
- run_representative_mmr_reuse.py `EXTRACTED`
- test_issue212_mmr_unmasked_fallback.py `EXTRACTED`
- test_issue213_mmr_one_bar_veto.py `EXTRACTED`
- test_mmr_ocr_heuristics.py `EXTRACTED`
- generate_numbering_overrides.py `EXTRACTED`
- test_issue208_mmr_variant_aggregation.py `EXTRACTED`

### method
- ._detect_number_with_evidence() `EXTRACTED`
- ._process_page_with_support() `EXTRACTED`
- .process_pages() `EXTRACTED`
- ._detect_number_with_evidence_once() `EXTRACTED`
- ._run_calibrated_shifted_staff_values() `EXTRACTED`
- ._select_variant_result() `EXTRACTED`
- .__init__() `EXTRACTED`
- ._detect_number_with_evidence_j2() `EXTRACTED`
- ._should_veto_one_bar_rest() `EXTRACTED`
- ._targeted_shift_x1() `EXTRACTED`
- ._aggregate_targeted_staff_results() `EXTRACTED`
- ._select_staff_value() `EXTRACTED`
- ._draw_debug() `EXTRACTED`
- ._count_high_confidence_one_bar_evidence() `EXTRACTED`
- ._valid_status() `EXTRACTED`
- ._native_inset_bbox() `EXTRACTED`
- ._targeted_retry_candidate_acceptable() `EXTRACTED`
- ._run_targeted_full_span_staff() `EXTRACTED`
- ._run_targeted_shifted_staff() `EXTRACTED`
- ._support_view() `EXTRACTED`

### rationale_for
- Integrated processor for batch MMR detection. `EXTRACTED`

### uses
- TestMMROCRHeuristics `INFERRED`
- _TargetedHarness `INFERRED`
- MaskedEmptyUnmaskedNumberOCR `INFERRED`
- _TargetedRetryOCR `INFERRED`
- _RecordingRapidOCR `INFERRED`
- CurrentEmptyLeftWideNumberOCR `INFERRED`
- OneEvidencePerVariantOCR `INFERRED`
- MaskedNumberUnmaskedDifferentNumberOCR `INFERRED`
- VariantOCR `INFERRED`
- RaisesOnEmptyCropOCR `INFERRED`
- _FixedClassifier `INFERRED`
- _ScriptedProcessor `INFERRED`
- CurrentEmptyLeftWideLowScoreOCR `INFERRED`
- MaskedEmptyUnmaskedLowScoreOCR `INFERRED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*