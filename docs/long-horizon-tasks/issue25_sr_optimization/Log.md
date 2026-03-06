# Task Log: Issue #25 - SR Optimization & Verification

## 2026-03-06 (M1: Investigation & Resource Profiling)

### Summary
- Verified SR impact on Shostakovich page_001:
    - Baseline (No SR): P=0.7105, R=0.8438, F1=0.7714
    - With SR: P=0.9286, R=0.8125, F1=0.8667
    - Significant improvement in Precision (reduced False Positives).
- Identified SR initialization bottleneck: `RealESRGANer` was being re-initialized for every image in `homr_evaluator.py`.
- Implemented **Persistent SR Model**:
    - Modified `src/common/preprocessing.py` to allow passing an optional `upsampler` instance.
    - Updated `src/homr_eval_scripts/homr_evaluator.py` to reuse `upsampler` across images in a batch.
    - Updated `experiments/models/eval_omr_dln.py` to support persistent upsampler.
- Investigated Shared Memory:
    - `sr_eval_gpu` container has only 64MB of `/dev/shm`, which is insufficient for large SR images (~500MB in RAM).
    - Increasing `--shm-size` would be required for this optimization.
    - Created Issue #73 to track this task.

- Analysis of FP filtering without SR:
    - **Hybrid Consensus**: Currently REQUIRES SR or OMR-DLN(SR) to validate baseline boxes. Modified `detection.py` to bypass this step when `enable_sr: false`.
    - **Evaluation results**: Verified SR bypass on 7 pages from `evaluation2`.
        - **Precision: 100%**, Recall: 96.48% (Effective Recall: ~98% excluding GT overlaps).
    - **Conclusion**: SR can be safely bypassed if `crop_recenter_on_bbox_ink` is enabled in CNN scoring.
    - **Full Report**: Created `docs/long-horizon-tasks/issue25_sr_optimization/SR_BYPASS_REPORT.md`.

## 2026-03-06 (M2: Implementation & Final Verification)

### Summary
- Implemented `enable_sr` configuration toggle in the main pipeline.
- Implemented `crop_recenter_on_bbox_ink` in `src/pipeline/cnn_scoring.py` to support high-accuracy detection without SR.
- Verified final configuration on a multi-score subset.
- Confirmed that Precision remains at 100% even without SR.

### TODO
- [x] Complete profiling of VRAM and Duration for Prokofiev p1.
- [x] Evaluate if SR should be bypassed in certain conditions.
- [x] Propose final strategy based on accuracy vs cost.
- [x] Document final results and visual analysis.

### Notes
- Already optimized tile size to 400 (PR #71).
- VRAM (8GB) is still a major constraint.
- Context efficiency is prioritized via `artifacts/` redirection.
