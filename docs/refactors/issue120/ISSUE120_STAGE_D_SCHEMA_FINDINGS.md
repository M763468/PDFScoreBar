# Issue 120 Stage D Payload Schema Findings

## Purpose

This note records the first payload-schema inspection for #147.

It should be read with:

```text
docs/refactors/issue120/ISSUE120_STAGE_D_DRIFT_RECOVERY.md
```

## Input roots inspected

```text
historical = logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
baseline   = logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_baseline
hybrid     = logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate
omr_sr     = logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_omr_sr
sr         = logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_sr
first_available = logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_first_available
```

All roots resolved the canonical 68-page manifest:

```text
resolved=68
missing=0
```

## Summary

```text
label            median item count   median width   median height   score keys
historical       315.0               4.0            107.0           0
baseline         123.0               1.0             97.75          0
hybrid            54.0               7.0            105.5           0
omr_sr            88.0               2.0            105.0           0
sr                63.0               7.0            105.0           0
first_available   54.0               7.0            105.5           0
```

Schema observations:

- historical payloads are list payloads with list boxes;
- baseline/hybrid/omr_sr/first_available also resolve as list-box payloads;
- sr resolves as list payloads with `orig_bbox`, `pred_bbox`, `staff_index`, and `system_index` item keys;
- none of the inspected roots have `score` keys in the sampled candidate files;
- therefore the primary difference is not scored-vs-unscored schema;
- the primary observed difference is candidate density and, secondarily, box width/source-family differences.

## Interpretation

The initial file-family mismatch hypothesis should be narrowed:

```text
Not supported:
  historical is scored dict payloads while regenerated roots are raw box lists.

Supported:
  historical is a much denser unscored candidate/box root than any current regenerated Stage D source.
```

The most likely Stage D gap is now:

```text
historical dense candidate-generation path
  !=
current Stage D sparse upstream-detector composition path
```

The current regenerated roots are structurally valid and schema-compatible enough to be consumed, but they do not reproduce the dense candidate volume of `scoring_input_eval2_v12`.

## Historical-code clue

PR #57 / Issue #53 used:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

as `bands_from` for probe-rescue candidate generation.

Issue #44 docs identify an older candidate source family:

```text
logs/issue36_prep/probe_candidates_filtered_v12
```

The Issue #44 workflow says the CNN training candidate JSONs were from this older candidate family, while later scoring/evaluation configs were fixed to use `scoring_input_eval2_v12` as the scored/evaluated root.

This suggests the next Stage D reconstruction search should prioritize the Issue #36/#44 candidate-generation path, not only the current HOMR/SR/OMR detector outputs.

## Next diagnostic questions

1. Does local `logs/issue36_prep/probe_candidates_filtered_v12` still exist?
2. If yes, how do its 68-page item counts and schemas compare with `scoring_input_eval2_v12`?
3. Can `probe_candidates_filtered_v12` or its producer regenerate a dense candidate root close to `scoring_input_eval2_v12`?
4. Did `scoring_input_eval2_v12` originate by copying/renaming/filtering `probe_candidates_filtered_v12`, or by running a later probe-generation variant?
5. Does the historical dense root depend on probe generation settings that are not represented in current Stage D HOMR/SR/OMR composition?

## Recommended local command

If the old Issue #36 candidate root exists locally, run:

```bash
PYTHONPATH=. python3 tools/issue120/inspect_stage_d_payload_schema.py \
  --root historical=logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12 \
  --root issue36_probe=logs/issue36_prep/probe_candidates_filtered_v12 \
  --root baseline=logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_baseline \
  --output-dir logs/issue120_e2e_recovery/stage_d_payload_schema_issue36
```

Then compare geometry:

```bash
PYTHONPATH=. python3 tools/issue120/compare_box_tree_stats.py \
  --left logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12 \
  --right logs/issue36_prep/probe_candidates_filtered_v12 \
  --output-dir logs/issue120_e2e_recovery/stage_d_box_tree_stats_historical_vs_issue36_probe
```

If this old root is close to historical, #147 should shift from upstream-detector composition to recovering the Issue #36 probe candidate producer.
