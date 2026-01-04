# Next Session Notes: NN Classifier Integration

**Last Updated**: 2026-01-04 (Post-Training)
**Current Phase**: Phase 8: Classifier Integration & Active Learning

---
### Operational Rules
- **Do not overwrite** `docs/SESSION_LOG.md`. Append new findings.
- **Reproducibility**: Record commit hash + command + output path for all major results.

---

## 1. Project Goal & Current Status
**Goal**: Integrate the trained CNN Classifier (`ResNet18`) into the Hybrid Barline Detection Pipeline to eliminate remaining False Positives.

**Status**:
- **Dataset**: `cnn_classifier_final_v2_fixed` (Repaired & Valid).
- **Model**: Trained ResNet18 (`logs/cnn_barline_classification/training_resnet18_b320/cnn_classifier_best.pth`) achieving **F1=1.0** on validation.
- **Code**: `train.py` is fully optimized (AdamW, CosineAnnealing, AMP).

## 2. Immediate Tasks (Next Session)

### A. Inference Pipeline Integration
**Objective**: Create a Python script (`inference_filter.py` or similar) that uses the trained model to filter candidate boxes.
1.  **Input**:
    - Original Image (Page image).
    - Candidate Boxes (JSON from Hybrid Pipeline, e.g., `fp_boxes.json` or `geom_kept.json`).
2.  **Process**:
    - Load Model (`resnet18`).
    - Crop & Transform (Must match training transforms: Resize 256x128, Normalize).
    - Batch Inference.
3.  **Output**:
    - Filtered JSON (Candidates with `score > threshold`).
    - Visualization (Overlay of Accepted vs Rejected).

### B. Active Learning (Hard Negative Mining)
**Objective**: Challenge the "Perfect F1" score by running the model on raw geometric candidates (`geom_kept.json`) from *all* available pages (including those not in training if available).
1.  **Run Inference**: Apply model to `geom_kept.json` (high recall, low precision source).
2.  **Identify Failures**:
    - **False Positives**: High score (> 0.9) but NOT a barline (Visual check).
    - **False Negatives**: Low score (< 0.1) but IS a barline (Visual check).
3.  **Feedback**: Add these "Hard" cases to the dataset (new `hard_negatives` folder) and retrain.

### C. Pipeline Finalization
- **Replace/Augment**: Decide where to insert the CNN filter in `run_hybrid_pipeline.sh`.
    - Likely *after* geometric filtering (`probe_bar_candidates.py`) and *before* final formatting.

## 3. Reference Configs
- **Best Model**: `logs/cnn_barline_classification/training_resnet18_b320/cnn_classifier_best.pth`
- **Config**: `experiments/cnn_classifier/config.yaml`
- **Dataset**: `datasets/cnn_classifier_final_v2_fixed`