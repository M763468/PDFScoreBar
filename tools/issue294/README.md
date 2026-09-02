# Issue #294 experiment helpers

These helpers are experiment-only and do not change production dispatch/configuration.

## Current interpretation

The same-original A/B compares more than runtime behavior:

- A: HOMR `864e288`, SegNet 155 FP32, Transformer 220/epoch-55 FP32.
- B: HOMR `b377620`, SegNet 308 FP16, Transformer 331 FP16.
- Observed upstream `main` on 2026-09-03: HOMR `3fe86a3`, SegNet 308 FP16, Transformer 426 FP16.

Therefore A-vs-B is a whole candidate-stack comparison, not a runtime-only causal attribution. See `model_lineage.json`.

## No-reinference GT check

After a completed same-original run, evaluate the standalone HOMR barline producer outputs against the local #255-style barline GT with:

```bash
PYTHON=/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python
$PYTHON tools/issue294/evaluate_existing_ab_gt_host.py \
  --run-tag issue294_same_original_smoke_02
```

The default GT root is `data/training/annotations`. The helper reuses the accepted #255 barline evaluation implementation (`IoU=0.5`, original-page `orig_bbox`) and performs no HOMR inference. Its result is a producer-level detector metric, not the final Stage-E CNN metric.

Do not promote B to the representative 012-014 or full68 gates solely from wall-time improvement. Review standalone GT metrics, raw geometry, MusicXML/topology drift, fixed-support hybrid replay, and the maintained-model lineage first.
