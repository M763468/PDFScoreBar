# filter_probe_candidates

> 19 nodes · cohesion 0.18

## Key Concepts

- **filter_probe_candidates()** (21 connections) — `src/pipeline/steps/candidate_filters.py`
- **candidate_filters.py** (16 connections) — `src/pipeline/steps/candidate_filters.py`
- **reproduce_clean_seed_v12.py** (8 connections) — `tools/repro_accuracy/reproduce_clean_seed_v12.py`
- **split_box_vertically()** (7 connections) — `src/pipeline/steps/candidate_filters.py`
- **ndarray** (6 connections)
- **main()** (5 connections) — `tools/repro_accuracy/reproduce_clean_seed_v12.py`
- **_build_page_mask()** (4 connections) — `src/pipeline/steps/candidate_filters.py`
- **_box_mask_overlap_ratio()** (3 connections) — `src/pipeline/steps/candidate_filters.py`
- **_page_bbox_from_mask()** (3 connections) — `src/pipeline/steps/candidate_filters.py`
- **build_parser()** (3 connections) — `tools/repro_accuracy/reproduce_clean_seed_v12.py`
- **_center_in_bbox()** (2 connections) — `src/pipeline/steps/candidate_filters.py`
- **_median()** (2 connections) — `src/pipeline/steps/candidate_filters.py`
- **test_rejected_paper_experiment_is_not_a_production_filter_option()** (2 connections) — `tests/test_issue252_prokofiev_probe_boundary.py`
- **Any** (1 connections)
- **Heuristic filters to remove false positive candidates.** (1 connections) — `src/pipeline/steps/candidate_filters.py`
- **Split a box vertically into segments where ink is present, separated by gaps.** (1 connections) — `src/pipeline/steps/candidate_filters.py`
- **Apply heuristic filters to remove false positive candidates. Returns: A tuple…** (1 connections) — `src/pipeline/steps/candidate_filters.py`
- **Return binary mask of the paper area (largest bright connected component).** (1 connections) — `src/pipeline/steps/candidate_filters.py`
- **ArgumentParser** (1 connections)

## Relationships

- [trace_prokofiev_probe_boundary.py](trace_prokofiev_probe_boundary.py.md) (8 shared connections)
- [load_json_boxes](load_json_boxes.md) (6 shared connections)
- [probe_scan.py](probe_scan.py.md) (4 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (4 shared connections)
- [test_issue252_prokofiev_probe_boundary.py](test_issue252_prokofiev_probe_boundary.py.md) (3 shared connections)
- [summarize_stage_c_filter_ablation.py](summarize_stage_c_filter_ablation.py.md) (3 shared connections)

## Source Files

- `src/pipeline/steps/candidate_filters.py`
- `tests/test_issue252_prokofiev_probe_boundary.py`
- `tools/repro_accuracy/reproduce_clean_seed_v12.py`

## Audit Trail

- EXTRACTED: 57 (98%)
- INFERRED: 1 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*