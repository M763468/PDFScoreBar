# Issue #245 focused upstream detector investigation

This directory contains temporary investigation tooling for Issue #245.

## Current boundary

Static history inspection established the following:

- The accepted fresh Stage E run in PR #181 completed all 68 pages with the detector target.
- The tracked baseline HOMR generation code has not changed between the PR #181 merge checkpoint and the current `develop` branch.
- Current `HybridDetector` may select either the in-process HOMR path or the evaluator fallback path depending on whether all imports guarded by `_HOMR_AVAILABLE` succeed.
- Therefore the first focused experiment records runtime/import provenance and compares both baseline HOMR paths on an identical image.

This is not evidence for a production-default change. It intentionally does not run dense reconstruction, CNN scoring, physical-measure construction, MMR, or numbering.

## Initial page-001 experiment

Run inside the managed pipeline Python environment from the repository root:

```bash
PYTHONPATH=. /opt/venv_pipeline/bin/python \
  tools/issue245/run_page001_homr_probe.py --force
```

The wrapper resolves `page_001` from:

```text
logs/issue236_pipeline_connected_review_smoke/source_run/review/manual_correction_input.json
```

To use a different handoff or page:

```bash
PYTHONPATH=. /opt/venv_pipeline/bin/python \
  tools/issue245/run_page001_homr_probe.py \
  --handoff logs/<run>/review/manual_correction_input.json \
  --page-id page_001 \
  --output-root logs/issue245_focused_homr_probe/<run-name>
```

## Outputs

Generated outputs remain under ignored `logs/` paths:

```text
runtime_provenance.json
focused_homr_probe_report.json
in_process.log
evaluator.log
in_process/<run-id>/baseline/...
evaluator/<run-id>/...
```

The report records:

- exact git branch and commit;
- Python, platform, package, import-file, and module-hash provenance;
- ONNX Runtime providers and CUDA visibility;
- `_HOMR_AVAILABLE` and the baseline route selected by `HybridDetector`;
- input image path, hash, dimensions, dtype, and channels;
- baseline prediction counts and tolerant matching between the two routes;
- staff-mask hashes, dimensions, and nonzero-pixel counts.

## Decision gate

- If `HybridDetector` selects `evaluator_fallback`, first identify the failed import and do not tune detector thresholds.
- If it selects `in_process` but differs materially from the evaluator, compare the route matching the retained historical artifact before changing production behavior.
- If both current routes agree but differ from historical baseline HOMR, investigate package/model/provider/preprocessing provenance next.
- Do not run full-68 until focused evidence explains the first baseline HOMR divergence.
- Do not revive `production_dense_v1` or use retained historical artifacts as production inputs.
