# Issue #46 FN_det Improvement Experiment Log

## Purpose

`evaluation2` の `FN_det`（候補生成/前処理起因の miss）改善に向けた試行を、再現可能な形で記録する。

このドキュメントは次の目的で使う。

- 何を試したかを時系列で残す
- baseline との差分を明確にする
- 効かなかった案の再試行を避ける
- Issue コメントの要約元（長文記録の正本）にする

## Recording Rules

- 実験ごとに `Experiment ID` を付ける（例: `E46-PS-001`）
- `logs/` の成果物パスと Issue コメント URL を必ず記録する
- baseline 比較なしの結果は採用判断しない
- 採用/不採用/保留を明記する
- 仮説と検証方法をセットで書く（推測だけ残さない）

## Baseline (Current Reference)

- Target set: `logs/cnn_barline_classification/issue44_baseline_v1/eval2_fn_det_candidates_th0p5.csv`
- Count: `15 GT` (`10 pages`)
- Current eval baseline:
  - `threshold=0.1`: `TP=3561`, `FP=2`, `FN=23`
  - `threshold=0.5`: `TP=3542`, `FP=1`, `FN=42`
- `FN_det` focus baseline at `th=0.5`: `15`

## Terms (for this document)

- `th`
  - `re_evaluate_global.py` で使う **CNN score threshold**（候補採択しきい値）
  - 例: `th=0.1` は `score > 0.1` の候補を最終採択
- `ge` (`crop_recenter_apply_if_width_ge_unit_ratio`)
  - score-side crop recenter を適用する候補幅の **下限**（`unit_size` 比）
  - 意味: `bbox_width >= ge * unit_size` の候補にだけ crop recenter を適用
  - 例: `ge=0.4` は「幅が `0.4 * unit_size` 以上の候補のみ recenter 対象」

## Experiment Template

### Experiment ID: `E46-XXX-000`

- Date:
- Branch:
- Scope:
- Hypothesis:
- Change:
- Target data:
- Baseline for comparison:
- Metrics:
- Result:
- Interpretation:
- Decision: `Adopt` / `Reject` / `Hold`
- Logs:
- Issue comment:

## Experiment Records

### Experiment ID: `E46-SCORE-001`

- Date: 2026-02-23
- Branch: `task/issue46-fn-det-preproc`
- Scope: score-side candidate bbox preprocessing (`score_candidates_batch.py`)
- Hypothesis:
  - double/end bar 系の wide bbox を split / recenter / merged 表現にすると、`FN_det` の一部を `FN_cnn` または TP に改善できる
- Change:
  - optional preprocessing added (default OFF):
    - `split_wide_candidates`
    - `recenter_wide_single_peak`
    - `emit_merged_two_peak_box`
  - experiment configs added under `configs/cnn_barline_runs/issue44_baseline_v1/`
- Target data:
  - `logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12`
- Baseline for comparison:
  - issue44 baseline scoring + `evaluate_global` (`threshold=0.1`, `0.5`)
- Metrics:
  - `TP/FP/FN`, `FN_det`, `FN_cnn`
- Result:
  - baseline 比 `FN_det: 15 -> 14`（1件改善）
  - 追加の `recenter` / `merged` は改善増分なし
  - global metrics (`th=0.1`) は `TP=3561, FP=2, FN=23` で据え置き
- Interpretation:
  - 方向性（複合バーの表現差対応）は妥当
  - ただし score-side のみでは改善幅が小さい
- Decision: `Hold`（baselineを壊さない optional path として保持、主戦場は upstream へ）
- Logs:
  - `logs/cnn_barline_classification/issue44_baseline_v1/eval2_global_summary_th0p1_splitwide_v1.csv`
  - `logs/cnn_barline_classification/issue44_baseline_v1/eval2_global_summary_th0p1_splitwide_recenter_v1.csv`
  - `logs/cnn_barline_classification/issue44_baseline_v1/eval2_global_summary_th0p1_splitwide_recenter_merge_v1.csv`
- Issue comment:
  - `https://github.com/M763468/PDFScoreBar/issues/46#issuecomment-3944406903`

### Experiment ID: `E46-PROBE-001`

