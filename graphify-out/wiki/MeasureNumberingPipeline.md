# MeasureNumberingPipeline

> 29 nodes · cohesion 0.13

## Key Concepts

- **MeasureNumberingPipeline** (43 connections) — `src/measure_numbering/pipeline.py`
- **phase_b_page001_acceptance.py** (23 connections) — `tools/issue264/phase_b_page001_acceptance.py`
- **run()** (14 connections) — `tools/issue264/phase_b_page001_acceptance.py`
- **.process_page()** (11 connections) — `src/measure_numbering/pipeline.py`
- **barlines.py** (11 connections) — `src/pipeline/steps/barlines.py`
- **build_numbering()** (10 connections) — `tools/issue264/phase_b_page001_acceptance.py`
- **normalize_barlines()** (9 connections) — `src/pipeline/steps/barlines.py`
- **test_issue264_phase_b_manifest.py** (6 connections) — `tests/test_issue264_phase_b_manifest.py`
- **target_manifest_entry()** (6 connections) — `tools/issue264/phase_b_page001_acceptance.py`
- **._connector_evidence_staves()** (5 connections) — `src/measure_numbering/pipeline.py`
- **apply_barline_overrides()** (5 connections) — `src/pipeline/steps/barlines.py`
- **.run_sequential()** (4 connections) — `src/measure_numbering/pipeline.py`
- **Path** (4 connections)
- **.extract()** (4 connections) — `src/measure_numbering/pipeline.py`
- **Any** (4 connections)
- **Path** (4 connections)
- **._image_to_connector_mask()** (3 connections) — `src/measure_numbering/pipeline.py`
- **override_triples()** (3 connections) — `tools/issue264/phase_b_page001_acceptance.py`
- **physical_counts()** (3 connections) — `tools/issue264/phase_b_page001_acceptance.py`
- **sha256()** (3 connections) — `tools/issue264/phase_b_page001_acceptance.py`
- **ndarray** (2 connections)
- **Staff** (2 connections)
- **Any** (2 connections)
- **.test_pipeline_uses_connector_aware_builder_by_default()** (2 connections) — `tests/test_issue197_system_grouping_connector_evidence.py`
- **test_acceptance_target_entry_supports_composite_stem()** (2 connections) — `tests/test_issue264_phase_b_manifest.py`
- *... and 4 more nodes in this community*

## Relationships

- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (9 shared connections)
- [Staff](Staff.md) (9 shared connections)
- [load_json](load_json.md) (8 shared connections)
- [Score](Score.md) (7 shared connections)
- [diagnose_phase_b_layout_divergence.py](diagnose_phase_b_layout_divergence.py.md) (6 shared connections)
- [get_nested](get_nested.md) (5 shared connections)
- [SystemBuilder](SystemBuilder.md) (4 shared connections)
- [evaluate_barline_rules.py](evaluate_barline_rules.py.md) (4 shared connections)
- [StaffExtractor](StaffExtractor.md) (3 shared connections)
- [BBox](BBox.md) (3 shared connections)
- [PipelineOrchestrator](PipelineOrchestrator.md) (3 shared connections)
- [manual_corrections.py](manual_corrections.py.md) (3 shared connections)

## Source Files

- `src/measure_numbering/pipeline.py`
- `src/pipeline/steps/barlines.py`
- `tests/test_issue197_system_grouping_connector_evidence.py`
- `tests/test_issue264_phase_b_manifest.py`
- `tools/issue264/phase_b_page001_acceptance.py`

## Audit Trail

- EXTRACTED: 123 (90%)
- INFERRED: 13 (10%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*