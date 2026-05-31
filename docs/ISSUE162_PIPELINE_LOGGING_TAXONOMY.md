# Issue 162 Pipeline Logging Taxonomy

This document defines the default logging contract for full-pipeline and Stage E
runs. The goal is to keep default logs bounded and reviewable while preserving
diagnostic evidence under `logs/` when explicitly requested.

## Categories

| Category | Default console output | Artifact capture | Diagnostic enablement | Current examples |
| --- | --- | --- | --- | --- |
| Acceptance-critical summary | Yes | Yes | Always on | Stage E detector eval output, `evaluation_contract.json`, `stage_e_runtime_summary.json`, `pipeline_stdout_stderr.summary.json` |
| Operational progress | Yes, bounded summaries plus live tqdm-style progress | Yes | Full step chatter via `--pipeline-diagnostic-logs` or `PDFSCORE_STAGE_E_DIAGNOSTIC_LOGS=1` | Stage E start/end lines, image copy count, runtime/resource summary paths, pipeline phase summary, live `tqdm` progress |
| Diagnostic per-item detail | No | Yes | `pipeline.log`; include in captured stdout/stderr with `--pipeline-diagnostic-logs` or `PDFSCORE_STAGE_E_DIAGNOSTIC_LOGS=1` | probe scale-aware parameter lines, MMR per-hit `[FOUND]` / `[RESCUE]` messages |
| External-tool raw output | No by default, except warnings/errors | Yes, in raw stdout/stderr artifacts | `pipeline_stdout_stderr.raw.log`; captured stdout/stderr can be made verbose with `--pipeline-diagnostic-logs` or `PDFSCORE_STAGE_E_DIAGNOSTIC_LOGS=1` | HOMR eprint/info output, Real-ESRGAN initialization/inference lines, OMR-DLN subprocess output |
| Warning/error | Yes | Yes | Always on | missing component warnings, failed image reads, Real-ESRGAN import/init/inference failures, subprocess failures |

## Stage E Default Policy

`tools/issue120/run_stage_e_full_pipeline.py` uses `default_quiet` logging unless
diagnostic verbosity is requested.

- Pipeline stream handler level: `WARNING`
- Progress bars: mirrored to the live console from the raw captured stream
- Captured stream artifact: `logs/issue120_e2e_recovery/stage_e_full_pipeline/pipeline_stdout_stderr.log`
- Raw captured stream artifact: `logs/issue120_e2e_recovery/stage_e_full_pipeline/pipeline_stdout_stderr.raw.log`
- Captured stream summary: `pipeline_stdout_stderr.summary.json`
- Detailed diagnostic file log: `pipeline.log`

The Stage E runner still records the stdout/stderr artifact and summary under
`logs/`. In default mode, the raw file preserves fd-level external output while
the default `pipeline_stdout_stderr.log` is filtered to warnings/errors and any
unexpected direct stream output rather than routine per-page progress. During
the run, progress-like `tqdm` lines are mirrored from the raw capture back to
the console so a long Stage E run still shows liveness and phase progress.

## Existing Log Source Evaluation

Issue #162 audited the Stage E / full-pipeline log stream after Issue #159 added
stdout/stderr capture. The default stream mixed acceptance summaries, operational
progress, per-page diagnostics, external tool output, progress bars, and warnings.

The following policy is now applied:

