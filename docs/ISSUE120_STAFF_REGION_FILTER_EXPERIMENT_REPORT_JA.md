# Issue 120 五線領域フィルタ実験レポート

## 目的

`docs/ISSUE120_STAFF_REGION_FILTER_VISUALIZATION_JA.md` の改善策に沿って、
raw staff mask から五線譜領域 band を作り、既存の best candidate set に replay した。

目的は次の確認である。

- `fp_out_of_staff` を落とせるか。
- 既存 TP / GT を落として FN を増やさないか。
- 最終 KPI である measure-count `abs_delta_sum=4` を悪化させないか。

実装コードや config は変更していない。実験用 JSON と KPI 出力のみ `logs/` 配下に生成した。

## 入力と出力

入力:

- Manifest: `logs/issue120_e2e_recovery/eval2_full_configs/manifest.json`
- Base run root: `logs/full_pipeline_runs/evaluation2_full_v12_restore`
- Base candidate set:
  `score_ge_0p5_minh_2p8_softshort_2p9_scorelt_0p9`
- GT: `data/evaluation2/annotations`
- Images: `data/evaluation2/images`

出力:

- v1: `logs/issue120_e2e_recovery/staff_region_filter_experiment_v1/`
- v2: `logs/issue120_e2e_recovery/staff_region_filter_experiment_v2/`

各 experiment directory には以下を保存した。

- `detection_summary.csv`
- `detection_per_page.csv`
- `dropped_predictions.csv`
- staff band CSV
- variant 別 replay run-root
- variant 別 `measure_count/`

## 実験内容

### v1: `debug_3_staff.png` 由来の line-mask band

`debug_3_staff.png` を画像サイズに resize し、横線 row をクラスタリングして staff-region band を作成した。
5本線グループを想定し、推定 staff spacing に対して上下に unit-scaled pad を加えた。

比較した VOV threshold:

- `0.10`
- `0.25`
- `0.50`

### v2: hybrid `*_staff_mask.png` 由来の adaptive band

v1 では `Shostakovich-Sym5-Va/page_025` の mask が line-like ではなく太い region-like mask で、
band が1本に崩れた。そのため v2 では hybrid output の `*_staff_mask.png` を使い、
以下を自動判定した。

- region-like mask: 太い row segment を staff-region として扱う。
- line-like mask: v1 と同様に5本線グループへ変換する。

同じく VOV threshold `0.10`, `0.25`, `0.50` を比較した。

## 検出レベル結果

Base は current best candidate set の replay である。

| experiment | variant | TP | FP | FN | delta TP | delta FP | delta FN | dropped TP | dropped `fp_out_of_staff` |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| base | `base_best_softshort` | 3558 | 64 | 23 | 0 | 0 | 0 | 0 | 0 |
| v1 | `robust_staff_vov_0p10` | 3511 | 58 | 70 | -47 | -6 | +47 | 47 | 3 |
| v1 | `robust_staff_vov_0p25` | 3511 | 58 | 70 | -47 | -6 | +47 | 47 | 3 |
| v1 | `robust_staff_vov_0p50` | 3510 | 18 | 71 | -48 | -46 | +48 | 48 | 3 |
| v2 | `hybrid_staff_region_vov_0p10` | 3502 | 61 | 79 | -56 | -3 | +56 | 56 | 2 |
| v2 | `hybrid_staff_region_vov_0p25` | 3502 | 60 | 79 | -56 | -4 | +56 | 57 | 2 |
| v2 | `hybrid_staff_region_vov_0p50` | 3501 | 27 | 80 | -57 | -37 | +57 | 57 | 3 |

結果:

- `fp_out_of_staff` は最大でも 3 件しか落ちない。
- その一方で、TP が 47-57 件落ちる。
- FP は減るが、FN 増加の方が大きく、検出レベルでは採用不可。

## Measure-count KPI

