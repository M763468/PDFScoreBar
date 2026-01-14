# Performance Comparison: CNN Model v3 vs v4 (Active Learning)

**Date**: 2026-01-12
**Subject**: Evaluation of Active Learning performance for barline detection.

## 1. Context
An active learning experiment (v4) was conducted by extracting 1,534 high-confidence False Positives (scores 0.5-0.9) from the evaluation set and retraining the ResNet18 model to improve precision.

## 2. Comparison Results (68 Pages)

Results measured at CNN threshold 0.5.

| Metric | v3 Model (Hard Negs) | v4 Model (Augmented FP) | Change |
| :--- | :--- | :--- | :--- |
| **Recall** | 99.94% | 99.6% | -0.34% |
| **Precision** | **99.94%** | 32.3% | **-67.6%** ⚠️ |
| **FP Count** | **2** | 7,441 | **+3720x** |
| **TP Count** | 3,568 | 3,557 | -11 |

## 3. Analysis of Failure (v4)

### Root Causes
1. **Overfitting**: The model achieved 100% training and validation accuracy but failed on the test/evaluation distribution.
2. **Distribution Mismatch**: FP samples were extracted only from scores with high error rates. The model failed catastrophically on scores like `Va_Prokofiev_Symphony1` which had zero FP samples in the new training set.
3. **Class Imbalance**: The dataset was heavily biased (93% TP, 7% FP), leading the model to "memorize" specific FP samples rather than learning generalizable features.

### Catastrophic Failure Example
On `Va_Prokofiev_Symphony1`, the v4 model produced **3,905 False Positives** compared to almost zero with the v3 model.

## 4. Final Decision
The active learning experiment (v4) was **REJECTED**. The project reverted to the **v3 model** combined with the `min_height_ratio` geometric filter, which proved significantly more robust and accurate.

## 5. Lessons Learned
- 100% training accuracy is a major red flag for overfitting.
- Data diversity (extracting FPs from ALL target scores) is critical for active learning.
- Simple geometric filters can sometimes outperform complex model retraining when the feature (like line height) is consistent.
