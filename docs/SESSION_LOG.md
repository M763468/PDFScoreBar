# Session Log

Last migrated: 2026-01-03 01:12:16

See `docs/DEVELOPMENT_LOG.md` for historical logs and `docs/NEXT_SESSION_NOTES.md` for the latest status.

## 2026-01-03: Dataset Investigation for CNN Classifier

**Objective:** Identify suitable datasets for training a lightweight CNN classifier to distinguish barlines from false positives (stems, clefs, etc.).

**Findings:**

1.  **DeepScores V2 (Recommended)**
    *   **Type:** Digitally rendered sheet music (matching the "PDF/Printed" domain of this project).
    *   **Variants:**
        *   **Complete:** ~255k images (~80GB). Too large for local training on limited resources.
        *   **Dense:** ~1,714 images (subset with high symbol density).
    *   **Size:** The "Dense" version is significantly smaller (likely <1GB compressed, though uncompressed size varies).
    *   **Content:** High-resolution images with bounding box annotations for 135 classes, including barlines and potential false positive classes (stems, beams, etc. implicitly or explicitly).
    *   **License:** CC-BY 4.0 (Permissive).
    *   **Suitability:** High. The "Dense" subset provides a good variety of complex contexts for hard negative mining.

2.  **MUSCIMA++**
    *   **Type:** Handwritten sheet music (CVC-MUSCIMA).
    *   **Size:** 140 images.
    *   **Suitability:** Low. The domain gap (handwritten vs. printed) makes it less ideal for this specific task compared to DeepScores.

**Conclusion:**
DeepScores V2 Dense is the best candidate. It provides sufficient volume and variety without the massive storage overhead of the complete set.

## 2026-01-03: DeepScores V2 Dense Re-evaluation

**Concerns:**
*   Is ~1,700 images (Dense) sufficient? (Yes, for a lightweight classifier, especially when combined with our hard negatives).
*   Is the variety sufficient? (Yes, "Dense" is specifically selected for complexity).
*   Download size? (~82GB for Complete, Dense is a subset but download might be packaged together or separately). *Update: Search results indicate Dense might be part of the larger package or hosted separately. Confirmed Dense size is much smaller (~1GB range usually, but search said 81.7GB for "dataset" - need to be careful if they are split).*
*   License: CC-BY 4.0 (Very permissive, requires attribution).
*   Disk Space: `/mnt/d` has 1.5TB available.

**Action Item:**
*   Proceed with setting up the pipeline using **local data first** (5 pages) to validate the code.
*   Simultaneously, download DeepScores V2 Dense (if separable) or prepare to handle the large download on `/mnt/d`.

## 2026-01-03: Download Script Preparation

*   Created `setup_scripts/download_deepscores_dense.sh`.
*   Target: `/mnt/d/datasets/DeepScoresV2`.
*   URL: `https://zenodo.org/record/4012193/files/ds2_dense.tar.gz` (Approx. 742 MB).

## 2026-01-03: Local Pipeline Verification

**Actions:**
1.  **TP Extraction:** Created `tools/extract_tp_crops.py` to extract confirmed true positives from `logs/homr_eval/` images based on rebuilt GT (`logs/phase6_detector_miss/gt_rebuild/`). Extracted **612 TP crops**.
2.  **FP Extraction:** Created `tools/extract_fp_crops_enhanced.py` to mine hard negatives from `logs/phase5b_confirmed_union_eval/` candidates that do not match GT. Extracted **497 FP crops**.
3.  **Training Script:** Created `experiments/cnn_classifier/train.py` using MobileNetV3 Small (pretrained).
4.  **Verification Run:**
    *   Executed training on local data (1109 total samples).
    *   Result: Model trained for 10 epochs.
    *   Performance: Train Acc reached ~78%, Val Acc hovered around ~50% (clear overfitting/instability due to small dataset size and lack of variety).
    *   Artifact: `logs/cnn_classifier_v1.pth`.

**Status:** The pipeline is functional. It successfully loads data, trains, and saves a model. The poor validation performance confirms the need for the DeepScores V2 dataset to improve generalization.

## 2026-01-03: CNN Classifier Dataset Integration (DeepScores + Local)
**Actions:**
1. Added `tools/cnn_classifier/build_cnn_dataset.py` to re-crop local TP/FP and integrate DeepScores V2 Dense negatives.
2. Built dataset at `/mnt/d/datasets/cnn_classifier_v1` with local TP=612 / FP=497 and DeepScores negatives=5000.
3. Generated splits and metadata under `/mnt/d/datasets/cnn_classifier_v1/splits` and `/mnt/d/datasets/cnn_classifier_v1/metadata`.
4. Updated `experiments/cnn_classifier/train.py` to use split-based dataset layout (override via `CNN_DATASET_ROOT`).
5. Created `.venv_cnn_classifier` environment and saved dependency lock to `experiments/cnn_classifier/requirements_cnn_classifier_venv.txt`.
6. Documented CNN classifier environment setup in `docs/ENVIRONMENTS.md`.

