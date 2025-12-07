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

### 1. GUI Helper Tool (Active)
**Status**: Initial version created (`tools/gui_helper`).
**Objective**: Expand the tool to support efficient FP cleanup for the entire dataset.
**Next Steps**:
- Add support for browsing multiple pages (currently hardcoded to `page_3`).
- Integrate `manual_ignore.json` output into the evaluation pipeline to automatically exclude marked FPs.
- Add keyboard shortcuts for faster review.

### 2. Model Retraining Investigation
**Objective**: Analyze why the SegNet model fragments barlines.
**Action**: Check training data quality or experiment with varying the probability threshold (currently fixed).

### 3. External Model Evaluation
**Objective**: Benchmark other OMR libraries (e.g., commercially available APIs or newer research models) on `page_3`.