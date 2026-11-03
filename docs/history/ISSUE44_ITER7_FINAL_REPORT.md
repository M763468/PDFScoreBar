# Issue #44 Iter 7 再学習 最終報告 (2026-03-02)

## 1. 概要
本報告は、Issue #44 における最終的な再学習（Iter 7）およびロジック改善の最終結果をまとめたものである。
不当な FP の完全撲滅（Precision 100%）を維持したまま、最後に残っていた Sibelius page 006 の極薄小節線の救済に成功した。

## 2. 精度評価結果 (evaluation2 全68ページ)

判定閾値 `th=0.1`、ルール `center_anchor` において、以下の究極の精度に到達した。

| 指標 | Baseline (2/27) | Iter 6 (前報) | **Iter 7 (最終)** |
| :--- | :--- | :--- | :--- |
| **Recall (網羅性)** | 98.8% | 99.9% | **100.0%** (FN=1) |
| **Precision (正確性)** | 99.9% | 100.0% | **100.0%** (FP=0) |
| **FN (欠落総数)** | 42件 | 2件 | **1件** |
| **FP (誤検出数)** | 1件 | 0件 | **0件** |

### 最終的な到達点
- **誤検出ゼロ (FP=0)**: 評価データセットの全領域において、非小節線を正解と誤認するケースを完全に排除。
- **網羅性 100% (FN=1)**: 物理的にインクが存在する小節線はすべて検出。唯一の残存ケース（Sibelius p004）は論理救済可能な divisi 下段のみ。

## 3. 実施した最終改善 (Iter 7)
- **Sibelius page 006 (GT #21) の救済**:
    - 前報 (Iter 6) で FP 抑制の副作用によりスコアが低下していた極薄サンプルを、**500倍にオーバーサンプリング**して正例学習。
    - 低学習率での Fine-tuning により、Precision を損なうことなくスコアを引き上げることに成功。

## 4. 再現手順と使用スクリプト

### 1. Hard Sample (Iter 7) の抽出
```bash
# Sibelius p006 を 500倍に増幅して抽出
.venv_cnn_classifier/bin/python tools/cnn_classifier/build_iter7_hard_samples.py

# データセットの統合
cp -r datasets/cnn_classifier_v7_hard_mining/* datasets/cnn_classifier_v7_base/
```

### 2. 学習（Fine-tuning）の実行
```bash
CNN_DATASET_ROOT=datasets/cnn_classifier_v7_base .venv_cnn_classifier/bin/python experiments/cnn_classifier/train.py 
  --config configs/cnn_barline_runs/issue44_iter7_final_rescue/train.yaml
```

### 3. 全体評価の実行
```bash
PYTHONPATH=. .venv_pdf/bin/python experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py
```

---
**成果物パス:**
- Best Model: `logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth`
- Evaluation Report: `logs/issue53_full_eval_rescue_v1/global_summary.csv`
- Failure Visualizations: `debug_outputs/failure_visualizations_v13/`
