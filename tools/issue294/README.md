# Issue #294 experiment helpers

These helpers are experiment-only and do not change production dispatch/configuration.

## Current interpretation

The same-original A/B compares more than runtime behavior:

- A: HOMR `864e288`, SegNet 155 FP32, Transformer 220/epoch-55 FP32.
- B: HOMR `b377620`, SegNet 308 FP16, Transformer 331 FP16.
- Observed upstream `main` on 2026-09-03: HOMR `3fe86a3`, SegNet 308 FP16, Transformer 426 FP16.

Therefore A-vs-B is a whole candidate-stack comparison, not a runtime-only causal attribution. See `model_lineage.json`.

The Stage-E baseline is operationally consumed as detector material. Barline/staff/clef material is created before Transformer parsing/MusicXML generation, while connector semantics remain owned by the current-x4 support producer. MusicXML differences are therefore not a primary replacement gate when the PDFScoreBar downstream barline/count/topology/numbering result is preserved.

## Primary downstream candidate matrix

Run the current control, the maintained-family candidate, and the latest upstream detector-material candidate together:

```bash
PYTHON=/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python
$PYTHON tools/issue294/run_downstream_candidate_matrix_host.py \
  --run-tag issue294_downstream_matrix_01 \
  --page 013
```

The host wrapper:

1. reruns the historical A and maintained-family B on the same original page;
2. resolves upstream `liebharc/homr` `main` to an immutable commit and checks out that exact commit under the ignored Issue #294 log cache;
3. runs C from that exact source commit as a detector-material-only candidate (Transformer/MusicXML are deliberately not executed);
4. generates one current-x4 HOMR + OMR-DLN support bundle and freezes it for all variants;
5. freezes A's historical staff/clef geometry for this causal gate;
6. replays A/B/C through production hybrid consensus, dense candidate reconstruction, CNN scoring, and `MeasureNumberingPipeline`;
7. reports final CNN barline count, measure count, system/staff/measure topology, numbering, and exact final-box equality.

The primary pass criterion is `count_topology_numbering_pass`. Exact final box identity is recorded but is not required if the operational count/topology/numbering result is unchanged.

This first matrix intentionally freezes historical staff/clef geometry so it answers whether changing baseline barline material degrades the final operational result. A candidate-native staff/clef mask gate is still required before production promotion.

## Upstream update policy

Production must never depend on floating `main`. The intended maintenance flow is:

1. discover the current upstream `main`;
2. resolve it to an immutable commit;
3. record source/model/runtime provenance and hashes;
4. run the downstream matrix on representative/focused pages;
5. run the mandatory risk pages (`013/045/066/067`) and then full68 when the focused gate passes;
6. only then manually promote the pinned production commit/model/runtime.

This lets upstream development continue without silently changing production behavior.

## Optional GT diagnostic

The no-reinference GT helper remains available when the local GT tree is present:

```bash
PYTHON=/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python
$PYTHON tools/issue294/evaluate_existing_ab_gt_host.py \
  --run-tag issue294_same_original_smoke_02
```

Missing GT is not a blocker for the downstream matrix. The GT helper is diagnostic only; it is no longer the primary gate.
