# Environment & Tooling Guide

This document records maintained development and evaluation environments. Historical
one-off containers and branch-specific worktrees are not current operating instructions
unless an active Issue explicitly revives them.

## Canonical full-pipeline runtime

### `pdfscore_pipeline_gpu`

This is the maintained production-only full-pipeline Docker image. Its `/opt` payload
contains no historical Stage-E runtime; retained compatibility tooling uses the separate
`pdfscore_stage_e_reproduction` image.

- Dockerfile: `Dockerfile`
- Build target: `make docker-build`
- Canonical GPU validation entry point: `make verify-gpu-smoke`
- Production-representative detector accuracy smoke: `make run-smoke`
- Pipeline entry point: `make run-pipeline CONFIG=<config.yaml>`
- Container interpreter: `/opt/venv_pipeline/bin/python`
- Normal mounted repository root: `/workspace`

The image installs project/runtime dependencies and the maintained HOMR ONNX provider patch
from `docker/patch_homr_onnx_provider.py`. Use this image for the verified dense production
route and full-pipeline validation that needs Docker/GPU execution. Historical Stage-E
reproduction uses a separate image (see below).

`make verify-gpu-smoke` is the authoritative environment gate. Before pipeline execution it
runs `scripts/docker_runtime_validation.sh`, which checks the bind-mounted source against the
source fingerprint recorded when the image was built, validates required assets, and probes
CUDA inside the container. The standard `configs/smoke_test.yaml` then runs the current dense
production detector contract on `Va_Prokofiev_Symphony1/page_001` from a fresh 360-DPI PDF
render and applies an explicit GT accuracy gate. The smoke fails if the rendered input no longer
matches the accepted evaluation image identity, if the detector settings drift from
`configs/dense_full_pipeline.yaml`, or if the page produces any hard FP/FN/soft residual.
Host `nvidia-smi` output is metadata only; the container CUDA probe is authoritative.

`make run-smoke` uses the same canonical runtime validation and accuracy gate without the outer
`gpu_smoke.sh` metadata/timeout wrapper. Smoke runs receive unique run IDs, so rerunning the
check does not require deleting root-owned Docker artifacts first.

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
| verified historical Stage-E HOMR stack | reproduction image only | `/opt/venv_stage_e_homr`, `/opt/homr_stage_e_profile`, `/opt/pdfscore_stage_e_profile` |
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
be reused across worktrees. An existing checkout-local cache can still be selected explicitly
with `PDFSCOREBAR_MODEL_CACHE="$PWD/.model_cache"` during migration; it is no longer an
implicit fallback.

The Real-ESRGAN resolver uses `PDFSCORE_REALESRGAN_WEIGHTS_DIR` in the image and retains the
legacy checkout path only as a host-development fallback. A canonical Docker smoke must not
require weights to be manually copied into `external/realesrgan/weights`.

The image-owned smoke CNN path remains available for legacy/workflow-only fixtures, but it is
not the standard accuracy smoke and must not be used as production-accuracy evidence. The
standard smoke uses the same `models/barline_cnn/manifest.json`, threshold, dense detector route,
and x4 support contract as `configs/dense_full_pipeline.yaml`. Docker still materializes the
tracked manifest through `src.common.model_artifacts`, including its SHA-256 check, and exposes
the verified bytes at the stable smoke-only compatibility path above.

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

Canonical Docker validation keeps two different identities deliberately separate:

- the **source fingerprint** is broad provenance for the checkout used to build an image; it
  includes bind-mounted application Python and remains useful for identifying source drift;
- the **runtime compatibility fingerprint** covers the image/environment-defining contract:
  Dockerfile instructions across the full build (including post-copy image-owned materialization),
  `pyproject.toml`, the HOMR ONNX-provider build patch, the image-owned barline-CNN manifest,
  and the project-local model-artifact materializer/import chain executed while that CNN is
  materialized. Dockerfile comments plus only the recognized source-provenance-only
  ARG/LABEL/fingerprint-emission commands are normalized out; unknown command spellings remain
  hashed rather than being ignored.

The GPU-smoke host resolver first resolves the mutable canonical tag to an immutable image ID.
Every recognized image is then checked against the runtime compatibility fingerprint before it
is accepted. Source-fingerprint equality affects provenance diagnostics only; it never bypasses
compatibility validation. When source provenance differs, the resolver derives the compatibility
fingerprint from the recognized PDFScoreBar image's retained build-source copy and compares that
with the active checkout. Therefore a Python-only change under bind-mounted `src/` can reuse an
existing compatible image, while dependency, CUDA/HOMR build-contract, patch, or image-owned
model-contract changes still require compatible image selection or a rebuild.

If the compatibility contract differs, validation compares the active topic with the available
`origin/develop` (or local `develop`) reference and distinguishes a stale topic base from
topic-owned environment changes and a genuinely stale image. Fetch `origin` before
classification when that reference may be outdated. A stale topic base should be refreshed onto
current `develop`; it is not a reason by itself to rebuild the image. Except for that case, the
resolver searches local PDFScoreBar images for a matching runtime compatibility fingerprint
before recommending another build.

