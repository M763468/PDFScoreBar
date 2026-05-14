# Issue 120 Restart Plan

## Purpose

Issue #120 is being handled as an audit-first recovery effort. The goal is to keep the repository operable while rebuilding the evidence chain for the historical detector result.

The restart work separates:

- branch and document governance;
- canonical detector evaluation;
- historical-best audit;
- generated-artifact cleanup;
- slow upstream regeneration;
- downstream/full-pipeline validation;
- targeted accuracy repair.

## Current branch model

### Active audit/integration target

```text
rebuild/issue120
```

Use this branch as the base for Issue #120 restart, audit, cleanup, and repair work. Do not merge it to `main` until the restart issues are complete.

### Frozen experimental branch

```text
fix/probe_seeds
```

Treat this branch as evidence. Do not merge it wholesale. Port only narrow changes after they pass the canonical full-68 gates.

### Default branch

```text
main
```

Do not use `main` as the immediate base for restart work. Any eventual merge to `main` must happen only after `rebuild/issue120` is audited, cleaned, and validated.

## Current completed foundation

### #133 / PR #138: restart plan

Status: completed.

Result:

- `rebuild/issue120` is the audit/integration target.
- `fix/probe_seeds` is frozen as an evidence branch.
- Issue #120 remains the parent Epic.
- Restart work is split into staged issues.

### #134 / PR #139: canonical full-68 detector-intermediate evaluator

Status: completed.

Canonical command:

```bash
make eval-issue120-full
```

Scope:

- evaluates saved detector intermediates;
- validates the canonical 68-page manifest;
- emits normalized detector metrics under ignored `logs/` output paths;
- does not run the full pipeline.

Verified saved-intermediate detector result:

```text
TP=3580 / FP=0 / FN=1
```

### #136 / PR #143: historical best audit and clean detector target

Status: completed.

PR:

```text
#143 docs/tools: audit Issue 120 historical best and reconstruction path
merge commit: 0c0eaafcb9dda3c3d48be2db6cea41c603187f0a
```

Current clean detector-level reconstruction target:

```text
#57 / Issue53 probe rescue candidate generation
  -> current pipeline CNN scoring
  -> cnn_apply_nms=false
  -> #134 canonical full-68 evaluator
  -> TP=3580 FP=0 FN=1
```

Boundary:

- This is detector-level reconstruction.
- It is not full slow-upstream pipeline reproduction.
- Downstream measure-count metrics remain separate.
- Stage D still needs to verify the historical upstream `bands_from` dependency.

### #135 / PR #144: generated artifact cleanup and retention policy

Status: completed.

PR:

```text
#144 chore/docs: define Issue 120 artifact retention policy
merge commit: f18dc801345e56a6ac90c95228b9448f2a34a440
```

Policy document:

```text
docs/ISSUE120_ARTIFACT_RETENTION.md
```

Current decision:

- source/docs/tools/config templates stay in Git;
- source evaluation inputs stay in Git while the repository depends on them;
- `data/evaluation2/golden_baseline_eval2_bc23deb/` is retained temporarily as detector-intermediate evidence;
- generated summaries and local run outputs belong under ignored paths such as `logs/`.

### #140 / PR #145: Stage D upstream regeneration diagnostic foundation

Status: open issue; diagnostic foundation merged.

PR:

```text
#145 tools/docs: add Issue 120 Stage D upstream regeneration runner
merge commit: a685bef1bda26e66937bd276df560ce655f67f5f
```

Stage D document:

```text
docs/refactors/issue120/ISSUE120_STAGE_D_UPSTREAM_REGEN.md
```

Current Stage D conclusion:

```text
Target: TP=3580 FP=0 FN=1
Best current Stage D composition tested: baseline source
Observed: TP=3543 FP=288 FN=38
```

Boundary:

- Current upstream components can regenerate structurally complete 68-page artifacts.
- Tested current compositions do not reproduce the historical detector target.
- The historical `logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12` artifact remains non-reproduced.
- #140 should be closed only after the issue thread records this boundary and any follow-up issue is opened or explicitly deferred.

## Open issue plan

### #140: Stage D closeout

Base: `rebuild/issue120`  
Branch: `audit/issue120-stage-d-upstream-regen` or a doc-only successor branch  
PR base: `rebuild/issue120`

Purpose:

Close out the Stage D audit by recording the current-upstream failure boundary in the issue thread.

Primary unresolved dependency:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

The issue can close as a documented audit if it clearly states that current upstream regeneration is structurally complete but does not preserve the selected detector target.

### #142: CNN scoring NMS repair/tuning

Base: `rebuild/issue120`  
Branch: `fix/issue120-cnn-nms-policy`  
PR base: `rebuild/issue120`

Purpose:

Decide whether the current NMS should be kept, tuned, made conditional, or disabled only for explicit Issue #120 reconstruction modes.

Current policy:

```text
general pipeline default: cnn_apply_nms=true
Issue120 reconstruction: cnn_apply_nms=false, explicitly recorded
```