| Source | Observed noise / value | Category | Default handling | Diagnostic handling |
| --- | --- | --- | --- | --- |
| Stage E runner logs | Run start/end, config path, capture path, runtime summary path | Operational progress | Kept on console as bounded runner messages | Same |
| Stage E detector eval | Page count, TP/FP/FN, FN attribution, canonical target result | Acceptance-critical summary | Kept in eval command output and `evaluation_contract.json` | Same |
| `src.pipeline.main` logger | Pipeline run path and step-level INFO messages | Operational progress / diagnostic detail | Stream handler is raised to `WARNING` during Stage E default capture | Full INFO stream with `--pipeline-diagnostic-logs` |
| `pipeline.log` file handler | DEBUG+ Python logging from pipeline modules | Diagnostic per-item detail | Always written as a diagnostic artifact; not treated as default console output | Same |
| HOMR fd-level output / `eprint` | Model download progress, per-page inference chatter, HOMR messages | External-tool raw output | Captured first to `pipeline_stdout_stderr.raw.log`, then filtered out of default log unless warning/error-like | Preserved directly in `pipeline_stdout_stderr.log` |
| HOMR repetitive internals | `Dewarping staff`, `Running TrOmr inference`, `Creating bounds for`, cache notices, download percentage lines, per-page symbol/staff counts, TrOMR timing, tuple cleanup chatter, RapidOCR/ORT startup noise | Suppressed low-value external detail | Dropped around in-process HOMR initialization/prediction unless warning/error-like | Restore with `PDFSCORE_HOMR_VERBOSE_INTERNAL_LOGS=1` only when debugging HOMR internals |
| Real-ESRGAN prints | Initialization/inference status and failures | External-tool raw output / warning/error | Routine messages moved to logger INFO; failures remain logger ERROR | INFO/errors available through `pipeline.log` and diagnostic captured stream |
| Real-ESRGAN tile prints | Per-tile stdout lines such as `Tile 1/130` | Suppressed low-value external progress | Dropped at the SR wrapper before raw stdout/stderr capture | Restore with `PDFSCORE_SR_TILE_LOGS=1` only when debugging Real-ESRGAN tiling internals |
| `tqdm` progress bars | Per-page progress lines such as `SR/Preparation: 10%...` | Operational progress | Mirrored live to the console, preserved in raw stdout/stderr, filtered out of default final log | Preserved directly in diagnostic captured stream |
| `src.measure_numbering.mmr` per-hit logs | `[FOUND]` / `[RESCUE]` per-measure evidence | Diagnostic per-item detail | Hidden from default captured stream by `WARNING` stream level; retained in `pipeline.log` | Visible in diagnostic captured stream |
| Warning/error lines | RapidOCR empty detections, missing files, subprocess failures, tracebacks | Warning/error | Kept in default `pipeline_stdout_stderr.log` and counted in summary | Same |

The Stage E validation run used for this issue produced these default-mode
observability numbers after filtering:

| Field | Value |
| --- | ---: |
| Raw stdout/stderr lines | 16,164 |
| Default stdout/stderr lines kept | 6 |
| Raw stdout/stderr size | 395,646 bytes |
| Default stdout/stderr size | 612 bytes |
| Dropped progress-like lines | 809 |
| Dropped other external raw lines | 15,349 |
| Default marker counts | `homr=0`, `real_esrgan=0`, `measure_numbering=0`, `progress_bar=0`, `warning_or_error=6` |

These numbers are observability evidence only. They are not detector acceptance
metrics.

The raw log was also reviewed for repeated low-value external messages. The
largest offenders were:

| Raw pattern | Observed lines | Decision |
| --- | ---: | --- |
| `Tile N/M` | 7,564 | Suppress in the SR wrapper; page-level SR `tqdm` remains visible |
| `Dewarping staff` | 2,556 | Suppress around in-process HOMR prediction |
| `Running TrOmr inference on staff image` | 1,278 | Suppress around in-process HOMR prediction |
| `Creating bounds for ...` | 680 | Suppress around in-process HOMR prediction |
| `Downloaded ... (%)` | 303 | Suppress around in-process HOMR initialization; model download start lines may remain, but percentage spam is not retained |
| `Inference Time Tromr`, `Removing tuplets`, RapidOCR INFO, known ORT fallback chatter | observed in 1-page smoke raw log | Suppress around in-process HOMR prediction; these are not page-level progress or actionable acceptance evidence |

The HOMR internal suppressor keeps warning/error-like lines. Use
`PDFSCORE_HOMR_VERBOSE_INTERNAL_LOGS=1` only when diagnosing HOMR internals.

## Final Stage E Log Artifacts

Default Stage E runs write the following log-related artifacts under
`logs/issue120_e2e_recovery/stage_e_full_pipeline/`.

