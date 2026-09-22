# Future Service Architecture and Engine Responsibility Boundary

> **Status: future architecture / roadmap.**
>
> This document describes the intended long-term boundary around the PDFScoreBar engine. It is
> **not** a description of the currently implemented runtime. For current production behavior,
> stage ownership, coordinate/process boundaries, and current artifacts, use
> [`PIPELINE_ARCHITECTURE.md`](PIPELINE_ARCHITECTURE.md), current source/tests, and the active
> production config.

## 1. Purpose and authority

PDFScoreBar is being prepared so that the score-processing engine can eventually be called by
interfaces other than the current repository-local config-first workflow. The durable goal is to
define a stable engine boundary that can be reused by a local CLI, a subprocess worker, a desktop
application, or a future service without turning service/control-plane concerns into engine
responsibilities.

This document owns the **future responsibility boundary and architectural direction**. It does not
redefine detector, HOMR, OMR-DLN, numbering, MMR, or current process/memory behavior.

Current behavior remains authoritative in:

- [`PIPELINE_ARCHITECTURE.md`](PIPELINE_ARCHITECTURE.md) for the production pipeline;
- [`manual_correction_review_package.md`](manual_correction_review_package.md) for the current
  config-first review/correction workflow;
- current source, tests, and production configuration for implementation details.

## 2. Current state

### 2.1 Current repository role

The current repository is a score-processing pipeline/engine. Its maintained production path owns
PDF rendering, score/barline detection, grouping and numbering, measure-number recognition,
correction application, and final/review artifact materialization.

The current execution boundary is still config-first:

```text
YAML config
  -> src.pipeline.main.run_pipeline(...)
  -> PipelineOrchestrator
  -> internal run directory
  -> current final/review/debug artifacts
```

The normal maintained entry is currently `make run-pipeline CONFIG=...` /
`src/pipeline/main.py --config ...`. The previously designed `pdfscorebar run ...` product-facing
CLI direction is not yet a current console-script contract.

### 2.2 Current output and correction workflow

The repository already has a real correction path; service-readiness must build on it instead of
inventing a second correction model.

The current config-first review workflow can materialize a package containing
`review/manual_correction_input.json`, package-local page evidence, and a correction directory. The
existing GUI can review the package, stage/save supported corrections, and the apply path can
canonicalize those corrections and regenerate corrected final numbering/PDF output.

Current correction semantics include, as applicable to the current workflow:

- MMR measure-span correction and suppression;
- measure-construction correction such as forcing a measure;
- barline construction add/remove correction;
- package-local movement-boundary review when movement evidence is attached.

The current detailed operating contract remains
[`manual_correction_review_package.md`](manual_correction_review_package.md). Future machine
contracts should expose compatible correction concepts through stable versioned inputs/artifact
descriptors rather than requiring external callers to understand arbitrary internal `logs/` or
run-directory paths.

### 2.3 What does not exist yet

The following are future directions, not current runtime claims:

- a production adapter that executes the current pipeline through the versioned
  `JobRequest` / `JobResult` library boundary;
- production emission of the defined structured `ProgressEvent` stream;
- production mapping of current failures into the defined structured `EngineError`
  taxonomy;
- a service/control-plane implementation;
- a production queue, job database, or object-storage integration;
- a guaranteed public `pdfscorebar` console surface.

### 2.4 Current versus target summary

| Concern | Current state | Target direction |
| --- | --- | --- |
| Job invocation | Config/run-directory oriented; v1 request types are defined but not wired to production execution | Versioned one-job engine request |
| Engine result | Internal run directory + known artifacts; v1 result/artifact types are defined | Structured result with artifact descriptors and provenance |
| Progress | Logs/current stage behavior; v1 event semantics are defined but not emitted by production | Stable structured progress/events |
| Errors | Existing exceptions/logging/exit behavior; v1 error envelope is defined but not wired | Structured engine error categories |
| Final/review outputs | Implemented current artifacts | Stable external artifact descriptors |
| Corrections | Config-first review package + existing GUI/apply path | Versioned correction input/output contract reusing current semantics |
| Service/control plane | Not implemented | Separate consumer of the engine contract |
| Service product policy | Not decided | Deferred future work |

