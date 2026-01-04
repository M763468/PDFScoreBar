# Next Session Notes: NN Classifier

**Last Updated**: 2026-01-04
**Current Phase**: Phase 7: Deep Learning Classifier (Post-Processing)

---
### Operational Rules
- **Do not overwrite** `docs/SESSION_LOG.md`. Append new findings.
- **Reproducibility**: Record commit hash + command + output path for all major results.
- **Parameters**: Explicitly record implicit parameters (e.g. `probe_endpoint_x_scale`).

---

## 1. Project Goal & Current Status
**Goal**: Train a lightweight CNN Classifier (`MobileNetV3` or similar) to verify candidate barlines and reject False Positives (FPs) that rule-based filters cannot handle (stems, text fragments, double bars).

**Status**:
- **Dataset**: `cnn_classifier_final_v2_fixed` is building (DeepScores Dense + Local FPs from `fp_boxes.json` + Rebuilt GT).
- **Training Code**: Basic `train.py` exists but lacks critical features for this specific task (Imbalance handling, Augmentation).
- **Previous Phase**: Hybrid Pipeline (Phase 6) achieved FN=0 but stalled at ~100 FPs/page. Shifted to CNN for final precision.

## 2. Immediate Tasks (Next Session)
**Priority**: Implement### A. Training Code Refactoring (`experiments/cnn_classifier/train.py`)
> [!WARNING]
> Training on `/mnt/` (Windows drives) is unstable with high parallelism (Errno 19).
> **Strongly Recommended**: Move dataset to Linux native partition (`~/datasets/...`).
### B. Execute Training
1.  **Command** (Optimized for SSD + VRAM, running on WSL Native):
    ```bash
    # Assuming dataset is moved to ~/datasets/cnn_classifier_final_v2_fixed
    CNN_DATASET_ROOT=~/datasets/cnn_classifier_final_v2_fixed \
    .venv_cnn_classifier/bin/python experiments/cnn_classifier/train.py \
    --model-name resnet18 \
    --epochs 30 \
    --batch-size 512 \
    --log-dir logs/cnn_final_res18 \
    --work-dir logs/cnn_final_res18
    ```
    *   **Note**: You can also use `--config experiments/cnn_classifier/config.yaml` to manage all advanced parameters (AMP, Compile, Imbalance, Augmentation, etc.).
    *   **Note**: `num_workers=8` and `pin_memory=True` are now default in `train.py` to faster loading.
2.  **Monitor**: check TensorBoard for F1-score convergence.
    - **Methods**:
        - `GaussianBlur`: Simulates ink bleed / low-res scanning.
        - `ColorJitter`: Simulates fading (low contrast/brightness).
        - **Custom Noise**: Add Gaussian/Impulse noise (salt-and-pepper) to simulate dirty scans.
        - **Morphology (Optional)**: Random `Erosion` (thinner/bumpy lines) or `Dilation` (ink spread) using OpenCV wrapper.
    - **Geometry Constraint**:
        - **Translate**: **Vertical ONLY** (`translate=(0, 0.1)`).
        - **Reason**: Task relies on "Center = Target". Horizontal shift risks validity (moving target off-center or bringing neighbor into focus).
        - **Rotation**: Keep small (`degrees=2`) or remove if X-shift risk is too high.
2.  **Class Imbalance Handling**:
    - **Issue**: TP (DeepScores) >> FP (Local Hard Negatives).
    - **Solution**: Implement `WeightedRandomSampler` or `pos_weight` in Loss function to prioritize FP rejection.
3.  **Metrics**:
    - Add `Precision`, `Recall`, `F1-Score` logging (TensorBoard). `Accuracy` is insufficient.
4.  **Model Config**:
    - Allow easy switching (argparse) between `MobileNetV3` (speed) and `ResNet18` (capacity).

### B. Training Execution
1.  **Baseline**: Train on `cnn_classifier_final_v2_fixed`.
2.  **Validation**: Evaluate on held-out pages (e.g., Page 001 if excluded, otherwise random split).
3.  **Integration**: Create inference script to plug into the pipeline (replacing/augmenting rule-based filters).

---

## 3. Historical Context & Baselines (Reference)

### A. Dataset Versions
- **v2 (Current)**:
    - **Source**: `fp_boxes.json` (Explicit "False Positives" from strict pipeline).
    - **Characteristics**: Sparse, high quality Hard Negatives.
- **v3 (Planned/Alternative)**:
    - **Source**: `geom_kept.json` (All geometric candidates - GT).
    - **Characteristics**: High volume (~4000 FPs), noisy but rich. Use if v2 generalization is poor.

### B. Phase 6: Hybrid Pipeline Performance
- **Baseline**: `20260102T134300_best_repro_fullparams` (Jan 2 run)
    - **Config**:
      ```bash
      PYTHONPATH=. .venv_pdf/bin/python tools/run_gt_rebuild_hybrid_eval.py \
      --output-root logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams \
      --union-root logs/phase5b_confirmed_union_eval \
      --endpoint-ratio-threshold 0.20 \
      --endpoint-x-scale 0.14 --endpoint-y-scale 0.80 \
      --notehead-open-kernel 5 --notehead-min-area 20 --notehead-dilate 7 \
      --notehead-max-aspect 2.0 --notehead-min-height 10 --notehead-max-width 6 \
      --probe-row-filter-mode bypass \
      --probe-notehead-dilate 13 --probe-endpoint-x-scale 0.04 --probe-endpoint-y-scale 0.80 \
      --probe-divisi-rescue --probe-divisi-dist-ratio 1.2 --probe-divisi-align-tol 10 --probe-divisi-align-min-count 2
      ```
    - **Metrics**: FN=0 (Recall 1.0) on all pages. FP Total=14 (P1=3, P3=2, P4=1, P10=0, P15=8).
    - **Conclusion**: This is the current best rule-based performance. Moving to CNN to check the remaining borderline cases and further robustify.

### C. LLM Experiments (Phase 6b)
- **Result**: Gemini 1.5 Flash showed promise but instability (TP rejection in strict modes, hallucination in loose modes).
- **Decision**: Deferred in favor of CNN. Reserved for final "Human-in-the-loop" review if needed.
