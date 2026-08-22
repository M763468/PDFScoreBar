# _run_variant

> 13 nodes · cohesion 0.24

## Key Concepts

- **_run_variant()** (16 connections) — `tools/issue252/trace_prokofiev_probe_boundary.py`
- **_apply_candidate_filter()** (9 connections) — `tools/issue252/trace_prokofiev_probe_boundary.py`
- **_extract_candidate_postprocess_cfg()** (8 connections) — `src/pipeline/steps/probe_scan.py`
- **_resolve_scale_aware_probe_kwargs()** (7 connections) — `src/pipeline/steps/probe_scan.py`
- **_estimate_unit_size_from_existing_boxes()** (6 connections) — `src/pipeline/steps/probe_scan.py`
- **Any** (5 connections)
- **ndarray** (5 connections)
- **_paper_side_context_ratio()** (4 connections) — `tools/issue252/trace_prokofiev_probe_boundary.py`
- **Box** (4 connections)
- **_parse_bool_like()** (3 connections) — `src/pipeline/steps/probe_scan.py`
- **test_tool_local_side_context_can_reproduce_rejected_experiment()** (2 connections) — `tests/test_issue252_prokofiev_probe_boundary.py`
- **Extract batch-only candidate postprocess pseudo keys from kwargs.** (1 connections) — `src/pipeline/steps/probe_scan.py`
- **Translate batch-only ratio knobs into detect_probe_scan kwargs. Supported…** (1 connections) — `src/pipeline/steps/probe_scan.py`

## Relationships

- [trace_prokofiev_probe_boundary.py](trace_prokofiev_probe_boundary.py.md) (17 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (9 shared connections)
- [test_issue252_prokofiev_probe_boundary.py](test_issue252_prokofiev_probe_boundary.py.md) (2 shared connections)
- [filter_probe_candidates](filter_probe_candidates.md) (2 shared connections)
- [detect_probe_scan](detect_probe_scan.md) (2 shared connections)
- [get_cnn_apply_nms](get_cnn_apply_nms.md) (1 shared connections)

## Source Files

- `src/pipeline/steps/probe_scan.py`
- `tests/test_issue252_prokofiev_probe_boundary.py`
- `tools/issue252/trace_prokofiev_probe_boundary.py`

## Audit Trail

- EXTRACTED: 52 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*