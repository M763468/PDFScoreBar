# Next Session Notes

**Last Updated**: 2025-12-17
**Current Phase**: Phase 4 (Context Filtering & Final Polish)

---
### Note for AI Assistant (Operational Rule)
-   The `docs/SESSION_LOG.md` file must **not** be completely overwritten. During a session, new findings and logs should be appended, or only relevant sections should be edited. The file should only be cleared with explicit user permission.
---

## Current Status

### Phase 3: Geometric FP Reduction ✅ **COMPLETE**
- **Method**: Row-based consistency filter.
- **Documented Best Result**: On `page_3` hybrid detections, this filter achieves **TP=152, FP=2, FN=0**. This is the official baseline for the start of Phase 4.

### Phase 4: Context & Pixel Filtering (In Progress)
- **Goal**: Start from the `TP=152, FP=2` baseline and implement a context-based filter to achieve **`TP=152, FP=0, FN=0`**.
- **Action Taken**: A "Note Head Collision" filter has been implemented as a pixel-based heuristic in `experiments/fp_reduction/analyze_staff_consistency.py`.
    -   **Mechanism 1 (Note Head Heuristic)**: The `--max-end-ink-density` argument filters detections if there is high ink density at the top/bottom corners of the bounding box. This is designed to identify and remove note stems attached to note heads.
    -   **Mechanism 2 (Faint Artifact Filter)**: The `--min-bbox-ink-density` argument filters detections with very low average ink density within their bounding box.
- **Current State**: Initial analysis confirmed these filters can target the remaining FPs, but tuning was hampered by an incorrect baseline and a coordinate scaling issue (which is now resolved). The immediate next step is to reproduce the correct baseline and then properly tune these new filters.

## Remaining Work / Next Session Tasks

### High Priority
1.  **Reproduce `TP=152, FP=2` Baseline**:
    -   Tune the **geometric filter** parameters (`--tol-ratio`, etc.) in `analyze_staff_consistency.py` to replicate the documented best result of `TP=152, FP=2, FN=0`. My previous runs resulted in an inferior `TP=150, FP=2, FN=2`, which must be corrected first.

2.  **Tune Note Head & Pixel Filters**:
    -   Starting from the correct `TP=152, FP=2` baseline, apply and tune the `--min-bbox-ink-density` and `--max-end-ink-density` filters.
    -   The goal is to find thresholds that eliminate the 2 FPs while retaining all 152 TPs.

3.  **Advanced Context Filters (Fallback Plan)**:
    -   If a perfect threshold cannot be found on the low-resolution image, this remains the necessary next step. It involves scaling coordinates up to the high-res `data/training/images/page_3.png` to perform a more detailed pixel analysis, which should provide a clearer signal to distinguish faint objects.

### Low Priority
4.  **Generalization Testing (Page 10, 15)**:
    -   Once a stable filter configuration is found for `page_3`, apply it to other pages to test for regressions.

5.  **Documentation & Deployment**:
    -   Finalize the recommended pipeline configuration.
    -   Create a master script `run_full_evaluation.py` that chains Hybrid Pipeline -> Geometric Filter -> (Optional) Pixel Filter.

## Key Artifacts & Locations
- **Main Filter Script**: `experiments/fp_reduction/analyze_staff_consistency.py`
- **Correct Image for Analysis**: `data/evaluation/images/page_3.png`

### Data Notes
-   **Evaluation Images** (`data/evaluation/images/`): Low Res (~600-800px width). Use these for `hybrid_results.json` coordinates.
-   **Training Images** (`data/training/images/`): High Res (~2500-3500px width). Use for high-quality visualization or deep learning training.
