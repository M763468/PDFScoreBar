# Repository Surface Inventory

Issue #230 inventories the repository surface after the usability, correction-workflow,
documentation, service-readiness, and Makefile cleanups. This document is the durable handoff to
Issue #100; it does not make historical or experimental paths part of the public user interface.

Inventory baseline: `develop` after PR #377 (`a924b737e23d3bc43dac2211e8f60071d7a9245f`).

## Classification

- **KEEP** — maintained repository surface. This includes runtime, validation, current
  documentation, developer tooling, or machine contracts that should remain available in the
  current repository. KEEP does not automatically mean "public end-user API".
- **ARCHIVE** — retained for reproducibility, forensic history, or scoped reference. It must not be
  advertised as the normal user/developer entrypoint.
- **REMOVE** — no maintained runtime/reproduction role is currently identified. Removal is expected
  after a focused reference/provenance check; this inventory does not bulk-delete it.
- **UNDECIDED** — current evidence is insufficient for safe removal. A narrow follow-up audit is
  required.

Issue-numbered names alone are not a removal criterion. A test, fixture, config, or tool can remain
KEEP/ARCHIVE when it protects a current contract or is the accepted reproduction path.

For the repository slices investigated by Issue #230, there are no remaining classification blockers:
items that were initially UNDECIDED have either been assigned a concrete KEEP/ARCHIVE/REMOVE-candidate
disposition below or reduced to implementation-time reference checks. UNDECIDED remains part of the
classification vocabulary for future newly discovered assets; it is not an outstanding #230 result.

## Current supported boundary

### Operator/runtime entrypoint

The current supported runtime is config-first:

```bash
make run-pipeline CONFIG=<config.yaml>
```

The canonical runtime image is `pdfscore_pipeline_gpu`; current environment details are owned by
`docs/ENVIRONMENTS.md`.

There is currently no installed `pdfscorebar` console script in `pyproject.toml`. The old
`pdfscorebar run/correct/apply-corrections` direction in Issue #226-#229 design records is therefore
not a current CLI contract and must not be used to decide what files are public.

### Output and correction surface

The final/review/debug concepts remain valid, but callers should depend on semantic artifacts rather
than internal run-directory details.

- Normal correction operation is the config-first review-package flow documented in
  `docs/manual_correction_review_package.md`.
- The supported user GUI is `tools/review_correction/server.py`; it starts from
  `review/manual_correction_input.json` and enforces the same-package handoff. See
  `docs/USER_CORRECTION_BOUNDARY.md` for its separation from GT/developer tooling.
- Issue #383 retired the legacy arbitrary-path manual-config builder; the supported GUI route begins
  from the package-local review handoff above.
- Final output remains the clean score-numbered PDF; review/debug geometry and correction provenance
  do not belong in the final artifact.

### Versioned engine boundary

The v1 `JobRequest`, `JobResult`, `ProgressEvent`, `EngineError`, artifact descriptors, and
`CorrectionSet` schemas are maintained machine-facing surface. The reference
`src.pipeline.engine_executor.PipelineJobExecutor` now exposes the v1 request/result boundary over
the config-first pipeline.

Direct execution of v1 `CorrectionSet` records is not connected by that reference executor; the
current review-package/apply flow remains the concrete correction execution path.

### Service/control-plane boundary

Future HTTP/API, queue, database, object-store, authentication, billing, persistence, and other
service/control-plane implementation concerns are not repository-surface requirements for
PDFScoreBar. `docs/FUTURE_SERVICE_ARCHITECTURE.md` deliberately permits those concerns to live in
another repository.

## Top-level inventory

