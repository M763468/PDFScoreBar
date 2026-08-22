# is_barline_match

> 32 nodes · cohesion 0.14

## Key Concepts

- **is_barline_match()** (18 connections) — `src/common/barline_evaluation.py`
- **mine_fn_cnn_hardpositives.py** (14 connections) — `tools/cnn_classifier/mine_fn_cnn_hardpositives.py`
- **mine_hard_negatives.py** (12 connections) — `tools/cnn_classifier/mine_hard_negatives.py`
- **main()** (11 connections) — `tools/cnn_classifier/mine_fn_cnn_hardpositives.py`
- **visualize_remaining_fn_v2.py** (11 connections) — `tools/visualize_remaining_fn_v2.py`
- **main()** (10 connections) — `tools/cnn_classifier/mine_hard_negatives.py`
- **re_evaluate_global.py** (10 connections) — `tools/re_evaluate_global.py`
- **find_gt_file()** (8 connections) — `tools/re_evaluate_global.py`
- **parse_scored_context()** (8 connections) — `tools/re_evaluate_global.py`
- **main()** (7 connections) — `tools/re_evaluate_global.py`
- **center_crop()** (6 connections) — `tools/cnn_classifier/score_candidates_batch.py`
- **crop_size_from_bbox()** (6 connections) — `tools/cnn_classifier/score_candidates_batch.py`
- **evaluate_and_visualize.py** (5 connections) — `tools/evaluate_and_visualize.py`
- **_best_recoverable_candidate()** (4 connections) — `tools/cnn_classifier/mine_fn_cnn_hardpositives.py`
- **_load_gt_boxes()** (4 connections) — `tools/cnn_classifier/mine_fn_cnn_hardpositives.py`
- **_load_gt_boxes()** (4 connections) — `tools/cnn_classifier/mine_hard_negatives.py`
- **main()** (4 connections) — `tools/evaluate_and_visualize.py`
- **Path** (4 connections)
- **load_config_file()** (3 connections) — `tools/cnn_classifier/mine_fn_cnn_hardpositives.py`
- **Path** (3 connections)
- **load_config_file()** (3 connections) — `tools/cnn_classifier/mine_hard_negatives.py`
- **Path** (3 connections)
- **load_config_file()** (3 connections) — `tools/re_evaluate_global.py`
- **HardPositiveRow** (2 connections) — `tools/cnn_classifier/mine_fn_cnn_hardpositives.py`
- **Box** (2 connections)
- *... and 7 more nodes in this community*

## Relationships

- [barline_evaluation.py](barline_evaluation.py.md) (12 shared connections)
- [greedy_barline_match](greedy_barline_match.md) (8 shared connections)
- [barline_iou](barline_iou.md) (6 shared connections)
- [score_candidates_batch.py](score_candidates_batch.py.md) (6 shared connections)
- [diagnose_stage_e_fns.py](diagnose_stage_e_fns.py.md) (4 shared connections)
- [eval_full68_from_intermediates.py](eval_full68_from_intermediates.py.md) (2 shared connections)

## Source Files

- `src/common/barline_evaluation.py`
- `tools/cnn_classifier/mine_fn_cnn_hardpositives.py`
- `tools/cnn_classifier/mine_hard_negatives.py`
- `tools/cnn_classifier/score_candidates_batch.py`
- `tools/evaluate_and_visualize.py`
- `tools/re_evaluate_global.py`
- `tools/visualize_remaining_fn_v2.py`

## Audit Trail

- EXTRACTED: 106 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*