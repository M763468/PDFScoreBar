# Engine Untrusted-PDF Safety Contract

This document is the normative Issue #338 safety contract for processing one
untrusted PDF through the future versioned engine boundary.

It layers on:

- [ENGINE_JOB_CONTRACT.md](ENGINE_JOB_CONTRACT.md) for v1 request/result/error shapes;
- [ENGINE_JOB_LIFECYCLE.md](ENGINE_JOB_LIFECYCLE.md) for deadline, cancellation,
  publication, and cleanup semantics.

The current config-first production pipeline remains an operator/trusted-input
workflow. Issue #338 does not silently turn arbitrary repository paths or
current YAML configuration into a public upload API.

The reusable implementation is
\`src/pipeline/engine_input_safety.py\`.

## 1. Security boundary

An anonymous or otherwise untrusted caller must not be able to convert one
engine request into unbounded work or arbitrary host filesystem/network access.

For a future untrusted one-job adapter:

1. the caller supplies PDF bytes or an already-staged engine reference;
2. the adapter stages the input under a worker-owned input root;
3. the engine preflights path, byte, PDF, page, and predicted render bounds;
4. rejected input returns a structured v1 \`EngineError\` before page rendering
   or model inference where feasible;
5. accepted work executes inside the worker/container resource boundary;
6. only artifacts advertised by a terminal non-failure \`JobResult\` are public.

Authentication, accounts, billing, global rate limiting, IP reputation, queue
fairness, and cross-job scheduling remain service/control-plane concerns. They
do not replace these per-job bounds.

## 2. Current-runtime audit

The current repository has useful safety pieces, but its config-first path was
not designed to accept arbitrary public uploads.

| Area | Current behavior | Issue #338 consequence |
| --- | --- | --- |
| PDF byte loading | \`PipelineOrchestrator._run_pdf_to_images()\` calls \`Path.read_bytes()\` before opening PyMuPDF | Untrusted adapters must enforce a byte cap before the current unbounded read pattern |
| PDF parsing | PyMuPDF opens the full source bytes and exposes \`page_count\` | Parser errors/encryption need deterministic public-safe mapping |
| Rendering | \`render_pdf_to_memory()\` calls \`page.get_pixmap()\` and accumulates rendered pages in a list | Predicted dimensions/per-page/total pixels must be bounded before rendering |
| Page selection | Existing helpers validate selected page indices | Untrusted execution additionally needs document-page and selected-page ceilings |
| Input paths | Config accepts operator-provided paths | Public jobs must resolve only inside a worker-owned input root and reject traversal/URL-like references |
| Symlinks | No general public-input symlink policy exists | Untrusted input defaults to no symlink traversal |
| Output names | v1 exposes caller \`output_name\` | It is a filename stem only, not a path |
| Artifact paths | v1 artifact \`relative_path\` already rejects absolute/\`..\` traversal | Preserve this existing contract |
| Child processes | Heavy stages already use process boundaries in several paths | #337 termination semantics still require worker/process-group integration |
| Runtime downloads | Production model/runtime assets are materialized explicitly during build/preparation; runtime resolvers verify local assets | Ordinary job execution must remain offline and fail if required local assets are unavailable |
| Logs | Current internal pipeline logs can contain full local paths and child output | \`pipeline.log\` is diagnostic, not a public caller response |
| Cleanup/publication | #337 defines attempt cleanup and states that internal path existence is not publication | Limit/input rejection is a failed attempt and must not publish partial final/review artifacts |

The direct PDF renderer also hashes the source and records provenance. That is
useful internal evidence, but a future public result must not copy internal
absolute paths into public metadata.

## 3. Default per-job policy

\`JobSafetyPolicy\` provides concrete defaults and allows a worker/service
adapter to choose stricter values for its deployment.

| Limit | Default |
| --- | ---: |
| PDF bytes | 256 MiB |
| document pages | 500 |
| selected pages | 200 |
| rendered width per page | 12,000 px |
| rendered height per page | 12,000 px |
| rendered pixels per page | 64,000,000 |
| total rendered pixels for selected pages | 1,000,000,000 |
| attempt-local temp/intermediate/output disk | 16 GiB |
| symlink input traversal | rejected |
| worker-owned input root | required |

These values are hard rejection ceilings, not a claim that every job below
them fits every machine. A deployment may lower them without changing the v1
wire schema. Raising them is an operational/security decision and does not
remove the worker/container hard-resource requirements below.

The page/pixel limits are calculated from PyMuPDF page geometry and the actual
requested render DPI before \`get_pixmap()\`. They bound output amplification,
but they cannot prove that a pathological PDF has cheap parsing/rendering
complexity.

## 4. PDF preflight contract

\`validate_local_pdf()\` performs the reusable preflight.

### 4.1 Path/reference checks

For an untrusted \`local_path\` request:

- URL-like references such as \`http:\`, \`https:\`, \`file:\`, or other URI
  schemes are rejected;
- control characters and explicit \`..\` path components are rejected;
- the resolved file must remain inside a worker-owned \`allowed_root\`;
- symlink components are rejected by default;
- the final opened object must be a regular file;
- the adapter should make the staged input root immutable to the untrusted
  caller before validation begins.

The implementation also uses \`O_NOFOLLOW\` where available for the final file.
Filesystem validation alone cannot eliminate every time-of-check/time-of-use
race if another actor can mutate parent directories concurrently. That is why
the worker-owned, non-attacker-writable staging root is part of the contract.

\`engine_ref\` is an opaque engine-owned identity. Resolving it to storage is
an adapter responsibility, but the resolved object must enter the same bounded
PDF validation path before rendering.

### 4.2 Bounded byte read

The input is opened as a regular file and read incrementally up to
\`max_pdf_bytes\`; SHA-256 is computed during the same read. A size observed
above the configured limit rejects the job before PyMuPDF parsing.

The bounded preflight intentionally avoids the current
\`Path.read_bytes()\`-before-validation pattern for untrusted inputs.

### 4.3 PDF validity and encryption

The following are deterministic non-retryable input failures:

- unreadable/malformed/non-PDF content;
- zero-page PDF;
- password-protected/encrypted PDF.

Issue #338 does not add password handling or attempt to decrypt caller input.
Supporting encrypted input later would require a separate explicit credential
and secret-handling contract.

### 4.4 Page and render-plan limits

Before rendering page content, preflight validates:

- total document page count;
- selected page count;
- selected page indices;
- predicted width and height at the requested DPI;
- pixels for every selected page;
- total predicted pixels across the selected page set.

The validated metadata contains source basename, SHA-256, byte size, page
count, selected pages, render DPI, dimensions/pixel counts, and total render
pixels. It intentionally omits the worker's absolute local path.

Embedded object/image dimensions inside a PDF are not treated as a sufficient
security metric: vector content, compressed streams, and other PDF structures
can still be expensive. The rendered-output bounds plus hard worker limits are
the security boundary.

## 5. Output names and path construction

The v1 \`config_overrides.output_name\` is a caller-visible filename stem only.

It must be non-empty and must not contain:

- \`/\` or \`\\\`;
- \`.\` or \`..\` as the whole value;
- ASCII control characters;
- more than 200 UTF-8 bytes.

The engine/adapter chooses directories. A caller cannot use \`output_name\` to
select an absolute path, parent directory, model path, run root, temp root, or
other internal location.

Existing v1 artifact descriptors retain their separate containment rule:
\`relative_path\` artifacts cannot be absolute and cannot contain \`..\`.

## 6. Structured rejection categories

Preflight failures map into the existing v1 \`EngineError\` envelope.

| Condition | Category | Code | Retryable |
| --- | --- | --- | --- |
| malformed/unreadable PDF | \`input\` | \`input_pdf_invalid\` | false |
| encrypted/password PDF | \`input\` | \`input_pdf_encrypted\` | false |
| missing/non-regular input | \`input\` | \`input_pdf_unavailable\` | false |
| URL/traversal/symlink/outside-root input | \`input\` | \`input_reference_not_allowed\` | false |
| invalid request page list | \`invalid_request\` | \`request_pages_invalid\` / \`request_page_out_of_range\` | false |
| unsafe output stem | \`invalid_request\` | \`output_name_invalid\` | false |
| input bytes exceed policy | \`resource\` | \`input_pdf_bytes_limit_exceeded\` | false |
| document/selected pages exceed policy | \`resource\` | \`input_pdf_page_limit_exceeded\` / \`input_pdf_selected_pages_limit_exceeded\` | false |
| render dimension exceeds policy | \`resource\` | \`input_pdf_render_dimension_limit_exceeded\` | false |
| page pixels exceed policy | \`resource\` | \`input_pdf_render_pixels_limit_exceeded\` | false |
| total render pixels exceed policy | \`resource\` | \`input_pdf_total_render_pixels_limit_exceeded\` | false |
| attempt storage exceeds policy | \`resource\` | \`attempt_disk_budget_exceeded\` | false |

Configured limit rejection is a non-success engine result. It must not be
automatically retried unchanged and must not publish partial final/review
artifacts.

## 7. Public-safe versus diagnostic information

\`InputSafetyError.to_engine_error()\` maps preflight failure into the v1
envelope.

Public responses may contain:

- stable category/code;
- bounded \`public_message\`;
- actionability/retryability;
- validated metadata intentionally selected for the result contract.

Public responses must not contain:

- absolute host/container paths;
- arbitrary caller filenames beyond the intentional caller-visible reference
  or sanitized basename;
- parser stack traces;
- child command lines/environment;
- model/cache locations;
- internal run/temp directory names;
- raw \`pipeline.log\`.

Precise parser exceptions, internal paths, limits observed, stage names, and
stack traces may exist in trusted diagnostics/\`debug_context\`.
\`EngineError.to_dict()\` continues to omit \`debug_context\` by default.

## 8. Runtime network and model assets

Ordinary one-job execution is an offline contract.

The canonical image/build path already materializes maintained HOMR, historical
Stage-E HOMR, Real-ESRGAN, and the production CNN assets during image
construction/preparation. Runtime resolvers verify local materialized assets
and fail when required assets are missing.

\`src.common.model_artifacts materialize\` is an explicit operator/build action
and may use the network. A job executor must not invoke it, HOMR initialization
downloads, arbitrary URLs, or equivalent download helpers to make a job
succeed.

A service worker should run with outbound network disabled by default. If a
third-party dependency unexpectedly attempts a download, that attempt should
fail and become a dependency/internal failure rather than granting the PDF job
network access.

Any externally supplied OMR/MMR/model assets must likewise be staged and
verified before accepting untrusted jobs.

## 9. Worker/container requirements

Python-level PDF validation is necessary but not sufficient. Parsing itself and
accepted PDF content can still consume unexpected CPU/RAM, and native
PDF/CUDA/runtime code must be treated as part of the untrusted-input boundary.

A worker that accepts arbitrary PDFs must provide, outside the pure helper:

- a disposable one-job attempt workspace;
- input staged under a worker-owned root and made read-only/non-attacker-writable
  during execution;
- a non-root process where practical;
- no Docker socket or unrelated host filesystem mounts;
- read-only runtime/model assets;
- bounded CPU and RAM;
- bounded GPU placement/VRAM impact appropriate to the deployment;
- a hard attempt deadline in addition to #337 cooperative checkpoints;
- a bounded writable filesystem/volume for temp/intermediate/final staging;
- process-group/container termination for hung children;
- outbound network disabled for ordinary jobs;
- quarantine/deletion of the attempt workspace after hard termination.

The engine exposes \`max_attempt_disk_bytes\` and
\`enforce_attempt_disk_budget()\` as an in-process hook. A filesystem/container
quota is still the hard backstop because a killed or compromised process cannot
be trusted to call the hook.

The engine does not promise cross-job fairness or isolation. A service/worker
pool must ensure one job cannot read another job's workspace or use unbounded
shared resources.

## 10. Pathological/decompression amplification

Byte/page/pixel checks reduce common amplification vectors but do not fully
bound PDF parser/render complexity. Examples include deeply nested objects,
compressed streams, pathological vector content, or native-library edge cases.

Therefore:

- preflight occurs inside the same constrained worker/container trust boundary;
- rendering/inference is never relied upon as a validator;
- deadline/CPU/RAM/disk limits remain mandatory after preflight success;
- hard worker termination is a valid safety backstop;
- a hard-killed attempt is non-success even if partial files remain.

No limit bypass may silently switch render DPI, skip requested pages, reduce
model quality, or alter detector/MMR semantics merely to obtain a successful
result.

## 11. Cleanup and publication

#337 remains authoritative for cleanup/publication.

For an Issue #338 rejection:

- do not launch unnecessary GPU/model inference after a deterministic preflight
  failure;
- do not advertise final/review artifacts;
- best-effort delete engine-owned staging/temp files;
- keep only bounded diagnostics according to trusted operator policy;
- never delete immutable caller/source inputs outside the engine-owned attempt
  workspace;
- if the process is hard-killed, the outer worker owns later
  quarantine/deletion.

Internal file existence is not publication.

## 12. Implementation status

Issue #338 intentionally adds the reusable validation/policy layer without
rewiring the current production \`run_pipeline()\` execution path.

Implemented now:

- bounded local PDF byte read and SHA-256;
- malformed/encrypted PDF classification;
- page-selection and pre-render dimension/pixel limits;
- validated metadata without absolute paths;
- local path/root/traversal/URL/symlink checks;
- caller \`output_name\` filename-stem validation;
- attempt-disk budget hook;
- v1 \`EngineError\` mapping;
- focused tests for the implemented behaviors.

Still owned by a future production \`JobExecutor\`/worker adapter:

- invoking this preflight before current PDF rendering;
- applying the disk hook throughout attempt writes;
- mapping terminal failures into a concrete \`JobResult\`;
- hard CPU/RAM/VRAM/filesystem/container controls;
- outbound-network policy enforcement at worker/container level;
- process-group termination integration from #337.

Those integrations must preserve the current detector/MMR/numbering accuracy
contract and should receive runtime/GPU validation when they actually change
the production execution path.
