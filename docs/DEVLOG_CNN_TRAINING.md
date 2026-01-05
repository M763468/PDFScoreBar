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
