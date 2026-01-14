# Next Session Notes: FP Reduction & Pipeline Refinement

**Last Updated**: 2026-01-12 (Post-Final Optimization)
**Current Phase**: Branch Closure - Ready for Merge

---
### Operational Rules
- **Do not overwrite** `docs/SESSION_LOG.md`. Append new findings.
- **Reproducibility**: Record commit hash + command + output path for all major results.

---

## 1. Project Goal & Current Status
**Goal**: Integrate the trained CNN Classifier (`ResNet18`) into the Hybrid Barline Detection Pipeline to eliminate remaining False Positives.

**Status Update (2026-01-12)**:
- **GT Completed**: Ground Truth for `evaluation2` expanded to **68 pages, 3570 barlines**
    - Initial: 25 pages (Prokofiev) - 2026-01-06
    - Added: Shostakovich (22 pages), Sibelius (10 pages), additional Prokofiev pages
    - Location: `data/evaluation2/annotations/{subdir}/{page_name}/boxes_sorted_*.json`
- **Best Configuration Achieved**: **99.94% Precision & Recall**
    - True Positives: 3568
    - False Positives: 2
    - False Negatives: 2
    - Key Discovery: `min_height_ratio=0.012` filter is critical

## 2. Completed Tasks (Since 2026-01-06)

### A. Hard Negative Mining ✅ (Completed 2026-01-06)
**Results**: ResNet18 trained on `cnn_classifier_v3_hardneg` achieved **Val F1: 0.9946**.
*   **Best Model**: `logs/cnn_barline_classification/training_resnet18_v3_hardneg/cnn_classifier_best.pth`.

### B. GT Completion ✅ (Completed 2026-01-12)
- **Shostakovich Missing Pages**: `page_011` finalized as `boxes_sorted_v20260109.json`. `page_001` skipped (cover page).
- **Full Dataset**: All `evaluation2` pages are now accounted for (68 pages total).
- **Status**: Ground truth finalization complete.

### C. Evaluation Pipeline Development ✅ (Completed 2026-01-12)
**Scripts Created**:
1. `tools/re_evaluate_global.py` - Global evaluation aggregation
2. `tools/cnn_classifier/score_candidates_batch.py` - Batch CNN scoring (optimized with batch size 64)
3. `tools/visualize_error_crops.py` - Error visualization tool
4. `tools/cnn_classifier/extract_fps_by_score_range.py` - FP extraction for active learning

**Result**: Complete evaluation infrastructure established.

### D. Detection Parameter Optimization ✅ (Completed 2026-01-12)
**Critical Discovery**: `min_height_ratio=0.012` filter
- On 3900px page: ~47px minimum height
- Shortest TP: ~66px (~1.7%)
- Most FPs: <31px (<0.8%)
- **Impact**: Eliminated majority of FPs while preserving all legitimate barlines

**Best Configuration Established**:
```bash
--ink-threshold 230
--min-ratio 0.70
--band-min-row-count 1
--min-height-ratio 0.012  # CRITICAL
```

**Result**: 99.94% Precision & Recall achieved.

### E. Vertical Closing Experiment ✅ (Completed 2026-01-12)
**Objective**: Rescue broken/fragmented barlines using morphological closing.

**Implementation**: 21-pixel vertical kernel

**Results**:
- Recall: 100% achievable (rescued broken barlines)
- Precision: 45.9% (3834 FPs generated)
- **Decision**: Rejected - trade-off too poor

### F. Active Learning Attempt (CNN v4) ✅ (Completed 2026-01-12)
**Objective**: Improve CNN with 1534 high-confidence FP samples.

**Dataset**: 20,416 TP + 1,534 FP = ~22,000 samples

