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
| `Dockerfile.groundingdino` | REMOVE candidate | abandoned zero-shot model experiment environment | The accepted history records GroundingDINO as a negative experiment, the Dockerfile depends on an ignored local `external/grounding_dino` clone, and no current runtime/validation contract uses it. Git history is sufficient recovery. |
| `Dockerfile.homr` | ARCHIVE | historical/specialized HOMR environment | Canonical pipeline uses `Dockerfile`; do not advertise this as normal runtime. |
| `src/**` | KEEP | production/library implementation | Treat as maintained until a module-level dependency audit proves a subtree obsolete. Do not infer removability from old naming alone. |
| `tests/**` | KEEP | current correctness/contract regression suite | Issue-numbered tests may still guard current behavior and remain KEEP unless their contract is explicitly retired. |
| `tests_legacy/**` | REMOVE after test migration/replacement | tests excluded from normal `make test` | Do not retain a second test surface. Preserve the useful thin-barline behavioral cases in `tests/`; replace the brittle GT-GUI server check with a deterministic current test, then retire the legacy directory. |
| `configs/**` | mixed KEEP/ARCHIVE | runtime, smoke, evaluation, reproduction configs | Current production/smoke/service/review configs KEEP; Issue/experiment snapshots ARCHIVE. See config detail below. |
| `models/**` | KEEP | versioned model manifests | Keep manifests/provenance. Large model bytes remain outside Git and are staged through the documented model-artifact mechanism. |
| `scripts/**` | mixed KEEP/ARCHIVE | maintained automation plus scoped validators | Current Docker/PR/validation scripts KEEP; Issue-specific validators are ARCHIVE unless still part of a maintained gate. |
| `tools/**` | mixed KEEP/ARCHIVE/REMOVE candidate | reusable utilities, reproduction tooling, and accumulated one-off analysis | Current utilities and explicit reproduction tools remain; scripts already established as legacy by #38/#45/#96 or superseded by current source should be retired rather than kept for compatibility. |
| `experiments/**` | ARCHIVE by default | experiments, comparison, reproduction, prototypes | Never public runtime and never an implicit production dependency. Remove one-off content after provenance/results are recoverable. |
| `data/**` | mixed KEEP/REMOVE candidate | canonical GT/baselines plus superseded pre-evaluation2 scaffolding | Keep `data/evaluation2/**`; retire the old training/evaluation/workbench tracked surface after removing its remaining legacy/default-path references. |
| `graphify-out/**` | KEEP (developer/generated) | optional repository navigation | Keep only the portable graph/report/wiki/manifest set while provenance is fresh; never use it as source of truth over source/tests. |
| `logs/README.md` | KEEP | generated-evidence placement policy | Runtime logs themselves stay ignored. Historical path prose should be corrected when it points to retired files/tools. |
| `artifacts/.gitkeep` | KEEP | local generated-artifact root | Artifacts are ignored/generated and are not public result API. |
| `external/**`, `.gitmodules` | REMOVE candidate | retired third-party experiment/reproduction surface | The retained OEMER runner/submodule and FSRCNN blob are not part of the current runtime. OEMER's checked-in runner contains stale path assumptions; the FSRCNN artifact belongs to a recorded failed experiment. Remove the tracked surface together with stale `external/README.md`; ignored operator caches/clones are not repository API. |
| `setup_scripts/**` | REMOVE candidate | old local bootstrap/download helpers | `setup.sh`/`start.sh` hard-code a user checkout path, `check_container.sh` targets obsolete `pdf_score_dev_gpu`, and the DeepScores downloader hard-codes `/mnt/d/datasets/DeepScoresV2`. None is a maintained repository setup contract; DeepScores provenance does not require retaining this machine-specific downloader. |

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

### REMOVE candidate — confirmed inert legacy key

`configs/dense_full_pipeline.yaml` still contains:

```yaml
container_name: sr_eval_gpu_exp
```

The current canonical runtime is `pdfscore_pipeline_gpu`. A current-source audit found no
`container_name` consumer anywhere under tracked `src/**`, and the targeted config/runtime tests
reviewed for this inventory do not reference `sr_eval_gpu_exp`. The generic YAML loader therefore
loads this key but no maintained source reads it. Treat it as inert legacy configuration and remove
it in a small config cleanup change; do not spend another local investigation re-proving whether the
key is consumed. Validate the eventual config edit according to `docs/dev/VALIDATION_POLICY.md`.

## Data inventory

Tracked data is not equivalent to generated runtime output.

### KEEP / validation-reference

`data/evaluation2/**` contains the canonical barline GT, `staff_units.json`, and the retained
`golden_baseline_eval2_bc23deb/**` evidence used by validation/reproduction work. This is not an
end-user input/output API, but it is repository evidence and must not be bulk-deleted as "artifact
cleanup".

