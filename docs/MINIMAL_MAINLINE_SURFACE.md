# Minimal distributable surface (#100 / #409)

The candidate has **109 tracked files** in
[MINIMAL_MAINLINE_SURFACE.json](MINIMAL_MAINLINE_SURFACE.json): 87 files under `src/`,
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

Existing production scan diagnostics remain because the current scan emits those artifacts
through `probe_detector/debug.py`. This renderer has no GT/evaluation imports. Four lazy
legacy-route imports remain declared, plus lazy evaluation exports from `src/common`;
one historical worker default is also excluded and overridden by the maintained subclass;
the release supports only maintained_original/dense_full_pipeline. Their excluded modules
are unnecessary for supported execution. These are explicit compatibility boundaries,
not extra shipped files.

The local job adapter also bridges the v1 engine review output to the user application.
The engine deliberately strips filesystem source references and renames its work tree.
The adapter creates a separate relocated `local_manifest.json` beside the immutable
retained manifest, binds the local handoff to it, and updates the result artifact hash.
The original manifest hash stays inspectable; engine API and correction schemas are unchanged.
Review launch can prepare this bridge for a retained local job without detector inference.

## Consolidation requested after the 130-file audit

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

## Revised 109-file acceptance evidence

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
