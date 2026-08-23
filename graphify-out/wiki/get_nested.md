# get_nested

> 11 nodes · cohesion 0.38

## Key Concepts

- **get_nested()** (31 connections) — `src/pipeline/core/config.py`
- **filters.py** (12 connections) — `src/pipeline/steps/filters.py`
- **resolve_page_filters()** (8 connections) — `src/pipeline/steps/filters.py`
- **is_blank_page()** (6 connections) — `src/pipeline/steps/filters.py`
- **get_user_exclude_indices()** (5 connections) — `src/pipeline/steps/filters.py`
- **Any** (5 connections)
- **staff_detect_failed()** (5 connections) — `src/pipeline/steps/filters.py`
- **._resolve_page_runs()** (4 connections) — `src/pipeline/orchestrator.py`
- **Path** (3 connections)
- **Resolves which runs to use for each page (legacy manual resolution).** (1 connections) — `src/pipeline/orchestrator.py`
- **Filtering helpers for blank/staff checks.** (1 connections) — `src/pipeline/steps/filters.py`

## Relationships

- [.run](run.md) (10 shared connections)
- [load_image](load_image.md) (6 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (5 shared connections)
- [load_yaml](load_yaml.md) (5 shared connections)
- [probe_scan.py](probe_scan.py.md) (4 shared connections)
- [run_full_pipeline.py](run_full_pipeline.py.md) (2 shared connections)
- [test_issue264_phase_a_connector_geometry.py](test_issue264_phase_a_connector_geometry.py.md) (2 shared connections)
- [dense_probe_candidate.py](dense_probe_candidate.py.md) (2 shared connections)
- [DetectorOrchestrator](DetectorOrchestrator.md) (1 shared connections)
- [PipelineOrchestrator](PipelineOrchestrator.md) (1 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (1 shared connections)

## Source Files

- `src/pipeline/core/config.py`
- `src/pipeline/orchestrator.py`
- `src/pipeline/steps/filters.py`

## Audit Trail

- EXTRACTED: 60 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*