### REMOVE candidates — pre-evaluation2 tracked surface

The current GT preparation documentation identifies `data/evaluation2/**` as the canonical GT
workflow. The older tracked surfaces can now be classified more narrowly:

- `data/workbench/**` contains only ignored-directory scaffolding. Current script-management rules
  already assign throwaway scratch work to ignored `tmp/`; retire the tracked workbench scaffold.
- `data/training/**` contains Jan-2026 annotation snapshots and old training-path scaffolding. The
  production pipeline imports `src.pdf_to_images` in-process with explicit config-owned input/output;
  the remaining `data/training/...` values in `src/pdf_to_images.py` are standalone CLI defaults, not
  production data contracts. Make that CLI explicit/neutral and retire the old tracked snapshots.
- `data/evaluation/**` contains the old single-page `page_003` GT. The remaining known source defaults
  point to legacy standalone routes (`external/oemer/run_omerer.py` and the `src/ml_detector` demo),
  while current detector validation is based on `evaluation2`. Retire this surface together with
  those legacy routes.

Exact old annotation bytes remain recoverable from Git history; no accepted current evaluation
contract requires keeping these directories active. Large operator datasets/images remain ignored
and should not be added to the public repository without an explicit retention decision.

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

### Resolved legacy candidates

`tools/gt_relabel_gui/manual_config_builder.py` is a REMOVE candidate. The maintained manual flow
starts from package-local `review/manual_correction_input.json`; the builder accepts arbitrary paths,
is not imported by the current server flow, and is mentioned by current documentation only to label
it legacy. It should not survive merely as backward-compatible public surface.