The in-container preflight runs the active checkout's contract code after host-side image
resolution and rechecks the bind-mounted compatibility fingerprint, protecting against source
changes between selection and execution. A source-fingerprint mismatch is reported as provenance
rather than treated by itself as an image incompatibility.

Canonical builds record source fingerprint, commit, and branch labels in the image and write
host-side build provenance to `artifacts/docker_build_provenance.txt`. Existing pre-#352
runtime images without those labels remain inspectable through the embedded source fingerprint;
their runtime compatibility can be derived from the retained build-source copy without requiring
a rebuild solely to add new metadata.
To list reusable local runtime images and their provenance, run:

```bash
python3 scripts/docker_image_resolver.py list
```

`DOCKER_IMAGE=<ref>` remains an explicit override. When it is set, validation verifies that
specific image and never silently substitutes another local image.

## Docker build and cleanup lifecycle

`make docker-build` builds the selected image without removing containers or images used by
other worktrees. Container cleanup is a separate explicit command:

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

The container/image cleanup split from Issue #261 / PR #325 is preserved; Issue #352 removes
implicit container cleanup from builds to avoid interrupting other worktrees. A build failure such
as `context canceled` must be diagnosed from the actual Docker/build signal and build-context
evidence; it must not be attributed to `docker rmi` merely because cleanup happened nearby.
Build-context reduction belongs to `.dockerignore` maintenance and does not change runtime
asset ownership.

`make docker-build` updates the shared `pdfscore_pipeline_gpu` tag by default and records the
source fingerprint/commit/branch used for that build. When a topic branch intentionally changes
runtime-sensitive files and should not repoint the shared tag, build an explicit temporary tag:

```bash
make docker-build DOCKER_IMAGE=pdfscore_issue352
```

The validation resolver can reuse that image by fingerprint without requiring the mutable
canonical tag to point at it. `make docker-clean` never removes runtime images. Full image
removal remains explicit; use `DOCKER_IMAGE=<ref> make docker-clean-full` when intentionally
removing a non-default tag.

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

The historical Stage-E profile remains available as an isolated compatibility component
for retained historical tooling. It is not a production dependency: the root `Dockerfile` contains no historical venv, cloned source,
model downloads, or markers. Canonical preflight validates the maintained profile paths
and the exact HOMR/evaluator marker values from its manifest.

Build the reproduction extension explicitly from a production image:

```bash
make docker-build
make -f tools/issue120/Makefile.stage_e.mk docker-build-stage-e
make -f tools/issue120/Makefile.stage_e.mk run-issue120-stage-e-full
```

The extension is `docker/Dockerfile.stage-e`; its default output is
`pdfscore_stage_e_reproduction`. For an isolated build, set
`ISSUE120_PRODUCTION_IMAGE=<production-image>` and `ISSUE120_STAGE_E_IMAGE=<reproduction-image>`
on those Make commands. Pin the base to an immutable image ID when retaining reproduction
provenance. Its separate asset-contract label excludes it from canonical image resolution,
including explicit overrides to production preflight. This extension retains the historical
source commits, model SHA-256 checks, and isolated dependency versions; it does not select the historical profile for production.

The old Stage-E name is retained as a compatibility identifier for #120 tools, manifests,
and accepted historical results. Its remaining purpose is exposing the pinned component to
retained tooling and component comparison experiments. This extension inherits the current production main
venv; it does not reconstruct the complete historical two-HOMR environment or guarantee
its full68 metrics. Full historical environment reproduction is outside #398 acceptance.
The canonical `maintained_original` route does not need it. Removing that compatibility contract or renaming its interfaces would be a separate retirement decision;
no historical data, source pins, or profile is deleted here. The exact input images are still
an external prerequisite, as recorded in the milestone below.

The component profile's exact provenance, package versions, model hashes, and `/opt/` runtime
paths are stored in:

```text
configs/detector_profiles/stage_e_verified_homr.json
```

The maintained original profile and current-runtime HOMR used by `current_x4_support` share
the main image/runtime but retain separate input and coordinate contracts. The historical
profile is not selected by the canonical dense route. See `TWO_HOMR_MILESTONE.md` for
reproduction requirements.

## Historical evaluation environments

### `homr_eval_gpu`

`Dockerfile.homr` is retained for isolated/historical HOMR evaluation. It is not the default
full-pipeline environment. Use it only when an Issue explicitly requires isolated HOMR
behavior or historical reproduction.

The former SR-specific `sr_eval_gpu` / `/opt/venv_sr` compatibility selector and the inert
`container_name: sr_eval_gpu_exp` dense-config key were removed by Issue #379. Maintained heavy
pipeline subprocesses now select only the unified `pdfscore_pipeline_gpu` environment, with
`PIPELINE_PYTHON` retained as the explicit interpreter override when no maintained heavy-step
environment is selected. Historical tools that still hard-code the former SR environment are not
setup guidance and are tracked separately for retirement.

