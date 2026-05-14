# Issue 120 Stage D Producer Findings

## Purpose

This note records the #147 producer investigation after confirming that the historical Stage-D target artifact is equivalent to an Issue #36 dense probe-candidate root.

Read with:

```text
docs/refactors/issue120/ISSUE120_STAGE_D_DRIFT_RECOVERY.md
docs/refactors/issue120/ISSUE120_STAGE_D_SCHEMA_FINDINGS.md
```

## Confirmed identity

The historical root:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

and the Issue #36 candidate root:

```text
logs/issue36_prep/probe_candidates_filtered_v12
```

are byte-identical for the canonical per-page candidate files checked:

```text
left_files=68
missing=0
mismatch=0
```

This means `scoring_input_eval2_v12` can be treated as a copy or direct equivalent of `probe_candidates_filtered_v12` for Stage-D candidate-root recovery.

## Repository/local grep findings

The grep result identifies these relevant current repository references:

```text
tools/repro_accuracy/reproduce_clean_seed_v12.py
tools/issue120/run_stage_c_seed_regen_then_eval.py
tools/repro_accuracy/verify_repro_batch_final.py
tools/repro_accuracy/find_baseline_runs.py
tools/repro_accuracy/reorganize_seeds.py
tools/verification/gt_preparation/README.md
tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py
tools/verification/gt_preparation/apply_candidate_filter_from_inventory.py
tools/gt_relabel_gui/prepare_rebuild_eval2.py
```

The most directly relevant producer script is:

```text
tools/repro_accuracy/reproduce_clean_seed_v12.py
```

It regenerates:

```text
logs/repro_v12_recovery_final/probe_candidates_filtered_v12
```

using:

```text
inventory: logs/issue36_prep/20260208_bench_inventory.json
run root:  logs/hybrid_generalization/verify_fixed_v10
```

and a fixed mapping from score name to historical hybrid-generalization run IDs:

```text
Shostakovich-Festival_Overture_Va -> 20260324_121505
Shostakovich-Sym5-Va              -> 20260330_034727
Sibelius-Violin_Concerto-Viola    -> 20260330_042631
Va_Prokofiev_Symphony1            -> 20260330_044952
Va__Prokofiev_Symphony5           -> 20260330_095914
```

The #120 wrapper:

```text
tools/issue120/run_stage_c_seed_regen_then_eval.py
```

already codifies this dependency as Stage C:

```text
inventory: logs/issue36_prep/20260208_bench_inventory.json
run root:  logs/hybrid_generalization/verify_fixed_v10
output:    logs/repro_v12_recovery_final/probe_candidates_filtered_v12
```

## Issue #36 producer family

The Issue #36 / GT-preparation documentation identifies the general producer chain:

```text
generate_probe_candidates_from_inventory.py
  -> probe_candidates_from_bench_vN
apply_candidate_filter_from_inventory.py
  -> probe_candidates_filtered_vN
```

The local metadata inventory includes many historical summary and filter outputs, including:

```text
logs/issue36_prep/20260208_bench_inventory.json
logs/issue36_prep/excluded_pages_for_gt_prep.json
logs/issue36_prep/20260211_probe_generation_summary_v12.json
logs/issue36_prep/20260211_filter_apply_summary_v12.json
logs/issue36_prep/filter_suggestions_v12/**
```

This is enough to distinguish two related but different producer paths:

1. Generic Issue #36 GT-prep producer:

   ```text
   generate_probe_candidates_from_inventory.py
     -> apply_candidate_filter_from_inventory.py
     -> probe_candidates_filtered_vN
   ```

2. Historical v12 recovery producer now used by Stage C:

   ```text
   reproduce_clean_seed_v12.py
     -> hybrid_generalization/verify_fixed_v10 score-run mapping
     -> probe scan with broad recall settings
     -> filter_probe_candidates strict rules
     -> probe_candidates_filtered_v12
   ```

