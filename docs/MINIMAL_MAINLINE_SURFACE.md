# Minimum executable surface (Issue #100)

## Answer

The current proposed subset is the **105 tracked files** listed in
[`MINIMAL_MAINLINE_SURFACE.json`](MINIMAL_MAINLINE_SURFACE.json): 91 files under `src/`,
4 runtime helpers under `tools/`, 3 model files, 2 configs, 2 Docker helpers,
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
physical extraction.** The selected Dockerfile still builds the historical Stage-E stack
([#398](https://github.com/M763468/PDFScoreBar/issues/398)); production HOMR code is
still mixed with evaluation/history code under `src/homr_eval_scripts/`
([#115](https://github.com/M763468/PDFScoreBar/issues/115)); and four production helpers
still live under `tools/`. An isolated copy of selected files can import the engine and
start the CLI. A full GPU run of that copy has not passed. Do not present this subset as a
finished standalone distribution.

## What goes where

| Surface | Extract? | Contents |
| --- | --- | --- |
| Runtime | Yes | Exact files in the JSON `runtime_bundle_patterns` list; each entry is now a file path |
| Development and validation | No | `tests/**`, CI, smoke configs, `data/evaluation2/**`, most verification tools, training tools, repository validation scripts |
| History and reproduction | No | `experiments/**`, Issue-specific tools, Stage-E route/profile, `Dockerfile.homr` |
| Repository documentation | No | `docs/**` remains for development and operation; it is not an execution dependency |

The JSON separately explains every tracked `src/` file excluded from the selected dense
engine path. The old standard/hybrid route, Issue #120 candidate route, Stage-E route,
compatibility shims, HOMR evaluator CLI, and movement-boundary candidate producer are
retained in this repository but excluded from the proposed subset. Current HOMR workers
use selected `core/` modules; directory names alone are not a dependency test.

Four `tools/` files are exceptions to the directory rule: the dense route launches
`generate_probe_candidates_from_inventory.py` and
`apply_candidate_filter_from_inventory.py`, the latter imports
`suggest_candidate_drops.py`, and numbering launches `add_measure_numbers.py`.
Those exact files are selected. The checker catches new direct `tools/*.py` references
that are missing from the list.

## Placement already corrected

- The production OMR-DLN worker moved from `experiments/models/` to
  `src/pipeline/detection/omr_dln_worker.py`. The canonical caller invokes it as a module;
  evaluation-only options remain in experiment code.
- The dense production orchestrators have `dense_orchestrator*.py` names. The old
  `restored_orchestrator*.py` modules are compatibility shims outside the subset.
- The production MMR checkpoint moved from training tooling to `models/mmr/` without
  changing its bytes. Source-tree tests and a visualizer moved out of `src/`; the retired
  OEMER-dependent detector was removed.

## Target layout after the remaining splits

```text
src/common/                 shared runtime code
src/homr_runtime/           production HOMR code after #115
src/measure_numbering/      numbering and OCR
src/pipeline/              engine, dense detection, review and output
configs/                    dense algorithm base and maintained HOMR profile
models/                     CNN/OMR manifests and MMR checkpoint
docker/                     maintained runtime helpers
Dockerfile, pyproject.toml, README.md
```

The current file list still contains `src/homr_eval_scripts/core/**`, two mixed HOMR
profile modules, and four helpers under `tools/`; the layout above is the target, not
an assertion that those moves are complete. `Dockerfile` cannot yet represent only the
production environment because it also builds Stage-E assets (#398).

## Check and authority

Run `python3 tools/check_repository_surface.py`. CI runs the same gate. It verifies that
selected files are tracked, every tracked `src/` file is selected or excluded, excluded
groups do not silently enter the runtime subset, and referenced subprocess helpers are
selected. It does not prove that model inference or a Docker build succeeds.

This document is the sole current explanation of the extraction target. The JSON is its
machine-readable file list. [`REPOSITORY_SURFACE_INVENTORY.md`](REPOSITORY_SURFACE_INVENTORY.md)
is the broader #230 development-repository audit, not another list of files to ship.
