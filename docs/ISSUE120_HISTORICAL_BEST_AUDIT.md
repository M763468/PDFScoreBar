# Issue 120 Historical Best Accuracy Audit

## Purpose

This document is the working audit for #136. Its goal is to separate three different claims that were previously mixed together:

1. saved intermediate evaluation reproduces `TP=3580 / FP=0 / FN=1`;
2. the current downstream detector stages can regenerate those intermediates;
3. the current full pipeline can regenerate the same detector result end-to-end.

Only item 1 is currently verified by the canonical #134 evaluator. Items 2 and 3 remain open.

## Current verified fact

After #134, the following command evaluates saved post-CNN-scoring detector intermediates:

```bash
make eval-issue120-full
```

Local result reported for `data/evaluation2/golden_baseline_eval2_bc23deb`:

```text
Pages: 68/68
Detector: GT=3581 Pred=3597 TP=3580 FP=0 FN=1 FN_det=0 FN_cnn=1 Precision=1.000000 Recall=0.999721
```

Precise interpretation:

> The saved post-CNN-scoring detector intermediates under `data/evaluation2/golden_baseline_eval2_bc23deb` reproduce `TP=3580 / FP=0 / FN=1` under the canonical 68-page evaluator.

This is not full-pipeline reproduction.

## Branch and PR evidence inventory

### Clean starting point

- Commit: `90a278c668e148a68d5a8c3c19c067bb5ff29649`
- Role: original clean rebuild base for Issue #120.
- Meaning: useful as a historical source branch base, but not itself the current verified best.

### PR #127: Golden Baseline introduction

- PR: #127 `test: Phase 1.1 - 前提バグ修正とGolden Baseline検証の追加 (Epic #120)`
- Base: `rebuild/issue120` at `90a278c668e148a68d5a8c3c19c067bb5ff29649`
- Merge commit: `7d3fbf89dcd52b22b3919d36a30b2d46959fdd84`
- Claimed result: `TP=3580, FP=0, FN=1` over 68 pages.
- Added artifact tree: `data/evaluation2/golden_baseline_eval2_bc23deb/`.
- Added verifier: `tools/repro_accuracy/verify_golden_baseline.py`.
- Important limitation: this PR introduced saved scored/candidate outputs as a Golden Baseline. It does not by itself prove that the current full pipeline can regenerate those outputs.

### PR #128: in-process / batch infrastructure

- PR: #128 `feat: Phase 1.2 - In-process実行化とBatch Orchestrator等の基盤統合 (Epic #120)`
- Merge commit: `b89ad515d065fc98f21c674092bb02a784277292`
- Claimed result: `tools/repro_accuracy/verify_golden_baseline.py` still reports `TP=3580, FP=0, FN=1`.
- Interpretation: preservation of the saved Golden Baseline evaluator, not necessarily full regeneration.

### PR #129: native filtering and box tightening

- PR: #129 `feat: Phase 3 - ネイティブフィルタリングとBox Tightening (Epic #120)`
- Merge commit: `db422aed34ae846d6aa288a89ad78e7075b1aaad`
- Claimed result: `tools/repro_accuracy/verify_golden_baseline.py` still reports `TP=3580, FP=0, FN=1`.
- Interpretation: likely still verifier-based unless separate run artifacts are found.

### PR #130 / #131: tall band / rounding fix

- PR #130 was later superseded by #131.
- PR #131 merge commit: `25548b29bb5d706b7c0bcb9f4d5881e892cc1a9b`.
- Claimed result: `evaluate_full_rescue_v1.py` with native inference and cache disabled maintained `TP=3580, FP=0, FN=1`.
- Current finding: `evaluate_full_rescue_v1.py` is not present at `rebuild/issue120` under `tools/repro_accuracy/`. This claim needs source recovery from past commit/log/artifact before it can be treated as reproducible.

### PR #132: refactor step

- PR: #132 `Refactor: Step 5 (Phase 2) - Pipeline and Utility Refactoring`
- Merge commit: `fa0bb34c2d103f796228039740ae0412df47298b`
- Claimed result: `evaluate_full_rescue_v1.py` with native inference maintained `TP=3580, FP=0, FN=1`.
- Current finding: same as #131. The script and exact generated output tree must be recovered or reconstructed.