- Date: 2026-02-23
- Branch: `task/issue46-fn-det-preproc`
- Scope: upstream probe scan scale-aware parameter sweep (`min_peak_distance`, `x_merge_tol`)
- Hypothesis:
  - close double-bar peaks が固定 `min_peak_distance` / `x_merge_tol` によって潰れており、`unit_size` ベースの scale-aware 指定で回収できる
- Change:
  - `src/pipeline/probe_scan.py`:
    - `min_peak_distance_unit_ratio`
    - `x_merge_tol_unit_ratio`
    - existing box 高さから `unit_size ~= median(h)/4` を推定して concrete px に変換
  - `src/pipeline/detection.py`: pass-through keys 追加
- Target data:
  - `FN_det=15` の 10ページ
  - `logs/hybrid_pipeline_bench/eval2_<score>_<page>_*/hybrid_predictions.json`
- Baseline for comparison:
  - probe scan default params (`ink=230`, `min_ratio=0.70`, `vertical_closing=0`)
- Metrics:
  - per-GT best IoU (`IoU>=0.5` hit count)
- Result:
  - hit count: `6/15` のまま（改善 0 / 退行 0）
  - `x_merge_tol` ratio 指定で `Sibelius page_004` の 1本は IoU 改善（`0.2485 -> 0.3927`）だが未達
- Interpretation:
  - `min_peak_distance` 単独より merge 条件の方が効くケースはある
  - しかし `IoU>=0.5` を超えるには bbox 表現の正規化が別途必要
- Decision: `Hold`（config knob は再利用価値あり、単独採用はしない）
- Logs:
  - `logs/issue46_probe_scan_sweeps/fn_det15_probe_scan_ratio_sweep_v1/summary.json`
  - `logs/issue46_probe_scan_sweeps/fn_det15_probe_scan_ratio_sweep_v1/summary.csv`
  - `logs/issue46_probe_scan_sweeps/fn_det15_probe_scan_ratio_sweep_v1/per_gt.csv`
- Issue comment:
  - `https://github.com/M763468/PDFScoreBar/issues/46#issuecomment-3944453706`

### Experiment ID: `E46-PROBE-002`

- Date: 2026-02-23
- Branch: `task/issue46-fn-det-preproc`
- Scope: upstream probe scan threshold sweep (`ink_threshold`, `min_ratio`, `vertical_closing`)
- Hypothesis:
  - 候補の完全欠落に寄っているケースは、probe 条件緩和で `IoU>=0.5` に入る候補が増える
- Change:
  - code change なし（`run_probe_scan_batch()` の既存引数 sweep）
- Target data:
  - `FN_det=15` の 10ページ
- Baseline for comparison:
  - probe scan default params (`ink=230`, `min_ratio=0.70`, `vertical_closing=0`)
- Metrics:
  - per-GT best IoU (`IoU>=0.5` hit count), avg candidates/page
- Result:
  - hit count 改善なし（best でも `6/15`）
  - `mean best IoU` は改善（例: `0.3999 -> 0.4699`）
  - 強く緩めると退行あり（`ink240_mr0p55_vc2`: `5/15`）
- Interpretation:
  - 候補生成しきい値の緩和だけでは主問題を解けない
  - 候補 bbox の形状/位置ズレ（表現問題）の寄与が大きい
- Decision: `Reject`（本件の主対策としては不適）
- Logs:
  - `logs/issue46_probe_scan_sweeps/fn_det15_probe_scan_threshold_sweep_v1/summary.json`
  - `logs/issue46_probe_scan_sweeps/fn_det15_probe_scan_threshold_sweep_v1/summary.csv`
  - `logs/issue46_probe_scan_sweeps/fn_det15_probe_scan_threshold_sweep_v1/per_gt.csv`
- Issue comment:
  - `https://github.com/M763468/PDFScoreBar/issues/46#issuecomment-3944453706`

## Next Planned Experiment

### Experiment ID: `E46-PROBE-003`

- Date: 2026-02-23
- Branch: `task/issue46-fn-det-preproc`
- Scope: probe output candidate bbox normalization (unit-size based, additive postprocess)
- Hypothesis:
  - double/end/repeat の複合バー、および縦方向過伸長 bbox を `unit_size` ベースの標準形に寄せた候補を追加すると、`IoU>=0.5` に入る GT が増える
