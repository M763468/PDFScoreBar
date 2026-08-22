# load_yaml

> 18 nodes · cohesion 0.21

## Key Concepts

- **load_yaml()** (26 connections) — `src/pipeline/core/config.py`
- **core/config.py** (21 connections) — `src/pipeline/core/config.py`
- **run_pipeline()** (15 connections) — `src/pipeline/main.py`
- **pipeline/main.py** (14 connections) — `src/pipeline/main.py`
- **test_pipeline_integration.py** (8 connections) — `tests/test_pipeline_integration.py`
- **write_yaml()** (6 connections) — `src/pipeline/core/config.py`
- **.test_full_sequence()** (5 connections) — `tests/test_pipeline_integration.py`
- **Any** (3 connections)
- **main()** (3 connections) — `src/pipeline/main.py`
- **clear_image_cache()** (3 connections) — `src/pipeline/utils/images.py`
- **TestPipelineIntegration** (3 connections) — `tests/test_pipeline_integration.py`
- **.setUpClass()** (3 connections) — `tests/test_pipeline_integration.py`
- **Path** (2 connections)
- **Configuration helpers for the pipeline.** (1 connections) — `src/pipeline/core/config.py`
- **Path** (1 connections)
- **End-to-end pipeline entrypoint (no CLI wrapper).** (1 connections) — `src/pipeline/main.py`
- **CLI entry point for the pipeline.** (1 connections) — `src/pipeline/main.py`
- **Entry point for running the full pipeline.** (1 connections) — `src/pipeline/main.py`

## Relationships

- [run_stage_e_full_pipeline.py](run_stage_e_full_pipeline.py.md) (6 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (5 shared connections)
- [get_nested](get_nested.md) (5 shared connections)
- [PipelineOrchestrator](PipelineOrchestrator.md) (5 shared connections)
- [apply_corrections.py](apply_corrections.py.md) (4 shared connections)
- [dense_probe_candidate.py](dense_probe_candidate.py.md) (3 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (3 shared connections)
- [trace_prokofiev_probe_boundary.py](trace_prokofiev_probe_boundary.py.md) (3 shared connections)
- [phase_c_phase_a_support.py](phase_c_phase_a_support.py.md) (3 shared connections)
- [run_phase_c_mmr_regression.py](run_phase_c_mmr_regression.py.md) (3 shared connections)
- [verify_detector_full68.py](verify_detector_full68.py.md) (3 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (2 shared connections)

## Source Files

- `src/pipeline/core/config.py`
- `src/pipeline/main.py`
- `src/pipeline/utils/images.py`
- `tests/test_pipeline_integration.py`

## Audit Trail

- EXTRACTED: 85 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*