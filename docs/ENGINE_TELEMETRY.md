# Engine Structured Telemetry Contract

> **Status: Issue #339 structured telemetry contract layered on Engine Job Contract v1.**
>
> The serialized job/result/error boundary is defined by
> [ENGINE_JOB_CONTRACT.md](ENGINE_JOB_CONTRACT.md), and terminal lifecycle semantics by
> [ENGINE_JOB_LIFECYCLE.md](ENGINE_JOB_LIFECYCLE.md). This document defines the stable progress,
> coarse timing, and optional resource-observation vocabulary used by engine callers.

The reusable implementation is src/pipeline/engine_telemetry.py. The current config-first
run_pipeline() can emit the same structured events when explicitly requested, but it is still not
the full v1 JobExecutor adapter.

## 1. Design boundary

Structured telemetry is an engine observation surface. It must not become an alternate execution
contract or require callers to parse pipeline.log.

The contract separates three layers:

1. **public progress events** — small, stable ProgressEvent records suitable for a CLI, worker,
   desktop app, or service adapter;
2. **compact job telemetry summary** — stage wall times and optional resource peaks suitable for a
   JobResult.resources projection or debug artifact;
3. **developer profiling/traces** — detailed Issue-specific traces, CUDA profiling, subprocess logs,
   and internal paths. These remain diagnostic and are not public progress fields.

Telemetry must not change detector, HOMR, OMR-DLN, grouping, numbering, MMR, correction, or artifact
publication semantics.

## 2. Stable ProgressEvent vocabulary

Issue #339 does **not** add new v1 enum or stage-registry values. The existing closed v1 vocabulary
remains authoritative.

Event kinds:

- job_started;
- stage_started;
- stage_progress;
- stage_completed;
- job_succeeded;
- job_review_required;
- job_failed;
- job_cancelled.

Stage IDs:

- job;
- input_validation;
- pdf_render;
- score_detection;
- measure_construction;
- measure_number_recognition;
- correction_application;
- numbering;
- artifact_materialization.

These are caller-facing work units, not internal function names. Dense detector subprocess names,
model filenames, run-directory names, and Issue-specific profiler span names must not become
required progress fields.

### 2.1 Additive v1 telemetry fields

Issue #339 adds two optional fields to ProgressEvent:

- elapsed_ms: non-negative integer wall-clock elapsed time for a completed coarse span or terminal
  job event;
- detail_code: non-empty namespaced machine-readable detail for an event.

Both are additive v1 fields under the compatibility policy in ENGINE_JOB_CONTRACT.md. Readers must
continue to work when either field is absent.

detail_code is intentionally an open string namespace. Consumers may recognize documented codes,
but must tolerate unknown future codes without treating them as a contract-version failure.

Current config-first codes include:

| Code | Meaning |
| --- | --- |
| pdf_render.page_prepared | rendered page is prepared for the next pipeline work |
| detection.source_generation_and_scoring | coarse dense/standard detection span |
| measure_construction.page_completed | one page completed base construction/numbering work |
| mmr.page_completed | one prepared page completed MMR batch output |
| mmr.skipped_missing_numbering_base | MMR could not process that page because its required base numbering artifact was absent |
| numbering.page_completed | one page completed final numbering work |
| page_skipped.user_excluded | caller/operator exclusion intentionally skipped that page in the reported stage |

Unknown detail codes are additive observations, not new terminal states.

## 3. Ordering and terminal semantics

The v1 ordering rules remain unchanged:

- one stream contains one job_id;
- sequence is strictly increasing;
- no event follows a terminal event;
- terminal progress kinds are derived from the terminal JobStatus.

TelemetryRecorder.terminal() maps exactly:

| JobStatus | ProgressKind |
| --- | --- |
| succeeded | job_succeeded |
| review_required | job_review_required |
| failed | job_failed |
| cancelled | job_cancelled |

Deadline and explicit-cancellation interpretation remains owned by
ENGINE_JOB_LIFECYCLE.md; telemetry must not redefine it.

The current config-first run_pipeline() has no v1 JobResult adapter yet. Its optional telemetry
integration therefore reports a normal return as job_succeeded and an unhandled ordinary exception
as job_failed, without inventing an EngineError category/code or inferring review_required.
A future v1 executor adapter must emit the terminal event from the same terminal disposition used to
construct its JobResult.

## 4. Progress units

Per-page progress is reported only where the current execution boundary can state it truthfully.

page_number is the one-based page ordinal inside the engine job's ordered page set. It is
not a promise that the source PDF page index is contiguous; the same ordinal is used across stages.

When completed_units / total_units are present:

- both are integers;
- completed_units <= total_units;
- unit identifies the work unit, currently usually page.

Callers may display completed_units / total_units, but must not assume equal work per page. In
particular, dense source generation and model work can be phase-batched and page costs vary
substantially. The engine must not emit a fabricated smooth percentage merely to make a UI look
active.

