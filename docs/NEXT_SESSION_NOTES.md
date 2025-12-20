# Next Session Notes

**Last Updated**: 2025-12-21
**Current Phase**: Phase 5b: FN Recovery (Planning: Detailed)

---
### Note for AI Assistant (Operational Rule)
- The `docs/SESSION_LOG.md` file must **not** be completely overwritten. During a session, new findings and logs should be appended, or only relevant sections should be edited. The file should only be cleared with explicit user permission.
---

## Phase 5 — FN Attribution & Recovery (Current Plan)

### Phase 5a Results (Confirmed) ✅ COMPLETE
**Conclusion**: False Negatives are fundamentally a **detector recall problem**.
- **~92% Ambiguous**: Not detected by either `homr` (SR) nor `omr-dln` (SR).
- **~8% Hybrid Loss**: Detected by at least one model but lost during integration.
- **Phase 4 Filters are Safe**: Post-processing geometric/pixel filters are **not** the cause of these FNs.

---

## Phase 5b — FN Recovery Strategies (Planning: Detailed)

This phase aims to recover FNs (especially the "ambiguous" majority) without regressing the confirmed `FP=0` baseline on `page_3`.

### B1) Improve candidate generation / detector recall (Primary)
**Hypothesis**: Lowering confidence thresholds or creating a naive union of detectors will recover "ambiguous" FNs.
- **What to test**:
  - **homr**: Relax confidence thresholds for barline candidates. Check internal parameters for thin-line sensitivity.
  - **omr-dln**: Relax YOLO confidence threshold (`--conf`).
  - **Detector Union**: Create a union of raw `homr` + `omr-dln` outputs (before hybrid consensus logic) to maximize recall.
  - **Fallback Generator**: Implement a lightweight classical CV proposer (Hough Transform / Vertical Projection) for "obvious" lines missed by ML.
- **Risks**: High risk of introducing FPs.
- **Mitigation**: Rely on the **Phase 4 filters** (proven robust) to clean up the increased candidate pool.

### B2) Hybrid integration fixes (Secondary)
**Hypothesis**: The intersection-heavy logic of the current hybrid merger discards valid single-model detections.
- **What to test**:
  - Switch merge logic from "Consensus/Intersection" to "Union" or "Score-weighted Union".
  - Tune IoU thresholds and coordinate rounding for matching.
- **Expected Outcome**: Recovery of the ~8% "hybrid_integration_loss" FNs.
- **Risks**: Low. Cheap to implement.

### B3) Pipeline-level gating
**Hypothesis**: Different pages (dense vs sparse, clean vs noisy) may require different pipelines.
- **What to change**:
  - Implement logic to conditionally apply specific detectors or fallbacks based on page characteristics (if needed).
- **Regression Guard**: Ensure `page_3` always runs its strict regression-tested path.

### B4) Evaluation Protocol for Phase 5b
**Standard**:
1.  **FN Recovery**: Measure recall improvement on the 4 FN-only GT pages (`page_10`, `page_15`, `Prokofiev_001`, `Prokofiev_004`).
2.  **FP Regression Guard**: **MUST** run full `page_3` pipeline after any change.
    - **Pass Criteria**: `TP=152, FP=0, FN=0`.
3.  **Qualitative Check**: Visual overlay inspection on non-GT pages to spot obvious new FPs.
4.  **Stop Condition**: If a change recovers FNs but creates stubborn FPs on `page_3`, rollback or refine filters.

---

## Phase 4 Summary (Quick Reference)

**Status**: ✅ COMPLETE & SAFE
- **Canonical Result**: `page_3` hybrid pipeline → **TP=152, FP=0, FN=0**.
- **Method**: Row-based geometric consistency + Notehead-context geometric filter (Ratio-based endpoint overlap).
- **Safety**: Cross-dataset review confirmed this logic is conservative and does not introduce FNs.
- **Details**: See `docs/DEVELOPMENT_LOG.md`.

---

## Completed Phases (Short Summary)

### Phase 3 ✅ COMPLETE (Row-Consistency Filter)
- Durable details: `docs/DEVELOPMENT_LOG.md`, `docs/fp_reduction/FINAL_SUMMARY.md`.

---
## Historical / Superseded Notes
- Phase 4b planning is superseded by Phase 5.
- "Any overlap" masks are forbidden (unsafe).
- Previous experiments are archived in `experiments/`.
