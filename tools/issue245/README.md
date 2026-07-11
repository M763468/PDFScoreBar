# Issue #245 focused upstream detector investigation

This directory contains temporary investigation tooling for Issue #245.

## Current boundary

Static history inspection and the first page-001 A/B established the following:

- PR #181 completed all 68 pages with the detector target, but that acceptance result used freshly reconstructed dense/probe candidates injected into the full pipeline. It did not establish that baseline HOMR reproduced the retained historical source artifacts.
- The tracked baseline HOMR generation code has not changed between the PR #181 merge checkpoint and the current `develop` branch.
- Current `HybridDetector` may select either the in-process HOMR path or the evaluator fallback path depending on whether all imports guarded by `_HOMR_AVAILABLE` succeed.
- In the current managed runtime, `_HOMR_AVAILABLE=true` and production selects the in-process path.
- On the identical page-001 image, the production in-process route emitted 177 predictions while the evaluator route emitted 108. Tolerant matching found 97 shared, 80 in-process-only, and 11 evaluator-only predictions.
- The evaluator initially failed because current HOMR requires GPU-awareness in `download_weights` and `ProcessingConfig`; the temporary compatibility shim adapts only the investigation subprocess.

This is not evidence for a production-default change. The focused experiments intentionally stop before dense reconstruction, CNN scoring, physical-measure construction, MMR, and numbering.

## Initial page-001 experiment

Resolve the host git metadata before entering the managed pipeline container. Do not run `git` inside the container.

```bash
ISSUE245_HOST_COMMIT="$(git rev-parse HEAD)"
ISSUE245_HOST_BRANCH="$(git branch --show-current)"

docker exec -w /workspace \
  -e PYTHONPATH=/workspace \
  -e ISSUE245_HOST_COMMIT="$ISSUE245_HOST_COMMIT" \
  -e ISSUE245_HOST_BRANCH="$ISSUE245_HOST_BRANCH" \
  pdfscore_pipeline_pytest_dev \
  /opt/venv_pipeline/bin/python \
  tools/issue245/run_page001_homr_probe.py --force
```

The wrapper resolves `page_001` from:

```text
logs/issue236_pipeline_connected_review_smoke/source_run/review/manual_correction_input.json
```

To use a different handoff or page, pass `--handoff`, `--page-id`, and `--output-root` to the wrapper.

## Retry after the legacy evaluator API failure

Current HOMR requires `download_weights(use_gpu_inference)`, but the legacy evaluator still calls `download_weights()` with no argument. Current `ProcessingConfig` also has a required `use_gpu_inference` field that the legacy evaluator detects incorrectly at class level.

Reuse the successful in-process output and rerun only the evaluator side:

```bash
docker exec -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_pytest_dev \
  /opt/venv_pipeline/bin/python \
  tools/issue245/retry_focused_evaluator.py --force
```

The retry uses `tools/issue245/run_homr_evaluator_compat.py` in a separate process. The shim adapts only the evaluator invocation and does not change the production `HybridDetector` route.

## Thin-barline isolation experiment

`HomrPredictor` adds `detect_thin_vertical_runs` candidates after core HOMR inference and tags newly inserted/replaced candidates with `system_index=-2`. The evaluator and in-process A/B differs substantially, so the next one-variable experiment disables only this augmentation in an isolated child process.

The existing production and evaluator artifacts are preserved. Run:

```bash
docker exec -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_pytest_dev \
  /opt/venv_pipeline/bin/python \
  tools/issue245/run_no_thin_variant.py --force
```

The generated report compares:

1. production in-process vs evaluator;
2. in-process with thin-barline augmentation disabled vs evaluator;
3. production in-process vs in-process with augmentation disabled.

It records prediction counts, tolerant matches, `system_index`/`staff_index` distributions, bbox size summaries, and the fraction of unmatched production candidates tagged as thin-barline additions.

## Outputs

Generated outputs remain under ignored `logs/` paths:

```text
host_run_context.json
runtime_provenance.json
focused_homr_probe_report.json
focused_homr_no_thin_report.json
in_process.log
evaluator.log
no_thin.log
in_process/<run-id>/baseline/...
evaluator/<run-id>/...
no_thin/<run-id>/baseline/...
```

## Decision gate

- If no-thin becomes close to evaluator and most production-only candidates are tagged `system_index=-2`, thin-barline augmentation is the leading baseline drift source.
- If no-thin still differs materially, separate the modular `run_homr_on_image`/heuristic path from evaluator preprocessing and filtering one condition at a time.
- Compare the surviving route against the retained historical baseline before any production behavior change.
- Do not run full-68 until focused evidence explains the first baseline HOMR divergence.
- Do not revive `production_dense_v1` or use retained historical artifacts as production inputs.