- Change:
  - `src/pipeline/probe_scan.py`
    - optional pseudo-kwargs (default OFF) を追加:
      - `post_emit_unit_normalized_box`
      - `post_norm_width_unit_ratio`
      - `post_norm_height_unit_ratio`
      - `post_apply_if_width_gt_unit_ratio`
      - `post_apply_if_height_gt_unit_ratio`
      - `post_vertical_min_height_unit_ratio`
      - `post_vertical_min_aspect_ratio`
    - `run_probe_scan_batch()` 出力直前に、縦長候補へ additive な normalized bbox を追加
  - `src/pipeline/detection.py`
    - 上記 pseudo-kwargs を `_PROBE_SCAN_KWARG_KEYS` に追加（config 経由で実験可能）
- Target data:
  - `FN_det=15` の 10ページ（`eval2_fn_det_candidates_th0p5.csv` 起点）
- Baseline for comparison:
  - probe scan default params + postprocess OFF
- Metrics:
  - per-GT best IoU (`IoU>=0.5` hit count), avg candidates/page
- Result:
  - baseline: `6/15`
  - `bboxnorm_w1p0_h4p0`: `6/15`（改善なし）
  - `bboxnorm_w0p8_h4p0`: `7/15`（+1, 退行0）
  - `bboxnorm_w0p8_h4p0_loose`: `7/15`（+1, 候補数増のみ）
  - 改善ケース:
    - `Va_Prokofiev_Symphony1/page_006` GT `[3199,4102,3210,4207]`
    - best IoU `0.453 -> 0.540`（`bboxnorm_w0p8_h4p0`）
- Interpretation:
  - 「bbox表現ズレ」が主因という仮説を支持
  - 幅を `0.8 * unit_size` に寄せる正規化が有効（少なくとも 1件は `IoU>=0.5` を超えた）
  - loose 条件は候補増に対して改善増分がなく、過剰
- Decision: `Hold`（有望。次は full eval に接続して `FN_det` / global 指標への寄与を確認）
- Logs:
  - `logs/issue46_probe_scan_sweeps/fn_det15_probe_scan_bboxnorm_sweep_v1/summary.json`
  - `logs/issue46_probe_scan_sweeps/fn_det15_probe_scan_bboxnorm_sweep_v1/summary.csv`
- Issue comment:
  - (to be added)

## Next Planned Experiment

### Experiment ID: `E46-PROBE-004`

- Date: 2026-02-23
- Branch: `task/issue46-fn-det-preproc`
- Scope: `E46-PROBE-003` の有望条件を issue44 eval2 再評価に接続（10ページ差し替え）
- Hypothesis:
  - `FN_det` 対象 10ページだけ probe candidates を bbox 正規化版で差し替えれば、global `FN_det` が改善する
- Change:
  - baseline scoring dir を複製:
    - `logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12`
    - → `.../scoring_input_eval2_v12_probe_bboxnorm_w0p8_h4p0_patch10`
  - `FN_det=15` に含まれる 10ページだけ、`run_probe_scan_batch()` + `bboxnorm_w0p8_h4p0` で candidates 再生成し差し替え
  - 差し替えページのみ `scored/filtered` を削除して CNN 再スコア
- Target data:
  - issue44 eval2 scoring dir（10ページ差し替え）
- Baseline for comparison:
  - issue44 baseline eval CSV (`threshold=0.1`, `0.5`)
- Metrics:
  - per-page / global `TP/FP/FN`, `FN_cnn`, `FN_det`
- Result:
  - **global は大幅悪化**（`th=0.1`, `0.5` ともに）
  - 例 (`th=0.1`): patched 10ページ aggregate で
    - `TP: 632 -> 614` (`-18`)
    - `FP: 2 -> 63` (`+61`)
    - `FN_total: 18 -> 36` (`+18`)
    - `FN_det: 15 -> 31` (`+16`)
