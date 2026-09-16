# Community 69

> 22 nodes · cohesion 0.17

## Key Concepts

- **.run()** (25 connections) — `src/pipeline/orchestrator.py`
- **.run_base_numbering_and_barline_correction()** (17 connections) — `src/pipeline/orchestrator.py`
- **.run_final_numbering_and_overlays()** (17 connections) — `src/pipeline/orchestrator.py`
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

- [Community 135](Community_135.md) (12 shared connections)
- [Community 80](Community_80.md) (11 shared connections)
- [Community 81](Community_81.md) (7 shared connections)
- [Community 16](Community_16.md) (5 shared connections)
- [Community 13](Community_13.md) (5 shared connections)
- [Community 12](Community_12.md) (4 shared connections)
- [Community 77](Community_77.md) (3 shared connections)
- [Community 153](Community_153.md) (3 shared connections)
- [Community 106](Community_106.md) (3 shared connections)
- [Community 169](Community_169.md) (2 shared connections)
- [Community 26](Community_26.md) (2 shared connections)
- [Community 10](Community_10.md) (2 shared connections)

## Source Files

- `src/pipeline/orchestrator.py`
- `src/pipeline/steps/numbering.py`

## Audit Trail

- EXTRACTED: 102 (97%)
- INFERRED: 3 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*