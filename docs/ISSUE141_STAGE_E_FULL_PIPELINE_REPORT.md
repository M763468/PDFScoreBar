# Issue 141: Stage E Full Pipeline Validation Report

> [!WARNING]
> This is a historical validation report, not a production runtime
> specification. The Stage E result depends on dense candidates regenerated from
> an inventory that already records upstream hybrid predictions and staff/clef
> masks. It therefore does **not** prove that fresh current-run HOMR/OMR/SR and
> hybrid artifacts reproduce the same detector route.
>
> Issue #244 attempted that fresh current-run reconstruction. Its one-page replay
> passed, but the full-68 detector and MMR regression failed. See
> [`docs/dev/DETECTOR_BASELINE_MATRIX.md`](dev/DETECTOR_BASELINE_MATRIX.md) for
> the current status.

## Historical purpose

Issue #141 validated that the retained/reconstructed Stage E route could be
connected through the full pipeline and evaluated on the canonical 68-page set.
It is retained for audit, provenance, and comparison.

## Historical execution configuration

- Run ID: `stage_e_full_pipeline`
- Output: `logs/issue120_e2e_recovery/stage_e_full_pipeline/`
- Components: dense candidate reconstruction, probe-rescue reconstruction,
  pipeline detector/CNN scoring, and downstream numbering
- NMS policy: `cnn_apply_nms: false`

The runner first calls `reconstruct_dense_full_pipeline_route()` with the
canonical inventory. That inventory supplies image paths plus upstream hybrid
predictions and staff/clef masks. The regenerated probe-rescue candidates are
then injected into the pipeline as precomputed detector inputs.

This distinction matters: the candidates are regenerated, but their upstream
bands/masks are not independently regenerated from a fresh arbitrary production
PDF run.

## Historical detector result

The original Stage E evaluation reported:

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
```

After PR #203 corrected the page_060 GT, re-evaluating the same retained artifact
against current GT produces:

```text
GT=3580
Pred=3600
TP=3579
FP=1
FN=1
```

The one FP is the known page_060 residual tracked by Issue #202. It is not an
Issue #244 regression.

## Historical repair summary

The initial Stage E route did not reproduce the detector target:

```text
TP=3359 FP=145 FN=222
```

The historical repair:

1. regenerated dense candidates from the canonical inventory;
2. applied staff/clef-aware filtering using inventory-recorded masks;
3. regenerated probe-rescue candidates;
4. injected those candidates into the pipeline;
5. disabled CNN NMS;
6. evaluated the resulting detector intermediates.

This proved the retained inventory-based route. It did not prove fresh upstream
artifact regeneration.

## Evaluation commands

Smoke evaluation:

```bash
make eval-issue120-stage-e-smoke
```

Full evaluation:

```bash
make eval-issue120-stage-e-full
```

For current-GT diagnostic evaluation where the historical fixed target is
expected to differ:

```bash
make eval-issue120-stage-e-full \
  ISSUE120_STAGE_E_EVAL_EXTRA_ARGS=--allow-target-mismatch
```

## Retention and use

Keep the Stage E runner, config, and retained artifact because they provide:

- detector provenance;
- a current-GT historical comparison baseline;
- a source for layer-by-layer artifact comparison;
- evidence that dense candidate/CNN stages can reach the historical target when
  supplied with the recorded upstream artifacts.

Do not copy the Stage E config into user-facing or corrected-rerun execution.
Production approval requires a fresh-run full-68 regression, including detector,
physical measure-count, MMR, and guard-case checks.
