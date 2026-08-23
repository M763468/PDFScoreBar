# MeasureNumberingPipeline

> 24 nodes · cohesion 0.13

## Key Concepts

- **MeasureNumberingPipeline** (43 connections) — `src/measure_numbering/pipeline.py`
- **score_to_dict()** (17 connections) — `src/measure_numbering/serialization.py`
- **.process_page()** (11 connections) — `src/measure_numbering/pipeline.py`
- **serialization.py** (9 connections) — `src/measure_numbering/serialization.py`
- **tools/add_measure_numbers.py** (9 connections) — `tools/add_measure_numbers.py`
- **main()** (6 connections) — `tools/add_measure_numbers.py`
- **render_overlay()** (6 connections) — `tools/add_measure_numbers.py`
- **._connector_evidence_staves()** (5 connections) — `src/measure_numbering/pipeline.py`
- **.run_sequential()** (4 connections) — `src/measure_numbering/pipeline.py`
- **Path** (4 connections)
- **.extract()** (4 connections) — `src/measure_numbering/pipeline.py`
- **._image_to_connector_mask()** (3 connections) — `src/measure_numbering/pipeline.py`
- **ndarray** (2 connections)
- **Staff** (2 connections)
- **_serialize_measure()** (2 connections) — `src/measure_numbering/serialization.py`
- **_serialize_staves()** (2 connections) — `src/measure_numbering/serialization.py`
- **.test_pipeline_uses_connector_aware_builder_by_default()** (2 connections) — `tests/test_issue197_system_grouping_connector_evidence.py`
- **normalize_barlines()** (2 connections) — `tools/add_measure_numbers.py`
- **Any** (1 connections)
- **Measure semantic masks against the staff geometry from the same producer. The…** (1 connections) — `src/measure_numbering/pipeline.py`
- **Integrated pipeline to assign measure numbers to a score.** (1 connections) — `src/measure_numbering/pipeline.py`
- **Serialization helpers for measure numbering results.** (1 connections) — `src/measure_numbering/serialization.py`
- **Convert a Score object tree into the numbering JSON contract.** (1 connections) — `src/measure_numbering/serialization.py`
- **Path** (1 connections)

## Relationships

- [Staff](Staff.md) (19 shared connections)
- [diagnose_phase_b_layout_divergence.py](diagnose_phase_b_layout_divergence.py.md) (6 shared connections)
- [.run](run.md) (5 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (5 shared connections)
- [SystemBuilder](SystemBuilder.md) (4 shared connections)
- [evaluate_barline_rules.py](evaluate_barline_rules.py.md) (4 shared connections)
- [phase_b_page001_acceptance.py](phase_b_page001_acceptance.py.md) (4 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (3 shared connections)
- [StaffExtractor](StaffExtractor.md) (3 shared connections)
- [BBox](BBox.md) (3 shared connections)
- [test_issue254_connector_artifact_contract.py](test_issue254_connector_artifact_contract.py.md) (2 shared connections)
- [test_issue264_phase_a_connector_geometry.py](test_issue264_phase_a_connector_geometry.py.md) (2 shared connections)

## Source Files

- `src/measure_numbering/pipeline.py`
- `src/measure_numbering/serialization.py`
- `tests/test_issue197_system_grouping_connector_evidence.py`
- `tools/add_measure_numbers.py`

## Audit Trail

- EXTRACTED: 87 (85%)
- INFERRED: 15 (15%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*