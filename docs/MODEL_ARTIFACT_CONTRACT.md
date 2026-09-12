# Canonical model artifact contract

This document records the model/weight identities consumed by the maintained Docker and
production runtime. It complements `docs/ENVIRONMENTS.md`; it does not move ownership away
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
  `.model_cache/<model-id>/<version>/<asset>` (or `PDFSCOREBAR_MODEL_CACHE` when a shared
  host cache is configured).
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
- host materialization: `.model_cache/barline_cnn/issue296-d27-v1/cnn_classifier_epoch_9.pth`
  (or the same suffix below `PDFSCOREBAR_MODEL_CACHE`)
- container runtime: materialized under `/opt/pdfscore-assets/model-cache/...` and exposed to
  smoke validation at `/opt/pdfscore-assets/barline_cnn_smoke.pth`
- resolver/materializer: `src.common.model_artifacts`
- explicit override: `PDFSCOREBAR_MODEL_CACHE` changes the cache root; production CNN model
  selection remains the owner of #315/configuration rather than this Docker contract
- update procedure: publish the deliberately selected replacement bytes, assign a new model
  version/release provenance, record its digest in the manifest, then materialize and validate
  it. Do not replace bytes under `issue296-d27-v1`.

### OMR-DLN measure detector

- logical model ID: `omr-dln-measures`
- selected version: `phase1-validated-v1`
- provenance: `models/omr_dln/manifest.json`; official `dmgonzalez8/OMR` model distribution
  and the exact bytes used by the final Phase 1 validation in PR #330
- expected SHA-256: `00d0bd8b399ae872f029eb38ed3985fcef33ca81cae414992b5cdb9062e91212`
- ownership: external/operator-supplied
- host materialization: `.model_cache/omr-dln-measures/phase1-validated-v1/YOLOv8m_Measures.pt`
  (or the same suffix below `PDFSCOREBAR_MODEL_CACHE`)
- container runtime: `/opt/pdfscore-external/omr-dln-measures/phase1-validated-v1/YOLOv8m_Measures.pt`
- resolver/materializer: `src.common.model_artifacts verify/import`; canonical Docker validation
  resolves the selected cached artifact and mounts it read-only
- explicit override: `OMR_DLN_MODEL_PATH`, retained for compatibility; the pointed file is
  verified against the selected manifest digest before use
- update procedure: obtain the intentionally selected official replacement, register a new
  version/provenance/digest/cache path in the manifest, import it with
  `python3 -m src.common.model_artifacts import ...`, and validate. The Phase 1 digest is
  historical provenance, not a permanent family hash.

Upstream distributes the model separately from the source repository. No explicit model
redistribution license was found in the upstream repository during Issue #329 Phase 2, so
PDFScoreBar does not silently redistribute or automatically substitute the model. The
operator import workflow verifies known selected bytes before publishing them into the common
cache.

### Real-ESRGAN x4

- logical model ID: `realesrgan-x4plus`
- selected version: upstream release `v0.1.0`, asset `RealESRGAN_x4plus.pth`
- provenance: official `xinntao/Real-ESRGAN` GitHub release; runtime package source is pinned
  separately in the Dockerfile
- integrity identity: selected release/asset plus SHA-256
  `4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1`
- ownership: Docker image
- host materialization: Docker build cache only; no canonical checkout-local copy required
- container runtime: `/opt/pdfscore-assets/realesrgan/RealESRGAN_x4plus.pth`
- resolver: `src.common.realesrgan_assets`
- explicit override: `PDFSCORE_REALESRGAN_WEIGHTS_DIR` (legacy checkout fallback remains for
  host development)
- update procedure: change the selected upstream release/asset deliberately, record/verify the
  new digest, rebuild the image, then run the Docker/GPU contract gates.

### Real-ESRGAN x2

