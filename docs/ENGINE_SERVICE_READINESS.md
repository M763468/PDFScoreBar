# Engine service-readiness gates

Issue #340 closes the service-readiness validation slice around the v1 engine
contract. The gates validate the engine boundary; they do not implement or
deploy a web service.

## Supported one-job boundary

The reusable synchronous adapter is
`src.pipeline.engine_executor.PipelineJobExecutor`:

```python
result = executor(request, on_progress=handle_event)
```

It accepts the v1 `JobRequest`, forwards v1 `ProgressEvent` records, and
returns a v1 `JobResult` with a structured `EngineError` on failure.

The adapter owns `artifact_root/<job_id>` attempt storage. Internal generated
configs, run directories, and `pipeline.log` remain implementation details.
Only relative paths advertised by `JobResult.artifacts` are caller-facing.

Publication is success-only:

- `final/<output-name>_score_numbered.pdf` is advertised as
  `final.score_numbered_pdf`;
- `review/manual_correction_input.json` is advertised for `review` and
  `debug` profiles;
- the public review handoff contains package-relative review files plus stable
  source-job/coordinate identity, but not the internal source run/manifest
  paths;
- a failed attempt advertises no final/review artifacts and removes any staged
  public output before returning.

The current reference executor does not directly apply a v1 `CorrectionSet`.
Such a request returns the structured
`correction_execution_unavailable` correction error. The gate nevertheless
verifies that the review artifact descriptor hash/coordinate identity can be
used by `CorrectionSet.assert_source_matches()`. The retained
review/correction workflow remains the concrete correction execution path.

## Cheap PR compatibility gate

`.github/workflows/pr-validation.yml` runs an `engine-contract` job with
only lightweight Python dependencies. It covers:

- JobRequest / JobResult / ProgressEvent / EngineError / CorrectionSet wire
  compatibility;
- accepted v1 and incompatible-version behavior;
- input safety and stable failure codes;
- lifecycle/telemetry invariants;
- executor final/review publication without exposing internal run/log paths;
- malformed request handling;
- deterministic child-process failure mapping and public-output cleanup.

The same executor tests are included in `make test-fast`.

## Clean container/runtime smoke

Run:

```bash
make verify-service-readiness-smoke
```

The Docker runtime wrapper first performs the existing canonical runtime
preflight, including the image/model artifact contract. It then starts the
service-readiness smoke with outbound container networking disabled
(`--network none`).

The smoke creates its PDF/staff/barline fixture deterministically under
`artifacts/`; it does not depend on the ignored local evaluation PDFs. The
representative job uses `configs/service_readiness_smoke.yaml` and the real
config-first pipeline/numbering/materialization path while intentionally
skipping detector and MMR inference. It asserts structured progress/result
serialization, final/review placement, correction-source compatibility, and
absence of internal run/log paths from the public result.

The same smoke also checks, before inference:

- corrupt PDF rejection;
- a configured PDF byte limit;
- missing required request fields;
- deterministic child-process failure mapping;
- no final/review publication after those failures.

This smoke is a service-boundary/runtime compatibility check, not an accuracy
benchmark.

## GPU and accuracy validation policy

Use the narrowest authoritative validation that can detect the change:

| Change | Required validation |
| --- | --- |
| Contract/schema/executor unit-only change | PR `engine-contract` gate and `make test-fast` |
| Container/service-boundary wiring | `make verify-service-readiness-smoke` |
| Production GPU/model loading or detector runtime path | `make verify-gpu-smoke` in addition to the above |
| Detector/MMR/numbering numerical behavior or canonical evaluation output | Existing focused tests + GPU smoke + the repository heavy/full evaluation required by `docs/dev/VALIDATION_POLICY.md` |

A full68 run is not required solely because serialization, failure mapping,
artifact descriptors, CI wiring, or the service-readiness smoke changed. If a
change also affects production accuracy behavior, the existing accuracy policy
remains authoritative.

## Relationship to a future service

A future service/control-plane may call this versioned engine boundary and own
HTTP, queues, persistence, object storage, retry scheduling, deployment, and
user/product policy separately. It must not parse `pipeline.log`, discover
files under internal run directories, or reimplement detector/MMR/numbering
semantics.
