# Logs Directory Structure

This directory contains execution logs, experiment results, and debug outputs.

## Placement precedence

Use one canonical location for each generated run or retained artifact. Do not duplicate the same
evidence under both an Issue root and a category root.

1. **Issue-scoped work:** when a run/artifact is produced for a specific GitHub Issue, keep it under
   one Issue root:

   ```text
   logs/issue<N>/<category-or-purpose>/<run-or-artifact>/...
   ```

   Examples:

   ```text
   logs/issue354/manual_gui_smoke/production_page001_20260921T144416Z/
   logs/issue355/analysis/dpi_ab/
   logs/issue294/benchmarks/maintained_homr/
   ```

   Category names such as `analysis`, `experiments`, `benchmarks`, or `eval` may be used
   **inside** the Issue root when useful. Do not create multiple sibling roots such as
   `logs/issue354_smoke` and `logs/issue354_retry`.

2. **Repository-wide / non-Issue work:** when evidence is not owned by a specific Issue, use the
   category roots below.

Existing historical paths are preserved for provenance. Do not move or rewrite old evidence solely
to match the current convention; migrate only when there is an explicit reason and references can be
updated safely.

## Directory Categories for non-Issue work

### 1. Evaluations (`*_eval/`)
Major evaluation pipelines.
- `homr_eval/`: HOMR evaluator outputs.
- `oemer_eval/`: OEMER evaluator outputs.
- `sr_eval/`: Super-resolution evaluation outputs.

### 2. Experiments (`experiments/`)
Specific experimental runs and model training.
- `cnn_barline_classification/`: CNN training logs.
- `hybrid_pipeline_bench/`: Hybrid pipeline benchmarks.
- `fp_reduction/`: False positive reduction experiments.

### 3. Analysis & Debugging (`analysis/`)
Ad-hoc investigations, failure analysis, and debug outputs.
- `night_run/`: Automated nightly regression tests.
- `probe_analysis/`: Investigation of probe scan failures.
- `gt_validation/`: Ground truth consistency checks.

### 4. System & Benchmarks (`system/`)
Performance benchmarks, system optimization logs, and environment tests.
- `benchmarks/`: Timing and resource usage logs.
- `optimization/`: Tuning logs (e.g., `opt_final.log`).

### 5. Archive (`archive/`)
Legacy logs or one-off runs that are no longer active but preserved for reference.
- Timestamped root folders (e.g., `20251130T...`) should be moved here only when their provenance
  and references do not depend on the existing path.

## Naming Convention
- Directories: `snake_case` or `kebab-case`.
- Run Folders: `YYYYMMDD_description` or `YYYYMMDDThhmmss_description`.
- Files: `descriptive_name.log` or `metrics.json`.

## Maintenance
- **Do not commit** large log files to Git.
- Use `.gitignore` to exclude specific log patterns, but keep the directory structure visible if possible (using `.gitkeep`).

## Lost & Found
- **`logs/hybrid_generalization/`**:
  - Contains extensive evaluation results on the `evaluation2` dataset.
  - The directory was missing as of Jan 2026, but traces were found in `docs/SESSION_LOG.md` (commit `e56e9fb`).
  - **Reproduction Command**:
    ```bash
    # Runs the hybrid pipeline on all evaluation2 images
    python3 tools/run_eval2_batch.py
    ```
  - Output will be generated at `logs/hybrid_pipeline_bench/` (subdirectory starting with `eval2_`).