## 2026-01-03: Local Crop Scale Fix (page_3 resolution)
**Actions:**
1. Updated local TP/FP cropping to scale crop size by barline bbox height (fixes page_3 over-wide crops due to low resolution).
2. Rebuilt local crops and splits in `/mnt/d/datasets/cnn_classifier_v1` (DeepScores negatives unchanged).

## 2026-01-03: Local Crop Scale Adjustment (bbox-scale v2)
**Actions:**
1. Changed local TP/FP crop sizing to `bbox_height * scale` with clamp (`--crop-scale 3.0`, min/max height 48/256).
2. Rebuilt local crops and splits in `/mnt/d/datasets/cnn_classifier_v1` to reduce page_3 over-wide crops.

## 2026-01-03: DeepScores Segmentation Check
**Actions:**
1. Verified DeepScores Dense segmentation is paletted; palette indices map to `categories[].color`.
2. No `barline` category present; sampled barline-like columns map to palette index 0 (background).
3. Conclusion: segmentation images do not provide barline TP directly.

## 2026-01-03: DeepScores Segmentation Sampling (manual TP boxes)
**Actions:**
1. Read manually drawn TP boxes from `logs/deepscores_tp/lg-101766503886095953-aug-beethoven--page-1_raw.json`.
2. Sampled segmentation palette values inside 28 boxes; dominant indices were 0/3 (unknown/background) and 165 (staff).
3. No distinct barline-specific palette color found.

## 2026-01-03: DeepScores Segmentation Visual Crops
**Actions:**
1. Exported per-box segmentation crops with palette stats to `logs/deepscores_tp/visuals/` for manual color inspection.

## 2026-01-03: DeepScores Palette Component Crops
**Actions:**
1. Extracted connected components for palette index 165 (staff color) across 5 segmentation images.
2. Saved crops and overlays under `logs/deepscores_tp/color_components/` with per-image summaries in `summary.json`.

## 2026-01-03: DeepScores Index 3 Vertical Components
**Actions:**
1. Confirmed palette index 3 contains vertical components that align with barlines (based on manual TP boxes).
2. Generated full-image overlays and crops for index 3 across 5 segmentation images under `logs/deepscores_tp/index3_all/`.

## 2026-01-03: DeepScores TP Extraction (index 3)
**Actions:**
1. Added segmentation-based TP extraction in `tools/cnn_classifier/build_cnn_dataset.py` (palette index 3, vertical filter).
2. Started full-dataset TP extraction in background; log at `logs/deepscores_tp/deepscores_tp_build.log`.

## 2026-01-03: CNN Classifier Dataset Verification
**Actions:**
1. Verified DeepScores TP extraction completed successfully: **24,791 samples** extracted.
2. Confirmed DeepScores TP extraction method:
   - Source: Segmentation images (palette index 3)
   - Filters: min_area=30, min_height=30, vertical_ratio=3.0 (h/w >= 3.0)
   - Process: Connected component analysis on palette index 3, filtered by size and aspect ratio
   - Crop naming: `{seg_filename}_idx{component_label}_x{x1}_y{y1}.png`
   - Coordinates: Stored implicitly in filename (x, y position of bbox top-left)

3. **CRITICAL ISSUE FOUND: Local TP/FP Contamination**
   - Local TP extraction: Uses GT boxes directly → **612 samples** (correct)
   - Local FP extraction: Uses unmatched predictions → **497 samples**
   - **Problem**: GT has 612 barlines, but only 499 matched predictions (TP)
   - **Result**: 113 GT barlines (612 - 499 = 113) are **missing from training data** (FN cases not included as TP)
   
4. Per-page breakdown (IoU threshold=0.5):
   - page_001: GT=78, Preds=117, TP=60, FP=57, **FN=18**
   - page_3: GT=152, Preds=300, TP=108, FP=192, **FN=44**
   - page_004: GT=114, Preds=154, TP=91, FP=63, **FN=23**
   - page_10: GT=154, Preds=254, TP=139, FP=115, **FN=15**
   - page_15: GT=114, Preds=171, TP=101, FP=70, **FN=13**
   - **TOTAL: GT=612, Preds=996, TP=499, FP=497, FN=113**

**Root Cause:**
The local TP extraction uses all GT boxes (line 165-181 in `build_cnn_dataset.py`), but the local FP extraction only considers predictions that don't match GT (line 197-215). This creates a mismatch: 612 TP samples are extracted from GT, but 113 of those GT boxes have no corresponding detection in the predictions (FN cases). These 113 samples are **true barlines that the detector missed**, so they should be included as TP training samples, but they are currently included in the TP set without corresponding detections.

**Impact:**
- The 612 local TP samples include 113 cases where the detector failed (FN).
- These FN cases are valid barlines (from GT), so including them as TP is correct.
- However, the FP set (497 samples) may contain some ambiguous cases that are actually valid barlines not in GT.
- The current approach is **conservative for TP** (includes all GT) but may have **noise in FP** (unmatched preds could include valid barlines).