| Area | Classification | Surface role | Action / boundary |
| --- | --- | --- | --- |
| `README.md`, `AGENTS.md`, `pyproject.toml` | KEEP | repository/runtime metadata and operating rules | Keep concise and current. Do not add a console-script contract until one is implemented. |
| `Makefile` | KEEP | maintained runtime/developer/validation entrypoint | Use `docs/MAKEFILE_SURFACE.md`; do not re-audit #369 here. Historical Issue #120 targets are reproduction surface, not general entrypoints. |
| `.github/**` | KEEP | CI, Issue/PR templates | Keep while referenced by current repository workflow. |
| `.agents/**`, `.gemini/GEMINI.md` | KEEP | repository developer/agent tooling | Not end-user API. Root Makefile currently exposes several `.agents/skills/**` helpers. |
| `Dockerfile`, `docker/**` | KEEP | canonical runtime build and runtime contract | Current Docker surface. |
| `Dockerfile.groundingdino` | REMOVED by #382 | retired zero-shot model experiment environment | The failed GroundingDINO experiment remains recoverable from history; the tracked experiment Dockerfile is no longer repository surface. |
| `Dockerfile.homr` | ARCHIVE | historical/specialized HOMR environment | Canonical pipeline uses `Dockerfile`; do not advertise this as normal runtime. |
| `src/**` | KEEP | production/library implementation | Treat as maintained until a module-level dependency audit proves a subtree obsolete. Do not infer removability from old naming alone. |
| `tests/**` | KEEP | current correctness/contract regression suite | Issue-numbered tests may still guard current behavior and remain KEEP unless their contract is explicitly retired. |
| `tests_legacy/**` | REMOVED by #380 | retired second test surface | The three useful thin-barline behavior cases were migrated into normal `tests/`; the fixed-port/sleep/static-JS GT-GUI check was retired as brittle/redundant rather than normalized into maintained coverage. |
| `configs/**` | mixed KEEP/ARCHIVE | runtime, smoke, evaluation, reproduction configs | Current production/smoke/service/review configs KEEP; Issue/experiment snapshots ARCHIVE. See config detail below. |
| `models/**` | KEEP | versioned model manifests | Keep manifests/provenance. Large model bytes remain outside Git and are staged through the documented model-artifact mechanism. |
| `scripts/**` | mixed KEEP/ARCHIVE | maintained automation plus scoped validators | Current Docker/PR/validation scripts KEEP; Issue-specific validators are ARCHIVE unless still part of a maintained gate. |
| `tools/**` | mixed KEEP/ARCHIVE/REMOVE candidate | reusable utilities, reproduction tooling, and accumulated one-off analysis | Current utilities and explicit reproduction tools remain; scripts already established as legacy by #38/#45/#96 or superseded by current source should be retired rather than kept for compatibility. |
| `experiments/**` | ARCHIVE by default, with explicit runtime exceptions | experiments, comparison, reproduction, prototypes | Never assume the whole tree is non-runtime. `experiments/models/eval_omr_dln.py` is currently a KEEP exception because the canonical dense route launches it directly; other experiment content remains ARCHIVE/remove-candidate by evidence. |
| `data/**` | KEEP current evaluation evidence + ignored local data | canonical GT/baselines and operator-owned ignored data | `data/evaluation2/**` remains the tracked canonical validation/GT surface; pre-evaluation2 tracked training/evaluation/workbench trees were removed by #381. |
| `graphify-out/**` | KEEP (developer/generated) | optional repository navigation | Keep only the portable graph/report/wiki/manifest set while provenance is fresh; never use it as source of truth over source/tests. |
| `logs/README.md` | KEEP | generated-evidence placement policy | Runtime logs themselves stay ignored. Historical path prose should be corrected when it points to retired files/tools. |
| `artifacts/.gitkeep` | KEEP | local generated-artifact root | Artifacts are ignored/generated and are not public result API. |
| `external/**`, `.gitmodules` | REMOVED by #382 | retired third-party experiment surface | The tracked OEMER runner/submodule, FSRCNN blob, stale external README, and the now-empty `.gitmodules` surface were removed. Ignored operator caches/clones are not repository API. |
| `setup_scripts/**` | REMOVED by #382 | retired local bootstrap/download helpers | User-specific Serena/container/bootstrap and WSL-specific dataset download helpers were removed; current setup guidance is owned by maintained repository docs/Makefile/runtime tooling. |