## 3. Target responsibility boundary

The intended long-term architecture is:

```text
future client / web UI / desktop app
                |
                v
future service / control plane
  HTTP/API, scheduling, persistence, storage,
  deployment/scaling, notifications, product policy
                |
                v
worker / adapter
  translate one external job into the engine contract,
  establish process/container/resource isolation
                |
                v
PDFScoreBar engine  <-- this repository's durable responsibility
  versioned one-job contract
  score-processing domain logic
  progress/error/resource reporting
  final/review artifact + correction semantics
  provenance and engine-side validation
```

The service/control-plane and worker layers are architectural consumers of the engine. They do not
have to live in this repository. In particular, once the engine contract is stable, a private
prototype or later public service may be developed in a separate repository with its own release,
deployment, persistence, and operational lifecycle.

A thin reference adapter may remain here if it is useful for validating the engine contract, but
service-specific orchestration must not become a prerequisite for using or testing the engine.

### 3.1 This repository should own

The PDFScoreBar engine should own:

- score-processing domain logic and its correctness/regression contracts;
- model/runtime/provenance identity needed to reproduce a job;
- the stable versioned one-job request/result boundary;
- stable final/review/debug artifact meanings exposed to callers;
- correction-input semantics and deterministic correction application;
- structured progress, warnings, and engine error semantics;
- engine-side input validation/resource-bound hooks;
- one-job success/failure/cancellation cleanup semantics that must be consistent regardless of
  caller;
- compatibility tests for the engine-facing contract.

### 3.2 A future service/control plane should own

A service/control plane should normally own:

- HTTP/web application concerns;
- queueing and cross-job scheduling;
- persistent job/history databases;
- object-storage integration and long-term retention policy;
- deployment, replication, autoscaling, and service monitoring;
- notification delivery;
- user/session/product policy;
- global abuse/rate-limit policy.

Those responsibilities should not leak into core score-processing types merely because one future
consumer is a web service.

### 3.3 Worker/adapter boundary

A future worker/adapter should remain deliberately thin. Its job is to:

- receive or resolve an external job;
- construct the supported engine request;
- establish the required process/container/resource boundary;
- forward structured progress;
- return the structured result/error and artifact descriptors.

It should not duplicate detector/MMR/numbering/correction rules. If a service-specific worker needs
queue leases, database transactions, object-store uploads, or retry orchestration, those concerns
belong to the service-side implementation and may live entirely outside this repository.

## 4. Target one-job dataflow

### 4.1 Initial processing

Conceptually, a future caller should be able to execute one synchronous engine job:

```text
JobRequest
  -> request/input validation
  -> one PDFScoreBar engine execution
       -> ProgressEvent*
  -> JobResult
       -> final artifacts
       -> optional review artifacts
       -> warnings/provenance/resource summary
```

The engine may internally continue to use multiple processes, GPU phase boundaries, retained
artifacts, or run directories. Those are implementation details unless a field is deliberately
promoted into the versioned external contract.

### 4.2 Review and correction loop

Correction is part of the intended engine product boundary, not an afterthought limited to the
current developer workflow.

A future review-capable flow should support this conceptual loop:

```text
initial JobRequest
  -> engine
  -> review-capable JobResult + review artifacts
  -> reviewer / correction UI
  -> versioned correction input
  -> engine reapply/reprocess
  -> corrected JobResult + final artifacts
```

The exact transport and UI may differ by caller. A local CLI may open the current GUI; a future
desktop or web application may provide another UI. The engine boundary should nevertheless preserve
one compatible correction meaning.