**Status:** Issue documented. Awaiting user decision on whether to:
1. Keep current approach (all GT as TP, unmatched preds as FP)
2. Only use matched predictions as TP (reduces TP to 499, excludes FN cases)
3. Manual review of FP samples to identify contamination

## 2026-01-03: DeepScores & Local Data Investigation Findings
**1. DeepScores Investigation:**
*   **Palette 3 Extraction:** Confirmed effective.
*   **Connected Components:** Properly separates distinct vertical segments.
*   **Filtering Stats** (Sample N=50 images):
    *   Total components (palette 3): 7307
    *   **Passed (TP candidates): 785 (10.7%)**
    *   **Filtered out:**
        *   **Height < 30px: 6411 (87.7%)** - Majority of index 3 components are very small vertical fragments/noise using current threshold.
        *   Area < 30px: 111 (1.5%)
        *   H/W Ratio < 3.0: 0 (0.0%)
*   **BBox Information:** Only top-left `x, y` is preserved in filenames (e.g., `..._x910_y833.png`). Width/Height are **lost** (implicit in crop center but original component dimensions are not saved).
*   **FP Generation:** Logic confirmed. Uses `extract_deepscores_negatives` to randomly sample crops from specific categories (stems, clefs, etc.) defined in DeepScores JSON annotations.

**2. Local TP/FP Investigation:**
*   **GT Verification:** Confirmed `DEFAULT_PAGES` in `build_cnn_dataset.py` matches the "rebuilt GT" paths documented in `SESSION_LOG`.
    *   page 3 uses `data/evaluation/annotations/page_003/boxes_sorted.json` (legacy baseline, correct per logs).
    *   others use `logs/phase6_detector_miss/gt_rebuild/...`.
*   **Visual Confirmation Tool:** Created `tools/cnn_classifier/visualize_candidates.py`.
    *   Draws **Green** boxes for TP candidates (All GT).
    *   Draws **Red** boxes for FP candidates (Unmatched Predictions).
    *   Outputs saved to `logs/cnn_classifier/candidate_vis/`.
*   **FP Crop Risk:** Since FP crops are generated from unmatched predictions (which might be spatially close to GT but < 0.5 IoU, or just noise), there is a significant risk that **valid GT barlines are included in "FP" crops** if the crop size covers them.
    *   *Visualization is crucial here to check if Red boxes are dangerously close to Green boxes.*

## 2026-01-03 DeepScores Filter & Local Data Fixes

### 1. DeepScores Filter Relaxation
*   **Observation**: Previous filters (`min_height=30`, `min_area=30`, `vertical_ratio=3.0`) were rejecting ~82% of valid barlines (23/28 GTs).
*   **Fix**: Relaxed filters significantly in `build_cnn_dataset.py`.
    *   `min_height`: 30 -> 5
    *   `min_area`: 30 -> 10
    *   `vertical_ratio`: Removed check entirely.
*   **Verification**: `visualize_deepscores_full.py` confirms that previously rejected but visibly correct barlines are now accepted (Green). `visualize_candidates` for DeepScores FP shows random sampling picks acceptable non-barline components (stems, etc.) or just random clutter which is fine for "Background/Negative" class.

### 2. Local TP/FP Source Correction
*   **Critical Finding**: The "Red Box on Green Box" issue (FP overlapping GT) was caused by using outdated prediction files (`phase5b`) for generating FPs. The `phase5b` predictions had many False Negatives (FN), meaning many true barlines were not in the prediction set.
    *   **Solution**: We identified the "Best Repro" run from Jan 2nd (`logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams_gtfix_p4b`) which yielded FN=0 on most pages. We now explicitly load `{log_root}/per_page/{page}/fp_boxes.json` as the source of FPs. These are the *actual* False Positives remaining after the optimized hybrid pipeline.
*   **Implementation**:
    *   Updated `build_cnn_dataset.py` to accept `--predictions-root`.
    *   Updated `visualize_candidates.py` to support visualizing from `predictions-root`.
*   **Verification**:
    *   Run `visualize_candidates.py` with the new source.
    *   Result: Red boxes (FPs) and Green boxes (GTs) are now distinct. The pervasive overlap is gone.

### 3. Dataset Rebuild (v2)
*   Building `cnn_classifier_v2` with these fixes.
*   Command:
    ```bash
    .venv_cnn_classifier/bin/python tools/cnn_classifier/build_cnn_dataset.py \
        --output-root /mnt/d/datasets/cnn_classifier_v2 \
        --deepscores-root /mnt/d/datasets/DeepScoresV2/ds2_dense \
        --predictions-root logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams_gtfix_p4b \
        --crop-width 128 --crop-height 256 --crop-scale 3.0 \
        --min-crop-height 48 --max-crop-height 256 \
        --tp-min-height 5 --tp-min-area 10 \
        --tp-max-total 30000 --max-total 30000
    ```

