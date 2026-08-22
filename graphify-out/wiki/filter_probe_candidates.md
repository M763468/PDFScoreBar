# filter_probe_candidates

> 15 nodes · cohesion 0.22

## Key Concepts

- **filter_probe_candidates()** (21 connections) — `src/pipeline/steps/candidate_filters.py`
- **candidate_filters.py** (16 connections) — `src/pipeline/steps/candidate_filters.py`
- **trim_box_to_ink()** (7 connections) — `src/pipeline/steps/candidate_filters.py`
- **ndarray** (6 connections)
- **_build_page_mask()** (4 connections) — `src/pipeline/steps/candidate_filters.py`
- **_box_mask_overlap_ratio()** (3 connections) — `src/pipeline/steps/candidate_filters.py`
- **_page_bbox_from_mask()** (3 connections) — `src/pipeline/steps/candidate_filters.py`
- **_center_in_bbox()** (2 connections) — `src/pipeline/steps/candidate_filters.py`
- **_median()** (2 connections) — `src/pipeline/steps/candidate_filters.py`
- **test_rejected_paper_experiment_is_not_a_production_filter_option()** (2 connections) — `tests/test_issue252_prokofiev_probe_boundary.py`
- **Any** (1 connections)
- **Heuristic filters to remove false positive candidates.** (1 connections) — `src/pipeline/steps/candidate_filters.py`
- **Apply heuristic filters to remove false positive candidates. Returns: A tuple…** (1 connections) — `src/pipeline/steps/candidate_filters.py`
- **Return binary mask of the paper area (largest bright connected component).** (1 connections) — `src/pipeline/steps/candidate_filters.py`
- **Trim box vertically based on ink density.** (1 connections) — `src/pipeline/steps/candidate_filters.py`

## Relationships

- [trace_prokofiev_probe_boundary.py](trace_prokofiev_probe_boundary.py.md) (6 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (5 shared connections)
- [test_issue252_prokofiev_probe_boundary.py](test_issue252_prokofiev_probe_boundary.py.md) (3 shared connections)
- [summarize_stage_c_filter_ablation.py](summarize_stage_c_filter_ablation.py.md) (3 shared connections)
- [summarize_stage_c_filter_drop_reasons.py](summarize_stage_c_filter_drop_reasons.py.md) (3 shared connections)
- [hybrid.py](hybrid.py.md) (3 shared connections)
- [_run_variant](_run_variant.md) (2 shared connections)

## Source Files

- `src/pipeline/steps/candidate_filters.py`
- `tests/test_issue252_prokofiev_probe_boundary.py`

## Audit Trail

- EXTRACTED: 47 (98%)
- INFERRED: 1 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*