The v1 machine contract is now defined in
[`ENGINE_JOB_CONTRACT.md`](ENGINE_JOB_CONTRACT.md). It maps the current barline,
measure-construction, MMR, and movement-boundary concepts into versioned correction records; binds
each correction set to the source job/artifact hash/coordinate/version; treats corrected execution
as a new job that may reuse compatible retained artifacts; rejects conflicts and stale source
identity; and defines explicit review-required result semantics.

The current review package and correction application behavior remain the concrete operator/runtime
semantics to reuse. The v1 contract provides the stable external envelope without requiring callers
to understand the internal run-directory layout.

The engine owns interpretation and application of supported corrections. A future service may own
review sessions, collaborative UI state, persistence/history, and long-term storage of user
decisions.

## 5. Versioned engine contract direction

Issue #336 defines the exact v1 serialized contract in
[`ENGINE_JOB_CONTRACT.md`](ENGINE_JOB_CONTRACT.md), with lightweight Python representations in
`src/pipeline/engine_contract.py`. This section remains the architecture-level summary of that
boundary; the contract document owns exact fields, compatibility, correction provenance,
idempotency/conflict behavior, and deterministic serialization.

### JobRequest

A request should identify:

- the input PDF or engine-local input reference;
- requested output profile/capabilities;
- supported configuration overrides only;
- optional versioned correction input;
- requested engine contract version;
- caller reference/job identifier only when its semantics are explicit.

The request must not require arbitrary internal run-directory paths or model implementation paths.

### JobResult

A result should provide:

- terminal status;
- engine/pipeline/provenance identity;
- processed/skipped page summary where applicable;
- final and/or review artifact descriptors;
- correction/review information when relevant;
- warnings;
- structured failure information when unsuccessful;
- timing/resource summary when available.

### ProgressEvent

Progress should expose stable job/stage/page units without requiring callers to regex
`pipeline.log`. Stable stage identifiers should describe meaningful engine work, not every internal
function name.

### EngineError

Errors should distinguish stable categories and public-safe messages from diagnostic context, and
should expose enough retryability/actionability information for a caller without moving retry
orchestration into the engine.

## 6. Lifecycle, safety, and resource boundary

A service-ready engine must make one job bounded and diagnosable even when no account/login layer
exists.

The architecture therefore requires explicit engine-side contracts for:

- validated PDF/input metadata and configurable per-job limits;
- malformed/encrypted/unsupported/pathological input rejection;
- page/rendered-pixel/file-size/resource-budget hooks where appropriate;
- timeout/cancellation boundaries;
- retryable versus non-retryable engine failures;
- GPU OOM, disk-full, subprocess crash, and missing-runtime/model-asset behavior;
- partial output semantics so failed/cancelled jobs are never presented as successful final output;
- temporary/review/debug/final artifact cleanup classes;
- public-safe versus diagnostic-only error/log information;
- runtime network/model-asset assumptions;
- worker/container isolation assumptions.

Detailed lifecycle, safety, telemetry, and compatibility contracts are intentionally split into
#337, #338, #339, and #340.

## 7. Phased roadmap

The phases are architectural milestones, not a requirement that all later service code live in this
repository.

### Phase 1 — engine productization

Stabilize the supported local input/output/review/correction surface and separate it from
experiment/debug/legacy paths. This is the main connection to #225 and repository-surface work such
as #230/#100.

### Phase 2 — service-ready engine contract

