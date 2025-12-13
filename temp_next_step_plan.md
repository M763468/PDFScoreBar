# Work Plan for Next Session: Preprocessing and Hybrid Tuning

This plan outlines the next steps based on `docs/NEXT_SESSION_NOTES.md` to achieve the objective of minimizing False Positives (FPs) while strictly maintaining 100% Recall for barline detection, anchored by `homr`.

## Current Status:
- Barline FP Reduction is LOCALLY COMPLETE (30 FPs remaining).
- Previous attempts with Vertical Closing and Lightweight Super-Resolution (FSRCNN) have FAILED and been ABANDONED due to performance degradation.

## Primary Objective:
- Implement a hybrid detection method that minimizes False Positives (FPs) while strictly maintaining 100% Recall, anchored by `homr`.

## Detailed Plan:

### Track 1: Preprocessing Experiments

**Task 1.1: Advanced Super-Resolution Research and Integration (Based on 1.3 in NEXT_SESSION_NOTES)**
- **Goal:** Identify, integrate, and evaluate a state-of-the-art super-resolution (SR) model to improve image quality for `homr` and `OMR-DLN` without destructive side effects.
- **Subtasks:**
    1.  **Research SOTA SR Models:** Investigate models like Real-ESRGAN or others from SRZoo that provide high-quality output. Focus on models with established Python implementations or readily available pre-trained weights.
        -   *Deliverable:* Selection of a candidate SR model and identification of its repository/implementation details.
    2.  **Integrate SR Model:** Clone the selected SR model's repository into `external/` or otherwise integrate necessary components.
        -   *Deliverable:* SR model code/dependencies present in `external/`.
    3.  **Implement SR Function:** Create a new function (e.g., `apply_advanced_super_resolution`) in `src/common/preprocessing.py` or a dedicated script within `tools/` that utilizes the integrated SR model. This function should be configurable (e.g., for upscaling factors like x2, x4).
        -   *Deliverable:* New SR function available for use.
    4.  **Evaluate Advanced SR on `homr`:** Apply the new SR preprocessing to input images and evaluate its impact on `homr`'s performance (TP, FP, FN, Precision, Recall, F1). Test with different upscaling factors (x2, x4 if applicable).
        -   *Deliverable:* Evaluation logs and summary for `homr`.
    5.  **Evaluate Advanced SR on `OMR-DLN`:** Apply the new SR preprocessing to input images and evaluate its impact on `OMR-DLN`'s performance. Test with different upscaling factors (x2, x4 if applicable).
        -   *Deliverable:* Evaluation logs and summary for `OMR-DLN`.

**Task 1.2: Combined Approach (Advanced SR + Gentle Vertical Closing) (Based on 1.4 in NEXT_SESSION_NOTES)**
- **Goal:** If Advanced SR proves successful, explore its combination with a gentle vertical closing operation.
- **Subtasks:**
    1.  **Create Combined Pipeline:** Develop a processing pipeline that first applies the successful Advanced SR, and then a mild `apply_vertical_closing` (with `kernel_height` e.g., `[3, 5]`).
    2.  **Evaluate Combined Approach on `homr`:** Test the combined pipeline and evaluate its impact on `homr`'s performance.
    3.  **Evaluate Combined Approach on `OMR-DLN`:** Test the combined pipeline and evaluate its impact on `OMR-DLN`'s performance.
    -   *Pre-requisite:* Successful completion of Task 1.1.

### Track 2: Hybrid Method Parameter Tuning

**Task 2.1: Create Parameter Tuning Script (Based on 2.1 in NEXT_SESSION_NOTES)**
- **Goal:** Develop a script to systematically tune hybrid detector parameters.
- **Subtasks:**
    1.  **Develop `tune_hybrid_detector.py`:** Create `experiments/fp_reduction/tune_hybrid_detector.py`. This script should:
        -   Accept `homr` and `OMR-DLN` detection JSON files as input.
        -   Allow adjustment of `homr` confidence threshold, `OMR-DLN` confidence threshold, and IoU threshold for matching detections.
        -   Output `TP, FP, FN` for each parameter combination.
        -   *Deliverable:* Functional tuning script.

**Task 2.2: Execute Parameter Sweep (Based on 2.2 in NEXT_SESSION_NOTES)**
- **Goal:** Run a comprehensive parameter sweep to identify optimal hybrid configurations.
- **Subtasks:**
    1.  **Define Parameter Ranges:** Specify appropriate ranges and step sizes for confidence (e.g., 0.1 to 0.9, step 0.1) and IoU (e.g., 0.1 to 0.5, step 0.05).
    2.  **Execute Sweep:** Run `tune_hybrid_detector.py` for all defined parameter combinations.
        -   *Deliverable:* Comprehensive log of `TP, FP, FN` for all combinations.

**Task 2.3: Analyze Tuning Results (Based on 2.3 in NEXT_SESSION_NOTES)**
- **Goal:** Identify the optimal hybrid configuration that meets the objective.
- **Subtasks:**
    1.  **Filter for 100% Recall:** Identify all parameter combinations where `FN=0`.
    2.  **Select Lowest FP:** From the 100% recall set, select the combination with the lowest number of False Positives.
        -   *Deliverable:* Optimal hybrid parameters and their performance metrics.

### Documentation & Logging
- Ensure all logs and experimental outputs are saved in `logs/model_experiments/preprocessing_and_tuning/` with structured naming.
- Update `docs/NEXT_SESSION_NOTES.md` with findings and next steps upon completion of major tasks.