# Next Session Notes

**Last Updated**: 2026-01-20
**Current Phase**: Full pipeline workflow implementation (image input -> measure numbering)

---
## Current Status (2026-01-20)
- The Phase 1 orchestrator (`tools/run_full_pipeline.py`) is **complete** and supports end-to-end processing.
- It integrates detection steps: Hybrid Detection (Docker) -> Probe Scan (Host) -> CNN Scoring (Host).
- It consumes PDF inputs and produces numbered measure JSONs and overlays.
- Reference log for changes: `docs/SESSION_LOG.md` (2026-01-20 entries).

### Implemented Pipeline Steps
1. **PDF to Images**: `src/pdf_to_images.py`
2. **Hybrid Detection**: `tools/run_hybrid_pipeline.sh` (inside Docker `sr_eval_gpu`).
   - Generates reliable candidates and **staff masks** (homr output).
3. **Probe Scan**: `tools/run_eval_experiment.py` (Host).
   - Uses Hybrid candidates and staff masks (new `--staff-mask-dir` support) to expand candidates.
4. **CNN Scoring**: `tools/cnn_classifier/score_candidates_batch.py` (Host).
   - Filters candidates using the trained CNN model.
5. **Measure Numbering**: `tools/add_measure_numbers.py`.
   - Uses filtered candidates and staff masks to assign measure numbers.
   - Supports MMR overrides and user corrections.

### Pending Validation
- The pipeline has been verified via `--validate-only` (dry-run logic).
- **Action Required**: Execute a full run on a real PDF (e.g., `data/evaluation/pdfs/おもちゃの交響曲_bass.pdf`) to verify:
  - Docker/Host file path handoffs.
  - Staff mask resolution in Probe Scan.
  - End-to-end numbering accuracy.

### Artifact Layout (Confirmed)
`logs/full_pipeline_runs/<run_id>/`
- `inputs/`: images (symlinks/copies).
- `intermediate/`:
  - `probe_scan/`: Results from Probe Scan and CNN Scoring.
  - `page_XXX/`: Numbering intermediate files (barlines_corrected.json, overrides).
- `outputs/`: Final JSONs and overlays.
- `manifest.json`: Full execution record.

## Goal
Validate and refine the end-to-end pipeline using real data.

## Next Actions
1. **Full Run Verification**: Run `tools/run_full_pipeline.py` on a target PDF.
2. **Parameter Tuning**: Adjust detection thresholds (ink, CNN score) based on results.
3. **User Correction UI**: Implement the data contract for `barline_overrides.json` and `overrides.json` in a UI or helper script.