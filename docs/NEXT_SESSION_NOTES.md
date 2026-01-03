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

**Best Baseline Snapshot (Detector Output):**
- **Source Run:** `logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams`
- **Totals:** TP=611 / FP=15 / FN=0
- **Summary:** `logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams/summary_table.md`
- **Pinned Copy:** `logs/gt_rebuild_hybrid_eval/_best/summary.md` (update this when a better run is confirmed)

**Spec Draft (v0, open questions explicitly allowed):**
- **Input:** Use detector output from `logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams` (exact JSON schema/path to be confirmed).
- **Numbering Core:** Count measures left-to-right, top-to-bottom by staff system; default start at 1.
- **Upbeat (Anacrusis):** Detection TBD; treat as “measure 0” or “not counted” until rules are defined.
- **Movement Boundaries:** Auto-detect TBD; allow manual reset points as an interim rule.
- **Multi-measure Rests:** Detection/reading of rest-number notation TBD.
- **Divisi:** Leverage existing barline-detection context where possible; concrete rule TBD.
- **Output:** Start with JSON (measure index + barline bbox + page/system position), then optionally render.

**Immediate Tasks (Issue-Ready, No Real Data Needed):**
1.  **Scope/Spec Draft:** Define measure numbering rules and open questions (upbeat detection, movement boundaries, multi-measure rests, divisi handling).
2.  **Input/Output Schema:** Propose JSON schemas for barline input and measure output.
3.  **Data Structure Design:** Define classes for `Measure`, `StaffSystem`, and `Page`.
4.  **Traversal/Numbering Core:** Specify algorithm to traverse barlines and assign numbers with reset hooks.
5.  **Unit Test Scaffold:** Create minimal fixtures and tests for traversal + numbering.

**Immediate Tasks (Needs Real Data / Deferred):**
1.  **Input Contract:** Confirm exact detector output path + JSON keys from real logs.
2.  **Upbeat (Anacrusis) Rules:** Determine detection criteria from real scores.
3.  **Movement Boundary Detection:** Decide auto-detection rules after observing examples.
4.  **Multi-measure Rest Handling:** Evaluate OCR/template approach on real pages.
5.  **Divisi Handling:** Validate reuse of existing barline context on real outputs.

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
