# verify_cnn_scored.py

> 12 nodes · cohesion 0.23

## Key Concepts

- **verify_cnn_scored.py** (5 connections) — `tools/repro_accuracy/verify_cnn_scored.py`
- **verify_v10_accuracy.py** (5 connections) — `tools/repro_accuracy/verify_v10_accuracy.py`
- **eval_yolo_world.py** (4 connections) — `experiments/models/eval_yolo_world.py`
- **main()** (4 connections) — `experiments/models/eval_yolo_world.py`
- **main()** (4 connections) — `tools/repro_accuracy/verify_cnn_scored.py`
- **main()** (4 connections) — `tools/repro_accuracy/verify_v10_accuracy.py`
- **load_gt_boxes()** (2 connections) — `experiments/models/eval_yolo_world.py`
- **parse_args()** (2 connections) — `experiments/models/eval_yolo_world.py`
- **get_gt_boxes()** (2 connections) — `tools/repro_accuracy/verify_cnn_scored.py`
- **load_json()** (2 connections) — `tools/repro_accuracy/verify_cnn_scored.py`
- **get_gt_boxes()** (2 connections) — `tools/repro_accuracy/verify_v10_accuracy.py`
- **load_json()** (2 connections) — `tools/repro_accuracy/verify_v10_accuracy.py`

## Relationships

- [greedy_barline_match](greedy_barline_match.md) (8 shared connections)

## Source Files

- `experiments/models/eval_yolo_world.py`
- `tools/repro_accuracy/verify_cnn_scored.py`
- `tools/repro_accuracy/verify_v10_accuracy.py`

## Audit Trail

- EXTRACTED: 23 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*