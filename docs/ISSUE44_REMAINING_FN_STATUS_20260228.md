# Issue #44 Remaining FN Status (2026-02-28)

## Scope
- Branch: `task/cnn-barline-classifier-retrain-eval2-gt`
- Goal: GT修正後の残FNを可視化し、残件に対処しやすい状態を固定する

## Repro

### 1. Baseline再現

```bash
PYTHONPATH=. .venv_cnn_classifier/bin/python \
  tools/cnn_classifier/score_candidates_batch.py \
  --config configs/cnn_barline_runs/issue44_baseline_v1/score_candidates_batch.yaml

PYTHONPATH=. .venv_cnn_classifier/bin/python \
  tools/re_evaluate_global.py \
  --config configs/cnn_barline_runs/issue44_baseline_v1/evaluate_global_th0p1.yaml
```

期待値:
- `TP=3561, FP=2, FN=23, FN_cnn=8, FN_det=15`

### 2. 現時点の最良条件再現

```bash
PYTHONPATH=. .venv_cnn_classifier/bin/python \
  tools/re_evaluate_global.py \
  --config configs/cnn_barline_runs/issue44_baseline_v1/issue44_evaluate_global_same_source_croprecenter_v2_ge0p5_th0p1.yaml
```

GT修正後期待値:
- `TP=3563, FP=2, FN=18, FN_cnn=4, FN_det=14`

## Current Best Condition
- Scored root:
  - `logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12_same_source_bboxnorm_w0p8_h4p0_patch10_croprecenter_v2_ge0p5`
- Eval config:
  - `configs/cnn_barline_runs/issue44_baseline_v1/issue44_evaluate_global_same_source_croprecenter_v2_ge0p5_th0p1.yaml`

## GT Fix Applied
- Removed 3 misannotated GT entries:
  - `Sibelius-Violin_Concerto-Viola/page_010`
    - `[669, 3729, 673, 3836]`
    - `[923, 3369, 927, 3478]`
  - `Va__Prokofiev_Symphony5/page_011`
    - `[2382, 905, 2386, 1014]`

## Remaining FN After GT Fix
- Total: `18`
- `FN_cnn=4`
- `FN_det=14`

## Visual Artifacts
- Directory:
  - `logs/cnn_barline_classification/issue44_baseline_v1/fn_remaining_same_source_croprecenter_v2_ge0p5_th0p1_after_gtfix`
- Sheets:
  - `contact_sheet_fn_cnn.png`
  - `contact_sheet_fn_det.png`
- Detail:
  - `summary.json`

## Interpretation
- GT修正でまず 3件減ったため、以後の対処対象はこの `18件` に絞れる。
- 再学習 iter2/3/4 は baseline を超えず、現時点では前処理改善の方が有効。
- 次段では、この18件をカテゴリ別に処理し、
  - 評価ルールで吸収できるもの
  - 純粋な detector / classifier 改善が必要なもの
 へ切り分ける。
