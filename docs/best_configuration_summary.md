# Best Configuration Summary: 99.94% Precision & Recall

**Last Updated**: 2026-01-12
**Status**: Production Ready

## 1. Overview
The final optimization phase for the CNN Barline Classifier integrated into the Hybrid Detection Pipeline achieved **99.94% Precision and Recall** across a 68-page evaluation set containing 3,570 ground truth barlines.

## 2. Configuration Parameters

### Detection (Stage 1 & 2)
The detection stage uses "Extreme Sensitivity" to ensure all potential barlines are captured, followed by a critical geometric filter.

```bash
python tools/run_eval_experiment.py \
    --image-root data/evaluation2/images \
    --output-root logs/global_extreme_mh_ratio \
    --ink-threshold 230 \
    --min-ratio 0.70 \
    --band-min-row-count 1 \
    --min-height-ratio 0.012 \
    --pattern "**/*.png"
```

**Key Parameters**:
- **`--ink-threshold 230`**: High sensitivity to ink density.
- **`--min-ratio 0.70`**: Relaxed fill-ratio to capture broken or faint lines.
- **`--min-height-ratio 0.012` (CRITICAL)**: Filters out candidates shorter than 1.2% of the image height. This effectively removes text fragments, dots, and short stems while preserving the shortest legitimate barlines (~1.7% height).

### CNN Scoring (Stage 3)
Candidates are scored by the ResNet18 model (`v3_final`) trained with hard negatives.

```bash
python tools/cnn_classifier/score_candidates_batch.py \
    --logs logs/global_extreme_mh_ratio \
    --model logs/cnn_retrain_v3_final/cnn_classifier_best.pth \
    --threshold 0.1
```

### Evaluation
Final evaluation uses a threshold of 0.5 for the CNN score.

```bash
python tools/re_evaluate_global.py \
    --scored-root logs/global_extreme_mh_ratio \
    --gt-root data/evaluation2/annotations \
    --output-csv logs/global_extreme_mh_ratio/global_summary.csv \
    --threshold 0.5
```

## 3. Results Summary (68 Pages, 3570 GT)

| Metric | Value |
| :--- | :--- |
| **True Positives (TP)** | 3568 |
| **False Positives (FP)** | 2 |
| **False Negatives (FN)** | 2 |
| **Precision** | **99.94%** |
| **Recall** | **99.94%** |

## 4. Remaining Errors

### False Positives (2)
Both are "hard negatives" on **Shostakovich 5** (P16, P19) visually similar to barlines (text brackets/note stems).

### False Negatives (2)
Both are on **Sibelius Violin Concerto (P4)**, where lines are extremely faint or broken beyond detection even with extreme sensitivity.

## 5. Conclusion
This configuration represents the practical performance limit of the current geometric + CNN approach. 99.94% accuracy is sufficient for production use, with manual review being trivial for the remaining 0.06% of cases.