The current dense detection boundary is therefore reported as a coarse score_detection span rather
than pretending the internal all-pages SR / page-local worker graph is a uniform page counter.

## 5. Timing semantics

elapsed_ms uses a monotonic wall clock around coarse engine spans.

It is intentionally **not** CUDA-kernel timing:

- public telemetry does not call torch.cuda.synchronize();
- it does not insert CUDA events;
- it does not reinterpret asynchronous GPU execution as a profiler-grade model inference duration.

This keeps structured progress lightweight and avoids changing GPU scheduling merely to obtain
telemetry. Detailed synchronization-correct attribution remains developer profiling work such as the
historical #281 methodology.

A stage that exits by exception is retained in the compact summary as state = aborted and does not
emit a false stage_completed event. The job may then emit its appropriate terminal failure or
cancellation event.

## 6. Resource summary

Resource sampling is **opt-in**. It is disabled for ordinary production/config-first execution.

When enabled, ResourceSampler performs best-effort periodic sampling without CUDA synchronization:

- recursive process-tree RSS and CPU use via psutil when available;
- process-tree GPU memory by matching sampled process PIDs to nvidia-smi compute-app accounting;
- device-level GPU utilization from nvidia-smi.

The compact numeric projection uses fields compatible with JobResult.resources:

- wall_time_seconds;
- progress_sink_error_count;
- resource_sample_count;
- resource_sample_interval_seconds;
- peak_process_tree_rss_bytes when process-tree measurement is available;
- peak_process_tree_cpu_percent when process-tree measurement is available;
- peak_process_count when process-tree measurement is available;
- peak_gpu_memory_bytes when NVIDIA process accounting is available;
- peak_device_gpu_utilization_percent when NVIDIA device sampling is available.

All are finite, non-negative numeric values as required by v1 JobResult.resources.

Sampling is observational rather than a hard quota mechanism. Periodic sampling can miss short
spikes, and device utilization can include unrelated work on a shared GPU. Hard CPU/RAM/GPU/disk
limits remain worker/container responsibilities under ENGINE_INPUT_SAFETY.md and
ENGINE_JOB_LIFECYCLE.md.

The implementation deliberately keeps psutil optional. Absence of an optional measurement source
omits those peak fields rather than failing the engine job.

## 7. Compact summary

TelemetryRecorder.summary() produces:

- schema pdfscorebar.engine.telemetry_summary.v1;
- job_id;
- coarse stage_spans containing stable stage IDs, elapsed milliseconds, and
  completed / aborted state;
- a numeric resources object.

The summary does not contain internal run-directory paths, model paths, subprocess command lines, or
raw logs. A future executor may copy the numeric resource projection into JobResult.resources and
retain the fuller summary as a debug artifact when its output profile permits it.

Progress sink failures are isolated from score processing and counted in
progress_sink_error_count. A failed observer must not silently turn otherwise valid score
processing into a different detector/MMR result.

## 8. Current config-first integration

src.pipeline.main.run_pipeline() now accepts optional:

- on_progress;
- telemetry_summary_path;
- sample_resources;
- resource_sample_interval_seconds.

When none are requested, no TelemetryRecorder is constructed and the existing pipeline execution
path remains the default.

The repository-local CLI exposes corresponding opt-in flags:

~~~bash
python -m src.pipeline.main \
  --config configs/dense_full_pipeline.yaml \
  --progress-jsonl artifacts/progress.jsonl \
  --telemetry-summary artifacts/telemetry.json
~~~

Resource sampling is separately enabled:

~~~bash
python -m src.pipeline.main \
  --config configs/dense_full_pipeline.yaml \
  --progress-jsonl artifacts/progress.jsonl \
  --telemetry-summary artifacts/telemetry.json \
  --sample-resources
~~~

JSONL progress is machine-readable and independent of console/file log wording. Diagnostic
pipeline.log remains useful for developers but is not a caller state contract.

## 9. Validation and non-impact contract

Focused tests cover:

- additive ProgressEvent serialization;
- strict sequence/terminal behavior;
- exact JobStatus -> terminal ProgressKind mapping;
- no event after terminal;
- aborted-stage behavior;
- progress sink failure isolation;
- JobResult.resources compatibility;
- current run_pipeline() default-off behavior;
- current config-runner success/failure terminal emission.

The telemetry integration does not change model/runtime selection, detector thresholds, image
geometry, grouping/MMR/numbering rules, or artifact publication rules. Default execution does not
construct the recorder. Opt-in coarse timing uses only monotonic host timing; optional resource
sampling uses observational host/NVIDIA queries and does not synchronize GPU work.

For those reasons a detector/full68 accuracy rerun is not a causal requirement for the contract
change itself. If later work moves telemetry inside numerically sensitive GPU kernels, changes
process/model lifetime, or changes scheduling, validation must be reclassified under
docs/dev/VALIDATION_POLICY.md.