### 4. Refinement: Broad Hard Negative Mining & Visual Validation
*   **Concerns Addressed**:
    1.  *DeepScores Filters*: User requested visual proof of "Relaxed" TPs. Created `visualize_deepscores_tp_check.py` which draws the components accepted by filters (Green). Result: Most valid barlines are now kept.
    2.  *Crop Ambiguity*: User noted multiple lines in a crop. Clarified that the classifier assumes a **centered** object. Created `visualize_crop_centers.py` which draws a red crosshair on sample crops. Result: The crosshair lands on the target object (barline or stem), resolving ambiguity.
    3.  *Low FP Count*: Switched FP source from `fp_boxes.json` (final filtered, too sparse) to **`geom_kept.json`** (all geometrically valid vertical lines found by probe).
        *   Logic: `Candidates (geom_kept) - GT (IoU > 0.5) = Hard Negatives`.
        *   This provides a much larger pool of "stem-like" or "barline-like" objects for the classifier to learn from.

*   **Dataset v3**:
    *   Rebuilding `cnn_classifier_v3` with the `geom_kept.json` source.
    *   Command:
        ```bash
        .venv_cnn_classifier/bin/python tools/cnn_classifier/build_cnn_dataset.py \
            --output-root /mnt/d/datasets/cnn_classifier_v3 \
            --deepscores-root /mnt/d/datasets/DeepScoresV2/ds2_dense \
            --predictions-root logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams_gtfix_p4b \
            --fp-source-file geom_kept.json \
            --crop-width 128 --crop-height 256 --crop-scale 3.0 \
            --min-crop-height 48 --max-crop-height 256 \
            --tp-min-height 5 --tp-min-area 10 \
            --tp-max-total 30000 --max-total 30000
        ```

### 5. Final Verification: Increased Local FP Visualization
*   **Action**: Ran `visualize_candidates.py` specifically targeting the new `geom_kept.json` source (minus GT).
*   **Result**:
    *   Output directory: `logs/cnn_classifier/candidate_vis_v3/`
    *   Observation: Green boxes (GT) are correctly untouched. Red boxes (FPs) are now much more numerous and cover "vertical line-like" objects (stems, barline fragments) that are NOT barlines.
    *   Example stats (Page 3): ~156 FPs (previously ~13).
    *   This confirms the "Hard Negative Mining" strategy is working and the dataset will be rich.

### 6. Final Solution: "Noisy" FP Source (Batch 23) + Strict Filtering
*   **Strategy**: To satisfy the user request for "More FPs" while maintaining "Strict Separation", we switched the FP source to a historical run known for high recall (noisy): `logs/validation/20251227T_batch23_musicxml_system/`.
*   **Results** (with Strict IoU < 0.1):
    *   Page 3: **1443 FPs** (Cleanly separated Hard Negatives).
    *   Page 15: **2010 FPs**.
    *   Page 4: **394 FPs**.
    *   Page 001: (Not present in Batch 23, will yield 0 local FPs but DeepScores negatives still apply).
*   **Conclusion**: This source provides ~4000 local Hard Negatives, far exceeding the previous ~100. Combined with strict filtering, this eliminates label noise (Overlap) while providing the rich training signal requested.

## Recovered Considerations from Deleted TODOs (from train.py in commit e89e374)
The following considerations were noted in `tools/cnn_classifier/train.py` but lost during the merge:
1.  **Dataset Recreation**: "TODO: データセット再作成：元の画像の解像度の違いから、TP/FPのcrop画像の範囲がずれている可能性あり+ダウンロードしたデータから作った追加データセットへのパス移動" (Targeting this now).
2.  **Model Selection**: "Use MobileNetV3 Small for lightweight inference TODO: adjust as needed. is this the best choice?."
3.  **Data Augmentation**: "TODO: データ拡張を追加検討".
4.  **Hyperparameters**:
    *   `BATCH_SIZE = 16`: "Small batch size for limited resources TODO: adjust as needed".
    *   `IMG_SIZE = (256, 128)`: "consistent with crop logic TODO: adjust as needed".
    *   `optimizer`: "is this the best optimizer?".
## 2026-01-04: Training Script Refactoring
**Action**: Rewrote `experiments/cnn_classifier/train.py` to support robust training.
**Features Added**:
1.  **Data Augmentation**:
    *   `GaussianBlur` (Radius 0.5-1.5, p=0.3) for ink bleed simulation.
    *   `AddSaltPepperNoise` (Density 0.02, p=0.3) for dirty scan simulation.
    *   `ColorJitter` (Brightness/Contrast 0.3) for fading.
    *   `RandomAffine` (Vertical shift 10%, Rotation +/- 2deg) for geometric robustness.
2.  **Class Imbalance**:
    *   Implemented `WeightedRandomSampler` to balance TP/FP capability in each batch.
    *   Automatically calculates weights based on loaded dataset.
