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

## Page 10 Qualitative Generalization Check (2025-12-15)

**Type**: Qualitative only (no GT evaluation by design)

### Results
- **Input**: 322 hybrid detections
- **Rows found**: 13 (clustering successful)
- **Noise points**: 0 (all barlines assigned)
- **Staff space**: 11.85px (vs 8.70px on page_3)

### Filter Behavior
All configurations kept **100% of barlines** (322/322):
- Absolute 5px: 100% kept
- Absolute 7px: 100% kept
- Ratio 0.3 (3.6px): 100% kept
- Ratio 0.4 (4.7px): 100% kept

### Interpretation
- **Positive**: Hybrid pipeline produces very clean detections on Page 10
- **Positive**: Row clustering generalizes well (13 rows found)
- **Positive**: Staff space estimation adapts correctly (11.85px vs 8.70px)
- **Note**: 100% pass rate suggests either:
  1. Excellent detection quality (no FPs), OR
  2. Tolerances may be too loose for this page

### Artifacts
- Results: `logs/phase3_staff_consistency/20251215_page10_qualitative/`
- Debug overlays: `debug_ratio_0.3.jpg`, `debug_ratio_0.4.jpg`
- Report: `qualitative_report.md`

### Known Issue: Page 10 Visualization
- **Problem**: Debug overlays show scale mismatch between barline detections and source image
- **Difference**: Page 3 overlays display correctly, Page 10 does not
- **Likely cause**: Inconsistent image/coordinate handling in visualization path
- **Status**: Known issue, deferred to next session (no fix attempted)
- **Impact**: Does not affect filter logic or statistics, only visual validation

## Page 15 Execution Plan

**Manual Execution by User** (not AI agent):
- Page 15 hybrid detection will be executed manually in separate terminal
- AI agent is NOT responsible for running Page 15
- Next session will only:
  1. Verify existing outputs exist
  2. Apply Phase 3 row-based filter
  3. Document results

**Command for Manual Execution**:
```bash
# Run from project root
./tools/run_hybrid_pipeline.sh \
    --image data/training/images/page_15.png \
    --run-id page_15_hybrid_test
```

**Expected Output Location**:
- `logs/hybrid_generalization/page_15_hybrid_test/omr_sr/predictions.json`

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

### Immediate (small task remain in Phase 3)
1.  Fix issue in **Page 10 Qualitative Generalization Check**
2.  Do remained task of **Page 15 Execution Plan**

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
5. **Apply filter to Page 10**
   - Test ratio-based tolerance on different musical content
   - Validate staff_space estimation robustness
   - Compare results with page_3

6. **Page 15 evaluation** (when OMR complete)
   - Full pipeline validation
   - Cross-page consistency check

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