The earlier broad tools audit (#96), GT-tool audit (#38), and CNN script cleanup (#45) already did
the expensive historical classification work. Their durable placement rules now live in
`docs/SCRIPT_MANAGEMENT.md`; #230 should not recreate a second all-files inventory. Apply their
accepted classifications against current source:

- explicitly maintained directories/tools such as `tools/verification/**`, the current
  `tools/gt_relabel_gui/**` flow (excluding the legacy builder above),
  `tools/movement_boundary_review.py`, and `tools/check_makefile_references.py` remain KEEP;
- `tools/issue120/**` remains ARCHIVE because it is an explicit retained reproduction contract;
- `tools/run_full_pipeline.py` is self-declared deprecated and superseded by `src.pipeline.main`:
  REMOVE candidate;
- old SR measurement helpers such as `tools/measure_sr_only.py`, `tools/measure_sr_impact.py`, and
  `tools/measure_sr_x2_impact.py` hard-code `sr_eval_gpu` / `/opt/venv_sr` and belong to the retired
  environment path: REMOVE candidate once any still-needed result is anchored in Issue history;
- root-level scripts already classified Legacy by #96/#38/#45, and one-off
  `analyze_*` / `debug_*` / `visualize_*` / `structural_*` scripts with no current caller or retained
  reproduction contract, should be REMOVE candidates rather than indefinite UNDECIDED files.

A cleanup PR should still perform a mechanical inbound-reference check before deleting a concrete
batch, but that check is deletion validation, not another open-ended classification investigation.

## Legacy environment/runtime candidates

### `sr_eval_gpu` fallback

`src/pipeline/core/python_env.py` still probes `sr_eval_gpu` and can select
`/opt/venv_sr/bin/python` after the canonical `pdfscore_pipeline_gpu` path.

The current environment guide already classifies this route as legacy compatibility rather than an
endorsed setup recipe. The maintained operator entrypoint runs the pipeline inside
`pdfscore_pipeline_gpu`; current workers call `get_pipeline_python()`, but on that supported route it
selects `/opt/venv_pipeline/bin/python`. The `sr_eval_gpu` branch therefore exists for an unsupported
host/old-container fallback, not for the documented runtime contract.

Judgment: **REMOVE candidate** in a focused code cleanup. Preserve the canonical
`pdfscore_pipeline_gpu` and explicit `PIPELINE_PYTHON` behavior, add/adjust targeted interpreter
selection tests, and run the validation required for a pipeline-core change. Checking whether an old
`sr_eval_gpu` container happens to be running on one workstation is not needed to decide the public
repository surface.

### Old bootstrap scripts

`setup_scripts/setup.sh` and `setup_scripts/start.sh` hard-code
`/home/masaki_muramatsu/ws_PDFScoreBar` and start a Serena server. `setup_scripts/check_container.sh`
targets `pdf_score_dev_gpu`, which is not the maintained runtime container. The remaining
`download_deepscores_dense.sh` hard-codes a WSL-specific `/mnt/d/datasets/DeepScoresV2` destination.
DeepScores remains relevant historical/training provenance, but that does not make this machine-
specific downloader a maintained setup surface. Judgment: **REMOVE the tracked setup_scripts
surface** in a later cleanup; personal bootstrap helpers belong outside the public repository.

### Extra model Docker/external surface

The third-party/environment slice can be separated rather than treated uniformly:

- `Dockerfile.homr`: **ARCHIVE/KEEP**. `docs/ENVIRONMENTS.md` explicitly retains it for isolated or
  historical HOMR evaluation when an Issue calls for that environment.
- `Dockerfile.groundingdino`: **REMOVE candidate**. The accepted historical ledger records the
  zero-shot GroundingDINO attempt as unsuccessful; the Dockerfile also assumes an ignored local
  `external/grounding_dino` checkout. No current runtime contract depends on it.
- `external/oemer/**` plus its `.gitmodules` entry: **REMOVE candidate**. The checked-in runner is
  internally stale: from its present path it computes the repository root incorrectly, looks for
  `src/archive/oemer/oemer_src` even though the submodule is declared under `external/oemer/oemer_src`,
  and records an obsolete `src/archive/oemer/run_omerer.py` command. Current Make/Docker/package
  surfaces do not use it; Oemer conclusions remain historical evidence.
- `external/models/FSRCNN_x2.pb`: **REMOVE candidate**. It was introduced for a failed lightweight
  super-resolution experiment, whose durable negative result is already preserved in the compact
  legacy development history.

`external/README.md` should be removed or rewritten with the same cleanup so it does not continue to
advertise retired local clones as current repository dependencies.

## Need for local-state investigation

No additional workstation/local-state survey is required to make the classifications above.
Current GitHub source, current durable docs, and completed Issue audits are sufficient to distinguish
the maintained surface from legacy compatibility. In particular, re-running local `git grep` for
facts already established above, checking whether an obsolete container happens to exist locally,
or checking whether ignored third-party clones are present would duplicate evidence without changing
the repository contract.

Local execution becomes relevant only when a later cleanup **implements** behavior-sensitive changes
such as removing the interpreter fallback. At that point use the validation policy for the changed
code/config; that is implementation validation, not a remaining #230 classification question.

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

1. **#379 — Legacy interpreter/config compatibility**
   - remove `sr_eval_gpu` / `/opt/venv_sr` fallback while preserving canonical container and explicit
     interpreter override behavior;
   - remove confirmed-inert `container_name: sr_eval_gpu_exp` from the dense config;
   - validate as a focused pipeline/config change, not as another repository-surface investigation.

2. **#380 — Legacy tests migration**
   - move the useful high-level thin-barline cases into normal `tests/` coverage;
   - replace the fixed-port/sleep/static-JS GT GUI test with a deterministic current test;
   - retire `tests_legacy/**` once no unique check remains there.

3. **#381 — Pre-evaluation2 data and legacy standalone routes**
   - make `src/pdf_to_images.py` standalone defaults explicit/neutral rather than anchoring old
     `data/training` paths;
   - retire `data/training/**`, `data/evaluation/**`, and empty `data/workbench/**` tracked surface;
   - retire/update legacy standalone consumers at the same time rather than preserving old data only
     to keep obsolete demos runnable.

4. **#382 — Legacy bootstrap and third-party experiment surface**
   - retire `setup_scripts/**`, `Dockerfile.groundingdino`, `external/oemer/**`, the Oemer submodule
     entry, `external/models/FSRCNN_x2.pb`, and stale `external/README.md` claims;
   - retain `Dockerfile.homr` as the explicitly documented historical HOMR environment.

5. **#383 — Confirmed legacy tool entrypoints**
   - first cleanup batch covers the legacy manual-config builder, deprecated full-pipeline runner,
     and old `sr_eval_gpu` measurement helpers;
   - later domain-sized batches may use the already accepted #38/#45/#96 classifications without
     reopening a repository-wide historical audit;
   - preserve explicit reproduction tools such as Issue #120 and move any still-unique reusable logic
     before deletion.

## Issue #230 completion boundary

With #379-#383 created, Issue #230 has completed the decision work it owns:

- the maintained runtime/output/correction/engine boundary is recorded;
- top-level repository surface is classified;
- initially ambiguous legacy slices have concrete dispositions;
- completed specialist audits are incorporated rather than repeated;
- #100 has an explicit minimal-mainline handoff;
- behavior-changing and deletion work is separated into scoped follow-up Issues.

Actual deletion or runtime compatibility removal should therefore happen in those follow-up Issues,
not by expanding #230 into an implementation umbrella. A cleanup PR may still cite #230 as the
source decision, but it should close its own implementation Issue.

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