## Config inventory

### KEEP — current machine/runtime contracts

At minimum:

- `configs/dense_full_pipeline.yaml` — canonical selected production configuration;
- `configs/smoke_test.yaml` — production-representative smoke;
- `configs/service_readiness_smoke.yaml` — one-job compatibility/container smoke;
- `configs/review_manual_correction_package_example.yaml` — current review-package example;
- `configs/detector_profiles/**` and `configs/detector_routes/**` while referenced by current
  production/reproduction contracts;
- configuration fixtures that are directly consumed by maintained tests/validation.

### ARCHIVE — scoped reproduction/evidence

Issue- or experiment-specific configs remain only when they are the accepted reproduction/config
record. Examples include `issue120_*`, `issue333_*`, `issue43_*`, evaluation comparison configs,
and `configs/cnn_barline_runs/**`.

They are not default runtime choices merely because they are checked in.

### Removed legacy dense-container key

Issue #379 removed the inert `container_name: sr_eval_gpu_exp` setting from
`configs/dense_full_pipeline.yaml`. The #230 audit had already established that tracked `src/**`
contained no `container_name` consumer; the cleanup therefore removes stale configuration rather
than changing detector routing or container selection.

## Data inventory

Tracked data is not equivalent to generated runtime output.

### KEEP / validation-reference

`data/evaluation2/**` contains the canonical barline GT, `staff_units.json`, and the retained
`golden_baseline_eval2_bc23deb/**` evidence used by validation/reproduction work. This is not an
end-user input/output API, but it is repository evidence and must not be bulk-deleted as "artifact
cleanup".

### Retired pre-evaluation2 tracked surface

Issue #381 removed the old tracked `data/training/**`, `data/evaluation/**`, and
`data/workbench/**` trees after `data/evaluation2/**` became the canonical retained GT/evaluation
surface. The standalone PDF conversion CLI now requires explicit input/output paths, the stale
`src/ml_detector` demo path was removed, and current temporary-work guidance points to ignored
`tmp/`.

Historical annotation bytes remain recoverable from Git history; do not recreate the retired trees
as current GT/workbench locations. Large operator datasets/images remain ignored and should not be
added to the public repository without an explicit retention decision.

## Documentation inventory

Use `docs/DOCUMENTATION_INVENTORY.md` as the specialized audit rather than repeating the full
document-by-document classification here.

For repository-surface purposes:

- canonical/current and current/reference docs are KEEP;
- `docs/FUTURE_SERVICE_ARCHITECTURE.md` is KEEP as an explicitly future responsibility boundary;
- Issue/refactor docs are ARCHIVE only when they retain a scoped contract or unique evidence;
- completed task-control/handoff prose with no unique durable content is REMOVE under the #280
  retirement rule;
- `docs/refactors/issue226/**` through `issue229/**` are historical/scoped design records, not a
  second current CLI/runtime source of truth;
- `docs/manual_correction_review_package.md` is the current correction operating guide.

Issue #230 also found stale current-facing wording left after PR #376: the documentation index and
durable documentation inventory still described the production executor adapter as not yet wired.
Those statements should be updated in this branch to match the current
`PipelineJobExecutor` boundary.

## Makefile inventory

Issue #369 / PR #377 already completed the target-level audit. Its result is authoritative for this
scope:

- maintained runtime/developer/validation targets stay KEEP;
- Issue #120 reproduction targets stay ARCHIVE/reproduction surface even when retained in the root
  Makefile;
- Stage-E reproduction is intentionally moved behind `tools/issue120/Makefile.stage_e.mk`;
- stale `check-consistency` and `setup-worktree` targets were removed;
- `make check-makefile` is the lightweight reference gate.

