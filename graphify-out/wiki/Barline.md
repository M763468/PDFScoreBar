# Barline

> God node · 49 connections · `src/measure_numbering/types.py`

**Community:** [Community 10](Community_10.md)

## Connections by Relation

### calls
- .number_system() `EXTRACTED`
- .process_page() `EXTRACTED`
- .create_system() `EXTRACTED`
- .make_barlines() `EXTRACTED`
- run_verification() `EXTRACTED`
- run_visualization() `EXTRACTED`
- .create_mock_score() `EXTRACTED`
- .make_numbered_system() `EXTRACTED`
- .test_score_flow() `EXTRACTED`
- _one_page() `EXTRACTED`
- .test_single_system_flow() `EXTRACTED`
- [main()](main%28%29.md) `EXTRACTED`
- load_barlines() `EXTRACTED`

### contains
- measure_numbering/types.py `EXTRACTED`

### imports
- pipeline.py `EXTRACTED`
- test_issue257_mmr_page_rebase.py `EXTRACTED`
- measure_numbering/numbering.py `EXTRACTED`
- verify_measure_numbering_pipeline.py `EXTRACTED`
- visualize_measure_numbering.py `EXTRACTED`
- builder.py `EXTRACTED`
- test_issue217_empty_system_output_contract.py `EXTRACTED`
- test_numbering.py `EXTRACTED`
- test_numbering_overrides.py `EXTRACTED`
- test_issue197_system_grouping_connector_evidence.py `EXTRACTED`
- verify_divisi_batch.py `EXTRACTED`
- visualize_systems.py `EXTRACTED`
- test_issue194_first_interval_guard.py `EXTRACTED`
- debug_end_bar_removal.py `EXTRACTED`

### rationale_for
- Represents a vertical barline detected in the score. `EXTRACTED`

### references
- .build_systems() `EXTRACTED`
- load_local_gt() `EXTRACTED`
- process_page() `EXTRACTED`
- ._check_aligned_connection() `EXTRACTED`
- ._assign_barlines_to_staves() `EXTRACTED`
- ._find_aligned_pairs() `EXTRACTED`
- ._deduplicate_barlines() `EXTRACTED`
- ._is_narrow_ghost_start_interval() `EXTRACTED`
- ._measure_interval_widths() `EXTRACTED`

### uses
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) `INFERRED`
- SystemBuilder `INFERRED`
- MeasureNumberer `INFERRED`
- StaffExtractor `INFERRED`
- TestIssue197SystemGroupingConnectorEvidence `INFERRED`
- TestIssue194FirstIntervalGuard `INFERRED`
- TestIssue217EmptySystemOutputContract `INFERRED`
- TestNumberingOverrides `INFERRED`
- TestMeasureNumberer `INFERRED`
- _FakeNumberingPipeline `INFERRED`
- _FakeImage `INFERRED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*