# Barline

> God node · 68 connections · `src/measure_numbering/types.py`

**Community:** [Community 10](Community_10.md)

## Connections by Relation

### calls
- .number_system() `EXTRACTED`
- .process_page() `EXTRACTED`
- .create_system() `EXTRACTED`
- .make_barlines() `EXTRACTED`
- test_empty_reviewed_output_removes_source_reset_from_corrected_numbering() `EXTRACTED`
- run_verification() `EXTRACTED`
- run_visualization() `EXTRACTED`
- test_actual_model_outputs_preserve_every_voice_and_shared_boundaries() `EXTRACTED`
- music() `EXTRACTED`
- test_visibility_uses_constructed_measures_not_barline_count_or_stale_measures() `EXTRACTED`
- .create_mock_score() `EXTRACTED`
- .apply() `EXTRACTED`
- scan() `EXTRACTED`
- .make_numbered_system() `EXTRACTED`
- build() `EXTRACTED`
- test_issue268_numberer_boundary_reset_precedes_existing_set_number_override() `EXTRACTED`
- test_multistaff_boundary_needs_staff_span_or_cross_staff_support() `EXTRACTED`
- _one_page() `EXTRACTED`
- system() `EXTRACTED`
- .test_score_flow() `EXTRACTED`

### contains
- measure_numbering/types.py `EXTRACTED`

### imports
- test_issue415_numbering_audit.py `EXTRACTED`
- pipeline.py `EXTRACTED`
- test_issue257_mmr_page_rebase.py `EXTRACTED`
- test_issue218_multistaff_system_grouping.py `EXTRACTED`
- test_reviewed_movement_apply.py `EXTRACTED`
- test_issue413_system_identity.py `EXTRACTED`
- measure_numbering/numbering.py `EXTRACTED`
- test_numbering_geometry_scale.py `EXTRACTED`
- test_clipped_system_end.py `EXTRACTED`
- test_numbering_overrides.py `EXTRACTED`
- builder.py `EXTRACTED`
- verify_measure_numbering_pipeline.py `EXTRACTED`
- visualize_measure_numbering.py `EXTRACTED`
- test_issue217_empty_system_output_contract.py `EXTRACTED`
- test_measure_numbering_numbering.py `EXTRACTED`
- test_issue197_system_grouping_connector_evidence.py `EXTRACTED`
- verify_divisi_batch.py `EXTRACTED`
- clipped_end.py `EXTRACTED`
- test_issue194_first_interval_guard.py `EXTRACTED`
- visualize_measure_systems.py `EXTRACTED`

### rationale_for
- Represents a vertical barline detected in the score. `EXTRACTED`

### references
- .build_systems() `EXTRACTED`
- ._check_aligned_connection() `EXTRACTED`
- process_page() `EXTRACTED`
- load_local_gt() `EXTRACTED`
- ._assign_barlines_to_staves() `EXTRACTED`
- ._find_aligned_pairs() `EXTRACTED`
- ._deduplicate_barlines() `EXTRACTED`
- ._is_narrow_ghost_start_interval() `EXTRACTED`
- ._measure_interval_widths() `EXTRACTED`

### uses
- [MeasureNumberer](MeasureNumberer.md) `INFERRED`
- MeasureNumberingPipeline `INFERRED`
- StaffExtractor `INFERRED`
- SystemBuilder `INFERRED`
- ClippedSystemEndDetector `INFERRED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*