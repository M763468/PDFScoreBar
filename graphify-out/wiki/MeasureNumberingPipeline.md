# MeasureNumberingPipeline

> 13 nodes · cohesion 0.24

## Key Concepts

- **MeasureNumberingPipeline** (43 connections) — `src/measure_numbering/pipeline.py`
- **.process_page()** (11 connections) — `src/measure_numbering/pipeline.py`
- **._connector_evidence_staves()** (5 connections) — `src/measure_numbering/pipeline.py`
- **.run_sequential()** (4 connections) — `src/measure_numbering/pipeline.py`
- **Path** (4 connections)
- **.extract()** (4 connections) — `src/measure_numbering/pipeline.py`
- **._image_to_connector_mask()** (3 connections) — `src/measure_numbering/pipeline.py`
- **ndarray** (2 connections)
- **Staff** (2 connections)
- **.test_pipeline_uses_connector_aware_builder_by_default()** (2 connections) — `tests/test_issue197_system_grouping_connector_evidence.py`
- **Any** (1 connections)
- **Measure semantic masks against the staff geometry from the same producer. The…** (1 connections) — `src/measure_numbering/pipeline.py`
- **Integrated pipeline to assign measure numbers to a score.** (1 connections) — `src/measure_numbering/pipeline.py`

## Relationships

- [Staff](Staff.md) (8 shared connections)
- [SystemBuilder](SystemBuilder.md) (4 shared connections)
- [Score](Score.md) (4 shared connections)
- [evaluate_barline_rules.py](evaluate_barline_rules.py.md) (4 shared connections)
- [diagnose_phase_b_layout_divergence.py](diagnose_phase_b_layout_divergence.py.md) (3 shared connections)
- [phase_b_page001_acceptance.py](phase_b_page001_acceptance.py.md) (3 shared connections)
- [StaffExtractor](StaffExtractor.md) (3 shared connections)
- [BBox](BBox.md) (3 shared connections)
- [.run](run.md) (2 shared connections)
- [test_issue254_connector_artifact_contract.py](test_issue254_connector_artifact_contract.py.md) (2 shared connections)
- [test_issue264_phase_a_connector_geometry.py](test_issue264_phase_a_connector_geometry.py.md) (2 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (2 shared connections)

## Source Files

- `src/measure_numbering/pipeline.py`
- `tests/test_issue197_system_grouping_connector_evidence.py`

## Audit Trail

- EXTRACTED: 52 (81%)
- INFERRED: 12 (19%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*