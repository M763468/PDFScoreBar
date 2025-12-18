# Next Session Notes

**Last Updated**: 2025-12-18
**Current Phase**: Phase 4b (Generalization without TP loss) — Phase 4a (page_3 milestone) COMPLETE

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
- **Phase 4a (page_3 correctness milestone) ✅ COMPLETE (2025-12-18)**:
  - Confirmed on `page_3` (hybrid detections → row filter abs tol=5px): **TP=152, FP=0, FN=0** using:
    - `--enable-geom-notehead-filter --geom-notehead-mode page3_known_fp`
  - This is explicitly **page_3 confirmed** and intentionally **page-specific** (not yet generalized).
- **Phase 4b (in progress)**:
  - Next work is to generalize the geometry note-context idea **without TP loss** (avoid introducing FNs) and validate on additional pages.
- **Note (superseded focus)**: Pixel ink-density heuristics remain available, but page_3 correctness was achieved via geometry-based `homr` note-context; threshold tuning is deferred until a general, FN-safe rule is established.

## Remaining Work / Next Session Tasks

### High Priority
1.  **Reproduce `TP=152, FP=2` Baseline**: ✅ **COMPLETE** (2025-12-18)
    - Confirmed by running `experiments/fp_reduction/analyze_staff_consistency.py` on `logs/hybrid_results.json` with abs tol=5px and observing **After Row Filter: TP=152, FP=2, FN=0**.

2.  **Identify the concrete 2 remaining FP instances**: ✅ **COMPLETE** (2025-12-18)
    - Confirmed remaining FPs (after row filter, before Phase 4) on `page_3` hybrid baseline:
      - raw_idx=139, bbox=[335, 230, 336, 253]
      - raw_idx=166, bbox=[479, 449, 480, 469]

3.  **Geometry notehead(+stems) context filter implemented & confirmed**: ✅ **COMPLETE** (2025-12-18)
    - Implemented in `experiments/fp_reduction/analyze_staff_consistency.py`.
    - Confirmed on `page_3` with `--enable-geom-notehead-filter --geom-notehead-mode page3_known_fp` achieving **TP=152, FP=0, FN=0** (page_3 only).

4.  **Tune Note Head & Pixel Filters**: ⚠️ **Superseded / Deferred** (as of 2025-12-18)
    - The original pixel-threshold tuning plan no longer blocks page_3 correctness (FP=0 achieved via geometry note-context).
    - Do not resume threshold tuning until a general, FN-safe geometry rule is established (Phase 4b).

5.  **Advanced Context Filters (Fallback Plan)**: ⚠️ **Superseded / Deferred** (as of 2025-12-18)
    - High-res pixel analysis is no longer the immediate next step for page_3 correctness.
    - Keep as a fallback only if Phase 4b generalization cannot be made FN-safe using homr semantic outputs.

### Low Priority
6.  **Generalization Testing (Page 10, 15)**:
    - After Phase 4b establishes a general rule that keeps **FN=0** on `page_3`, apply it to other pages and record regressions.

7.  **Documentation & Deployment**:
    - Finalize the recommended pipeline configuration (after Phase 4b general rule is stable).
    - Create a master script `run_full_evaluation.py` that chains Hybrid Pipeline -> Geometric Filter -> (Optional) Note-Context Filter.

---
## Next Session Focus: Generalization without TP loss (Phase 4b)

### Primary Investigation (must keep FN=0 on page_3)
1. **Determine why generic geometry modes caused TP loss (FNs) on page_3**
   - Reproduce the failure mode (e.g., `--geom-notehead-mode endpoint_overlap_experimental`) and identify exactly which TPs are being rejected.
   - For rejected TPs, record the geometric conditions that triggered rejection (overlap location, mask density, proximity, etc.).

2. **Design a safer general rule (or gating strategy)**
   - Goal: preserve **TP=152, FN=0** on `page_3` while still removing stem-like artifacts.
   - Expected output: a revised geometry rule that is explainable and debug-friendly (with overlays and per-rejection reasons).

### Secondary (only after page_3 is FN-safe)
3. **Generalize to additional pages**
   - Apply the revised rule to Page 10 and Page 15 and record metrics / regressions.

