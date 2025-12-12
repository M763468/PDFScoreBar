# Next Session Notes

## Project Status: Barline FP Reduction
**Status**: **LOCALLY COMPLETE** (Dec 2025)

The optimization of visual heuristics for barline detection has concluded.
- **Heuristic 1 (Safe Filter)** is enabled.
- All other heuristics (H2-H5) are disabled.
- **Result**: 30 FPs remaining (irreducible without risking TPs).

## Documentation & Tools
- **Summary**: `docs/fp_reduction/FINAL_SUMMARY.md`
- **Logs**: `docs/fp_reduction/development_log.md`
- **Scripts**: `tools/fp_reduction/*.py`

## Recommended Next Sessions

### 2. Model Retraining Investigation
**Objective**: Analyze why the SegNet model fragments barlines.
**Action**: Check training data quality or experiment with varying the probability threshold (currently fixed).

### 3. External Model Evaluation
**Objective**: Benchmark other OMR libraries (e.g., commercially available APIs or newer research models) on `page_3`.

## Next Session – Preprocessing and Hybrid Tuning (Dec 2025)

### 1) Objective & Hypothesis
- **Objective**: Establish a hybrid detection method that minimizes False Positives (FPs) while strictly maintaining 100% Recall, anchored by `homr`.
- **Hypothesis**:
    1.  Image preprocessing (e.g., vertical closing, super-resolution) can improve the baseline performance of both `homr` (by reducing FPs from fragmented lines) and `OMR-DLN` (by reducing FNs from faint lines).
    2.  Systematically tuning the parameters of a hybrid `homr` + `OMR-DLN` model can yield a combination that surpasses the performance of either model alone.

### 2) Next-Session TODOs:

#### Track 1: Preprocessing Experiments (Revised)



-   `[X]` **1.1: Vertical Closing for homr & OMR-DLN.**

    -   **Status**: **FAILED & ABANDONED**.

    -   **Summary**: A series of experiments were run to apply vertical closing on both `homr` and `OMR-DLN`. This approach, which relied on binarization and morphological operations, was found to be fundamentally incompatible with both models, causing catastrophic failures (`No staffs found` or 0% recall) regardless of parameters.

    -   **Conclusion**: Applying aggressive, pixel-level morphological operations directly to the input image is not a viable strategy for these models.



-   `[X]` **1.2: Super-Resolution (Lightweight FSRCNN).**

    -   **Status**: **FAILED & ABANDONED (for lightweight SR)**.

    -   **Hypothesis**: Upscaling the input image using a super-resolution (SR) model can restore detail in faint/aliased lines without the destructive side effects of the previous approach, improving detection for both `homr` and `OMR-DLN`.

    -   **Activity Log**:

        -   **1.2.1**: Implemented lightweight SR function (`apply_super_resolution`) in `preprocessing.py` using OpenCV's `dnn_superres` module and a downloaded FSRCNN model.

        -   **1.2.2 (homr evaluation)**: FAILED. TP=92, FP=113, FN=60 (Precision=0.448, Recall=0.605, F1=0.515). Performance significantly degraded compared to the baseline (F1=0.897).

        -   **1.2.3 (OMR-DLN evaluation)**: FAILED. TP=135, FP=30, FN=17 (Precision=0.818, Recall=0.888, F1=0.851). Performance slightly degraded compared to the OMR-DLN baseline (F1=0.895).

    -   **Conclusion**: Lightweight super-resolution (OpenCV `dnn_superres` with `FSRCNN_x2`) failed to improve the performance of either `homr` or `OMR-DLN`. Both models experienced performance degradation or no improvement. This suggests that the generated high-frequency components might act as noise or alter crucial image characteristics that the models rely on.



-   `[ ]` **1.3: Advanced Super-Resolution (Next Step).**

    -   **Hypothesis**: While lightweight SR failed, a more sophisticated SR model (e.g., with better noise reduction or more accurate detail synthesis) might provide benefits.

    -   **Plan**:

        -   **1.3.1**: Research and select a state-of-the-art SR model (e.g., Real-ESRGAN from `https://github.com/xinntao/Real-ESRGAN` or a model from SRZoo) that is known for higher quality output.

        -   **1.3.2**: Clone the repository (if applicable) and integrate the model into `external/`.

        -   **1.3.3**: Implement a new SR function in `preprocessing.py` or a dedicated script to apply this advanced SR model.

        -   **1.3.4**: Evaluate this advanced SR preprocessing on `homr` and `OMR-DLN`.



-   `[ ]` **1.4: Combined Approach (Advanced SR + Vertical Closing).**

    -   **Hypothesis**: If advanced SR is successful (from `1.3`), the resulting higher-quality image may be more robust to a *gentle* vertical closing operation.

    -   **Plan**: If a successful advanced SR method is found, create a pipeline that applies SR first, then applies `apply_vertical_closing` with a mild `kernel_height` (e.g., `[3, 5]`), and evaluate on both `homr` and `OMR-DLN`.

#### Track 2: Hybrid Method Parameter Tuning
-   `[ ]` **2.1: Create a Parameter Tuning Script.**
    -   Create a new script: `experiments/fp_reduction/tune_hybrid_detector.py`.
    -   This script will take `homr` and `OMR-DLN` detection JSON files as input.
    -   It should allow adjusting:
        -   `homr` confidence score threshold.
        -   `OMR-DLN` confidence score threshold.
        -   IoU threshold for matching detections between the two models.
-   `[ ]` **2.2: Execute Parameter Sweep.**
    -   Define a range and step for each parameter (e.g., confidence from 0.1 to 0.9, step 0.1; IoU from 0.1 to 0.5, step 0.05).
    -   Run the tuning script, iterating through all parameter combinations.
    -   Log `TP, FP, FN` for each combination.
-   `[ ]` **2.3: Analyze Tuning Results.**
    -   Identify all parameter combinations that achieve 100% Recall (`FN=0`).
    -   From that set, find the combination that results in the lowest number of False Positives (FPs).

### 3) Documentation & Logging
-   All experimental outputs (detection JSONs, logs) will be saved to `logs/model_experiments/preprocessing_and_tuning/`.
-   Use a structured naming convention for log files to capture the parameters of each run (e.g., `run_closing_homr.log`, `run_tune_conf0.5_iou0.3.log`).
-   A final summary of findings will be added to this document upon completion.

### Explicit Notes for Future Work:
- Future work should treat `homr` as the “recall anchor”. Any new model or heuristic must **not** compromise 100% recall.
- External models like OMR-DLN should primarily be used as precision/FP filters, or as a source of high-confidence predictions that complement `homr`.
- We will NOT create new annotated datasets or do heavy retraining in the immediate next sessions. Focus remains on evaluating existing pretrained models and refining heuristic-based filtering.
