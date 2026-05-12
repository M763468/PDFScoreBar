# Issue 120 Artifact Retention Policy

## Purpose

This document is the #135 retention policy for Issue #120 restart work. It separates source files from generated run artifacts and records the temporary exception for the canonical detector-intermediate fixture used by the #134/#143 evaluation path.

## Current decision

`data/evaluation2/golden_baseline_eval2_bc23deb/` is not treated as a normal generated run output during #135. It is a retained detector-intermediate fixture until Stage D/E prove a regenerated upstream path or an external artifact handoff replaces it.

The retained fixture is still not full-pipeline evidence. It supports only these audited detector-level layers:

```text
Stage A: saved scored intermediates -> #134 evaluator
Stage B: saved candidates -> current CNN scoring -> #134 evaluator
Stage C: Issue53 probe rescue candidates -> current CNN scoring -> #134 evaluator
```

The current detector-level target remains:

```text
TP=3580 / FP=0 / FN=1
```

This is separate from downstream measure-count metrics.

## Artifact classes

### Source

Keep in Git.

Examples:

- `src/**`
- `tools/**`
- `tests/**`
- `docs/**`
- stable config templates under `configs/**`
- canonical evaluation code such as `tools/issue120/eval_full68_from_intermediates.py`

### Source evaluation input

Keep in Git while the repository depends on local evaluation2 inputs.

Examples:

- `data/evaluation2/images/**/page_*.png`
- `data/evaluation2/annotations/**/boxes_sorted.json`

These are input data, not generated outputs from an Issue #120 run.

### Retained Issue #120 intermediate fixture

Keep temporarily, with explicit rationale.

Current retained path:

```text
data/evaluation2/golden_baseline_eval2_bc23deb/
```

Retained per-page files:

```text
pipeline2_no_peak_candidates.json
pipeline2_no_peak_filtered_cnn.json
pipeline2_no_peak_scored.json
```

Retained metadata:

```text
eval_config.yaml
```

Rationale:

- `pipeline2_no_peak_scored.json` is the Stage A saved-scored fixture used by `make eval-issue120-full`.
- `pipeline2_no_peak_candidates.json` is the Stage B saved-candidates fixture used to isolate current CNN scoring behavior.
- `pipeline2_no_peak_filtered_cnn.json` is retained as historical scorer output evidence while #140/#141 are still open.
- `eval_config.yaml` is a small historical provenance snapshot tying the fixture to `logs/issue53_full_eval_rescue_v1` and the canonical matching thresholds.

Removal condition:

- Do not remove this fixture until Stage D/E either regenerate equivalent upstream artifacts or define another durable artifact handoff.
- Once that happens, remove the fixture from Git and require local/external artifact provisioning instead.

### Generated artifact

Do not keep in Git.

Examples:

- `logs/**`
- `artifacts/**`
- `output/**`
- `debug_outputs/**`
- `temp/**`
- `configs/tmp_*.yaml`
- `configs/tmp_issue120_*.yaml`
- generated evaluation summaries such as:
  - `global_summary.csv`
  - `detector_metrics.json`
  - `detector_page_metrics.csv`
  - `evaluation_contract.json`
  - `intermediate_provenance.json`
  - `manifest.json`
  - `missing_pages.json`
- crops, overlays, contact sheets, and manual visual-review PNGs outside canonical input data

Generated artifacts should be regenerated under ignored `logs/` paths.

### Historical external/local artifact

Do not commit. Document paths and provenance.

Known Issue #120 examples:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth
logs/issue53_full_eval_rescue_v1
logs/repro_v12_recovery_final
logs/hybrid_generalization/verify_fixed_v10
logs/issue36_prep/20260208_bench_inventory.json
```

These paths may be required for Stage C/D investigations, but they remain local or external artifacts.

## Current #135 cleanup action

Remove generated summaries from the retained fixture tree when they are not required inputs to canonical evaluation.

Removed by #135:

```text
data/evaluation2/golden_baseline_eval2_bc23deb/global_summary.csv
```

Use the #134 evaluator to regenerate normalized summaries under ignored output paths:

```bash
make eval-issue120-full
```

Default output:

```text
logs/issue120_e2e_recovery/latest_full_report/
```

## Inventory command

Run this before and after cleanup changes:

```bash
PYTHONPATH=. python3 tools/issue120/inventory_tracked_artifacts.py --format markdown
```

For machine-readable output:

```bash
PYTHONPATH=. python3 tools/issue120/inventory_tracked_artifacts.py --format json
```

For a future CI-style guard:

```bash
PYTHONPATH=. python3 tools/issue120/inventory_tracked_artifacts.py --fail-on-generated
```

Do not enable the guard globally until the retained Issue #120 fixture exception has been resolved or encoded in CI policy.

## PR review checklist

A PR touching Issue #120 artifacts should state:

- whether each changed path is source, source evaluation input, retained fixture, generated artifact, or external/local artifact;
- whether detector metrics or downstream measure-count metrics are affected;
- whether any generated files were committed;
- where local outputs are written under ignored `logs/` paths;
- whether `cnn_apply_nms` is explicitly recorded when reporting Issue #120 detector reconstruction metrics.
