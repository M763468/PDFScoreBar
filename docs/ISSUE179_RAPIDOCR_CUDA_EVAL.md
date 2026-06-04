# Issue #179 RapidOCR CUDA evaluation

This document records the experiment-only design for evaluating RapidOCR CUDA as
an opt-in performance feature. It is not a fallback-warning fix.

## Design

- Keep default Stage E behavior unchanged.
- Use `tools/issue179/run_stage_e_rapidocr_cuda_experiment.py` for comparison
  runs instead of changing the normal Stage E runner.
- The wrapper patches only the two Stage E-relevant RapidOCR construction sites:
  - `src.measure_numbering.mmr.RapidOCR`
  - `homr.title_detection.RapidOCR`
- CUDA mode is enabled only when `PDFSCORE_RAPIDOCR_USE_CUDA=1`.
- CUDA mode passes:
  - `det_use_cuda=True`
  - `cls_use_cuda=True`
  - `rec_use_cuda=True`
- The wrapper writes `rapidocr_provider_summary.json` under the Stage E run root.
- Logs remain under `logs/` and must not be committed.

## One-command comparison

Run the standard subset comparison and package report artifacts:

```bash
tools/issue179/run_stage_e_rapidocr_comparison.sh \
  --pages 10 \
  --repetitions 3 \
  --sample-interval 1.0
```

The command performs these steps:

1. Create a deterministic non-excluded Stage E inventory subset.
2. Run `default` and `PDFSCORE_RAPIDOCR_USE_CUDA=1` modes in alternating order for each repetition.
3. Run subset detector contract evaluation after each run with partial/target-mismatch allowances.
4. Write comparison JSON/Markdown.
5. Package a report bundle under `logs/issue179_rapidocr_cuda/`.

For reporting, attach the generated tarball and, if needed, the top-level
`experiment_<timestamp>.log` file. Raw per-run stdout/stderr logs are intentionally
not copied into the bundle.

Common variants:

```bash
# Faster command-shape check
tools/issue179/run_stage_e_rapidocr_comparison.sh --pages 1 --repetitions 1

# More stable comparison
tools/issue179/run_stage_e_rapidocr_comparison.sh --pages 20 --repetitions 3

# Skip subset contract evaluation if only checking runtime plumbing
tools/issue179/run_stage_e_rapidocr_comparison.sh --pages 10 --repetitions 3 --skip-eval
```

## 1-page smoke

Default:

```bash
docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  -e PDFSCORE_HOMR_VERBOSE_INTERNAL_LOGS=1 \
  pdfscore_pipeline_gpu \
  /bin/sh -lc '
    /opt/venv_pipeline/bin/python tools/issue179/run_stage_e_rapidocr_cuda_experiment.py \
      --config configs/issue120_stage_e_full_pipeline.yaml \
      --output-root logs/issue179_rapidocr_cuda/default_smoke_1page \
      --inventory logs/issue162_log_subset/inventory_1page.json \
      --exclude logs/issue162_log_subset/exclude_empty.json \
      --expected-pages 1 \
      --resource-sample-interval-sec 1.0
  '
```

CUDA opt-in:

```bash
docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  -e PDFSCORE_HOMR_VERBOSE_INTERNAL_LOGS=1 \
  -e PDFSCORE_RAPIDOCR_USE_CUDA=1 \
  pdfscore_pipeline_gpu \
  /bin/sh -lc '
    /opt/venv_pipeline/bin/python tools/issue179/run_stage_e_rapidocr_cuda_experiment.py \
      --config configs/issue120_stage_e_full_pipeline.yaml \
      --output-root logs/issue179_rapidocr_cuda/cuda_smoke_1page \
      --inventory logs/issue162_log_subset/inventory_1page.json \
      --exclude logs/issue162_log_subset/exclude_empty.json \
      --expected-pages 1 \
      --resource-sample-interval-sec 1.0
  '
```

Inspect provider summaries:

```bash
cat logs/issue179_rapidocr_cuda/default_smoke_1page/stage_e_full_pipeline/rapidocr_provider_summary.json
cat logs/issue179_rapidocr_cuda/cuda_smoke_1page/stage_e_full_pipeline/rapidocr_provider_summary.json
```

## Multi-page subset

Create a deterministic 10-page subset from the canonical Stage E inventory:

