# barline_iou

> 38 nodes · cohesion 0.11

## Key Concepts

- **barline_iou()** (59 connections) — `src/common/barline_evaluation.py`
- **edge_crop_homr_merge.py** (8 connections) — `tools/edge_crop_homr_merge.py`
- **generate_hybrid_results.py** (8 connections) — `tools/generate_hybrid_results.py`
- **multi_crop_merge.py** (8 connections) — `tools/multi_crop_merge.py`
- **scale_merge_homr_preds.py** (8 connections) — `tools/scale_merge_homr_preds.py`
- **main()** (7 connections) — `tools/multi_crop_merge.py`
- **main()** (6 connections) — `tools/edge_crop_homr_merge.py`
- **main()** (6 connections) — `tools/generate_hybrid_results.py`
- **main()** (6 connections) — `tools/scale_merge_homr_preds.py`
- **diagnose_false_negatives.py** (5 connections) — `tools/diagnose_false_negatives.py`
- **choose_representative()** (4 connections) — `tools/edge_crop_homr_merge.py`
- **cluster_boxes()** (4 connections) — `tools/edge_crop_homr_merge.py`
- **load_homr_boxes()** (4 connections) — `tools/edge_crop_homr_merge.py`
- **Box** (4 connections)
- **choose_representative()** (4 connections) — `tools/generate_hybrid_results.py`
- **choose_representative()** (4 connections) — `tools/multi_crop_merge.py`
- **cluster_boxes()** (4 connections) — `tools/multi_crop_merge.py`
- **load_homr_boxes()** (4 connections) — `tools/multi_crop_merge.py`
- **Box** (4 connections)
- **choose_representative()** (4 connections) — `tools/scale_merge_homr_preds.py`
- **cluster_boxes()** (4 connections) — `tools/scale_merge_homr_preds.py`
- **load_homr_boxes()** (4 connections) — `tools/scale_merge_homr_preds.py`
- **Box** (4 connections)
- **find_matches_for_gt()** (3 connections) — `tools/diagnose_false_negatives.py`
- **main()** (3 connections) — `tools/diagnose_false_negatives.py`
- *... and 13 more nodes in this community*

## Relationships

- [barline_evaluation.py](barline_evaluation.py.md) (11 shared connections)
- [greedy_barline_match](greedy_barline_match.md) (9 shared connections)
- [mine_fn_cnn_hardpositives.py](mine_fn_cnn_hardpositives.py.md) (4 shared connections)
- [hybrid_omr_dln_union.py](hybrid_omr_dln_union.py.md) (3 shared connections)
- [trace_prokofiev_probe_boundary.py](trace_prokofiev_probe_boundary.py.md) (3 shared connections)
- [notehead_fn_cause_analysis.py](notehead_fn_cause_analysis.py.md) (3 shared connections)
- [tune_hybrid_detector.py](tune_hybrid_detector.py.md) (2 shared connections)
- [trace_stage_analysis.py](trace_stage_analysis.py.md) (2 shared connections)
- [diagnose_phase_b_layout_divergence.py](diagnose_phase_b_layout_divergence.py.md) (2 shared connections)
- [probe_scan.py](probe_scan.py.md) (2 shared connections)
- [load_json_boxes](load_json_boxes.md) (2 shared connections)
- [evaluate_barline_rules.py](evaluate_barline_rules.py.md) (2 shared connections)

## Source Files

- `src/common/barline_evaluation.py`
- `tools/diagnose_false_negatives.py`
- `tools/edge_crop_homr_merge.py`
- `tools/generate_hybrid_results.py`
- `tools/multi_crop_merge.py`
- `tools/scale_merge_homr_preds.py`

## Audit Trail

- EXTRACTED: 131 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*