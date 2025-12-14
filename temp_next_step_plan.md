# Next Steps Plan

> [!IMPORTANT]
> **Documentation Policy**: Documentation (e.g., `docs/DEVELOPMENT_LOG.md`, `docs/ENVIRONMENTS.md`) must be updated proactively whenever new scripts, findings, or artifacts are produced.

## Phase 1: Pipeline Setup & Documentation
**Goal**: Finalize the automation script and update environment docs.

1.  **Finalize Script**:
    -   [x] Make executable: `chmod +x tools/run_hybrid_pipeline.sh`
2.  **Documentation**:
    -   [x] Update `docs/ENVIRONMENTS.md`:
        -   Add "Hybrid Pipeline" section.
        -   Document usage: `tools/run_hybrid_pipeline.sh --image <path> --run-id <id> [--gt <path>]`.

## Phase 2: Robustness Verification (Generalization)
**Goal**: Verify hybrid method robustness on unseen data (Qualitative Evaluation).
*Note: These targets lack Ground Truth, so metrics will not be calculated. Focus on visual overlay review.*

1.  **Data Preparation (New PDF)**:
    -   [x] Convert `data/evaluation/pdfs/Va_Prokofiev_Symphony1.pdf` to images.
    -   Command:
        ```bash
        python src/pdf_to_images.py \
            --pdf data/evaluation/pdfs/Va_Prokofiev_Symphony1.pdf \
            --output-dir data/evaluation/images/Va_Prokofiev_Symphony1 \
            --prefix page
        ```
    -   Target: Page 2 and 3 (index 1 and 2).

2.  **Execution (Hybrid Pipeline)**:
    -   [x] **Target A (Page 10)**:
        -   [x] Start OMR inference (background).
        -   [x] Wait for completion.
        -   [x] Verify `logs/hybrid_generalization/page_10_hybrid_test/`.
        ```bash
        ./tools/run_hybrid_pipeline.sh \
            --image data/training/images/page_10.png \
            --run-id page_10_hybrid_test
        ```
    -   [ ] **Target B (Training Set)**: `data/training/images/page_15.png`
        ```bash
        ./tools/run_hybrid_pipeline.sh \
            --image data/training/images/page_15.png \
            --run-id page_15_hybrid_test
        ```
    -   [ ] **Target C (New PDF)**: `data/evaluation/images/Va_Prokofiev_Symphony1/page_002.png`
        ```bash
        ./tools/run_hybrid_pipeline.sh \
            --image data/evaluation/images/Va_Prokofiev_Symphony1/page_002.png \
            --run-id prokofiev_p2_hybrid_test
        ```


## Phase 3: Deep FP Analysis (Staff Consistency)
**Goal**: Eliminate remaining FPs (e.g., 8 on `page_3`) using global staff system consistency.

1.  **Investigation**:
    -   [ ] Analyze `homr`'s internal data structures (`predictions.staff`, `predictions.bar_lines`) to understand how to reliably group barlines by system.
2.  **Implementation**:
    -   [x] Create `experiments/fp_reduction/analyze_staff_consistency.py`.
    -   **Logic**:
        -   Group candidate barlines by Staff System.
        -   Calculate linear regression (or simple statistics) of Top/Bottom Y-coordinates for the system.
        -   Reject candidates that deviate significantly (> threshold) from the system's vertical span trend.

3.  **Evaluation**:
    -   [x] Run on `page_3` (with GT) to measure FP reduction vs Recall loss. (Alignment Diagnosed: See diagnosis_report.md)
    -   [ ] Run on Phase 2 images (qualitative) to ensure no regressions on valid barlines.

## Phase 4: Future Optimization (Deferred)
*See `docs/notes/technical_debt.md`.*