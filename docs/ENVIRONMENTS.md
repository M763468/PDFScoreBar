# Environment & Tooling Guide

This document records the maintained development and evaluation environments. Historical one-off containers and branch-specific worktrees should not be treated as current operating instructions unless an active issue explicitly revives them.

## Host / uv environments

### Default host checks

Use the repository `Makefile` as the normal entry point for lightweight validation:

```bash
make test-fast
make lint
```

Select additional validation according to `docs/dev/VALIDATION_POLICY.md`.

### CNN classifier environment

The CNN classifier training and evaluation path remains host/uv based.

```bash
uv venv .venv_cnn_classifier
uv pip sync experiments/cnn_classifier/requirements_cnn_classifier_venv.txt
```

Common entry points:

```bash
.venv_cnn_classifier/bin/python tools/cnn_classifier/build_cnn_dataset.py
.venv_cnn_classifier/bin/python experiments/cnn_classifier/train.py
```

Dataset paths are local to the operator. Use `CNN_DATASET_ROOT` when the default local path is not valid.

## Runtime Docker image

### `pdfscore_pipeline_gpu`

This is the maintained full-pipeline Docker image.

- Dockerfile: `Dockerfile`
- Build target: `make docker-build`
- Smoke entry point: `make run-smoke`
- Pipeline entry point: `make run-pipeline CONFIG=<config.yaml>`

The image installs the project package and pinned third-party runtime dependencies. It also applies the maintained HOMR ONNX provider patch from `docker/patch_homr_onnx_provider.py` during build.

Use this image for full-pipeline and Issue #120 / Stage E validation that requires the Docker/GPU runtime.

## HOMR-only legacy image

### `homr_eval_gpu`

`Dockerfile.homr` is retained as a HOMR-isolated legacy evaluation image. It is not the default full-pipeline environment.

Use it only when an issue explicitly needs isolated HOMR behavior or historical HOMR reproduction. Otherwise prefer `pdfscore_pipeline_gpu`.

## Removed / obsolete environments

The former `sr_eval_gpu` / `Dockerfile.sr_eval` environment and the dependent `tools/run_hybrid_pipeline.sh` wrapper were removed during Issue #190 cleanup. They represented an older SR-specific experiment path and should not be used as current guidance.

## Data and generated output policy

- Repository-retained evaluation fixtures are documented in `data/README.md` and issue-specific retention documents such as `docs/ISSUE120_ARTIFACT_RETENTION.md`.
- Generated run outputs belong under ignored `logs/` paths.
- Do not commit ad-hoc artifacts, visual overlays, temporary JSON summaries, or local draft files unless an issue-specific retention policy explicitly requires them.
- `data/workbench/` is for local temporary work; contents should be reviewed before committing.

## Review helpers

The browser-based GT editor remains the preferred manual review helper for ground-truth correction:

```bash
python3 tools/gt_relabel_gui/server.py --mode gt --config <config.json> --port 8010 --host 0.0.0.0
```

For overlay generation, use the maintained tools under `tools/` and write outputs under `logs/`.