- Interpretation:
  - この比較は `bbox 正規化の効果` だけでなく、**候補ソースそのものの差し替え**（`issue36_prep` 候補 → `hybrid_pipeline_bench + probe_scan` 再生成候補）を同時に含むため、因果評価として不適切
  - `E46-PROBE-003` の局所改善（FN_det subset で +1）を否定する結果ではない
  - 比較設計を修正する必要あり（同一候補ソース上で bbox 正規化のみを加える）
- Decision: `Reject (Confounded)`（比較設計の不備。再設計してやり直す）
- Logs:
  - `logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12_probe_bboxnorm_w0p8_h4p0_patch10/`
  - `logs/cnn_barline_classification/issue44_baseline_v1/eval2_global_summary_th0p1_probe_bboxnorm_w0p8_h4p0_patch10.csv`
  - `logs/cnn_barline_classification/issue44_baseline_v1/eval2_global_summary_th0p5_probe_bboxnorm_w0p8_h4p0_patch10.csv`
- Issue comment:
  - (to be added)

## Next Planned Experiment

### Experiment ID: `E46-PROBE-005`

- Date: 2026-02-23
- Branch: `task/issue46-fn-det-preproc`
- Scope: 同一候補ソース（`issue36_prep`）上で bbox 正規化のみを additive 適用して比較
- Hypothesis:
  - 候補ソース差を固定すれば、`E46-PROBE-003` の改善（少なくとも 1件）を global 指標へ安全に伝播できる
- Change:
  - baseline scoring dir を複製:
    - `logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12`
    - → `.../scoring_input_eval2_v12_same_source_bboxnorm_w0p8_h4p0_patch10`
  - `FN_det=15` 対象 10ページの `pipeline2_no_peak_candidates.json` に対して、
    - `unit_size` を候補bbox高さ中央値から推定
    - `bboxnorm_w0p8_h4p0` 相当の normalized bbox を additive 追加
  - 差し替えページのみ CNN 再スコア→global 再評価
- Target data:
  - issue44 baseline scoring dir（同一候補ソース、10ページ差分）
- Baseline for comparison:
  - issue44 baseline eval CSV (`threshold=0.1`, `0.5`)
- Metrics:
  - issue44 eval2 `GLOBAL TOTAL` (`TP/FP/FN`, `FN_det`, `FN_cnn`)
  - patched 10ページの page-level diff
- Result:
  - `th=0.1`: global `TP/FP/FN` は不変
    - `FN_det: 15 -> 14`
    - `FN_cnn: 8 -> 9`
  - `th=0.5`: global `TP/FP/FN` は不変
    - `FN_det: 15 -> 14`
    - `FN_cnn: 27 -> 28`
  - 変化したページは `Va_Prokofiev_Symphony1/page_006` のみ
    - `FN_det -> FN_cnn` に1件シフト（TP/FP/FN_total は不変）
- Interpretation:
  - bbox 正規化で detector miss を 1件救えることは再確認できた
  - ただし現行CNN閾値/スコアでは、その候補が最終的に採択されず `FN_cnn` に移るため net 改善は 0
  - `E46-SCORE-001`（score-side preprocessing）と同じパターンで整合的
- Decision: `Hold`（局所改善は確認済み。次は CNN スコアリング側との組み合わせ最適化が必要）
- Logs:
  - `logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12_same_source_bboxnorm_w0p8_h4p0_patch10/`
  - `logs/cnn_barline_classification/issue44_baseline_v1/eval2_global_summary_th0p1_same_source_bboxnorm_w0p8_h4p0_patch10.csv`
  - `logs/cnn_barline_classification/issue44_baseline_v1/eval2_global_summary_th0p5_same_source_bboxnorm_w0p8_h4p0_patch10.csv`
- Issue comment:
  - (to be added)

## Next Planned Experiment

### Experiment ID: `E46-COMB-001`

- Date: 2026-02-23
- Branch: `task/issue46-fn-det-preproc`
- Scope: probe bbox 正規化（`E46-PROBE-005`） + threshold sweep の組み合わせ検証
- Hypothesis:
  - detector miss を救った候補が `FN_cnn` に落ちるなら、threshold を下げた帯域で net 改善が現れる