| experiment | variant | pred | gt | delta | abs delta sum | delta pages | precision | recall |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| base | `base_best_softshort` | 3380 | 3384 | -4 | 4 | 2 | 0.998817 | 0.997636 |
| v1 | `robust_staff_vov_0p10` | 3340 | 3384 | -44 | 44 | 4 | 0.998802 | 0.985816 |
| v1 | `robust_staff_vov_0p25` | 3340 | 3384 | -44 | 44 | 4 | 0.998802 | 0.985816 |
| v1 | `robust_staff_vov_0p50` | 3340 | 3384 | -44 | 44 | 4 | 0.997006 | 0.984043 |
| v2 | `hybrid_staff_region_vov_0p10` | 3334 | 3384 | -50 | 50 | 7 | 0.998800 | 0.984043 |
| v2 | `hybrid_staff_region_vov_0p25` | 3334 | 3384 | -50 | 50 | 7 | 0.998800 | 0.984043 |
| v2 | `hybrid_staff_region_vov_0p50` | 3334 | 3384 | -50 | 50 | 7 | 0.998800 | 0.984043 |

結果:

- 現行 best `abs_delta_sum=4` に対して、v1 は `44`、v2 は `50` まで悪化。
- したがって、今回の staff-region band replay は measure-count 目的では採用不可。

## 主な悪化ページ

v1:

- `Shostakovich-Sym5-Va/page_025`: `-36`
- `Sibelius-Violin_Concerto-Viola/page_004`: `-4`
- 既存の残課題:
  - `Sibelius-Violin_Concerto-Viola/page_006`: `-3`
  - `Va_Prokofiev_Symphony1/page_005`: `-1`

v2:

- `Shostakovich-Sym5-Va/page_010`: `-18`
- `Va__Prokofiev_Symphony5/page_021`: `-19`
- `Shostakovich-Sym5-Va/page_006`: `-4`
- `Sibelius-Violin_Concerto-Viola/page_004`: `-4`
- 既存の残課題:
  - `Sibelius-Violin_Concerto-Viola/page_006`: `-3`
  - `Va_Prokofiev_Symphony1/page_005`: `-1`

## 解釈

今回の実験で分かったこと:

1. raw `debug_3_staff.png` から単純に staff-region band を作るだけでは不十分。
   - page によって line-like mask と region-like mask が混在する。
   - v1 は `Shostakovich-Sym5-Va/page_025` で band が1本に崩れた。

2. hybrid `*_staff_mask.png` を使っても、そのままでは不十分。
   - v2 では low-band ページは解消したが、TP/FN はさらに悪化した。
   - staff region が真の小節線全体を覆えない、または対象 staff を取り違えるページが残る。

3. `fp_out_of_staff` だけを見るとよさそうに見えても、全GT/TPで見ると破綻する。
   - 落とせた `fp_out_of_staff` は 2-3 件のみ。
   - 代わりに 47-57 件の TP が落ちた。

4. 現時点で「五線領域 band への y方向VOV」だけを broad filter にするのは危険。
   - 現行 best の measure-count KPI を大きく悪化させる。

## 改善方針

次に試すべきなのは、単純な y方向 band VOV ではなく、より局所的な staff membership 判定である。

候補:

1. x位置を考慮した staff membership
   - 現在の band はページ幅全体の y範囲として扱われる。
   - 実際には staff/system は x方向に開始・終了があり、局所的に存在する。
   - bbox center x 付近で staff line が存在するかを見て、band 全幅判定を避ける。

2. staff-line group ごとの x-range を保持する
   - band を `(y1, y2)` だけでなく `(x1, y1, x2, y2)` として扱う。
   - `debug_3_staff.png` から staff group ごとに横方向 coverage を推定する。
   - `fp_out_of_staff` が同じ y範囲にいても、staff x-range 外なら落とせる。

3. GT/TP-first replay を必須にする
   - 新しい staff 判定は、まず全 GT と現行 TP に適用する。
   - TP が落ちるページを可視化してから閾値を決める。

4. count-affecting FP に限定する
   - 29件の `fp_out_of_staff` 全体を狙うのではなく、measure-count に効くものを優先する。
   - 近傍GT duplicate や count-neutral なものは broad filter の対象から外す。

## 結論

今回の実験は採用不可。

`debug_3_staff.png` または hybrid `*_staff_mask.png` から作った staff-region band に対し、
単純な y方向 VOV threshold をかける方法は、`fp_out_of_staff` を十分に落とせず、
真のTPを大量に落として measure-count を大きく悪化させた。

次は、x-range を持つ局所 staff-region 判定を replay-only で試すべきである。
