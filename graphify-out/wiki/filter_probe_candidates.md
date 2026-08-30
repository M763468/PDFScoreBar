# filter_probe_candidates

> 26 nodes · cohesion 0.15

## Key Concepts

- **filter_probe_candidates()** (21 connections) — `src/pipeline/steps/candidate_filters.py`
- **candidate_filters.py** (16 connections) — `src/pipeline/steps/candidate_filters.py`
- **summarize_stage_c_filter_drop_reasons.py** (14 connections) — `tools/issue120/summarize_stage_c_filter_drop_reasons.py`
- **main()** (8 connections) — `tools/issue120/summarize_stage_c_filter_drop_reasons.py`
- **replay_page()** (7 connections) — `tools/issue120/summarize_stage_c_filter_drop_reasons.py`
- **ndarray** (6 connections)
- **make_rules()** (5 connections) — `tools/issue120/summarize_stage_c_filter_drop_reasons.py`
- **render_markdown()** (5 connections) — `tools/issue120/summarize_stage_c_filter_drop_reasons.py`
- **_build_page_mask()** (4 connections) — `src/pipeline/steps/candidate_filters.py`
- **load_inventory()** (4 connections) — `tools/issue120/summarize_stage_c_filter_drop_reasons.py`
- **PageFilterReasonRow** (4 connections) — `tools/issue120/summarize_stage_c_filter_drop_reasons.py`
- **write_csv()** (4 connections) — `tools/issue120/summarize_stage_c_filter_drop_reasons.py`
- **_box_mask_overlap_ratio()** (3 connections) — `src/pipeline/steps/candidate_filters.py`
- **_page_bbox_from_mask()** (3 connections) — `src/pipeline/steps/candidate_filters.py`
- **build_parser()** (3 connections) — `tools/issue120/summarize_stage_c_filter_drop_reasons.py`
- **Any** (3 connections)
- **Path** (3 connections)
- **_center_in_bbox()** (2 connections) — `src/pipeline/steps/candidate_filters.py`
- **_median()** (2 connections) — `src/pipeline/steps/candidate_filters.py`
- **test_rejected_paper_experiment_is_not_a_production_filter_option()** (2 connections) — `tests/test_issue252_prokofiev_probe_boundary.py`
- **Namespace** (2 connections)
- **Any** (1 connections)
- **Heuristic filters to remove false positive candidates.** (1 connections) — `src/pipeline/steps/candidate_filters.py`
- **Apply heuristic filters to remove false positive candidates. Returns: A tuple…** (1 connections) — `src/pipeline/steps/candidate_filters.py`
- **Return binary mask of the paper area (largest bright connected component).** (1 connections) — `src/pipeline/steps/candidate_filters.py`
- *... and 1 more nodes in this community*

## Relationships

- [trace_prokofiev_probe_boundary.py](trace_prokofiev_probe_boundary.py.md) (11 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (9 shared connections)
- [summarize_stage_c_filter_ablation.py](summarize_stage_c_filter_ablation.py.md) (3 shared connections)
- [iter_manifest](iter_manifest.md) (2 shared connections)
- [eval_full68_from_intermediates.py](eval_full68_from_intermediates.py.md) (1 shared connections)

## Source Files

- `src/pipeline/steps/candidate_filters.py`
- `tests/test_issue252_prokofiev_probe_boundary.py`
- `tools/issue120/summarize_stage_c_filter_drop_reasons.py`

## Audit Trail

- EXTRACTED: 75 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*