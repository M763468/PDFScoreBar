# MeasureNumberingPipeline

> 28 nodes · cohesion 0.19

## Key Concepts

- **MeasureNumberingPipeline** (34 connections) — `src/measure_numbering/pipeline.py`
- **evaluate_barline_rules.py** (30 connections) — `tools/evaluate_barline_rules.py`
- **main()** (18 connections) — `tools/evaluate_barline_rules.py`
- **Box** (10 connections)
- **_metrics()** (8 connections) — `tools/evaluate_barline_rules.py`
- **Path** (8 connections)
- **greedy_match_by_rule()** (7 connections) — `tools/evaluate_barline_rules.py`
- **_measure_count_for_boxes()** (6 connections) — `tools/evaluate_barline_rules.py`
- **barline_ioa()** (5 connections) — `tools/evaluate_barline_rules.py`
- **_measure_iou_2d()** (5 connections) — `tools/evaluate_barline_rules.py`
- **_measure_local_kpis()** (5 connections) — `tools/evaluate_barline_rules.py`
- **_box_area()** (4 connections) — `tools/evaluate_barline_rules.py`
- **_intersection_area()** (4 connections) — `tools/evaluate_barline_rules.py`
- **load_gt_boxes()** (4 connections) — `tools/evaluate_barline_rules.py`
- **parse_scored_context()** (4 connections) — `tools/evaluate_barline_rules.py`
- **RuleResult** (4 connections) — `tools/evaluate_barline_rules.py`
- **center_distance_x()** (3 connections) — `tools/evaluate_barline_rules.py`
- **find_gt_file()** (3 connections) — `tools/evaluate_barline_rules.py`
- **_find_staff_mask_for_eval2_page()** (3 connections) — `tools/evaluate_barline_rules.py`
- **load_config_file()** (3 connections) — `tools/evaluate_barline_rules.py`
- **load_fn_det_classification()** (3 connections) — `tools/evaluate_barline_rules.py`
- **_rule_accept()** (3 connections) — `tools/evaluate_barline_rules.py`
- **_x_iou()** (3 connections) — `tools/evaluate_barline_rules.py`
- **_extract_measures()** (2 connections) — `tools/evaluate_barline_rules.py`
- **_rule_rank()** (2 connections) — `tools/evaluate_barline_rules.py`
- *... and 3 more nodes in this community*

## Relationships

- [Score](Score.md) (7 shared connections)
- [Staff](Staff.md) (7 shared connections)
- [greedy_barline_match](greedy_barline_match.md) (6 shared connections)
- [SystemBuilder](SystemBuilder.md) (4 shared connections)
- [.process_page](process_page.md) (3 shared connections)
- [Barline](Barline.md) (3 shared connections)
- [.run](run.md) (2 shared connections)
- [test_issue254_connector_artifact_contract.py](test_issue254_connector_artifact_contract.py.md) (2 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (2 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (2 shared connections)
- [barline_iou](barline_iou.md) (2 shared connections)
- [SystemConnectorEvidenceExtractor](SystemConnectorEvidenceExtractor.md) (1 shared connections)

## Source Files

- `src/measure_numbering/pipeline.py`
- `tools/evaluate_barline_rules.py`

## Audit Trail

- EXTRACTED: 101 (89%)
- INFERRED: 13 (11%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*