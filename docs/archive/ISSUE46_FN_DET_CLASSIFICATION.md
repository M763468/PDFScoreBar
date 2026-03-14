# Issue #46 FN_det=15 Failure Type Classification (baseline th=0.5)

## Purpose

Issue #46 の Acceptance Criteria

- `FN_det=15` 全件の失敗タイプ分類

を満たすため、baseline (`eval2_fn_det_candidates_th0p5.csv`) を正本として分類結果を固定する。

## Source

- `logs/cnn_barline_classification/issue44_baseline_v1/eval2_fn_det_candidates_th0p5.csv`

## Classification Rule (revised)

- `候補なし`:
  - `best_cand` が空（候補未生成）
- `複線統合` (Double/End Bar Merging):
  - GT が複線（double/end/repeat）の片線定義
  - 候補が複線をまとめて含む、または相方線に寄って `IoU < 0.5`
- `幾何ミスマッチ` (Geometric Mismatch):
  - 候補は GT 近傍にあるが、幅過大・中心ズレ・縦過伸長で `IoU < 0.5`
- `別線マッチ` (False Assignment):
  - 隣接の別線を候補として選択している（局所補正で説明しづらい）

## Result (15/15)

| id | score | page | gt (x1,y1,x2,y2) | best_iou | best_cand | type | note |
|---:|---|---|---|---:|---|---|---|
| 1 | Sibelius-Violin_Concerto-Viola | page_001 | [3049,2266,3053,2373] | 0.2388 | [3038,2264,3042,2373] | 複線統合 | ダブルバー相方寄りの候補（表現差） |
| 2 | Sibelius-Violin_Concerto-Viola | page_004 | [2713,3166,2720,3274] | 0.3765 | [2713,3105,2731,3274] | 複線統合 | 2本をまとめた候補（7px→18px） |
| 3 | Sibelius-Violin_Concerto-Viola | page_004 | [2724,3163,2729,3274] | 0.4607 | [2713,3105,2731,3274] | 複線統合 | 2本をまとめた候補（5px→18px） |
| 4 | Sibelius-Violin_Concerto-Viola | page_004 | [2941,4088,2949,4195] | 0.3314 | [2930,4015,2957,4195] | 幾何ミスマッチ | 幅過大/縦過伸長（8px→27px） |
| 5 | Sibelius-Violin_Concerto-Viola | page_008 | [779,1732,783,1839] | 0.0000 | - | 候補なし | 候補未生成 |
| 6 | Sibelius-Violin_Concerto-Viola | page_008 | [787,1732,791,1839] | 0.0000 | - | 候補なし | 候補未生成 |
| 7 | Sibelius-Violin_Concerto-Viola | page_010 | [884,4065,888,4173] | 0.0000 | - | 候補なし | 候補未生成 |
| 8 | Va_Prokofiev_Symphony1 | page_001 | [839,3435,846,3538] | 0.0000 | - | 候補なし | 候補未生成 |
| 9 | Va_Prokofiev_Symphony1 | page_001 | [851,3434,856,3538] | 0.0000 | - | 候補なし | 候補未生成 |
| 10 | Va_Prokofiev_Symphony1 | page_006 | [3199,4102,3210,4207] | 0.4534 | [3183,4101,3216,4208] | 複線統合 | end bar周辺の複数候補で過幅側がbest化 |
| 11 | Va__Prokofiev_Symphony5 | page_003 | [601,451,609,563] | 0.0000 | - | 候補なし | 候補未生成 |
| 12 | Va__Prokofiev_Symphony5 | page_003 | [852,3864,861,3975] | 0.0000 | - | 候補なし | 候補未生成 |
| 13 | Va__Prokofiev_Symphony5 | page_008 | [906,910,910,1020] | 0.0884 | [921,907,925,1017] | 別線マッチ | 右側別線へマッチ（x中心差 +15px） |
| 14 | Va__Prokofiev_Symphony5 | page_015 | [909,2238,913,2346] | 0.0896 | [892,2237,901,2344] | 別線マッチ | 左側別線へマッチ（x中心差 -14.5px） |
| 15 | Va__Prokofiev_Symphony5 | page_016 | [779,1802,783,1912] | 0.0000 | - | 候補なし | 候補未生成 |

## Aggregate

- 候補なし: 8
- 複線統合: 4
- 幾何ミスマッチ: 1
- 別線マッチ: 2

## Implication for Track A

- 優先1: `候補なし` 8件の回収（peak 探索/前処理緩和）
- 優先2: `複線統合` 4件の分離表現改善（split 条件・複線扱い）
- 優先3: `幾何ミスマッチ` 1件の bbox 正規化改善
- 優先4: `別線マッチ` 2件の誤選択抑止（過適用抑制）