#230 must not duplicate that audit.

## Production-owned exceptions under experiment paths

Repository placement does not override actual runtime dependency. The current canonical dense route
in `src/pipeline/detection/current_support_worker.py` directly launches:

```text
experiments/models/eval_omr_dln.py
```

and `docker/runtime_contract.py` fingerprints `experiments/models` as runtime-sensitive source.

Therefore `experiments/models/eval_omr_dln.py` is **KEEP / current runtime dependency** despite living
under `experiments/**`. Issue #100 must either carry this file into the minimal mainline or first
move the maintained OMR-DLN entrypoint into `src/**` and update the runtime contract/caller
coherently. It must not be omitted merely because its path begins with `experiments/`.

This is intentionally a narrow exception. Historical GroundingDINO, YOLO-World, and other OMR-DLN
comparison scripts under `experiments/models/**` do not become current runtime surface merely
because the directory is fingerprinted.

## Tools and experiments

This is the largest remaining mixed surface and should not be handled as one deletion PR.

### KEEP examples

- `tools/review_correction/server.py` — user correction application boundary;
- `tools/gt_relabel_gui/**` — GT/developer tooling and shared manual UI assets;
- `tools/movement_boundary_review.py` and current movement-boundary helpers;
- `tools/check_makefile_references.py`;
- maintained verification/model/review utilities explicitly referenced from current docs, tests,
  Makefile, or CI.

### ARCHIVE examples

- `tools/issue120/**` — retained reproduction surface;
- other Issue-specific tools whose accepted result cannot be reproduced or understood without the
  retained tool;
- experiment code with explicit provenance and continuing comparison value.

### Resolved legacy candidates

Issue #383 retired the first confirmed legacy-tool batch:

- the arbitrary-path manual-config builder;
- the deprecated `tools/run_full_pipeline.py` entrypoint superseded by `src.pipeline.main`;
- the three old SR measurement helpers that hard-coded `sr_eval_gpu` / `/opt/venv_sr`.

