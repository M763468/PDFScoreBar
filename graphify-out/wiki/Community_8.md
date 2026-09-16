# Community 8

> 69 nodes · cohesion 0.06

## Key Concepts

- **run_probe_scan_batch()** (47 connections) — `src/pipeline/steps/probe_scan.py`
- **probe_scan.py** (44 connections) — `src/pipeline/steps/probe_scan.py`
- **cnn_scoring.py** (36 connections) — `src/pipeline/steps/cnn_scoring.py`
- **detection/orchestrator.py** (26 connections) — `src/pipeline/detection/orchestrator.py`
- **run_cnn_scoring_batch()** (26 connections) — `src/pipeline/steps/cnn_scoring.py`
- **load_json_boxes()** (19 connections) — `src/pipeline/steps/hybrid_consensus.py`
- **_score_directory()** (18 connections) — `src/pipeline/steps/cnn_scoring.py`
- **build_probe_run_id()** (15 connections) — `src/pipeline/core/run_ids.py`
- **run_ids.py** (11 connections) — `src/pipeline/core/run_ids.py`
- **_load_bands_for_image()** (10 connections) — `src/pipeline/steps/probe_scan.py`
- **verify_final_comparison.py** (10 connections) — `tools/verify_final_comparison.py`
- **unified_recipe.py** (9 connections) — `tools/repro_accuracy/unified_recipe.py`
- **split_score_page_from_composite_stem()** (8 connections) — `src/pipeline/core/run_ids.py`
- **_extract_candidate_postprocess_cfg()** (8 connections) — `src/pipeline/steps/probe_scan.py`
- **reproduce_clean_seed_v12.py** (8 connections) — `tools/repro_accuracy/reproduce_clean_seed_v12.py`
- **split_box_vertically()** (7 connections) — `src/pipeline/steps/candidate_filters.py`
- **trim_box_to_ink()** (7 connections) — `src/pipeline/steps/candidate_filters.py`
- **GPUNormalize** (7 connections) — `src/pipeline/steps/cnn_scoring.py`
- **_resolve_scale_aware_probe_kwargs()** (7 connections) — `src/pipeline/steps/probe_scan.py`
- **batch_re_evaluate_bench.py** (7 connections) — `tools/batch_re_evaluate_bench.py`
- **verify_repro_batch_final.py** (7 connections) — `tools/repro_accuracy/verify_repro_batch_final.py`
- **apply_nms()** (6 connections) — `src/pipeline/steps/cnn_scoring.py`
- **_estimate_unit_size_from_existing_boxes()** (6 connections) — `src/pipeline/steps/probe_scan.py`
- **main()** (6 connections) — `tools/verify_final_comparison.py`
- **_augment_unit_normalized_boxes()** (5 connections) — `src/pipeline/steps/probe_scan.py`
- *... and 44 more nodes in this community*

## Relationships

- [Community 16](Community_16.md) (21 shared connections)
- [Community 11](Community_11.md) (19 shared connections)
- [Community 14](Community_14.md) (15 shared connections)
- [Community 59](Community_59.md) (13 shared connections)
- [Community 61](Community_61.md) (12 shared connections)
- [Community 49](Community_49.md) (9 shared connections)
- [Community 29](Community_29.md) (9 shared connections)
- [Community 102](Community_102.md) (8 shared connections)
- [Community 64](Community_64.md) (7 shared connections)
- [Community 7](Community_7.md) (7 shared connections)
- [Community 40](Community_40.md) (6 shared connections)
- [Community 0](Community_0.md) (5 shared connections)

## Source Files

- `src/pipeline/core/run_ids.py`
- `src/pipeline/detection/orchestrator.py`
- `src/pipeline/steps/candidate_filters.py`
- `src/pipeline/steps/cnn_scoring.py`
- `src/pipeline/steps/hybrid_consensus.py`
- `src/pipeline/steps/probe_scan.py`
- `tools/batch_re_evaluate_bench.py`
- `tools/repro_accuracy/reproduce_clean_seed_v12.py`
- `tools/repro_accuracy/unified_recipe.py`
- `tools/repro_accuracy/verify_repro_batch_final.py`
- `tools/verify_final_comparison.py`

## Audit Trail

- EXTRACTED: 309 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*