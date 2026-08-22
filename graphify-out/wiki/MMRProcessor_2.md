# MMRProcessor

> God node · 50 connections · `src/measure_numbering/mmr.py`

**Community:** [MMRProcessor](MMRProcessor.md)

## Connections by Relation

### calls
- run_mmr_batch() `EXTRACTED`
- run() `EXTRACTED`
- run_legacy() `EXTRACTED`
- run() `EXTRACTED`
- [main()](main%28%29.md) `EXTRACTED`
- run_h2_matrix() `EXTRACTED`
- _processor() `EXTRACTED`
- run_mmr_batch() `EXTRACTED`
- test_detect_number_uses_best_scored_variant_not_first_valid_variant() `EXTRACTED`
- test_detect_number_preserves_three_value_contract() `EXTRACTED`
- test_detect_number_uses_max_one_bar_evidence_across_variants_not_sum() `EXTRACTED`
- test_one_bar_veto_targets_marginal_cnn_negative_ocr_score_only() `EXTRACTED`
- test_ocr_candidate_scoring_receives_processed_dimensions() `EXTRACTED`
- [main()](main%28%29.md) `EXTRACTED`
- test_count_one_bar_evidence_is_compatible_with_minimal_injected_ocr() `EXTRACTED`

### contains
- mmr.py `EXTRACTED`

### imports
- [audit_positive_geometry_disagreements.py](audit_positive_geometry_disagreements.py.md) `EXTRACTED`
- [test_issue274_mmr_support_reuse.py](test_issue274_mmr_support_reuse.py.md) `EXTRACTED`
- steps/numbering.py `EXTRACTED`
- [diagnose_ocr_frame_changed_pages.py](diagnose_ocr_frame_changed_pages.py.md) `EXTRACTED`
- run_representative_mmr_reuse.py `EXTRACTED`
- [test_issue212_mmr_unmasked_fallback.py](test_issue212_mmr_unmasked_fallback.py.md) `EXTRACTED`
- test_issue213_mmr_one_bar_veto.py `EXTRACTED`
- test_mmr_ocr_heuristics.py `EXTRACTED`
- generate_numbering_overrides.py `EXTRACTED`
- test_issue208_mmr_variant_aggregation.py `EXTRACTED`

### method
- ._process_page_with_support() `EXTRACTED`
- .process_pages() `EXTRACTED`
- ._detect_number_with_evidence() `EXTRACTED`
- .__init__() `EXTRACTED`
- ._should_veto_one_bar_rest() `EXTRACTED`
- ._count_high_confidence_one_bar_evidence() `EXTRACTED`
- ._valid_status() `EXTRACTED`
- ._detect_number_with_evidence_once() `EXTRACTED`
- ._draw_debug() `EXTRACTED`
- ._support_view() `EXTRACTED`
- ._detect_number() `EXTRACTED`

### rationale_for
- Integrated processor for batch MMR detection. `EXTRACTED`

### uses
- [TestMMROCRHeuristics](TestMMROCRHeuristics.md) `INFERRED`
- MaskedEmptyUnmaskedNumberOCR `INFERRED`
- _RecordingRapidOCR `INFERRED`
- CurrentEmptyLeftWideNumberOCR `INFERRED`
- OneEvidencePerVariantOCR `INFERRED`
- MaskedNumberUnmaskedDifferentNumberOCR `INFERRED`
- _FixedClassifier `INFERRED`
- _ScriptedProcessor `INFERRED`
- VariantOCR `INFERRED`
- RaisesOnEmptyCropOCR `INFERRED`
- CurrentEmptyLeftWideLowScoreOCR `INFERRED`
- MaskedEmptyUnmaskedLowScoreOCR `INFERRED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*