| Artifact | Format | Purpose | Default content |
| --- | --- | --- | --- |
| `pipeline_stdout_stderr.log` | Plain text | Bounded default captured stream | Created only when warning/error-like fd output exists |
| `pipeline_stdout_stderr.raw.log` | Plain text | Detailed stdout/stderr evidence | Progress bars and direct fd output after removing known low-value repeated external chatter |
| `pipeline_stdout_stderr.summary.json` | JSON object | Machine-readable summary of the bounded default stream | Whether `pipeline_stdout_stderr.log` exists, line count, byte size, marker counts |
| `pipeline.log` | Plain text logging format | Diagnostic Python logger timeline from the in-process pipeline | DEBUG+ pipeline logging, including config, step boundaries, phase summaries, and subprocess wrapper records |
| `stage_e_runtime_summary.json` | JSON object | Runtime, resource, and log policy summary | Pipeline duration, log artifact paths, filter summary, progress mirror summary, resource summary |
| `stage_e_resource_samples.jsonl` | JSON Lines | Periodic resource samples | Process/RSS/rusage/GPU samples |
| `stage_e_resource_samples.summary.json` | JSON object | Resource sample aggregate | Peak memory/CPU/GPU values |
| `eval_detector/evaluation_contract.json` | JSON object | Acceptance-critical detector contract | Expected/evaluated page counts, TP/FP/FN, FN attribution, `target_met` |

In diagnostic mode, `pipeline_stdout_stderr.log` is intentionally verbose and
`pipeline_stdout_stderr.raw.log` is not created by the runner. In that mode,
`stage_e_runtime_summary.json` records `stdout_stderr_raw_log: null`,
`stdout_stderr_low_value_raw_suppression_summary: null`, and
`stdout_stderr_filter_summary: null`.

### `pipeline_stdout_stderr.summary.json`

The summary JSON has this shape. This example is from a 1-page smoke run with
no warning/error output:

```json
{
  "path": "logs/issue120_e2e_recovery/stage_e_full_pipeline/pipeline_stdout_stderr.log",
  "exists": false,
  "size_bytes": 0,
  "line_count": 0,
  "logger_counts": {},
  "marker_counts": {
    "homr": 0,
    "real_esrgan": 0,
    "measure_numbering": 0,
    "progress_bar": 0,
    "warning_or_error": 0
  },
  "summary_path": "logs/issue120_e2e_recovery/stage_e_full_pipeline/pipeline_stdout_stderr.summary.json"
}
```

`marker_counts` are intentionally coarse. They are used to evaluate log
taxonomy behavior, not detector correctness.

When no warning/error-like fd output is present, the runner does not create an
empty `pipeline_stdout_stderr.log`. The summary JSON remains present so tooling
can distinguish "no default log was needed" from "summary was not generated".

### `stage_e_runtime_summary.json` log fields

The `pipeline` object records the log policy and filtering result. This example
uses the same 1-page smoke run as above:

```json
{
  "pipeline": {
    "stdout_stderr_log": "logs/issue120_e2e_recovery/stage_e_full_pipeline/pipeline_stdout_stderr.log",
    "stdout_stderr_raw_log": "logs/issue120_e2e_recovery/stage_e_full_pipeline/pipeline_stdout_stderr.raw.log",
    "stdout_stderr_raw_log_size_bytes": 2056,
    "stdout_stderr_log_size_bytes": 0,
    "stdout_stderr_log_summary": {
      "exists": false,
      "line_count": 0,
      "marker_counts": {
        "homr": 0,
        "real_esrgan": 0,
        "measure_numbering": 0,
        "progress_bar": 0,
        "warning_or_error": 0
      }
    },
    "stdout_stderr_low_value_raw_suppression_summary": {
      "schema_version": "tools.issue120.stage_e_low_value_raw_suppression.v1",
      "path": "logs/issue120_e2e_recovery/stage_e_full_pipeline/pipeline_stdout_stderr.raw.log",
      "preserve_homr_internal": false,
      "preserve_sr_tile_logs": false,
      "input_line_count": 64,
      "output_line_count": 36,
      "suppressed_line_count": 28,
      "sanitized_progress_line_count": 1
    },
    "stdout_stderr_filter_summary": {
      "schema_version": "tools.issue120.stage_e_console_filter.v1",
      "raw_path": "logs/issue120_e2e_recovery/stage_e_full_pipeline/pipeline_stdout_stderr.raw.log",
      "filtered_path": "logs/issue120_e2e_recovery/stage_e_full_pipeline/pipeline_stdout_stderr.log",
      "raw_line_count": 36,
      "kept_line_count": 0,
      "dropped_line_count": 36,
      "dropped_progress_line_count": 23,
      "dropped_external_raw_line_count": 13,
      "filtered_log_written": false
    },
    "stdout_stderr_progress_mirror_summary": {
      "schema_version": "tools.issue120.stage_e_console_progress_mirror.v1",
      "capture_path": "logs/issue120_e2e_recovery/stage_e_full_pipeline/pipeline_stdout_stderr.raw.log",
      "mirror_progress": true,
      "mirrored_progress_line_count": 23,
      "mirrored_warning_or_error_line_count": 0
    },
    "logging_policy": {
      "schema_version": "tools.issue120.stage_e_pipeline_logging_policy.v1",
      "mode": "default_quiet",
      "console_log_level": "WARNING",
      "progress_bars_console_mirrored": true,
      "detail_artifact": "logs/issue120_e2e_recovery/stage_e_full_pipeline/pipeline.log",
      "raw_stdout_stderr_artifact": "logs/issue120_e2e_recovery/stage_e_full_pipeline/pipeline_stdout_stderr.raw.log",
      "diagnostic_enable": "--pipeline-diagnostic-logs or PDFSCORE_STAGE_E_DIAGNOSTIC_LOGS=1"
    }
  }
}
```

The default filtered log should remain small enough to inspect directly. The
default raw log is still detailed evidence, but it is no longer a dump of every
repetitive external print. When debugging a pipeline failure, inspect
`pipeline_stdout_stderr.raw.log` and `pipeline.log` together. When reproducing
external tool behavior line-for-line, enable diagnostic mode.

`pipeline.log` is not the default console log. It is the pipeline's Python
logging timeline, written by the file logger. It is useful for reconstructing
which configured steps ran, which subprocess wrapper commands were launched,
and what phase summaries were emitted. It should not be used as an
acceptance-critical metric source, and it intentionally does not contain every
fd-level print from external tools; those belong to `pipeline_stdout_stderr.raw.log`.

Real-ESRGAN tile-level stdout (`Tile N/M`) is intentionally suppressed before
raw stdout/stderr capture. It produces thousands of lines per Stage E run and
does not identify the current page or a failure condition. Page-level SR
progress remains visible through `tqdm`. To inspect Real-ESRGAN tiling internals
for a focused diagnosis, run with:

```bash
PDFSCORE_SR_TILE_LOGS=1 make run-issue120-stage-e-full
```

HOMR internals such as `Dewarping staff`,
`Running TrOmr inference on staff image`, `Creating bounds for ...`,
download percentage lines, TrOMR timing, tuple cleanup chatter, RapidOCR INFO,
known ORT fallback chatter, and per-page staff/symbol counts are also
suppressed by default for the same reason: they produce many lines without
indicating the current score/page or an actionable state. Page-level
`Homr Inference` progress remains visible. To restore those internals for a
focused HOMR investigation:

```bash
PDFSCORE_HOMR_VERBOSE_INTERNAL_LOGS=1 make run-issue120-stage-e-full
```

Use either form to restore verbose captured output for diagnosis:

```bash
make run-issue120-stage-e-full ISSUE120_STAGE_E_EXTRA_ARGS="--pipeline-diagnostic-logs"
```

```bash
PDFSCORE_STAGE_E_DIAGNOSTIC_LOGS=1 make run-issue120-stage-e-full
```

## Non-Metric Boundary

This taxonomy does not define new acceptance metrics. Detector metrics remain in
the Stage E detector evaluation artifacts, while downstream measure-count status
remains separate in the evaluation contract. Log marker counts such as
`homr`, `real_esrgan`, `measure_numbering`, `progress_bar`, and
`warning_or_error` are observability fields only.