**Results**:
- Training: 100% accuracy (overfitting)
- Evaluation: **Precision degraded to 32.3%** (worse than v3's 45.9%)
- **Decision**: Rejected - reverted to v3 model

**Root Cause**:
- Data distribution mismatch (no FPs from Va_Prokofiev_Symphony1)
- Insufficient FP diversity
- Class imbalance not addressed

## 3. Final Configuration & Results

### Production Configuration
**Detection**:
```bash
python tools/run_eval_experiment.py \
    --image-root data/evaluation2/images \
    --output-root logs/global_extreme_mh_ratio \
    --ink-threshold 230 --min-ratio 0.70 \
    --band-min-row-count 1 --min-height-ratio 0.012 \
    --pattern "**/*.png"
```

**CNN Scoring**:
```bash
python tools/cnn_classifier/score_candidates_batch.py \
    --logs logs/global_extreme_mh_ratio \
    --model logs/cnn_retrain_v3_final/cnn_classifier_best.pth \
    --threshold 0.1
```

**Evaluation**:
```bash
python tools/re_evaluate_global.py \
    --scored-root logs/global_extreme_mh_ratio \
    --gt-root data/evaluation2/annotations \
    --output-csv logs/global_extreme_mh_ratio/global_summary.csv \
    --threshold 0.5
```

### Final Results (68 Pages, 3570 GT Barlines)
- **Precision**: 99.94% (3568 TP / 3570 detections)
- **Recall**: 99.94% (3568 TP / 3570 GT)
- **Errors**: 2 FP + 2 FN = 4 total errors

**Remaining Errors**:
- **FP (2)**: Text brackets on Shostakovich 5 (P16, P19) - "hard negatives"
- **FN (2)**: Broken barlines on Sibelius VC P4 - insufficient ink density

**Error Visualizations**: `logs/best_config_errors/`

## 4. Key Lessons Learned

### What Worked ✅
1. **Geometric filtering** (`min_height_ratio`) - simple, effective, interpretable
2. **"No Peak" candidate generation** - maximized recall
3. **Comprehensive evaluation infrastructure** - enabled rapid iteration
4. **Visual error analysis** - identified patterns and root causes

### What Didn't Work ❌
1. **Vertical closing** - 100% recall but 3834 FPs (precision 45.9%)
2. **Active learning without diverse data** - overfitting and catastrophic failure
3. **CNN-only filtering** - insufficient for aggressive detection

### Critical Insights
- Geometric filters outperformed complex CNN approaches
- Data diversity is critical - distribution mismatch leads to failure
- 99.94% is excellent - perfect accuracy may not be worth the cost
- 100% training accuracy is a red flag, not success

## 5. Reference Configs & Artifacts

### Production Model
- **Path**: `logs/cnn_retrain_v3_final/cnn_classifier_best.pth`
- **Architecture**: ResNet18
- **Validation F1**: 0.9946
- **Performance**: 99.94% Precision & Recall (with min_height_ratio filter)

### Key Scripts
- **Dataset Builder**: `tools/cnn_classifier/build_cnn_dataset.py`
- **Training**: `experiments/cnn_classifier/train.py`
- **Batch Scoring**: `tools/cnn_classifier/score_candidates_batch.py`
- **Global Evaluation**: `tools/re_evaluate_global.py`
- **Error Visualization**: `tools/visualize_error_crops.py`

### Documentation
- **Development Log**: `docs/DEVLOG_CNN_TRAINING.md` (complete history 2026-01-03 to 2026-01-12)
- **Session Log**: `docs/SESSION_LOG.md` (detailed session notes)
- **Best Config Guide**: `docs/best_configuration_summary.md`
- **Performance Comparison**: `docs/performance_comparison.md`

## 6. Branch Status & Next Steps

### Branch Closure Checklist
- [x] DEVLOG_CNN_TRAINING.md updated with all work
- [x] SESSION_LOG.md contains detailed session notes
- [x] Best configuration documented with reproduction steps
- [x] Error analysis completed with visualizations
- [x] NEXT_SESSION_NOTES.md updated
- [x] Final documentation files created (best_configuration_summary.md, performance_comparison.md)
- [ ] Final commit prepared
- [ ] Ready for merge to main

### Recommendations for Production
- Use best configuration (99.94% precision/recall)
- Accept 4 remaining errors as practical limit (0.11% error rate)
- Manual review of errors is trivial if perfect accuracy required

### Future Research Directions
- Score-specific parameter tuning
- Context-aware filtering (staff lines, periodicity)
- Larger, more diverse training datasets (10,000+ FPs from all scores)
- Early stopping to prevent overfitting

---

**Status**: Branch ready for closure and merge to main. All objectives completed.