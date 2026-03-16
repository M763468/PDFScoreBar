# Session Log (Combined Integration Track)

**NOTE**: This log combines the Full Pipeline Workflow planning and the Pipeline Optimization tracks.
Authoritative records for specific subsystems are in:
- `docs/DEVLOG_MEASURE_NUMBERING.md` (numbering/MMR)
- `docs/DEVLOG_CNN_TRAINING.md` (CNN training)
- `docs/performance_comparison.md` (benchmarks)

---

## Phase 1: Pipeline Analysis & Performance Benchmarking (2026-01-15)

### Objective
Establish a performance baseline for the current hybrid pipeline and identify major bottlenecks.

### Initial Performance Measurements (Baseline - Page 10)
| Stage | Duration | Notes |
| :--- | :--- | :--- |
| **Step 1: Homr Baseline** | **~2 min** | Baseline detection without SR. |
| **Step 2: Homr SR (x4)** | **~7 min** | **Primary Bottleneck**. Segnet (~80s) and TrOmr (~180s) scale poorly. |
| **Step 3: OMR-DLN SR** | **~1.5 min** | Redundant SR calculation. |
| **Total** | **~11 min** | |

---

## Phase 2: Implementation of Proxy Inference Optimization (2026-01-17)

### Objective
Eliminate the performance bottleneck in Step 2 (Homr SR) using "Proxy Inference".

### Changes
- **Modified**: `src/homr_eval_scripts/homr_evaluator.py`
    - Creates a temporary downscaled proxy image (~3.5MP) for inference.
    - Maps detected coordinates back to the high-resolution system.
- **Speedup**: Segnet ~66x improvement, TrOmr ~6.5x improvement. Step 2 Homr processing time reduced to **< 40s** (excluding SR generation).

---

## Full Pipeline Workflow Planning (2026-01-17)

### Objective
Define the end-to-end pipeline from PDF/Image input to measure-numbered output.

### Achievements
- `tools/run_full_pipeline.py`: Created a config-driven orchestrator.
- `configs/full_pipeline_template.yaml`: Defined the standard configuration structure.
- **Workflow Steps identified**: Ingest -> Barline Detection -> User Correction -> Measure Numbering -> MMR Detection -> Final Export.

---

## Phase 3: Cache Cleanup & Dependency Repair (2026-01-17)

### Changes
- **Fix**: Added `torch.cuda.empty_cache()` after SR to prevent 75s Segnet slowdowns.
- **Infrastructure**: Restored `external/omr_dln` and model weights.
- **Verification**: Confirmed end-to-end timing: **Page 10 ~259s (4.3 min)**.

---

## Detection Integration in Orchestrator (2026-01-20)

### Changes
- Updated `tools/run_full_pipeline.py` to invoke the full hybrid detection sequence:
    1. `run_hybrid_pipeline.sh` (Docker)
    2. `run_eval_experiment.py` (Host - Probe Scan)
    3. `score_candidates_batch.py` (Host - CNN Scoring)
- Verified Host/Docker path translation via `data/workbench` mount.

---

## Phase 4: SR Cache Reuse Validation (2026-01-23)

### Objective
Quantify impact of reusing pre-computed SR images.
- **Result (Page 10)**: Saved **54s** (~20% total time). Caching is confirmed as a critical optimization for large scores.

---

## Phase 5: Advanced Optimization & SR Tuning (2026-01-24)

### Objective
Optimize Real-ESRGAN tiling and finalize pipeline optimizations.

### Real-ESRGAN Tiling Benchmark (Page 10, RTX 4060 8GB)
| Setting (Tiling) | Total Time (Step 2) | Notes |
| :--- | :--- | :--- |
| **Auto (512)** | **221s** | Optimal balance. |
| **Tile 512** | 256s | Matches auto performance. |
| **Tile 1024** | 577s | Significantly slower (VRAM overhead). |

### Key Findings
- `tile=512` is the sweet spot for 8GB VRAM hardware.
- The pipeline's remaining bottleneck is "Cold Start" (initialization), which must be addressed by Batch Processing Architecture.