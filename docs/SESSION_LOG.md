# Session Log

Last migrated: 2026-01-14

**Note**: The contents of this log have been migrated to `docs/DEVLOG_CNN_TRAINING.md` as part of the `experiment/cnn_classifier` branch closure.
Refer to that file for the complete history of the CNN training experiments.

New session entries should be appended below.

---

## Phase 1: Pipeline Analysis & Performance Benchmarking (2026-01-15)

### Objective
Establish a performance baseline for the current hybrid pipeline and identify major bottlenecks.

### Baseline Environment
- **Machine**: GeForce 4060 (8GB VRAM)
- **Container**: `sr_eval_gpu` (Docker)
- **Pipeline Script**: `tools/run_hybrid_pipeline.sh`
- **SR Model**: Real-ESRGAN x4 (`RealESRGAN_x4plus.pth`)

### Benchmarking Targets
- Page 10: `data/training/images/page_10.png`
- Page 15: `data/training/images/page_15.png`

### Initial Performance Measurements (Baseline)

| Page | Total Time | Homr Baseline | Homr SR | OMR-DLN SR | Hybrid Gen |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Page 10 | TBD | TBD | TBD | TBD | TBD |
| Page 15 | TBD | TBD | TBD | TBD | TBD |

### Interrupted Benchmark Analysis (2026-01-15)
- **Status**: The benchmark run for `page_10` was interrupted.
- **Progress**:
    - Step 1 (Homr Baseline): Completed.
    - Step 2 (Homr SR): Started but stalled/interrupted during inference.
    - Step 3 (OMR-DLN SR): Not started.
    - Step 4 (Hybrid Gen): Not started.
- **Log Analysis**: `logs/page_10_bench.log` shows the process hanging after "Running TrOmr inference on staff image 0" during the SR step. This confirms the SR/Inference stage is the major bottleneck or stability risk.

### Session Summary (2026-01-15) - Pipeline Optimization Phase 1
- **Achievements**:
    - Merged `experiment/cnn_classifier` into `main`.
    - Created `feature/pipeline_optimization` branch.
    - Updated `NEXT_SESSION_NOTES.md` with a 5-phase optimization plan.
    - Modified `tools/run_hybrid_pipeline.sh` to include automatic stage timing and summary reporting.
    - Identified Step 2 (Homr SR / Real-ESRGAN x4) as the primary bottleneck and a potential stability risk (hang during TrOmr inference).
- **Current Status**:
    - Initial benchmark for `page_10` stalled and was manually interrupted.
    - Cleanup attempt for `logs/hybrid_generalization/page_10_bench/` failed due to root-owned files from the Docker container.
- **Next Steps**:
    - **Cleanup**: (User Action) Remove `logs/hybrid_generalization/page_10_bench/` using `sudo` if possible.
    - **Benchmark**: Execute the timed pipeline with a fresh ID (e.g., `page_10_bench_v2`) to capture complete performance metrics.
    - **Optimization**: Focus on reducing SR overhead, possibly by caching SR results or optimizing inference (FP16/TensorRT).

### Next Session Commands (Reference)
```bash
# 1. Cleanup root-owned files (Use sudo if necessary)
# sudo rm -rf logs/hybrid_generalization/page_10_bench/

# 2. Re-run timed benchmark with fresh ID
bash tools/run_hybrid_pipeline.sh --image data/training/images/page_10.png --run-id page_10_bench_v2

# 3. Monitor log (if backgrounded)
# tail -f logs/page_10_bench_v2.log
```
ユーザーコメント：ファイルの削除は行いました。古い物がなくなったのだから、bench_v2としなくてもよいのでは？             │
また、日付などをファイル名に入れておかないとどの段階でのbenchか後からわからなくなる可能性が高いです。
  logs/hybrid_pipeline_benchなどのべつのディレクトリに、範囲と日付（時間）が分かる形で保存する方がよいと思います。     

---