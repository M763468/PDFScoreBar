# .run

> 22 nodes · cohesion 0.17

## Key Concepts

- **.run()** (25 connections) — `src/pipeline/orchestrator.py`
- **.run_base_numbering_and_barline_correction()** (17 connections) — `src/pipeline/orchestrator.py`
- **.run_final_numbering_and_overlays()** (17 connections) — `src/pipeline/orchestrator.py`
- **._run_pdf_to_images()** (11 connections) — `src/pipeline/orchestrator.py`
- **._review_package_config()** (10 connections) — `src/pipeline/orchestrator.py`
- **.run_mmr_batch_detection()** (10 connections) — `src/pipeline/orchestrator.py`
- **Path** (9 connections)
- **._materialize_review_package_if_requested()** (6 connections) — `src/pipeline/orchestrator.py`
- **._should_persist_pdf_images()** (6 connections) — `src/pipeline/orchestrator.py`
- **Any** (6 connections)
- **._resolved_for_manifest()** (5 connections) — `src/pipeline/orchestrator.py`
- **get_image_cache()** (5 connections) — `src/pipeline/utils/images.py`
- **._validate_review_package_prerequisites()** (4 connections) — `src/pipeline/orchestrator.py`
- **.__init__()** (3 connections) — `src/pipeline/orchestrator.py`
- **Return whether rendered PDF pages must be written to run_dir images.** (1 connections) — `src/pipeline/orchestrator.py`
- **Executes the full pipeline.** (1 connections) — `src/pipeline/orchestrator.py`
- **Materialize the manual-correction review package when enabled.** (1 connections) — `src/pipeline/orchestrator.py`
- **Resolve the config-first review package output contract. This is intentionally…** (1 connections) — `src/pipeline/orchestrator.py`
- **Phase A: Base Numbering & Barline Correction.** (1 connections) — `src/pipeline/orchestrator.py`
- **Phase B: MMR Batch Detection.** (1 connections) — `src/pipeline/orchestrator.py`
- **Phase C: Final Numbering & Overlays.** (1 connections) — `src/pipeline/orchestrator.py`
- **Step 1: Convert PDF to images in-process.** (1 connections) — `src/pipeline/orchestrator.py`

## Relationships

- [get_nested](get_nested.md) (12 shared connections)
- [PipelineOrchestrator](PipelineOrchestrator.md) (11 shared connections)
- [load_json](load_json.md) (7 shared connections)
- [run_mmr_batch](run_mmr_batch.md) (5 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (5 shared connections)
- [Score](Score.md) (5 shared connections)
- [images.py](images.py.md) (3 shared connections)
- [MMRProcessor](MMRProcessor.md) (2 shared connections)
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) (2 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (2 shared connections)
- [diagnose_phase_b_layout_divergence.py](diagnose_phase_b_layout_divergence.py.md) (2 shared connections)
- [cnn_scoring.py](cnn_scoring.py.md) (2 shared connections)

## Source Files

- `src/pipeline/orchestrator.py`
- `src/pipeline/utils/images.py`

## Audit Trail

- EXTRACTED: 100 (97%)
- INFERRED: 3 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*