- Change:
  - 比較対象:
    - `baseline`: `scoring_input_eval2_v12`
    - `probe_bboxnorm_patch10`: `scoring_input_eval2_v12_same_source_bboxnorm_w0p8_h4p0_patch10`
  - `re_evaluate_global.py` を threshold sweep:
    - `0.1, 0.05, 0.02, 0.01, 0.005, 0.003`
- Target data:
  - issue44 eval2 全68ページ（比較対象2系統）
- Baseline for comparison:
  - 同一 threshold における `baseline` root
- Metrics:
  - global `TP/FP/FN`, `FN_cnn`, `FN_det`
  - `Va_Prokofiev_Symphony1/page_006` page-level diff
- Result:
  - `th=0.1 .. 0.01`: global `TP/FP/FN` は不変（`FN_det -1`, `FN_cnn +1` のみ）
  - `th=0.005` / `0.003` で初めて net 改善:
    - global delta: `TP +1`, `FP +1`, `FN_total -1`, `FN_det -1`
    - `page_006` が `TP 103 -> 104`, `FN_total 1 -> 0`
  - ただし absolute metrics では低閾値化に伴う FP 増が大きい
    - baseline `th=0.1`: `FP=2`
    - baseline `th=0.005`: `FP=126`
- Interpretation:
  - probe bbox 正規化で救った候補は実際に有効で、threshold を十分下げれば TP 化できる
  - しかし現行CNN score scaleでは対象候補スコアが低すぎ（例: `~0.0052`）、実用閾値 `0.1` では採択されない
  - 問題は detector 側だけでなく、CNN がこの bbox/crop を正例として強くスコアできない点にもある
- Decision: `Hold`（メカニズム確認として有益。実用改善には CNN側 or score-side表現改善が必要）
- Logs:
  - `logs/issue46_combo_sweeps/E46-COMB-001_threshold_sweep_v1/summary.json`
  - `logs/issue46_combo_sweeps/E46-COMB-001_threshold_sweep_v1/summary.csv`
  - `logs/issue46_combo_sweeps/E46-COMB-001_threshold_sweep_v1/deltas_baseline_to_probe_bboxnorm_patch10.csv`
- Issue comment:
  - (to be added)

## Next Planned Experiment

### Experiment ID: `E46-COMB-002`

- Date: 2026-02-23
- Branch: `task/issue46-fn-det-preproc`
- Scope: `page_006` 型 hard case 向けの score-side crop 表現改善（bbox内インク重心で crop X を再中心化）
- Hypothesis:
  - CNN に渡す crop の X 中心を `bbox中心` ではなく `bbox内インク重心` に寄せると、正例 barline が bbox 端にあるケースの低スコアを改善できる
- Change:
  - `tools/cnn_classifier/score_candidates_batch.py`
    - optional score-side crop recentering (default OFF):
      - `crop_recenter_on_bbox_ink`
      - `crop_recenter_min_aspect_ratio`
      - `crop_recenter_apply_if_width_le_unit_ratio`
      - `crop_recenter_mask_ratio`
      - `crop_recenter_max_shift_unit_ratio`
    - narrow/tall candidate の bbox ローカル x-profile から高濃度列の重心を推定し、crop X中心を微調整
  - reproducible config:
    - `configs/cnn_barline_runs/issue44_baseline_v1/score_candidates_batch_croprecenter_v1.yaml`
- Target data:
  - `probe_bboxnorm_patch10` root:
    - `logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12_same_source_bboxnorm_w0p8_h4p0_patch10`
  - copied + rescored root:
    - `..._croprecenter_v1`
- Baseline for comparison:
  - issue44 baseline (`scoring_input_eval2_v12`)
  - `E46-PROBE-005` result root (`probe_bboxnorm_patch10`)
- Metrics:
  - target candidate score (`Va_Prokofiev_Symphony1/page_006`, bbox `[3190,4101,3210,4208]`)
  - global `TP/FP/FN`, `FN_cnn`, `FN_det` at `th=0.1`, `0.5`
