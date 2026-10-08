# Minimal distributable surface (#100 / #409)

The candidate has **104 tracked files** in
[MINIMAL_MAINLINE_SURFACE.json](MINIMAL_MAINLINE_SURFACE.json): 82 files under `src/`,
plus production config/model/Docker/package files, the package-bound user correction
application, and minimum user documentation. The exact distribution is the union of
`runtime_bundle_patterns`, `distribution_support_patterns`, and
`distribution_metadata_patterns`. A generated `DISTRIBUTION_PROVENANCE.json` records
source identity, dirty status, and each shipped file's hash.

This is an isolated-validated candidate for #410, not authorization to promote `main`.
#410 consumes the accepted selection and establishes release promotion separately.

## Re-audit after #115 and #398

The former #392 list was a dependency closure. This audit applies product responsibility:
PDF input, numbered final PDF, user review, recorded corrections, corrected final PDF,
and inspectable runtime/model/input identity.

| Selected category | Concrete release reason |
| --- | --- |
| `src/common`, `src/homr_runtime` | Model/resource resolution, production geometry and pinned HOMR inference |
| `src/measure_numbering` | Grouping, MMR/OCR, numbering and overlay rendering |
| Dense production `src/pipeline` | PDF jobs, detector/SR workers, candidate processing, corrections, final output and provenance |
| Two canonical configs | Dense algorithm base and pinned maintained HOMR profile |
| Three model files | CNN/download contract, verified external OMR-DLN contract, tracked production MMR checkpoint |
| Production Docker helpers and metadata | Clean build, compatibility/preflight, normal PDF and correction operation |
| Seven `tools/review_correction` files | Supported user server, package/state adapter, local English/Japanese UI |
| README + user guide | Install, run, review/correct, troubleshooting and asset ownership |
| Distribution manifest | Auditable exact release selection |

Every existing runtime entry was revisited against those responsibilities. GT matching was
unnecessarily imported from `src/common/barline_evaluation.py` by shared package exports
and production geometry callers. Unchanged geometric functions/constants now live in
`barline_geometry.py`; evaluation exports stay lazy for develop callers. The evaluation
module is excluded. No thresholds or model bytes changed.

