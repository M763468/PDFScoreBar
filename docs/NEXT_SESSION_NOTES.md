# Next Session Notes

**Last Updated**: 2025-12-22
**Current Phase**: Phase 5b: FN Recovery (Strategy 1 Confirmed)

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

## Phase 5b — FN Recovery Strategies (In Progress)

This phase aims to recover FNs (especially the "ambiguous" majority) without regressing the confirmed `FP=0` baseline on `page_3`.

### B1) Improve candidate generation / detector recall (Primary)
**Hypothesis**: Lowering confidence thresholds or creating a naive union of detectors will recover "ambiguous" FNs.
- **Risks**: High risk of introducing FPs.
- **Mitigation**: Rely on the **Phase 4 filters** (proven robust) to clean up the increased candidate pool.

#### B1.1 Confirmed Result: homr min-height relaxation (Tested & Rejected — Ineffective)
- **Result**: Relaxing `--barline-min-height-factor` (1.0 → 0.8 → 0.6) recovered **zero** additional FN candidates across FN-only GT pages.
- **FN recovery**: 0 on `page_10`, `page_15`, `Prokofiev_001`, `Prokofiev_004`.
- **FP risk**: High (significant FP increases in raw homr output).
- **Regression**: Raw-level regression observed on `page_3` at factor=0.6.
- **Clarification**: The page_3 regression refers to **raw homr output**, not the final Phase 4 pipeline; Phase 4 FP=0 safety is **not** contradicted.

#### B1.1 Confirmed Result: omr-dln sweep + raw union (Measurement only)
- **omr-dln conf sweep**: FN-only recovery is flat at **22/64** for `conf=0.1..0.5`; page_3 raw FP stays ~**17–20**.
- **raw union (homr ∪ omr-dln)**: FN-only recovery improves to **36/64** (FN total **28**), but page_3 raw FP rises to ~**47–50**.
- **Interpretation**: conf tuning alone is not promising; raw union boosts recall but introduces raw FP risk. No hybrid integration yet.

#### B1.1 vs B2 Clarification (Planning)
- The completed **raw union** measurement is a detector-level check (B1.1) and also informs B2 because B2 considers union-like merge logic.
- B2’s core question is different: whether **hybrid merge logic** causes integration-loss FNs and can be fixed.
- Next step is **not** “adopt union,” but to **measure union outputs after Phase 4 filters** to see if FP=0 is preserved and how much FN recovery remains.

#### Remaining B1.1 Recall Experiments (Planned)
- [ ] **omr-dln** recall behavior (confidence threshold sweeps; raw outputs).
- [ ] **Detector union**: raw `homr ∪ omr-dln` (pre-hybrid).
- [ ] **Detector union (SR)**: `homr+SR ∪ omr-dln` (if feasible).
- [ ] **Comparison**: recall gain vs FP risk across homr, omr-dln, and unions.

### B2) Hybrid integration fixes (Secondary)
**Hypothesis**: The intersection-heavy logic of the current hybrid merger discards valid single-model detections.
- **What to test**:
  - Switch merge logic from "Consensus/Intersection" to "Union" or "Score-weighted Union".
  - Tune IoU thresholds and coordinate rounding for matching.
- **Expected Outcome**: Recovery of the ~8% "hybrid_integration_loss" FNs.
- **Risks**: Low. Cheap to implement.
- **Immediate measurement**: Evaluate union outputs **after Phase 4 filters** to verify FP=0 safety and net FN recovery (no pipeline changes yet).

#### B2.1 Confirmed Union (Strategy 1) Implemented & Evaluated ✅
- **Description**: A symmetric merge rule. A candidate is kept if it represents a consensus (IoU > 0.5) between **any two** detectors (`baseline`+`sr`, `baseline`+`omr`, or `sr`+`omr`).
- **Implementation**: Added as a `--merge-strategy` flag to `tools/generate_hybrid_results.py`.
- **FN Recovery (after Phase 4 row-filter)**:
  - **Total Recovered: 5 / 29** (17.2%)
  - `page_10`: Recovered **5** FNs.
  - `page_15`, `page_001`, `page_004`: Recovered **0** FNs.
- **FP Regression Guard (`page_3`)**: **PASSED**
  - The strategy introduced 8 FPs at the merge stage.
  - The existing Phase 4 filters (row + geom note-context) **successfully removed all 8 FPs**, resulting in a final score of **TP=152, FP=0, FN=0**.
- **Conclusion**: **"Confirmed Union" is the new baseline merge strategy.** It is safe and provides a modest but real improvement in FN recovery. This supersedes previous implicit baseline merge behavior.

#### **Next Steps (B2)**
- [ ] **Investigate Row Filter FN on `page_10`**: The row filter incorrectly removed one TP recovered by the new merge. This should be analyzed.
- [ ] **Design & Evaluate Strategy 2 ("Promiscuous Union")**: If more FN recovery is needed, this is the next logical step. It is expected to be higher-risk than Strategy 1.

**Recent check (measurement only):**
- Baseline Phase 4 on `page_3`: **TP=152, FP=0, FN=0** (reproduced).
- Union→Phase4 on `page_3`: **TP=152, FP=26, FN=0** → not safe under current Phase 4 filters.
- FN-only pages post-filter recovery: **34/64** (row filter only; geom notehead disabled outside `page_3`).

**Phase5-only generalized geom notehead eval (union inputs):**
- Implemented a page-agnostic endpoint_ratio notehead filter for evaluation only; outputs and overlays are under `logs/phase5b/notehead_geom_eval/20251221T141710/`.
- Union→(row + generalized geom) results: `page_3` **TP=151, FP=24, FN=1**; FN-only recovery **33/64** (see overlays for review).

**Phase5b2 hygiene step (analysis only):**
- Overlay semantics normalized, margin-like unmatched-kept classified, and stage counts verified under `logs/phase5b/notehead_geom_eval/20251221T141710/analysis_20251221T145756/`.

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

### Phase 5b status update (analysis)
- **Phase4 filter verification**: pixel ink-density filter is effectively disabled in the canonical Phase4 command (`--min-bbox-ink-density 0.0`, `--max-end-ink-density 1.0`); FP=0 is achieved by **row filter + geom note-context**.
- **FN trace breakdown (64 FN-only targets)**: detector-miss **35**, merge-loss **29**, row/notehead loss **0**.