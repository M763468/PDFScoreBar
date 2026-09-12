# Production Model Artifacts

Production-consumed learned checkpoints must not use `logs/` as their durable source of truth.
`logs/` remains experiment/generated output. Production model identity is instead defined by a
small tracked manifest plus a versioned GitHub Release asset.

## Contract

Each production model manifest uses schema `pdfscorebar.model_artifact.v1` and records:

- a logical `model_id` and `version`;
- the expected model `architecture`;
- the GitHub Release repository, tag, and asset name;
- the exact SHA-256 digest and byte size of the accepted bytes;
- a relative `cache_path` below the local model cache;
- provenance needed to identify the accepted training/evaluation decision and production scoring
  contract.

The release asset is the durable binary source. The manifest is the repository-tracked identity
and integrity contract. Release assets are treated as immutable by project policy: do not edit,
delete/re-upload, or replace an existing production asset in place. Publish a new version/tag and
update the manifest in a reviewed change. SHA-256 verification remains authoritative even if the
hosting service itself would technically allow an asset to be replaced.

## Current production barline CNN

The verified dense Stage-E route uses the Issue #296 D27 checkpoint recorded in:

```text
models/barline_cnn/manifest.json
```

Immutable identity/provenance for this version:

- model: `barline-cnn@issue296-d27-v1`
- architecture: `efficientnet_b0`
- accepted experiment: D27 current-producer candidate-aligned EfficientNet-B0
- accepted Issue / PR: `#296` / `#310`
- accepted merge commit: `49a9da6a5f352e48cffd79306d75acdc8da3d9e7`
- historical source path of the exact accepted bytes:
  `logs/cnn_barline_classification/issue296_efficientnet_b0_current_candidate_aligned_v1/cnn_classifier_epoch_9.pth`
- release tag: `model-barline-cnn-issue296-d27-v1`
- release asset: `cnn_classifier_epoch_9.pth`
- SHA-256: `f41a9b578396493a83e39ed284b1781f65d6adec8f624e6b7234e917c919c5cd`
- size: `16339553` bytes
- local cache path: `.model_cache/barline_cnn/issue296-d27-v1/cnn_classifier_epoch_9.pth`
- production threshold: `0.4965248107910156`
- `cnn_apply_nms: false`
- #296 training/evaluation matcher provenance: `center_anchor`, `vov_threshold=0.5`,
  `xdist_threshold=12.0`

Issue #315 publication verification proved that the local accepted checkpoint, the freshly
downloaded Release asset, and the empty-cache materialized artifact have the same SHA-256 and
size. The verified Stage-E resolver then loaded the materialized checkpoint successfully. This is
artifact relocation only; it does not change the accepted #296 checkpoint bytes, architecture,
threshold, crop/scoring path, or model-quality decision.

## Local cache

By default, materialized models live under repo-local `.model_cache/`, which is ignored by Git.
Set `PDFSCOREBAR_MODEL_CACHE` to use another persistent cache root, for example a mounted model
volume in a container or a dedicated local artifact disk.

The cache is disposable: deleting it must not destroy the durable model because the release asset
and tracked manifest are sufficient to restore it.

## Materialize and verify

Materialization is explicit. Production execution must not silently download a missing model or
fall back to another checkpoint.

For the current production barline CNN:

```bash
python -m src.common.model_artifacts materialize models/barline_cnn/manifest.json
```

A cached model can be verified without downloading:

```bash
python -m src.common.model_artifacts verify models/barline_cnn/manifest.json
```

To print the expected cache path:

```bash
python -m src.common.model_artifacts path models/barline_cnn/manifest.json
```

Materialization downloads to a temporary file, verifies SHA-256, then atomically publishes the
file to the cache. A missing cached artifact, corrupt cached artifact, malformed manifest, or
release download with the wrong digest fails loudly. Use `--force` only to deliberately repair a
known-bad cached copy from the same manifest/release contract.

For private GitHub assets, `GITHUB_TOKEN` may be supplied to the materializer. Do not store tokens
in manifests or configuration.

## Publishing a replacement model

1. Finish model selection and evaluation before artifact publication.
2. Compute SHA-256 and byte size for the exact accepted checkpoint bytes.
3. Publish those exact bytes under a new GitHub Release tag; never overwrite an existing production
   asset.
4. Fresh-download the asset and prove SHA-256/size identity with the accepted source bytes.
5. Add/update the tracked manifest with the release coordinates, digest, size, scoring contract,
   and accepted Issue/PR provenance.
6. Materialize from an empty cache and verify that the digest matches the original checkpoint.
7. Load the materialized checkpoint through the affected production route.
8. Run validation proportional to the change. Artifact relocation alone does not justify model
   quality retuning or a new full evaluation when bytes and scoring contract are unchanged.

Never delete the only local copy until the release asset has been uploaded, downloaded again, and
verified against the tracked digest.

## Cleanup

Experiment checkpoints under `logs/` may be removed only after the accepted production bytes have
been published and independently materialized/verified. Cached files under `.model_cache/` may be
removed at any time and recreated from the manifest.
