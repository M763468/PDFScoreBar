# Canonical model artifact contract

[日本語](MODEL_ARTIFACT_CONTRACT.ja.md)

This document records the model/weight identities consumed by the maintained Docker and
production runtime. It complements `docs/dev/ENVIRONMENTS.md`; it does not move ownership away
from the Issues that selected or validated a model.

The common rule is:

```text
logical model ID -> selected version -> provenance -> expected integrity identity
```

A digest belongs to the selected version, not permanently to the model family. Replacing
bytes under an unchanged version/provenance identity is an integrity failure. A deliberate
model update registers a new version/provenance/digest and may coexist with the historical
version in cache.

## Path and ownership conventions

- Repository-managed downloadable artifacts use `src.common.model_artifacts` and default to
  `$XDG_CACHE_HOME/pdfscorebar/models/<model-id>/<version>/<asset>`, or
  `~/.cache/pdfscorebar/models/<model-id>/<version>/<asset>` when `XDG_CACHE_HOME` is
  unset. `PDFSCOREBAR_MODEL_CACHE` remains the explicit cache-root override.
- Image-owned assets live outside `/workspace`, normally below `/opt/pdfscore-assets`, so the
  active-checkout bind mount cannot hide them.
- External/operator-supplied assets are registered in the same host-side version namespace
  when possible and mounted read-only below `/opt/pdfscore-external/<model-id>/<version>/...`.
- Explicit path environment variables are compatibility/override paths. They must not bypass
  the integrity identity of a selected version when a manifest owns that identity.

## Inventory

### Barline CNN

- logical model ID: `barline-cnn`
- selected version: `issue296-d27-v1`
- provenance: `models/barline_cnn/manifest.json`; accepted #296 D27 checkpoint, published by
  the #315 production artifact migration
- expected SHA-256: `f41a9b578396493a83e39ed284b1781f65d6adec8f624e6b7234e917c919c5cd`
- ownership: repository-managed release artifact; canonical smoke copy is image-owned
- host materialization:
  `$XDG_CACHE_HOME/pdfscorebar/models/barline_cnn/issue296-d27-v1/cnn_classifier_epoch_9.pth`
  (or the `~/.cache/pdfscorebar/models` fallback / `PDFSCOREBAR_MODEL_CACHE` override)
- container runtime: materialized under `/opt/pdfscore-assets/model-cache/...` and exposed to
  smoke validation at `/opt/pdfscore-assets/barline_cnn_smoke.pth`
- resolver/materializer: `src.common.model_artifacts`
- explicit override: `PDFSCOREBAR_MODEL_CACHE` changes the cache root; production CNN model
  selection remains the owner of #315/configuration rather than this Docker contract
- update procedure: publish the deliberately selected replacement bytes, assign a new model
  version/release provenance, record its digest in the manifest, then materialize and validate
  it. Do not replace bytes under `issue296-d27-v1`.

### OMR-DLN measure detector (removed in #522)

- logical model ID: `omr-dln-measures` — **no longer selected**. Version `phase1-validated-v1`
  (SHA-256 `00d0bd8b399ae872f029eb38ed3985fcef33ca81cae414992b5cdb9062e91212`) remains as
  historical provenance of accepted results up to #416/#519 only.
- `models/omr_dln/manifest.json`, the OMR-DLN worker/job route, `OMR_DLN_MODEL_PATH` and the
  Docker mount were removed. Hybrid support uses x4 HOMR staff-piece support
  (`src/pipeline/steps/hybrid_consensus.py`). Settings that still name OMR-DLN fail explicitly;
  there is no fallback to the old weight.

### First-party x4 SR (`pdfscorebar-sr-x4`)

- logical model ID: `pdfscorebar-sr-x4`
- selected version/identity: `models/sr_x4/manifest.json` (`version`, `sha256`, `size_bytes`,
  RRDBNet `num_feat`/`num_block`/`num_grow_ch`)
