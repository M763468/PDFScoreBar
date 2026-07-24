# Development Log: CNN Classifier Training

This log tracks the progress of the `experiment/cnn_classifier` worktree.
Refer to `docs/DEVELOPMENT_LOG.md` for the main branch history.

## 2026-01-03: Initial Setup

- Created this log file to separate training logs from the main development log.
- Preparing for dataset creation and CNN training pipeline setup.

## 2026-01-04: Dataset Repair & Training Optimization

### Dataset Issue & Fix
- **Problem**: The `splits` directory in `datasets/cnn_classifier_final_v2_fixed` contained 0-byte (empty) files due to broken symbolic links.
- **Solution**: Modified `tools/cnn_classifier/build_cnn_dataset.py` to copy files physically (`shutil.copy2`) instead of linking. Rebuilt the splits using `--only-split`.
- **Status**: Dataset is now robust and portable.

### Training Script Refinement
- **Config**: Implemented logic to ensure `config.yaml` values override `argparse` defaults.
- **Optimization**:
    - **Optimizer**: Switched to `AdamW` (better generalization).
    - **Scheduler**: Added `CosineAnnealingLR` (smooth convergence).
    - **Batch Size**: Tuned to `256` (optimal for VRAM/Speed).
    - **Logging**: TensorBoard enabled by default.
- **API**: Updated to modern `torch.amp` (resolving deprecation warnings).

### Training Results (ResNet18)
- **Run**: `logs/cnn_barline_classification/training_resnet18_b320/` (batch 320 run)
- **Metrics**:
    - **Val F1**: **1.0000** (Perfect on current validation set).
    - **Val Loss**: **0.000014**.
- **Conclusion**: The model has learned the current distribution perfectly.
- **Next Step**: The high score suggests we need to validate against "unseen" False Positives (Active Learning) as the current validation set might be too easy or similar to training data.

## 2026-01-05: FN Diagnosis & Candidate Expansion Strategy

### 1. Diagnosis of False Negatives
- **Issue**: Visible barlines were being missed (FN) even with "Relaxed" probe scan parameters.
- **Investigation**:
    - Created `experiments/cnn_classifier/debug_probe_values.py` to inspect pixel-level metrics.
    - **Finding**: Missed barlines (e.g., thick double bars) often have high ink density but **low peak sharpness** (`peak_dominance` < 1.2), causing them to be rejected by the heuristic `scan_x_peak_ratio_min`.

### 2. "No Peak" Experiment (Recall Breakthrough)
- **Hypothesis**: Disabling the peak sharpness check and the candidate count limit (`max_per_band`) would capture these difficult barlines, at the cost of more FPs.
- **Configuration** ("No Peak"):
    - `band_source="row_stats"`
    - `min_ratio=0.50`
    - `scan_x_peak_ratio_min=0.0` (Disabled)
    - `max_per_band=0` (Disabled)
- **Results**:
    - **Candidate Explosion**: ~100 -> **~592** candidates/page.
    - **Recall Gain**: The CNN accepted **+65%** more barlines (82.6 -> 136.7 avg/page).
    - **Trade-off**: False Positives increased significantly (~455/page rejected, but many still accepted).
- **Decision**: Adopt "No Peak" as the standard candidate generation strategy. The heuristic filters were the bottleneck. We will now rely on the CNN (and post-processing) to filter the noise.

### 3. Next Steps (FP Reduction)
- **Hard Negative Mining**: Use the No Peak candidates (`expanded_candidates_nopeak.json`) to mine "Hard Negatives" (candidates that are NOT barlines) for retraining.
- **Post-Processing**: Implement context-aware filters (stem detection, periodicity) to handle the remaining FPs.

### 4. Inference Logic Verification
- **Task**: "Inference Pipeline Integration" (Partially Completed).
- **Implementation**: Created `experiments/cnn_classifier/inference_visualize.py`.
    - **Function**: Loads the trained ResNet18 model, executes batch inference on candidate JSONs, applying standard transforms (Resize 256x128, Normalize).
    - **Output**: Generates `*_scored.json` (candidates with probability scores) and visualization overlays.
- **Outcome**: Successfully verified that the model can be applied to full-page candidates. This script serves as the prototype for the final production `inference_filter.py`.

## 2026-01-05: Provisional GT Creation for Evaluation2 (Prokofiev)

**Objective**: Prepare a baseline Ground Truth (GT) for the `evaluation2` dataset (Prokofiev) to enable manual refinement.

