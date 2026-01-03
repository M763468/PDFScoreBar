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
