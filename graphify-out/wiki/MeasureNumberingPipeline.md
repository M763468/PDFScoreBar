# MeasureNumberingPipeline

> 39 nodes · cohesion 0.13

## Key Concepts

- **MeasureNumberingPipeline** (43 connections) — `src/measure_numbering/pipeline.py`
- **Score** (40 connections) — `src/measure_numbering/types.py`
- **evaluate_barline_rules.py** (30 connections) — `tools/evaluate_barline_rules.py`
- **main()** (18 connections) — `tools/evaluate_barline_rules.py`
- **.process_page()** (11 connections) — `src/measure_numbering/pipeline.py`
- **Box** (10 connections)
- **_metrics()** (8 connections) — `tools/evaluate_barline_rules.py`
- **Path** (8 connections)
- **greedy_match_by_rule()** (7 connections) — `tools/evaluate_barline_rules.py`
- **_measure_count_for_boxes()** (6 connections) — `tools/evaluate_barline_rules.py`
- **._connector_evidence_staves()** (5 connections) — `src/measure_numbering/pipeline.py`
- **barline_ioa()** (5 connections) — `tools/evaluate_barline_rules.py`
- **_measure_iou_2d()** (5 connections) — `tools/evaluate_barline_rules.py`
- **_measure_local_kpis()** (5 connections) — `tools/evaluate_barline_rules.py`
- **.run_sequential()** (4 connections) — `src/measure_numbering/pipeline.py`
- **Path** (4 connections)
- **.extract()** (4 connections) — `src/measure_numbering/pipeline.py`
- **_box_area()** (4 connections) — `tools/evaluate_barline_rules.py`
- **_intersection_area()** (4 connections) — `tools/evaluate_barline_rules.py`
- **load_gt_boxes()** (4 connections) — `tools/evaluate_barline_rules.py`
- **parse_scored_context()** (4 connections) — `tools/evaluate_barline_rules.py`
- **RuleResult** (4 connections) — `tools/evaluate_barline_rules.py`
- **._image_to_connector_mask()** (3 connections) — `src/measure_numbering/pipeline.py`
- **center_distance_x()** (3 connections) — `tools/evaluate_barline_rules.py`
- **find_gt_file()** (3 connections) — `tools/evaluate_barline_rules.py`
- *... and 14 more nodes in this community*

## Relationships

- [Staff](Staff.md) (24 shared connections)
- [diagnose_phase_b_layout_divergence.py](diagnose_phase_b_layout_divergence.py.md) (10 shared connections)
- [get_nested](get_nested.md) (6 shared connections)
- [load_json](load_json.md) (5 shared connections)
- [MeasureNumberer](MeasureNumberer.md) (5 shared connections)
- [SystemBuilder](SystemBuilder.md) (4 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (4 shared connections)
- [StaffExtractor](StaffExtractor.md) (4 shared connections)
- [barline_evaluation.py](barline_evaluation.py.md) (4 shared connections)
- [BBox](BBox.md) (3 shared connections)
- [test_issue254_connector_artifact_contract.py](test_issue254_connector_artifact_contract.py.md) (2 shared connections)
- [test_issue264_phase_a_connector_geometry.py](test_issue264_phase_a_connector_geometry.py.md) (2 shared connections)

## Source Files

- `src/measure_numbering/pipeline.py`
- `src/measure_numbering/types.py`
- `tools/evaluate_barline_rules.py`

## Audit Trail

- EXTRACTED: 157 (89%)
- INFERRED: 20 (11%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*