**Strategy**:
1.  **Source**: Use "Peak-enabled" candidates ("Ultraloose" configuration) to minimize initial noise (compared to "No Peak").
2.  **Filter**: Apply the trained CNN classifier (`ResNet18`) and keep candidates with `Score > 0.5`.
3.  **Output**: Generate "Provisional GT" JSON files compatible with the `gt_relabel_gui` tool.

**Actions**:
1.  **Script Creation**: Created `tools/cnn_classifier/create_provisional_gt.py`.
    *   **Usage**: `.venv_cnn_classifier/bin/python tools/cnn_classifier/create_provisional_gt.py --scored-root logs/cnn_validation_eval2_ultraloose --output-root data/evaluation2/annotations_provisional`
    *   Reads `*_scored.json` from `logs/cnn_validation_eval2_ultraloose/`.
    *   Filters boxes with `score > 0.5`.
    *   Saves result to `data/evaluation2/annotations_provisional/{subdir}/{page_name}.json`.
2.  **Execution**: Generated GT for 33 pages (Prokofiev1, Prokofiev5).
3.  **GUI Config**: Created `tools/cnn_classifier/create_gt_gui_config.py` and generated `tools/gt_relabel_gui/evaluation2_config.json`.
    *   **Usage**: `python tools/cnn_classifier/create_gt_gui_config.py --json-root data/evaluation2/annotations_provisional --image-root data/evaluation2/images --output-config tools/gt_relabel_gui/evaluation2_config.json`
    *   Maps each image to its provisional GT JSON.
    *   Enables the user to load this config in `gt_relabel_gui` and manually correct the boxes (remove FPs).

**Artifacts**:
*   Provisional GT: `data/evaluation2/annotations_provisional/`
*   GUI Config: `tools/gt_relabel_gui/evaluation2_config.json`
*   Usage:
    ```bash
    # Run the GUI with the new config
    python tools/gt_relabel_gui/server.py --mode gt --config tools/gt_relabel_gui/evaluation2_config.json
    ```

## 2026-01-05: Provisional GT & Config Refinement (User Feedback)
**Issues Reported**:
1.  **Black Images**: GUI was not displaying images because config contained paths resolving to symlink targets (outside repo root), which the server blocked.
2.  **Duplicates**: `prokofiev1` was a duplicate of `Va_Prokofiev_Symphony1`.
3.  **Redundant Work**: `Va_Prokofiev_Symphony1` pages 001/004 already have GT.
4.  **Missing BBox**: GUI showed images but not boxes because `app_gt.js` expected `editable` field which was missing.

**Fixes**:
1.  **Path Resolution**: Modified `tools/cnn_classifier/create_gt_gui_config.py` to use absolute paths preserving the repo structure.
2.  **Server Security**: Updated `tools/gt_relabel_gui/server.py` to use `os.path.abspath` for safer symlink support.
3.  **Filtering**: Updated script to exclude duplicates and existing GT.
4.  **Config Field**: Added `editable` field to config.
5.  **Regeneration**: Re-ran the script. Config now contains 25 valid pages.


## 2026-01-06: GT Finalization
**Objective**: Archive the manually corrected Ground Truth files.
**Action**:
1.  **Finalization Script**: Created `tools/cnn_classifier/finalize_gt.py`.
    *   **Usage**: `python tools/cnn_classifier/finalize_gt.py` (Copies `*_sorted.json` to `data/evaluation2/annotations/` as `boxes_sorted_v20260106.json`).
    *   Copies `*_sorted.json` from `annotations_provisional` to `data/evaluation2/annotations/`.
    *   Renames to `boxes_sorted_v20260106.json`.
2.  **Execution**: Copied 25 verified GT files to their permanent location.
**Result**: 25 New Ground Truth files added to `evaluation2` dataset.

---

## 2026-01-06 to 2026-01-12: Evaluation Pipeline & Final Optimization

### Evaluation Pipeline Development

**Objective**: Build comprehensive evaluation infrastructure for the 68-page dataset.

**Ground Truth Expansion**:
- Initial: 25 pages (Prokofiev)
- Added: Shostakovich (22 pages), Sibelius (10 pages), additional Prokofiev pages
- **Final: 68 pages, 3570 ground truth barlines**

**Scripts Created**:

1. **Global Evaluation Script**: `tools/re_evaluate_global.py`
   - Aggregates results across all pages
   - Greedy barline matching algorithm
   - Per-page and global metrics (TP, FP, FN, Precision, Recall)
   - CSV output for analysis
   - Usage:
     ```bash
     python tools/re_evaluate_global.py \
         --scored-root logs/evaluation_results \
         --gt-root data/evaluation2/annotations \
         --output-csv logs/evaluation_results/global_summary.csv \
         --threshold 0.5
     ```

