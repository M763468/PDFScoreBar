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