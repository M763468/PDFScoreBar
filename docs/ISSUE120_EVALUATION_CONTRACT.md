# Issue 120 Evaluation Contract

> [!IMPORTANT]
> This contract is canonical for evaluating saved post-CNN detector
> intermediates on the historical 68-page Issue #120 set. It is not a production
> runtime profile and must not be used to choose PDF raster settings or a
> candidate-generation route.
>
> Issue #244 tested a proposed fresh current-run dense route and the full-68
> regression failed. The current status and required approval gates are recorded
> in [`docs/dev/DETECTOR_BASELINE_MATRIX.md`](dev/DETECTOR_BASELINE_MATRIX.md).

## Purpose

This document defines the canonical Issue #120 evaluation entrypoint introduced
for #134.

The entrypoint intentionally evaluates saved intermediate outputs. It does not
run the full pipeline. This prevents long full-pipeline runs from being confused
with lightweight evaluation and makes it explicit when a result is based on a
previously generated intermediate tree.

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
```

The historical result must be interpreted with the GT revision used for the
specific evaluation. After PR #203 corrected the page_060 GT, the retained
artifact is expected to expose one FP that is tracked separately by Issue #202.