### #141: Stage E full 68-page pipeline validation

Base: `rebuild/issue120`  
Branch: `audit/issue120-stage-e-full-pipeline`  
PR base: `rebuild/issue120`

Purpose:

Run or document full 68-page pipeline validation after Stage D clarifies upstream artifact regeneration.

Current dependency:

- Stage D has a current-upstream failure boundary.
- Stage E must not claim full detector-target reproduction from current upstream artifacts unless new evidence changes that boundary.

### #137: Targeted accuracy repair

Base: `rebuild/issue120`  
Branch: `fix/issue120-accuracy-after-audit`  
PR base: `rebuild/issue120`

Purpose:

Resume targeted accuracy work only after the canonical detector target, artifact policy, Stage D boundary, and NMS policy are clear.

## Artifact retention policy

The detailed #135 policy is maintained in:

```text
docs/ISSUE120_ARTIFACT_RETENTION.md
```

Use these classes.

### Source

Keep in Git.

Examples:

- `src/**`
- `tools/**`
- `tests/**`
- `docs/**`
- stable config templates under `configs/**`

### Source evaluation input

Keep in Git while the repository depends on local evaluation2 inputs.

Examples:

- `data/evaluation2/images/**/page_*.png`
- `data/evaluation2/annotations/**/boxes_sorted.json`

### Retained Issue #120 detector-intermediate fixture

Temporarily keep in Git until Stage D/E provide a regenerated or external artifact replacement:

```text
data/evaluation2/golden_baseline_eval2_bc23deb/
```

Retained per-page evidence:

```text
pipeline2_no_peak_candidates.json
pipeline2_no_peak_filtered_cnn.json
pipeline2_no_peak_scored.json
```

Retained metadata:

```text
eval_config.yaml
```

This fixture is not full-pipeline evidence. It supports the Stage A/B detector-level audit only.

### Generated artifact

Do not keep in Git.

Examples:

- `logs/**`
- `artifacts/**`
- `output/**`
- `debug_outputs/**`
- temporary generated configs;
- generated evaluation summaries such as `global_summary.csv`, `detector_metrics.json`, `detector_page_metrics.csv`, `evaluation_contract.json`, `intermediate_provenance.json`, `manifest.json`, and `missing_pages.json`;
- crops, overlays, contact sheets, and manual visual-review PNGs outside canonical input data.

Generated outputs should be written under ignored `logs/` paths.

### Historical external/local artifact

Do not commit. Record provenance and local paths.

Known examples:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth
logs/issue53_full_eval_rescue_v1
logs/repro_v12_recovery_final
logs/hybrid_generalization/verify_fixed_v10
logs/issue36_prep/20260208_bench_inventory.json
```

## Artifact inventory command

Run:

```bash
PYTHONPATH=. python3 tools/issue120/inventory_tracked_artifacts.py --format markdown
```

Machine-readable output:

```bash
PYTHONPATH=. python3 tools/issue120/inventory_tracked_artifacts.py --format json
```

## Evaluation policy

A result is canonical only if all of the following are recorded:

- branch and commit SHA;
- command;
- config path and config hash or content snapshot;
- manifest path and page count;
- input image root;
- GT root;
- output path;
- detector metrics;
- downstream measure-count metrics, when available;
- whether the run was full 68 pages or partial;
- `cnn_apply_nms` when CNN scoring is involved.

Detector metrics and measure-count metrics must be reported separately.

Required detector metrics:

- `TP`
- `FP`
- `FN`
- `FN_cnn`
- `FN_det`
- `GT`
- precision
- recall

Required downstream measure-count metrics:

- predicted measure count
- GT measure count
- net delta
- absolute delta sum
- pages with delta
- measure precision
- measure recall

## Accuracy work guardrails

Do not resume broad accuracy changes until Stage D closeout and NMS policy are clear.

When accuracy work resumes:

- change one mechanism per PR;
- run canonical full-68 evaluation before and after;
- avoid broad low-score rescue without full evidence;
- avoid broad X-alignment rescue without full evidence;
- avoid fixed-pixel thresholds; prefer unit-scaled rules;
- do not accept a change that improves a local page subset but worsens the chosen canonical gate;
- explicitly separate detector-level improvement from measure-count improvement.

## Recommended order from here

```text
1. Close out #140 by recording the Stage D boundary in the issue thread.
2. Open or defer a follow-up for historical `scoring_input_eval2_v12` provenance recovery / upstream geometry repair.
3. Work #142 to decide NMS behavior before broad accuracy repair.
4. Work #141 as full 68-page validation, explicitly separating detector metrics from downstream measure-count metrics.
5. Work #137 targeted accuracy repair using canonical gates.
```

## Current decision

Until changed by a later audited issue:

```text
detector target: TP=3580 / FP=0 / FN=1
Issue120 reconstruction CNN setting: cnn_apply_nms=false
general pipeline CNN setting: cnn_apply_nms=true
```

This detector target is not a downstream measure-count target and is not yet full-pipeline reproduction.
