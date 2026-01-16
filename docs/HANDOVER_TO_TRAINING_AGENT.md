# Handover to Training Agent (experiment/cnn_classifier)

You are operating in the `experiment/cnn_classifier` worktree.
Your primary goal is to **train a lightweight CNN classifier** to distinguish true barlines from false positives (stems, clef parts, etc.), using the data accumulated in `logs/`.

## Context & Constraints
- **Branch:** `experiment/cnn_classifier`
- **GPU:** GeForce 4060 (8GB VRAM). Resource is limited; use lightweight models (e.g., MobileNetV3, ResNet18) and small batch sizes.
- **Data:** The `logs/` directory is symlinked from the main worktree. It contains `fp_crops` and `tp_crops` from previous experiments.
- **API Status:** Gemini API is currently unavailable/rate-limited. Focus entirely on local training tasks.

## Initial Setup Tasks
1.  **Log Separation:**
    - Create `docs/DEVLOG_CNN_TRAINING.md` for your session logs.
    - Do NOT append to `docs/DEVELOPMENT_LOG.md` to avoid merge conflicts with the main branch.
    - Update `README.md` (in your worktree) to point to `docs/DEVLOG_CNN_TRAINING.md` for active logs.

2.  **Dataset Preparation:**
    - Explore `logs/` to find usable crop images (`fp_crops` folders from various runs).
    - Note: You may need to generate `tp_crops` if they are not saved. Check `run_gt_rebuild_hybrid_eval.py` options or write a script to extract TPs based on GT.
    - Investigate **DeepScores V2** dataset availability for pre-training or augmentation (optional but recommended if local data is insufficient).

3.  **Training Pipeline:**
    - Create a training script (e.g., `experiments/cnn_classifier/train.py`).
    - Implement a simple data loader and binary classification model.
    - Run training in the background.

## Communication
- Do not modify files outside your worktree.
- If you need to communicate results back to the main branch, save them as artifacts in `logs/` (which is shared) or update `docs/NEXT_SESSION_NOTES.md` in your branch (to be merged later).
