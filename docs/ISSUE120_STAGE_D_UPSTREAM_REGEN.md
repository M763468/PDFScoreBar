# Issue 120 Stage D Upstream Regeneration

## Purpose

Stage D verifies whether the slow upstream artifacts used by the Issue #120 detector reconstruction can be regenerated from the current repository and local evaluation2 inputs.

The Stage C detector-level target is already known:

```text
#57 / Issue53 probe rescue candidate generation
  -> current pipeline CNN scoring
  -> cnn_apply_nms=false
  -> #134 canonical full-68 evaluator
  -> TP=3580 FP=0 FN=1
```

The unresolved Stage D question is whether this historical `bands_from` input can be regenerated or replaced by an equivalent current upstream artifact:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

## Scope boundary

Stage D is an audit/regeneration issue. It should not change detector or scoring logic unless a small change is needed to expose reproducible commands or provenance.

Detector metrics and downstream measure-count metrics must remain separate.

## Current upstream path in the current pipeline

The current full detection stack is:

```text
HybridDetector
  -> baseline HOMR output
  -> SR image generation
  -> SR-side HOMR output
  -> OMR-DLN on SR images
  -> hybrid consensus
  -> probe scan using hybrid output as bands_from
  -> CNN scoring
```

Relevant source files:

```text
src/pipeline/detection/hybrid.py
src/pipeline/detection/orchestrator.py
src/pipeline/steps/probe_scan.py
src/pipeline/steps/cnn_scoring.py
```

Important implementation detail:

- Hybrid outputs are mostly keyed by page stem such as `page_001`.
- The canonical Issue #120 68-page set contains repeated page stems across different scores.
- Therefore Stage D regeneration should run score-by-score and then compose a score-aware `bands_from` directory.

## Added helpers

Stage D adds:

```text
tools/issue120/run_stage_d_upstream_regen.py
tools/issue120/summarize_stage_d_drift.py
```

`run_stage_d_upstream_regen.py`:

1. runs the current `HybridDetector` score-by-score;
2. writes generated upstream artifacts under ignored `logs/` paths;
3. composes a score-aware `bands_from` candidate directory;
4. writes a provenance file describing the regenerated upstream artifact.

`summarize_stage_d_drift.py` reads generated local logs after a Stage D run and prints a page-level drift summary. It does not rerun HOMR/SR/OMR, probe scan, CNN scoring, or evaluation.

Default output root:

```text
logs/issue120_e2e_recovery/stage_d_upstream_regen
```

Composed `bands_from` directory:

```text
logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate
```

Provenance file:

```text
logs/issue120_e2e_recovery/stage_d_upstream_regen/stage_d_upstream_regen_provenance.json
```

## Local run commands

Run a dry-run first:

```bash
PYTHONPATH=. python3 tools/issue120/run_stage_d_upstream_regen.py --dry-run
```

Run the full Stage D upstream regeneration in Docker/GPU:

```bash
docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python tools/issue120/run_stage_d_upstream_regen.py \
    --clean-output
```

Equivalent Make target:

```bash
make regen-issue120-stage-d-upstream ISSUE120_CLEAN_OUTPUT=1
```

If the full run is too expensive, run one score first:

```bash
docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python tools/issue120/run_stage_d_upstream_regen.py \
    --clean-output \
    --scores Shostakovich-Festival_Overture_Va
```

Equivalent Make target:

```bash
make regen-issue120-stage-d-upstream \
  ISSUE120_CLEAN_OUTPUT=1 \
  ISSUE120_STAGE_D_SCORES=Shostakovich-Festival_Overture_Va
```

## Stage C verifier against regenerated upstream artifacts

After Stage D upstream regeneration completes, run Stage C using the regenerated `bands_from` directory:

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

Equivalent Make target:

```bash
make verify-issue120-stage-d
```

Expected detector target if Stage D passes:

```text
TP=3580 FP=0 FN=1
```

## Current local result

A local Stage D run using regenerated current upstream artifacts did **not** preserve the detector target:

```text
Pages: 68/68
Detector: GT=3581 Pred=3769 TP=3527 FP=183 FN=54 FN_det=37 FN_cnn=17 Precision=0.950674 Recall=0.984920
```

Interpretation:

- Stage D currently fails against the selected detector target.
- `FN_det=37` indicates candidate-generation or upstream-band coverage loss before CNN scoring.
- `FN_cnn=17` indicates additional scoring/filtering loss after candidate generation.
- `FP=183` indicates candidate geometry/coverage drift or over-generation, not only missing detections.

This confirms that the current regenerated upstream path is not equivalent to the historical `bands_from` artifact.

## Drift summary command

After a failed Stage D run, summarize page-level drift with:

```bash
make summarize-issue120-stage-d
```

Direct command:

```bash
PYTHONPATH=. python3 tools/issue120/summarize_stage_d_drift.py \
  --eval-dir logs/issue120_e2e_recovery/stage_d_from_current_upstream_eval \
  --upstream-dir logs/issue120_e2e_recovery/stage_d_upstream_regen
```

The summary is written under ignored logs by default:

```text
logs/issue120_e2e_recovery/stage_d_from_current_upstream_eval/stage_d_drift_summary.md
```

Use this output to identify whether the largest deltas cluster in upstream composition, candidate coverage, detector-side misses, CNN-side misses, or false positives.

## Reporting checklist

Record the following in the PR or issue comment:

```text
Stage D upstream regeneration command
Stage D provenance path
Composed pages / missing pages
Stage C verifier command
Candidate coverage summary
Detector: GT / Pred / TP / FP / FN / FN_det / FN_cnn
cnn_apply_nms setting
Worst pages by FN_det / FP / candidate coverage
Any missing upstream component or failed page
```

If the detector target is not preserved, Stage D can still close as an audit if it documents the failure boundary and opens follow-up issues.

## Outputs and Git policy

Do not commit generated outputs from Stage D.

Keep generated artifacts under ignored `logs/` paths, especially:

```text
logs/issue120_e2e_recovery/stage_d_upstream_regen/
logs/issue120_e2e_recovery/stage_d_from_current_upstream_candidates/
logs/issue120_e2e_recovery/stage_d_from_current_upstream_scoring/
logs/issue120_e2e_recovery/stage_d_from_current_upstream_eval/
```
