# get_nested

> 34 nodes · cohesion 0.12

## Key Concepts

- **get_nested()** (31 connections) — `src/pipeline/core/config.py`
- **.run()** (25 connections) — `src/pipeline/orchestrator.py`
- **.run_base_numbering_and_barline_correction()** (17 connections) — `src/pipeline/orchestrator.py`
- **.run_final_numbering_and_overlays()** (17 connections) — `src/pipeline/orchestrator.py`
- **filters.py** (12 connections) — `src/pipeline/steps/filters.py`
- **._review_package_config()** (10 connections) — `src/pipeline/orchestrator.py`
- **.run_mmr_batch_detection()** (10 connections) — `src/pipeline/orchestrator.py`
- **resolve_barlines_and_masks_config()** (9 connections) — `src/pipeline/detection/utils.py`
- **Path** (9 connections)
- **resolve_page_filters()** (8 connections) — `src/pipeline/steps/filters.py`
- **empty_numbering_payload()** (7 connections) — `src/pipeline/steps/numbering.py`
- **._materialize_review_package_if_requested()** (6 connections) — `src/pipeline/orchestrator.py`
- **._should_persist_pdf_images()** (6 connections) — `src/pipeline/orchestrator.py`
- **Any** (6 connections)
- **_ReviewPackageConfig** (6 connections) — `src/pipeline/orchestrator.py`
- **is_blank_page()** (6 connections) — `src/pipeline/steps/filters.py`
- **._resolved_for_manifest()** (5 connections) — `src/pipeline/orchestrator.py`
- **get_user_exclude_indices()** (5 connections) — `src/pipeline/steps/filters.py`
- **Any** (5 connections)
- **staff_detect_failed()** (5 connections) — `src/pipeline/steps/filters.py`
- **._resolve_page_runs()** (4 connections) — `src/pipeline/orchestrator.py`
- **._validate_review_package_prerequisites()** (4 connections) — `src/pipeline/orchestrator.py`
- **.__init__()** (3 connections) — `src/pipeline/orchestrator.py`
- **Path** (3 connections)
- **Resolves paths based on configuration when detection is skipped.** (1 connections) — `src/pipeline/detection/utils.py`
- *... and 9 more nodes in this community*

## Relationships

- [load_image](load_image.md) (12 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (11 shared connections)
- [PipelineOrchestrator](PipelineOrchestrator.md) (11 shared connections)
- [load_json](load_json.md) (10 shared connections)
- [test_issue264_phase_a_connector_geometry.py](test_issue264_phase_a_connector_geometry.py.md) (7 shared connections)
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) (6 shared connections)
- [load_yaml](load_yaml.md) (5 shared connections)
- [run_mmr_batch](run_mmr_batch.md) (5 shared connections)
- [detection/__init__.py](detection-__init__.py.md) (3 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (3 shared connections)
- [diagnose_phase_b_layout_divergence.py](diagnose_phase_b_layout_divergence.py.md) (3 shared connections)
- [score_candidates_batch.py](score_candidates_batch.py.md) (3 shared connections)

## Source Files

- `src/pipeline/core/config.py`
- `src/pipeline/detection/utils.py`
- `src/pipeline/orchestrator.py`
- `src/pipeline/steps/filters.py`
- `src/pipeline/steps/numbering.py`

## Audit Trail

- EXTRACTED: 153 (96%)
- INFERRED: 7 (4%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*