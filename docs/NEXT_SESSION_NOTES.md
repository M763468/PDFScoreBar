# Next Session Notes: FP Reduction & Pipeline Refinement

**Last Updated**: 2026-01-06 (Post-GT Finalization)
**Current Phase**: Phase 9: False Positive Reduction & Hard Negative Mining

---
### Operational Rules
- **Do not overwrite** `docs/SESSION_LOG.md`. Append new findings.
- **Reproducibility**: Record commit hash + command + output path for all major results.

---

## 1. Project Goal & Current Status
**Goal**: Integrate the trained CNN Classifier (`ResNet18`) into the Hybrid Barline Detection Pipeline to eliminate remaining False Positives.

**Status Update (2026-01-06)**:
- **GT Completed**: Ground Truth for `evaluation2` (Prokofiev) has been manually verified and finalized.
    - Source: CNN-filtered "Peak-enabled" candidates.
    - Verified Pages: 25 pages (Prokofiev5, Va_Prokofiev_Symphony1).
    - Location: `data/evaluation2/annotations/{subdir}/{page_name}/boxes_sorted_v20260106.json`.

## 2. Immediate Tasks (Next Session)

### A. Hard Negative Mining (Priority 1)
**Objective**: Retrain the CNN model using "No Peak" candidates + Validated GT.
1.  **Generate Negatives**:
    - Use `expanded_candidates_nopeak.json` (need to generate for all 25 pages if not already done).
    - Compare against the **Finalized GT** (`boxes_sorted_v20260106.json`).
    - Candidates NOT in GT = **Hard Negatives**.
2.  **Dataset Augmentation**:
    - Create `cnn_classifier_v3_hardneg`.
    - Mix in the new hard negatives.
3.  **Retrain**:
    - Train ResNet18 on Dataset v3.

### B. Pipeline Finalization
- **Develop Production Script**: Create `inference_filter.py`.
- **Integration**: Update `run_hybrid_pipeline.sh`.

## 3. Reference Configs
- **Best Model (Current)**: `logs/cnn_barline_classification/training_resnet18_b320/cnn_classifier_best.pth`
- **Candidate Generator**: `experiments/cnn_classifier/generate_expanded_candidates.py`
- **Dataset Builder**: `tools/cnn_classifier/build_cnn_dataset.py`