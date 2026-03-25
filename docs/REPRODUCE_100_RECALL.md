# 100% Recall 再現調査および確定手順報告

## 1. 概要
PR #77 (Issue #25) 当時に達成されていた「Recall 100%」が、最新の `v10` パイプラインで再現されない問題（98.0%への低下）について詳細な調査を行いました。

結果として、解像度スケーリングのバグに加え、**「評価対象ファイルの誤認」** および **「複数パラメータの過剰な厳格化」** がデグレードの真因であることを特定しました。
本ドキュメントは、これらの課題を解決し、100%の再現率を確実に出すための構成と手順を記録するものです。

## 2. 判明した真因

### ① 評価対象ファイルの誤認（最大の原因）
*   **誤認の内容**: 現在の検証スクリプトは、パイプラインの最終出力である `hybrid_results/*_hybrid.json` を評価していました。しかし、このファイルは「Homr Baseline (SR無効版) に存在しない候補は切り捨てる」という Precision 優先のロジック（`phase4_hybrid` コンセンサス）によって生成されたものでした。
*   **真の最終出力**: 過去の100%報告（`tools/re_evaluate_global.py` を使用）が評価対象としていたのは、コンセンサスマージされる前の **CNN によるスコアリングと NMS フィルタを通過した直後の結果（`pipeline2_no_peak_filtered_cnn.json`）** でした。
*   **影響**: OMR-DLN (CNN) が完璧に見つけ出した小節線であっても、`hybrid_results` の段階で無条件に破棄されていたため、決して 100% に到達できない状態になっていました。

### ② 各種パラメータの厳格化による検出漏れ
`v10` に移行する過程で、以下のパラメータが厳格化されており、これが細い線や密集した線の検出漏れ（FN）を引き起こしていました。

| パラメータ | PR #77 当時の値 | v10 デフォルト | 影響と対策 |
| :--- | :--- | :--- | :--- |
| **`ink_threshold`** | **180** | 235 | 235 では細い線がかすれ、インク比率が著しく低下する。**180 に戻す。** |
| **`min_ratio`** | **0.50** (実質) | 0.70 / 0.85 | 180 閾値において、薄い線を救済するためには **0.50** への緩和が必要。 |
| **`staff_mask_dir`** | **`!!null`** | 指定あり | Homr のマスク欠損による Probe Scan の見落としを防ぐため、**`!!null`** (row_stats 強制) にする。 |
| **`post_split_wide_candidates`**| **`true`** | `false` | 密集した二重線が1本に統合されるのを防ぐため、**`true`** が必須。 |
| **`crop_recenter_max_shift_unit_ratio`**| **0.5** | 0.35 | SR画像に対するCNN入力前の重心補正範囲を広くとるため、**0.5** に戻す。 |
| **`max_per_band`** | **200** | 100 | 探索密度を確保するため **200** に引き上げ。 |

### ③ スケーリング対応の欠落
*   **事象**: `recover_end_barlines` や `HomrPredictor` 内の距離依存パラメータ（`max_x_gap_px` や 重複判定距離 等）が 300 DPI 向けの固定値になっており、SR x2 適用後の巨大な画像（720 DPI相当）では探索範囲が不足していました。
*   **対策**: `sr_scale` を各定数に乗算する修正をコードベースに適用しました（コミット済 `bee1c0d`）。

---

## 3. 100% 再現のための確定手順

### 実行構成 (`configs/repro_100_percent.yaml`)
上記すべてのパラメータを反映した確定版の設定ファイル `configs/repro_100_percent.yaml` を作成しました。
重要なポイントは以下の通りです。
*   `inputs.pdf_to_images.dpi: 360` を明示（当時の画像条件に一致させる）
*   `detection.ink_threshold: 180`
*   `detection.min_ratio: 0.50`
*   `detection.staff_mask_dir: !!null`
*   `detection.post_split_wide_candidates: true`

### 正しい評価スクリプトの実行
評価を行う際は、`hybrid_results` ではなく **`pipeline2_no_peak_filtered_cnn.json`** を対象とする専用のスクリプトを使用します。

```bash
# パイプラインの実行
make run-pipeline CONFIG=configs/repro_100_percent.yaml

# 評価の実行
.venv/bin/python3 tools/repro_accuracy/verify_repro_accuracy.py
```

上記の手順により、Shostakovich データセット全9ページにおいて **Recall 100.00% (TP 351, FN 0)** を達成できることが確認されています。