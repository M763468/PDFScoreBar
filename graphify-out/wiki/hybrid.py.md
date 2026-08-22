# hybrid.py

> 43 nodes · cohesion 0.08

## Key Concepts

- **hybrid.py** (28 connections) — `src/pipeline/detection/hybrid.py`
- **HybridDetector** (21 connections) — `src/pipeline/detection/hybrid.py`
- **load_json_boxes()** (19 connections) — `src/pipeline/steps/hybrid_consensus.py`
- **HomrPredictor** (13 connections) — `src/homr_eval_scripts/core/predictor.py`
- **.run()** (13 connections) — `src/pipeline/detection/hybrid.py`
- **._run_homr_in_process()** (13 connections) — `src/pipeline/detection/hybrid.py`
- **profile_hybrid.py** (13 connections) — `src/pipeline/detection/profile_hybrid.py`
- **hybrid_consensus.py** (13 connections) — `src/pipeline/steps/hybrid_consensus.py`
- **_HomrInternalLogFilter** (10 connections) — `src/pipeline/detection/hybrid.py`
- **apply_hybrid_consensus_filter()** (9 connections) — `src/pipeline/steps/hybrid_consensus.py`
- **reproduce_clean_seed_v12.py** (8 connections) — `tools/repro_accuracy/reproduce_clean_seed_v12.py`
- **Path** (6 connections)
- **main()** (5 connections) — `tools/repro_accuracy/reproduce_clean_seed_v12.py`
- **._write_line()** (4 connections) — `src/pipeline/detection/hybrid.py`
- **._all_stems_exist()** (4 connections) — `src/pipeline/detection/hybrid.py`
- **._get_python_cmd()** (4 connections) — `src/pipeline/detection/hybrid.py`
- **_suppress_homr_low_value_internal_logs()** (4 connections) — `src/pipeline/detection/hybrid.py`
- **log_vram_usage()** (4 connections) — `src/pipeline/detection/utils.py`
- **.__init__()** (3 connections) — `src/pipeline/detection/hybrid.py`
- **._omr_all_stems_exist()** (3 connections) — `src/pipeline/detection/hybrid.py`
- **._rel()** (3 connections) — `src/pipeline/detection/hybrid.py`
- **Any** (3 connections)
- **_has_match()** (3 connections) — `src/pipeline/steps/hybrid_consensus.py`
- **build_parser()** (3 connections) — `tools/repro_accuracy/reproduce_clean_seed_v12.py`
- **_env_flag_enabled()** (2 connections) — `src/pipeline/detection/hybrid.py`
- *... and 18 more nodes in this community*

## Relationships

- [run_probe_scan_batch](run_probe_scan_batch.md) (18 shared connections)
- [VerifiedProfileHybridDetector](VerifiedProfileHybridDetector.md) (14 shared connections)
- [barline_evaluation.py](barline_evaluation.py.md) (7 shared connections)
- [heuristics.py](heuristics.py.md) (5 shared connections)
- [trace_prokofiev_probe_boundary.py](trace_prokofiev_probe_boundary.py.md) (5 shared connections)
- [run_stage_d_upstream_regen.py](run_stage_d_upstream_regen.py.md) (4 shared connections)
- [apply_advanced_sr](apply_advanced_sr.md) (3 shared connections)
- [run_detection_step](run_detection_step.md) (3 shared connections)
- [summarize_stage_c_filter_ablation.py](summarize_stage_c_filter_ablation.py.md) (3 shared connections)
- [summarize_stage_c_filter_drop_reasons.py](summarize_stage_c_filter_drop_reasons.py.md) (3 shared connections)
- [filter_probe_candidates](filter_probe_candidates.md) (3 shared connections)
- [common/connector_artifacts.py](common-connector_artifacts.py.md) (2 shared connections)

## Source Files

- `src/homr_eval_scripts/core/predictor.py`
- `src/pipeline/detection/hybrid.py`
- `src/pipeline/detection/profile_hybrid.py`
- `src/pipeline/detection/utils.py`
- `src/pipeline/steps/hybrid_consensus.py`
- `tools/repro_accuracy/reproduce_clean_seed_v12.py`

## Audit Trail

- EXTRACTED: 148 (94%)
- INFERRED: 10 (6%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*