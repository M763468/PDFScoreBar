# Regression Test Workflow

> [!NOTE]
> **Status (Mar 2026)**: This workflow remains active. The `make test` target is the preferred way to run unit tests.

## Purpose
- Standardize pre-commit / pre-PR verification so behavior regressions are caught consistently.
- Keep real-data smoke and parity checks reproducible across sessions.

## Prerequisites
- Read `docs/ENVIRONMENTS.md` and run commands in the correct environment.
- For pipeline real-data checks, use `sr_eval_gpu` container.

## Mandatory Checks Before Commit/PR
1. Format
```bash
make format
```
2. Lint
```bash
make lint
```
3. Unit tests (minimum)
```bash
make test
```

## Test Placement Policy
- `tests/`: actively maintained tests for current code paths, expected to run in normal dev environments.
- `tests_legacy/`: archive area for historical tests temporarily excluded from the default pre-PR set.
- New tests must be added to `tests/` (or integration/verification scripts under `tools/verification/`), not to `tests_legacy/`.
- `tests_legacy/` items may be reworked and moved back into `tests/` when related issues are addressed.

## When Adding Tests
- Prefer deterministic unit tests first (`tests/`).
- If the change touches real-data behavior, add/update one reproducible parity or smoke command under `tools/verification/`.
- In PR comments, report both:
  - lightweight test result (`tests/` target),
  - real-data verification result (if applicable).
- If legacy tests are moved out, record the reason and expected return condition in `tests_legacy/README.md`.

## Real-Data Smoke (Detection Path)
Use the already organized smoke assets under `logs/issue23_smoke/` and the newly verified Shostakovich baseline documentation for high-DPI scaling checks.

### 1. High-DPI Detection Recall (Critical Fix for Barlines)
If modifying `predictor.py` or tuning geometric/CNN constraints in the detection pipeline, **you must verify that full-page barlines are not rejected at high resolutions**.
- Follow the instructions in `docs/REPRODUCE_100_RECALL.md` to run the baseline evaluation.
- Ensure the total output explicitly matches or exceeds the **351 GT count** for the Shostakovich test set.

### 2. Issue 23 General Smoke Test

1. Run integrated pipeline (inside `sr_eval_gpu`)
```bash
docker exec sr_eval_gpu bash -lc "cd /workspace && \
  /opt/venv_sr/bin/python -m src.pipeline.main \
  --config logs/issue23_smoke/config_issue23_smoke_images.yaml"
```
2. Confirm outputs exist
- `logs/full_pipeline_runs/<run_id>/intermediate/probe_scan/*/pipeline2_no_peak_candidates.json`
- `logs/full_pipeline_runs/<run_id>/intermediate/probe_scan/*/pipeline2_no_peak_filtered_cnn.json`

## Real-Data Parity Check (src vs tools)
Run parity check with the canonical script:

```bash
docker exec sr_eval_gpu bash -lc "cd /workspace && \
  /opt/venv_sr/bin/python tools/verification/run_probe_detector_parity_check.py \
  --image /workspace/data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png \
  --staff-mask /workspace/logs/issue23_smoke/runs/hybrid_issue23_smoke_images_20260207/sr/batch/page_001/page_001_proxy_debug_3_staff.png \
  --existing-boxes /workspace/logs/issue23_smoke/runs/hybrid_issue23_smoke_images_20260207/hybrid_results/page_001_hybrid.json \
  --output /workspace/logs/issue34_smoke/issue34_parity_latest/parity_summary.json"
```

Check:
- `logs/issue34_smoke/issue34_parity_latest/parity_summary.json`
- all cases have `exact_match: true`

Reference example (2026-02-08, `issue34_parity_latest`):
- `baseline_staffmask_dense`: `src_count=7700`, `tools_count=7700`
- `rescue_off_custom_width`: `src_count=2227`, `tools_count=2227`
- `row_stats_mode`: `src_count=440`, `tools_count=440`

## Logging Rules
- Save new verification outputs under `logs/<topic>/<run_id or timestamp>/`.
- Do not scatter logs across multiple top-level locations for one issue.
- If a run location changes, add a short `README.md` in that log folder with canonical paths.

## Report Template (PR Comment)
- Environment used (container/venv)
- Commands executed
- Result summary (pass/fail)
- Real-data parity result (`exact_match` and counts)
- Log location