- Result:
  - target candidate score:
    - before: `0.00523`
    - after crop recenter: `0.28713` （`th=0.1` 超え）
  - global vs issue44 baseline:
    - `th=0.1`: `TP +3`, `FP +2`, `FN_total -3`, `FN_cnn -2`, `FN_det -1`
      - `3561/2/23` → `3564/4/20`
    - `th=0.5`: `TP +13`, `FP +0`, `FN_total -13`, `FN_cnn -12`, `FN_det -1`
      - `3542/1/42` → `3555/1/29`
  - global vs `E46-PROBE-005` (`probe_bboxnorm_patch10`):
    - `th=0.1`: `TP +3`, `FP +2`, `FN_total -3`, `FN_cnn -3`, `FN_det ±0`
    - `th=0.5`: `TP +13`, `FP +0`, `FN_total -13`, `FN_cnn -13`, `FN_det ±0`
- Interpretation:
  - score-side crop 表現は強く効く（少なくとも本件の主要ボトルネックの一つ）
  - `FN_det` を救った候補が `FN_cnn` に落ちる問題に対して、threshold 低下なしで有効
  - とくに `th=0.5` で `FP増なし` の改善が大きい
  - `th=0.1` では `FP +2` の副作用があるため、導入時はページ別/score別の FP 内訳確認が必要
- Decision: `Hold (Promising)`（有望。次は FP +2 の原因分析と、baseline root 単独適用の比較）
- Logs:
  - `logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12_same_source_bboxnorm_w0p8_h4p0_patch10_croprecenter_v1/`
  - `logs/cnn_barline_classification/issue44_baseline_v1/eval2_global_summary_th0p1_same_source_bboxnorm_patch10_croprecenter_v1.csv`
  - `logs/cnn_barline_classification/issue44_baseline_v1/eval2_global_summary_th0p5_same_source_bboxnorm_patch10_croprecenter_v1.csv`
  - `logs/issue46_combo_sweeps/E46-COMB-001_threshold_sweep_v1/*`（threshold sweep 比較）
- Issue comment:
  - (to be added)

## Next Planned Experiment

### Experiment ID: `E46-COMB-003`

- Date: 2026-02-23
- Branch: `task/issue46-fn-det-preproc`
- Scope: crop recenter の FP +2 原因分析と適用条件の絞り込み（極細候補を除外）
- Hypothesis:
  - `crop_recenter_on_bbox_ink` の副作用 FP は極細候補（非barline系の縦線）で起きており、適用下限幅を導入すれば `th=0.1` の FP増を抑えつつ改善を維持できる
- Change:
  - `tools/cnn_classifier/score_candidates_batch.py`
    - `crop_recenter_apply_if_width_ge_unit_ratio` を追加（default `0.0`）
  - tuned config:
    - `configs/cnn_barline_runs/issue44_baseline_v1/score_candidates_batch_croprecenter_v2_ge0p5.yaml`
    - `crop_recenter_apply_if_width_ge_unit_ratio: 0.5`
- Root cause analysis (`E46-COMB-002` v1):
  - `th=0.1` の `FP +2` は `Va__Prokofiev_Symphony5/page_003` に集中
  - 同一偽線まわりの極細候補（幅 `7px`）2件が score 上昇
  - TP 改善の対象候補 (`Va_Prokofiev_Symphony1/page_006`) は幅 `20px`
- Target data:
  - `probe_bboxnorm_patch10` root をコピーした `...croprecenter_v2_ge0p5`
- Baseline for comparison:
  - issue44 baseline
  - `E46-COMB-002` v1 (`...croprecenter_v1`)
- Metrics:
  - global `TP/FP/FN`, `FN_cnn`, `FN_det` at `th=0.1`, `0.5`
  - page-level diff (`th=0.1`)
- Result:
  - vs issue44 baseline:
    - `th=0.1`: `TP +2`, `FP +0`, `FN_total -2`, `FN_cnn -1`, `FN_det -1`
      - `3561/2/23` → `3563/2/21`
    - `th=0.5`: `TP +3`, `FP +0`, `FN_total -3`, `FN_cnn -2`, `FN_det -1`
      - `3542/1/42` → `3545/1/39`
  - vs `E46-COMB-002` v1:
    - `th=0.1`: `TP -1`, `FP -2`, `FN_total +1`
    - `th=0.5`: `TP -10`, `FP ±0`, `FN_total +10`
  - `th=0.1` page-level改善（baseline比）は2ページのみ:
    - `Sibelius-Violin_Concerto-Viola/page_009`: `TP +1`, `FN_cnn -1`
    - `Va_Prokofiev_Symphony1/page_006`: `TP +1`, `FN_det -1`
