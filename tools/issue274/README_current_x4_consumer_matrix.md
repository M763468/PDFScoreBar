# Issue #274 current-x4 consumer matrix — v1 forensic record

`run_current_x4_consumer_matrix.py` was intended as a focused consumer-policy gate
before attempting to remove pinned x4 HOMR (C).  The completed run is **invalid as
a production A/B replay** and must not be used to select a support/suppression
policy.

The experiment code and output are intentionally retained because the failed sanity
gate exposed an important Stage-E contract boundary.

## Result

The report decision was:

```text
invalid_matrix_replay_does_not_reproduce_retained_ab
```

The control and B replay cells both failed to reproduce the retained Stage-E page
metrics.  Candidate counts collapsed from hundreds per page to roughly the hybrid
seed count.

The immediate trace is:

- `detect_probe_scan` still generated hundreds of raw candidates;
- the v1 harness then passed them through the current one-pass
  `src.pipeline.steps.candidate_filters.filter_probe_candidates` path;
- essentially all generated candidates were dropped;
- the final set therefore mostly consisted of the hybrid seeds.

This is a harness-contract mismatch, not evidence that the dense candidates or the
support/suppression hypotheses are intrinsically wrong.

## Why v1 did not reproduce Stage-E

The accepted Stage-E route is not a one-pass
`run_probe_scan_batch -> current candidate_filters -> CNN` pipeline.

`src.pipeline.detector_routes.dense_full_pipeline` has two PDFScoreBar-owned dense
passes:

1. first-pass dense generation from inventory;
2. first-pass filtering through
   `tools/verification/gt_preparation/apply_candidate_filter_from_inventory.py` /
   `suggest_candidate_drops.py`;
3. second probe-rescue generation seeded by the first-pass filtered root;
4. CNN scoring of that second-pass candidate set.

The v1 matrix short-circuited that route.  It also used a different filter
implementation and did not supply the actual Stage-E inventory staff-mask contract.
Consequently the mandatory replay check correctly rejected the matrix.

## Clef-axis correction

The `retained_c` cells in v1 all resolved `clef_path: null`, so the clef/no-clef
axis was not exercised at all.

More importantly, the real Stage-E first-pass filter resolves its clef mask from
the **inventory record / staff-mask tree**.  Therefore a clef artifact must not be
called "C-derived" merely because a nearby C detection JSON exists.  Its concrete
producer must be established from the retained inventory/filter summary.

Ownership remains:

- clef/staff mask pixel generation: upstream HOMR;
- selecting/persisting/handing those masks to Stage-E: PDFScoreBar orchestration;
- candidate filtering itself: PDFScoreBar extension.

`analyze_stage_e_multiplicity_and_mask_provenance.py` is the retained-only follow-up
that records the actual mask paths and classifies the producer tree.

## Revised interpretation of the five B-route residuals

The retained Stage-E boundary traces show that the critical targets generally do
**not** disappear completely from the final candidate set.  Instead, several
control pages contain two distinct nearby candidate boxes where the B replay
contains one candidate that can match more than one GT identity.  The resulting
one-to-one evaluation loss is therefore a barline **multiplicity / identity
capacity** problem rather than simply a missing-candidate problem.

Examples already visible in retained residuals include:

- `Sym5/page_013`: control has two target-compatible dense candidates; B replay has
  one current-x4-supported box;
- `Sibelius/page_004`: the same pattern occurs for both structural residuals;
- `Sym5/page_015`: the final candidate exists with a high CNN score, so the route
  must be analysed as an identity/competition problem in addition to the earlier
  x4 IoU/thin geometry observation.

This means an experiment that modifies only the second-pass
`has_existing_for_suppression` closure is too narrow.

## Current design guardrails

The next architecture/design work follows these rules:

1. expensive HOMR evidence production is separate from PDFScoreBar barline identity;
2. x4 HOMR is evidence, not the owner of final per-staff/per-system topology;
3. same x-position alone does not identify one physical barline entity;
4. candidate admissibility, evidence support, and identity/multiplicity are separate
   contracts;
5. any identity/suppression policy must be coherent across **both** Stage-E dense
   passes;
6. globally disabling suppression is only a causal upper bound, not a production
   design;
7. staff/clef inventory dependencies must be assigned to the selected canonical
   producer bundle before C can be removed;
8. no additional HOMR inference is needed for the current retained-artifact
   investigation.

See `HOMR_FEATURE_OWNERSHIP.md` for the upstream/PDFScoreBar ownership map.
