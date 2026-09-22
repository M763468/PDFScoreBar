# Issue #43 probe X-domain full68 A/B

This directory contains the reproducibility harness for Issue #43.

## Purpose

The probe X-domain change is downstream of maintained HOMR/SR hybrid source
generation. A causal A/B should therefore keep that upstream fixed.

The harness:

1. generates the current production upstream once, unless a retained inventory is supplied;
2. records one 68-page dense inventory containing the exact image, hybrid prediction,
   staff-mask, and clef-mask inputs;
3. reconstructs both `full_width` and `staff_mask` probe variants from that same inventory;
4. scores both variants with the current production CNN manifest/threshold;
5. evaluates both with the canonical evaluation2 center-anchor detector evaluator;
6. records candidate-set deltas, projected-width reduction, direct probe timings,
   downstream timings, and final detector-output deltas.

Production defaults are not changed by this experiment.

## First full68 run

From the Issue #43 worktree:

```bash
bash experiments/issue43/run_full68_x_domain_ab.sh issue43_full68_01
```

The maintained-HOMR/SR upstream runs once. Both downstream variants reuse the
resulting inventory.

Primary report:

```text
logs/issue43/full68_x_domain_ab/issue43_full68_01/
  issue43_full68_x_domain_ab_report.json
```

Retained upstream inventory:

```text
logs/issue43/full68_x_domain_ab/issue43_full68_01/
  retained_upstream_inventory.json
```

## Rerun only the downstream A/B

Use a new run tag and the retained inventory:

```bash
experiments/issue43/run_full68_x_domain_ab.sh issue43_full68_recheck \
  --inventory \
  logs/issue43/full68_x_domain_ab/issue43_full68_01/retained_upstream_inventory.json
```

This skips HOMR/SR upstream inference entirely.

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
