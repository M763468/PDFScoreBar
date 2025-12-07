# Model Survey Plan: Evaluation Phase

**Date**: Dec 2025
**Status**: In Progress - OMR-DLN Complete
**Branch**: `feature/barline_model_experiments`

---

## 1. Overview
We have transitioned from heuristic optimization to **Model Survey Mode**. The goal is to determine if **Zero-Shot** or **Pretrained** Computer Vision models can outperform our `homr` baseline (152 TP / 30 FP) without the need for immediate training or dataset creation.

## 2. Candidate Models (Prioritized)

| Priority | Model Family | Repository | Strategy |
| :--- | :--- | :--- | :--- |
| **1** | **OMR-DLN (YOLOv8)** | [dmgonzalez8/OMR](https://github.com/dmgonzalez8/OMR) | **Pretrained Detector**. Use model fine-tuned on DeepScoresV2. |
| **2** | **YOLO-World** | [ultralytics/ultralytics](https://github.com/ultralytics/ultralytics) | **Zero-Shot Detection**. Prompt model with "barline", "vertical line". |
| **3** | **Grounding DINO** | [IDEA-Research/GroundingDINO](https://github.com/IDEA-Research/GroundingDINO) | **Open-set Object Detection**. Best-in-class zero-shot performance. |
| **4** | **Homr (Tuned)** | [liebharc/homr](https://github.com/liebharc/homr) | **Baseline**. Continue to use as reference. |

*Note: Standard COCO detectors (YOLOv8, Mask R-CNN) are unlikely to work without training. We prioritize Open-Vocabulary models.*

## 3. Evaluation Checklist

### OMR-DLN (YOLOv8) (Complete ✓)
- [x] **Setup**: Clone repo `dmgonzalez8/OMR` to `external/omr_dln`.
- [x] **Setup**: Create venv and install dependencies (`ultralytics`).
- [x] **Setup**: Locate and download pretrained weights from repository's Google Drive link.
- [x] **Experiment**:
    - Input: `data/evaluation/images/page_3.png`
    - Model: YOLOv8m trained on DeepScoresV2 for measure detection.
    - Confidence Threshold: 0.25
- [x] **Analysis**:
    - Visual Inspection: Overlay boxes on image.
    - Quantitative: Compute precision/recall against `page_3` GT.
- [x] **Report**: Document findings in `experiments/models/omr_dln/README.md`.

**Result Summary**: Achieved high precision (0.890) with significantly reduced FPs (17), but introduced 15 FNs (recall 0.901), making it unsuitable as a standalone replacement for measure numbering without 100% recall.

### YOLO-World (Complete ✓)
- [x] **Setup**: Clone repo to `external/`, install dependencies.
- [x] **Sanity Check**: Run on a simple demo image to verify installation.
- [x] **Experiment**:
    - Input: `data/evaluation/images/page_3.png`
    - Prompts: `["barline", "vertical line", "measure line"]`
    - Confidence Threshold: 0.05
- [x] **Analysis**:
    - Visual Inspection: Overlay boxes on image.
    - Quantitative: Compute precision/recall against `page_3` GT.
- [x] **Report**: Document findings in `experiments/models/yolo_world/README.md`.

**Result**: **FAILED** - 0% Recall (0/152 detected). Zero-shot does not work for this domain.

---

## 4. Testing Methodology

### Input Data
- **Image**: `data/evaluation/images/page_3.png` (The "difficult" page with 30 FPs).
- **Ground Truth**: `data/evaluation/annotations/page_003/boxes_sorted.json`.

### Metrics
- **Recall**: Must be **100% (152/152)** to be viable.
- **Precision**: Higher is better. Target < 30 False Positives.
- **IoU**: Intersection over Union >= 0.5 (or relaxed vertical overlap).

### Failure Condition
If a model fails to detect simple barlines (Recall < 50%) or hallucinates wildly (FP > 100) even with prompt tuning, it is marked as **"Requires Training"** and we move to the next candidate.

---

## 5. Results Summary

### YOLO-World (YOLOv8x-Worldv2)
- **Status**: ✗ **FAILED** (Zero-Shot)
- **Recall**: 0.0% (0/152)
- **Precision**: 0.0%
- **Conclusion**: Zero-shot transfer from natural images to music notation is ineffective. Fine-tuning required.
- **Report**: [`experiments/models/yolo_world/README.md`](../../experiments/models/yolo_world/README.md)

---

**Next Step**: Evaluate **Grounding DINO** or conduct controlled sanity checks on YOLO-World configuration.
