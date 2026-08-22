# run_probe_scan_batch()

> God node · 47 connections · `src/pipeline/steps/probe_scan.py`

**Community:** [run_probe_scan_batch](run_probe_scan_batch.md)

## Connections by Relation

### calls
- ensure_dir() `EXTRACTED`
- detect_probe_scan() `EXTRACTED`
- load_image() `EXTRACTED`
- filter_probe_candidates() `EXTRACTED`
- build_probe_run_id() `EXTRACTED`
- ._run_probe_scan() `EXTRACTED`
- split_wide_candidates() `EXTRACTED`
- _load_bands_for_image() `EXTRACTED`
- regenerate_probe_rescue_candidates() `EXTRACTED`
- _extract_candidate_postprocess_cfg() `EXTRACTED`
- split_box_vertically() `EXTRACTED`
- _resolve_scale_aware_probe_kwargs() `EXTRACTED`
- trim_box_to_ink() `EXTRACTED`
- run_probe_rescue_candidate_generation() `EXTRACTED`
- _estimate_unit_size_from_existing_boxes() `EXTRACTED`
- [main()](main%28%29.md) `EXTRACTED`
- run_test() `EXTRACTED`
- _build_staff_mask_map() `EXTRACTED`
- _augment_unit_normalized_boxes() `EXTRACTED`
- run_batch_verification() `EXTRACTED`

### contains
- probe_scan.py `EXTRACTED`

### imports
- [dense_probe_candidate.py](dense_probe_candidate.py.md) `EXTRACTED`
- detection/orchestrator.py `EXTRACTED`
- [dense_full_pipeline.py](dense_full_pipeline.py.md) `EXTRACTED`
- [run_issue53_probe_rescue_then_eval.py](run_issue53_probe_rescue_then_eval.py.md) `EXTRACTED`
- verify_final_comparison.py `EXTRACTED`
- unified_recipe.py `EXTRACTED`
- verify_sr_levels_with_v12.py `EXTRACTED`
- reproduce_clean_seed_v12.py `EXTRACTED`
- reproduce_issue44_validation.py `EXTRACTED`
- verify_sr_bypass_filtering.py `EXTRACTED`
- batch_re_evaluate_bench.py `EXTRACTED`
- issue46_track_a_split_test.py `EXTRACTED`
- issue46_track_a_split_test_v2.py `EXTRACTED`
- evaluate_full_rescue_v1.py `EXTRACTED`

### rationale_for
- Generate probe candidates for all pages in-process. Output format and file… `EXTRACTED`

### references
- [Any](Any.md) `EXTRACTED`
- [Path](Path.md) `EXTRACTED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*