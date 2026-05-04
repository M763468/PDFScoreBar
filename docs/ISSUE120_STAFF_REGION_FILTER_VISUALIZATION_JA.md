# Issue 120 五線領域フィルタ可視化メモ

## 作成した可視化

出力先:

- `logs/issue120_e2e_recovery/staff_region_filter_investigation/visuals/`

主なファイル:

- `dropped_tp_staff_region_contact_sheet.png`
- `shostakovich_sym5_va_page006_tp_drop_crop.png`
- `sibelius_vc_va_page006_tp_drop_crop.png`
- `prokofiev5_page002_multi_tp_drop_crop.png`
- 各ページの `*_overview.png`
- `visual_manifest.json`

凡例:

- 水色の帯: 現在 CNN-stage の `staff_vov_threshold` 判定で使われる
  seed-derived staff band
- オレンジ: HOMR `debug_3_staff.png` の raw staff mask pixel
- マゼンタ: GT box
- 赤: VOV 閾値を上げると破棄される、もともとは GT に match していた予測

## 可視化した代表例

| score/page | dropped prediction | matched GT | seed band | seed VOV | threshold |
| --- | --- | --- | --- | ---: | ---: |
| `Shostakovich-Sym5-Va/page_006` | `[911, 2990, 913, 3086]` | `[917, 2985, 921, 3082]` | `[2977, 3012]` | 0.229167 | 0.25 |
| `Sibelius-Violin_Concerto-Viola/page_006` | `[1552, 4072, 1563, 4178]` | `[1556, 4072, 1560, 4175]` | `[4149, 4175]` | 0.245283 | 0.25 |
| `Va__Prokofiev_Symphony5/page_002` | `[709, 3561, 710, 3674]` | `[701, 3561, 710, 3670]` | `[3668, 3702]` | 0.053097 | 0.25 |

これらはすべて、現在の評価では真の GT に match している TP です。しかし現在の
seed-derived staff band に対する VOV が低いため、`staff_vov_threshold` を上げると
FN 化します。

## 現在の五線領域の判断方法

現在の処理では「五線領域」が一種類ではありません。

1. seed generation の候補フィルタ
   - `logs/hybrid_pipeline_bench/.../debug_3_staff.png` を staff mask として読む。
   - `filter_probe_candidates()` が bbox 内の staff mask pixel 比率を計算する。
   - `min_staff_overlap_ratio: 0.02` 未満なら候補を落とす。

2. pass2 probe scan
   - 現行 config では `enable_heuristic_filters: false`。
   - そのため `candidate_filter_kwargs.min_staff_overlap_ratio` は pass2 候補には効かない。

3. CNN-stage staff overlap filter
   - `bands_from=probe_seeds` から seed boxes を読み、`build_row_stats()` で y 方向の
     median band を作る。
   - `filter_by_staff_overlap()` は候補 bbox とこの band の縦方向 VOV だけを見る。
   - 判定式は `max_vov >= staff_vov_threshold`。
   - 現行 config は `staff_vov_threshold: 0.0` なので、実質的に全候補が通る。

## なぜ閾値を上げると GT を破棄するのか

今回の可視化で、seed-derived staff band が真の小節線全体を覆えていない例が確認できました。

例えば `Va__Prokofiev_Symphony5/page_002` では、真の小節線 box は
`y=3561..3670` 付近にありますが、seed-derived band は `y=3668..3702` と下端側に寄っています。
このため、GT と一致している予測でも VOV は `0.053` 程度にしかなりません。

つまり FN 増加の主因は「GT が五線外」ではなく、現在のフィルタ用 staff band が
実際の五線譜領域として不十分、または位置ずれしていることです。

## 改善策

推奨する改善順は次の通りです。

1. raw `debug_3_staff.png` をそのまま pixel overlap 判定に使わない
   - GT 3581件中 3235件が pixel overlap `< 0.02` になる。
   - line mask は細すぎるため、barline box の inside-staff 判定には直接使えない。

2. line mask から robust な staff-region band を作る
   - 5本線をクラスタリングし、上端から下端までを staff region として膨張する。
   - 膨張量は固定pxではなく `unit_size` ベースにする。
   - staff 1段ごとに band を作り、上下隣接 staff や divisi を不用意に結合しない。

3. seed-derived band だけに依存しない
   - seed boxes 由来の median band は、候補生成の偏りをそのまま staff 認識に持ち込む。
   - 今回の FN 化例のように、真の小節線の一部だけを覆う band になることがある。

4. 新しい staff-region band を replay で検証する
   - 対象は `fp_out_of_staff` だけでは不十分。
   - 全 GT/TP box に対して、同じ band 判定をかけて FN 化しないことを確認する。
   - 受け入れ条件は、少なくとも現行 best の measure-count `abs_delta_sum=4` を悪化させないこと。

5. pass2 scan の候補生成にも同じ staff-region 表現を使う
   - 現在は pass2 で `enable_heuristic_filters: false` のため、seed 側の mask overlap
     と CNN 側の band VOV の間に穴がある。
   - ただし broad filter として即導入せず、まず replay で FP/FN/measure-count の影響を確認する。

## 次に試すべき小実験

実装前に、次の replay-only 実験を行うのが安全です。

1. `debug_3_staff.png` から unit-scaled staff-region band を生成する。
2. 生成した band を全 68 ページの GT/TP/FP に適用する。
3. 次を CSV 化する。
   - `fp_out_of_staff` のうち落ちる数
   - 既存 TP のうち落ちる数
   - 落ちる TP の具体例
   - measure-count KPI の変化
4. FN が増える場合は、その例を今回と同様に可視化し、band 生成が悪いのか、GT が悪いのかを分ける。

この replay で GT/TP を保ったまま `fp_out_of_staff` を十分に落とせることが確認できてから、
pipeline 側へ narrow fix として実装する。
