# Next Session Notes

**Last Updated**: 2026-01-03
**Current Phase**: **Plan A (Measure Numbering)** & **Plan B (CNN Training)** Parallel Execution

---
## Overview: Parallel Tracks

The project is currently split into two parallel tracks to address the "False Positive (FP) Reduction" bottleneck and advance the overall "Measure Numbering" goal.

1.  **Track A (Measure Numbering):** Focus on the logic and data structures for assigning measure numbers to detected barlines. This work is independent of the detector's perfection.
    *   **Worktree:** `ws_PDFScoreBar_model_exp` (Current)
    *   **Branch:** `feature/measure_numbering`
    *   **Active Log:** `docs/DEVLOG_MEASURE_NUMBERING.md`

2.  **Track B (CNN Training):** Focus on training a lightweight CNN (e.g., MobileNetV3) to filter out FPs (stems, artifacts) that Gemini 1.5 Flash struggled with.
    *   **Worktree:** `../ws_PDFScoreBar_training`
    *   **Branch:** `experiment/cnn_classifier`
    *   **Active Log:** `docs/DEVLOG_CNN_TRAINING.md`
    *   **Handover Note:** See `docs/HANDOVER_TO_TRAINING_AGENT.md` for setup instructions.

---

## Track A: Measure Numbering (This Worktree)

**Goal:** Design and implement the system to count measures based on detected barlines.

**Immediate Tasks:**
1.  **Directory Setup:** Create `src/measure_numbering/` (or similar).
2.  **Data Structure Design:** Define classes for `Measure`, `StaffSystem`, and `Page`.
3.  **Multi-measure Rest Logic:** Implement OCR/Template Matching to read numbers above H-bar rests (using OpenCV/Tesseract).
4.  **Graph/Sequence Logic:** Implement algorithm to traverse barlines and assign numbers, handling anomalies (upbeats, repeats - effectively or simplistically).

## Track B: CNN Training (Training Worktree)

**Goal:** Train a binary classifier (Barline vs. Artifact) using crops from `logs/`.

**Status:**
- Worktree created at `../ws_PDFScoreBar_training`.
- `logs/` symlinked to share data.
- **Action:** Open a new terminal, `cd ../ws_PDFScoreBar_training`, and instruct the AI to read `docs/HANDOVER_TO_TRAINING_AGENT.md`.

---

## Historical Context (Pre-Split)

See `docs/DEVELOPMENT_LOG.md` for all activities prior to 2026-01-03, including:
- Phase 6 Detector Miss Analysis
- Gemini 1.5 Flash Experiments (CoT + Rescue Prompt)
- Hybrid Detector Tuning (var88 baseline)

**Confirmed Baseline (Detector):** `var88` (clefs_keys left + probe_notehead_dilate=13 + notehead_dilate=7) achieves FN=0 but leaves some FPs. Track B aims to filter these.