- provenance: trained by PDFScoreBar from random initialization (Issue #533) with
  `tools/issue533/train_sr.py` on procedural synthetic notation from
  `tools/issue533/synth_score.py`; no pretrained weight, teacher model, score PDF, evaluation
  image or ground truth. The manifest records the training command, seed, script hashes and
  runtime.
- network: the vendored Apache-2.0 RRDBNet (`src/third_party/realesrgan_sr`)
- ownership: repository-tracked (like the MMR checkpoint); shipped in the distribution
- container runtime: bind-mounted `/workspace/models/sr_x4/...`
- resolver: `src.common.model_artifacts.resolve_first_party_sr`, which verifies SHA-256 before
  every load; the runtime preflight and Docker build also verify it
- explicit override: none
- update procedure: train a new version with the tracked scripts, add it with a new manifest
  `version`/`sha256`, and pass the Issue #533 Full68 gate against the current model before
  switching. Bytes that do not match the manifest fail closed.

x2 SR is not supported. The production dense route requires `sr_scale=4`.

The Real-ESRGAN release weights (`RealESRGAN_x4plus` SHA-256
`4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1`, `RealESRGAN_x2plus`
`49fafd45f8fd7aa8d31ab2a22d14d91b536c34494a5cfe31eb5d89c2fa266abb`) were used until Issue #533.
They are no longer downloaded or selected. The manifest selects the current weights.

### Maintained HOMR runtime assets

- logical model IDs: maintained HOMR segmentation (and HOMR's OCR assets). Since Issue #533 the
  transformer encoder/decoder are not part of the runtime: PDFScoreBar uses only SegNet barlines and
  masks, `HomrPredictor` skips HOMR's staff transcription, and the image does not contain the
  transformer checkpoint (Run 426).
- selected runtime version: HOMR source commit
  `457e7c6518a10ba755db2e60883419e56c4d7369`
- selected GPU model identity at that commit:
  - segmentation: `segnet_308-3296ccd40960f90ca6ab9c035cca945675d30a0f_fp16`
- provenance: upstream HOMR `onnx_checkpoints` GitHub release, selected by the pinned HOMR
  source code and materialized by `docker/init_homr_segnet.py` (SegNet and OCR initialization
  only; `homr.main --init` is not used because it also downloads the transformer)
- integrity identities:
  - segmentation package (upstream release): `8d05a37fe76829673bc9def0a7caf168e5860aa4d1a8f7ac1b6123aa69fe3d82`
  - extracted segmentation ONNX (checked by the Docker build):
    `60f495496cb41473c0521d0811d8f44b9d5cff892d287974a8aebb3eaee2fa83`
  - historical, no longer shipped: transformer encoder package
    `1390295d921a5e646a6405d23ca6a922a7dcefa97cb425317be84de5195fd49c`, decoder package
    `0d21e347661c147b073a35c880cfc52c1ae71d40a990e5964e3736a595657ce8`
- ownership: Docker image / pinned upstream HOMR runtime
- host materialization: Docker build cache only
- container runtime: HOMR package directories inside `/opt/venv_pipeline`; no `/workspace`
  dependency is allowed for canonical validation
- resolver/materializer: `docker/init_homr_segnet.py` during Docker build; the build fails on a
  SegNet hash mismatch or when a transformer ONNX checkpoint is present
- explicit override: none for canonical runtime
- update procedure: update the HOMR source pin deliberately, inventory the asset names and
  release digests selected by that commit, rebuild, probe ONNX CUDA provider, and run canonical
  smoke. A newer upstream release must not silently redefine the pinned runtime identity.

The release-package hashes above describe the archives served by upstream. They are provenance
for the selected pinned HOMR runtime; the Docker image remains the runtime ownership boundary.

### Pinned Stage-E HOMR assets

- logical model IDs: `stage-e-homr-segnet`, `stage-e-homr-transformer-encoder`,
  `stage-e-homr-transformer-decoder`
- selected version/provenance: HOMR commit `864e2882f7a41afcf8f16654728a473ae56826d6`
  with PDFScoreBar evaluator commit `bd6ae56f8be6c87088143cfbf0ba09dee94fe0d7`
- expected runtime-file SHA-256 values:
  - segmentation ONNX: `e6a7c1e84f8d2f19f20a47e0889be2392cd487d27fa77984e4877b86534dee83`
  - transformer decoder ONNX: `381646983d14f17a11e4be671aaf6e4f81727b3a9edf0cf4890109a321ffce68`
  - transformer encoder ONNX: `22a443b2ea18da82128ae52e85436d6fb4728ab68aee24adb2ac9dfc2003a30c`
- ownership: reproduction-only Docker image, intentionally historical/pinned
- host materialization: Docker build cache only
- container runtime: `/opt/homr_stage_e_profile` with isolated Python runtime
  `/opt/venv_stage_e_homr`
- resolver/materializer: `docker/Dockerfile.stage-e` `download_weights()` at the pinned source commit followed by
  explicit SHA-256 verification
- explicit override: none in the canonical Stage-E profile
- update procedure: this profile is historical provenance. A replacement is a new profile/model
  version with its own source/evaluator provenance and digests; do not mutate the recorded
  Stage-E identity in place.

## Updating a model

For any manifest-owned artifact:

1. select the replacement intentionally and record its upstream/training provenance;
2. assign a new logical version (do not reuse the old version for different bytes);
3. compute/record the expected digest for that version;
4. update the cache/runtime identity if it embeds the version;
5. materialize/import and verify the selected bytes;
6. run the validation class required by `docs/dev/VALIDATION_POLICY.md`.

A test must continue to prove both halves of the contract: a declared version+digest update is
accepted, while changing bytes without changing the selected identity fails integrity checks.
