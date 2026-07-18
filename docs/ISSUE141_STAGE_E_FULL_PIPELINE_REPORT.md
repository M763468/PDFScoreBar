# Issue 141: Stage E Full Pipeline Validation Report

## 2026-07-19 provenance correction

The detector metrics in this report remain valid for the accepted Issue #120
**checkpoint reconstruction route**. They must not be cited as evidence that a
newly supplied PDF can regenerate equivalent detector inputs from current
HOMR/SR/OMR.

The Stage E runner executes the HOMR/SR/OMR-inclusive pipeline, but its accepted
candidate geometry is supplied through a reconstructed inventory route:

```text
logs/issue36_prep/20260208_bench_inventory.json
  -> record["hybrid_predictions"]
  -> dense probe reconstruction
  -> clef/staff-aware filtering
  -> probe-rescue reconstruction
  -> detection.precomputed_probe_candidates_root
  -> detection.cnn_bands_from
```

Consequently, the current hybrid output is not authoritative for the accepted
probe candidates or CNN band geometry. The correct detector input classification
for this result is:

```text
precomputed_candidate_route
fresh_upstream_authoritative=false
```

The unresolved clean-PDF/fresh-upstream boundary is owned by Issue #245 and is
documented in
[`ISSUE245_REPRODUCIBILITY_ROOT_CAUSE.md`](ISSUE245_REPRODUCIBILITY_ROOT_CAUSE.md).

## Purpose

This document records the 68-page Issue #120 checkpoint regression and its
runtime surface. It verifies that the retained inventory contract, candidate
reconstruction, CNN scoring, and downstream pipeline wiring remain reproducible.
It does not verify arbitrary fresh upstream regeneration.

## Execution configuration

- **Run ID**: `stage_e_full_pipeline`
- **Output location**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/`
- **Components executed**: inventory-based dense candidate reconstruction,
  probe-rescue reconstruction, HOMR/SR/OMR-inclusive pipeline execution, CNN
  scoring, and downstream measure numbering
- **Authoritative probe input**: reconstructed `precomputed_probe_candidates_root`
- **Authoritative CNN bands**: reconstructed `cnn_bands_from`
- **NMS policy**: `cnn_apply_nms: false`

The Stage E implementation writes new candidate files inside the current run, but
the authoritative existing boxes originate from inventory-referenced retained
`hybrid_predictions`. A newly written artifact is not necessarily a fresh-source
artifact.

## Runtime, resource, and log surface

Issue #159 added metric-neutral observability:

- `dense_route_execution_summary.json` records dense-route phase durations,
  command logs, and generated roots.
- `stage_e_runtime_summary.json` records dense reconstruction, image-copy, and
  pipeline durations.
- `stage_e_resource_samples.jsonl` and its summary record best-effort CPU, RSS,
  and GPU observations.
- `pipeline_stdout_stderr.log` and its summary capture external runtime output.
- Dense reconstruction logs are compact by default; verbose logs are opt-in.

Generated summaries remain under ignored `logs/` paths.

## One-command checkpoint evaluation

After the Stage E checkpoint run completes, first run the small artifact-discovery
smoke check:

```bash
make eval-issue120-stage-e-smoke
```

Then evaluate the complete checkpoint contract:

```bash
make eval-issue120-stage-e-full
```

Expected outputs:

```text
logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector/evaluation_contract.json
logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector/detector_metrics.json
logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector/detector_page_metrics.csv
logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector/manifest.json
```

These commands evaluate the checkpoint route. They do not change its detector
input classification to `fresh_upstream`.

## Detector metrics

Checkpoint target:

```text
Pages=68/68
GT=3581
Pred=3600
TP=3580
FP=0
FN=1
FN_det=0
FN_cnn=1
Precision=1.000000
Recall=0.999721
cnn_apply_nms=false
```

Observed checkpoint result:

```text
TP=3580
FP=0
FN=1
```

The checkpoint target was met.

## Initial real-upstream failure

Before inventory-based candidate injection, the real HOMR/SR/OMR-inclusive route
produced:

```text
TP=3359
FP=145
FN=222
FN_det=222
FN_cnn=0
```

This was the relevant fresh-upstream failure boundary at the time. The subsequent
repair did not make the current upstream artifacts equivalent; it replaced their
authority at the candidate stages with the recovered inventory route.

## Repair mechanics

The accepted repair performs these operations:

1. Load image, staff-mask, and retained `hybrid_predictions` paths from the Issue
   #36 benchmark inventory.
2. Regenerate dense probe candidates around the inventory hybrid boxes.
3. Apply clef/staff-aware filtering.
4. Regenerate probe-rescue candidates from the filtered root.
5. Assign the reconstructed roots to
   `precomputed_probe_candidates_root` and `cnn_bands_from`.
6. Execute the remaining pipeline and evaluate the resulting checkpoint artifacts.

This is a useful, reproducible historical regression route. It is not a clean
fresh-input production route.

## Downstream measure-count metrics

Detector metrics and downstream measure-count metrics remain separate. The
pipeline writes numbering output under:

```text
logs/issue120_e2e_recovery/stage_e_full_pipeline/outputs/numbering_final.json
```

A canonical downstream measure-count comparator was not attached to this audit;
the evaluation contract records `measure_count_summary.status=not_provided`.

## Correct interpretation

- The Issue #120 checkpoint candidate route is reproducible.
- Its detector metric is `TP=3580 / FP=0 / FN=1` with NMS disabled.
- The run executes full pipeline components, but current HOMR/SR/OMR output is not
  authoritative for probe or CNN band geometry.
- The report must not be used to claim that arbitrary fresh PDFs reproduce the
  same upstream detector contract.
- Fresh upstream accuracy requires a separate contract where both candidate-source
  override keys are absent and the current hybrid output is authoritative.