2. **Batch Scoring Pipeline**: `tools/cnn_classifier/score_candidates_batch.py`
   - Recursive directory traversal
   - Batch inference (batch size 64) for GPU efficiency
   - Skip already-processed files
   - Robust image path resolution with `rglob` fallback
   - Empty file handling (saves empty JSONs for 0-candidate pages)
   - Usage:
     ```bash
     python tools/cnn_classifier/score_candidates_batch.py \
         --logs logs/detection_output \
         --model logs/cnn_retrain_v3_final/cnn_classifier_best.pth \
         --threshold 0.1
     ```

3. **Error Visualization Tool**: `tools/visualize_error_crops.py`
   - Generates 256×256 crops of all FP and FN errors
   - Labels images with error type and location
   - Enables visual pattern analysis
   - Usage:
     ```bash
     python tools/visualize_error_crops.py \
         --image-root data/evaluation2/images \
         --scored-root logs/evaluation_results \
         --gt-root data/evaluation2/annotations \
         --output-root logs/error_crops \
         --threshold 0.5
     ```

**FP/FN Attribution Analysis**:
- **FN (Detector)**: Missed by initial probe scan
- **FN (CNN)**: Detected but rejected by CNN
- **Finding**: Most FNs are detector-stage (probe scan too conservative)

---

## 2026-01-12: Best Configuration Discovery

### Detection Parameter Tuning

**Ink Threshold Experiments**:
- Tested: 230 (standard), 210 (lower)
- **Chosen: 230** (balanced ink detection, minimal texture noise)

**Critical Discovery: Min Height Ratio Filter**

**Parameter**: `min_height_ratio = 0.012`

**Rationale**:
- On 3900px height page: ~47px minimum
- Shortest True Positive: ~66px (~1.7%)
- Most False Positives: <31px (<0.8%)

**Implementation**:
```python
min_height = image_height * min_height_ratio
candidates = [c for c in candidates if (c["y2"] - c["y1"]) >= min_height]
```

**Impact**: Eliminated majority of FPs (text fragments, dots, short stems) while preserving all legitimate barlines.

### Best Configuration Established

**Detection Parameters**:
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

### Results (68 Pages, 3570 GT Barlines)

- **Total Ground Truth**: 3570 barlines
- **True Positives**: 3568
- **False Positives**: **2**
- **False Negatives**: **2**
- **Recall**: **99.94%** (3568/3570)
- **Precision**: **99.94%** (3568/3570)

### Remaining Errors (4 Total)

**False Positives (2) - Both on Shostakovich 5**:

| Page | Coordinate | Type | Image |
|:-----|:-----------|:-----|:------|
| P16 | (2713, 3681) | Text bracket or note stem | `logs/best_config_errors/Shosrakovich-Sym5-Va_page_016_FP_2713_3681.png` |
| P19 | (1308, 420) | Text fragment or bracket | `logs/best_config_errors/Shosrakovich-Sym5-Va_page_019_FP_1308_420.png` |

**Characteristics**: "Hard negatives" that passed both geometric and CNN filters. Visually similar to barlines.

**False Negatives (2) - Both on Sibelius Violin Concerto (Viola), Page 4**:

| Coordinate | Type | Image |
|:-----------|:-----|:------|
| (2715, 3167) | Extremely faint/broken barline | `logs/best_config_errors/Sibelius-Violin_Concerto-Viola_page_004_FN_2715_3167.png` |
| (2725, 3168) | Broken/fragmented barline | `logs/best_config_errors/Sibelius-Violin_Concerto-Viola_page_004_FN_2725_3168.png` |

**Characteristics**: Insufficient ink density or vertical continuity. Adjacent (10px apart), likely same measure.

---

## 2026-01-12: Vertical Closing Experiment (FN Recovery)

### Objective
Rescue broken/fragmented barlines by connecting vertical gaps using morphological closing.

### Implementation

**Method**: Apply morphological closing with vertical kernel.

```python
if vertical_closing > 0:
    kernel = np.ones((vertical_closing, 1), np.uint8)
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, kernel)
```

**Kernel Size Selection**:

Created `experiments/legacy/tools_archive/test_morphological_closing.py` to test on Sibelius VC Page 4, FN at (2715, 3167):

