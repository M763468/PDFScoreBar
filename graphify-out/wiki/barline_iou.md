# barline_iou

> 36 nodes · cohesion 0.11

## Key Concepts

- **barline_iou()** (59 connections) — `src/common/barline_evaluation.py`
- **edge_crop_homr_merge.py** (8 connections) — `tools/edge_crop_homr_merge.py`
- **generate_hybrid_results.py** (8 connections) — `tools/generate_hybrid_results.py`
- **multi_crop_merge.py** (8 connections) — `tools/multi_crop_merge.py`
- **main()** (7 connections) — `tools/multi_crop_merge.py`
- **tune_hybrid_detector.py** (6 connections) — `experiments/fp_reduction/tune_hybrid_detector.py`
- **main()** (6 connections) — `tools/edge_crop_homr_merge.py`
- **main()** (6 connections) — `tools/generate_hybrid_results.py`
- **diagnose_false_negatives.py** (5 connections) — `tools/diagnose_false_negatives.py`
- **has_match()** (4 connections) — `experiments/fp_reduction/tune_hybrid_detector.py`
- **load_json_boxes()** (4 connections) — `experiments/fp_reduction/tune_hybrid_detector.py`
- **main()** (4 connections) — `experiments/fp_reduction/tune_hybrid_detector.py`
- **choose_representative()** (4 connections) — `tools/edge_crop_homr_merge.py`
- **cluster_boxes()** (4 connections) — `tools/edge_crop_homr_merge.py`
- **load_homr_boxes()** (4 connections) — `tools/edge_crop_homr_merge.py`
- **Box** (4 connections)
- **choose_representative()** (4 connections) — `tools/generate_hybrid_results.py`
- **choose_representative()** (4 connections) — `tools/multi_crop_merge.py`
- **cluster_boxes()** (4 connections) — `tools/multi_crop_merge.py`
- **load_homr_boxes()** (4 connections) — `tools/multi_crop_merge.py`
- **Box** (4 connections)
- **find_matches_for_gt()** (3 connections) — `tools/diagnose_false_negatives.py`
- **main()** (3 connections) — `tools/diagnose_false_negatives.py`
- **offset_boxes()** (3 connections) — `tools/edge_crop_homr_merge.py`
- **cluster_boxes()** (3 connections) — `tools/generate_hybrid_results.py`
- *... and 11 more nodes in this community*

## Relationships

- [greedy_barline_match](greedy_barline_match.md) (20 shared connections)
- [mine_fn_cnn_hardpositives.py](mine_fn_cnn_hardpositives.py.md) (4 shared connections)
- [hybrid_omr_dln_union.py](hybrid_omr_dln_union.py.md) (3 shared connections)
- [trace_prokofiev_probe_boundary.py](trace_prokofiev_probe_boundary.py.md) (3 shared connections)
- [notehead_fn_cause_analysis.py](notehead_fn_cause_analysis.py.md) (3 shared connections)
- [scale_merge_homr_preds.py](scale_merge_homr_preds.py.md) (3 shared connections)
- [trace_stage_analysis.py](trace_stage_analysis.py.md) (2 shared connections)
- [cnn_scoring.py](cnn_scoring.py.md) (2 shared connections)
- [VerifiedProfileHybridDetector](VerifiedProfileHybridDetector.md) (2 shared connections)
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) (2 shared connections)
- [diagnose_stage_e_fns.py](diagnose_stage_e_fns.py.md) (2 shared connections)
- [musicxml_density_filter.py](musicxml_density_filter.py.md) (2 shared connections)

## Source Files

- `experiments/fp_reduction/tune_hybrid_detector.py`
- `src/common/barline_evaluation.py`
- `tools/diagnose_false_negatives.py`
- `tools/edge_crop_homr_merge.py`
- `tools/generate_hybrid_results.py`
- `tools/multi_crop_merge.py`

## Audit Trail

- EXTRACTED: 125 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*