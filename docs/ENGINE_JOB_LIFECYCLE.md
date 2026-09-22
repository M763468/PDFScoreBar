# Engine One-Job Lifecycle Contract

> **Status: Issue #337 lifecycle contract layered on Engine Job Contract v1.**
>
> The serialized external boundary is already defined by
> [`ENGINE_JOB_CONTRACT.md`](ENGINE_JOB_CONTRACT.md) / `src.pipeline.engine_contract`.
> This document does not redefine that schema. It specifies how one synchronous engine attempt
> reaches the existing v1 terminal statuses, how timeout/cancellation/retryability behave, and when
> artifacts may be treated as published.
>
> Current production runtime behavior remains authoritative in
> [`PIPELINE_ARCHITECTURE.md`](PIPELINE_ARCHITECTURE.md), current source/tests, and the active
> production configuration.

## 1. Scope and authority

PDFScoreBar remains synchronous at the one-job engine boundary:

```text
JobRequest
  -> one engine attempt
       -> ProgressEvent*
  -> JobResult
```

A future worker/service may wrap that call with queueing, leases, persistence, retries, worker
placement, or object storage. Those are not engine responsibilities.

This lifecycle contract owns:

- the meaning of the v1 terminal statuses in execution/lifecycle terms;
- execution deadlines and cooperative cancellation;
- safe cancellation/timeout checkpoints;
- retryability semantics carried by `EngineError.retryable`;
- re-execution and general attempt idempotency expectations;
- partial-artifact publication rules;
- one-attempt temporary/intermediate cleanup;
- lifecycle mappings for OOM, disk full, subprocess crash, invalid PDF, missing runtime assets;
- alignment with existing review/correction behavior.

This contract does **not** define:

