# Issue #245 focused upstream detector investigation

This directory contains temporary investigation tooling for Issue #245.

## Current boundary

Static history inspection and focused page-001 experiments established the following:

- PR #181 completed all 68 pages with the detector target, but that acceptance result used freshly reconstructed dense/probe candidates injected into the full pipeline. It did not establish that baseline HOMR reproduced retained historical source artifacts.
- The tracked baseline HOMR generation code has not changed between the PR #181 merge checkpoint and the current `develop` branch.
- Current `HybridDetector` may select either the in-process HOMR path or the evaluator fallback path depending on whether all imports guarded by `_HOMR_AVAILABLE` succeed.
- In the current managed runtime, `_HOMR_AVAILABLE=true` and production selects the in-process path.
- On the corrected-rerun page-001 image, production in-process emitted 177 predictions and the evaluator emitted 108. They shared 97 tolerant matches, with 80 production-only and 11 evaluator-only predictions.
- Disabling only `detect_thin_vertical_runs` reduced in-process output to 79 predictions. All 79 matched evaluator output, and the evaluator's remaining 29 predictions were all thin-barline additions.
- Production vs no-thin had 79 matches and 98 production-only predictions. All 98 were tagged `system_index=-2`.
- Core HOMR output is therefore aligned between the two entrypoints. The observed baseline route divergence is isolated to thin-barline augmentation and its configuration.
- The corrected-rerun `source.png` and canonical full-68 image are not byte-identical. Historical baseline comparison must use the canonical image so input drift is not mixed into route drift.

This is not evidence for a production-default change. The focused experiments intentionally stop before dense reconstruction, CNN scoring, physical-measure construction, MMR, and numbering.

## Corrected-rerun page-001 probe

The initial probe resolves `page_001` from:

```text
logs/issue236_pipeline_connected_review_smoke/source_run/review/manual_correction_input.json
```

From the Issue #245 worktree, use the worktree code and bind the main clone's ignored `logs/` directory:

```bash
ISSUE245_HOST_COMMIT="$(git rev-parse HEAD)"
ISSUE245_HOST_BRANCH="$(git branch --show-current)"

docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -v /home/masaki_muramatsu/ws_PDFScoreBar/logs:/workspace/logs \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  -e ISSUE245_HOST_COMMIT="$ISSUE245_HOST_COMMIT" \
  -e ISSUE245_HOST_BRANCH="$ISSUE245_HOST_BRANCH" \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python \
  tools/issue245/run_page001_homr_probe.py --force
```

The legacy evaluator requires the temporary API compatibility shim because current HOMR requires GPU-awareness in `download_weights` and `ProcessingConfig`. The shim changes only the investigation subprocess.

## Thin-barline isolation result

`HomrPredictor` adds `detect_thin_vertical_runs` candidates after core HOMR inference and tags inserted or replaced candidates with `system_index=-2`.

The isolated child process disables only this augmentation:

```bash
docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -v /home/masaki_muramatsu/ws_PDFScoreBar/logs:/workspace/logs \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python \
  tools/issue245/run_no_thin_variant.py --force
```

Observed corrected-rerun page-001 matrix:

| Comparison | Left | Right | Matches | Left only | Right only |
| --- | ---: | ---: | ---: | ---: | ---: |
| production vs evaluator | 177 | 108 | 97 | 80 | 11 |
| no-thin vs evaluator | 79 | 108 | 79 | 0 | 29 |
| production vs no-thin | 177 | 79 | 79 | 98 | 0 |

Every unmatched prediction in these comparisons was tagged as a thin-barline addition. The production-specific baseline configuration is much more permissive than the evaluator default and creates long one-pixel-wide candidates.

## Canonical historical comparison

The corrected-rerun source image has SHA-256:

```text
ded2967352ca8323fedd1e04dd31677a639c34814a0ccc2388264a6fc851d930
```

The canonical full-68 `Va_Prokofiev_Symphony1/page_001.png` has SHA-256:

```text
48e073dd8184495b9751ad62e85a872bc93cce751ba0a8c988300f7c5ae444a6
```

`run_canonical_historical_probe.py` verifies the canonical hash, freshly generates three current routes on that exact image, and compares each with the retained historical baseline:

1. production in-process thin-barline configuration;
2. evaluator default thin-barline configuration;
3. in-process with thin-barline augmentation disabled.

The historical artifact is read-only comparison evidence. It is not copied into or consumed by a production detector route.

```bash
docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -v /home/masaki_muramatsu/ws_PDFScoreBar/logs:/workspace/logs \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python \
  tools/issue245/run_canonical_historical_probe.py --force
```

Default retained historical root:

```text
logs/hybrid_pipeline_bench/eval2_Va_Prokofiev_Symphony1_page_001_20260131_103421
```

Expected report:

```text
logs/issue245_focused_homr_probe/
  canonical_va_prokofiev_symphony1_page001/
    canonical_historical_probe_report.json
```

## Decision gate

- Select the thin-barline configuration that is closest to the retained historical baseline on the canonical image.
- Repeat the selected one-variable route on a small representative page set before full-68.
- Do not change the production default until detector, physical-measure, MMR, page-033 veto, and corrected-final page-001 gates pass.
- Do not revive `production_dense_v1` or use retained historical artifacts as production inputs.
