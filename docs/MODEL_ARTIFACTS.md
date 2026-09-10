# Production Model Artifacts

Production-consumed learned checkpoints must not use `logs/` as their durable source of truth.
`logs/` remains experiment/generated output. Production model identity is instead defined by a
small tracked manifest plus an immutable release asset.

## Contract

Each production model manifest uses schema `pdfscorebar.model_artifact.v1` and records:

- a logical `model_id` and `version`;
- the expected model `architecture`;
- the GitHub Release repository, tag, and asset name;
- the exact SHA-256 digest of the accepted bytes;
- a relative `cache_path` below the local model cache;
- provenance needed to identify the accepted training/evaluation decision.

The release asset is the durable binary source. The manifest is the repository-tracked identity
and integrity contract. Do not edit or replace an existing release asset in place; publish a new
version/tag and update the manifest in a reviewed change.

## Local cache

By default, materialized models live under repo-local `.model_cache/`, which is ignored by Git.
Set `PDFSCOREBAR_MODEL_CACHE` to use another persistent cache root, for example a mounted model
volume in a container or a dedicated local artifact disk.

The cache is disposable: deleting it must not destroy the durable model because the release asset
and tracked manifest are sufficient to restore it.

## Materialize and verify

Materialization is explicit. Production execution must not silently download a missing model or
fall back to another checkpoint.

```bash
python -m src.common.model_artifacts materialize models/<model>/manifest.json
```

A cached model can be verified without downloading:

```bash
python -m src.common.model_artifacts verify models/<model>/manifest.json
```

To print the expected cache path:

```bash
python -m src.common.model_artifacts path models/<model>/manifest.json
```

Materialization downloads to a temporary file, verifies SHA-256, then atomically publishes the
file to the cache. A missing cached artifact, corrupt cached artifact, malformed manifest, or
release download with the wrong digest fails loudly. Use `--force` only to deliberately repair a
known-bad cached copy from the same manifest/release contract.

For private GitHub assets, `GITHUB_TOKEN` may be supplied to the materializer. Do not store tokens
in manifests or configuration.

## Publishing a replacement model

1. Finish model selection and evaluation before artifact publication.
2. Compute SHA-256 for the exact accepted checkpoint bytes.
3. Publish those exact bytes under a new immutable GitHub Release tag.
4. Add/update the tracked manifest with the release coordinates, digest, and provenance.
5. Materialize from an empty cache and verify that the digest matches the original checkpoint.
6. Load the materialized checkpoint through the affected production route.
7. Run validation proportional to the change. Artifact relocation alone does not justify model
   quality retuning or a new full evaluation when bytes and scoring contract are unchanged.

Never delete the only local copy until the release asset has been uploaded, downloaded again, and
verified against the tracked digest.

## Cleanup

Experiment checkpoints under `logs/` may be removed only after the accepted production bytes have
been published and independently materialized/verified. Cached files under `.model_cache/` may be
removed at any time and recreated from the manifest.
