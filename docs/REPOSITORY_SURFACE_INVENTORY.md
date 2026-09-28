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
- The supported GUI route starts from `review/manual_correction_input.json` and enforces the
  same-package handoff.
- `tools/gt_relabel_gui/manual_config_builder.py` is a legacy/developer helper that accepts arbitrary
  paths; it is not the normal correction workflow.
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
| `Dockerfile.groundingdino` | ARCHIVE | model experiment environment | Not canonical runtime. Retain only while its experiment/reproduction value remains. |
| `Dockerfile.homr` | ARCHIVE | historical/specialized HOMR environment | Canonical pipeline uses `Dockerfile`; do not advertise this as normal runtime. |
| `src/**` | KEEP | production/library implementation | Treat as maintained until a module-level dependency audit proves a subtree obsolete. Do not infer removability from old naming alone. |
| `tests/**` | KEEP | current correctness/contract regression suite | Issue-numbered tests may still guard current behavior and remain KEEP unless their contract is explicitly retired. |
| `tests_legacy/**` | UNDECIDED | legacy tests outside normal `make test` path | Narrow audit. If no unique maintained contract remains, remove rather than keeping a second test surface. |
| `configs/**` | mixed KEEP/ARCHIVE | runtime, smoke, evaluation, reproduction configs | Current production/smoke/service/review configs KEEP; Issue/experiment snapshots ARCHIVE. See config detail below. |
| `models/**` | KEEP | versioned model manifests | Keep manifests/provenance. Large model bytes remain outside Git and are staged through the documented model-artifact mechanism. |
| `scripts/**` | mixed KEEP/ARCHIVE | maintained automation plus scoped validators | Current Docker/PR/validation scripts KEEP; Issue-specific validators are ARCHIVE unless still part of a maintained gate. |
| `tools/**` | mixed KEEP/ARCHIVE/UNDECIDED | reusable utilities, reproduction tooling, and accumulated one-off analysis | Keep supported utilities; retain explicit reproduction tools as ARCHIVE; audit ad-hoc root/debug scripts in small domain slices. |
| `experiments/**` | ARCHIVE by default | experiments, comparison, reproduction, prototypes | Never public runtime and never an implicit production dependency. Remove one-off content after provenance/results are recoverable. |
| `data/**` | mixed KEEP/ARCHIVE/UNDECIDED | GT, committed fixtures/baselines, and old workspace scaffolding | Canonical GT/baseline evidence is retained; do not treat tracked evaluation evidence as disposable generated output. |
| `graphify-out/**` | KEEP (developer/generated) | optional repository navigation | Keep only the portable graph/report/wiki/manifest set while provenance is fresh; never use it as source of truth over source/tests. |
| `logs/README.md` | KEEP | generated-evidence placement policy | Runtime logs themselves stay ignored. Historical path prose should be corrected when it points to retired files/tools. |
| `artifacts/.gitkeep` | KEEP | local generated-artifact root | Artifacts are ignored/generated and are not public result API. |
| `external/**`, `.gitmodules` | UNDECIDED | third-party/reproduction assets | Current production does not use this directory as a generic public dependency boundary. Audit the retained OEMER submodule, legacy FSRCNN blob, and stale README claims together. |
| `setup_scripts/**` | REMOVE candidate | old local Serena/container bootstrap | Contains user-specific absolute paths and the old `pdf_score_dev_gpu` container contract; conflicts with current `AGENTS.md`/ENVIRONMENTS guidance. Verify no remaining reference, then retire. |

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

### UNDECIDED / cleanup candidate

`configs/dense_full_pipeline.yaml` still contains:

```yaml
container_name: sr_eval_gpu_exp
```

The current canonical runtime is `pdfscore_pipeline_gpu`. Before removing this key, confirm whether
the active code reads it or whether it is inert legacy configuration. If removal can affect runtime,
handle it in a focused implementation PR with the validation required by
`docs/dev/VALIDATION_POLICY.md`.

## Data inventory

Tracked data is not equivalent to generated runtime output.

### KEEP / validation-reference

`data/evaluation2/**` contains the canonical barline GT, `staff_units.json`, and the retained
`golden_baseline_eval2_bc23deb/**` evidence used by validation/reproduction work. This is not an
end-user input/output API, but it is repository evidence and must not be bulk-deleted as "artifact
cleanup".

### UNDECIDED

