# MeasureNumberingPipeline

> God node · 43 connections · `src/measure_numbering/pipeline.py`

**Community:** [Community 26](Community_26.md)

## Connections by Relation

### calls
- [main()](main%28%29.md) `EXTRACTED`
- .run_base_numbering_and_barline_correction() `EXTRACTED`
- .run_final_numbering_and_overlays() `EXTRACTED`
- _number_route() `EXTRACTED`
- run() `EXTRACTED`
- test_numbering_uses_semantic_staff_geometry_only_for_connector_rois() `EXTRACTED`
- _rebuild() `EXTRACTED`
- [main()](main%28%29.md) `EXTRACTED`
- test_numbering_auto_resolves_connector_masks_from_staff_mask_siblings() `EXTRACTED`
- .test_pipeline_page_image_fallback_can_generate_connector_evidence() `EXTRACTED`
- .test_positive_only_fallback_omits_absent_pairs() `EXTRACTED`
- .test_pipeline_uses_connector_aware_builder_by_default() `EXTRACTED`

### contains
- pipeline.py `EXTRACTED`

### imports
- pipeline/orchestrator.py `EXTRACTED`
- run_grouped_final_numbering_comparison.py `EXTRACTED`
- evaluate_barline_rules.py `EXTRACTED`
- test_issue254_connector_artifact_contract.py `EXTRACTED`
- phase_b_page001_acceptance.py `EXTRACTED`
- diagnose_phase_b_layout_divergence.py `EXTRACTED`
- test_issue264_phase_a_connector_geometry.py `EXTRACTED`
- test_issue197_system_grouping_connector_evidence.py `EXTRACTED`
- tools/add_measure_numbers.py `EXTRACTED`

### method
- .process_page() `EXTRACTED`
- ._connector_evidence_staves() `EXTRACTED`
- .__init__() `EXTRACTED`
- .run_sequential() `EXTRACTED`
- ._image_to_connector_mask() `EXTRACTED`

### rationale_for
- Integrated pipeline to assign measure numbers to a score. `EXTRACTED`

### references
- build_numbering() `EXTRACTED`
- _measure_count_for_boxes() `EXTRACTED`
- _page_image_ink_evidence() `EXTRACTED`

### uses
- [Staff](Staff.md) `INFERRED`
- [BBox](BBox.md) `INFERRED`
- [Barline](Barline.md) `INFERRED`
- Score `INFERRED`
- PipelineOrchestrator `INFERRED`
- MeasureNumberer `INFERRED`
- Page `INFERRED`
- SystemConnectorEvidenceExtractor `INFERRED`
- TestIssue197SystemGroupingConnectorEvidence `INFERRED`
- ConnectorAwareSystemBuilder `INFERRED`
- _ReviewPackageConfig `INFERRED`
- RuleResult `INFERRED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*