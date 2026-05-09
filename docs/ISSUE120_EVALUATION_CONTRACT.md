# Issue 120 Evaluation Contract

## Purpose

This document defines the canonical Issue #120 evaluation entrypoint introduced for #134.

The entrypoint intentionally evaluates saved intermediate outputs. It does not run the full pipeline. This prevents long, noisy full-pipeline runs from being confused with lightweight evaluation and makes it explicit when a result is based on a previously generated intermediate tree.

## Canonical command

```bash
make eval-issue120-full
```

Default inputs:

```text
ISSUE120_RESULTS_DIR=data/evaluation2/golden_baseline_eval2_bc23deb
ISSUE120_GT_ROOT=data/evaluation2/annotations
ISSUE120_OUTPUT_DIR=logs/issue120_e2e_recovery/latest_full_report
ISSUE120_SCORE_THRESHOLD=0.1
ISSUE120_XDIST_THRESHOLD=12.0
ISSUE120_MEASURE_SUMMARY=
ISSUE120_PROVENANCE_JSON=
```

Equivalent direct command:

```bash
PYTHONPATH=. python3 tools/issue120/eval_full68_from_intermediates.py \
  --results-dir data/evaluation2/golden_baseline_eval2_bc23deb \
  --gt-root data/evaluation2/annotations \
  --output-dir logs/issue120_e2e_recovery/latest_full_report \
  --score-threshold 0.1 \
  --xdist-threshold 12.0

PYTHONPATH=. python3 tools/issue120/attach_eval_provenance.py \
  --output-dir logs/issue120_e2e_recovery/latest_full_report \
  --results-dir data/evaluation2/golden_baseline_eval2_bc23deb
```

## Evaluated page set

The command validates the canonical 68-page `evaluation2` subset used by Issue #120. Partial inputs fail by default.

Use `--allow-partial` only for debugging. Partial results are not canonical.

## Input contract

The evaluator consumes existing detector intermediate files.

Required per page:

```text
pipeline2_no_peak_scored.json
```

Optional per page:

```text
pipeline2_no_peak_candidates.json
```

These files correspond to a detector-stage boundary after candidate generation and CNN scoring. They are not raw OMR, HOMR, OMR-DLN, SR, or hybrid-consensus outputs.

When candidates are available, the evaluator also reports approximate `FN_det` / `FN_cnn` split:

- `FN_det`: no matching candidate exists for the missed GT.
- `FN_cnn`: a matching candidate exists, but the scored prediction did not pass the score threshold.

Accepted result layouts:

```text
<results-dir>/eval2_<score>_<page>/pipeline2_no_peak_scored.json
<results-dir>/<score>/<page>/pipeline2_no_peak_scored.json
<results-dir>/<score>/eval2_<score>_<page>/pipeline2_no_peak_scored.json
```

The same layouts are used for `pipeline2_no_peak_candidates.json`.

## Output contract

The command writes outputs under `ISSUE120_OUTPUT_DIR`, which must remain ignored by Git.

Generated files:

```text
manifest.json
missing_pages.json             # only when required inputs are missing
detector_metrics.json
detector_page_metrics.csv
evaluation_contract.json
intermediate_provenance.json
```

`evaluation_contract.json` is the canonical machine-readable summary for this entrypoint.

## Detector metrics

The evaluator reports:

- `TP`
- `FP`
- `FN`
- `FN_det`
- `FN_cnn`
- `GT`
- predicted boxes after threshold
- candidate count, if candidates are present
- precision
- recall

Matching rule defaults:

```text
rule_name=center_anchor
vov_threshold=0.5
xdist_threshold=12.0
score_threshold=0.1
```

These defaults intentionally match the previous `verify_golden_baseline.py` contract rather than later ad-hoc restore scripts.

## Provenance contract

The default provenance block records that this is a post-CNN-scoring detector-intermediate evaluation.

Expected upstream stages before this intermediate include:

1. initial OMR/HOMR pass;
2. optional SR image generation;
3. OMR/HOMR pass on the SR image;
4. optional OMR-DLN or other detector outputs used by the run;
5. hybrid consensus / seed preparation;
6. probe scan candidate generation;
7. CNN scoring of candidates.

The evaluator does not prove that those upstream stages were regenerated from the current code. It proves only that the saved post-CNN-scoring intermediates evaluate to the reported detector metrics under the canonical 68-page manifest and matching rule.

To attach a verified local provenance record:

```bash
make eval-issue120-full \
  ISSUE120_RESULTS_DIR=logs/path/to/intermediates \
  ISSUE120_PROVENANCE_JSON=logs/path/to/provenance.json
```

Recommended provenance JSON fields:

```json
{
  "schema_version": "issue120.intermediate_provenance.v1",
  "status": "verified_local_run",
  "results_dir": "logs/path/to/intermediates",
  "evaluated_stage": "post_cnn_scoring_detector_intermediate",
  "generation_commit": "<commit sha>",
  "generation_command": "<command or script used to create intermediates>",
  "source_artifact": "<artifact path or external reference>",
  "notes": []
}
```

## Measure-count metrics

This PR does not implement full downstream numbering evaluation. If a downstream measure-count run has already produced a summary JSON, attach it with:

```bash
make eval-issue120-full ISSUE120_MEASURE_SUMMARY=path/to/measure_summary.json
```

The measure summary is copied into `evaluation_contract.json` under `measure_count_summary`.

Until a canonical measure-count evaluator exists, detector metrics and measure-count metrics must be treated separately.

## Long-running pipeline runs

Full pipeline execution for 68 pages may take tens of minutes or hours and can produce large logs. It is intentionally not part of `make eval-issue120-full`.

The slow stages are expected to be the initial OMR/HOMR processing, SR processing, and the second OMR/HOMR pass over SR output. Hybrid consensus, probe scan, and CNN scoring are comparatively cheaper and can be rerun more often once the slow upstream outputs are available.

Recommended local workflow:

1. Run or recover the slow upstream OMR/SR/HOMR outputs locally.
2. Generate or recover the post-CNN-scoring intermediate tree.
3. Point `ISSUE120_RESULTS_DIR` at that tree.
4. Run `make eval-issue120-full ISSUE120_RESULTS_DIR=<path>`.
5. Commit only source/tool/doc changes, not the generated output tree.

## Historical-best verification

The local run below reproduces the detector-intermediate historical target from saved intermediates:

```text
Pages: 68/68
Detector: GT=3581 Pred=3597 TP=3580 FP=0 FN=1 FN_det=0 FN_cnn=1 Precision=1.000000 Recall=0.999721
```

This should be described precisely as:

> The saved post-CNN-scoring detector intermediates under `data/evaluation2/golden_baseline_eval2_bc23deb` reproduce `TP=3580 / FP=0 / FN=1` under the canonical 68-page evaluator.

It should not be described as full pipeline reproduction unless the upstream OMR/SR/HOMR/hybrid/probe/CNN generation path is also regenerated or otherwise proven.