## Data and generated output policy

- Repository-retained evaluation fixtures are documented in `data/README.md` and relevant
  Issue retention records.
- Generated runs, metrics, model outputs, and large intermediate artifacts belong under
  ignored `logs/` paths unless an explicit retention policy says otherwise.
- Local scratch/workbench material belongs under ignored `tmp/`; do not recreate a tracked `data/workbench/` tree.
- For CNN dataset work, stage active datasets under repository `datasets/` before bulk
  operations; use `/mnt/*` as source/archive rather than metadata-heavy scratch space.

The accepted two-HOMR milestone is **not fresh-clone reproducible** through the current
compatibility extension: its exact evaluation images remain external, and the extension does
not reconstruct the complete historical main dependency stack. The milestone doc separates
those requirements from the retained Stage-E component pins. The Docker smoke removes the
former ignored/local-only CNN dependency. OMR-DLN remains an explicit external asset, but once its
selected version is registered in the common model cache, canonical smoke no longer depends
on an ad-hoc checkout-local model path.

## Persistent pytest-capable pipeline container

For repeated pipeline evaluation that also needs repository pytest, use a named persistent
container based on `pdfscore_pipeline_gpu`. The production runtime intentionally does not
include pytest; do not weaken or rewrite repository pytest coverage for that reason.

Create the container when absent. Resolve the production tag to a verified immutable image,
and mount the registered external OMR-DLN weight so this container can run pipeline checks:

```bash
image_id=$(python3 scripts/docker_image_resolver.py resolve \
  --repo-root . --image-ref pdfscore_pipeline_gpu --explicit)
omr_host=$(python3 -m src.common.model_artifacts verify models/omr_dln/manifest.json)
omr_runtime=$(python3 -c \
  'import json; print(json.load(open("models/omr_dln/manifest.json"))["runtime_path"])')
docker run -dit --gpus all \
  --name pdfscore_pipeline_pytest_dev \
  -v "$PWD":/workspace \
  -v "$omr_host:$omr_runtime:ro" \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  -e OMR_DLN_MODEL_PATH="$omr_runtime" \
  "$image_id" bash
```

Updating an image tag does not change an existing container's image. After a Docker/runtime
update, inspect the container's immutable image ID and resolve that ID against the active
checkout before reusing it:

```bash
docker inspect pdfscore_pipeline_pytest_dev --format '{{.Image}}'
python3 scripts/docker_image_resolver.py resolve --repo-root . \
  --image-ref "$(docker inspect pdfscore_pipeline_pytest_dev --format '{{.Image}}')" --explicit
```

When incompatible, save its inspect metadata, stop it if running, and rename it to an unused
archive name before creating the replacement. This preserves its writable layer and bind
mounts; do not delete it as part of a routine refresh. Reinstall pytest in the new development
container only. Check CUDA, assets and production provenance again before pipeline use.

Start a compatible container when it already exists but is stopped:

```bash
docker start pdfscore_pipeline_pytest_dev
```

Install development test tools once into the persistent validation container. Git is needed
by the repository's mocked Docker lifecycle tests; neither tool is added to the production
image:

```bash
docker exec pdfscore_pipeline_pytest_dev \
  /bin/sh -c 'apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*'
# Root in this container accesses the host-owned checkout; trust this mount only.
docker exec pdfscore_pipeline_pytest_dev git config --global --add safe.directory /workspace
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

### Production-only adoption snapshot (#398)

The local maintained environment was updated on 2026-10-03:

| Reference | Adopted environment |
| --- | --- |
| `pdfscore_pipeline_gpu:latest` | production-only image `5311cf22ab01`, built from application revision `b25af348` |
| `pdfscore_stage_e_reproduction:latest` | retained Stage-E component compatibility image `c5da1954371d`; current main venv, not a complete historical environment |
| `pdfscore_pipeline_pytest_dev` | running development container based on `5311cf22ab01`, with GPU, checkout/external-model mounts, pytest 8.4.2 and Git |
| `pdfscore_pipeline_gpu:before-issue398` | retained prior all-in-one image, excluded from current setup instructions |
| `pdfscore_pipeline_pytest_dev_before_issue398` | stopped archive of the old development container; its writable layer was preserved |

Other Issue-scoped or historical containers were not promoted to maintained environments.
This is an adoption snapshot; tags can change later. Use `docker image inspect` and
`docker inspect` to establish current identities. Inspect snapshots, migration commands,
preflight and test evidence are retained locally under `logs/issue398/environment-update/`.

## Review helpers

The browser-based GT editor remains the preferred manual GT review helper:

```bash
python3 tools/gt_relabel_gui/server.py --mode gt --config <config.json> --port 8010 --host 0.0.0.0
```

Write generated overlays and review outputs under `logs/` or the configured review package
root according to the relevant workflow.
