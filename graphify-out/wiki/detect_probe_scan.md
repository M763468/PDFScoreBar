# detect_probe_scan

> 70 nodes · cohesion 0.06

## Key Concepts

- **detect_probe_scan()** (22 connections) — `src/pipeline/probe_detector/__init__.py`
- **bands.py** (20 connections) — `src/pipeline/probe_detector/bands.py`
- **build_row_stats()** (19 connections) — `src/pipeline/probe_detector/bands.py`
- **probe_detector/__init__.py** (16 connections) — `src/pipeline/probe_detector/__init__.py`
- **staff_bands_from_mask()** (12 connections) — `src/pipeline/probe_detector/bands.py`
- **run_probe_detector_parity_check.py** (10 connections) — `tools/verification/run_probe_detector_parity_check.py`
- **run_parity_check()** (9 connections) — `tools/verification/run_probe_detector_parity_check.py`
- **resolve_bands()** (8 connections) — `src/pipeline/probe_detector/bands.py`
- **write_debug_output()** (8 connections) — `src/pipeline/probe_detector/debug.py`
- **probe_detector/types.py** (8 connections) — `src/pipeline/probe_detector/types.py`
- **rescue.py** (7 connections) — `src/pipeline/probe_detector/rescue.py`
- **apply_gap_rescue()** (7 connections) — `src/pipeline/probe_detector/rescue.py`
- **build_divisi_map()** (6 connections) — `src/pipeline/probe_detector/bands.py`
- **debug.py** (6 connections) — `src/pipeline/probe_detector/debug.py`
- **apply_rightmost_rescue()** (6 connections) — `src/pipeline/probe_detector/rescue.py`
- **generate_probe_candidates_from_inventory.py** (6 connections) — `tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py`
- **_run_one()** (6 connections) — `tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py`
- **ndarray** (5 connections)
- **scan_staff_band_from_ink()** (5 connections) — `src/pipeline/probe_detector/bands.py`
- **_draw_crop_band_overlays()** (5 connections) — `src/pipeline/probe_detector/debug.py`
- **BandSelectionConfig** (5 connections) — `src/pipeline/probe_detector/types.py`
- **DivisiRescueConfig** (5 connections) — `src/pipeline/probe_detector/types.py`
- **GapRescueConfig** (5 connections) — `src/pipeline/probe_detector/types.py`
- **RightmostRescueConfig** (5 connections) — `src/pipeline/probe_detector/types.py`
- **_draw_crop_labels()** (4 connections) — `src/pipeline/probe_detector/debug.py`
- *... and 45 more nodes in this community*

## Relationships

- [run_probe_scan_batch](run_probe_scan_batch.md) (7 shared connections)
- [score_candidates_batch.py](score_candidates_batch.py.md) (5 shared connections)
- [trace_prokofiev_probe_boundary.py](trace_prokofiev_probe_boundary.py.md) (5 shared connections)
- [run_gt_rebuild_hybrid_eval.py](run_gt_rebuild_hybrid_eval.py.md) (3 shared connections)

## Source Files

- `src/pipeline/probe_detector/__init__.py`
- `src/pipeline/probe_detector/bands.py`
- `src/pipeline/probe_detector/debug.py`
- `src/pipeline/probe_detector/rescue.py`
- `src/pipeline/probe_detector/types.py`
- `tests/test_probe_bands.py`
- `tools/check_improved_rule.py`
- `tools/explain_rule_failure.py`
- `tools/regression_check_staff.py`
- `tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py`
- `tools/verification/run_probe_detector_parity_check.py`

## Audit Trail

- EXTRACTED: 167 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*