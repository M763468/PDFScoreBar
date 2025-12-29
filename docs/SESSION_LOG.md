# 記述例
---
## 2025-12-29 End barline recovery (prototype)
**作業目的 / 方針 / 位置づけ**
- 残り10件のFNのうち、end barline を最初の対象として回復するための後処理を追加。
- 検出器本体は変えず、homr evaluator の post-processing として「右端候補 x + 縦線検出 + 右側stem排除」を試行。
**作業時間**
- 2025-12-29 00:30:57 JST - 2025-12-29 00:57:01 JST
**変更したファイル（概要のみ）**
- `src/homr_eval_scripts/homr_evaluator.py`（end barline recovery の追加、overlay に END_RECOVERED ラベル付与）
**試した結果（出力ディレクトリのみ）**
- 省略
---
# 実際の作業記録
## 2025-12-30 var88確認と残存FPの目視レビュー
**作業目的 / 方針 / 位置づけ**
- var88の実装・パラメータ・出力を確認し、残存FPの傾向を把握。
- homr/omr-dlnの中間マスク活用の可能性を前提に、FP原因を画像ベースで整理。
**作業時間**
- 2025-12-30 01:04:42 JST
**確認した内容**
- var88結果: `logs/gt_rebuild_hybrid_eval/20251230T_hybrid_row_notehead_endbar/var88_clef_filter/summary_table.md`
  - page_001: TP=78 FP=12 FN=0
  - page_004: TP=112 FP=12 FN=0
  - page_10: TP=154 FP=4 FN=0
  - page_15: TP=112 FP=11 FN=0
- 実行スクリプト: `tools/run_gt_rebuild_hybrid_eval.py`
  - 入力: union preds + homr debug masks (notehead/clefs_keys/staff/barline) + omr-dln preds
  - row_filter → notehead endpoint overlap filter → endbar recovery → clefs_keys filter
  - notehead mask filter parameters（geom_debugより）:
    - open_kernel=5, min_area=20, dilate=7, max_aspect=2.0, min_height=10, max_width=6
- FP分類（barline_mask_ratio）:
  - `postfilter_analysis/summary.json` より、page_001/15はbarline_mask_ratio>=0.5のFPが多く、page_004/10は低いFPが中心
**FPの目視傾向（fp_crops）**
- clef/accidental/装飾記号や密集したstem列付近で、細い縦線がbarline扱いされる例が多い。
- staff線に近接する短い縦片（barline_mask_ratio=0.0のもの）と、barline_mask自体が強く反応している縦片が混在。
**次の検討タスク**
- homrの debug_5_stems_rest / debug_4_symbols / debug_17_notes など中間マスクとFPの重なりを確認。
- barline_mask_ratio と追加マスク（stems/rest/notes）の組み合わせでFPを除去できるか検討。
## 2025-12-30 FP重なり分析の対象整理（page3含む）
**作業目的 / 方針 / 位置づけ**
- 4ページ+page3に対して、FPと中間マスクの重なり分析を行うための入力を確定。
- 画像処理ベースで使えるマスク（stems/rest, symbols, notes, barline, notehead等）を優先。
**作業時間**
- 2025-12-30 01:17:13 JST
**確認内容（対象入力の確定）**
- var88対象ページ（page_001/004/10/15）のFP:
  - `logs/gt_rebuild_hybrid_eval/20251230T_hybrid_row_notehead_endbar/var88_clef_filter/per_page/<page_xx>/fp_boxes.json`
- 中間マスク（homr debug出力）:
  - `logs/homr_eval/20251229T_gt_rebuild_eval/page_xxx/page_xxx_debug_5_stems_rest.png`
  - `logs/homr_eval/20251229T_gt_rebuild_eval/page_xxx/page_xxx_debug_4_symbols.png`
  - `logs/homr_eval/20251229T_gt_rebuild_eval/page_xxx/page_xxx_debug_17_notes.png`
  - `logs/homr_eval/20251229T_gt_rebuild_eval/page_xxx/page_xxx_debug_8_bar_line_img.png`
  - `logs/homr_eval/20251229T_gt_rebuild_eval/page_xxx/page_xxx_debug_6_notehead.png`
- page3の候補入力:
  - FP候補: `logs/phase5b/b2_phase4_filter_check/20251221T132439/overlays/page_3_union_phase4_fp_boxes.json`
  - マスク: `logs/homr_eval_baseline/baseline_verification/page_3/page_3_debug_*`
