# .run

> 21 nodes · cohesion 0.18

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

- [PipelineOrchestrator](PipelineOrchestrator.md) (11 shared connections)
- [get_nested](get_nested.md) (10 shared connections)
- [load_image](load_image.md) (6 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (5 shared connections)
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) (5 shared connections)
- [load_json](load_json.md) (4 shared connections)
- [write_json](write_json.md) (3 shared connections)
- [diagnose_phase_b_layout_divergence.py](diagnose_phase_b_layout_divergence.py.md) (3 shared connections)
- [pdf_to_images.py](pdf_to_images.py.md) (3 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (2 shared connections)
- [Staff](Staff.md) (2 shared connections)
- [materialize_manual_correction_review_package](materialize_manual_correction_review_package.md) (1 shared connections)

## Source Files

- `src/pipeline/orchestrator.py`

## Audit Trail

- EXTRACTED: 97 (97%)
- INFERRED: 3 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*