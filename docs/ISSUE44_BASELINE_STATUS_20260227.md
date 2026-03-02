# Issue #44 Baseline Status (2026-02-27)

## Scope
- Branch: `task/cnn-barline-classifier-retrain-eval2-gt`
- Base: `feature/batch_orchestrator`
- Goal: `evaluation2` GT を使った CNN 判定モデルの再学習フローを再現可能化し、評価指標を固定する

## Repro Commands

```bash
.venv_pdf/bin/python tools/re_evaluate_global.py \
  --config configs/cnn_barline_runs/issue44_baseline_v1/evaluate_global.yaml

.venv_pdf/bin/python tools/re_evaluate_global.py \
  --config configs/cnn_barline_runs/issue44_baseline_v1/evaluate_global_th0p1.yaml
```

## Config Fix Applied
- `configs/cnn_barline_runs/issue44_baseline_v1/score_candidates_batch.yaml`
- `configs/cnn_barline_runs/issue44_baseline_v1/evaluate_global.yaml`
- `configs/cnn_barline_runs/issue44_baseline_v1/evaluate_global_th0p1.yaml`

上記3ファイルの `scored_root/logs` を
`logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12`
へ統一。旧設定（`logs/issue36_prep/...`）では `0 scored files` になる。

## Current Metrics (68 pages, GT=3584)
- `threshold=0.5`: TP=3542, FP=1, FN=42, FN_cnn=27, FN_det=15
  - Recall=0.988281, Precision=0.999718
- `threshold=0.1`: TP=3561, FP=2, FN=23, FN_cnn=8, FN_det=15
  - Recall=0.993583, Precision=0.999439

## Artifacts
- Model: `logs/cnn_barline_classification/issue44_baseline_v1/cnn_classifier_best.pth`
- Eval CSV:
  - `logs/cnn_barline_classification/issue44_baseline_v1/eval2_global_summary.csv`
  - `logs/cnn_barline_classification/issue44_baseline_v1/eval2_global_summary_th0p1.csv`
- Workflow note:
  - `tools/cnn_classifier/README_issue44_retrain_eval2.md`

## Relation to #48
- #48 の評価ルール再設計はマージ済み（PR #50）かつ Issue close 済み。
- #44 ではこの baseline を基準に、必要時のみ追加再学習 run を実施する。
