
# Next Steps Plan

> [!IMPORTANT]
> **Documentation Policy**: Documentation (e.g., `docs/DEVELOPMENT_LOG.md`, `docs/ENVIRONMENTS.md`) must be updated proactively whenever new scripts, findings, or artifacts are produced, even if not explicitly listed as a step.

## Phase 1: Simple Hybrid Pipeline Scripts
**Goal**: Automate the current multi-step hybrid process for easier testing.

1.  **Create `tools/run_hybrid_pipeline.sh`**:
    -   Sequential execution of: `homr` (Baseline) -> `homr` (SR) -> `OMR-DLN` (SR) -> `generate_hybrid_results.py`.
    -   Inputs: Image Path, Run ID/Output Dir.
2.  **Documentation**:
    -   Update `docs/ENVIRONMENTS.md` with the location and usage of this new script.

## Phase 2: Preliminary Generalization
**Goal**: Verify hybrid method robustness on unseen data.

1.  **Prepare Targets**:
    -   **Training Set**: Use `data/training/images/page_10.png` and `page_15.png`.
    -   **New PDF**: Run `src/pdf_to_images.py` on `data/evaluation/pdfs/Va_Prokofiev_Symphony1.pdf` to generate test images (Pick 1-2 pages, excluding title/blank pages).
2.  **Run Pipeline**:
    -   Execute `run_hybrid_pipeline.sh` on the selected images.
    -   Output maps to `logs/hybrid_generalization/<image_name>`.
3.  **Manual Review**:
    -   User visualizes outputs (overlays).
    -   Log observations (success/failure) in `docs/DEVELOPMENT_LOG.md`.

## Phase 3: Deep FP Analysis
**Goal**: Eliminate remaining FPs (e.g., 8 on `page_3`) using consistency logic.

1.  **Staff Line Consistency Experiment**:
    -   Script: `experiments/fp_reduction/analyze_staff_consistency.py`.
    -   Logic: Group barlines by system; reject outliers that deviate from the system's top/bottom linear trend.
2.  **Evaluation**:
    -   Run on `page_3` and Phase 2 targets.
    -   Quantify FP reduction vs. Recall loss.
3.  **Documentation**:
    -   Record detailed findings, logic, and results in `docs/DEVELOPMENT_LOG.md`.

## Phase 4: Future Optimization (Deferred)
*See `docs/notes/technical_debt.md`.*