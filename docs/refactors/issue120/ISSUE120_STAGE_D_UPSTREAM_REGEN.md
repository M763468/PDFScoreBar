# Issue 120 Stage D Upstream Regeneration

## Purpose

Stage D verifies whether the slow upstream artifacts used by the Issue #120 detector reconstruction can be regenerated from the current repository and local `evaluation2` inputs.

Current detector-level target:

```text
#57 / Issue53 probe rescue candidate generation
  -> current pipeline CNN scoring
  -> cnn_apply_nms=false
  -> #134 canonical full-68 evaluator
  -> TP=3580 FP=0 FN=1
```

Unresolved upstream artifact:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

Detector metrics and downstream measure-count metrics must remain separate.

## Scope boundary

This is an audit/regeneration issue. It must not silently change detector/scoring behavior.

This PR provides reproducible Stage-D commands, provenance, diagnostics, and failure-boundary documentation. It does not claim Stage D passes.

## Current upstream path

```text
HybridDetector
  -> baseline HOMR output
  -> SR image generation
  -> SR-side HOMR output
  -> OMR-DLN on SR images
  -> hybrid consensus
  -> probe scan using composed bands_from
  -> CNN scoring
```

Relevant files:

```text
src/pipeline/detection/hybrid.py
src/pipeline/detection/orchestrator.py
src/pipeline/steps/probe_scan.py
src/pipeline/steps/cnn_scoring.py
tools/issue120/run_stage_d_upstream_regen.py
tools/issue120/run_issue53_probe_rescue_then_eval.py
tools/issue120/summarize_stage_d_drift.py
tools/issue120/compare_box_tree_stats.py
```

The canonical Issue #120 68-page set reuses page stems such as `page_001` across scores. Stage D therefore runs upstream generation score-by-score to avoid output collisions, then composes a score-aware `bands_from` tree.

This score-by-score model reload is intentional for this audit PR. It trades runtime efficiency for unambiguous artifacts. A production-quality persistent-model implementation belongs in a later upstream repair PR after the artifact boundary is understood.

## Generated outputs

Default root:

```text
logs/issue120_e2e_recovery/stage_d_upstream_regen
```

Default composed bands tree:

```text
logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate
```

Source-specific composed trees:

```text
logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_baseline
logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_sr
logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_omr_sr
```

Do not commit generated outputs.

## Make targets

The Stage-D Make targets redirect verbose output into `artifacts/` logs.

```bash
make regen-issue120-stage-d-upstream ISSUE120_CLEAN_OUTPUT=1
make verify-issue120-stage-d
make summarize-issue120-stage-d
make compare-issue120-stage-d-boxes
```

Useful variables:

```text
ISSUE120_IMAGE_ROOT
ISSUE120_GT_ROOT
ISSUE120_MODEL_PATH
ISSUE120_STAGE_D_OUTPUT_ROOT
ISSUE120_STAGE_D_BANDS_FROM
ISSUE120_STAGE_D_CANDIDATES_DIR
ISSUE120_STAGE_D_SCORING_DIR
ISSUE120_STAGE_D_EVAL_DIR
ISSUE120_STAGE_D_COMPOSE_SOURCE
```

## Direct Docker commands

Run upstream regeneration:

```bash
docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python tools/issue120/run_stage_d_upstream_regen.py \
    --clean-output
```

Run Stage C verifier against regenerated upstream bands:

```bash
docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python tools/issue120/run_issue53_probe_rescue_then_eval.py \
    --bands-from logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate \
    --output-root logs/issue120_e2e_recovery/stage_d_from_current_upstream_candidates \
    --scoring-output-dir logs/issue120_e2e_recovery/stage_d_from_current_upstream_scoring \
    --eval-output-dir logs/issue120_e2e_recovery/stage_d_from_current_upstream_eval
```

## Compose-source diagnostics

Recompose existing upstream outputs without rerunning HOMR/SR/OMR:

```bash
docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python tools/issue120/run_stage_d_upstream_regen.py \
    --compose-only \
    --compose-source baseline
```

Repeat with `--compose-source sr` and `--compose-source omr_sr` as needed.

Important guardrail:

```text
--compose-only must not be combined with --clean-output
```

`--compose-only` rebuilds `bands_from_candidate_*` from existing `hybrid_runs`; cleaning the output root would delete those inputs.

## Current local Stage-D results

Default hybrid-source composition:

```text
GT=3581 Pred=3769 TP=3527 FP=183 FN=54 FN_det=37 FN_cnn=17 Precision=0.950674 Recall=0.984920
```

Baseline-source composition after schema normalization:

```text
Candidate coverage:
Pages=68
Baseline candidates=29443
Compared candidates=21415
Ratio=0.7273375675033115
Empty compared pages=0

Detector:
GT=3581 Pred=3907 TP=3543 FP=288 FN=38 FN_det=19 FN_cnn=19 Precision=0.924824 Recall=0.989388
```

Interpretation:

- Baseline source is the best current source-specific composition tested.
- It improves recall and reduces detector-side misses relative to hybrid composition.
- It substantially increases false positives.
- It still does not reproduce the target `TP=3580 FP=0 FN=1`.

## Reporting checklist

Record:

```text
Stage D upstream command
Stage D provenance path
Composed pages / missing pages
Stage C verifier command
Candidate coverage summary
Detector: GT / Pred / TP / FP / FN / FN_det / FN_cnn
cnn_apply_nms setting
Worst pages by FN_det / FP / candidate coverage
Any missing upstream component or failed page
```

## Current conclusion

Current upstream components can regenerate structurally complete 68-page artifacts, but none of the tested compositions reproduce the historical detector target.

```text
Target: TP=3580 FP=0 FN=1
Best current Stage D composition tested: baseline source
Observed: TP=3543 FP=288 FN=38
```

The historical `scoring_input_eval2_v12` artifact remains non-reproduced. Further progress should be split into historical source recovery or upstream/geometry repair after this diagnostic foundation is merged.
