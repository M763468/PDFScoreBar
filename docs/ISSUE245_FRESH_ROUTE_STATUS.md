# Issue #245 fresh-route status

## Status

The fresh upstream detector contract is not restored yet.

A valid fresh run must use current HOMR/SR/OMR hybrid outputs as the authoritative
source for both probe generation and CNN band geometry. It must not set:

```text
detection.precomputed_probe_candidates_root
detection.cnn_bands_from
```

The difference between the historical checkpoint route and this fresh contract is
documented in [`ISSUE245_REPRODUCIBILITY_ROOT_CAUSE.md`](ISSUE245_REPRODUCIBILITY_ROOT_CAUSE.md).

## Current decisions

- Historical reproduction is not the primary goal. Focused probes ruled out SR
  scale, evaluator revision, and retained SR working-image pixels as sufficient
  explanations for the fresh residuals.
- The accepted Issue #120 Stage E metric is a checkpoint/precomputed candidate
  result. Its inventory records reference retained `hybrid_predictions`; it does
  not prove that a newly supplied PDF regenerates equivalent HOMR/SR/OMR output.
- The Issue #245 fresh runner now rejects precomputed probe candidates and CNN
  band overrides before creating its output directory.
- The OMR-DLN measure model has been restored from the official distribution and
  can be selected through `OMR_DLN_MODEL_PATH`.
- The aligned-expansion rescue remains implemented for explicit experiments but
  is disabled in canonical dense and Issue #120 Stage E configs.
- Generic paper-overlap or CNN threshold changes have not been made.

## Focused aligned-expansion result

The experimental aligned-expansion rescue restored the focused Shostakovich and
Sibelius targets:

```text
Shostakovich page_013:
  bbox=[1679,1145,1683,1296]
  IoU=0.6369
  CNN=0.9998832

Sibelius page_004 x~1516:
  bbox=[1514,4067,1518,4202]
  IoU=0.6943
  CNN=0.9999934

Sibelius page_004 x~1926:
  bbox=[1923,4067,1927,4200]
  IoU=0.6377
  CNN=0.9999875
```

This establishes a mechanism on those pages only. It is not a production safety
result.

## Fresh Prokofiev safety failure

The official OMR-DLN model was restored and loaded successfully as an OMR
`detect` model. A fresh x2 SR/HOMR/OMR/hybrid run for
`Va_Prokofiev_Symphony1` completed without historical detector or candidate
artifacts.

For `page_004`:

- `[847,2490,854,2591]` was present and CNN accepted;
- `[847,2675,854,2776]` was absent from the fresh candidate set;
- the fresh producer had no clef-mask file, so the remaining miss was not caused
  by the same-file staff/clef-mask rejection;
- aligned expansion selected 131 candidates for 155 existing boxes;
- all 131 were added after trimming;
- 110 rescue candidates passed CNN;
- two focused false positives were introduced;
- the missing target was still not generated.

This violates the rescue safety contract. Enabling the rescue in canonical
configs before a fresh full-68 gate was an invalid promotion and has been
reverted.

## External model contract

The required OMR-DLN model is the measure-detection `YOLOv8m_Measures.pt` from
[dmgonzalez8/OMR](https://github.com/dmgonzalez8/OMR). It is an externally
distributed model, not a project training output.

Current verified model:

```text
path=/home/masaki_muramatsu/ws_PDFScoreBar/external/omr_dln/models/public_models/YOLOv8m_Measures.pt
size=52,308,289 bytes
sha256=00d0bd8b399ae872f029eb38ed3985fcef33ca81cae414992b5cdb9062e91212
task=detect
```

The normal repository-relative path remains compatible. A shared read-only path
can be selected with `OMR_DLN_MODEL_PATH` so worktrees do not duplicate the
weight.

## Fresh reproduction command

The score-isolated fresh runner prevents repeated page stems across scores from
colliding and rejects checkpoint candidate-source overrides:

```bash
docker run --rm --gpus all \
  -v "$WT:/workspace" \
  -v "$MAIN/data:/workspace/data:ro" \
  -v "$MAIN_MODEL:/models/YOLOv8m_Measures.pt:ro" \
  -v "$MAIN_SR_MODEL:/workspace/external/realesrgan/weights/RealESRGAN_x2plus.pth:ro" \
  -v "$MAIN_CNN:/workspace/logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth:ro" \
  -e OMR_DLN_MODEL_PATH=/models/YOLOv8m_Measures.pt \
  -e PYTHONPATH=/workspace -w /workspace pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python tools/issue245/run_fresh_stage_e_full68.py \
  --output-root logs/issue245_fresh_stage_e_full68/run_1
```

Each run must use a new output root. The provenance report records
`detector_input_contract.mode=fresh_upstream` only when current hybrid outputs
remain authoritative.

## Next investigation boundary

Do not tune the broad aligned-expansion selector next.

Trace the remaining Prokofiev reference `[847,2675,854,2776]` through:

```text
baseline HOMR
SR-side HOMR
OMR-DLN
hybrid consensus
row-band construction
existing suppression
raw probe generation
heuristic filtering
trim
CNN
```

The next repair must target the first layer where the reference or its containing
row disappears. It must remain default OFF until fresh full-68 detector,
physical-measure, MMR, guard-case, and corrected-final gates pass.