- a production queue or scheduler;
- queue leases or cross-job scheduling;
- persistent job/history state;
- object-storage retention duration;
- authentication/accounts/billing;
- concrete untrusted-PDF size/page/pixel limits (#338);
- richer progress/resource telemetry (#339);
- service deployment or container compatibility gates (#340).

## 2. Relationship to Engine Job Contract v1

Issue #336 is complete and its v1 types are normative. In particular:

- `JobStatus` is exactly:
  - `succeeded`;
  - `review_required`;
  - `failed`;
  - `cancelled`.
- `failed` and `cancelled` require an `EngineError`.
- `succeeded` and `review_required` must not contain an `EngineError`.
- `review_required` requires `review.required=true` and a valid correction-source artifact.
- `EngineError` exposes:
  - `category`;
  - stable machine-readable `code`;
  - public-safe message;
  - `user_actionable`;
  - `retryable`;
  - optional diagnostic-only `debug_context`.
- `caller_reference` is correlation metadata, not an idempotency key.
- correction execution uses the versioned `CorrectionSet` provenance/idempotency rules from #336.

Issue #337 therefore does not introduce a second terminal-status enum or another error envelope.

## 3. Current behavior audit

The current config-first runtime is not yet wired to the v1 `JobExecutor` protocol.

| Concern | Current behavior | Gap relative to lifecycle contract |
| --- | --- | --- |
| Invocation | `run_pipeline(...)` is synchronous and returns an internal run directory | No v1 adapter produces `JobResult` yet |
| Top-level failure | Exceptions propagate; top-level logging handler is restored in `finally` | No current exception-to-`EngineError` adapter |
| Timeout | No `run_pipeline()` deadline parameter | Hung work may continue until an outer process/container limit acts |
| Cancellation | No cancellation token/checkpoint is accepted | No cooperative cancellation in current pipeline |
| Child processes | Dense-route workers use `subprocess.run`; OMR helper uses `run_with_logging` | No common timeout/cancel/process-group termination policy |
| Child failure | Non-zero exit becomes `RuntimeError` / `CalledProcessError` | Failure is not yet mapped to v1 error categories/codes |
| Run completion marker | `manifest.json` and `filters.json` are written near normal completion | Not a public lifecycle result |
| Per-page output | `numbering_final.json` can be written before later work completes | Existing "final"-named files can be partial-attempt evidence |
| Review package | Materialized after normal pipeline work completes | Materialization itself is not transactional |
| JSON/PDF writes | Several outputs are written directly to destination paths | Process/disk failure can leave a partial destination file |
| Cleanup | Run/intermediate/SR/debug data generally remains until separate cleanup | No per-attempt lifecycle cleanup class |
| Re-execution | `--skip-existing` can reuse internal artifacts | Operator mechanism, not public idempotency |
| Correction rerun | Retained-artifact selective rerun already preserves source provenance | Corrected attempt publication/cleanup is not yet a v1 executor transaction |

Two current-runtime consequences are important:

1. internal file existence is not proof of a successful one-job result;
2. a hard-killed current process may leave partial files without any terminal engine result.

## 4. Terminal semantics

### 4.1 `succeeded`

The requested engine work completed and the `JobResult` intentionally advertises the artifact set
that callers may consume.

Requirements:

- required artifacts for the request are complete enough for their declared role;
- advertised artifact descriptors are the publication boundary;
- staging/internal paths are not caller-visible deliverables merely because they exist;
- no `EngineError` is attached;
- terminal progress, when emitted, is `job_succeeded`.

### 4.2 `review_required`

The engine completed a valid review-producing attempt, but caller/user review is required before the
workflow should be treated as fully accepted final output.

Requirements inherited from v1:

- `review.required=true`;
- `review.correction_source_artifact_id` names an artifact returned by this result;
- that correction-source artifact has the required hash and coordinate-space identity;
- no `EngineError` is attached;
- terminal progress, when emitted, is `job_review_required`.

Lifecycle implications:

- review artifacts advertised by this result are valid published deliverables;
- internal partial files not advertised by the result remain non-public;
- callers must not collapse `review_required` into `succeeded`;
- correction/reprocess is a new engine job under the #336 `CorrectionSet` contract.

### 4.3 `failed`

The attempt did not complete the requested engine operation.

Requirements:

- an `EngineError` is present;
- no internal partial file is implicitly promoted to a successful deliverable;
- diagnostic artifacts may be retained according to the bounded cleanup policy;
- terminal progress, when emitted, is `job_failed`.

A deadline expiry is `failed`, not `cancelled`.

### 4.4 `cancelled`

An explicit cancellation request was observed at a supported cancellation checkpoint and execution
stopped because of that request.

Requirements:

- an `EngineError` is present with category `cancelled`;
- no unadvertised partial output is treated as successful;
- terminal progress, when emitted, is `job_cancelled`;
- resubmission is an outer-caller decision, not an engine-side automatic retry.

If a process/container is killed before the engine can observe cancellation, the engine may be
unable to emit a `cancelled` result. The outer adapter must still treat the attempt as non-success;
it must never infer success from leftover files.

## 5. Execution deadline and cancellation

### 5.1 Reusable control primitive

Issue #337 provides `src.pipeline.engine_lifecycle` with:

- `CancellationToken`;
- monotonic `ExecutionDeadline`;
- `ExecutionControl.checkpoint()`;
- `JobCancelled`;
- `JobDeadlineExceeded`;
- mapping from those control exceptions into the normative v1 `JobStatus` / `EngineError`.

These are engine implementation helpers, not new wire-schema fields.

### 5.2 Safe checkpoints

Lifecycle checks should be added at stable boundaries rather than interrupting arbitrary Python/CUDA
execution:

- before expensive PDF rendering/inference;
- between coarse public stages;
- between pages when stage semantics allow;
- before launching a child process;
- after child completion and before consuming its result;
- before final/review artifact materialization;
- immediately before terminal publication.

Cancellation requested during a non-interruptible CPU/GPU operation may be observed only at the next
checkpoint.

### 5.3 Cancellation precedence

If explicit cancellation and deadline expiry are both already true when one checkpoint is reached,
explicit cancellation wins. The attempt maps to `JobStatus.CANCELLED`.

This makes a caller-requested stop distinguishable from an engine attempt that independently ran out
of its execution budget.

### 5.4 Deadline mapping

A deadline checkpoint maps to:

- status: `failed`;
- category: `resource`;
- code: `execution_deadline_exceeded`;
- public message: bounded, non-diagnostic;
- `retryable=true`.

Here `retryable=true` means a fresh attempt of the same semantic request **may** succeed under
different transient timing/placement conditions. It does not instruct the engine or queue to retry
automatically.

### 5.5 Explicit cancellation mapping

An observed explicit cancellation maps to:

- status: `cancelled`;
- category: `cancelled`;
- code: `job_cancelled`;
- `retryable=false`.

The outer caller may still deliberately submit a new job later. The flag only states that
cancellation itself is not a transient failure that should be automatically retried.

### 5.6 Child-process termination policy

When lifecycle control is wired into the current subprocess boundaries, the desired policy is:

1. check cancellation/deadline before launch;
2. launch the disposable child in a terminable process-group boundary;
3. observe cancellation/deadline while waiting;
4. request group termination;
5. allow a short bounded grace interval;
6. hard-kill if the child does not exit;
7. do not consume the child result unless exit/result validation succeeds;
8. map the parent attempt to `cancelled` or `failed` according to the triggering condition.

The current subprocess call sites do not yet implement this common policy. Existing intentional
GPU/process isolation must be preserved when that integration is added.

### 5.7 Hard outer timeout

A worker/container may enforce a hard execution limit as a backstop. SIGKILL/container loss can
prevent engine `finally` cleanup and terminal serialization. Therefore correctness must not depend
on post-kill cleanup, and absence of a terminal successful result is always non-success.

## 6. Retryability policy

`EngineError.retryable` is an engine hint. It does not implement retry orchestration.

The v1 boolean is interpreted as follows:

- `true`: a fresh attempt with the same semantic request may reasonably succeed without requiring
  input/correction changes; the outer caller still owns retry count/backoff/placement.
- `false`: unchanged automatic retry is not recommended. A user/service may submit a new job after
  changing input, corrections, configuration, or intent.

Recommended lifecycle mappings:

| Failure | v1 category | Suggested code | user_actionable | retryable |
| --- | --- | --- | --- | --- |
| malformed/corrupt/unsupported PDF | `input` | `input_pdf_invalid` | true | false |
| invalid request/config override | `invalid_request` | `request_invalid` | true | false |
| configured per-job limit rejection | `resource` | `resource_limit_exceeded` | true | false |
| execution deadline exceeded | `resource` | `execution_deadline_exceeded` | false | true |
| GPU OOM | `resource` | `gpu_out_of_memory` | false | true |
| disk full / write capacity failure | `resource` | `disk_capacity_exhausted` | false | true |
| unexpected child-process crash/signal | `internal` | `child_process_failed` | false | true |
| missing/invalid required model/runtime asset | `dependency` | `runtime_dependency_unavailable` | false | true |
| stale/invalid correction source | `correction` | `correction_source_invalid` | true | false |
| explicit observed cancellation | `cancelled` | `job_cancelled` | false | false |
| unknown internal error | `internal` | `internal_error` | false | true |

These mappings are defaults. When the engine can identify a more precise deterministic condition, it
should prefer that precise code/category over a generic retryable internal error.

A service may additionally suppress retries for policy/operational reasons. The engine does not own
queue backoff or retry limits.

## 7. Re-execution and idempotency

PDFScoreBar does not promise cross-worker exactly-once execution.

General job semantics:

- each execution gets a new engine `job_id`;
- `caller_reference` is correlation metadata and must not be treated as an idempotency key;
- retry/re-execution should use a fresh attempt workspace by default;
- a prior partial internal run directory must not be trusted merely because the same caller reference
  is reused;
- current `--skip-existing` remains an internal/operator optimization and recovery mechanism, not
  the external retry contract.

Correction-specific idempotency is already normative in #336 and remains unchanged:

- `correction_set_id` identifies one logical correction submission;
- repeating identical canonical content against the same source is an idempotent repeat;
- reusing the ID with different content is a conflict;
- the corrected execution itself is a new engine job;
- persistence of idempotency history belongs to caller/executor integration, not the pure contract
  module.

## 8. Artifact lifecycle and publication

Artifact meaning, not current directory name, determines lifecycle treatment.

| Class | Current examples | On non-failure terminal result | On failed/cancelled attempt | Public contract |
| --- | --- | --- | --- | --- |
| immutable input/reference | input PDF, source review package, CorrectionSet | caller-owned / retain | retain | input/reference only |
| ephemeral working data | temporary render/SR/staging/request files | delete when no longer needed | best-effort delete | never a deliverable |
| attempt intermediate | detector/MMR/numbering intermediates | retain only by debug/reuse policy | optional bounded diagnostics | not published by existence |
| explicitly reusable artifact | validated retained artifact with provenance | retain when contract permits | retain only if independently valid | descriptor/provenance governed |
| review deliverable | manual-correction handoff/package | publish only when descriptor returned | do not publish incomplete package | artifact descriptor |
| final deliverable | completed score-numbered output | publish only when descriptor returned | do not publish partial destination | artifact descriptor |
| debug/provenance evidence | logs, structured diagnostics, traces | optional bounded retain | optional bounded retain | diagnostic role only |

The key rule is:

> **Internal path existence is not publication. A caller may consume only artifacts intentionally
> advertised by a terminal non-failure `JobResult`.**

For `failed` or `cancelled`, leftover files can remain as diagnostic attempt evidence, but they
must not be surfaced as successful final/review deliverables.

For `review_required`, advertised review/correction-source artifacts are valid published outputs;
the caller still must honor the terminal status and continue the review workflow rather than treating
the result as `succeeded`.

## 9. Atomicity and partial writes

Current helpers often write JSON/PDF directly to destination paths. That means an OS/process/disk
failure can leave a partial destination.

Future lifecycle-aware materialization should prefer, where practical:

1. write to an attempt-local temporary path on the same filesystem;
2. flush/close and validate the artifact;
3. atomically replace/rename into the attempt's committed artifact location;
4. construct the descriptor from the committed artifact;
5. emit the terminal non-failure result only after required publication completes.

This is especially important for final PDFs, review handoffs, and any machine artifact used by a
later correction attempt.

## 10. Cleanup semantics

### 10.1 `succeeded` / `review_required`

After committed artifacts are ready:

- remove ephemeral data with no retained debug/reuse role;
- retain advertised artifacts and required provenance;
- retain optional debug evidence only according to bounded local policy;
- a cleanup warning that does not compromise an advertised artifact may be returned as a warning.

### 10.2 `failed`

- do not publish internal partial final/review artifacts;
- best-effort remove engine-owned ephemeral/staging files;
- optionally retain bounded diagnostic evidence;
- never delete immutable caller inputs or a successful source review package;
- record cleanup failure as diagnostic context/warning without converting the failed attempt to
  success.

### 10.3 `cancelled`

Use the same cleanup principles as failure, while preserving the distinct `cancelled` status.

### 10.4 Hard termination

The engine cannot guarantee cleanup after SIGKILL, container loss, machine failure, or filesystem
loss. The worker that owns the attempt workspace must be able to quarantine/delete it later without
understanding detector/MMR internals. TTL and long-term retention remain service/storage policy.

## 11. Failure-specific behavior

### Invalid/corrupt PDF

Current PyMuPDF open/render errors propagate. The future executor should map deterministic PDF
rejection to `ErrorCategory.INPUT` and a public-safe input code/message. Concrete preflight limits
and hostile-input checks are #338.

### GPU OOM

Treat as `failed`, category `resource`. Do not silently lower model quality or change the
requested semantic processing contract inside the same attempt just to obtain success. Existing
disposable process boundaries remain useful for releasing GPU state.

### Disk full/write failure

Treat as `failed`, category `resource`. A partial destination is not publication. Retry is an
outer decision after resource placement/capacity can change.

### Child-process crash

A non-zero/signal outcome is a failed parent attempt unless a more specific input/resource error is
known. Missing, stale, or malformed child result files must never be consumed as success.

### Missing model/runtime asset

Treat as `dependency`. Do not silently download/substitute a different model during ordinary job
execution. Another correctly prepared worker may retry the same semantic request.

## 12. Review/correction lifecycle

The existing review/correction semantics remain the implementation basis:

```text
initial JobRequest
  -> succeeded OR review_required JobResult
  -> advertised review/correction-source artifact
  -> CorrectionSet bound to source job/artifact/hash/coordinate/version
  -> new corrected JobRequest / new job_id
  -> corrected JobResult
```

Lifecycle rules:

- only a published review/correction-source descriptor can be the supported correction source;
- a failed/cancelled attempt does not create a valid review handoff merely because a partial review
  directory exists;
- stale correction-source identity is rejected using the #336 provenance gate;
- failure/cancellation of a corrected job does not reclassify the successful source job;
- the source review package and correction input are immutable inputs to the corrected attempt;
- corrected attempt intermediates follow ordinary attempt cleanup rules;
- corrected final/review artifacts are published only by that corrected attempt's terminal
  non-failure result.

## 13. Process exit and result consistency

A future CLI/subprocess adapter should obey:

- exit code zero only for non-error terminal outcomes accepted by that adapter;
- `failed` and `cancelled` use non-zero process exit;
- the exact numeric non-zero allocation is adapter policy unless separately standardized;
- emitted structured result and process exit must not contradict one another;
- if the process dies before terminal result serialization, the outer adapter treats it as
  non-success;
- free-form logs are diagnostics, never the state machine.

Because `review_required` is a valid non-failure `JobResult`, a CLI/worker may use zero for it as
long as it also preserves the explicit `review_required` status. Callers must not infer
`succeeded` from process code alone.

## 14. Responsibility split

### Engine / this repository

- synchronous one-attempt semantics;
- lifecycle checkpoints and control exceptions;
- mapping lifecycle control into v1 status/error;
- safe child-termination hooks when integrated;
- artifact publication rules;
- engine-owned attempt-local cleanup;
- retained-artifact provenance validation;
- correction/reprocess semantics;
- focused compatibility tests.

### #338

Accepted safety semantics are recorded in
[`ENGINE_INPUT_SAFETY.md`](ENGINE_INPUT_SAFETY.md):

- untrusted-PDF/path/network safety;
- concrete configurable per-job bounds;
- rejection before unnecessary expensive inference where feasible;
- worker/container hard-resource and offline-runtime assumptions.

### #339

- structured progress/resource telemetry beyond the already-frozen v1 core event vocabulary;
- ordering and resource instrumentation consistent with this lifecycle.

### #340

- cheap contract/failure tests plus container/runtime smoke proving the accepted one-job boundary.

### Future service/control plane

- queue leases;
- cross-job scheduling and concurrency;
- persistent job/history state;
- retry count/backoff/orchestration;
- worker placement/replacement;
- object-storage upload and retention duration;
- global quota/rate-limit/product policy.

## 15. Implementation status after #337

Issue #337 intentionally does not yet wire `run_pipeline()` or every dense-route subprocess into a
new executor. The accepted incremental implementation is:

- retain the current production pipeline behavior unchanged;
- add reusable cancellation/deadline primitives;
- map those primitives to the already-merged v1 `JobStatus` / `EngineError`;
- document current gaps and the required publication/cleanup semantics;
- cover the helper behavior with cheap focused tests.

A later pipeline adapter can consume these primitives without changing the #336 wire schema. Wiring
them through heavy GPU stages should preserve the current process/memory architecture and receive the
validation appropriate to that runtime change.
