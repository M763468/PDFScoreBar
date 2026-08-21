# Environment & Tooling Guide

This document records maintained development and evaluation environments. Historical
one-off containers and branch-specific worktrees are not current operating instructions
unless an active Issue explicitly revives them.

## Canonical full-pipeline runtime

### `pdfscore_pipeline_gpu`

This is the maintained full-pipeline Docker image.

- Dockerfile: `Dockerfile`
- Build target: `make docker-build`
- Smoke entry point: `make run-smoke`
- Pipeline entry point: `make run-pipeline CONFIG=<config.yaml>`
- Container interpreter: `/opt/venv_pipeline/bin/python`
- Normal mounted repository root: `/workspace`

The image installs project/runtime dependencies and the maintained HOMR ONNX provider patch
from `docker/patch_homr_onnx_provider.py`. Use this image for the verified dense production
route and Stage-E/full-pipeline validation that needs Docker/GPU execution.

Read `PIPELINE_ARCHITECTURE.md` for the current two-HOMR process boundaries; container names
or old phase diagrams are not an architecture contract.

## Host / uv environments

### Default host checks

Use the repository Makefile for lightweight validation:

```bash
make test-fast
make lint
```

Choose stronger validation according to `docs/dev/VALIDATION_POLICY.md`.

### CNN classifier environment

CNN classifier training/evaluation remains host/uv based when that workflow is needed:

```bash
uv venv .venv_cnn_classifier
uv pip sync experiments/cnn_classifier/requirements_cnn_classifier_venv.txt
```

Dataset and generated model paths are operator-local unless an explicit retention policy says
otherwise. Do not interpret a `logs/` model path in a production config as proof that the
weight is present in a fresh checkout.

## Pinned Stage-E HOMR profile

The dense production route uses a pinned original-image HOMR profile whose exact provenance,
package versions, model hashes, and `/opt/` runtime paths are stored in:

```text
configs/detector_profiles/stage_e_verified_homr.json
```

That pinned profile is distinct from the current-runtime HOMR used by `current_x4_support`.
See `TWO_HOMR_MILESTONE.md` for reproduction requirements.

## Legacy compatibility environments

### `homr_eval_gpu`

`Dockerfile.homr` is retained for isolated/historical HOMR evaluation. It is not the default
full-pipeline environment. Use it only when an Issue explicitly requires isolated HOMR
behavior or historical reproduction.

### `sr_eval_gpu` compatibility fallback

The former SR-specific environment and `Dockerfile.sr_eval`/old wrapper workflow are not
maintained current guidance. `src/pipeline/core/python_env.py` still contains a host-side
compatibility fallback that can select a running `sr_eval_gpu` when the unified container is
not available. Treat that as legacy implementation compatibility, **not** as an endorsed
setup recipe.

`configs/dense_full_pipeline.yaml` also retains a legacy-looking `container_name` setting.
Issue #280 intentionally does not alter production config/runtime semantics; removal of
those compatibility remnants requires separate verification.

## Data and generated output policy

- Repository-retained evaluation fixtures are documented in `data/README.md` and relevant
  Issue retention records.
- Generated runs, metrics, model outputs, and large intermediate artifacts belong under
  ignored `logs/` paths unless an explicit retention policy says otherwise.
- `data/workbench/` is local temporary work and must be reviewed before committing.
- For CNN dataset work, stage active datasets under repository `datasets/` before bulk
  operations; use `/mnt/*` as source/archive rather than metadata-heavy scratch space.

The accepted two-HOMR milestone is **not fresh-clone reproducible** today because its exact
evaluation page images and configured CNN weight are not retained in Git. The milestone doc
records that dependency rather than silently substituting new artifacts.

## Persistent pytest-capable pipeline container

For repeated pipeline evaluation that also needs repository pytest, follow `AGENTS.md` and
use the documented persistent `pdfscore_pipeline_pytest_dev` pattern when appropriate. The
base image remains `pdfscore_pipeline_gpu`; do not weaken or rewrite pytest coverage because
the runtime image lacks pytest by default.

## Review helpers

The browser-based GT editor remains the preferred manual GT review helper:

```bash
python3 tools/gt_relabel_gui/server.py --mode gt --config <config.json> --port 8010 --host 0.0.0.0
```

Write generated overlays and review outputs under `logs/` or the configured review package
root according to the relevant workflow.