The previous blanket exclusion of the user correction application is removed at the
**distribution** boundary. Its seven operational files are selected individually;
`acceptance.py` and `browser_acceptance.cjs` remain development validation. User and
GT applications are already independent (#393); no GT server/assets are included.

The release supports only maintained_original/dense_full_pipeline. Develop-only probe
images, wide-candidate splitting and standalone numbering CLI/overlay are excluded;
their opt-in paths remain functional in develop. Lazy historical compatibility routes
and evaluation exports also stay excluded with explicit manifest reasons.

The local job adapter also bridges the v1 engine review output to the user application.
The engine deliberately strips filesystem source references and renames its work tree.
The adapter creates a separate relocated `local_manifest.json` beside the immutable
retained manifest, binds the local handoff to it, and updates the result artifact hash.
The original manifest hash stays inspectable; engine API and correction schemas are unchanged.
Review launch can prepare this bridge for a retained local job without detector inference.

## Failure-contract review: 106 to 104 files

The previous audit retained page-local SR because selected low-level entrypoints accepted
absent `precomputed_sr`. That condition selects a separate compatibility mode; batch failure
has never automatically retried it. The production contract now defaults to `batch_required`:
missing, explicit null, or malformed precomputed SR fails before HOMR starts. The maintained
source-page worker and batch helper validate it before baseline inference. Develop callers
must explicitly request `sr_mode=page_local`; legacy non-batch source generation writes that
mode. Both modes remain in develop; only batch SR is supported in the distribution.

| Case | Classification and current behavior |
| --- | --- |
| Generic SR returns original image on failure | Historical develop compatibility: `apply_advanced_sr(strict=False)` retained. Verified page-local SR explicitly uses `strict=True`; dependency/model/init/inference errors propagate and output must be exactly x4 before it is saved or marked completed. Batch SR already raises and checks shape. |
| No precomputed SR | Explicit develop page-local execution mode; production fails. `current_sr_worker.py` and its `common/preprocessing.py` dependency are excluded only from distribution, with the subprocess reference declared optional. |
| Invalid HOMR/OMR JSON or coordinates | Corruption, not empty prediction: canonical consensus uses strict loader and raises with the artifact path. Legacy development loader calls explicitly use `strict=False`. |
| Valid empty list or empty predictions list | Normal zero detections; strict loader still returns `[]`. |
| Edge-clipped zero-width/height box | Existing HOMR/OMR output contract retained, including `int` conversion; reversed bounds remain errors. |
| No optional rescue seed | Generic/develop no-seed usage remains supported with `require_seed_files=False`. |
| Missing/corrupt required rescue seed | Canonical dense rescue sets `require_seed_files=True`; missing file raises with page identity and searched paths, invalid JSON raises with its path. An existing valid empty seed remains supported. |
| Missing/unreadable staff mask with explicit `scan_x_domain_mode=staff_mask` | Required mask is now fail-closed before probe detection, with page/path context. `staff_mask_or_existing_boxes` and `full_width` retain the existing optional-mask behavior; a decoded all-zero mask remains a valid input. |

Source files are retained. No numeric algorithm, model, threshold, coordinate rounding,
consensus order or normal successful SR output is changed. The failure behavior is deliberately
stricter: affected workers stop, engine jobs return FAILED, and no normal final/review artifacts
are published. Existing v1 public engine schemas stay unchanged. Failure injection and actual
normal workflow acceptance are recorded separately below.

## 104-file failure-review acceptance evidence

Evidence root: `logs/issue409/failure-review-20261009/`. Runtime source `e1038b97`
was materialized cleanly at `/tmp/pdfscorebar-issue409-failure104b`: **92 runtime + 11
support + 1 metadata = 104 files** (82 source + 22 others). Image
`pdfscore_issue409_failure104`, ID
`sha256:f55c753c9de72ea2b5892a4b996beaa569be5a0ba17da40f2d15d6bf9f4ee3dd`.
Subsequent excluded tests/tools/documentation changes do not alter the selected file bytes;
`final-distribution-parity.json` verifies every shipped hash against that clean candidate.

| Check | Result / evidence |
| --- | --- |
| Worker/parent/engine failure injection and compatibility | PASS; `final-focused-tests.log`, 102 tests: SR import/model/init/inference/shape, absent/null/invalid SR, broken component JSON and missing/corrupt required seed; FAILED and no final/review publication. Valid empty results, edge-clipped coordinates and explicit development modes remain supported. |
| Public engine compatibility | PASS; `engine-contract.log`, 70 tests, same PR engine gate |
| Lightweight regression / historical diagnostic | PASS; `test-fast-final-details.log`, 110 tests; `historical-tool-contract.log`, 15 tests; suites overlap |
| Exact isolated distribution/build/preflight | PASS; `materialize-final.log` (dirty=false), dependency/reference/content check, `build-final.log`, GPU/ONNX/model/source provenance in `run.log` and `review.log` |
| Independent normal 300 DPI PDF job | PASS; `run.log`, job `job-c50d9a5a755549b198e4b5ca49e8eff1`: one requested/processed page, final PDF and review handoff, no skips/warnings |
| Actual user correction UI | PASS; `browser/browser-report.json` and `languages.json`: save/apply/PDF download/stale retention, Japanese/English, no page errors |
| Corrected numbering and PDF semantics | PASS; `correction-semantic-check.json`: `[1,2,3,4,5]` to `[1,3,4,5,6]`, next row label 7 and 251 dark label pixels; downloaded PDF equals final PDF, original manifest hash preserved, upstream inference rerun=false |
| Original 360 DPI canonical accuracy gate | PASS; `canonical-smoke.log`: 85/85 matches, hard FP=0, FN=0, soft=0; original PDF/render hashes and detection-config parity |
| Retained Full68 reader compatibility | PASS; `audit_retained_json.py` / `retained-full68-json-audit-final.json`: 68 baseline, 68 current HOMR, 68 OMR and 68 required rescue seeds; strict/tolerant coordinate lists identical, no schema failures. Historical schema evidence, not fresh accuracy inference. |
| Static checks | PASS; Ruff src/tests/tools/docker/scripts, diff/surface and excluded historical-tool compilation. An owned host pycache initially blocked compilation; disposable `PYTHONPYCACHEPREFIX` resolved it. |

Reproduction command for the unchanged accuracy contract:

```bash
DOCKER_IMAGE=pdfscore_issue409_failure104 bash scripts/docker_runtime_validation.sh \
  --config logs/issue409/failure-review-20261009/canonical-smoke.yaml
```

`unchanged-model-config.json` records byte equality against `64d4b7a2` for the dense
config, maintained HOMR profile and all three selected model contracts/assets. Failure
checks deliberately change invalid-input behavior; numerical bodies, ordering, rounding,
models and thresholds are unchanged. Edge-clipped zero dimensions were identified in
accepted historical output and preserved before runtime acceptance.

Fresh Full68 inference is deferred: the changed valid-input reader contract has been checked
against all 272 retained files, and the original canonical accuracy gate passes. This does
not claim a fresh Full68 accuracy result. Explicit development page-local GPU inference is
also not run: it is outside the supported 104-file distribution; real subprocess failure
injection and development compatibility tests cover its changed contract. Both normal
production PDF workflows ran batch SR on GPU. Temporary review/browser containers were
stopped; browser dependencies were installed only in a disposable validation container.
Current architecture documents these failure contracts; future service responsibility
boundaries do not change. CI status is recorded in PR #412 for the final head.

## Historical review audit: 109 to 106 files

The review identified a develop direct-run regression: canonical image discovery still
uses `inputs.pdf_to_images.output_dir` when PDF rendering is disabled. The path is restored
to `data/evaluation2/images`. The isolated PDF executor removes that field and enables
rendering into the job workspace; no dataset directory is shipped or required by PDF jobs.

| Candidate | Decision and reachable contract |
| --- | --- |
| `detection/current_sr_worker.py` | Retained: `current_support_worker.run` without `precomputed_sr` explicitly launches this subprocess. The selected source-page worker also accepts absent precomputed SR. Normal batch calls supply it, but low-level worker entrypoints retain the fallback contract. No exclusion is justified without changing that contract. |
| `common/preprocessing.py` | Retained: the retained page-local SR worker imports `apply_advanced_sr`; owns SR model resolution and x4 processing for that fallback. The separate batch worker uses `current_sr_runtime` and does not replace this implementation. |
| `probe_detector/debug.py` | Excluded from distribution only: `detect_probe_scan` imports its renderer inside `debug_path is not None`. Canonical callers do not pass `debug_path`; develop diagnostic output is tested and preserved. |
| `utils/wide_split_utils.py` | Excluded from distribution only: import moved inside enabled `post_split_wide_candidates` branch. Canonical config disables it; develop opt-in calls the same implementation and is tested. |
| `measure_numbering/cli.py` | Excluded from distribution only: production phases call `MeasureNumberingPipeline` directly. `render_overlay` is already imported only for `steps.overlay=true` (canonical false); unused production `build_add_measure_numbers_cmd` still builds the develop standalone subprocess command. Engine final PDF and correction apply use `review/final_output.py`. Both optional references are declared; develop CLI and overlay are tested. |

Batch SR errors, missing outputs or missing pages raise before source-page dispatch;
invalid precomputed SR fails validation rather than retrying page-local inference. Re-running
canonical detection regenerates batch SR. Missing `precomputed_sr` on the retained low-level
entrypoints is different: it still selects the page-local fallback. Existing tests cover both
paths, malformed precomputed input, and SR batch input validation. Numeric algorithms,
model assets, thresholds, and interpreter/model provenance mechanisms are unchanged.

The exact manifest declares lazy optional imports and the standalone subprocess module string.
Source fingerprint covers the changed modules; distribution provenance records the canonical
config hash. The image/runtime compatibility fingerprint is unchanged. No repository
source is deleted, and `common/__init__.py` is retained. Engine debug telemetry is still
supported; only opt-in probe image diagnostics are excluded. The optional debug/wide split/
numbering overlay features require develop and are outside the supported user distribution.

## Historical 106-file acceptance evidence

Validated clean source: `20ab997934f25311cff194f71809cc87f0769b4d` at
`/tmp/pdfscorebar-issue409-review106`. Exact union: 94 runtime + 11 support + 1 metadata
files; 84 source files and 22 other files. Image `pdfscore_issue409_review106`, ID
`sha256:d8a36f850fc2c9dc464c4b98b3b71fc005dd8f17e7d9a4e5477b4b04eef9f791`.
Evidence is under `logs/issue409/review-20261008/`.

| Gate | Result / evidence |
| --- | --- |
| Direct-run input discovery and isolated PDF configuration | PASS; focused tests use the unchanged canonical config with images at `data/evaluation2/images`; PDF config removes external output_dir and enables job-local rendering |
| Develop optional features and SR fallback contracts | PASS; `focused-tests-fixed.log`, 51 tests; actual debug artifacts, enabled wide splitter, overlay and CLI help; retained SR worker and precomputed-SR contracts |
| Maintained fast suite | PASS; `test-fast-details.log`, 110 tests |
| Exact clean distribution/build/preflight | PASS; `materialize.log` (106 files, dirty=false), independent dependency/reference/content check, `build.log`, GPU/model/provenance in `run.log` and `review.log` |
| Isolated PDF-to-final | PASS; `run.log`, normal Prokofiev page 1 at 300 DPI; `results/job-a7200b3af4d44a218b42dc7af9a01c90/` |
| Actual browser correction and languages | PASS; `browser/browser-report.json`, `browser/languages.json`; save/apply/download/stale retention, English/Japanese, no browser errors |
| Semantic corrected final | PASS; `correction-semantic-check.json`: `[1,2,3,4,5]` → `[1,3,4,5,6]`, second-row label 7 in PDF pixels, downloaded PDF matches final PDF, original manifest hash preserved; upstream inference is not rerun |
| Same canonical 360 DPI accuracy gate | PASS; `canonical-smoke.log`, 85/85 matches, hard FP=0, FN=0, soft=0; original source PDF/render hashes and detection-config parity |
| Static/CI | PASS; focused Ruff, diff check, repository-surface; engine contract compatibility, make lint and repository-surface CI |

Reproduce accuracy from develop:

```bash
DOCKER_IMAGE=pdfscore_issue409_review106 bash scripts/docker_runtime_validation.sh \
  --config logs/issue409/review-20261008/canonical-smoke.yaml
```

`provenance.json` records source/image identities, exact exclusions, entrypoint/model audit,
and whole-module AST equality after removing only the two relocated optional imports.
Canonical config differs from the previous candidate only in the restored external input path.
Full68 is not rerun: numerical algorithms, model assets, thresholds and detector settings are
unchanged, and the original canonical gate passes. Page-local fallback GPU inference is also
not rerun: that code is retained unchanged and its focused contracts pass. Normal batch SR
was exercised with the actual GPU in both PDF runs. Those are the validation limits; the
result does not claim a fresh Full68 or fallback GPU evaluation.
Temporary review/browser containers were stopped; their evidence and previous acceptance
runs were retained. Current architecture documentation reflects optional imports; future
architecture needs no change because responsibilities and service boundaries are unchanged.

## Historical consolidation from 130 to 109 files

The revised candidate removes **21 files (16.2%)** while keeping the supported workflow.

| Shared responsibility | Consolidation | Net reduction |
| --- | --- | ---: |
| Pipeline configuration, run IDs, subprocess logging, output I/O | Four helpers into `src/pipeline/core/__init__.py` | 4 |
| Numbering records and JSON representation | Serialization into `measure_numbering/types.py` | 1 |
| Numbering execution phases and their services | Four modules into `steps/numbering_phases.py` | 3 |
| Probe measurements before candidate acceptance | Projections, peaks, scan measurements into `probe_detector/measurements.py` | 2 |
| HOMR records and existing defaults | Settings into `homr_runtime/types.py` | 1 |
| Verified model and asset resolution | SR and OMR paths into `common/model_artifacts.py` | 2 |
| User correction state and result controls | Both browser adapters into `correction_state.js` | 1 |
| Empty or docstring-only package markers | Native namespace packages; substantive initializers retained | 7 |

All callers, including retained development tooling, use the new owners. No compatibility
stub is shipped. Numbering scheduling, candidate acceptance, engine contracts and model
loading remain separate responsibilities. Function/class bodies and decorators were checked
against the pre-consolidation commit before formatting; model/config bytes remain unchanged.
The previous 130-file validation below is historical evidence; the 109-file candidate
has its own independent acceptance record.

## Develop-only classification

Anything outside the three exact lists stays on `develop`, including:

- All evaluation/GT corpora, `data/**`, `datasets/**`, tests and fixtures, CI, and full
  regression/evaluation tooling. None is required for supported product operation.
- Stage-E reproduction image, profiles, routes and `tools/issue120/**`; historical HOMR
  Dockerfile; experiments and issue evidence under ignored logs.
- GT/relabel/training tools, review acceptance harnesses, broad scripts/Makefile automation,
  repository inventory/checkers and extraction tooling.
- Agent/Codex/Gemini automation, skills and generated Graphify output.
- Architecture, validation, service design, history and investigation documentation.

Source exclusions and config/test roles are individually recorded in the JSON; the default
exclusion rule also covers future unselected files. Maintained development status does not
confer release status. No retained development evidence is deleted by extraction.

## Documentation audiences

| Audience | Release selection |
| --- | --- |
| User/release | README and USER_GUIDE only: build, run, review/correct, troubleshooting |
| Operator/reference | Manifest/model identities; preflight and result provenance |
| Developer | Architecture, environment, engine contracts, validation policy, inventories; excluded |
| Historical/investigation | Refactor/Issue docs and accepted experiments; excluded |

Audience patterns in the manifest describe responsibility; they do not select extra files.
The user guide is the single operational instruction set. The previous developer README's
links to excluded architecture/agent documentation have been removed from the release entry.

## Materialization and checks

From develop:

```bash
python3 tools/check_repository_surface.py
python3 tools/materialize_distribution.py materialize /tmp/pdfscorebar-candidate
python3 tools/materialize_distribution.py check /tmp/pdfscorebar-candidate
```

Use a fresh directory outside the development checkout. The materializer rejects symlinks,
path traversal, duplicates, missing inputs, and existing output directories. It copies only
exact selected files, stores file hashes and source identity, then checks the isolated tree.
The checker needs no Git or undeclared development file in the candidate; the developer-side
checker examines it from outside. Checks cover local imports, known subprocess module
references, document/UI links, content hashes and unexpected files. They complement actual
Docker/PDF/application acceptance and do not prove numerical accuracy.

Run `python3 docker/distribution.py build`, `preflight`, `run` and `review` **from the candidate**
as described in USER_GUIDE. Required acceptance is clean production build, canonical preflight,
PDF-to-final, review/save/apply-to-corrected-final, both UI languages, no GT/development/reproduction
dependency, and inspectable provenance. Keep evidence under `logs/issue409/` in develop.
Full detector evaluation is unnecessary for unchanged geometry/algorithm/model bytes; focused
geometry compatibility and production smoke still apply. Do not report the candidate accepted
before every required packaging gate passes.

## Historical 109-file acceptance evidence

Validated source: `d8583b65cd33e64bc6898c4aee58f88d1d69aea3`, clean candidate08 at
`/tmp/pdfscorebar-issue409-candidate08`. Evidence is under `logs/issue409/refinement/`.
Dedicated image: `pdfscore_issue409_consolidated`, ID
`sha256:c7b96903a46641c28b20e742f44a3565366db77d00d8c2d370834ab4f868ac9e`.

| Required gate | Result / evidence |
| --- | --- |
| Exact isolated distribution | PASS; `materialize08.log`, 109 files, clean source, dependency/reference/content check |
| Independent production build and GPU preflight | PASS; `build08.log`, `run08.log`, `review08.log`; verified image/model/runtime provenance |
| Normal PDF-to-final | PASS; `run08.log`, Prokofiev page 1 at default 300 DPI; `results08/job-c0cb1558fabe47ce8d0a062cdbdbdeb9/` |
| Real browser save/apply/download/stale retention | PASS; `browser08/browser-report.json`, downloaded final PDF and screenshots |
| English/Japanese application | PASS; `browser08/languages.json`, no browser errors |
| Semantic corrected output | PASS; `correction-semantic-check.json`: span 2 changes `[1,2,3,4,5]` to `[1,3,4,5,6]`; second-row label 7 verified in PDF image pixels; downloaded PDF hash and original manifest hash verified |
| Same canonical 360 DPI accuracy contract | PASS; `canonical-smoke.log`, 85 predictions / 85 GT / 85 matches, hard FP=0, FN=0, soft=0; fixed input/source PDF hashes and detector config parity |
| Existing contracts | PASS; `test-fast-details.log` 110, `focused-python-tests.log` 88, `isolated-client-tests.log` 22, `pipeline-contract-tests.log` 53, `runtime-model-tests.log` 50, `model-tests.log` 12 (overlapping coverage) |
| Unchanged numerical implementation and artifacts | PASS; `ast-parity.json`: 59 assembled definitions verified before formatting, moved definitions rechecked afterward; canonical configs and all three selected model files unchanged |
| Static checks | PASS; repository surface, Ruff check/format and `git diff --check` |

Reproduce the GPU accuracy gate from develop with:

```bash
DOCKER_IMAGE=pdfscore_issue409_consolidated bash scripts/docker_runtime_validation.sh \
  --config logs/issue409/refinement/canonical-smoke.yaml
```

The initial mixed Docker test invocation had six Node-dependent failures because that
Python validation container has no `node`; those tests passed on the host. The Python
subset was then run separately in Docker. All failed-attempt evidence is retained.
Browser-only libraries were installed in a disposable validation container, and the temporary
review/browser containers were stopped. Production dependencies were unchanged.
Full68 remains deferred because numerical bodies, thresholds, models and canonical config
are unchanged; actual worker execution, existing contracts and the original canonical smoke
were revalidated after consolidation. Current and future architectural responsibility
boundaries remain unchanged; only current module ownership documentation required updates.

## Historical 130-file acceptance evidence

Validated source: `b0bb70ec` (clean candidate06, 130 selected files). The clean tree
was materialized at `/tmp/pdfscorebar-issue409-candidate06` and built with the production
Dockerfile. Build cache reused the unchanged pinned dependency layers; no development
checkout was part of that build context. Evidence remains in `logs/issue409/validation/`.

| Required gate | Result / evidence |
| --- | --- |
| Isolated dependency/reference/content check | PASS; `materialize_distribution.py check` without Git in candidate |
| Clean primary Docker build | PASS; `build06.log`, dedicated `pdfscore_issue409_final` image |
| Canonical runtime preflight | PASS; `review06.log` includes candidate06 CUDA/ONNX/model/provenance check |
| Normal PDF → numbered final PDF | PASS; `run04.log`, Prokofiev page 1, default 300 DPI, `results04/` |
| Review → record → apply → corrected final PDF | PASS; `browser06-retry.log`, `browser04/browser-report.json` |
| English/Japanese functional UI | PASS; `browser04/languages.json`, both screenshots, no browser errors |
| Correction downstream semantics/provenance | PASS; `correction-semantic-check.json`: span 3 shifts following numbers by 2; second row label 8; rendered label pixels and original manifest hash checked |
| Existing detector numerical gate | PASS; `canonical-smoke.log`: 360 DPI accepted input, 85/85 matches, hard FP/FN/soft residual all 0 |
| Development contracts | PASS; `test-fast-details.log` (110), `contracts-tests.log` (58), `bridge-focused-tests.log` (59, overlapping coverage), lint/diff checks |

The normal PDF job used candidate04 with the same production source/UI/model bytes.
Candidate05 changed only manifest classification and an unused default image directory;
the PDF executor removes that directory before running. Candidate06 adds the local review
bridge and its user instructions. Its actual bridge/apply was validated against the retained
job without repeating detector inference. `candidate04-to05.json` and fixed-base
`geometry-ast-parity.json` record that reuse boundary. The canonical accuracy smoke uses
external GT from develop as a regression checker; GT is absent from the candidate and its
normal job/correction execution.

Initial browser execution needed separate network-namespace access and validation-only
Chromium dependencies in a disposable container. The first real apply exposed the missing
local manifest connection; it failed and led to the adapter fix. A subsequent browser retry
used span 3 because span 2 was already recorded by that failed attempt. Both failed attempts
and the successful attempt remain retained. A text-extraction assertion was also invalid
for the established raster PDF renderer; the corrected check verifies numbering, rendered
label records and pixels rather than assuming a text layer.

Full68 evaluation was not run: detector/OCR/MMR algorithms, geometric arithmetic, thresholds
and model/dependency versions are unchanged. Focused parity, correction semantics and the
canonical one-page accuracy gate cover this packaging change. The supported distribution
is Linux/NVIDIA Docker with operator-imported OMR-DLN. Promotion, publishing and `main`
changes belong to #410; no branch was merged or promoted here.
