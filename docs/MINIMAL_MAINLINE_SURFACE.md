# Minimal distributable surface (#100 / #409)

The candidate has **130 tracked files** in
[MINIMAL_MAINLINE_SURFACE.json](MINIMAL_MAINLINE_SURFACE.json): 107 files under `src/`,
plus production config/model/Docker/package files, the package-bound user correction
application, and minimum user documentation. The exact distribution is the union of
`runtime_bundle_patterns`, `distribution_support_patterns`, and
`distribution_metadata_patterns`. A generated `DISTRIBUTION_PROVENANCE.json` records
source identity, dirty status, and each shipped file's hash.

This is a candidate for isolated acceptance, not authorization to promote `main`.
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
| Eight `tools/review_correction` files | Supported user server, package/state adapter, local English/Japanese UI |
| README + user guide | Install, run, review/correct, troubleshooting and asset ownership |
| Distribution manifest | Auditable exact release selection |

Every existing runtime entry was revisited against those responsibilities. GT matching was
unnecessarily imported from `src/common/barline_evaluation.py` by shared package exports
and production geometry callers. Unchanged geometric functions/constants now live in
`barline_geometry.py`; evaluation exports stay lazy for develop callers. The evaluation
module is excluded. No thresholds or model bytes changed.

The previous blanket exclusion of the user correction application is removed at the
**distribution** boundary. Its eight operational files are selected individually;
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
