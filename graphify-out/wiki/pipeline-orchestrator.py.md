# pipeline/orchestrator.py

> 25 nodes · cohesion 0.15

## Key Concepts

- **pipeline/orchestrator.py** (44 connections) — `src/pipeline/orchestrator.py`
- **get_nested()** (31 connections) — `src/pipeline/core/config.py`
- **filters.py** (12 connections) — `src/pipeline/steps/filters.py`
- **detection/utils.py** (8 connections) — `src/pipeline/detection/utils.py`
- **resolve_barlines_and_masks_config()** (8 connections) — `src/pipeline/detection/utils.py`
- **resolve_paths_from_detection()** (8 connections) — `src/pipeline/detection/utils.py`
- **resolve_page_filters()** (8 connections) — `src/pipeline/steps/filters.py`
- **_ReviewPackageConfig** (6 connections) — `src/pipeline/orchestrator.py`
- **is_blank_page()** (6 connections) — `src/pipeline/steps/filters.py`
- **apply_barline_overrides()** (5 connections) — `src/pipeline/steps/barlines.py`
- **normalize_barlines()** (5 connections) — `src/pipeline/steps/barlines.py`
- **get_user_exclude_indices()** (5 connections) — `src/pipeline/steps/filters.py`
- **Any** (5 connections)
- **staff_detect_failed()** (5 connections) — `src/pipeline/steps/filters.py`
- **._resolve_page_runs()** (4 connections) — `src/pipeline/orchestrator.py`
- **Path** (3 connections)
- **Any** (2 connections)
- **Path** (2 connections)
- **Any** (2 connections)
- **Utility functions for path resolution and system monitoring in detection.** (1 connections) — `src/pipeline/detection/utils.py`
- **Resolves output paths for barlines and staff masks after detection.** (1 connections) — `src/pipeline/detection/utils.py`
- **Resolves paths based on configuration when detection is skipped.** (1 connections) — `src/pipeline/detection/utils.py`
- **Pipeline orchestration for end-to-end processing.** (1 connections) — `src/pipeline/orchestrator.py`
- **Resolves which runs to use for each page (legacy manual resolution).** (1 connections) — `src/pipeline/orchestrator.py`
- **Filtering helpers for blank/staff checks.** (1 connections) — `src/pipeline/steps/filters.py`

## Relationships

- [.run](run.md) (19 shared connections)
- [load_image](load_image.md) (11 shared connections)
- [run_stage_e_full_pipeline.py](run_stage_e_full_pipeline.py.md) (8 shared connections)
- [run_detection_step](run_detection_step.md) (6 shared connections)
- [pdf_to_images.py](pdf_to_images.py.md) (4 shared connections)
- [steps/numbering.py](steps-numbering.py.md) (3 shared connections)
- [score_candidates_batch.py](score_candidates_batch.py.md) (3 shared connections)
- [Score](Score.md) (3 shared connections)
- [manual_corrections.py](manual_corrections.py.md) (3 shared connections)
- [PipelineOrchestrator](PipelineOrchestrator.md) (3 shared connections)
- [cnn_scoring.py](cnn_scoring.py.md) (3 shared connections)
- [detection/orchestrator.py](detection-orchestrator.py.md) (2 shared connections)

## Source Files

- `src/pipeline/core/config.py`
- `src/pipeline/detection/utils.py`
- `src/pipeline/orchestrator.py`
- `src/pipeline/steps/barlines.py`
- `src/pipeline/steps/filters.py`

## Audit Trail

- EXTRACTED: 126 (97%)
- INFERRED: 4 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*