Define and validate the versioned one-job boundary, lifecycle/error semantics, untrusted-input
bounds, structured progress/resource telemetry, and compatibility gates (#336-#340).

This is the main long-term responsibility of this repository under the service-readiness Epic.

### Phase 3 — private/single-instance prototype

Build a thin real consumer of the engine boundary to prove that the engine can be called without
depending on internal run layout or repository-local operator knowledge.

This prototype will likely be better treated as a **separate service/application project or
repository**. Keeping it here is not an architectural requirement. The PDFScoreBar repository should
only absorb generic engine/contract improvements discovered by the prototype.

### Phase 4 — optional broader service

If there is a product need, evolve the external service toward broader availability, storage,
scaling, operational monitoring, and other service concerns.

This phase is expected to be service-side work and may have a completely separate repository,
deployment cadence, and technology stack. It must consume the PDFScoreBar engine contract rather
than pulling service-specific concerns back into the engine.

## 8. Future work and deferred product decisions

The following decisions are deliberately deferred until a concrete service/product need exists:

- anonymous versus authenticated access;
- accounts, identity, and saved user history;
- billing/subscriptions;
- quotas and product-level global rate limits;
- long-term artifact retention;
- cloud/vendor selection;
- database/object-storage products;
- deployment topology and autoscaling;
- notification mechanisms;
- whether Phase 3/4 uses one service repository or several.

An anonymous/no-login/no-billing one-shot conversion service remains a valid future option. That
possibility is the reason engine safety must not depend on authentication, but it does **not** make
authentication/account/billing design part of the current engine contract work.

## 9. Relationship to existing work

- #334 — parent Epic and service-readiness workstream definition.
- #335 — this durable architecture/responsibility-boundary record.
- #336 — v1 JobRequest/JobResult/ProgressEvent/EngineError/CorrectionSet contract and shared Python types.
- #337 — bounded execution, cancellation/retry, partial output, and cleanup semantics.
- #338 — untrusted-PDF / anonymous-job engine-side safety contract.
- #339 — structured progress and resource telemetry.
- #340 — engine contract/container compatibility gates.
- #225 / #226-#229 / #236 — user-facing entrypoint, output-profile, final-output, and correction
  concepts that service-readiness should reuse rather than replace.
- #230 / #100 / #115 — repository/public-surface cleanup that should preserve the stable engine
  boundary while retiring experiment/legacy surface.

Accuracy/correctness, usability/productization, and service-readiness are coordinated workstreams,
not a strict serial dependency chain. A future service contract must reuse accepted output and
correction concepts, but it need not wait for every unrelated accuracy or cleanup issue to finish.

## 10. Documentation maintenance and change triggers

The current and future architecture documents intentionally have different authority. Keeping them
separate is useful only if changes review both sides when a boundary moves.

| Change | Required documentation review |
| --- | --- |
| Current stage ownership, authoritative geometry, route order, model/runtime ownership, or major process/memory boundary | Update `PIPELINE_ARCHITECTURE.md`; also review this document if the change alters assumptions visible at the engine boundary |
| Implemented external one-job/artifact/progress/error/correction behavior | Update this document when architectural intent changes **and** update current operating/architecture docs that now describe implemented behavior |
| Final/review/correction workflow semantics | Review this document plus `manual_correction_review_package.md`; update `PIPELINE_ARCHITECTURE.md` when production pipeline behavior/ownership also changes |
| Future service-only product/deployment choice | Update this document only when the long-term boundary materially changes; do not rewrite current production architecture |
| Pure internal refactor with unchanged boundaries | No mechanical architecture-doc rewrite; verify that existing statements remain true |

Repository PRs include an architecture-document checklist so changes should explicitly record
whether these current/future documents were reviewed. The documentation index also keeps the two
documents in different current/future categories.

Do not duplicate detailed current pipeline internals here simply to keep the documents “in sync.”
The maintenance contract is to keep **ownership/boundary statements consistent**, while detailed
current runtime behavior remains in the current architecture source of truth.

## 11. Non-goals

This architecture document does not:

- implement a service, HTTP API, queue, database, or object store;
- select a cloud/vendor/deployment platform;
- design authentication, accounts, or billing;
- duplicate the exact serialized schemas owned by `ENGINE_JOB_CONTRACT.md`;
- replace the current manual-correction operating guide;
- redefine detector/HOMR/OMR-DLN/MMR/numbering behavior;
- require Phase 3 or later service code to live in this repository;
- turn speculative service implementation details into current runtime contracts.