The smaller `data/training/**`, `data/evaluation/**`, and `data/workbench/**` surfaces predate the
current evaluation2 discipline and include old annotation/workspace scaffolding. Audit consumers
before deciding whether to retain fixtures, move durable GT, or retire the remainder.

Large operator datasets/images remain ignored and should not be added to the public repository
without an explicit retention decision.

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

## Tools and experiments

This is the largest remaining mixed surface and should not be handled as one deletion PR.

### KEEP examples

- `tools/gt_relabel_gui/**` — current correction/GT GUI implementation;
- `tools/movement_boundary_review.py` and current movement-boundary helpers;
- `tools/check_makefile_references.py`;
- maintained verification/model/review utilities explicitly referenced from current docs, tests,
  Makefile, or CI.

### ARCHIVE examples

- `tools/issue120/**` — retained reproduction surface;
- other Issue-specific tools whose accepted result cannot be reproduced or understood without the
  retained tool;
- experiment code with explicit provenance and continuing comparison value.

### Legacy/developer example

`tools/gt_relabel_gui/manual_config_builder.py` remains available for arbitrary-path one-page
development use but is not the supported review-package route. Keep it out of user-facing
instructions. A later cleanup may remove it once no maintained developer workflow needs it.

### UNDECIDED bulk area

The many root-level `analyze_*`, `debug_*`, `visualize_*`, `probe_*`, one-off batch scripts, and
`experiments/legacy/**` cannot safely be classified from names alone. Audit them by domain/Issue,
checking:

1. whether current source/tests/Makefile/CI import or invoke them;
2. whether a current doc advertises them;
3. whether they are the sole reproduction path for an accepted result;
4. whether unique results/rationale are already recoverable from Issue/PR/commit/history;
5. whether reusable logic should be promoted before deletion.

If none apply, REMOVE and rely on Git history instead of retaining an active-looking script.

## Legacy environment/runtime candidates

### `sr_eval_gpu` fallback

`src/pipeline/core/python_env.py` still probes `sr_eval_gpu` and can select
`/opt/venv_sr/bin/python` after the canonical `pdfscore_pipeline_gpu` path.

This is a runtime behavior change if removed, so #230 should not delete it as documentation cleanup.
A focused follow-up should first prove that maintained entrypoints no longer require the fallback,
then remove it with targeted tests and the applicable runtime validation.

### Old bootstrap scripts

`setup_scripts/setup.sh` and `setup_scripts/start.sh` hard-code
`/home/masaki_muramatsu/ws_PDFScoreBar` and start a Serena server. `setup_scripts/check_container.sh`
targets `pdf_score_dev_gpu`, which is not the maintained runtime container. These scripts should not
be presented as repository setup. They are REMOVE candidates after a repository-reference check.

### Extra model Docker/external surface

`Dockerfile.groundingdino`, `Dockerfile.homr`, `external/oemer/**`,
`external/models/FSRCNN_x2.pb`, and `.gitmodules` belong to older model/reproduction lines rather
than the canonical Docker contract. Audit them as one narrow third-party/environment slice before
removal so reproducibility and licensing/provenance are not accidentally discarded.

## Boundary for Issue #100

Issue #100 should consume this inventory rather than infer "minimal" from directory size.

The initial minimal-mainline KEEP set should include:

1. current runtime implementation and dependency/build metadata;
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

## Follow-up cleanup slices

Do not combine these into a single bulk deletion.

1. **Legacy runtime/config compatibility**
   - `src/pipeline/core/python_env.py`: `sr_eval_gpu` / `/opt/venv_sr` fallback;
   - `configs/dense_full_pipeline.yaml`: `container_name: sr_eval_gpu_exp`;
   - prove maintained entrypoints are independent before changing behavior.

2. **Legacy bootstrap and third-party environment surface**
   - `setup_scripts/**`;
   - `Dockerfile.groundingdino`, `Dockerfile.homr`;
   - `external/**` / `.gitmodules`;
   - update/remove stale external/setup documentation together.

3. **Tools/experiments retirement**
   - audit root one-off analysis/debug/visualization scripts in domain-sized batches;
   - preserve explicit reproduction tools and move any reusable logic before deletion.

4. **Legacy tests/data scaffolding**
   - `tests_legacy/**`;
   - pre-evaluation2 `data/training/**`, `data/evaluation/**`, `data/workbench/**`;
   - retain only unique current fixtures/contracts.

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