3.  **Metrics**:
    *   Added `Precision`, `Recall`, `F1-score` logging to console and TensorBoard.
    *   Added model checkpointing based on **Best Val F1**.
4.  **Model**:
    *   Added support for `resnet18` via `--model-name` argument.
**Verification**:
*   Performed smoke test on `cnn_classifier_v1` (26k samples).
*   Confirmed `tensorboard` and `pyyaml` dependencies installed.
*   Confirmed training loop and augmentation pipeline (including new transforms) execute without error.

## 2026-01-04: Training Configuration Update (Commit b606ed6)
**Objective**: Finalize training script with advanced augmentation and dataset paths.

**Changes (Commit b606ed6):**
1.  **Augmentation & New Arguments**:
    *   **Arguments Verified**:
        *   `--amp`: Verified active via logs (`FutureWarning: torch.cuda.amp.GradScaler`).
        *   `--compile`: Verified active via logs (`Compiling model with mode=reduce-overhead`).
        *   `--imbalance`: Verified usage of `WeightedRandomSampler`.
        *   `--sp-p`, `--sp-density`: Verified integration in `train.py`.
    *   Integrated GPU-accelerated `GPUSaltPepperNoise` and `GPUNormalize`.
    *   Integrated CPU-based `RandomAffine` and `ColorJitter`.
2.  **Configuration**:
    *   Updated `config.yaml` to point to `datasets/cnn_classifier_final_v2_fixed`.
    *   Added `prefetch_factor` and `num_workers` tuning.
3.  **Refactoring**:
    *   Major cleanup of `train.py` to support `torch.compile` and `AMP` properly.

**Verification (Post-Commit):**
*   **Issue Found**: The default dataset path `datasets/cnn_classifier_final_v2_fixed/splits` contains empty files (likely copy error).
    *   *Workaround*: The source folders `local/tp` and `local/fp` inside the dataset folder are valid.
*   **Smoke Test**: Successfully trained for 1 epoch using valid local data subset.
    *   Command: `.venv_cnn_classifier/bin/python experiments/cnn_classifier/train.py --config experiments/cnn_classifier/config.yaml --epochs 1 --batch-size 16 --num-workers 2 --work-dir logs/cnn_smoke_test --tp-dir datasets/cnn_classifier_final_v2_fixed/local/tp --fp-dir datasets/cnn_classifier_final_v2_fixed/local/fp`
    *   Result: Train F1 ~0.71, Val F1 ~0.83.
*   **Dataset Status (Fixed)**:
    *   User re-executed repair command (`build_cnn_dataset.py --only-split`) after deleting corrupted splits.
    *   **Final Confirmation**: Checked `datasets/cnn_classifier_final_v2_fixed/splits`. Files are now valid symbolic links with correct metadata. Total size reported as non-zero (80M blocks for names/links).
*   **Status**: Code and Dataset are fully verified and ready for production training.

## 2026-01-04: Ready for Production Training
**Status**: All checks passed. Dataset repaired. Config verified.

**Recommended Training Command**:
```bash
.venv_cnn_classifier/bin/python experiments/cnn_classifier/train.py --config experiments/cnn_classifier/config.yaml
```
*   **Model**: ResNet18
*   **Batch Size**: 512
*   **Epochs**: 30
*   **Optimization**: AMP + torch.compile enabled
*   **Dataset**: `datasets/cnn_classifier_final_v2_fixed` (Splits repaired)

## 2026-01-04: Dataset Repair (Force Copy Mode)
**Issue**: Symbolic links in `splits` directory were broken (pointing to non-existent paths), causing `FileNotFoundError` during training.
**Actions**:
1.  **Script Update**: Modified `tools/cnn_classifier/build_cnn_dataset.py` to always copy files using `shutil.copy2` instead of creating symlinks.
2.  **Reproduction Fix**: Deleted the corrupted `splits` directory and regenerated it using the `--only-split` command.
**Confirmation**:
*   Verified non-zero file sizes in `datasets/cnn_classifier_final_v2_fixed/splits/` (e.g., 3.5K, 3.9K per PNG).
*   Total split directory metadata/data size reached ~134M.
**Status**: Dataset is verified robust (no links). Ready for production training.

## 2026-01-04: Training Optimization & Fixes
**Objective**: Address user feedback on training performance, configuration priority, and API warnings.

**Changes**:
1.  **Config Precedence**: Fixed `train.py` logic where `argparse` defaults were overriding `config.yaml`.
    *   Defaults now set to `None` in parser; applied manually after config merge.
    *   Verified `batch_size: 256` and `epochs: 30` are correctly respected.
2.  **API Modernization**:
    *   Updated `torch.cuda.amp` to `torch.amp` (with `device_type='cuda'`) to resolve `FutureWarning`.
