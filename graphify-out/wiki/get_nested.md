# get_nested

> 23 nodes · cohesion 0.17

## Key Concepts

- **get_nested()** (31 connections) — `src/pipeline/core/config.py`
- **detection/__init__.py** (20 connections) — `src/pipeline/detection/__init__.py`
- **resolve_paths_from_detection()** (14 connections) — `src/pipeline/detection/utils.py`
- **filters.py** (12 connections) — `src/pipeline/steps/filters.py`
- **detection/utils.py** (11 connections) — `src/pipeline/detection/utils.py`
- **resolve_barlines_and_masks_config()** (9 connections) — `src/pipeline/detection/utils.py`
- **resolve_page_filters()** (8 connections) — `src/pipeline/steps/filters.py`
- **is_blank_page()** (6 connections) — `src/pipeline/steps/filters.py`
- **get_user_exclude_indices()** (5 connections) — `src/pipeline/steps/filters.py`
- **Any** (5 connections)
- **staff_detect_failed()** (5 connections) — `src/pipeline/steps/filters.py`
- **_discover_current_homr_staff_mask()** (4 connections) — `src/pipeline/detection/utils.py`
- **._resolve_page_runs()** (4 connections) — `src/pipeline/orchestrator.py`
- **Path** (3 connections)
- **Path** (3 connections)
- **Any** (2 connections)
- **Detection package providing barline detection orchestration.** (1 connections) — `src/pipeline/detection/__init__.py`
- **Utility functions for path resolution and system monitoring in detection.** (1 connections) — `src/pipeline/detection/utils.py`
- **Resolves paths based on configuration when detection is skipped.** (1 connections) — `src/pipeline/detection/utils.py`
- **Find one retained current-HOMR mask beside a replay connector artifact.** (1 connections) — `src/pipeline/detection/utils.py`
- **Resolves output paths for barlines and staff masks after detection.** (1 connections) — `src/pipeline/detection/utils.py`
- **Resolves which runs to use for each page (legacy manual resolution).** (1 connections) — `src/pipeline/orchestrator.py`
- **Filtering helpers for blank/staff checks.** (1 connections) — `src/pipeline/steps/filters.py`

## Relationships

- [.run](run.md) (12 shared connections)
- [load_yaml](load_yaml.md) (7 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (6 shared connections)
- [run_full_pipeline.py](run_full_pipeline.py.md) (5 shared connections)
- [detection/orchestrator.py](detection-orchestrator.py.md) (5 shared connections)
- [test_issue264_phase_a_connector_geometry.py](test_issue264_phase_a_connector_geometry.py.md) (5 shared connections)
- [cnn_scoring.py](cnn_scoring.py.md) (5 shared connections)
- [images.py](images.py.md) (4 shared connections)
- [restored_orchestrator_batch_sr.py](restored_orchestrator_batch_sr.py.md) (3 shared connections)
- [dense_probe_candidate.py](dense_probe_candidate.py.md) (2 shared connections)
- [install_homr_skip_existing_guard](install_homr_skip_existing_guard.md) (2 shared connections)
- [hybrid.py](hybrid.py.md) (2 shared connections)

## Source Files

- `src/pipeline/core/config.py`
- `src/pipeline/detection/__init__.py`
- `src/pipeline/detection/utils.py`
- `src/pipeline/orchestrator.py`
- `src/pipeline/steps/filters.py`

## Audit Trail

- EXTRACTED: 107 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*