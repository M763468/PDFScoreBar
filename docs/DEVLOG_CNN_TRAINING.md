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