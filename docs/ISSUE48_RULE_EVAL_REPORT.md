# Issue #48 Evaluation Rule Reframe Report

## 目的
- IoU単独判定から拡張した複数ルールを同一入力で比較し、`FN_det/FN_cnn/TP/FP/FN` と最終目標（小節番号付与）の関係を確認する。
- #46で整理した失敗4分類（候補なし/複線統合/幾何ミスマッチ/別線マッチ）ごとに、判定差分を定量化する。

## 追加実装
- `tools/evaluate_barline_rules.py`
  - 4ルール同時評価:
    - `baseline_iou`: IoU>=0.5（既存 `greedy_barline_match` と同一）
    - `relaxed_geom`: IoU>=0.3 OR (縦重なり>=0.7 かつ 中心x距離<=5)
    - `coverage_ioa`: IoA(GT基準)>=0.8 かつ 縦重なり>=0.7
    - `center_anchor`: 縦重なり>=0.5 かつ 中心x距離<=12
  - 出力:
    - `rule_eval_per_page.csv`
    - `rule_eval_summary.csv`
    - `rule_eval_fn_det15_cases.csv`
    - `rule_eval_fn_det15_by_category.csv`
    - `rule_eval_kpi_inversion_cases.csv`
- `docs/ISSUE48_FN_DET15_CLASSIFICATION.csv`（#46の15件分類をCSV化）
- `configs/cnn_barline_runs/issue44_baseline_v1/issue48_rule_eval_th0p1.yaml`

## 実行結果（eval2, th=0.1, 68ページ）
- 出力: `logs/cnn_barline_classification/issue48_rule_eval/eval2_th0p1/rule_eval_summary.csv`

| rule | TP | FP | FN_total | FN_cnn | FN_det | Recall | Precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline_iou | 3561 | 2 | 23 | 8 | 15 | 0.9936 | 0.9994 |
| relaxed_geom | 3563 | 11 | 21 | 10 | 11 | 0.9941 | 0.9969 |
| center_anchor | 3563 | 11 | 21 | 11 | 10 | 0.9941 | 0.9969 |
| coverage_ioa | 3534 | 40 | 50 | 12 | 38 | 0.9860 | 0.9888 |

解釈:
- `relaxed_geom` / `center_anchor` は `FN_det` 改善に有効（15 -> 11/10）が、FPは増加。
- `coverage_ioa` は過検出が大きく不適。

## #46の4分類への影響（15件）
- 出力: `logs/cnn_barline_classification/issue48_rule_eval/eval2_th0p1/rule_eval_fn_det15_by_category.csv`

要点:
- `候補なし` 8件: すべて未解決（全ルールで `FN_det`）
- `別線マッチ` 2件: すべて未解決（全ルールで `FN_det`）
- `幾何ミスマッチ` 1件: `relaxed_geom` / `center_anchor` で `TP` 化
- `複線統合` 4件: `relaxed_geom` / `center_anchor` で一部 `TP` 化（ただし未回収も残る）

## 「検出KPI改善だが最終KPI悪化」再現確認
- ルール比較単体（同一候補集合）では、`MeasureAbsDeltaSum` が全ルール同値で逆転ケースなし。
  - `rule_eval_kpi_inversion_cases.csv` は空。
- 追加で #46 の9ページセットを比較:
  - `track_a_split_v1` vs `track_a_noexistingsuppr_v1`
  - 検出KPI: `FN_total -3`, `FN_det -3`, `FP +12`
  - 番号付与proxy（本ツールの measure_abs_delta_sum）: `13 -> 12`（悪化は未再現）

結論:
- 現在のproxyは差分感度が低く、最終KPIの逆転を常に検出できない。
- #48では「局所的な番号ズレ/分割誤り」を直接数える指標を追加する必要がある。

## probe候補生成とGT判定の不整合（現時点）
1. 複線（double/end bar）で、検出候補が2本を包括するbboxになりやすい。
2. IoU中心判定では、包含していても幅過大/中心ずれで `FN_det` 扱いになりやすい。
3. `existing suppression` は `FN_det` を減らせる一方でFP増を招く（#46 A04）。

## 次Issueへの分割案（実装順）
1. 候補なし8件の回収（probe scan rescueの局所再探索）
2. 複線統合ケース向け評価・後段ロジック整合（double/end barの論理イベント化）
3. 最終KPIの高感度化（measure count差分だけでなく、局所番号ズレ件数を導入）
4. `existing suppression` の条件付き緩和（FN_det改善とFP抑制の両立）
