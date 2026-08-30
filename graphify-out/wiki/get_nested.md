# get_nested

> 26 nodes · cohesion 0.15

## Key Concepts

- **get_nested()** (31 connections) — `src/pipeline/core/config.py`
- **.run()** (25 connections) — `src/pipeline/orchestrator.py`
- **.run_base_numbering_and_barline_correction()** (17 connections) — `src/pipeline/orchestrator.py`
- **.run_final_numbering_and_overlays()** (17 connections) — `src/pipeline/orchestrator.py`
- **._run_pdf_to_images()** (11 connections) — `src/pipeline/orchestrator.py`
- **._review_package_config()** (10 connections) — `src/pipeline/orchestrator.py`
- **.run_mmr_batch_detection()** (10 connections) — `src/pipeline/orchestrator.py`
- **resolve_barlines_and_masks_config()** (9 connections) — `src/pipeline/detection/utils.py`
- **Path** (9 connections)
- **._materialize_review_package_if_requested()** (6 connections) — `src/pipeline/orchestrator.py`
- **._should_persist_pdf_images()** (6 connections) — `src/pipeline/orchestrator.py`
- **Any** (6 connections)
- **._resolved_for_manifest()** (5 connections) — `src/pipeline/orchestrator.py`
- **._resolve_page_runs()** (4 connections) — `src/pipeline/orchestrator.py`
- **._validate_review_package_prerequisites()** (4 connections) — `src/pipeline/orchestrator.py`
- **.__init__()** (3 connections) — `src/pipeline/orchestrator.py`
- **Resolves paths based on configuration when detection is skipped.** (1 connections) — `src/pipeline/detection/utils.py`
- **Resolves which runs to use for each page (legacy manual resolution).** (1 connections) — `src/pipeline/orchestrator.py`
- **Return whether rendered PDF pages must be written to run_dir images.** (1 connections) — `src/pipeline/orchestrator.py`
- **Executes the full pipeline.** (1 connections) — `src/pipeline/orchestrator.py`
- **Materialize the manual-correction review package when enabled.** (1 connections) — `src/pipeline/orchestrator.py`
- **Resolve the config-first review package output contract. This is intentionally…** (1 connections) — `src/pipeline/orchestrator.py`
- **Phase A: Base Numbering & Barline Correction.** (1 connections) — `src/pipeline/orchestrator.py`
- **Phase B: MMR Batch Detection.** (1 connections) — `src/pipeline/orchestrator.py`
- **Phase C: Final Numbering & Overlays.** (1 connections) — `src/pipeline/orchestrator.py`
- *... and 1 more nodes in this community*

## Relationships

- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (15 shared connections)
- [PipelineOrchestrator](PipelineOrchestrator.md) (12 shared connections)
- [test_issue264_phase_a_connector_geometry.py](test_issue264_phase_a_connector_geometry.py.md) (7 shared connections)
- [filters.py](filters.py.md) (7 shared connections)
- [load_json](load_json.md) (7 shared connections)
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) (5 shared connections)
- [Score](Score.md) (5 shared connections)
- [run_full_pipeline.py](run_full_pipeline.py.md) (4 shared connections)
- [load_yaml](load_yaml.md) (4 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (3 shared connections)
- [pdf_to_images.py](pdf_to_images.py.md) (3 shared connections)
- [dense_probe_candidate.py](dense_probe_candidate.py.md) (2 shared connections)

## Source Files

- `src/pipeline/core/config.py`
- `src/pipeline/detection/utils.py`
- `src/pipeline/orchestrator.py`

## Audit Trail

- EXTRACTED: 130 (98%)
- INFERRED: 3 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*