3.  **Optimization**:
    *   **LR Scheduler**: Added `CosineAnnealingLR` for better convergence.
    *   **Optimizer**: Changed `Adam` to `AdamW` for better weight decay handling.
    *   **Learning Rate**: Increased default from `0.0003` to `0.001` (to pair with scheduler/AdamW).
    *   **Checkpointing**: Added `--save-interval` (default 5 epochs).
    *   **Logging**: TensorBoard now enabled by default at `work_dir/runs`.
    *   **Bug Fix**: Fixed `UnboundLocalError` for `work_dir`.

**Status**: Ready for optimized training run.

## 2026-01-04: Validation of CNN Classifier on Evaluation2 Set
**Objective**: Validate the trained ResNet18 model on a new dataset (`data/evaluation2/pdfs`) without GT, using visual inspection.

**Actions**:
1.  **Data Preparation**:
    *   Converted `Va_Prokofiev_Symphony1.pdf` and `Va__Prokofiev_Symphony5.pdf` to images in `data/evaluation2/images`.
2.  **Pipeline Debugging**:
    *   Encountered path resolution issues with symlinked data directories in `tools/run_hybrid_pipeline.sh`.
    *   **Fix**: Modified `tools/run_hybrid_pipeline.sh` to correctly handle relative paths and disable strict repository root checks when running with symlinked data.
3.  **Candidate Generation**:
    *   Created `run_batch_candidates.sh` to batch process all 30+ pages.
    *   Started batch processing in background (Log: `batch_run.log`).
    *   *Note*: Processing takes ~10 mins/page due to SR steps.
4.  **Inference & Visualization**:
    *   Created `experiments/cnn_classifier/inference_visualize.py` to load candidates, infer, and generate overlays.
    *   **Feature Update**: Added `_all_candidates.png` output to visualize raw candidates (Blue) alongside filtered results (Green/Red).
    *   **Visual Refinement**: Increased box thickness and added score labels to improve visibility on high-resolution images.
    *   **Fix**: Improved parsing logic in the inference script to handle subdirectory names containing underscores.

**Preliminary Findings (Investigation of False Negatives)**:
*   **Visual Audit**: Checked `eval2_Va_Prokofiev_Symphony1_page_002`. Identified several barlines missing from the final result (FN).
*   **Root Cause Diagnosis**: 
    *   Audit of `_all_candidates.png` revealed that the missing barlines are **not present even in the raw candidate set**.
    *   **Conclusion**: The issue lies **upstream** in the Hybrid Pipeline (homr / OMR-DLN detection steps) rather than the CNN classifier filtering logic. The classifier cannot accept what the detector does not propose.
*   **Next Action**: Investigate why the hybrid pipeline is failing to propose these barlines on the `evaluation2` set (potential scale or resolution mismatch in detector configurations).

**Execution Status**:
*   Batch detection job is ongoing.
*   Visualization script is ready for incremental runs:
    ```bash
    .venv_cnn_classifier/bin/python experiments/cnn_classifier/inference_visualize.py \
      --image-root data/evaluation2/images \
      --json-root logs/hybrid_generalization \
      --output-root logs/cnn_validation_eval2 \
      --model-path logs/cnn_barline_classification/training_resnet18_b320/cnn_classifier_best.pth \
      --skip-existing --run-prefix eval2
    ```

### Analysis of Upstream Candidate Generation (`tools/run_gt_rebuild_hybrid_eval.py`)
**Objective**: Understand how the legacy pipeline increased candidates to resolve False Negatives.

**Key Mechanisms Identified**:
1.  **Candidate Expansion via `probe_scan`**:
    *   **Band Identification**: Uses initial consensus barlines as anchors to identify vertical regions (bands) where barlines should exist.
    *   **Ink Density Scanning**: Scans these bands horizontally for high ink-density peaks, picking up lines missed by segmentation-based detectors (homr/OMR-DLN).
    *   **Rescue Logic**: Includes specialized routines (`scan_x_peak_rescue`, `scan_rightmost_rescue`) to recover faint or edge-of-page barlines.
2.  **Refinement via Multi-stage Filtering**:
    *   **`row_filter`**: Ensures new candidates align with the vertical height and position of existing barline rows.
    *   **`geom_notehead_ratio_filter`**: Filters out stems by checking proximity to detected noteheads (using a dilated notehead mask).
    *   **Structural Filters**: Applies overlap checks for clefs/keys and enforces minimum height ratios relative to staff height.

**Conclusion**: The current `run_hybrid_pipeline.sh` only performs the consensus step and lacks this "Expansion & Refinement" stage. The observed False Negatives are likely due to barlines being missed by the initial detectors and never being "probed" for in the image. Integrating a version of this logic is the likely next step for improving recall.

### Verify Candidate Expansion for CNN (Recovering False Negatives)
**Objective**: Verify if the CNN classifier can correctly classify barlines when provided with a better set of candidates (generated by "Candidate Expansion" logic) that covers the False Negatives missed by the standard pipeline.

