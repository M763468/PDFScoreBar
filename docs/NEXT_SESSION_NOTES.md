# Next Session Notes

**Last Updated**: 2026-01-04
**Current Phase**: **Plan A (Measure Numbering)** & **Plan B (CNN Training)** Parallel Execution

---
## Overview: Parallel Tracks

The project is currently split into two parallel tracks to address the "False Positive (FP) Reduction" bottleneck and advance the overall "Measure Numbering" goal.

1.  **Track A (Measure Numbering):** Focus on the logic and data structures for assigning measure numbers to detected barlines.
    *   **Worktree:** `ws_PDFScoreBar_model_exp` (Current)
    *   **Branch:** `feature/measure_numbering`
    *   **Active Log:** `docs/DEVLOG_MEASURE_NUMBERING.md`

2.  **Track B (CNN Training):** Focus on training a lightweight CNN to filter out FPs.
    *   **Worktree:** `../ws_PDFScoreBar_training`
    *   **Branch:** `experiment/cnn_classifier`
    *   **Active Log:** `docs/DEVLOG_CNN_TRAINING.md`

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


### Completed Work (Session 2026-01-04)
1.  **Scaffolding**: Created `src/measure_numbering` package and `types.py` (Data Structures: `Barline`, `Staff`, `System`, `Score`).
2.  **System Inference Logic (`builder.py`)**:
    *   **Decision**: Geometric heuristic (clustering by gap) was initially unreliable.
    *   **Implementation**: Simplified logic to fallback to **Single System per Page** or **Explicit System Index** first.
    *   **Refinement**: Implemented **Geometric Grouping for Divisi**, prioritizing **Aligned Physical Connectivity** (vertical ink check at aligned barline positions) to correctly handle multi-staff systems without false positives.
    *    Verified with unit tests and batch runs on Prokofiev 1 & 5.
3.  **Basic Numbering Logic (`numbering.py`)**:
    *   Implemented `MeasureNumberer` which assigns sequential numbers to measures within defined systems.
    *   Verified with unit tests (single system and multi-page flow).
4.  **Real Data Verification & Logic Refinement**:
    *   Tested against Page 10 real detection output.
    *   **Deduplication**: Implemented 15px threshold to merge redundant detector candidates.
    *   **Implicit Start**: Added logic to detect and complete missing first measures (ghost barlines).
    *   **Coordinate Scaling**: Identified and resolved downscaling issues in `homr` staff masks.
    *   **Visualization**: Confirmed correctness with centered measure numbers and transparent overlays.
    *   **Divisi Verification**: Confirmed robust grouping on Prokofiev dataset, distinguishing true divisi from coincidental alignment (e.g., elimination of false positives on Prokofiev 5).

### Completed Work (Session 2026-01-12)
1.  **Refine Multi-measure Rest Recognition**:
    *   **Phase 1.5 Logic Fixes (Completed)**:
        *   **End Bar Fix**: Implemented `MIN_MEASURE_WIDTH=25px` in `src/measure_numbering/numbering.py` to prevent counting end bars as separate measures.
        *   **Dataset Padding**: Updated `tools/create_mmr_train_data.py` to add 20px margin around measure crops.
        *   **Config Generation**: Created `data/evaluation2/rest_gt_config_all.json` covering all 68 evaluation pages for GT annotation.
    *   **Evaluation**: Re-ran batch evaluation (F1=0.53) - confirmed heuristics are insufficient, mandating the classifier approach.
    *   **Phase 2: Classifier-based MMR Detection (Completed)**:
        *   **Dataset**: Generated ~3700 samples (192 Rest) using config-based script.
        *   **Training**: Trained ResNet18 (Validation F1 > 0.99).
        *   **Integration**: Replaced heuristic script with CNN inference. Verified on Prokofiev 5 (Precision 94%, Recall 90%).

### Remaining Work / Next Steps
1.  **Refine & Scale Evaluation**:
    *   **Expand**: Run batch verification on `Shostakovich` and `Sibelius` datasets (requires fixing directory paths).
    *   **OCR Refinement**: Detailed diagnosis of the few remaining "detected but wrong number" errors.
2.  **Phase 3: OCR Selector (Planned)**:
    *   Train a secondary model or object detector to identify *which* number to read within a multi-measure rest (handling rehearsal marks vs rest counts).
3.  **Production-ready Integration**:
    *   Combine `Detector JSON` + `Staff Mask PNG` + `Numbering Logic` into a single standalone pipeline script.
    *   **Upbeats (Anacrusis)**: Formal detection or manual overrides.
    *   **Repeats / Segno**: Handling non-linear flow (if logical measure count differs from graphical sequence).
4.  **Multi-page & Performance Verification**:
    *   Run the numbering pipeline on full multi-page PDFs to ensure state (measure count) is correctly preserved.
    *   Implement movement boundary detection to reset numbering.
5.  **Divisi Logic Improvement (New)**:
    *   **Finding**: The current "Aligned Physical Connectivity" check (vertical ink) is too eager on single-staff pages with noise or extended barline ink (e.g., `Angerer_Kinder_Symphony`), causing false positive system grouping.
    *   **Action**: Refine the `SystemBuilder` logic. Potential ideas:
        *   Require *multiple* aligned connections (not just 1).
        *   Check for system brackets/braces (if available from detection).
        *   Adaptive thresholding based on page-wide statistics.

### Key Artifacts
- `tools/train_mmr_classifier.py`: Training script.
- `tools/generate_numbering_overrides_cnn.py`: Inference script (integrated).
- `mmr_classifier_best.pth`: Trained model weights.
- `docs/SESSION_LOG.md`: Detailed activity log.

---

## Track B: CNN Training (Merged)
This track is now merged back into the main workflow as the classifier has been successfully trained and integrated.