- Interpretation:
  - 極細候補除外で `FP +2` は解消できる
  - ただし保守的にしすぎると `th=0.5` の大幅改善をかなり失う（v1 の gains を削る）
  - 適用下限幅は `0.5u` 固定より、score threshold / scoreごとの運用に応じたチューニング余地あり
- Decision: `Hold (Practical at th=0.1)`（issue44 の実用閾値 `0.1` 基準では有望）
- Logs:
  - `logs/cnn_barline_classification/issue44_baseline_v1/eval2_global_summary_th0p1_same_source_bboxnorm_patch10_croprecenter_v2_ge0p5.csv`
  - `logs/cnn_barline_classification/issue44_baseline_v1/eval2_global_summary_th0p5_same_source_bboxnorm_patch10_croprecenter_v2_ge0p5.csv`
- Issue comment:
  - (to be added)

## Next Planned Experiment

### Experiment ID: `E46-COMB-004`

- Date: 2026-02-23
- Branch: `task/issue46-fn-det-preproc`
- Scope: `crop_recenter_apply_if_width_ge_unit_ratio` sweep（`0.25, 0.4, 0.5`） + 再スコア時間改善（評価内容不変）
- Hypothesis:
  - `0.5u` は保守的すぎる可能性があり、中間値で `th=0.1` の FP増を抑えつつ `th=0.5` の改善量を増やせる
- Runtime fix (evaluation content unchanged):
  - CUDA availability を確認して GPU 実行を利用（`.venv_cnn_classifier` で `torch.cuda.is_available()==True`）
  - さらに、variant ごとに **影響ページのみ再スコア**:
    - `probe_bboxnorm_patch10` root をコピー
    - 各ページの candidates に対し `crop_recenter` 条件を dry 判定
    - 影響ページだけ `scored/filtered` を削除して `score_candidates_batch.py` 実行
    - 未影響ページは元の scored 結果を再利用（評価内容は同一）
- Change:
  - code change なし（運用/実行方法のみ）
  - 比較対象:
    - `E46-COMB-002` v1 (`ge=0.0`)
    - `E46-COMB-003` tuned (`ge=0.5`)
    - `E46-COMB-004` sweep (`ge=0.25`, `ge=0.4`)
- Metrics:
  - global delta vs baseline at `th=0.1`, `0.5`
  - `FP` 再発有無
  - impacted page count / rescore seconds
- Result:
  - Runtime:
    - full rescore (68 pages, GPU, `ge=0.5`) 実測: `~41.6s`
    - selective rescore:
      - `ge=0.25`: impacted `68` pages, `~38.8s`
      - `ge=0.4`: impacted `65` pages, `~36.7s`
    - 改善は限定的（影響ページが多いため）が、再利用方式は評価内容を変えずに適用可能
  - Global metrics (vs issue44 baseline):
    - `ge=0.25`
      - `th=0.1`: `TP +3`, `FP +1`, `FN_total -3`, `FN_cnn -2`, `FN_det -1`
      - `th=0.5`: `TP +13`, `FP +0`, `FN_total -13`, `FN_cnn -12`, `FN_det -1`（`E46-COMB-002` v1 と同等）
    - `ge=0.4`
      - `th=0.1`: `TP +2`, `FP +0`, `FN_total -2`, `FN_cnn -1`, `FN_det -1`（`E46-COMB-003` と同等）
      - `th=0.5`: `TP +5`, `FP +0`, `FN_total -5`, `FN_cnn -4`, `FN_det -1`（`ge=0.5` より改善量が大きい）
  - `ge=0.5`（参考, E46-COMB-003）:
    - `th=0.1`: `TP +2`, `FP +0`, `FN_total -2`
    - `th=0.5`: `TP +3`, `FP +0`, `FN_total -3`
- Interpretation:
  - 実用閾値 `th=0.1` を重視するなら:
    - `ge=0.4` / `0.5` は `FP増なし`
    - `ge=0.25` は `FP +1` と引き換えに `TP +3`
  - `th=0.5` も見るなら、`ge=0.4` が `0.5u` より良いトレードオフ
  - 現時点の妥協点は **`ge=0.4`** が有力