**次の検討タスク**
- 上記入力を用いて、FPごとのマスク重なり率（stems/rest, symbols, notes, barline, notehead）を定量化。
## 2025-12-30 FP×中間マスク重なり分析（リサイズ前提）
**作業目的 / 方針 / 位置づけ**
- var88のFP/TPに対して、homr中間マスクの重なり率を数値化し、除去ルール設計の当たりを付ける。
- マスクは `load_mask` と同様に元画像サイズへリサイズして比較。
**作業時間**
- 2025-12-30 01:28:01 JST
**実施内容（手法の作用機序）**
- FP/TPボックスに対し、各マスク内の「非ゼロ画素率」を計算（box内平均）。
- ルール案の検討に向け、barline/stems_rest/clefs_keys/notehead の重なり分布を比較。
**主な結果（要点）**
- barline mask: TPは高比率が多い一方で、FPも中〜高比率が混在（page_001/15で顕著）。
- stems_rest: TP/FPとも重なりが高めのため、単独では弁別に不向き。
- clefs_keys: page_004でFP重なりが高く、限定的に効く可能性。
- notehead: FPの重なりは低く、既存endpoint衝突に追加しても効果は限定的。
- debug_17_notes / debug_4_symbols は「可視化オーバーレイ」で実マスクではない可能性が高く、今回は使用しない。
**安全側のルール仮説（TPを落とさない閾値の検討）**
- 4ページ（001/004/10/15）で、`barline_ratio < 0.02 AND clefs_keys_ratio < 0.02` の条件は **TPヒット 0**。
  - FP除去数: page_001=5, page_004=4, page_10=4, page_15=1。
- page3（FPのみ）では同条件で 17/26 を除去。TP側の検証は未実施（TPボックス未取得のため）。
**補足**
- candidate_stats.csv の特徴量（min_dist_to_notehead など）は、var88のFP/TPボックスと一致せず、現状の検証には使えない。
**次の検討タスク**
- page3のTPボックス（またはGT）を確保し、同条件でFNが出ないことを確認。
- 上記条件を起点に、閾値の微調整または追加条件（barline_ratio低+clefs_keys低）を再評価。
## 2025-12-30 候補ルールの整理と安全性確認
**作業目的 / 方針 / 位置づけ**
- FN=0を崩さない条件でFPを落とせるルールを抽出。
- 既存マスク（barline / clefs_keys）を使った軽量ルールを最優先で検討。
**作業時間**
- 2025-12-30 01:31:44 JST
**候補ルール（作用機序）**
- ルール案: `barline_ratio < 0.02 AND clefs_keys_ratio < 0.02`
  - barlineマスクに反応が弱く、かつclefs_keys領域にも該当しない縦片をFPとして除去する狙い。
**安全性チェック（4ページ）**
- page_001/004/10/15では上記条件で **TPヒット0** を確認。
- FP削減効果: page_001=5, page_004=4, page_10=4, page_15=1。
**未確認点**
- page3はTPボックス（またはGT）が未取得のため、FN影響の検証が未完了。
## 2025-12-30 page3 GTを使った安全性確認
**作業目的 / 方針 / 位置づけ**
- docs/ENVIRONMENTS.md の記載に従い、page3のGTを使用して候補ルールのFN影響を確認。
- 既存の barline matcher（`greedy_barline_match`）で正確性を担保。
**作業時間**
- 2025-12-30 02:06:43 JST
**参照したドキュメント**
- `docs/ENVIRONMENTS.md`（`data/evaluation/annotations/page_003/boxes_sorted.json` の記載）
**検証内容（作用機序）**
- page3 preds: `logs/phase5b_confirmed_union_eval/page_3_hybrid_preds.json`
- GT: `data/evaluation/annotations/page_003/boxes_sorted.json`（barline_location）
- barline/clefs_keys マスクで `barline_ratio < 0.02 AND clefs_keys_ratio < 0.02` の候補を除外
- マッチングは `src/common/barline_evaluation.greedy_barline_match` を使用
**結果**
- base: TP=152 / FP=8 / FN=0
- filtered: TP=152 / FP=7 / FN=0
- 除去予測数: 3（FP減少は1）
**次の検討タスク**
- 上記ルールを `tools/run_gt_rebuild_hybrid_eval.py` に組み込み、5ページ一括評価で効果確認。
## 2025-12-30 低barline+低clefsフィルタの実装
**作業目的 / 方針 / 位置づけ**
- 候補ルールをコード化し、var88の評価パイプラインで再実行できるようにする。
- 作用機序をログとして残し、次回のスイープが容易になるようにする。
**作業時間**
- 2025-12-30 02:09:21 JST
**変更内容（作用機序）**
- `barline_ratio < barline_low_ratio` かつ `clefs_ratio < clefs_low_ratio` の候補をFPとして除外。
- 追加パラメータ: `--filter-barline-clefs-low`, `--barline-low-ratio`, `--clefs-low-ratio`。
- 出力: `barline_clefs_low_filter.json` に before/after と除外候補を記録。
**変更したファイル**
- `tools/run_gt_rebuild_hybrid_eval.py`
## 2025-12-30 var88出力に対するフィルタ効果の再評価