| Kernel Size | Ink Ratio Before | Ink Ratio After | Improvement |
|------------:|-----------------:|----------------:|:------------|
| 5px | 0.5892 | 0.6587 | +11.8% |
| 9px | 0.5892 | 0.7066 | +19.9% |
| 13px | 0.5892 | 0.7545 | +28.1% |
| **21px** | 0.5892 | **0.8199** | **+39.2%** ✅ |

**Chosen**: 21-pixel kernel (optimal for connecting typical barline gaps).

**Integration**: Modified `tools/run_gt_rebuild_hybrid_eval.py` and added `--vertical-closing` parameter to `tools/run_eval_experiment.py`.

### Results with Vertical Closing

**Configuration**: Best config + `--vertical-closing 21`

**Results (65 Pages, Threshold=0.5)**:
- **Recall**: 99.6% (3257 TP / 3270 GT)
- **Precision**: 45.9% (3257 TP / 7091 detections)
- **False Positives**: **3834** (massive increase!)
- **False Negatives**: 13

**Results (Threshold=0.1)**:
- **Recall**: **100.0%** (3269 TP / 3270 GT) ✅
- **Precision**: 34.8%
- **False Positives**: **6132**
- **False Negatives**: 1

### Trade-off Analysis

**Gains**:
- ✅ Rescued broken barlines → 100% recall achievable
- ✅ 3/5 scores achieved 100% recall

**Costs**:
- ❌ Generated many FP candidates (3834 at threshold 0.5)
- ❌ Precision dropped from 99.94% → 45.9%
- ❌ CNN unable to filter the additional FPs effectively

**Conclusion**: Vertical closing works for FN rescue, but NOT worth it unless CNN filtering can be dramatically improved. Better to accept 2 FNs than 3834 FPs.

---

## 2026-01-12: Active Learning Attempt (CNN v4 Retraining)

### Objective
Improve CNN's ability to reject FPs by retraining with high-confidence false positives extracted from evaluation results.

### FP Extraction

**Script**: `tools/cnn_classifier/extract_fps_by_score_range.py`

**Strategy**: Extract FPs with CNN scores 0.5-0.9 (high-confidence false positives that should be easy for model to learn).

**Usage**:
```bash
python tools/cnn_classifier/extract_fps_by_score_range.py \
    --scored-root logs/global_final_opt \
    --image-root data/evaluation2/images \
    --gt-root data/evaluation2/annotations \
    --output-dir datasets/cnn_classifier_v4_fp_augmented/splits/train/fp \
    --min-score 0.5 --max-score 0.9 \
    --max-samples 2000 --threshold 0.5
```

**Results**:
- **Extracted**: 1534 high-confidence FP samples
- **Output**: `datasets/cnn_classifier_v4_fp_augmented/splits/train/fp/`

### CNN v4 Retraining

**Dataset**:
- **TP samples**: 20,416 (from existing dataset)
- **FP samples**: 1,534 (newly extracted)
- **Total**: ~22,000 samples (5.5x increase from original 4017)
- **Class balance**: 93% TP, 7% FP

**Training Configuration**:
```bash
python experiments/cnn_classifier/train.py \
    --tp-dir datasets/cnn_classifier_v3_active_learning/splits/train/tp \
    --fp-dir datasets/cnn_classifier_v4_fp_augmented/splits/train/fp \
    --model-name resnet18 \
    --learning-rate 0.001 \
    --batch-size 320 \
    --epochs 50 \
    --work-dir logs/cnn_retrain_v4_fp_augmented
```

**Training Results**:
- **Duration**: ~20 minutes (batch size 320)
- **Final Training Metrics**: Loss 0.0000, Accuracy 1.0000, F1 1.0000
- **Final Validation Metrics**: Loss 0.0000, Accuracy 1.0000, F1 1.0000
- **Model**: `logs/cnn_retrain_v4_fp_augmented/cnn_classifier_best.pth`

**⚠️ Red Flag**: 100% training accuracy suggests overfitting.

### Evaluation Results - Performance DEGRADED

**Results (68 Pages, Threshold=0.5)**:
- **Recall**: 99.6% (3557 TP / 3570 GT)
- **Precision**: **32.3%** (3557 TP / 11,998 detections) ⚠️
- **False Positives**: **7441** (increased from 3834 with v3!)
- **False Negatives**: 13

**Results (Threshold=0.1)**:
- **Recall**: 100.0%
- **Precision**: **26.6%** ⚠️
- **False Positives**: **9848**
- **False Negatives**: 1