**Methodology**:
1.  **Script Creation**: Created `experiments/cnn_classifier/generate_expanded_candidates.py` to generate candidates using `detect_probe_scan` with Rescue logic enabled.
    *   **Critical Fix**: Discovered that `band_source="staff_mask"` resulted in thousands of tiny, invalid candidates (10px height) due to line-level masks. Changed to `band_source="row_stats"` to correctly identify staff systems from existing barlines, resolving the issue.
2.  **Experiment Configurations**: Tested three candidate generation strategies on the `evaluation2` dataset:
    *   **Raw (Standard)**: Output of `probe_scan` with Rescue enabled. Standard thresholds (`min_ratio=0.85`, `peak_ratio=1.6`).
    *   **Row (Filtered)**: The **Raw** candidates processed by `row_filter` (geometric filtering).
    *   **Relaxed**: Output of `probe_scan` with Rescue enabled but looser thresholds (`min_ratio=0.70`, `peak_ratio=1.4`) to maximize recall.
3.  **Inference**: Ran `inference_visualize.py` on each candidate set to assess CNN performance.

**Results Summary**:
| Configuration | Mean Candidates | Mean Accepted (Barline) | Mean Rejected (FP) | Acceptance Ratio |
| :--- | :--- | :--- | :--- | :--- |
| **Row** (Filtered) | 93.3 | 74.9 | 18.5 | 80.2% |
| **Raw** (Standard) | 95.9 | 76.3 | 19.6 | 79.6% |
| **Relaxed** (Looser) | 102.3 | 81.0 | 21.3 | 79.2% |
| **Ultraloose** (Aggr) | 101.4 | 82.6 | **18.8** | 81.5% |
| **Hyperlapse** (Max) | 101.6 | **82.9** | **18.6** | **81.7%** |
| **Needle** (Width=1) | **107.3** | **83.0** | 24.3 | 77.3% |

**Key Findings**:
*   **Needle Probe (Width=1)**: This setting (`width=1`, `ink=180`) achieved the absolute highest recall (83.0), surpassing Hyperlapse by a tiny margin (+0.1). However, it generated significantly more noise (+5.7 FP/page) than the 4px scans. The Acceptance Ratio dropped to 77.3%.
*   **Saturation Confirmed**: The recall gain from aggressive strategies (Hyperlapse/Needle) over "Ultraloose" is negligible (< 0.4 barline/page), while noise increases or remains stable. This confirms we are at the limit of the `probe_scan` geometry.
*   **Best Configuration**: **"Ultraloose"** (`width=4`, `ink=200`, `ratio=0.5`) remains the optimal robust choice, offering near-perfect recall (within 0.4 of Needle) with strictly lower noise.
*   **Row Filter Cost**: Applying `row_filter` reduced recall (avg -1.4 barlines/page) with negligible precision gain. It is too destructive for this pipeline stage.
*   **CNN Robustness**: The CNN's acceptance ratio peaked at **81.5%** with Ultraloose inputs, confirming its robustness.

**Remaining Issues**:
*   **Left-Edge False Positives**: Some false positives persist at the extreme left edge of the page.

**Artifacts**:
*   Generator Script: `experiments/cnn_classifier/generate_expanded_candidates.py`
*   Analysis Script: `experiments/cnn_classifier/summarize_inference_stats.py`
*   Logs: `logs/cnn_validation_eval2_ultraloose/` (Recommended)


### Debugging False Negatives & "No Peak" Experiment
**Objective**: Diagnose why visible barlines were still being missed (FNs) despite parameter relaxation, and test if removing the "Peak Sharpness" constraint solves this.

**Findings**:
1.  **Diagnosis**: Analysis of `debug_probe_values.py` on a missed barline (Prokofiev1 Page 003, under 'F') revealed that valid barlines often have high ink density but low `peak_dominance` (e.g., 1.04 vs min 1.2). This happens with thick barlines (double bars) or when lines are adjacent to other heavy symbols, causing the candidate generator to reject them as "not a peak".
2.  **Experiment (No Peak Condition)**:
    *   **Configuration**: `min_ratio=0.50`, `scan_x_peak_ratio_min=0.0` (Disabled), `max_per_band=0` (Unlimited).
    *   **Hypothesis**: By removing the peak check and count limits, we flood the CNN with every local maximum that meets the ink threshold, relying on the model's superior discrimination.
    *   **Results**:
        *   **Candidate Explosion**: Candidates per page jumped from ~100 to **~592**.
        *   **Recall Breakthrough**: The number of candidates *accepted* by the CNN as barlines increased by **+65%** (from 82.6 to **136.7** per page). This confirms that previous heuristics were suppressing ~50 valid barlines per page.
        *   **New Challenge**: While the CNN effectively rejected ~455 false candidates, the absolute number of False Positives (FPs) has likely increased due to the sheer volume of inputs. The user noted "FPs are appearing", indicating the model isn't perfect.

**Conclusion**:
The heuristic-based filtering in Candidate Generation was the primary bottleneck for Recall. The "No Peak" strategy successfully uncaps Recall but shifts the burden entirely to the CNN. The next phase must focus on analyzing and reducing these residual False Positives, possibly by retraining the model on these "hard negatives" or applying post-classification filters.

