# trace_prokofiev_probe_boundary.py

> 44 nodes · cohesion 0.13

## Key Concepts

- **trace_prokofiev_probe_boundary.py** (38 connections) — `tools/issue252/trace_prokofiev_probe_boundary.py`
- **probe_boundary.py** (20 connections) — `tools/issue252/probe_boundary.py`
- **build_report()** (20 connections) — `tools/issue252/trace_prokofiev_probe_boundary.py`
- **_run_variant()** (16 connections) — `tools/issue252/trace_prokofiev_probe_boundary.py`
- **stage_summary()** (11 connections) — `tools/issue252/probe_boundary.py`
- **normalize_box()** (9 connections) — `tools/issue252/probe_boundary.py`
- **Any** (9 connections)
- **_apply_candidate_filter()** (9 connections) — `tools/issue252/trace_prokofiev_probe_boundary.py`
- **_extract_candidate_postprocess_cfg()** (8 connections) — `src/pipeline/steps/probe_scan.py`
- **split_tall_existing_boxes()** (8 connections) — `tools/issue252/probe_boundary.py`
- **split_box_vertically()** (7 connections) — `src/pipeline/steps/candidate_filters.py`
- **_resolve_scale_aware_probe_kwargs()** (7 connections) — `src/pipeline/steps/probe_scan.py`
- **target_metrics()** (7 connections) — `tools/issue252/probe_boundary.py`
- **validate_fresh_contract_payload()** (7 connections) — `tools/issue252/probe_boundary.py`
- **write_json()** (7 connections) — `tools/issue252/probe_boundary.py`
- **_estimate_unit_size_from_existing_boxes()** (6 connections) — `src/pipeline/steps/probe_scan.py`
- **artifact_record()** (6 connections) — `tools/issue252/probe_boundary.py`
- **_debug_records()** (6 connections) — `tools/issue252/probe_boundary.py`
- **load_json()** (6 connections) — `tools/issue252/probe_boundary.py`
- **Box** (6 connections)
- **Path** (6 connections)
- **Any** (5 connections)
- **sha256()** (5 connections) — `tools/issue252/probe_boundary.py`
- **_detection_config()** (5 connections) — `tools/issue252/trace_prokofiev_probe_boundary.py`
- **ndarray** (5 connections)
- *... and 19 more nodes in this community*

## Relationships

- [run_probe_scan_batch](run_probe_scan_batch.md) (13 shared connections)
- [test_issue252_prokofiev_probe_boundary.py](test_issue252_prokofiev_probe_boundary.py.md) (11 shared connections)
- [filter_probe_candidates](filter_probe_candidates.md) (8 shared connections)
- [detect_probe_scan](detect_probe_scan.md) (5 shared connections)
- [load_json_boxes](load_json_boxes.md) (5 shared connections)
- [barline_iou](barline_iou.md) (3 shared connections)
- [load_yaml](load_yaml.md) (3 shared connections)
- [get_cnn_apply_nms](get_cnn_apply_nms.md) (3 shared connections)

## Source Files

- `src/pipeline/steps/candidate_filters.py`
- `src/pipeline/steps/probe_scan.py`
- `tests/test_issue252_prokofiev_probe_boundary.py`
- `tools/issue252/probe_boundary.py`
- `tools/issue252/trace_prokofiev_probe_boundary.py`

## Audit Trail

- EXTRACTED: 170 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*