- Decision: `Hold (Promising, ge=0.4 preferred)` 
- Logs:
  - `logs/issue46_combo_sweeps/E46-COMB-004_widthge_sweep_v1/summary.json`
  - `logs/issue46_combo_sweeps/E46-COMB-004_widthge_sweep_v1/eval2_global_summary_ge0p25_th0p1.csv`
  - `logs/issue46_combo_sweeps/E46-COMB-004_widthge_sweep_v1/eval2_global_summary_ge0p25_th0p5.csv`
  - `logs/issue46_combo_sweeps/E46-COMB-004_widthge_sweep_v1/eval2_global_summary_ge0p4_th0p1.csv`
  - `logs/issue46_combo_sweeps/E46-COMB-004_widthge_sweep_v1/eval2_global_summary_ge0p4_th0p5.csv`
- Issue comment:
  - (to be added)

## Next Planned Experiment

### Experiment ID: `E46-COMB-005`

- Date: 2026-02-23
- Branch: `task/issue46-fn-det-preproc`
- Scope: 独立寄与比較（2x2）: `probe bboxnorm` と `crop recenter (ge=0.4)` の単独/併用
- Hypothesis:
  - `probe bboxnorm` と `crop recenter` は異なる失敗モードに効いており、単独寄与を分解して評価できる
- Change:
  - `crop recenter only (ge=0.4)` root を baseline から作成:
    - `logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12_croprecenter_v3_ge0p4`
  - `E46-COMB-004` の `both (probe+bboxnorm + crop recenter ge=0.4)` と合わせて 2x2 比較
  - selective rescore（影響ページのみ再スコア、未影響ページは scored 再利用）を適用
- Comparison matrix (2x2):
  - none: `baseline`
  - probe only: `E46-PROBE-005` root
  - crop only: `crop recenter only (ge=0.4)`
  - both: `E46-COMB-004 ge=0.4`
- Metrics:
  - global `TP/FP/FN`, `FN_cnn`, `FN_det` at `th=0.1`, `0.5`
  - baseline 比差分
  - additive 期待に対する interaction（簡易）
- Result (vs baseline):
  - `th=0.1`
    - probe only: `TP +0`, `FP +0`, `FN_total +0`, `FN_cnn +1`, `FN_det -1`
    - crop only (`ge=0.4`): `TP +1`, `FP +0`, `FN_total -1`, `FN_cnn -1`, `FN_det +0`
    - both: `TP +2`, `FP +0`, `FN_total -2`, `FN_cnn -1`, `FN_det -1`
    - interaction (both - probe - crop + baseline): `TP +1`, `FN_total -1`
  - `th=0.5`
    - probe only: `TP +0`, `FP +0`, `FN_total +0`, `FN_cnn +1`, `FN_det -1`
    - crop only (`ge=0.4`): `TP +4`, `FP +0`, `FN_total -4`, `FN_cnn -4`, `FN_det +0`
    - both: `TP +5`, `FP +0`, `FN_total -5`, `FN_cnn -4`, `FN_det -1`
    - interaction: `TP +1`, `FN_total -1`
- Interpretation:
  - `probe bboxnorm` は主に `FN_det` を触るが、単独では net 改善にならない（`FN_cnn` へシフト）
  - `crop recenter (ge=0.4)` は単独でも net 改善を出す（主に `FN_cnn` 削減）
  - 併用すると、各単独の効果に加えて小さな相乗効果（+1 TP）がある
- Decision: `Adopt candidate (for experimental branch)`（`ge=0.4` を現時点の第一候補として継続検証）
- Logs:
  - `logs/issue46_combo_sweeps/E46-COMB-005_independent_contrib_v1/independent_contrib_2x2_summary.json`
  - `logs/issue46_combo_sweeps/E46-COMB-005_independent_contrib_v1/eval2_global_summary_crop_only_ge0p4_th0p1.csv`
  - `logs/issue46_combo_sweeps/E46-COMB-005_independent_contrib_v1/eval2_global_summary_crop_only_ge0p4_th0p5.csv`
- Issue comment:
  - (to be added)
