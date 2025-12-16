# Next Session Notes

**Last Updated**: 2025-12-15  
**Current Phase**: Phase 3 Complete, Ready for Phase 4

## Current Status

### Phase 3: Geometric FP Reduction ✅ **COMPLETE**

**Best Results Achieved** (page_3, hybrid pipeline):
- **Input**: TP=152, FP=8, FN=0 (Precision=95.0%)
- **After Filter**: TP=152, FP=2, FN=0 (Precision=**98.7%**, Recall=**100%**)
- **Configuration**: Tolerance 5-7px (absolute) or Ratio 0.3-0.4 × staff_space

**Method**: Row-based consistency filter
- Manual Y-distance clustering (groups barlines into rows)
- Per-row median top/bottom reference
- Reject barlines deviating beyond tolerance

**Key Learnings**:
1. Ratio-based tolerance (relative to staff spacing) outperforms absolute pixel values
2. Hybrid pipeline (SR + homr) starts with 73% fewer FPs than baseline (8 vs 30)
3. Geometric filter alone achieves 98.7% precision with perfect recall
4. Remaining 2 FPs require context-based analysis

## Page 10 Qualitative Generalization Check (2025-12-16)

**Status**: ✅ **COMPLETE**

### Summary
- To resolve the poor detection quality found previously, the Page 10 analysis was re-run to correctly mirror the successful Page 3 methodology.
- Existing intermediate results from the original `page_10_hybrid_test` run (`baseline`, `sr`, `omr_sr`) were used to generate the correct `hybrid_predictions.json` file, ensuring the full consensus logic was applied.
- The `tolerance_sweep.py` script (used for Page 3) was temporarily modified to support qualitative-only analysis (no GT) and was run on the corrected hybrid predictions.

### Findings
- The resulting debug overlay (`debug_qualitative_ratio_0.3.jpg`) shows a significant improvement in detection quality. The number of raw detections is much lower (128 vs. 322), and obvious false positives have been eliminated by the hybrid consensus step.
- **New Finding (FN)**: However, the corrected analysis reveals a high number of False Negatives (FN). Many true barlines are not being detected. This is particularly noticeable for barlines at the very end of a staff system, which seem to be universally missed.
- This confirms the hypothesis that the previous poor quality was due to skipping the hybrid filtering step and reveals a new recall problem to be addressed.

### Key Artifacts (NEW)
- **Corrected Output Directory**: `logs/phase3_staff_consistency/20251216_page10_hybrid_filter_FIXED/`
- **Corrected Debug Overlay**: `debug_qualitative_ratio_0.3.jpg` in the directory above.
- **Qualitative Summary**: `qualitative_summary.json` in the directory above.
- **Note**: The `tolerance_sweep.py` and `generate_hybrid_results.py` scripts have been reverted to their original state.

## Page 15 Generalization Check (2025-12-16)

**Status**: ✅ **COMPLETE** (Qualitative)

### Summary
- Following the same procedure as the corrected Page 10 analysis, the full hybrid pipeline was applied to Page 15.
- The `generate_hybrid_results.py` script (with temporary modifications) was used to create the correct `hybrid_predictions.json`.
- The `tolerance_sweep.py` script (also temporarily modified) was then run to perform a qualitative analysis.

### Findings
- The hybrid consensus mechanism significantly reduced the number of initial detections (from 154/146/242 down to 90), which successfully eliminated most obvious false positives before the geometric filter was even applied.
- The geometric filter then removed a few more outliers, resulting in a visually clean set of detections.
- **(User Comment)** Similar to Page 10, there appears to be a high number of False Negatives (FN), especially at the end of staff systems. This is a high-priority recall issue, but is **blocked** pending user review and potential creation of new GT data.

### Key Artifacts
- **Output Directory**: `logs/phase3_staff_consistency/20251216_page15_hybrid_filter/`
- **Debug Overlay**: `debug_qualitative_ratio_0.3.jpg` in the directory above.
- **Qualitative Summary**: `qualitative_summary.json` in the directory above.

## What Was Completed