The earlier broad tools audit (#96), GT-tool audit (#38), and CNN script cleanup (#45) remain the
accepted classification basis. Explicitly maintained utilities such as `tools/verification/**`, the
current `tools/gt_relabel_gui/**` flow, movement-boundary tooling, Makefile reference checks, and
retained Issue #120 reproduction tooling remain KEEP/ARCHIVE according to their current contracts.

Later legacy-tool cleanup can use the same accepted classifications plus a mechanical inbound-
reference check; it should not recreate another repository-wide historical inventory.

A cleanup PR should still perform a mechanical inbound-reference check before deleting a concrete
batch, but that check is deletion validation, not another open-ended classification investigation.

## Legacy environment/runtime candidates

### Removed legacy SR interpreter fallback

Issue #379 removed the host-side `sr_eval_gpu` probe and `/opt/venv_sr/bin/python` fallback from
`src/pipeline/core/python_env.py`. Maintained heavy-step selection now recognizes only the unified
`pdfscore_pipeline_gpu` environment and `/opt/venv_pipeline/bin/python`, while retaining the
existing explicit `PIPELINE_PYTHON` override behavior when no maintained heavy-step environment is
selected.

This completes the #230 decision for that compatibility path. Historical tools that hard-code the
former environment remain separate #383 cleanup targets; they are not a reason to restore the
runtime fallback.

### Retired bootstrap and third-party experiment surface

Issue #382 completed this cleanup:

- `setup_scripts/**` was removed;
- `Dockerfile.groundingdino` was removed;
- the tracked OEMER runner/submodule and its only `.gitmodules` entry were removed;
- `external/models/FSRCNN_x2.pb` and stale `external/README.md` were removed;
- `Dockerfile.homr` was explicitly retained as **ARCHIVE/KEEP** for isolated/historical HOMR
  evaluation when an Issue requires that environment.

The negative GroundingDINO/FSRCNN and historical OEMER conclusions remain recoverable from Issue/PR/
commit history; the removed files no longer form active-looking repository surface.

## Need for local-state investigation

No additional workstation/local-state survey is required to make the classifications above.
Current GitHub source, current durable docs, and completed Issue audits are sufficient to distinguish
the maintained surface from legacy compatibility. In particular, re-running local `git grep` for
facts already established above, checking whether an obsolete container happens to exist locally,
or checking whether ignored third-party clones are present would duplicate evidence without changing
the repository contract.

The behavior-sensitive interpreter cleanup was subsequently implemented in #379 with focused
interpreter-selection coverage and repository PR validation. Workstation-local existence of obsolete
containers/clones was not used as a repository-surface criterion.

## Boundary for Issue #100

Issue #100 should consume this inventory rather than infer "minimal" from directory size.

The initial minimal-mainline KEEP set should include:

1. current runtime implementation and dependency/build metadata, including runtime dependencies that
   still live outside `src/**` such as `experiments/models/eval_omr_dln.py` until that entrypoint is
   migrated into `src/**`;
2. canonical runtime/config/model-manifest inputs;
3. versioned engine/artifact/correction contracts and their tests;
4. current output/review/correction semantics and operating documentation;
5. current validation/CI required to establish those contracts;
6. selected GT/fixtures/reproduction assets that are necessary to prove maintained behavior;
7. developer tooling only where it is intentionally part of maintaining the repository.

Issue #100 should not automatically migrate:

- arbitrary historical Issue docs;
- active-looking one-off analysis scripts;
- experiment directories without continuing reproduction value;
- ignored logs/artifacts;
- old environment/bootstrap routes;
- service/control-plane implementation that belongs outside the engine repository.

## Completed cleanup slices

The #230 follow-up implementation line is complete:

1. **#379 / PR #384** — removed legacy SR-container/interpreter compatibility and the inert dense
   container config key while preserving the canonical runtime and explicit interpreter override.
2. **#380 / PR #385** — migrated useful thin-barline behavior coverage into `tests/**` and retired
   the separate `tests_legacy/**` surface.
3. **#381 / PR #386** — retired pre-evaluation2 tracked data/default paths while preserving
   `data/evaluation2/**` and keeping retired local data trees ignored.
4. **#382 / PR #387** — retired obsolete bootstrap and abandoned GroundingDINO/OEMER/FSRCNN tracked
   experiment surface while retaining `Dockerfile.homr`.
5. **#383 / PR #388** — retired the confirmed legacy manual-config/full-pipeline/SR-measurement
   entrypoints while retaining current utilities and explicit reproduction contracts.

## Issue #230 completion boundary

With #379-#383 merged and closed, Issue #230's decision work and its first concrete cleanup line are complete:

- the maintained runtime/output/correction/engine boundary is recorded;
- top-level repository surface is classified;
- initially ambiguous legacy slices have concrete dispositions;
- completed specialist audits are incorporated rather than repeated;
- #100 has an explicit minimal-mainline handoff;
- behavior-changing and deletion work is separated into scoped follow-up Issues.

The actual deletion/runtime-compatibility changes were implemented in #379-#383 rather than by
expanding #230 into an implementation umbrella. Future cleanup should continue to use the removal
rule below and create a focused implementation boundary only when new concrete candidates are found.

## Removal rule

A repository item may move from UNDECIDED/ARCHIVE to REMOVE only when:

1. no maintained runtime/test/CI/Makefile/current-doc route depends on it;
2. it is not the sole reproduction mechanism for an accepted result;
3. unique durable decisions/provenance are recoverable from current source/tests/docs or
   Issue/PR/commit history;
4. removal does not silently change production behavior;
5. surviving references are updated in the same cleanup.

This deliberately rejects "keep it because it used to exist" as well as "delete it because it looks
old". The maintained contract and recoverable provenance decide.