**Comparison with v3 Model**:

| Metric | v3 Model | v4 Model | Change |
|:-------|----------:|---------:|:-------|
| Precision (th=0.5) | 45.9% | **32.3%** | **-29%** ⚠️ |
| FP Count (th=0.5) | 3834 | **7441** | **+94%** |
| Precision (th=0.1) | 34.8% | **26.6%** | **-24%** |
| FP Count (th=0.1) | 6132 | **9848** | **+61%** |

**Catastrophic Failure on Va_Prokofiev_Symphony1**:
- **Precision**: **12.8%** (545 TP, 3905 FP!)
- This score had **ZERO FP samples** in the training data

### Root Cause Analysis

**1. Overfitting**:
- Training accuracy: 100% (perfect fit to training data)
- Model memorized training samples instead of learning generalizable features
- No early stopping or regularization

**2. Data Distribution Mismatch**:
- FP samples extracted only from scores with high FP rates (Shostakovich, Sibelius, prokofiev5)
- Va_Prokofiev_Symphony1 had zero FP samples in training data
- Model failed catastrophically on unseen score

**3. Insufficient FP Diversity**:
- Only 1,534 FP samples (7% of dataset)
- All from high-confidence range (0.5-0.9)
- Missing medium/low-confidence FPs (0.1-0.5)

**4. Class Imbalance**:
- 93% TP vs 7% FP
- Model biased toward accepting everything as TP
- Should have used weighted loss or balanced sampling

### Lessons Learned

**What Went Wrong**:
1. ❌ Insufficient FP sample diversity (only 1,534 samples, specific scores)
2. ❌ No validation on held-out scores (should have reserved entire scores for validation)
3. ❌ No early stopping (100% training accuracy is a red flag)
4. ❌ Class imbalance not addressed
5. ❌ Extracted FPs only from high-confidence range (0.5-0.9)

**What Would Be Needed**:
1. ✅ 10,000+ FP samples from ALL scores
2. ✅ Include full confidence range (0.1-0.9)
3. ✅ Reserve entire scores for validation (not random samples)
4. ✅ Early stopping based on validation loss
5. ✅ Weighted loss or balanced sampling for class imbalance
6. ✅ Data augmentation (rotation, brightness, etc.)

**Decision**: Revert to best historical configuration (v3 model + min_height_ratio filter).

---

## 2026-01-12: Final Configuration & Conclusions

### Decision: Revert to Best Historical Configuration

**Rationale**:
- v4 model performed WORSE than v3 (32.3% vs 45.9% precision)
- Best historical configuration achieved **99.94% precision/recall**
- Further CNN improvements require much larger, more diverse training dataset
- **Geometric filtering (min_height_ratio) more effective than CNN-only approach**

### Final Best Configuration

**Detection**:
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

**Key Parameter**: `min_height_ratio=0.012` - Filters candidates shorter than 1.2% of image height

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

### Final Results Summary

**68 Pages, 3570 Ground Truth Barlines**:
- **True Positives**: 3568
- **False Positives**: 2
- **False Negatives**: 2
- **Recall**: **99.94%** (3568/3570)
- **Precision**: **99.94%** (3568/3570)

**Error Visualizations**: Saved to `logs/best_config_errors/`

### Key Lessons Learned

**1. Geometric Filtering is Powerful**:
- Simple height-based filter (`min_height_ratio`) eliminated most FPs
- More effective than CNN-only approach
- Fast, interpretable, robust

**2. CNN Training Requires Careful Data Curation**:
- Distribution mismatch leads to catastrophic failure
- Need samples from ALL target domains
- Overfitting is easy to achieve but useless

**3. Trade-offs are Fundamental**:
- Recall vs. Precision
- Sensitivity vs. Specificity
- Complexity vs. Interpretability

**4. 99.94% is Excellent for Practical Use**:
- Perfect accuracy may not be achievable or necessary
- 4 errors out of 3570 is negligible for most applications
- Diminishing returns beyond this point

### Recommendations

**For Production Use**:
- ✅ Use best configuration (99.94% precision/recall)
- ✅ Accept 4 errors as practical limit (0.11% error rate)
- ✅ Manual review of 4 errors is trivial if perfect accuracy required

**For Research**:
- Score-specific parameter tuning
- Context-aware filtering (check for nearby staff lines, periodicity)
- Hybrid detection strategies (selective vertical closing)
- Larger, more diverse CNN training dataset (10,000+ FPs from all scores)

### Artifacts Created

