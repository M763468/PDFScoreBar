# Issue #53 Probe Rescue (Gap Rescue) Evaluation

## Overview
Issue #53「候補探索の改善」において導入された Probe Rescue (特に Gap Rescue) 機能の、全パイプライン（Probe Scan + CNN Scoring + Global Evaluation）における効果を評価するためのスクリプト群です。

## Contents
- `evaluate_full_rescue_v1.py`: 
  - `evaluation2` データセット（68ページ）に対して、Gap Rescue を有効にしたプローブスキャンを実行し、既存の CNN モデルでスコアリングを行った後、`center_anchor` ルールで最終的な精度を算出します。

## Prerequisites
- Python 環境（`.venv_pdf` 推奨）
- 以下のデータ/ログが配置されていること：
  - `data/evaluation2/images`, `annotations`
  - `logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12`
  - `logs/cnn_barline_classification/issue44_baseline_v1/cnn_classifier_best.pth`

## Usage
リポジトリルートから以下のコマンドを実行してください：

```bash
PYTHONPATH=. .venv_pdf/bin/python experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py
```

## Results
実行後、`logs/issue53_full_eval_rescue_v1/` に以下のファイルが生成されます：
- `global_summary.csv`: 最終的な Precision / Recall 統計
- `*_scored.json`: 各ページの検出・判定結果

この評価により、Issue #51 で特定された「候補完全欠落 10件」のうち、何件が物理的に救済されたかを確認できます。
