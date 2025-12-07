# Evaluation Report: OMR-DLN (YOLOv8 for Measure Detection)

**Date**: Dec 2025  
**Model Source**: [dmgonzalez8/OMR](https://github.com/dmgonzalez8/OMR)  
**Model**: YOLOv8m fine-tuned on DeepScoresV2 for **measure detection**.

## 1. Strategy

This evaluation uses a pretrained YOLOv8 model from the OMR-DLN repository. Based on analysis of the repository, the most promising approach is not to detect barlines directly, but to use the provided model that was trained specifically to detect **measures**.

The evaluation pipeline is as follows:
1.  Run the pretrained YOLOv8 model on a score image to get bounding boxes for measures.
2.  For each detected measure box `(x1, y1, x2, y2)`, infer two barlines: one at the left edge `x1` and one at the right edge `x2`.
3.  Evaluate this set of inferred barlines against the ground truth for barlines.

This approach bypasses the ambiguity of direct barline detection and leverages the model's training on larger, more distinct objects (measures).

## 2. How to Run Evaluation

### Prerequisites
1.  **Download Weights**: Download the pretrained model weights from the Google Drive link in the [OMR-DLN repo](https://github.com/dmgonzalez8/OMR). Specifically, you need the **YOLOv8m model trained for measure detection**.
2.  **Place Weights**: Rename the downloaded file to `yolov8m_measure_deepscores.pt` and place it in `external/omr_dln/models/public_models/`.
3.  **Environment**: Ensure the `.venv_omr_dln` virtual environment is set up with `ultralytics` and other dependencies installed.

### Execution
Run the wrapper script `eval_omr_dln.py` with the required arguments.

```bash
# Activate the correct virtual environment
source .venv_omr_dln/bin/activate

# Run evaluation on page_3
python experiments/models/eval_omr_dln.py \
    --image data/evaluation/images/page_3.png \
    --gt data/evaluation/annotations/page_003/boxes_sorted.json \
    --output-dir logs/model_experiments/omr_dln/run_001 \
    --conf 0.25
```

## 3. Expected Outcome

- The script will generate a `prediction_vis.jpg` in the output directory, showing the detected **measure boxes (green)** and the **inferred barlines (blue)**.
- `metrics.json` will contain the final evaluation results (TP, FP, FN) for the inferred barlines.
- `predictions.json` will contain the coordinates of the inferred barlines.

## 4. Results

### Metrics on page_3 (conf=0.25)
| Metric | Value |
|---|---|
| True Positives (TP) | 137 |
| False Positives (FP)| 17 |
| False Negatives (FN)| 15 |
| **Precision** | **0.890** |
| **Recall** | **0.901** |
| **F1-Score** | **0.895** |

### Interpretation
The OMR-DLN measure detection model shows significant promise in improving **precision**. It successfully reduced the number of false positives from 30 (in the `homr` baseline) to just 17. However, this came at the cost of **recall**. The model failed to identify 15 barlines that the baseline correctly found. Because the end-goal of measure numbering requires a complete set of barlines, the introduction of false negatives makes this model unsuitable as a standalone replacement. Its strength in rejecting false positives is valuable, but its imperfect recall is a critical weakness for this specific application.