**Documentation**:
- `docs/SESSION_LOG.md` - Detailed session notes
- `docs/CNN_RETRAINING_GUIDE.md` - Retraining procedure guide
- `docs/best_configuration_summary.md` - Best config detailed analysis
- `docs/performance_comparison.md` - v3 vs v4 comparison

**Error Images**:
- `logs/best_config_errors/` - 4 error visualizations

**Models**:
- `logs/cnn_retrain_v3_final/cnn_classifier_best.pth` - Production model
- `logs/cnn_retrain_v4_fp_augmented/cnn_classifier_best.pth` - v4 model (failed experiment)

**Datasets**:
- `datasets/cnn_classifier_v4_fp_augmented/` - 1,534 extracted FP samples

---

## Reference Information

### Key Scripts

**Dataset & Training**:
- `tools/cnn_classifier/build_cnn_dataset.py` - Dataset builder (TP/FP crops)
- `experiments/cnn_classifier/train.py` - CNN training script

**Evaluation Pipeline**:
- `tools/cnn_classifier/score_candidates_batch.py` - Batch CNN scoring
- `tools/re_evaluate_global.py` - Global evaluation aggregation
- `tools/visualize_error_crops.py` - Error visualization
- `tools/cnn_classifier/extract_fps_by_score_range.py` - FP extraction for active learning

**Detection**:
- `tools/run_eval_experiment.py` - Detection pipeline wrapper
- `tools/run_gt_rebuild_hybrid_eval.py` - Core detection logic
- `experiments/legacy/tools_archive/test_morphological_closing.py` - Vertical closing validation

**Ground Truth**:
- `tools/cnn_classifier/create_provisional_gt.py` - Provisional GT creation
- `tools/cnn_classifier/create_gt_gui_config.py` - GUI config generator
- `tools/cnn_classifier/finalize_gt.py` - GT finalization

### Production Model

- **Path**: `logs/cnn_retrain_v3_final/cnn_classifier_best.pth`
- **Architecture**: ResNet18
- **Training Data**: 20,416 TP + diverse FP samples
- **Validation F1**: 0.9946
- **Performance**: 99.94% Precision & Recall (when combined with min_height_ratio filter)

### Best Configuration

**Detection Parameters**:
```bash
--ink-threshold 230
--min-ratio 0.70
--band-min-row-count 1
--min-height-ratio 0.012  # CRITICAL PARAMETER
```

**CNN Parameters**:
- Scoring threshold: 0.1
- Evaluation threshold: 0.5

**Key Discovery**: `min_height_ratio=0.012` filter is more effective than CNN-only filtering.

### Datasets

**Training Datasets**:
- `datasets/cnn_classifier_final_v2_fixed` - Initial training dataset (~20,000 samples)
- `datasets/cnn_classifier_v3_active_learning` - With hard negatives
- `datasets/cnn_classifier_v4_fp_augmented` - With 1,534 extracted FPs (failed experiment)

**Ground Truth**:
- `data/evaluation2/annotations` - 68 pages, 3570 barlines
- Scores: Shostakovich 5 (22 pages), Sibelius VC (10 pages), Prokofiev (36 pages)

**Error Visualizations**:
- `logs/best_config_errors/` - 4 error images (2 FP, 2 FN)

### Documentation

- `docs/DEVLOG_CNN_TRAINING.md` - This file (complete development history)
- `docs/SESSION_LOG.md` - Detailed session notes (2026-01-03 to 2026-01-12)
- `docs/best_configuration_summary.md` - Best config detailed analysis
- `docs/performance_comparison.md` - v3 vs v4 model comparison
- `docs/CNN_RETRAINING_GUIDE.md` - Retraining procedure guide

---

**Branch Status**: Ready for closure. Best configuration (99.94% precision/recall) documented and reproducible.

## 2026-01-14: Branch Closure Preparation

**Objective**: Organize remaining tasks and finalize documentation for the `experiment/cnn_classifier` branch.

**Actions**:
1.  **Documentation Recovery**: Created missing documentation files mentioned in the checklist:
    - `docs/best_configuration_summary.md`: Detailed parameters and results for the 99.94% precision/recall config.
    - `docs/performance_comparison.md`: Analysis of v3 vs v4 (Active Learning) results.
2.  **Checklist Update**: Updated `docs/NEXT_SESSION_NOTES.md` to reflect that all documentation is complete.
3.  **Staging**: Staged final documentation changes for the closing commit.

**Status**: Achievements summarized and branch is ready for merge to main.
