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

The full68 retained-upstream run completed on 2026-09-22 and answered the
remaining Issue #43 question. The results and candidate audit are summarized
below.


## Audit candidate deltas after full68

After a completed full68 run, audit whether removed/added rescue candidates are
low-scoring, edge-biased, outside the local staff-mask-supported X span, or
GT-matchable without rerunning HOMR/SR or detector reconstruction:

```bash
RUN_TAG=$(cat logs/issue43/latest_full68_run_tag.txt)
REPORT="logs/issue43/full68_x_domain_ab/$RUN_TAG/issue43_full68_x_domain_ab_report.json"

python experiments/issue43/audit_full68_candidate_changes.py \
  --report "$REPORT"
```

The audit writes `candidate_delta_audit.json` beside the main full68 report.

## Completed full68 result

Run `issue43_full68_20260922T121216Z` completed with exit code 0. Both variants
used the same retained upstream inventories and the canonical evaluation2
center-anchor detector evaluator (`GT=3567`). Final detector output was exact:

| Result | `full_width` | `staff_mask`, pad 1.0 staff unit |
| --- | ---: | ---: |
| Predicted boxes | 3643 | 3643 |
| TP / hard FP / FN | 3532 / 11 / 35 | 3532 / 11 / 35 |
| Final boxes added / removed | 0 / 0 | 0 / 0 |
| Raw probe candidates | 27868 | 27715 |
| Rescue candidates | 29612 | 29510 |

The staff-mask mode bounded all 703 bands with no full-width fallback and
reduced projected X columns by 14.93%. Candidate-delta audit found all 157
removed rescue candidates and all 55 added candidates below the production CNN
threshold and unmatched to canonical GT. Of the removed candidates, 153/157
were in the outer 12% page margins. Probe-local timings improved, but downstream
total time did not; no end-to-end speedup is claimed.

The saved current-production output in this run scored `3535 / 11 / 32`; the
full-width reconstruction differed on three CNN rescoring results on one page.
The broader absolute detector-metric difference from the earlier D27 result was
investigated separately in #372. #372 closed after an equivalent full68
physical-measure-count audit (`3287` vs `3287`), with the stroke-level D27
comparison still recorded as a failure. #372 did not merge a production change,
so it does not change this same-upstream #43 A/B result. This PR keeps
`full_width` as the production default; it does not claim to restore D27
stroke-level TP/FP/FN.
