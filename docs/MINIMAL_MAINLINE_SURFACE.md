# Minimal distributable surface

[日本語](MINIMAL_MAINLINE_SURFACE.ja.md)

The candidate has **120 tracked files** in
[MINIMAL_MAINLINE_SURFACE.json](MINIMAL_MAINLINE_SURFACE.json): 91 files under `src/`,
plus production config/model/Docker/package files, the package-bound user correction
application, minimum user documentation, and checkout-local ignore rules. The exact distribution is the union of
`runtime_bundle_patterns`, `distribution_support_patterns`, and
`distribution_metadata_patterns`. A generated `DISTRIBUTION_PROVENANCE.json` records
source identity, dirty status, and each shipped file's hash.

This selection was defined by Issues #100 and #409 and first promoted to `main` through
#410 (release candidate RC4, PR #442). Changes on `develop` reach `main` only through a later
release promotion under the [branch policy](dev/BRANCH_POLICY.md). The acceptance evidence for
each historical candidate size is kept in
[the #409 acceptance history](releases/issue409/ACCEPTANCE_HISTORY.md).

## Selection rationale

The former #392 list was a dependency closure. This audit applies product responsibility:
PDF input, numbered final PDF, user review, recorded corrections, corrected final PDF,
and inspectable runtime/model/input identity. The selected SR cache module implements the
opt-in compiler-cache contract; it is part of the runtime bundle even though the worker imports
it only when a cache is selected. The cache-unset SR execution path remains unchanged. The source concurrency module
is included because the maintained batch-SR detector imports it even with the
generic one-worker default; selecting two workers remains environment-specific opt-in.

| Selected category | Concrete release reason |
| --- | --- |
| `src/common`, `src/homr_runtime` | Model/resource resolution, production geometry and pinned HOMR inference |
| `src/measure_numbering` | Grouping, MMR/OCR, numbering and overlay rendering |
| Dense production `src/pipeline` | PDF jobs, detector/SR workers, candidate processing, corrections, final output and provenance |
| Two canonical configs | Dense algorithm base and pinned maintained HOMR profile |
| Three model files | CNN/download contract, verified external OMR-DLN contract, tracked production MMR checkpoint |
| Production Docker helpers and metadata | Clean build, compatibility/preflight, normal PDF and correction operation |
| Eleven `tools/review_correction` files | Supported user server, package/state adapter, local English/Japanese UI |
| README + user guide | Install, run, review/correct, troubleshooting and asset ownership |
| Distribution metadata and ignore rules | Auditable exact release selection; keep generated runtime files out of Git |

Every existing runtime entry was revisited against those responsibilities. GT matching was
unnecessarily imported from `src/common/barline_evaluation.py` by shared package exports
and production geometry callers. Unchanged geometric functions/constants now live in
`barline_geometry.py`; evaluation exports stay lazy for develop callers. The evaluation
module is excluded. No thresholds or model bytes changed.

The previous blanket exclusion of the user correction application is removed at the
**distribution** boundary. Its eleven operational files are selected individually;
`acceptance.py` and `browser_acceptance.cjs` remain development validation. User and
GT applications are already independent (#393); no GT server/assets are included.
The maintained number-layer module is classified under the runtime source bundle.
Issue441 probe/export/verification scripts and browser acceptance runners are retained
as development validation, while tests for numbering ownership, checkpoints and
returned-PDF safety are maintained contracts. None of their private inputs ship.

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

## Failure contracts

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
normal workflow acceptance are recorded in
[the #409 acceptance history](releases/issue409/ACCEPTANCE_HISTORY.md).

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
| User/release | English and Japanese README and USER_GUIDE: build, run, review/correct, troubleshooting |
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
dependency, and inspectable provenance. Keep evidence under the active Issue's log root
(`logs/issue<N>/`) in develop.
Full detector evaluation is unnecessary for unchanged geometry/algorithm/model bytes; focused
geometry compatibility and production smoke still apply. Do not report the candidate accepted
before every required packaging gate passes.
