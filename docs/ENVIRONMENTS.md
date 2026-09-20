# Environment & Tooling Guide

This document records maintained development and evaluation environments. Historical
one-off containers and branch-specific worktrees are not current operating instructions
unless an active Issue explicitly revives them.

## Canonical full-pipeline runtime

### `pdfscore_pipeline_gpu`

This is the maintained full-pipeline Docker image.

- Dockerfile: `Dockerfile`
- Build target: `make docker-build`
- Canonical GPU validation entry point: `make verify-gpu-smoke`
- Low-level smoke target: `make run-smoke`
- Pipeline entry point: `make run-pipeline CONFIG=<config.yaml>`
- Container interpreter: `/opt/venv_pipeline/bin/python`
- Normal mounted repository root: `/workspace`

The image installs project/runtime dependencies and the maintained HOMR ONNX provider patch
from `docker/patch_homr_onnx_provider.py`. Use this image for the verified dense production
route and Stage-E/full-pipeline validation that needs Docker/GPU execution.

`make verify-gpu-smoke` is the authoritative environment gate. Before pipeline execution it
runs `scripts/docker_runtime_validation.sh`, which checks the bind-mounted source against the
source fingerprint recorded when the image was built, validates required assets, and probes
CUDA inside the container. Host `nvidia-smi` output is metadata only; the container CUDA probe
is authoritative.

`make run-smoke` remains a lower-level pipeline invocation and does not replace that preflight.

Read `PIPELINE_ARCHITECTURE.md` for the current two-HOMR process boundaries; container names
or old phase diagrams are not an architecture contract.

## Docker source, mount, and asset ownership contract

The canonical runtime deliberately bind-mounts the active checkout at `/workspace`. This
means source files copied into `/workspace` during `docker build` are hidden at runtime. Files
that must survive that mount therefore must not rely on image contents under `/workspace`.

The ownership rules are:

| Runtime dependency | Owner | Canonical location / mechanism |
|---|---|---|
| main Python/runtime dependencies | Docker image | `/opt/venv_pipeline` |
| maintained current HOMR package/runtime | Docker image | installed in `/opt/venv_pipeline` from the Dockerfile pin |
| verified historical Stage-E HOMR stack | Docker image | `/opt/venv_stage_e_homr`, `/opt/homr_stage_e_profile`, `/opt/pdfscore_stage_e_profile` |
| Real-ESRGAN x2/x4 weights | Docker image | `/opt/pdfscore-assets/realesrgan` |
| canonical smoke CNN bytes | Docker image, derived from the tracked #315 manifest | `/opt/pdfscore-assets/barline_cnn_smoke.pth` |
| OMR-DLN `YOLOv8m_Measures.pt` | operator/external asset | selected manifest version in the common host model cache, mounted read-only below `/opt/pdfscore-external/omr-dln-measures/<version>/` |
| repository source/config/input data | active checkout | bind-mounted at `/workspace` |
| generated run artifacts | active checkout/operator | ignored `logs/`, `artifacts/`, and configured output paths |

The cross-model version/provenance/integrity and update rules are inventoried in
`docs/MODEL_ARTIFACT_CONTRACT.md`. Host-side model artifacts default to a shared per-user
cache at `$XDG_CACHE_HOME/pdfscorebar/models`, or `~/.cache/pdfscorebar/models` when
`XDG_CACHE_HOME` is unset. `PDFSCOREBAR_MODEL_CACHE` remains the explicit override. The
default is intentionally independent of the active checkout so one verified registration can
be reused across worktrees.

The Real-ESRGAN resolver uses `PDFSCORE_REALESRGAN_WEIGHTS_DIR` in the image and retains the
legacy checkout path only as a host-development fallback. A canonical Docker smoke must not
require weights to be manually copied into `external/realesrgan/weights`.

The smoke CNN does not create a second production model contract. Docker materializes the
tracked `models/barline_cnn/manifest.json` through `src.common.model_artifacts`, including its
SHA-256 check, then exposes the verified bytes at the stable smoke-only path above. Production
CNN artifact migration remains owned by Issue #315 and its manifest contract.

The OMR-DLN weight is different: it is externally distributed and is not silently downloaded,
redistributed, or substituted by the Docker build. Register the selected official
`YOLOv8m_Measures.pt` once in the common cache with:

```bash
python3 -m src.common.model_artifacts import \
  models/omr_dln/manifest.json /path/to/official/YOLOv8m_Measures.pt
```

The import verifies the selected version digest before atomically publishing the file to the
cache. Canonical `make verify-gpu-smoke` resolves that selected cache entry itself and mounts
it read-only at the manifest-declared container path. `OMR_DLN_MODEL_PATH` remains an explicit
compatibility override and is verified against the same selected-version digest before use.
The legacy repository-local OMR-DLN path also remains accepted for compatibility, but it is
not the canonical staging workflow.

