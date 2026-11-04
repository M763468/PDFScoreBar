# MeasureNumberer

> God node · 60 connections · `src/measure_numbering/numbering.py`

**Community:** [Community 10](Community_10.md)

## Connections by Relation

### calls
- test_empty_reviewed_output_removes_source_reset_from_corrected_numbering() `EXTRACTED`
- run_verification() `EXTRACTED`
- run_visualization() `EXTRACTED`
- test_actual_model_outputs_preserve_every_voice_and_shared_boundaries() `EXTRACTED`
- test_visibility_uses_constructed_measures_not_barline_count_or_stale_measures() `EXTRACTED`
- test_real_manual_precedence_then_numbering_with_empty_system_and_terminal_rest() `EXTRACTED`
- test_issue268_numberer_boundary_reset_precedes_existing_set_number_override() `EXTRACTED`
- test_empty_predictions_and_multiple_pages_preserve_continuity() `EXTRACTED`
- test_overrides_address_same_physical_system_as_compact_json() `EXTRACTED`
- test_real_manual_span_and_movement_reset_keep_page_identity() `EXTRACTED`
- test_multistaff_boundary_needs_staff_span_or_cross_staff_support() `EXTRACTED`
- .__init__() `EXTRACTED`
- test_transitive_divisi_merge_preserves_neighbor_and_measure_progression() `EXTRACTED`
- test_movement_reset_and_set_number_share_compact_identity() `EXTRACTED`
- test_clipped_scan_counts_shared_last_interval_once_and_preserves_mmr() `EXTRACTED`
- test_pipeline_extracts_pair_evidence_and_numbers_divisi_once() `EXTRACTED`
- test_missing_image_does_not_infer_end_from_staff_bbox() `EXTRACTED`
- .setUp() `EXTRACTED`
- .__init__() `EXTRACTED`
- .setUp() `EXTRACTED`

### contains
- measure_numbering/numbering.py `EXTRACTED`

### imports
- test_issue415_numbering_audit.py `EXTRACTED`
- pipeline.py `EXTRACTED`
- test_issue257_mmr_page_rebase.py `EXTRACTED`
- test_issue218_multistaff_system_grouping.py `EXTRACTED`
- test_reviewed_movement_apply.py `EXTRACTED`
- test_issue413_system_identity.py `EXTRACTED`
- test_clipped_system_end.py `EXTRACTED`
- test_numbering_overrides.py `EXTRACTED`
- verify_measure_numbering_pipeline.py `EXTRACTED`
- visualize_measure_numbering.py `EXTRACTED`
- test_measure_numbering_numbering.py `EXTRACTED`
- test_issue194_first_interval_guard.py `EXTRACTED`

### method
- .number_system() `EXTRACTED`
- ._system_unit_size() `EXTRACTED`
- ._supported_multistaff_barlines() `EXTRACTED`
- .number_score() `EXTRACTED`
- ._is_narrow_ghost_start_interval() `EXTRACTED`
- ._deduplicate_barlines() `EXTRACTED`
- ._measure_interval_widths() `EXTRACTED`
- ._median() `EXTRACTED`

### rationale_for
- Assigns measure numbers to systems of music. `EXTRACTED`

### uses
- [BBox](BBox.md) `INFERRED`
- [Barline](Barline.md) `INFERRED`
- [Score](Score.md) `INFERRED`
- MeasureNumberingPipeline `INFERRED`
- System `INFERRED`
- StaffExtractor `INFERRED`
- TestNumberingOverrides `INFERRED`
- TestIssue194FirstIntervalGuard `INFERRED`
- Measure `INFERRED`
- _FakeNumberingPipeline `INFERRED`
- MeasureAttribute `INFERRED`
- _EmptySystemMixin `INFERRED`
- _FakeImage `INFERRED`
- _FakeTwoSystemNumberingPipeline `INFERRED`
- TestMeasureNumberer `INFERRED`
- _FakeEmptyNumberingPipeline `INFERRED`
- _FakeEmptyTwoSystemNumberingPipeline `INFERRED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*