### Phase 1: Baseline Evaluation ✅
- Established homr baseline: TP=152, FP=30, FN=0 on page_3
- Created unified_metric.py (homr-equivalent evaluation with padding)
- Resolved metric definition mismatch (expand_barline_box with min_width=12px)

### Phase 2: Hybrid Pipeline ✅
- Integrated SR (super-resolution) preprocessing
- Achieved 73% FP reduction: 30 → 8 FPs
- Validated on page_3, page_10

### Phase 3: Geometric FP Reduction ✅
- Implemented row-based consistency filter
- Conducted tolerance sweep (absolute + ratio-based)
- **Baseline results**: FP 30→5 (83% reduction, Precision 96.8%)
- **Hybrid results**: FP 8→2 (75% reduction, Precision 98.7%)
- Production-ready configuration identified

## Remaining Work / Next Session Tasks

### High Priority
1.  **Investigate False Negative (FN) Issue**: Both Page 10 and Page 15 analyses show that the hybrid pipeline fails to detect many true barlines, especially at the end of staff systems. This is now the primary issue to resolve. The investigation should start by analyzing the inputs to `generate_hybrid_results.py` to see which model (baseline, sr, or omr) is failing to detect these barlines.
2.  **Investigate Slow Super-Resolution (SR) Performance**: The SR step (`realesrgan`) is unacceptably slow and causes timeouts. Investigate the cause by checking the implementation in `homr_evaluator.py` and `eval_omr_dln.py`, reviewing the official Real-ESRGAN repository for known performance issues or alternative models, and exploring potential optimizations. One potential optimization is to clone the `realesrgan` repository into `external/` and import its classes/models directly rather than using the current method.

#### Slow Super-Resolution (SR) Performance Investigation

**Status**: 🚧 **IN PROGRESS** (Blocked)

**Goal**: Improve the performance of the Real-ESRGAN super-resolution step, which currently causes timeouts when running the full hybrid pipeline.

**Steps Taken**:
- Cloned the official `xinntao/Real-ESRGAN` repository into `external/realesrgan`.
- Created a dedicated Python virtual environment `.venv_realesrgan` and installed `external/realesrgan/requirements.txt` into it using `uv`.
- Modified `src/common/preprocessing.py` to attempt to import and use the `realesrgan` library directly from the locally cloned source code, rather than the pip-installed package. This also defers model downloading and caching to the `RealESRGANer` class.

**Current Blocking Issue**:
- When attempting to test the modified `apply_advanced_sr` function by running `experiments/models/eval_omr_dln.py` within the newly created `.venv_realesrgan` environment, a `ModuleNotFoundError: No module named 'ultralytics'` occurred.
- This indicates that `eval_omr_dln.py` has dependencies (specifically `ultralytics`) that are not present in `.venv_realesrgan`.

**Next Steps (for next session)**:
- Identify all missing dependencies for `eval_omr_dln.py` (likely via its own `requirements.txt` or manual inspection).
- Install these missing dependencies into `.venv_realesrgan`.
- Re-run `eval_omr_dln.py` to test the performance of the local Real-ESRGAN integration and verify it functions correctly without timeouts.
- Analyze any observed performance improvements or new issues.
- **IMPORTANT**: Revert the changes to `src/common/preprocessing.py` after testing, unless decided otherwise.

### Phase 4
3. **Analyze remaining 2 FPs** on page_3 hybrid results
   - Visual inspection of FP patterns
   - Identify distinguishing features vs true barlines
   - Visual inspection of overlays recommended

4. **Implement context-based filters** (if needed)
   - Notehead proximity check
   - Stem attachment analysis
   - Width/aspect ratio filtering
   - Target: FP < 2 while maintaining Recall ≥ 98%

### Generalization Testing
5. **(COMPLETED FOR NOW)** **Apply filter to Page 10**
6. **(COMPLETED FOR NOW)** **Page 15 evaluation**

### Documentation & Deployment
7. **Update analyze_staff_consistency.py**
   - Set ratio-based mode as default (ratio=0.3-0.4)
   - Add command-line arguments for tolerance configuration
   - Include staff_space estimation in output

8. **Create deployment guide**
   - Recommended configuration
   - Performance benchmarks
   - Troubleshooting common issues