For Issue #120 Stage-D recovery, the second path is currently more relevant because it is already wrapped by `run_stage_c_seed_regen_then_eval.py` and targets the exact v12 candidate root.

## Current Stage-D implication

The current Stage-D upstream regeneration runner composes sparse detector-output roots from current HOMR/SR/OMR/hybrid outputs. That path is not sufficient to reproduce the historical dense candidate root.

The better Stage-D framing is:

```text
historical detector target root
  = logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
  = byte-identical to logs/issue36_prep/probe_candidates_filtered_v12

therefore Stage-D reconstruction should recover or validate the producer of:
  logs/issue36_prep/probe_candidates_filtered_v12

not only compose current sparse detector outputs into candidate filenames.
```

## Recommended next local checks

### 1. Validate Stage C producer inputs

```bash
PYTHONPATH=. python3 tools/issue120/run_stage_c_seed_regen_then_eval.py --validate-only
```

If this fails, report the missing paths from:

```text
logs/issue120_e2e_recovery/stage_c_seed_regen_eval/stage_c_input_validation.json
```

### 2. Regenerate v12 candidates and compare with historical

This can be heavier because it runs probe candidate regeneration across 68 pages:

```bash
PYTHONPATH=. python3 tools/issue120/run_stage_c_seed_regen_then_eval.py \
  --coverage-only \
  --regen-output-dir logs/issue120_e2e_recovery/stage_d_issue36_repro \
  --regenerated-candidates-dir logs/issue120_e2e_recovery/stage_d_issue36_repro/probe_candidates_filtered_v12 \
  --stage-c-eval-dir logs/issue120_e2e_recovery/stage_d_issue36_repro_eval
```

Then compare byte identity against historical:

```bash
python3 - <<'PY'
import hashlib
from pathlib import Path

left = Path('logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12')
right = Path('logs/issue120_e2e_recovery/stage_d_issue36_repro/probe_candidates_filtered_v12')
filename = 'pipeline2_no_peak_candidates.json'

left_files = sorted(left.rglob(filename))
missing = []
mismatch = []
for lf in left_files:
    rel = lf.relative_to(left)
    rf = right / rel
    if not rf.exists():
        missing.append(str(rel))
        continue
    lh = hashlib.sha256(lf.read_bytes()).hexdigest()
    rh = hashlib.sha256(rf.read_bytes()).hexdigest()
    if lh != rh:
        mismatch.append(str(rel))

print(f'left_files={len(left_files)}')
print(f'missing={len(missing)}')
print(f'mismatch={len(mismatch)}')
if missing:
    print('missing sample:', missing[:10])
if mismatch:
    print('mismatch sample:', mismatch[:10])
PY
```

### 3. If byte identity fails, compare statistics

```bash
PYTHONPATH=. python3 tools/issue120/inspect_stage_d_payload_schema.py \
  --root historical=logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12 \
  --root regenerated=logs/issue120_e2e_recovery/stage_d_issue36_repro/probe_candidates_filtered_v12 \
  --output-dir logs/issue120_e2e_recovery/stage_d_payload_schema_issue36_repro

PYTHONPATH=. python3 tools/issue120/compare_box_tree_stats.py \
  --left logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12 \
  --right logs/issue120_e2e_recovery/stage_d_issue36_repro/probe_candidates_filtered_v12 \
  --output-dir logs/issue120_e2e_recovery/stage_d_box_tree_stats_historical_vs_issue36_repro
```

## Routing decision

If `run_stage_c_seed_regen_then_eval.py --coverage-only` regenerates a byte-identical v12 root, then #147 can close with a corrected Stage-D conclusion:

```text
Stage-D dense candidate-root reconstruction path is Issue #36/#Stage-C v12 seed regeneration, not sparse current HOMR/SR/OMR composition.
```

If regeneration is close but not byte-identical, #147 should continue as a producer drift investigation.

If required `hybrid_generalization/verify_fixed_v10` inputs are missing, #147 should document that the candidate root is recoverable from local historical artifacts but not fully reproducible from repository-tracked inputs.
