# run_probe_scan_batch

> 43 nodes · cohesion 0.10

## Key Concepts

- **run_probe_scan_batch()** (47 connections) — `src/pipeline/steps/probe_scan.py`
- **probe_scan.py** (44 connections) — `src/pipeline/steps/probe_scan.py`
- **run_cnn_scoring_batch()** (26 connections) — `src/pipeline/steps/cnn_scoring.py`
- **load_json_boxes()** (19 connections) — `src/pipeline/steps/hybrid_consensus.py`
- **build_probe_run_id()** (15 connections) — `src/pipeline/core/run_ids.py`
- **run_ids.py** (11 connections) — `src/pipeline/core/run_ids.py`
- **_load_bands_for_image()** (10 connections) — `src/pipeline/steps/probe_scan.py`
- **verify_final_comparison.py** (10 connections) — `tools/verify_final_comparison.py`
- **unified_recipe.py** (9 connections) — `tools/repro_accuracy/unified_recipe.py`
- **_extract_candidate_postprocess_cfg()** (8 connections) — `src/pipeline/steps/probe_scan.py`
- **reproduce_clean_seed_v12.py** (8 connections) — `tools/repro_accuracy/reproduce_clean_seed_v12.py`
- **reproduce_issue44_validation.py** (8 connections) — `tools/reproduce_issue44_validation.py`
- **_resolve_scale_aware_probe_kwargs()** (7 connections) — `src/pipeline/steps/probe_scan.py`
- **batch_re_evaluate_bench.py** (7 connections) — `tools/batch_re_evaluate_bench.py`
- **build_probe_run_id_from_parts()** (6 connections) — `src/pipeline/core/run_ids.py`
- **_estimate_unit_size_from_existing_boxes()** (6 connections) — `src/pipeline/steps/probe_scan.py`
- **main()** (6 connections) — `tools/verify_final_comparison.py`
- **_augment_unit_normalized_boxes()** (5 connections) — `src/pipeline/steps/probe_scan.py`
- **_build_staff_mask_map()** (5 connections) — `src/pipeline/steps/probe_scan.py`
- **Any** (5 connections)
- **run_batch_verification()** (5 connections) — `tools/batch_re_evaluate_bench.py`
- **main()** (5 connections) — `tools/repro_accuracy/reproduce_clean_seed_v12.py`
- **main()** (5 connections) — `tools/repro_accuracy/unified_recipe.py`
- **main()** (5 connections) — `tools/reproduce_issue44_validation.py`
- **Path** (4 connections)
- *... and 18 more nodes in this community*

## Relationships

- [trace_prokofiev_probe_boundary.py](trace_prokofiev_probe_boundary.py.md) (24 shared connections)
- [score_candidates_batch.py](score_candidates_batch.py.md) (20 shared connections)
- [greedy_barline_match](greedy_barline_match.md) (19 shared connections)
- [cnn_scoring.py](cnn_scoring.py.md) (15 shared connections)
- [detection/orchestrator.py](detection-orchestrator.py.md) (9 shared connections)
- [restored_orchestrator.py](restored_orchestrator.py.md) (6 shared connections)
- [VerifiedProfileHybridDetector](VerifiedProfileHybridDetector.md) (6 shared connections)
- [score_candidates_then_eval_full68.py](score_candidates_then_eval_full68.py.md) (5 shared connections)
- [verify_detector_full68.py](verify_detector_full68.py.md) (3 shared connections)
- [dense_full_pipeline.py](dense_full_pipeline.py.md) (3 shared connections)
- [dense_probe_candidate.py](dense_probe_candidate.py.md) (3 shared connections)
- [run_issue53_probe_rescue_then_eval.py](run_issue53_probe_rescue_then_eval.py.md) (3 shared connections)

## Source Files

- `src/pipeline/core/run_ids.py`
- `src/pipeline/steps/cnn_scoring.py`
- `src/pipeline/steps/hybrid_consensus.py`
- `src/pipeline/steps/probe_scan.py`
- `tools/batch_re_evaluate_bench.py`
- `tools/repro_accuracy/reproduce_clean_seed_v12.py`
- `tools/repro_accuracy/unified_recipe.py`
- `tools/reproduce_issue44_validation.py`
- `tools/verify_final_comparison.py`

## Audit Trail

- EXTRACTED: 220 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*