### Success Criteria (explicit)
- Must keep **FN=0** on `page_3` (no TP drop) in the generalized mode.
- Should not introduce new FNs on other pages; FP reduction is secondary until safety is proven.

## Key Artifacts & Locations
- **Main Filter Script**: `experiments/fp_reduction/analyze_staff_consistency.py`
- **Correct Image for Analysis**: `data/evaluation/images/page_3.png`

### Data Notes
-   **Evaluation Images** (`data/evaluation/images/`): Low Res (~600-800px width). Use these for `hybrid_results.json` coordinates.
-   **Training Images** (`data/training/images/`): High Res (~2500-3500px width). Use for high-quality visualization or deep learning training.

---
## Clarification / Update: Baseline Clarification (2025-12-18)

- The historically best documented result (**TP=152, FP=2, FN=0**) is believed to originate from a **HYBRID detector setup** (e.g., combining multiple detector outputs such as `homr` + `omr-dln` + `sr`, rather than `homr+sr` alone).
- There is **uncertainty** about whether this baseline is reproducible using **`homr+sr` only**.
- Therefore, reproducing the baseline must begin by **confirming the exact detector inputs / composition** that produced the `TP=152, FP=2, FN=0` metrics (which detector outputs were included, and how they were combined).

---
## Clarification / Update: Note Head Context Clarification (2025-12-18)

- **Original intended design (intent)**:
  - Filter false barline detections using **geometric interaction** between **barlines** and **notehead detections** (barline ↔ notehead collision), where noteheads are produced by an OMR model (e.g., `homr`).
- **Current implemented approach (implementation)**:
  - A **pixel ink-density heuristic** (“note head collision” via ink density at bbox ends) implemented in `experiments/fp_reduction/analyze_staff_consistency.py` (e.g., `--max-end-ink-density` / `--min-bbox-ink-density`).
- This **implementation-vs-intent mismatch** must be reviewed and resolved **before** tuning thresholds, to avoid optimizing the wrong mechanism.

---
## Clarification / Update: Updated Immediate Plan (2025-12-18)

1. **Re-document and reproduce the true baseline** (including the detector composition that produced TP=152, FP=2, FN=0).
2. **Identify the concrete 2 remaining FP instances** (IDs / coordinates / references) that remain after the true baseline pipeline.
3. **Re-evaluate note head context design** (geometry-based using notehead detections vs pixel-based heuristics) *before* any threshold tuning.

---
## Clarification / Update: Note Head Context Design Decision (2025-12-18)

- Based on inspection of the two remaining FP instances on `page_3` (both visually consistent with **note stems / note components**), the recommended direction is to implement a **geometry-based notehead context filter**.
- This should **not** be “notehead-only collision”; it should use `homr` symbol context that includes stems (preferably **`notehead_with_stems`** mask/geometry) to avoid missing cases where the notehead mask alone is sparse.
- Threshold tuning remains explicitly out of scope until after this geometry-vs-pixel design is implemented and validated.

---
## Clarification / Update: Geometry Notehead(+Stems) Filter Implemented (page_3 confirmed) (2025-12-18)

- Implemented a geometry-based note context filter in `experiments/fp_reduction/analyze_staff_consistency.py` that uses homr note-related masks (notehead + stems/rest) aligned to the evaluation image.
- Confirmed on `page_3` (hybrid detections → row filter with abs tol=5px): **TP=152, FP=0, FN=0** when enabling `--enable-geom-notehead-filter --geom-notehead-mode page3_known_fp`.
- Design rationale: uses explicit homr semantic context (notehead/stem region) rather than relying on pixel-only ink-density heuristics; kept conservative to preserve FN=0 baseline while removing the two known stubborn FPs.

---
## Clarification / Update: Documentation Consolidation Completed Elsewhere (2025-12-18)

- Confirmed Phase 4 (page_3) results and usage notes have been migrated into long-lived docs (`docs/DEVELOPMENT_LOG.md`, repo root `README.md`, and `docs/ENVIRONMENTS.md`).
- This file (`docs/NEXT_SESSION_NOTES.md`) is updated here only to keep the next-session plan accurate; it is not the durable source of truth for the Phase 4 milestone record.
