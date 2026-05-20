# Issue 158: Dense Route Naming Boundary

## Purpose

Issue #158 separates production detector-route names from historical checkpoint names without changing detector behavior, thresholds, CNN scoring, or NMS policy.

The canonical Stage E full-pipeline checkpoint remains the acceptance gate for this refactor:

```text
expected_pages=68
evaluated_pages=68
TP=3580
FP=0
FN=1
FN_det=0
FN_cNN=1
cnn_apply_nms=false
target_met.detector=true
```

## Production names

New production-oriented detector-route code should use these names:

- Module: `src.pipeline.detector_routes.dense_full_pipeline`
- Route builder: `reconstruct_dense_full_pipeline_route`
- Artifact type: `DenseRouteArtifacts`
- Artifact field for route-supplied probe candidates: `probe_rescue_root`
- Image inventory loader: `load_route_image_paths`
- Probe rescue regeneration: `regenerate_probe_rescue_candidates`
- Detector config keys:
  - `detection.precomputed_probe_candidates_root`
  - `detection.cnn_bands_from`
  - `detection.probe_use_original_images`

These names describe runtime semantics rather than the Stage E checkpoint or the Issue53 provenance.

## Historical names retained only for compatibility or provenance

The following names remain intentionally:

- `tools/issue120/run_stage_e_full_pipeline.py`
- `tools/issue120/eval_stage_e_from_manifest.py`
- `tools/issue120/attach_stage_e_eval_contract.py`
- `configs/issue120_stage_e_full_pipeline.yaml`
- `logs/issue120_e2e_recovery/stage_e_full_pipeline/`
- evaluation contract schema `issue141.stage_e_full_pipeline.v1`
- report `docs/ISSUE141_STAGE_E_FULL_PIPELINE_REPORT.md`

These identify the checkpoint and reproduce the exact #141/#156 Stage E validation contract. They are not the public detector-route API.

The old module `src.pipeline.detector_routes.stage_e_dense_full_pipeline` remains as a compatibility shim for existing references. New code should import from `src.pipeline.detector_routes.dense_full_pipeline`.

## Config migration notes

Use these production keys in new configs:

| Legacy key | Production key |
| --- | --- |
| `detection.stage_e_issue53_candidates_root` | `detection.precomputed_probe_candidates_root` |
| `detection.stage_e_dense_reconstruction_root` | `detection.cnn_bands_from` |

The legacy keys remain supported in `DetectorOrchestrator` as read-only fallback keys for historical Stage E configs. They should not be used in new route configs.

## What should not be renamed in this issue

Do not rename checkpoint commands, log directories, or evaluation contract schema names unless a new migration layer is added. Those names are part of the reproducibility surface for the canonical Stage E contract, while the production detector-route API has moved to semantic dense-route names.

Do not use historical dense candidate logs as runtime input. Dense candidates, filtered candidates, and probe-rescue candidates must continue to be reconstructed inside the current run.
