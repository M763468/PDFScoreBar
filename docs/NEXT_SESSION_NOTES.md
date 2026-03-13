# Next Session Notes: Full Pipeline Workflow & Optimization

**Last Updated**: 2026-01-24
**Current Phase**: Full pipeline integration & Batch processing optimization

---

## 1. Current Status (2026-01-24)

### Pipeline Optimization (from feature/pipeline_optimization)
- **Proxy Inference Strategy**: Implemented and verified (Phase 2).
    - Segnet ~66x speedup, TrOmr ~6.5x speedup. Inference is no longer the bottleneck.
- **Real-ESRGAN Tuning (Phase 5A)**: Completed.
    - **Optimal Config**: `tile=512` (Auto) + `fp16` is the best balance for RTX 4060 (8GB).
    - **CLI Control**: Added `--sr-tile`, `--sr-tile-pad`, `--sr-fp32` to `homr_evaluator.py`.
- **SR Reuse Validation (Phase 4)**: Verified.
    - Caching SR images saves ~54s/page for large scores.

### Full Pipeline Planning (from plan/full_pipeline_workflow)
- `tools/run_full_pipeline.py`: Created a config-driven orchestrator.
- **Workflow Defined**: Ingest -> Barline Detection (Hybrid) -> Measure Numbering -> MMR Detection -> Final Export.
- **Detection Integration**: Updated orchestrator to invoke the full hybrid detection sequence (Docker `run_hybrid_pipeline.sh` + Host scripts).

---

## 2. Tasks & Strategy (Combined)

### Phase 5B: Batch Processing Architecture (Implementation Target)
**Goal**: Consolidate the "Python Loop" optimization into the "End-to-End Orchestrator".
- **Reason**: The orchestrator is the natural place to handle batch processing and model persistence (loading SR/Homr models once).
- **Tasks**:
    *   [ ] **Orchestrator Logic**: Ensure `tools/run_full_pipeline.py` effectively manages the batch loop.
    *   [ ] **Model Persistence**: Modify underlying scripts (`homr_evaluator.py`, `eval_omr_dln.py`) or the orchestrator to keep models in VRAM across images if possible, or organize the batch to minimize reload overhead (e.g. process all SR -> process all Homr).
    *   [ ] **Memory Management**: Implement explicit `gc.collect()` and `torch.cuda.empty_cache()` calls between large batch steps.

### Full Pipeline Integration
*   [ ] **End-to-End Verification**: Run the full pipeline on `evaluation2` dataset using the optimized SR settings.
*   [ ] **User Correction**: Implement/Verify the data contracts for barline and MMR overrides.

---

## 3. Reference: Pipeline Configuration

### Config Structure (Draft)
```yaml
run:
  run_id: "2026-01-24_demo"
  output_root: "logs/full_pipeline_runs"
inputs:
  pdf_path: "data/scores/demo/score.pdf"
  # ... (omitted details, see docs/FULL_PIPELINE_README.md)
steps:
  pdf_to_images: true
  filter_pages: true
  apply_barline_overrides: true
  numbering_base: true
  mmr_overrides: true
  apply_measure_overrides: true
  overlay: false
```

### Optimization Reference
*   **SR Tiling**: Default to `tile=512`. Use `tile=0` only for small images if needed (auto-handled).
*   **Precision**: Always use `fp16` on CUDA.

---

## 4. Immediate Pitfalls
- Do **not** reuse `logs/hybrid_generalization` outputs for the target full-pipeline run; let the pipeline generate fresh artifacts to ensure consistency.
- Toy Symphony PDF has cover/blank pages; expect blank filtering and page mapping issues.