**作業目的 / 方針 / 位置づけ**
- 新フィルタの評価を、既存var88出力（geom_kept）に対して行い、FN影響を確実に判定。
- 既存の barline matcher を使い、4ページ+page3で評価。

**作業時間**
- 2025-12-30 02:12:43 JST

**検証内容（作用機序）**
- var88の予測: `logs/gt_rebuild_hybrid_eval/20251230T_hybrid_row_notehead_endbar/var88_clef_filter/per_page/<page>/geom_kept.json`
- GT: `logs/phase6_detector_miss/gt_rebuild/page_xxx_boxes_sorted.json`
- barline/clefs_keys マスクで `barline_ratio < 0.02 AND clefs_keys_ratio < 0.02` を除外。
- マッチングは `src/common.barline_evaluation.greedy_barline_match` を使用。

**結果（FN=0維持）**
- page_001: FP 12 → 7（除去=5, TP=78 維持）
- page_004: FP 12 → 8（除去=4, TP=112 維持）
- page_10: FP 4 → 0（除去=4, TP=154 維持）
- page_15: FP 11 → 10（除去=1, TP=112 維持）
- page_3: FP 8 → 7（除去=3, TP=152 維持, FN=0）

**補足**
- `tools/run_gt_rebuild_hybrid_eval.py` を直接再実行した際、union_rootの不一致でFNが増えたため、既存var88出力に対する評価へ切り替えた。

**結果のログ/可視化**
- まとめ: `logs/gt_rebuild_hybrid_eval/20251230T_var88_barline_clefs_low_geomkept/summary_table.md`
- overlays: `logs/gt_rebuild_hybrid_eval/20251230T_var88_barline_clefs_low_geomkept/overlays/`
  - `page_001_fp_only.png`, `page_004_fp_only.png`, `page_10_tp_fp_fn.png`, `page_15_fp_only.png`, `page_3_fp_only.png`
- FP crops: `logs/gt_rebuild_hybrid_eval/20251230T_var88_barline_clefs_low_geomkept/per_page/<page>/fp_crops/`
## 2025-12-30 残存FPの可視化確認
**作業目的 / 方針 / 位置づけ**
- 残っているFPを画像で確認し、次のフィルタ方針を検討。
**作業時間**
- 2025-12-30 02:27:31 JST
**観察メモ（暫定）**
- page_001/004/15のFP cropは、細い縦線が密に並ぶ記号周辺や、短い縦片がstaffに跨る形状が多い。
- page_3のFPは短い縦片（装飾や譜表端の縦成分）に見えるものが中心。

## 2025-12-30 union_root確認と可視化ログの整備

**作業目的 / 方針 / 位置づけ**
- union_rootの正規パスをドキュメントから特定し、再評価時の誤りを防ぐ。
- 今回の可視化ログの位置をSESSION_LOGに明記する。

**作業時間**
- 2025-12-30 02:30:55 JST

**確認したドキュメント**
- `docs/ENVIRONMENTS.md` / `docs/DEVELOPMENT_LOG.md`

**確認結果**
- confirmed unionの出力先は `logs/phase5b_confirmed_union_eval`（`tools/run_confirmed_union_eval.sh` の OUTPUT_DIR）。

**可視化ログ（今回の結果）**
- まとめ: `logs/gt_rebuild_hybrid_eval/20251230T_var88_barline_clefs_low_geomkept/summary_table.md`
- overlays: `logs/gt_rebuild_hybrid_eval/20251230T_var88_barline_clefs_low_geomkept/overlays/`
- FP crops: `logs/gt_rebuild_hybrid_eval/20251230T_var88_barline_clefs_low_geomkept/per_page/<page>/fp_crops/`

## 2025-12-30 追加指標の分離可能性チェック

**作業目的 / 方針 / 位置づけ**
- 残存FPに対し、簡易指標でTP/FPの分離が可能かを確認。

**作業時間**
- 2025-12-30 02:40:33 JST

**試した指標**
- 左右インク密度の非対称性（barline近傍の左右帯の差分）。
- barline maskの縦連続性（最大縦ラン）。
- barline/stems overlapの比率。

**結果**
- いずれもTP/FPの分離が弱く、単独の閾値ではFN=0維持が困難と判断。