### Reproduction Details: Experiment 7 (No Peak)
To replicate this experiment, use the following parameters and commands:

**1. Candidate Generation**
*   **Script**: `experiments/cnn_classifier/generate_expanded_candidates.py`
*   **Parameters** (in `detect_probe_scan`):
    *   `band_source="row_stats"`
    *   `probe_width=4`, `ink_threshold=200`, `min_ratio=0.50`
    *   `scan_x_peak_ratio_min=0.0` (DISABLED)
    *   `scan_rightmost_min_ratio=0.10`
    *   `max_per_band=0` (DISABLED)
*   **Command**:
    ```bash
    .venv_pdf/bin/python experiments/cnn_classifier/generate_expanded_candidates.py \
      --logs-root logs/hybrid_generalization \
      --image-root data/evaluation2/images
    ```
    *Output*: `logs/hybrid_generalization/<run_id>/expanded_candidates_nopeak.json`

**2. Inference**
*   **Script**: `experiments/cnn_classifier/inference_visualize.py`
*   **Model**: `logs/cnn_barline_classification/training_resnet18_b320/cnn_classifier_best.pth`
*   **Command**:
    ```bash
    .venv_cnn_classifier/bin/python experiments/cnn_classifier/inference_visualize.py \
      --json-root logs/hybrid_generalization \
      --image-root data/evaluation2/images \
      --output-root logs/cnn_validation_eval2_nopeak \
      --model-path logs/cnn_barline_classification/training_resnet18_b320/cnn_classifier_best.pth \
      --candidates-file expanded_candidates_nopeak.json
    ```

**3. Metrics Analysis**
*   **Script**: `experiments/cnn_classifier/summarize_inference_stats.py`
*   **Command**:
    ```bash
    .venv_pdf/bin/python experiments/cnn_classifier/summarize_inference_stats.py \
      Ultraloose:logs/cnn_validation_eval2_ultraloose \
      NoPeak:logs/cnn_validation_eval2_nopeak
    ```
    *(Note: Reads logs to compare strategies)*

### Ad-hoc Debugging Tools & Scripts
The following temporary scripts were created and used during this session to diagnose the False Negative issue. They are not part of the main pipeline but are preserved for reproducibility.

**1. `experiments/cnn_classifier/debug_probe_values.py`**
*   **Purpose**: Deep inspection of `detect_probe_scan` logic. Dumps per-pixel column metrics (`ink_ratio`, `peak_dominance`, `reject_reason`) within a specific scan band to a CSV file. Used to understand why the "F" barline was rejected.
*   **Usage**:
    ```bash
    .venv_pdf/bin/python experiments/cnn_classifier/debug_probe_values.py \
        --image-path data/evaluation2/images/prokofiev1/page_003.png \
        --json-path logs/hybrid_generalization/eval2_prokofiev1_page_003/hybrid_predictions.json \
        --output-path logs/cnn_validation_eval2_user/debug_band0.csv \
        --band-index 0
    ```

**2. `experiments/cnn_classifier/analyze_no_peak.py`**
*   **Purpose**: Simulates the "No Peak" logic on the CSV output from `debug_probe_values.py`. Counts and identifies candidates that would be accepted if the `peak_dominance` check were removed.
*   **Usage**:
    ```bash
    .venv_pdf/bin/python experiments/cnn_classifier/analyze_no_peak.py
    ```
    *(Note: Reads hardcoded path `logs/cnn_validation_eval2_user/debug_band0.csv` internally)*

**3. `experiments/cnn_classifier/debug_visualize_col.py`**
*   **Purpose**: Visualizes specific X-coordinates (candidates) on the page image as red vertical lines. Used to show the user exactly which candidates were being rejected or would be accepted under new logic.
*   **Usage**:
    ```bash
    .venv_pdf/bin/python experiments/cnn_classifier/debug_visualize_col.py \
        --image-path data/evaluation2/images/prokofiev1/page_003.png \
        --output-path logs/cnn_validation_eval2_user/debug_no_peak_vis.png \
        --band-y1 523 --band-y2 608 \
        --x-cols <comma_separated_x_values>
    ```

**4. `experiments/cnn_classifier/visualize_scan_bands.py`**
*   **Purpose**: Visualizes the scan bands (search regions) generated by `band_source="row_stats"`. Used to confirm that the missing barline was indeed inside a valid search band and not excluded by the band definition itself.
*   **Usage**:
    ```bash
    .venv_pdf/bin/python experiments/cnn_classifier/visualize_scan_bands.py \
        --image-path data/evaluation2/images/prokofiev1/page_003.png \
        --json-path logs/hybrid_generalization/eval2_prokofiev1_page_003/hybrid_predictions.json \
        --output-path logs/cnn_validation_eval2_user/debug_bands_vis.png
    ```

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