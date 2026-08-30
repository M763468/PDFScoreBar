# barline_evaluation.py

> 27 nodes · cohesion 0.15

## Key Concepts

- **barline_evaluation.py** (81 connections) — `src/common/barline_evaluation.py`
- **is_barline_match()** (18 connections) — `src/common/barline_evaluation.py`
- **barline_vertical_overlap()** (16 connections) — `src/common/barline_evaluation.py`
- **center_distance_x()** (13 connections) — `src/common/barline_evaluation.py`
- **Box** (11 connections)
- **visualize_remaining_fn_v2.py** (11 connections) — `tools/visualize_remaining_fn_v2.py`
- **get_barline_match_rank()** (8 connections) — `src/common/barline_evaluation.py`
- **expand_barline_box()** (7 connections) — `src/common/barline_evaluation.py`
- **debug_greedy_match.py** (6 connections) — `tools/debug_greedy_match.py`
- **main()** (5 connections) — `tools/debug_greedy_match.py`
- **evaluate_and_visualize.py** (5 connections) — `tools/evaluate_and_visualize.py`
- **expand_barline_boxes()** (4 connections) — `src/common/barline_evaluation.py`
- **main()** (4 connections) — `tools/evaluate_and_visualize.py`
- **inspect_gt_dupes.py** (4 connections) — `tools/inspect_gt_dupes.py`
- **_ensure_ordered()** (3 connections) — `src/common/barline_evaluation.py`
- **main()** (3 connections) — `tools/inspect_gt_dupes.py`
- **_barline_centroid()** (2 connections) — `src/common/barline_evaluation.py`
- **find_scored_file()** (2 connections) — `tools/evaluate_and_visualize.py`
- **Utilities for comparing barline detections against ground truth boxes.** (1 connections) — `src/common/barline_evaluation.py`
- **Return horizontal distance between centers of two boxes.** (1 connections) — `src/common/barline_evaluation.py`
- **Return vertical overlap ratio between two boxes (range 0..1).** (1 connections) — `src/common/barline_evaluation.py`
- **Check if a predicted box matches a ground truth box according to specified rule.** (1 connections) — `src/common/barline_evaluation.py`
- **Return a comparable tuple representing the 'goodness' of a match. Higher values…** (1 connections) — `src/common/barline_evaluation.py`
- **Return a tuple of padded barline boxes for downstream use.** (1 connections) — `src/common/barline_evaluation.py`
- **Pad a barline bounding box so IoU is less sensitive to tiny width offsets. The…** (1 connections) — `src/common/barline_evaluation.py`
- *... and 2 more nodes in this community*

## Relationships

- [greedy_barline_match](greedy_barline_match.md) (25 shared connections)
- [metrics.py](metrics.py.md) (11 shared connections)
- [barline_iou](barline_iou.md) (10 shared connections)
- [diagnose_stage_e_fns.py](diagnose_stage_e_fns.py.md) (10 shared connections)
- [mine_fn_cnn_hardpositives.py](mine_fn_cnn_hardpositives.py.md) (7 shared connections)
- [cnn_scoring.py](cnn_scoring.py.md) (5 shared connections)
- [evaluate_barline_rules.py](evaluate_barline_rules.py.md) (4 shared connections)
- [score_candidates_batch.py](score_candidates_batch.py.md) (4 shared connections)
- [eval_full68_from_intermediates.py](eval_full68_from_intermediates.py.md) (3 shared connections)
- [analyze_staff_consistency.py](analyze_staff_consistency.py.md) (2 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (2 shared connections)
- [debug_mechanism_page3.py](debug_mechanism_page3.py.md) (1 shared connections)

## Source Files

- `src/common/barline_evaluation.py`
- `tools/debug_greedy_match.py`
- `tools/evaluate_and_visualize.py`
- `tools/inspect_gt_dupes.py`
- `tools/visualize_remaining_fn_v2.py`

## Audit Trail

- EXTRACTED: 160 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*