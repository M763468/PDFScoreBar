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

### 1. GUI Helper Tool
**Objective**: Create a visualizer that loads `homr_evaluator` outputs (CSVs) and highlights "Warning" candidates (e.g., those flagged by H2-H5 logics).
**Goal**: Allow valid TPs to be kept while manually cleaning FPs efficiently.

### 2. Model Retraining Investigation
**Objective**: Analyze why the SegNet model fragments barlines.
**Action**: Check training data quality or experiment with varying the probability threshold (currently fixed).

### 3. External Model Evaluation
**Objective**: Benchmark other OMR libraries (e.g., commercially available APIs or newer research models) on `page_3`.