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

### PR #57: Issue #44 final baseline

- PR: #57 `feat(cnn): finalize baseline retraining and improve staff clustering logic (#44)`
- Head branch: `task/cnn-barline-classifier-retrain-eval2-gt`
- Head commit: `b58b988979573e651c5a2f57270ebc1c830135b4`
- Merge commit: `87fb6d0a47294d7879500285a62e519373498b65`
- Claimed result: `evaluate_full_rescue_v1.py` produced final detector result with `FP=0`, `FN=1`.
- Important recovered file:
  - `experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py`

Recovered script behavior:

```text
bands_from = logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
output_root = logs/issue53_full_eval_rescue_v1
model_path = logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth
```

It runs:

1. `run_probe_scan_batch` over all `data/evaluation2/images/page_*.png` with gap/x-peak/rightmost/divisi rescue.
2. `tools.cnn_classifier.score_candidates_batch.run_scoring_batch` with threshold `0.1`, crop recentering, and staff-aware filtering.
3. `tools/re_evaluate_global.py` using `center_anchor`, `vov_threshold=0.5`, `xdist_threshold=12.0`.

Interpretation:

- This is the likely historical source for `logs/issue53_full_eval_rescue_v1`.
- The checked-in `data/evaluation2/golden_baseline_eval2_bc23deb/eval_config.yaml` points to `logs/issue53_full_eval_rescue_v1` and uses the same canonical evaluation thresholds.
- This script is experimental and references pre-refactor module paths (`src.pipeline.probe_scan`, `tools.cnn_classifier.score_candidates_batch`). It is evidence, not a drop-in current pipeline command.

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
- Current finding: the script name appears to refer back to the experimental Issue #53/Issue #44 script under `experiments/issue53_probe_rescue/`, not to a current `tools/repro_accuracy/` script. The exact command/run artifact used for #131 still needs local confirmation.

### PR #132: refactor step

- PR: #132 `Refactor: Step 5 (Phase 2) - Pipeline and Utility Refactoring`
- Merge commit: `fa0bb34c2d103f796228039740ae0412df47298b`
- Claimed result: `evaluate_full_rescue_v1.py` with native inference maintained `TP=3580, FP=0, FN=1`.
- Current finding: same as #131. The historical script has been located under PR #57, but the exact #132 execution path remains to be reproduced or confirmed from local logs.

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

### `experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py`

Recovered from PR #57 head commit `b58b988979573e651c5a2f57270ebc1c830135b4`.

Role:

- Historical experiment script that likely generated `logs/issue53_full_eval_rescue_v1`.
- Starts from `logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12` as `bands_from`.
- Runs probe scan with rescue options.
- Runs CNN scoring with `issue44_iter7_final_rescue_v1/cnn_classifier_best.pth`.
- Evaluates with `xdist_threshold=12.0`.

Limitations:

- Uses old module paths and pre-#120 APIs.
- Assumes local log/model artifacts.
- Does not run the current full pipeline.

Status:

- Important historical source evidence.
- Should not be restored as-is into current workflow; instead, its stages should be represented by Stage B/C/D commands.

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

- Superseded for canonical Stage B verification by `tools/issue120/score_candidates_then_eval_full68.py`.
- Candidate for removal or archival after Stage B is validated, because overlapping scripts are a source of confusion.

### `tools/issue120/score_candidates_then_eval_full68.py`

Role:

- New Stage B wrapper for #136.
- Copies canonical candidate files into a fresh scoring output tree.
- Runs current `src.pipeline.steps.cnn_scoring.run_cnn_scoring_batch`.
- Evaluates newly scored outputs using the #134 canonical full-68 evaluator.
- Writes provenance that marks the result as `stage_b_candidate_to_cnn_scoring`.

Default command:

```bash
make verify-issue120-stage-b ISSUE120_CLEAN_OUTPUT=1
```

Optional command with historical staff-band source:

```bash
make verify-issue120-stage-b \
  ISSUE120_CLEAN_OUTPUT=1 \
  ISSUE120_BANDS_FROM=logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

Expected local prerequisites:

```text
data/evaluation2/golden_baseline_eval2_bc23deb/**/pipeline2_no_peak_candidates.json
data/evaluation2/images/**/page_*.png
data/evaluation2/annotations/**/boxes_sorted.json
logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth
```

Interpretation:

- If this reproduces `TP=3580 / FP=0 / FN=1`, then the saved candidates plus current CNN scoring path are compatible with the golden detector target.
- If this fails, the mismatch is in model availability/content, CNN scoring implementation, crop recentering/staff filtering, candidate layout, or evaluation defaults.
- It still does not prove seed/candidate regeneration.

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

Command:

```bash
make verify-issue120-stage-b ISSUE120_CLEAN_OUTPUT=1
```

If local staff-band artifacts are available, also run:

```bash
make verify-issue120-stage-b \
  ISSUE120_CLEAN_OUTPUT=1 \
  ISSUE120_BANDS_FROM=logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

Acceptance:

- Same canonical 68-page page set.
- Same metric contract as #134.
- If this fails, the problem is in CNN scoring, candidate layout, model path, staff-band source, or thresholding.

Status: wrapper added; local execution still required.

### Stage C: hybrid/probe seed regeneration -> CNN scoring -> canonical evaluation

Goal:

- Run `reproduce_clean_seed_v12.py` or a cleaned successor.
- Then run Stage B with `ISSUE120_CANDIDATES_DIR` pointing at regenerated candidates.

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

1. Run Stage B locally without `ISSUE120_BANDS_FROM`.
2. Run Stage B locally with historical `ISSUE120_BANDS_FROM` if that artifact exists.
3. Compare both outputs against the Stage A result.
4. If Stage B passes, archive or delete `verify_repro_batch_final.py` in a later cleanup PR to reduce script overlap.
5. If Stage B fails, inspect `logs/issue120_e2e_recovery/stage_b_candidate_scoring_eval/detector_page_metrics.csv` and compare with Stage A page metrics.
6. Then proceed to Stage C using `reproduce_clean_seed_v12.py` or a cleaned successor.

## Decision status

No clean transplant target is final yet.

Interim target:

- keep `TP=3580 / FP=0 / FN=1` as the detector-level historical target;
- treat `data/evaluation2/golden_baseline_eval2_bc23deb` as a verified saved-intermediate benchmark;
- do not claim full-pipeline reproduction until Stage C/D/E are verified.