## Key Artifacts & Locations

### Scripts
- **Main filter**: `experiments/fp_reduction/analyze_staff_consistency.py`
- **Tolerance sweep**: `experiments/fp_reduction/tolerance_sweep.py`
- **Unified metric**: `experiments/fp_reduction/unified_metric.py`

### Results & Reports
- **Hybrid final summary**: `logs/phase3_staff_consistency/20251215_hybrid_ratio_sweep_page3/hybrid_filter_summary.md`
- **Tolerance sweep**: `logs/phase3_staff_consistency/20251215_tolerance_sweep_page3/`
- **Baseline sweep**: `logs/phase3_staff_consistency/20251214_dbscan_filter_page3/`

### Documentation
- **Development log**: `docs/DEVELOPMENT_LOG.md` (append-only, authoritative history)
- **Project plan**: `temp_next_step_plan.md` (task checklist)
- **This file**: `docs/NEXT_SESSION_NOTES.md` (current status + next steps)

### Data Files
- **Hybrid detections**: `logs/hybrid_results.json` (177 detections, page_3)
- **Baseline detections**: `logs/homr_eval/baseline_for_hybrid/page_3/page_3_detections.json` (222 detections)
- **Ground truth**: `data/evaluation/annotations/page_003/boxes_sorted.json` (152 GT)

### Scripts & Commands

**For Hybrid Detection** (manual execution):
```bash
# Run from project root
./tools/run_hybrid_pipeline.sh \
    --image <path_to_image> \
    --run-id <run_identifier>

# Example for Page 15:
./tools/run_hybrid_pipeline.sh \
    --image data/training/images/page_15.png \
    --run-id page_15_hybrid_test
```

**For Row-Based Consistency Filter**:

*With GT evaluation (quantitative)*:
```bash
# Run inside Docker container
docker exec homr_eval_gpu bash -c "cd /workspace/external/homr && \
  poetry run python /workspace/experiments/fp_reduction/tolerance_sweep.py \
    --json <detections.json> \
    --image <source_image.png> \
    --gt <ground_truth.json> \
    --output <output_directory>"
```

*Without GT (qualitative only)*:
```bash
# Modify page10_qualitative.py paths and run:
docker exec homr_eval_gpu bash -c "cd /workspace/external/homr && \
  poetry run python /workspace/experiments/fp_reduction/page10_qualitative.py"
```

**Key Scripts**:
- Hybrid pipeline: `tools/run_hybrid_pipeline.sh`
- Tolerance sweep: `experiments/fp_reduction/tolerance_sweep.py`
- Qualitative check: `experiments/fp_reduction/page10_qualitative.py`
- Unified metric: `experiments/fp_reduction/unified_metric.py`

## Configuration Reference

### Optimal Settings (Production)

```python
# For hybrid pipeline on page_3
CONFIG = {
    "CLUSTER_MAX_DIST": 25,      # Row clustering threshold
    "MIN_ROW_COUNT": 3,          # Minimum barlines per row
    "USE_RATIO_TOLERANCE": True, # Enable adaptive tolerance
    "TOLERANCE_RATIO": 0.35,     # 0.3-0.4 recommended
    # Fallback absolute tolerances:
    "TOL_TOP_PX": 6,
    "TOL_BOTTOM_PX": 6
}
```

### Performance Benchmarks (page_3)

| Pipeline | Configuration | TP | FP | FN | Precision | Recall |
|----------|---------------|----|----|----|-----------| -------|
| Baseline | No filter | 152 | 30 | 0 | 83.5% | 100% |
| Baseline | Ratio 0.3 | 149 | 5 | 3 | 96.8% | 98.0% |
| **Hybrid** | **Tol 5-7px** | **152** | **2** | **0** | **98.7%** | **100%** |

## Notes for Next Session

- Phase 3 geometric filtering is **production-ready** for hybrid pipeline
- Focus should shift to:
  1. Analyzing remaining 2 FPs (what are they?)
  2. Generalization testing (Page 10, Page 15)
  3. Optional: Context-based filters for final polish
- No heavy OMR reruns needed
- All evaluation uses unified_metric (homr-equivalent)
