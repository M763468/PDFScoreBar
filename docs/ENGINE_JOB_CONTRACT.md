# Engine Job Contract v1

This document is the normative serialized boundary for Issue #336. It defines
one synchronous PDFScoreBar engine job independently of the current
configuration-first CLI and internal run-directory layout.

The Python representation lives in
`src/pipeline/engine_contract.py`. The contract is transport-neutral: a local
CLI, a worker process, or a future service adapter may all use the same
`JobRequest -> ProgressEvent* -> JobResult` model.

This change does **not** replace `run_pipeline()`, implement an HTTP API, or
turn internal `logs/` / `intermediate/` paths into public API.

## 1. Version envelope and compatibility

Every top-level serialized record carries:

- `schema`: a record-specific schema identifier;
- `contract_version`: currently `"1"`.

v1 schemas are:

| Record | Schema |
| --- | --- |
| JobRequest | `pdfscorebar.engine.job_request.v1` |
| JobResult | `pdfscorebar.engine.job_result.v1` |
| ProgressEvent | `pdfscorebar.engine.progress_event.v1` |
| EngineError | `pdfscorebar.engine.error.v1` |
| CorrectionSet | `pdfscorebar.engine.correction_set.v1` |

Compatibility rules:

- required v1 fields must be present in serialized records; deserializers do not
  substitute constructor defaults for an omitted required wire field;
- adding an optional field with unchanged meaning is additive within v1;
- v1 readers ignore unknown optional object fields;
- removing/renaming a required field or changing its meaning requires a new
  contract version;
- adding a value to a closed v1 enum/operation/stage registry is considered
  breaking for strict v1 readers and therefore requires a new version or an
  explicitly versioned extension;
- producers must never silently reinterpret a v1 field after deployment.

`canonical_json()` provides deterministic serialization: sorted object keys,
UTF-8 text, no insignificant whitespace, and rejection of NaN/Infinity.
Correction records are additionally serialized in `correction_id` order.

## 2. Direct Python boundary

The reusable boundary is expressed by the `JobExecutor` protocol:

```python
result = executor(request, on_progress=handle_event)
```

The current production pipeline is not yet wired to this protocol. That adapter
can be added separately without changing the serialized v1 contract.

## 3. JobRequest

Required semantics:

- `input.kind`: `local_path` or `engine_ref`;
- `input.reference`: the caller-visible input reference;
- optional `input.sha256`: source identity when known;
- `output_profile`: `final`, `review`, or `debug`;
- `config_overrides`: only supported public semantic overrides;
- optional `corrections`: a v1 CorrectionSet;
- optional `caller_reference`: opaque caller correlation value.

v1 intentionally allows only these configuration overrides:

- `pages`: one-based page numbers requested by the caller;
- `output_name`: caller-visible output stem.

Arbitrary repository config keys, model implementation paths, output roots,
worker settings, and internal run-directory paths are not part of the external
contract.

Example:

```json
{
  "schema": "pdfscorebar.engine.job_request.v1",
  "contract_version": "1",
  "input": {
    "kind": "local_path",
    "reference": "score.pdf"
  },
  "output_profile": "review",
  "config_overrides": {
    "pages": [1, 2],
    "output_name": "score"
  },
  "caller_reference": "cli-42"
}
```

## 4. Artifact descriptors

JobResult exposes artifacts by stable descriptor rather than by internal run
layout.

Each descriptor has:

- `artifact_id`: stable identity within the result;
- `role`: semantic role such as `final.score_numbered_pdf` or
  `review.manual_correction_input`;
- `location_kind`: `relative_path` or `engine_ref`;
- `reference`: package-relative path or engine-owned opaque reference;
- `media_type`;
- optional `sha256`;
- optional `coordinate_space`.

When `coordinate_space` is present, v1 requires these non-empty string
members so geometry provenance is meaningful and comparable:

- `type`;
- `origin`;
- `units`;
- `version`.

A `relative_path` must remain inside its returned artifact package. Absolute
paths and `..` traversal are rejected. Internal `logs/` or implementation
paths are therefore not required API fields.

## 5. CorrectionSet and current correction semantics

Corrections are engine inputs, not service/UI state. v1 preserves the current
manual-correction concepts and maps them into stable normalized operations:

| Current correction concept | v1 operation | Stable target/value |
| --- | --- | --- |
| MMR set measure span | `mmr.set_measure_span` | `page/system/measure` + `measure_span` |
| MMR suppress | `mmr.suppress` | `page/system/measure` |
| Measure construction force | `measure.force_measure` | `page/system/measure` |
| Add barline | `barline.add` | `page/bbox` |
| Remove barline | `barline.remove` | `page/bbox` |
| Movement boundary decision | `movement_boundary.set_decision` | `page/system` + `boundary` or `no_boundary` |

The normalized correction target uses the existing persisted zero-based
page/system/measure indexing contract. The current GUI staging
`measure_construction` field named `interval` is normalized to the canonical
measure target before it becomes a v1 correction record; this is a naming
adapter, not a change in correction meaning.

### 5.1 Provenance and stale-correction rejection

Every CorrectionSet identifies the exact source being corrected:

- `source_job_id`;
- `source_artifact_id`;
- `source_artifact_sha256`;
- `source_contract_version`;
- `coordinate_space`.

The correction source `coordinate_space` uses the same required
`type` / `origin` / `units` / `version` members as an artifact
descriptor. An empty coordinate object is not a valid provenance identity.

The engine must reject a correction set when any of those values no longer
matches the source artifact. It must not guess, rescale, or silently apply a
stale correction to a different artifact/version/coordinate contract.

The Python `CorrectionSet.assert_source_matches()` helper implements this
gate.

### 5.2 Reprocess, idempotency, and conflicts

v1 fixes:

- `reprocess_mode = "reuse_compatible_artifacts"`;
- `conflict_policy = "reject"`.

A corrected request is a **new engine job** with a new `job_id`. The correction
set points back to the source job/artifact. Reprocessing starts from that
identified source state and may reuse compatible retained artifacts; it must
not cumulatively apply the same corrections to an already corrected output.

Idempotency rules:

1. `correction_set_id` identifies one logical correction submission.
2. Repeating the same `correction_set_id` with the same canonical CorrectionSet
   payload against the same source is an idempotent repeat.
3. Reusing a `correction_set_id` with different canonical content is a
   conflict and must be rejected.
4. Duplicate `correction_id` values inside one CorrectionSet are invalid.
5. If two records cannot both be satisfied under the same source state, the
   executor rejects the set rather than choosing an implicit winner.

Persistence of idempotency history belongs to the caller/executor integration,
not to this pure data module.

## 6. JobResult

JobResult always contains:

- `job_id`;
- terminal `status`;
- engine/pipeline/source `provenance`;
- page summary (`requested`, `processed`, `skipped`);
- artifact descriptors;
- warnings;
- review disposition.

Optional data includes a structured failure, caller reference, and resource
summary.

Terminal statuses are:

- `succeeded`;
- `review_required`;
- `failed`;
- `cancelled`.

`failed` and `cancelled` require an EngineError. Successful and
review-required results must not contain one. `review_required` requires
`review.required=true`, and its correction source must name an artifact
returned by that result.

### 6.1 Representative success

```json
{
  "schema": "pdfscorebar.engine.job_result.v1",
  "contract_version": "1",
  "job_id": "job-success",
  "status": "succeeded",
  "provenance": {
    "engine_version": "0.1.0",
    "pipeline_version": "dense-v1",
    "source_commit": "abc123"
  },
  "pages": {
    "requested": 2,
    "processed": 2,
    "skipped": 0
  },
  "artifacts": [
    {
      "artifact_id": "final.pdf",
      "role": "final.score_numbered_pdf",
      "location_kind": "relative_path",
      "reference": "final/score_score_numbered.pdf",
      "media_type": "application/pdf"
    }
  ],
  "warnings": [],
  "review": {
    "required": false,
    "reason_codes": []
  }
}
```

### 6.2 Success with warning

A warning does not change terminal success by itself:

```json
{
  "status": "succeeded",
  "warnings": [
    {
      "code": "page_skipped",
      "message": "One page was skipped."
    }
  ]
}
```

The omitted fields are identical in meaning to the complete success example.

### 6.3 Review required

