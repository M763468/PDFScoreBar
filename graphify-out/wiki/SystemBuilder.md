# SystemBuilder

> 29 nodes · cohesion 0.20

## Key Concepts

- **SystemBuilder** (35 connections) — `src/measure_numbering/builder.py`
- **TestIssue197SystemGroupingConnectorEvidence** (20 connections) — `tests/test_issue197_system_grouping_connector_evidence.py`
- **.make_staff_pair()** (12 connections) — `tests/test_issue197_system_grouping_connector_evidence.py`
- **._group_by_geometry()** (10 connections) — `src/measure_numbering/builder.py`
- **.make_barlines()** (10 connections) — `tests/test_issue197_system_grouping_connector_evidence.py`
- **.build_systems()** (9 connections) — `src/measure_numbering/builder.py`
- **.make_connection_image()** (8 connections) — `tests/test_issue197_system_grouping_connector_evidence.py`
- **Staff** (6 connections)
- **Any** (5 connections)
- **._check_aligned_connection()** (5 connections) — `src/measure_numbering/builder.py`
- **.test_connector_density_schema_is_accepted()** (5 connections) — `tests/test_issue197_system_grouping_connector_evidence.py`
- **.test_connector_evidence_rescues_near_threshold_false_split()** (5 connections) — `tests/test_issue197_system_grouping_connector_evidence.py`
- **.test_high_alignment_connection_with_explicit_no_connector_is_guarded()** (5 connections) — `tests/test_issue197_system_grouping_connector_evidence.py`
- **.test_low_alignment_connection_with_explicit_no_connector_is_guarded()** (5 connections) — `tests/test_issue197_system_grouping_connector_evidence.py`
- **.test_low_alignment_connection_without_connector_evidence_keeps_legacy_merge()** (5 connections) — `tests/test_issue197_system_grouping_connector_evidence.py`
- **.test_near_threshold_pair_is_not_rescued_without_connector_evidence()** (5 connections) — `tests/test_issue197_system_grouping_connector_evidence.py`
- **Barline** (4 connections)
- **._assign_barlines_to_staves()** (4 connections) — `src/measure_numbering/builder.py`
- **._find_aligned_pairs()** (4 connections) — `src/measure_numbering/builder.py`
- **._group_by_index()** (4 connections) — `src/measure_numbering/builder.py`
- **._normalize_connector_evidence()** (4 connections) — `src/measure_numbering/builder.py`
- **.test_connector_evidence_rescues_with_image_without_internal_bridge()** (4 connections) — `tests/test_issue197_system_grouping_connector_evidence.py`
- **.test_pipeline_page_image_fallback_can_generate_connector_evidence()** (4 connections) — `tests/test_issue197_system_grouping_connector_evidence.py`
- **ndarray** (3 connections)
- **._has_left_connector_evidence()** (3 connections) — `src/measure_numbering/builder.py`
- *... and 4 more nodes in this community*

## Relationships

- [Staff](Staff.md) (20 shared connections)
- [BBox](BBox.md) (6 shared connections)
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) (4 shared connections)
- [StaffExtractor](StaffExtractor.md) (3 shared connections)
- [MMROCREngine](MMROCREngine.md) (1 shared connections)

## Source Files

- `src/measure_numbering/builder.py`
- `tests/test_issue197_system_grouping_connector_evidence.py`

## Audit Trail

- EXTRACTED: 95 (83%)
- INFERRED: 19 (17%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*