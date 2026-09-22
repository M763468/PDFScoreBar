# Issue #43 probe X-domain full68 A/B

This directory contains the reproducibility harness for Issue #43.

## Purpose

The probe X-domain change is downstream of maintained HOMR/SR hybrid source
generation. A causal A/B should therefore keep that upstream fixed.

The harness:

1. generates the current production upstream once per score, unless a retained upstream manifest is supplied;
2. records one manifest that points to the five score-isolated dense inventories containing the exact image, hybrid prediction, staff-mask, and clef-mask inputs;
3. reconstructs both `full_width` and `staff_mask` probe variants score-by-score from those same inventories;
4. scores both variants with the current production CNN manifest/threshold;
5. aggregates the 68 score/page outputs and evaluates them with the canonical evaluation2 center-anchor detector evaluator;
6. records candidate-set deltas, projected-width reduction, direct probe timings,
   downstream timings, and final detector-output deltas.

Score isolation is intentional. Staff-mask lookup is page-stem based inside each
production score run, so combining all five scores into one reconstruction input
would make repeated names such as `page_001` ambiguous.

Production defaults are not changed by this experiment.

## First full68 run

From the Issue #43 worktree, if the local-only evaluation images live in the main worktree:

```bash
PDFSCORE_EVAL2_IMAGES_ROOT=/home/masaki_muramatsu/ws_PDFScoreBar/data/evaluation2/images \
  bash experiments/issue43/run_full68_x_domain_ab.sh issue43_full68_01
```

If `data/evaluation2/images` already exists inside the Issue #43 worktree, the
environment variable can be omitted.

The maintained-HOMR/SR upstream runs once per score. Both downstream variants
reuse the resulting score-isolated inventories.

Primary report:

```text
logs/issue43/full68_x_domain_ab/issue43_full68_01/
  issue43_full68_x_domain_ab_report.json
```

Retained upstream manifest:

```text
logs/issue43/full68_x_domain_ab/issue43_full68_01/
  retained_upstream_manifest.json
```

## Rerun only the downstream A/B

Use a new run tag and the retained upstream manifest:

```bash
PDFSCORE_EVAL2_IMAGES_ROOT=/home/masaki_muramatsu/ws_PDFScoreBar/data/evaluation2/images \
  bash experiments/issue43/run_full68_x_domain_ab.sh issue43_full68_recheck \
  --upstream-manifest \
  logs/issue43/full68_x_domain_ab/issue43_full68_01/retained_upstream_manifest.json
```

This skips maintained HOMR/SR upstream inference entirely and reuses the same
five retained inventories.

## Interpretation

The primary correctness comparison is relative to the same current-production
upstream, not to historical Stage-E artifacts.

Review, in order:

- detector summary: TP / FP / FN and candidate count;
- exact final detector box-set differences;
- raw / filtered / rescue candidate additions and removals;
- projected-width ratio and full-width fallback behavior;
- direct probe/reconstruction timing.

E2E wall-time noise is not a primary Issue #43 signal because probe work is a
small fraction of current production runtime.

The first one-page effective A/B on `Va_Prokofiev_Symphony1/page_001` showed:

- detector output exact: 85 vs 85, no added/removed final boxes;
- probe candidate artifacts exact: 1905 vs 1905;
- projected X width reduced to about 79.5% of full width;
- direct probe timings did not improve;
- E2E timing difference was larger than the entire probe cost and is therefore
  not attributed to this change.

The full68 retained-upstream run is intended to answer the remaining Issue #43
question: whether pages outside that smoke page actually contain removable
margin/non-staff probe candidates without detector-accuracy regression.
