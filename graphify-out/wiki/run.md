# .run

> 27 nodes · cohesion 0.15

## Key Concepts

- **.run()** (24 connections) — `src/pipeline/orchestrator.py`
- **.run_base_numbering_and_barline_correction()** (17 connections) — `src/pipeline/orchestrator.py`
- **.run_final_numbering_and_overlays()** (17 connections) — `src/pipeline/orchestrator.py`
- **write_json()** (13 connections) — `src/pipeline/utils/io.py`
- **load_json()** (12 connections) — `src/pipeline/utils/io.py`
- **._run_pdf_to_images()** (11 connections) — `src/pipeline/orchestrator.py`
- **._review_package_config()** (10 connections) — `src/pipeline/orchestrator.py`
- **.run_mmr_batch_detection()** (10 connections) — `src/pipeline/orchestrator.py`
- **Path** (9 connections)
- **empty_numbering_payload()** (7 connections) — `src/pipeline/steps/numbering.py`
- **._materialize_review_package_if_requested()** (6 connections) — `src/pipeline/orchestrator.py`
- **._should_persist_pdf_images()** (6 connections) — `src/pipeline/orchestrator.py`
- **Any** (6 connections)
- **._resolved_for_manifest()** (5 connections) — `src/pipeline/orchestrator.py`
- **._validate_review_package_prerequisites()** (4 connections) — `src/pipeline/orchestrator.py`
- **Path** (4 connections)
- **write_manifest()** (4 connections) — `src/pipeline/utils/io.py`
- **.__init__()** (3 connections) — `src/pipeline/orchestrator.py`
- **Any** (3 connections)
- **Return whether rendered PDF pages must be written to run_dir images.** (1 connections) — `src/pipeline/orchestrator.py`
- **Executes the full pipeline.** (1 connections) — `src/pipeline/orchestrator.py`
- **Materialize the manual-correction review package when enabled.** (1 connections) — `src/pipeline/orchestrator.py`
- **Resolve the config-first review package output contract. This is intentionally…** (1 connections) — `src/pipeline/orchestrator.py`
- **Phase A: Base Numbering & Barline Correction.** (1 connections) — `src/pipeline/orchestrator.py`
- **Phase B: MMR Batch Detection.** (1 connections) — `src/pipeline/orchestrator.py`
- *... and 2 more nodes in this community*

## Relationships

- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (19 shared connections)
- [PipelineOrchestrator](PipelineOrchestrator.md) (11 shared connections)
- [load_image](load_image.md) (7 shared connections)
- [score_candidates_batch.py](score_candidates_batch.py.md) (7 shared connections)
- [steps/numbering.py](steps-numbering.py.md) (7 shared connections)
- [Score](Score.md) (5 shared connections)
- [Barline](Barline.md) (4 shared connections)
- [pdf_to_images.py](pdf_to_images.py.md) (3 shared connections)
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) (2 shared connections)
- [run_stage_e_full_pipeline.py](run_stage_e_full_pipeline.py.md) (2 shared connections)
- [materialize_manual_correction_review_package](materialize_manual_correction_review_package.md) (1 shared connections)
- [run_detection_step](run_detection_step.md) (1 shared connections)

## Source Files

- `src/pipeline/orchestrator.py`
- `src/pipeline/steps/numbering.py`
- `src/pipeline/utils/io.py`

## Audit Trail

- EXTRACTED: 123 (98%)
- INFERRED: 3 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*