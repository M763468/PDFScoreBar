# Barline Detection – Model Evaluation Strategy (Revised Dec 2025)

This document outlines the strategic shift from heuristic-based optimization to **model-based evaluation** for barline detection. It focuses on the **Evaluation-Only** phase, where we benchmark external pretrained models against our current baseline.

---

## 1. Revised Objective & Scope

### Objective
Identify an external, pretrained computer vision model that achieves **higher precision** than the current baseline (Homr + Safe Filter) on `page_3`, specifically targeting the reduction of False Positives (< 30) while maintaining **100% Recall**.

### Scope
- **IN SCOPE**:
  - evaluating off-the-shelf, pretrained models.
  - using `page_3.png` as the primary benchmark.
  - developing wrapper scripts to adapt external model outputs to our metric format.
- **OUT OF SCOPE**:
  - Training models from scratch.
  - Fine-tuning models.
  - Creating new datasets or annotations.
  - Developing GUI annotation tools.

---

## 2. Selection Criteria for Candidate Models

Based on the [Models Comparison PDF](Barline%20Detection%20&%20Measure%20Numbering%20–%20Models%20Comparison.pdf), models are selected based on:

1.  **Vertical Element Detection**: Can it detect lines, fences, or vertical structures?
2.  **Pretrained Weights**: Must provide `pt`, `onnx`, or `pth` weights (COCO, Objects365, etc.).
3.  **Local Execution**: Must run in our Python/Linux environment (no cloud APIs).
4.  **License**: Permissive or GPL (acceptable for internal evaluation).

---

## 3. Prioritized Model List

We will evaluate the following models in order of priority.

### Priority 1: YOLOv8 (Ultralytics)
*   **Family**: Object Detection (Real-time).
*   **Repository**: [https://github.com/ultralytics/ultralytics](https://github.com/ultralytics/ultralytics)
*   **Why**: Best trade-off for speed and accuracy. Pretrained on COCO; classes like "background" or generic objects might not perfectly align, but we test if any generic edge/line detection capabilities transfer or if we can abuse a class.
    *   *Note*: Since we are not training, we might use **Zero-shot** capabilities (e.g. YOLO-World) if available, or just check standard detection filtering.
    *   *Correction*: Standard YOLOv8 detects COCO objects (person, car...). Without fine-tuning, standard YOLO will **FAIL** to detect barlines.
    *   *Pivot*: We will evaluate **YOLO-World** (Open Vocabulary Detection) if supported, or other "Open Set" detectors from the same repo. If not, this step will confirm "Training Required" and we stop.

### Priority 2: Detectron2 (Mask R-CNN)
*   **Family**: Instance Segmentation.
*   **Repository**: [https://github.com/facebookresearch/detectron2](https://github.com/facebookresearch/detectron2)
*   **Why**: High-quality segmentation baseline. We will check if any pretrained model behaves reasonably or if we need Keypoint detection features.

### Priority 3: DETR (DEtection TRansformer)
*   **Family**: Transformer-based Detection.
*   **Repository**: [https://github.com/facebookresearch/detr](https://github.com/facebookresearch/detr)
*   **Why**: Semantic understanding of scenes.

> **CRITICAL NOTE**: Almost all "Standard" pretrained models (COCO) will fail to detect "Barlines" without fine-tuning. This "Evaluation Only" phase is expected to confirm **which architectures handle the image domain best** or if **Open Vocabulary** models (like GLIP, Grounding DINO, YOLO-World) can work zero-shot.
> 
> **Recommendation**: We will prioritize **Zero-Shot / Open-Vocabulary** detectors (like YOLO-World) over standard YOLOv8, as they can search for "vertical line" or "barline" text prompts.

---

## 4. Evaluation Protocol

For each candidate model:

1.  **Clone & Setup**:
    - Clone repo to `external/<model_name>`.
    - Create a minimal python script `experiments/models/eval_<model>.py`.
2.  **Inference**:
    - Load pretrained weights (largest available, e.g., `yolov8x`).
    - Attempt **Zero-Shot detection** (if supported) with prompts: "barline", "vertical line", "staff line".
    - Run on `data/evaluation/images/page_3.png`.
3.  **Format Conversion**:
    - Convert output (Box/Mask) to JSON format compatible with `homr_evaluator`.
4.  **Metric Calculation**:
    - Run our standard evaluator to get TP/FP/FN.
5.  **Logging**:
    - Save results to `logs/model_experiments/<model_name>/<run_id>/`.
    - Create a Summary Report.

---

## 5. Evaluation Results

### Phase 5: YOLO-World Zero-Shot Evaluation (Dec 2025)

**Model**: YOLOv8x-Worldv2 (Ultralytics)  
**Date**: 2025-12-07  
**Input**: `data/evaluation/images/page_3.png`  
**Prompts**: `["barline", "vertical line", "measure line"]`  
**Confidence Threshold**: 0.05

**Results**:
- **True Positives (TP)**: 0
- **False Positives (FP)**: 1
- **False Negatives (FN)**: 152
- **Recall**: **0.0%** (0/152)
- **Precision**: 0.0%

**Observations**:
- The model produced virtually no detections, even with explicit text prompts targeting vertical lines and barlines.
- Zero-shot transfer from natural-image domains (COCO/LVIS) to dense musical notation appears ineffective.

**Interpretation**:
This is a **negative but inconclusive** result. While YOLO-World completely failed in this configuration, the failure could stem from:
- Domain mismatch (music scores vs. natural images)
- Insufficient prompt engineering or vocabulary expansion
- Need for image preprocessing (e.g., staff removal, contrast enhancement)

**Conclusion**:
- ✗ YOLO-World **cannot be used zero-shot** for barline detection in its current configuration.
- ✓ This result **justifies** moving to the next candidate model (Grounding DINO) or revisiting with controlled sanity checks.
- Fine-tuning would be required to make YOLO viable for this task.

**Artifacts**:
- Report: [`experiments/models/yolo_world/README.md`](../../experiments/models/yolo_world/README.md)
- Logs: `logs/model_experiments/yolo_world/run_001/`
