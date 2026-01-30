# Logs Directory Structure

This directory contains execution logs, experiment results, and debug outputs.
To prevent clutter, all logs must be organized into the following categories.

## Directory Categories

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
- Timestamped root folders (e.g., `20251130T...`) should be moved here if not categorized.

## Naming Convention
- Directories: `snake_case` or `kebab-case`.
- Run Folders: `YYYYMMDD_description` or `YYYYMMDDThhmmss_description`.
- Files: `descriptive_name.log` or `metrics.json`.

## Maintenance
- **Do not commit** large log files to Git.
- Use `.gitignore` to exclude specific log patterns, but keep the directory structure visible if possible (using `.gitkeep`).