### PR #139: canonical intermediate evaluator

- PR: #139 `tools: add Issue 120 canonical full68 intermediate evaluator`
- Merge commit: `0febdf8da383c26367b20d75ca98f4554190f2c9`
- Verified result: saved post-CNN-scoring intermediates reproduce `TP=3580, FP=0, FN=1`.
- Scope: evaluation only; no proof of upstream regeneration.

## Artifact and script evidence

### `data/evaluation2/golden_baseline_eval2_bc23deb/`

This directory contains saved detector intermediates, including per-page:

```text
pipeline2_no_peak_candidates.json
pipeline2_no_peak_filtered_cnn.json
pipeline2_no_peak_scored.json
```

It also contains:

```text
eval_config.yaml
global_summary.csv
```

`eval_config.yaml` records:

```text
eval_rule: center_anchor
gt_root: data/evaluation2/annotations
output_csv: logs/issue53_full_eval_rescue_v1/global_summary.csv
scored_glob: '*_scored.json'
scored_root: logs/issue53_full_eval_rescue_v1
threshold: 0.1
vov_threshold: 0.5
xdist_threshold: 12.0
```

Interpretation:

- The checked-in Golden Baseline tree appears to have been extracted from `logs/issue53_full_eval_rescue_v1`.
- The matching thresholds match #134's canonical detector evaluator.
- The original source log tree `logs/issue53_full_eval_rescue_v1` is not assumed to be available from a fresh checkout.

### `tools/repro_accuracy/verify_golden_baseline.py`

Role:

- Evaluates saved scored JSON files from `data/evaluation2/golden_baseline_eval2_bc23deb`.
- Uses `score >= 0.1`, `center_anchor`, `vov_threshold=0.5`, `xdist_threshold=12.0`.
- Expects `TP=3580`, `FP=0`, `FN=1`.

Limitations:

- It glob-searches scored files rather than validating the canonical 68-page manifest.
- It does not explain how the scored files were generated.
- It does not regenerate candidates or CNN scores.

Status:

- Superseded as canonical evaluator by `make eval-issue120-full`, but still useful as historical evidence.

### `tools/repro_accuracy/reproduce_clean_seed_v12.py`

Role:

- Attempts to regenerate clean seeds from previous hybrid outputs.
- Uses `logs/issue36_prep/20260208_bench_inventory.json`.
- Uses `logs/hybrid_generalization/verify_fixed_v10` with fixed score-to-run timestamp mappings:
  - `Shostakovich-Festival_Overture_Va`: `20260324_121505`
  - `Shostakovich-Sym5-Va`: `20260330_034727`
  - `Sibelius-Violin_Concerto-Viola`: `20260330_042631`
  - `Va_Prokofiev_Symphony1`: `20260330_044952`
  - `Va__Prokofiev_Symphony5`: `20260330_095914`
- Combines baseline, SR, and OMR/SR detector outputs.
- Runs probe scan and candidate filters.
- Writes final candidates to `logs/repro_v12_recovery_final/probe_candidates_filtered_v12`.

Limitations:

- Depends on log trees that are not source inputs in Git.
- Does not itself prove that those upstream logs can be regenerated by the current pipeline.
- Uses custom seed logic that must be compared against current production pipeline behavior before being considered a clean transplant target.

Status:

- Key candidate for reproducing the seed/candidate stage, but currently not a canonical full regeneration path.

### `tools/repro_accuracy/verify_repro_batch_final.py`

Role:

- Uses candidates from `logs/repro_v12_recovery_final/probe_candidates_filtered_v12`.
- Copies candidates into a verification output root.
- Runs `run_cnn_scoring_batch` with model:
  `logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth`.
- Evaluates scored outputs.

Important discrepancy:

- It evaluates with `xdist_threshold=30.0`.
- The canonical #134 evaluator and Golden Baseline config use `xdist_threshold=12.0`.

Status:

- Useful to test candidate -> CNN scoring regeneration, but it must be adjusted or paired with `make eval-issue120-full` to report canonical metrics.

### `evaluate_full_rescue_v1.py`

Status:

- PR #130, #131, and #132 refer to it as the native inference script used to maintain `TP=3580, FP=0, FN=1`.
- It is not currently present in `tools/repro_accuracy/` on `rebuild/issue120`.
- The exact script must be recovered from a historical branch/commit or artifact before those PR claims can be upgraded from historical claim to reproducible evidence.

## Current conclusion

The detector-level Golden Baseline has one verified level and two unresolved upstream levels.

### Verified

Saved post-CNN-scoring intermediates under `data/evaluation2/golden_baseline_eval2_bc23deb` evaluate to:

```text
TP=3580 / FP=0 / FN=1
```

using the canonical 68-page evaluator from #134.

### Not yet verified

The current repository has not yet proven that it can regenerate those intermediates from:

```text
HOMR / OMR / SR / SR-side HOMR / OMR-DLN
  -> hybrid consensus / seed preparation
  -> probe scan candidates
  -> CNN scoring
```

### Therefore

The clean transplant target should not yet be described as "full pipeline reaches TP=3580 / FP=0 / FN=1".

Current safer wording:

> Detector-level target: saved post-CNN-scoring Golden Baseline intermediates reproduce `TP=3580 / FP=0 / FN=1`; #136 must still determine which upstream generation path can regenerate them.

## Proposed staged verification plan

### Stage A: saved scored intermediates

Command:

```bash
make eval-issue120-full \
  ISSUE120_RESULTS_DIR=data/evaluation2/golden_baseline_eval2_bc23deb
```

Expected:

```text
TP=3580 / FP=0 / FN=1
```

Status: verified locally after #134.

### Stage B: saved candidates -> CNN scoring -> canonical evaluation

Goal:

- Use checked-in `pipeline2_no_peak_candidates.json` or regenerated candidates.
- Run only CNN scoring.
- Evaluate output with #134 canonical evaluator.

Required change:

- Either add a small wrapper around `run_cnn_scoring_batch`, or adapt `verify_repro_batch_final.py` so the final evaluation is performed by `make eval-issue120-full` with `xdist_threshold=12.0`.

Acceptance:

- Same canonical 68-page page set.
- Same metric contract as #134.
- If this fails, the problem is in CNN scoring, candidate layout, model path, or thresholding.

### Stage C: hybrid/probe seed regeneration -> CNN scoring -> canonical evaluation

Goal:

- Run `reproduce_clean_seed_v12.py` or a cleaned successor.
- Then run Stage B.

Known dependencies:

```text
logs/issue36_prep/20260208_bench_inventory.json
logs/hybrid_generalization/verify_fixed_v10/<timestamped runs>
logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth
```

Acceptance:

- Regenerated candidates must produce canonical detector metrics.
- Missing upstream log dependencies must be reported explicitly, not silently skipped.

### Stage D: slow upstream regeneration

Goal:

- Regenerate the baseline HOMR/OMR, SR, and SR-side HOMR/OMR outputs used by Stage C.

This is expected to be the expensive stage and should be run locally, not as a default PR check.

Acceptance:

- The regenerated upstream outputs can feed Stage C.
- If Stage C differs, compare upstream detection JSONs before modifying detector logic.

### Stage E: full pipeline 68-page run

Goal:

- Confirm that the current pipeline can regenerate the detector result end-to-end.

Acceptance:

- Full pipeline output, after canonical evaluation, matches the selected gate or produces a documented delta.

## Recommended immediate #136 next steps

1. Recover or locate `evaluate_full_rescue_v1.py` from historical commits/artifacts.
2. Decide whether `verify_repro_batch_final.py` should be replaced by a canonical Stage B wrapper.
3. Check whether the model path `logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth` is available locally and how it should be referenced.
4. Run Stage B locally using checked-in Golden Baseline candidates.
5. Record whether candidate -> CNN scoring can reproduce the #134 result under `xdist_threshold=12.0`.

## Decision status

No clean transplant target is final yet.

Interim target:

- keep `TP=3580 / FP=0 / FN=1` as the detector-level historical target;
- treat `data/evaluation2/golden_baseline_eval2_bc23deb` as a verified saved-intermediate benchmark;
- do not claim full-pipeline reproduction until Stage C/D/E are verified.