```bash
PYTHONPATH=. python3 tools/issue179/make_stage_e_inventory_subset.py \
  --inventory logs/issue36_prep/20260208_bench_inventory.json \
  --exclude logs/issue36_prep/excluded_pages_for_gt_prep.json \
  --count 10 \
  --output-inventory logs/issue179_rapidocr_cuda/subsets/inventory_10page.json \
  --output-exclude logs/issue179_rapidocr_cuda/subsets/exclude_10page.json \
  --summary-out logs/issue179_rapidocr_cuda/subsets/summary_10page.json
```

Run 3 repetitions per mode:

```bash
for i in 1 2 3; do
  docker run --rm --gpus all \
    -v "$PWD":/workspace \
    -w /workspace \
    -e PYTHONPATH=/workspace \
    pdfscore_pipeline_gpu \
    /bin/sh -lc "
      /opt/venv_pipeline/bin/python tools/issue179/run_stage_e_rapidocr_cuda_experiment.py \
        --config configs/issue120_stage_e_full_pipeline.yaml \
        --output-root logs/issue179_rapidocr_cuda/default_10page_run${i} \
        --inventory logs/issue179_rapidocr_cuda/subsets/inventory_10page.json \
        --exclude logs/issue179_rapidocr_cuda/subsets/exclude_10page.json \
        --expected-pages 10 \
        --resource-sample-interval-sec 1.0
    "

  docker run --rm --gpus all \
    -v "$PWD":/workspace \
    -w /workspace \
    -e PYTHONPATH=/workspace \
    -e PDFSCORE_RAPIDOCR_USE_CUDA=1 \
    pdfscore_pipeline_gpu \
    /bin/sh -lc "
      /opt/venv_pipeline/bin/python tools/issue179/run_stage_e_rapidocr_cuda_experiment.py \
        --config configs/issue120_stage_e_full_pipeline.yaml \
        --output-root logs/issue179_rapidocr_cuda/cuda_10page_run${i} \
        --inventory logs/issue179_rapidocr_cuda/subsets/inventory_10page.json \
        --exclude logs/issue179_rapidocr_cuda/subsets/exclude_10page.json \
        --expected-pages 10 \
        --resource-sample-interval-sec 1.0
    "
done
```

Summarize:

```bash
PYTHONPATH=. python3 tools/issue179/summarize_stage_e_rapidocr_runs.py \
  --run default_10page_run1:logs/issue179_rapidocr_cuda/default_10page_run1 \
  --run default_10page_run2:logs/issue179_rapidocr_cuda/default_10page_run2 \
  --run default_10page_run3:logs/issue179_rapidocr_cuda/default_10page_run3 \
  --run cuda_10page_run1:logs/issue179_rapidocr_cuda/cuda_10page_run1 \
  --run cuda_10page_run2:logs/issue179_rapidocr_cuda/cuda_10page_run2 \
  --run cuda_10page_run3:logs/issue179_rapidocr_cuda/cuda_10page_run3 \
  --output-json logs/issue179_rapidocr_cuda/comparison_10page.json \
  --output-md logs/issue179_rapidocr_cuda/comparison_10page.md
```

## Full Stage E contract check

Only run this if subset results justify an opt-in implementation.

```bash
docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  -e PDFSCORE_RAPIDOCR_USE_CUDA=1 \
  pdfscore_pipeline_gpu \
  /bin/sh -lc '
    /opt/venv_pipeline/bin/python tools/issue179/run_stage_e_rapidocr_cuda_experiment.py \
      --config configs/issue120_stage_e_full_pipeline.yaml \
      --output-root logs/issue179_rapidocr_cuda/cuda_full \
      --resource-sample-interval-sec 5.0
  '

make eval-issue120-stage-e-full \
  ISSUE120_STAGE_E_OUTPUT=logs/issue179_rapidocr_cuda/cuda_full
```

## Decision rule

Proceed to a production opt-in implementation only if:

- CUDA runs consistently improve runtime beyond run-to-run noise.
- GPU memory and utilization remain acceptable for full Stage E.
- `rapidocr_provider_summary.json` proves the CUDA provider was actually used.
- Stage E detector contract remains preserved before merge.

Do not proceed if the observed difference is noise-level, if provider summary does
not show CUDA sessions, or if GPU memory pressure increases without a clear
runtime benefit.
