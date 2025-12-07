# Evaluation Report: YOLO-World (Zero-Shot)

**Date**: 2025-12-07  
**Model**: YOLOv8x-Worldv2 (Ultralytics)  
**Mode**: Zero-Shot Detection  
**Prompts**: `["barline", "vertical line", "measure line"]`  
**Confidence Threshold**: 0.05  
**Input**: `data/evaluation/images/page_3.png`

## 1. Summary of Results
The model **completely failed** to detect barlines in the score image `page_3`.

| Metric | Count / Score |
| :--- | :--- |
| **True Positives (TP)** | 0 |
| **False Positives (FP)** | 1 |
| **False Negatives (FN)** | 152 |
| **Recall** | **0.0%** |
| **Precision** | 0.0% |

## 2. Analysis

### Zero-Shot Capability
YOLO-World's open-vocabulary capability did not transfer to the domain of music score barlines. The visual features of thin vertical lines in dense staff contexts were likely considered "background" or "noise" by the model trained on natural images (COCO/LVIS).

### Prompt Engineering
Even with lowered confidence (0.05) and explicit prompts like "vertical line" and "barline", the model could not segment barlines from staff lines or stems. This suggests that text-based prompting alone is insufficient for this specialized visual domain.

### Visual Inspection
The single prediction (FP) was likely an artifact or misclassification. No meaningful barline detections were produced.

## 3. Caveats and Limitations

This is a **negative but inconclusive** result. The complete failure could stem from several factors:

1. **Domain Mismatch**: Music notation is fundamentally different from natural images in the training distribution
2. **Insufficient Prompt Engineering**: More sophisticated prompts or prompt expansion techniques might be needed
3. **Preprocessing Requirements**: The model might require:
   - Staff line removal
   - Contrast enhancement
   - Binarization or other image preprocessing
4. **Configuration Issues**: Potential model configuration or parameter settings that weren't explored

### What This Result Does NOT Prove
- ✗ That YOLO-World is inherently unsuitable for music notation (preprocessing might help)
- ✗ That all open-vocabulary models will fail (other architectures may perform better)
- ✗ That YOLO cannot work for this task (fine-tuning would likely succeed)

### What This Result DOES Prove
- ✓ Zero-shot YOLO-World with basic prompts cannot detect barlines in dense scores
- ✓ Domain transfer from natural images to music notation is non-trivial
- ✓ Evaluation infrastructure and protocol are working correctly

## 4. Conclusion

**YOLO-World (Zero-Shot) is NOT viable** in its current configuration.

To use YOLO for this task, one of the following is required:
1. **Fine-Tuning**: Annotate a dataset and train a specific "barline" class
2. **Advanced Prompting**: Explore prompt engineering techniques or vocabulary expansion
3. **Preprocessing Pipeline**: Develop specialized image preprocessing for music scores

## 5. Recommendations

### Immediate Next Steps
1. Proceed to evaluate **Grounding DINO** (next priority candidate)
2. Document this negative result to inform future model selection

### Future Considerations
If pursuing YOLO:
- Create a small annotated dataset (30-50 pages)
- Fine-tune YOLOv8-nano or YOLOv8-small for efficiency
- Export to ONNX for production deployment (GPL license consideration)

## 6. Run Logs
- **Log Dir**: `logs/model_experiments/yolo_world/run_001/`
- **Output Files**:
    - `metrics.json` - Quantitative results
    - `predictions.json` - Raw prediction coordinates
    - `prediction_vis.jpg` - Visualization overlay