### Source/image compatibility

The final image stores a fingerprint of runtime-sensitive source outside `/workspace` at:

```text
/opt/pdfscore-runtime/source_fingerprint.txt
```

The GPU-smoke host resolver recomputes the fingerprint from the bind-mounted checkout before
expensive model work. The canonical tag is resolved to an immutable image ID for the run. If
that tag points at different source, validation first searches local PDFScoreBar runtime images
for a matching fingerprint. If none matches, it compares the active topic with the available
`develop` reference and distinguishes a stale topic base from topic-owned runtime changes and
a genuinely stale image. A stale topic base should be refreshed onto current `develop`; it is
not a reason by itself to rebuild the image. The in-container fingerprint check remains as the
final integrity guard. Config files are intentionally outside the fingerprint so validation
configs can vary without image rebuilds; runtime-sensitive Python, Docker, and dependency
definition files remain covered.

Canonical builds record source fingerprint, commit, and branch labels in the image and write
host-side build provenance to `artifacts/docker_build_provenance.txt`. Existing pre-#352
runtime images without those labels remain inspectable through the embedded fingerprint file.
To list reusable local runtime images and their provenance, run:

```bash
python3 scripts/docker_image_resolver.py list
```

`DOCKER_IMAGE=<ref>` remains an explicit override. When it is set, validation verifies that
specific image and never silently substitutes another local image.

## Docker build and cleanup lifecycle

`make docker-build` performs the normal cleanup contract first and then builds the canonical
image. The normal cleanup removes only the canonical container:

```text
make docker-clean
  -> docker rm -f pdfscore_pipeline_gpu
```

It does **not** remove the image. Image removal is explicit:

```text
make docker-clean-full
  -> docker-clean
  -> docker rmi pdfscore_pipeline_gpu
```

This split is the Issue #261 / PR #325 contract and should be preserved. A build failure such
as `context canceled` must be diagnosed from the actual Docker/build signal and build-context
evidence; it must not be attributed to `docker rmi` merely because cleanup happened nearby.
Build-context reduction belongs to `.dockerignore` maintenance and does not change runtime
asset ownership.

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

## HOMR profiles

The dense production route uses an immutable maintained original-image HOMR profile whose
commit and runtime paths are stored in:

```text
configs/detector_profiles/maintained_original_homr.json
```

The historical Stage-E profile remains available for reproduction. Its exact provenance,
package versions, model hashes, and `/opt/` runtime paths are stored in:

```text
configs/detector_profiles/stage_e_verified_homr.json
```

The maintained original profile and current-runtime HOMR used by `current_x4_support` share
the main image/runtime but retain separate input and coordinate contracts. The historical
profile is not selected by the canonical dense route. See `TWO_HOMR_MILESTONE.md` for
reproduction requirements.

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
evaluation page images are not retained in Git. The milestone doc records that dependency
rather than silently substituting new artifacts. The Docker smoke removes the former
ignored/local-only CNN dependency. OMR-DLN remains an explicit external asset, but once its
selected version is registered in the common model cache, canonical smoke no longer depends
on an ad-hoc checkout-local model path.

## Persistent pytest-capable pipeline container

For repeated pipeline evaluation that also needs repository pytest, use a named persistent
container based on `pdfscore_pipeline_gpu`. The production runtime intentionally does not
include pytest; do not weaken or rewrite repository pytest coverage for that reason.

Create the container when absent:

```bash
docker run -dit --gpus all \
  --name pdfscore_pipeline_pytest_dev \
  -v "$PWD":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu bash
```

Start it when it already exists but is stopped:

```bash
docker start pdfscore_pipeline_pytest_dev
```

Install pytest once into the persistent validation container if it is missing:

```bash
docker exec -w /workspace pdfscore_pipeline_pytest_dev \
  /opt/venv_pipeline/bin/python -m pip install pytest
```

Run repository pytest with:

```bash
docker exec -w /workspace -e PYTHONPATH=/workspace pdfscore_pipeline_pytest_dev \
  /opt/venv_pipeline/bin/python -m pytest <tests-or-options>
```

Pipeline/evaluation commands may use the same interpreter:

```bash
docker exec -w /workspace -e PYTHONPATH=/workspace pdfscore_pipeline_pytest_dev \
  /opt/venv_pipeline/bin/python <script-or-module>
```

Remove this persistent container only when cleanup is explicitly intended; its purpose is to
avoid reinstalling validation-only tooling into short-lived production-runtime containers.

## Review helpers

The browser-based GT editor remains the preferred manual GT review helper:

```bash
python3 tools/gt_relabel_gui/server.py --mode gt --config <config.json> --port 8010 --host 0.0.0.0
```

Write generated overlays and review outputs under `logs/` or the configured review package
root according to the relevant workflow.