- logical model ID: `realesrgan-x2plus`
- selected version: upstream release `v0.2.1`, asset `RealESRGAN_x2plus.pth`
- provenance: official `xinntao/Real-ESRGAN` GitHub release; runtime package source is pinned
  separately in the Dockerfile
- integrity identity: selected release/asset plus SHA-256
  `49fafd45f8fd7aa8d31ab2a22d14d91b536c34494a5cfe31eb5d89c2fa266abb`
- ownership: Docker image
- host materialization: Docker build cache only; no canonical checkout-local copy required
- container runtime: `/opt/pdfscore-assets/realesrgan/RealESRGAN_x2plus.pth`
- resolver: `src.common.realesrgan_assets`
- explicit override: `PDFSCORE_REALESRGAN_WEIGHTS_DIR` (legacy checkout fallback remains for
  host development)
- update procedure: same version/provenance/digest rule as x4; rebuild and rerun Docker/GPU
  validation after an intentional update.

The Real-ESRGAN hashes above identify the currently selected upstream release bytes. Docker
must fail the build if downloaded bytes no longer match these identities rather than accepting
silent replacement.

### Maintained HOMR runtime assets

- logical model IDs: maintained HOMR segmentation plus transformer encoder/decoder (and HOMR
  init-managed OCR assets)
- selected runtime version: HOMR source commit
  `b377620a3a55bd7ff657481cec5b688dfbc9cee9`
- selected GPU model identities at that commit:
  - segmentation: `segnet_308-3296ccd40960f90ca6ab9c035cca945675d30a0f_fp16`
  - transformer encoder: `encoder_pytorch_model_331-e10346542968cc71fbcce0c0696f3ac963f11ae1_fp16`
  - transformer decoder: `decoder_pytorch_model_331-e10346542968cc71fbcce0c0696f3ac963f11ae1_fp16`
- provenance: upstream HOMR `onnx_checkpoints` GitHub release, selected by the pinned HOMR
  source code and materialized with `python -m homr.main --init --gpu force`
- upstream release-package SHA-256 identities:
  - segmentation package: `8d05a37fe76829673bc9def0a7caf168e5860aa4d1a8f7ac1b6123aa69fe3d82`
  - transformer encoder package: `13c67af5f192426726057f62e54f46bff4efb471e4a8a2f4631eda11079f2bfc`
  - transformer decoder package: `dd702a8d4e9e04b523f6e9d6bda34e012d265fe8550d6b36f5a1684a1f757cca`
- ownership: Docker image / pinned upstream HOMR runtime
- host materialization: Docker build cache only
- container runtime: HOMR package directories inside `/opt/venv_pipeline`; no `/workspace`
  dependency is allowed for canonical validation
- resolver/materializer: HOMR's pinned `--init --gpu force` path during Docker build
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
- ownership: Docker image, intentionally historical/pinned
- host materialization: Docker build cache only
- container runtime: `/opt/homr_stage_e_profile` with isolated Python runtime
  `/opt/venv_stage_e_homr`
- resolver/materializer: Dockerfile `download_weights()` at the pinned source commit followed by
  explicit SHA-256 verification
- explicit override: none in the canonical Stage-E profile
- update procedure: this profile is historical provenance. A replacement is a new profile/model
  version with its own source/evaluator provenance and digests; do not mutate the recorded
  Stage-E identity in place.

## OMR-DLN registration workflow

Obtain the official `YOLOv8m_Measures.pt` through the upstream distribution channel, then run
once for the selected manifest version:

```bash
python3 -m src.common.model_artifacts import \
  models/omr_dln/manifest.json /path/to/YOLOv8m_Measures.pt
```

The import rejects bytes that do not match the selected version digest and publishes verified
bytes atomically. Afterwards `make verify-gpu-smoke` resolves the cache entry itself. A shared
cache can be selected explicitly with `PDFSCOREBAR_MODEL_CACHE`; this is preferable when
validating multiple clean worktrees against the same registered external artifact.

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
