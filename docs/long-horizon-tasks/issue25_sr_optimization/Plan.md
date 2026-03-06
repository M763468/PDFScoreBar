# Task Plan: Issue #25 - SR Optimization & Verification

## Objective
Identify SR (Super Resolution) bottlenecks, optimize resource usage, and verify the necessity of SR.

## Context & Constraints
- **Device**: RTX 4060 (8GB VRAM).
- **Environment**: WSL2.
- **Reference**: Issue #70 (PR #71) optimizations.

## Milestones

### Milestone 0: Initialization & Baseline Review [COMPLETE]
- [x] Task directory and tracking files initialized.
- [x] Review performance data from Issue #70.

### Milestone 1: Investigation & Resource Profiling [COMPLETE]
- [x] Profile VRAM and Swap during pipeline execution.
- [x] Analyze data transfer overhead and model loading.
- [x] Investigate Shared Memory as a potential optimization (Found 64MB constraint, created Issue #73).

### Milestone 2: Accuracy & Performance Comparison [COMPLETE]
- [x] Compare accuracy on Shostakovich subset.
- [x] Run full pipeline evaluation *without* SR on multi-score subset (7 pages).
- [x] Analyze processing time difference and confirm Precision 100%.

### Milestone 3: Decision & Optimization [COMPLETE]
- [x] Present findings and a strategy for SR: **Bypass SR by default with ink-based recentering.**
- [x] Implement Persistent SR Model (as an alternative for when SR is enabled).
- [x] Implement `enable_sr` and `crop_recenter_on_bbox_ink` in the main pipeline.

## Verification & Testing
- Baseline comparison reports.
- Profiling logs (e.g., `nvidia-smi` output, custom logs).
- Regression tests after any implementation changes.