```json
{
  "status": "review_required",
  "review": {
    "required": true,
    "reason_codes": ["movement_boundary_ambiguous"],
    "correction_source_artifact_id": "review.manual_correction_input"
  }
}
```

The named correction source artifact must be present in the same result and
should include a content hash and coordinate-space description.

### 6.4 Failure

```json
{
  "status": "failed",
  "failure": {
    "schema": "pdfscorebar.engine.error.v1",
    "contract_version": "1",
    "category": "input",
    "code": "input_pdf_invalid",
    "public_message": "The input PDF could not be read.",
    "user_actionable": true,
    "retryable": false
  }
}
```

A production/public result uses `public_message` and omits diagnostic context.
Trusted diagnostics may serialize `debug_context` explicitly.

## 7. EngineError

Stable v1 categories are:

- `invalid_request`;
- `input`;
- `correction`;
- `resource`;
- `dependency`;
- `cancelled`;
- `internal`.

`code` is the stable machine-readable discriminator inside a category.
`public_message` is safe for an untrusted caller. `user_actionable` and
`retryable` are explicit booleans. Internal exception/path/stack information
belongs only in optional `debug_context`, which serialization excludes by
default.

Issue #337 defines the lifecycle/retry policy in
[`ENGINE_JOB_LIFECYCLE.md`](ENGINE_JOB_LIFECYCLE.md) while preserving this
public error envelope and the v1 terminal-status values.

## 8. ProgressEvent

Progress is structured data; callers must not parse `pipeline.log`.

Every event carries:

- `job_id`;
- strictly increasing `sequence`;
- `kind`;
- stable coarse `stage_id`;
- optional one-based `page_number`;
- optional `completed_units`, `total_units`, and `unit`;
- derived `terminal`.

v1 stage IDs are:

- `job`;
- `input_validation`;
- `pdf_render`;
- `score_detection`;
- `measure_construction`;
- `measure_number_recognition`;
- `correction_application`;
- `numbering`;
- `artifact_materialization`.

These are public work units, not internal function names. Their implementation
may change without changing the contract.

Terminal progress kinds are `job_succeeded`, `job_review_required`,
`job_failed`, and `job_cancelled`. Serialized events include `terminal`
as a required boolean derived from `kind`; readers reject a non-boolean or a
value that disagrees with `kind`. No event may follow a terminal event.
`validate_progress_sequence()` enforces job identity, strict monotonicity, and
terminal ordering.

Issue #339 may extend telemetry details with additive versioned fields, but
callers should continue to consume these stable event semantics.

## 9. Provenance and resource summary

JobResult provenance requires:

- `engine_version`;
- `pipeline_version`;
- `source_commit`.

Producers may add runtime/model identity fields without replacing those
required values. Model/runtime hashes should be recorded whenever they are
material to reproducibility.

`resources` is optional because not every adapter can measure every resource.
v1 accepts non-negative finite numeric fields such as
`wall_time_seconds`, `peak_rss_bytes`, and `peak_gpu_memory_bytes`.
More precise lifecycle/resource semantics are owned by #337 and #339.

## 10. Relationship to current output/review contracts

This contract reuses rather than replaces the accepted productization lineage:

- #227 defines `final` / `review` / `debug` output-profile meaning;
- #236 connects the review package, manual correction GUI, canonical correction
  files, corrected rerun, and final artifact flow;
- `docs/manual_correction_review_package.md` remains the current operator guide.

The engine contract gives those concepts a caller-facing versioned envelope.
Current internal run directories remain implementation details.

## 11. Validation and deferred work

Focused tests cover:

- deterministic request round-trip and v1 additive-field tolerance;
- unknown version rejection;
- current correction-operation mapping;
- stale correction source rejection;
- duplicate correction IDs and internal config-path rejection;
- success, warning, review-required, and failure result shapes;
- public-safe versus diagnostic error serialization;
- monotonic/terminal progress semantics;
- artifact path containment;
- NaN rejection.

This contract-only change does not alter detector/MMR/numbering inference,
model loading, GPU execution, or canonical evaluation outputs. Wiring a real
pipeline executor, lifecycle/cancellation behavior, untrusted-input safety,
richer telemetry, and container compatibility remain follow-up work under
#337-#340.
