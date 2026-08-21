# PDFScoreBar

PDFScoreBar is a score-processing pipeline for barline detection, system/measure grouping,
measure-number recognition, correction, and final output generation.

## Current architecture

The canonical description of the production pipeline is:

- [`docs/PIPELINE_ARCHITECTURE.md`](docs/PIPELINE_ARCHITECTURE.md) — current dense
  production caller chain, two-HOMR ownership, coordinate/process boundaries, MMR reuse.
- [`docs/TWO_HOMR_MILESTONE.md`](docs/TWO_HOMR_MILESTONE.md) — accepted Issue #274 / PR
  #279 high-accuracy two-HOMR milestone and reproduction contract.
- [`docs/README.md`](docs/README.md) — documentation index and historical/current
  classification.

Do not infer the current pipeline from old Issue investigation documents or stale generated
Graphify output. Source/tests and the canonical architecture document are authoritative.

## Development baseline

Normal development work targets `develop`; see [`docs/BRANCH_POLICY.md`](docs/BRANCH_POLICY.md).
Before running repository commands, read [`docs/ENVIRONMENTS.md`](docs/ENVIRONMENTS.md) and
choose validation using [`docs/dev/VALIDATION_POLICY.md`](docs/dev/VALIDATION_POLICY.md).

Common commands:

```bash
make help
make test-fast
make lint
make docker-build
make run-smoke
make run-pipeline CONFIG=configs/dense_full_pipeline.yaml
```

The maintained full-pipeline runtime is `pdfscore_pipeline_gpu`. Generated experiment and
pipeline outputs belong under `logs/` unless an explicit retention policy says otherwise.

## AI / repository navigation

Repository-specific agent rules live in [`AGENTS.md`](AGENTS.md). Graphify is a first-pass
navigation aid; its committed graph must be refreshed after meaningful architecture changes.
See [`docs/ai-workflow/GRAPHIFY.md`](docs/ai-workflow/GRAPHIFY.md).
