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
    *   **Decision**: Geometric heuristic (clustering by gap) was found unreliable.
    *   **Implementation**: Simplified logic to rely on **Explicit System Index** (from upstream metadata) or fallback to **Single System per Page**.
    *    Verified with unit tests using synthetic data.
3.  **Basic Numbering Logic (`numbering.py`)**:
    *   Implemented `MeasureNumberer` which assigns sequential numbers to measures within defined systems.
    *   Verified with unit tests (single system and multi-page flow).

### Remaining Work / Next Steps
1.  **Real Data Verification**:
    *   Test `SystemBuilder` and `MeasureNumberer` against real `homr` outputs.
    *   **Blocker**: Current `homr` detection JSONs often lack explicit "Staff" bounding boxes, which are required for `SystemBuilder`. Need to extract staff info from `staff_mask` or `homr` internal logs.
2.  **Integration**:
    *   Create a pipeline script: `Input JSON` -> `Builder` -> `Numberer` -> `Output JSON`.
3.  **Advanced Logic (Deferred)**:
    *   **Upbeat (Anacrusis)**: Handling partial first measures.
    *   **Multi-measure Rests**: Reading rest numbers.
    *   **Repeats / Segno**: Handling non-linear numbering flow.

### Key Artifacts
- `src/measure_numbering/types.py`: Core data classes (`unsafe_hash=True` for set ops).
- `src/measure_numbering/builder.py`: System grouping logic.
- `src/measure_numbering/numbering.py`: Measure numbering logic.
- `docs/SESSION_LOG.md`: Detailed activity log.

---

## Track B: CNN Training (Training Worktree)
(See `docs/DEVLOG_CNN_TRAINING.md` in the training worktree for details)
