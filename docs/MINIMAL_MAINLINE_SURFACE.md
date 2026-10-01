# Minimum executable surface (Issue #100)

## Answer

The current proposed subset is the **111 tracked files** listed in
[`MINIMAL_MAINLINE_SURFACE.json`](MINIMAL_MAINLINE_SURFACE.json): 101 files under `src/`,
3 model files, 2 configs, 2 Docker helpers,
and `Dockerfile`, `pyproject.toml`, and `README.md`. The root README is required by
`pyproject.toml` during installation. No `docs/**`, `tests/**`, CI, GT, or experiment
file is in the executable subset. These are selection counts, not a released package.

The intended entrypoint is `src.pipeline.engine_executor.PipelineJobExecutor`. It accepts
a PDF request, uses `configs/dense_full_pipeline.yaml` as the dense algorithm base,
renders the request PDF, and produces final and optional review artifacts. The checked-in
config still points to development images when run directly; the executor replaces that
input for a PDF job. Production model manifests and the tracked MMR checkpoint are in
`models/`; OMR-DLN weights remain an external verified asset.

**This is an explicit boundary, but the implementation is not yet sufficiently simple for
physical extraction.** The 101 source files reflect the current PDF rendering, two-HOMR
detection, SR/OMR-DLN/CNN consensus, measure numbering/OCR, engine, and correction/review
behavior. They are an audited dependency set for those behaviors, not a claim that 101 files
is a desirable final architecture. Three more `src/` files were excluded and one unused
ONNX helper was removed after the call-path audit; shrinking further requires a
behavior-preserving split of mixed modules
or a narrower product contract.

The selected Dockerfile still builds the historical Stage-E stack
([#398](https://github.com/M763468/PDFScoreBar/issues/398)); production HOMR code now lives
under `src/homr_runtime/` after the responsibility split
([#115](https://github.com/M763468/PDFScoreBar/issues/115)). Evaluation/core compatibility
adapters and the historical Stage-E profile executor are excluded from the runtime list.
Four production helpers
have now moved from `tools/` to `src/`, though their candidate-generation APIs still
carry evaluation-oriented inventory structure. An isolated bind-mounted copy of the earlier
102 selected files completed the one-page GPU pipeline and passed the 85/85 detector accuracy
gate. The additional file now excluded, `movement_boundary_review.py`, was not imported by
that run or by the selected engine/correction call paths. The run used the current full image
plus externally mounted validation input and model; building a production-only image from
the selected files remains blocked by #398.
Do not present this subset as a finished standalone distribution.

## What goes where

| Surface | Extract? | Contents |
| --- | --- | --- |
| Runtime | Yes | Exact files in the JSON `runtime_bundle_patterns` list; each entry is now a file path |
| Development and validation | No | `tests/**`, CI, smoke configs, `data/evaluation2/**`, most verification tools, training tools, repository validation scripts |
| History and reproduction | No | `experiments/**`, Issue-specific tools, Stage-E route/profile, `Dockerfile.homr` |
| Repository documentation | No | `docs/**` remains for development and operation; it is not an execution dependency |

The same JSON classifies **every tracked config and test module** outside that runtime
selection. Among the 77 tracked configs, 2 are runtime inputs, 4 support current
development/validation, and 71 are retained comparison or reproduction recipes. Two
unreferenced configs with retired runtime paths (`full_pipeline_template.yaml` and
`evaluation2_e2e_verification.yaml`) were removed. The 104 test modules are classified as
66 maintained contracts, 12 validation-harness tests, 5 developer-tool tests, and 21
reproduction tests. All tests and their 55 fixtures stay in the development repository;
none is needed merely to execute a PDF job. An Issue-numbered test is not assumed to be
obsolete solely because of its name.

The JSON separately explains every tracked `src/` file excluded from the selected dense
engine path. The old standard/hybrid route, Issue #120 candidate route, Stage-E route,
HOMR evaluator CLI, and movement-boundary candidate producer are
retained in this repository but excluded from the proposed subset. Current HOMR workers
use `src/homr_runtime/` modules; the old `core/` modules remain compatibility adapters
and evaluation diagnostics outside the selected bundle.

Three further `src/` files were excluded after call-path review. `barline_units.py` is
used by evaluation/tests, `engine_lifecycle.py` is a development contract helper not
wired into the executor, and `movement_boundary_review.py` supports the development GUI
and manual review authoring. The unused `ort_config.py` was removed from the repository.
The engine and correction rerun consume the resulting review records without importing
the authoring helper.
Correction application remains selected because the current product includes a separate
review-package correction flow, even though a one-job request does not execute
`CorrectionSet` records directly.

The dense route's candidate generator, filter, and drop heuristic now live under
`src/pipeline/detector_routes/`; the numbering CLI now lives under
`src/measure_numbering/`. Production and maintained development callers use those
modules. The old `tools/` commands were removed. The checker rejects new direct
`tools/*.py` references from selected runtime source.

## Placement already corrected

- The production OMR-DLN worker moved from `experiments/models/` to
  `src/pipeline/detection/omr_dln_worker.py`. The canonical caller invokes it as a module;
  evaluation-only options remain in experiment code.
- The dense production orchestrators have `dense_orchestrator*.py` names. The old
  `restored_orchestrator*.py` compatibility shims were removed after test and
  reproduction callers were moved to the canonical names.
- The production MMR checkpoint moved from training tooling to `models/mmr/` without
  changing its bytes. Source-tree tests and a visualizer moved out of `src/`; the retired
  OEMER-dependent detector was removed.

## Target layout after the remaining splits

```text
src/common/                 shared runtime code
src/homr_runtime/           prediction types, transforms, candidates, filtering, inference and outputs
src/measure_numbering/      numbering and OCR
src/pipeline/              engine, dense detection, review and output
configs/                    dense algorithm base and maintained HOMR profile
models/                     CNN/OMR manifests and MMR checkpoint
docker/                     maintained runtime helpers
Dockerfile, pyproject.toml, README.md
```

The current list contains production-owned HOMR modules and maintained profile backends.
`profile_sources*.py` owns shared source-generation/SR scheduling;
`maintained_profile*.py` selects only the maintained runtime, while the old
`homr_profile.py` and `profile_hybrid*.py` keep historical/compatibility dispatch outside
the selected bundle. `Dockerfile` cannot yet represent only the
production environment because it also builds Stage-E assets (#398).

## Check and authority

Run `python3 tools/check_repository_surface.py`. CI runs the same gate. It verifies that
selected files are tracked, imports from selected Python source (including relative imports
and package initializers) stay within the selection except for four explicitly recorded lazy
standard-route and non-maintained-profile compatibility imports. It rejects new undeclared runtime leaks and stale
exception records. It also verifies that every tracked `src/` file is selected or excluded, every
tracked config and test file has exactly one role, excluded groups do not silently enter
the runtime subset, and referenced subprocess helpers are selected. It does not prove
that model inference or a Docker build succeeds.

This document is the sole current explanation of the extraction target. The JSON is its
machine-readable file list. [`REPOSITORY_SURFACE_INVENTORY.md`](REPOSITORY_SURFACE_INVENTORY.md)
is the broader #230 development-repository audit, not another list of files to ship.
