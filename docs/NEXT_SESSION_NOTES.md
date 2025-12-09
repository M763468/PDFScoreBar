# Next Session Notes

## Project Status: Barline FP Reduction
**Status**: **LOCALLY COMPLETE** (Dec 2025)

The optimization of visual heuristics for barline detection has concluded.
- **Heuristic 1 (Safe Filter)** is enabled.
- All other heuristics (H2-H5) are disabled.
- **Result**: 30 FPs remaining (irreducible without risking TPs).

## Documentation & Tools
- **Summary**: `docs/fp_reduction/FINAL_SUMMARY.md`
- **Logs**: `docs/fp_reduction/development_log.md`
- **Scripts**: `tools/fp_reduction/*.py`

## Recommended Next Sessions

### 2. Model Retraining Investigation
**Objective**: Analyze why the SegNet model fragments barlines.
**Action**: Check training data quality or experiment with varying the probability threshold (currently fixed).

### 3. External Model Evaluation
**Objective**: Benchmark other OMR libraries (e.g., commercially available APIs or newer research models) on `page_3`.

## Next Session – External Model Experiments & Heuristic Revisit (Dec 2025)

### 1) Current Status:
- homr + Safe Filter: TP=152, FP=30, FN=0 (F1 ≈ 0.910) – still the baseline and "recall anchor".
- YOLO-World zero-shot: complete failure (0 recall) even on synthetic vertical lines. Deemed unsuitable.
- OMR-DLN (YOLOv8m measure detector + inferred barlines):
  - TP = 137, FP = 17, FN = 15, F1 ≈ 0.895.
  - Significantly better precision (fewer FPs) but worse recall (misses 15 barlines).
  - Not acceptable as a standalone replacement for measure numbering due to non-perfect recall.

### 2) Next-Session TODOs:

#### Track 1: External Model Experiments
- [ ] Identify at least 1–2 additional candidate repositories from the prior model survey PDF that offer DeepScores-based YOLO or other detector models. Focus on models explicitly trained on music notation datasets.
- [ ] For each new candidate model:
    - [ ] Clone or verify existing clone in `external/`.
    - [ ] Set up a minimal evaluation wrapper (similar to `eval_yolo_world.py` / `eval_omr_dln.py`).
    - [ ] Evaluate on `data/evaluation/images/page_3.png` with our GT.
    - [ ] Record TP/FP/FN, Precision, Recall, F1.
- [ ] Summarize pros/cons vs homr baseline.
- [ ] **Next Candidate:** Grounding DINO (Priority 2 in `model_survey_plan.md`) should be evaluated next if no other DeepScores-trained YOLO variants are easily found with weights.
  - Status 2025-12-10: first run (`logs/model_experiments/grounding_dino/run_001`) yielded TP=0/FP=2/FN=152 (F1=0). When running inside the container with the host repo mounted, install `libglib2.0-0` + `build-essential`, pin `numpy==1.26.4`, and rebuild GroundingDINO ops via `pip install --no-build-isolation --no-deps -e external/grounding_dino` before execution.

#### Track 2: Heuristics & Ideas for homr-side improvements
- [ ] Revisit heuristic ideas from previous phases (e.g., Phase 28 continuation ideas for context-aware filtering like notehead-stem pairing, staff span validation, or note group map exclusion) that were put on hold.
- [ ] Identify ideas that are:
    - (a) still relevant for reducing FPs, and
    - (b) potentially useful if combined with a learned detector (e.g., using OMR-DLN's outputs as a strong filter for homr's FPs, or for reconciling conflicting detections).
- [ ] Propose where to plug these ideas into a refined roadmap, potentially as a "Phase X: Hybrid Pipeline: homr (high recall) + learned model (FP suppression)".
- [ ] Select 1–2 ideas that are cheap to prototype and do NOT require new datasets.
    - **Example ideas**:
        - **Hybrid Scoring**: Assign scores to homr and OMR-DLN predictions and reconcile based on confidence and spatial proximity.
        - **Rule-based Reconciliation**: Implement specific rules to filter homr's FPs that OMR-DLN correctly rejected, or use OMR-DLN's high-precision detections to confirm homr's barlines.
- [ ] Write a small experiment plan for these selected ideas (what to change, which scripts, how to evaluate).

### Explicit Notes for Future Work:
- Future work should treat `homr` as the “recall anchor”. Any new model or heuristic must **not** compromise 100% recall.
- External models like OMR-DLN should primarily be used as precision/FP filters, or as a source of high-confidence predictions that complement `homr`.
- We will NOT create new annotated datasets or do heavy retraining in the immediate next sessions. Focus remains on evaluating existing pretrained models and refining heuristic-based filtering.
