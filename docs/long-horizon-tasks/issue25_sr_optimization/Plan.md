# Task Plan: Issue #25 - SR Optimization & Verification

## Objective
Identify SR (Super Resolution) bottlenecks, optimize resource usage, and verify the necessity of SR.

## Context & Constraints
- **Device**: RTX 4060 (8GB VRAM).
- **Environment**: WSL2.
- **Reference**: Issue #70 (PR #71) optimizations.

## Milestones

### Milestone 0: Initialization & Baseline Review
- [ ] Task directory and tracking files initialized. (Current)
- [ ] Review performance data from Issue #70 (Docs: `docs/long-horizon-tasks/ISSUE-070/`).

### Milestone 1: Investigation & Resource Profiling
- [ ] Profile VRAM and Swap during pipeline execution with current SR settings. Use `make` targets if available and redirect output to `artifacts/profiling_log.txt`.
- [ ] Analyze data transfer overhead between processes (e.g., image loading/saving).
- [ ] Investigate Shared Memory as a potential optimization.

### Milestone 2: Accuracy & Performance Comparison
- [ ] Run full pipeline evaluation *without* SR (simple scaling). Redirect output to `artifacts/eval_no_sr.txt`.
- [ ] Compare results with the SR baseline (Precision/Recall/F1). Redirect comparison analysis to `artifacts/accuracy_comparison.txt`.
- [ ] Analyze processing time difference.

### Milestone 3: Decision & Optimization
- [ ] Present findings and a strategy for SR (Keep/Optimize/Remove).
- [ ] If optimized, implement Shared Memory data transfer.
- [ ] Final verification of the chosen strategy.

## Verification & Testing
- Baseline comparison reports.
- Profiling logs (e.g., `nvidia-smi` output, custom logs).
- Regression tests after any implementation changes.
