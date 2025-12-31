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

## 2025-12-30 コミット切替でのvar18/19/25再現試行

**作業目的 / 方針 / 位置づけ**
- 2025-12-29 のSESSION_LOG_temp.mdに記載されていたprobe_scan条件（var18/19/25）を、当時に近いコミットで再現する。

**作業時間**
- 2025-12-30 14:51:25 JST - 2025-12-30 14:52:44 JST

**検証内容（作用機序）**
- `git stash` で現行変更を退避し、`3d0bf23` に checkout（detached HEAD）。
- var18/19/25のprobe_scan条件を指定（median_box前提）。
  - var18: probe_width=3, min_peak_distance=3, max_per_band=6, band_height_min=12
  - var19: probe_width=3, min_ratio=0.8, min_peak_distance=2, max_per_band=12
  - var25: min_peak_distance=2, max_per_band=0
- 他はvar88相当設定（clefs_keys left + notehead aspect + endpoint設定）。

**結果（要点）**
- いずれもFNが残り、var88（FN=0）には未到達。
  - var18: page_001 FN=14 / page_004 FN=12 / page_10 FN=3 / page_15 FN=7
  - var19: page_001 FN=10 / page_004 FN=6 / page_10 FN=2 / page_15 FN=6
  - var25: page_001 FN=2 / page_004 FN=5 / page_10 FN=2 / page_15 FN=1

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251230T145125_repro_var18_commit3d0b/`
- `logs/gt_rebuild_hybrid_eval/20251230T145208_repro_var19_commit3d0b/`
- `logs/gt_rebuild_hybrid_eval/20251230T145244_repro_var25_commit3d0b/`

## 2025-12-30 page3過去条件の再現確認

**作業目的 / 方針 / 位置づけ**
- page3で過去にFP=FN=0を達成した処理順序・条件が現在も再現できるか確認。

**作業時間**
- 2025-12-30 03:08:12 JST

**実行コマンド（再現用）**
- `.venv_pdf/bin/python experiments/fp_reduction/analyze_staff_consistency.py --json logs/hybrid_results.json --image data/evaluation/images/page_3.png --gt data/evaluation/annotations/page_003/boxes_sorted.json --output logs/phase4_notehead_geom/20251230T_phase4_repro_check --no-use-ratio-tolerance --tol-top-px 5 --tol-bottom-px 5 --enable-geom-notehead-filter --geom-notehead-mode page3_known_fp --homr-context-dir logs/homr_eval_baseline/baseline_verification/page_3`

**結果**
- Original: TP=152 FP=8 FN=0
- Row filter: TP=152 FP=2 FN=0
- Geom note context: TP=152 FP=0 FN=0
- Final: TP=152 FP=0 FN=0

**出力ログ**
- `logs/phase4_notehead_geom/20251230T_phase4_repro_check/`

## 2025-12-30 案A: 近接候補の最小間隔ルール（全ページ検証）

**作業目的 / 方針 / 位置づけ**
- 近接候補のX間隔が極端に狭い場合に、短い方をFPとして落とすルールを試す。
- グローバル閾値で有効かどうかを5ページで検証。

**作業時間**
- 2025-12-30 03:35:40 JST

**検証内容（作用機序）**
- rowクラスタ（Y距離でクラスタ化）内の候補をX中心でソートし、隣接間隔が中央値の `thr` 倍未満なら短い方を除外。
- thr は 0.2 / 0.25 / 0.3 をスイープ。
- 使用preds:
  - page_001/004/10/15: `logs/gt_rebuild_hybrid_eval/20251230T_hybrid_row_notehead_endbar/var88_clef_filter/per_page/<page>/geom_kept.json`
  - page_3: `logs/phase5b_confirmed_union_eval/page_3_hybrid_preds.json`
- GT:
  - page_001/004/10/15: `logs/phase6_detector_miss/gt_rebuild/page_xxx_boxes_sorted.json`
  - page_3: `data/evaluation/annotations/page_003/boxes_sorted.json`

**実行コマンド（再現用）**
- `.venv_pdf/bin/python - <<'PY' ... (spacing rule sweep) ... PY`
  - 出力: `logs/phase4_notehead_geom/20251230T_spacing_rule_sweep/metrics.json`

**結果（要点）**
- page_004でFNが発生（thr=0.2でもFN=3）し、FN=0条件を満たせない。
- page_001でもthr>=0.25でFNが発生。
- page_3はFPが減らず、除去数のみ増加（多数候補が落ちる）。

**結果ログ**
- `logs/phase4_notehead_geom/20251230T_spacing_rule_sweep/metrics.json`

## 2025-12-30 案B: endpoint windowのY拡張スイープ（page3）

**作業目的 / 方針 / 位置づけ**
- 低音・高音のnoteheadとの衝突不足に対し、endpoint windowのY方向拡張が有効か再検証。
- endpoint_ratio_overlap方式でYスケールのみ変更。

**作業時間**
- 2025-12-30 03:47:05 JST

**検証内容（作用機序）**
- `analyze_staff_consistency.py` の `--geom-notehead-mode endpoint_ratio_overlap` を使用。
- `endpoint_x_radius_scale=0.6` 固定、`endpoint_y_radius_scale` を 0.6/0.8/1.0/1.2/1.5 でスイープ。
- page3のみ評価（GTあり）。

**実行コマンド（再現用）**
- `.venv_pdf/bin/python experiments/fp_reduction/analyze_staff_consistency.py --json logs/hybrid_results.json --image data/evaluation/images/page_3.png --gt data/evaluation/annotations/page_003/boxes_sorted.json --output logs/phase4_notehead_geom/20251230T_endpoint_ratio_y0.8 --no-use-ratio-tolerance --tol-top-px 5 --tol-bottom-px 5 --enable-geom-notehead-filter --geom-notehead-mode endpoint_ratio_overlap --geom-endpoint-ratio-threshold 0.1 --geom-endpoint-x-radius-scale 0.6 --geom-endpoint-y-radius-scale 0.8 --homr-context-dir logs/homr_eval_baseline/baseline_verification/page_3`
- 0.6/1.0/1.2/1.5 も同様に output を変更して実行。

**結果（要点）**
- y=0.6: TP=151 / FP=2 / FN=1（FN発生）
- y=0.8/1.0/1.2/1.5: TP=152 / FP=2 / FN=0（FN=0維持だがFPは残存）

**可視化ログ**
- `logs/phase4_notehead_geom/20251230T_endpoint_ratio_y0.8/geom_kept_removed_overlay.png`
- `logs/phase4_notehead_geom/20251230T_endpoint_ratio_y0.8/geom_note_context_overlay.png`

## 2025-12-30 残存FPのendpoint衝突+row band可視化（全ページ）

**作業目的 / 方針 / 位置づけ**
- 残存FPがrow bandから外れているか、notehead endpoint衝突があるかを可視化して原因を特定。
- page3は過去にFP=FN=0だったため、後段追加候補の挙動を確認する。

**作業時間**
- 2025-12-30 07:39:59 JST

**検証内容（作用機序）**
- eval_rootの `fp_boxes.json` を対象に、notehead maskとendpoint windowの衝突を描画。
- row bandは `filtered_preds.json` のYクラスタから推定（cluster_by_y_distance）。
- endpoint windowは暫定で page3既知の半径 (rx=5, ry=7) を使用。

**実行コマンド（再現用）**
- `.venv_pdf/bin/python tools/render_fp_notehead_overlays.py --eval-root logs/gt_rebuild_hybrid_eval/20251230T_var88_barline_clefs_low_geomkept --output-root logs/fp_notehead_overlay/20251230T073959_var88_barline_clefs_low --endpoint-rx 5 --endpoint-ry 7`

**出力ログ**
- まとめ: `logs/fp_notehead_overlay/20251230T073959_var88_barline_clefs_low/summary.json`
- 各ページoverlay: `logs/fp_notehead_overlay/20251230T073959_var88_barline_clefs_low/page_XXX_fp_notehead_overlay.png`
- endpoint window: `logs/fp_notehead_overlay/20251230T073959_var88_barline_clefs_low/page_XXX_fp_endpoint_windows.png`
- FP crops: `logs/fp_notehead_overlay/20251230T073959_var88_barline_clefs_low/per_page/page_XXX/fp_crops/`

## 2025-12-30 homr中間マスクの棚卸しとFP重なり集計

**作業目的 / 方針 / 位置づけ**
- homrのdebug出力にどのマスクが存在するかを整理し、FPとの重なり傾向を把握。
- omr-dln側に中間マスクがあるかも確認。

**作業時間**
- 2025-12-30 07:46:18 JST

**実施内容**
- homr evalディレクトリから `*_debug_*.png` を収集して一覧化。
- 残存FP（barline_clefs_low後）と各マスクの重なり比率を集計。
- omr-dlnの出力を確認（中間マスクは未確認、predictionsのみ）。

**結果（要点）**
- homr debugで利用可能な主なマスク:
  - `debug_5_stems_rest`, `debug_6_notehead`, `debug_7_clefs_keys`, `debug_8_bar_line_img`, `debug_11_bar_lines`
- FPの箱全体に対するマスク重なり（ratio>=0.1）:
  - notehead/stems_restはほぼゼロ（endpoint衝突は別扱い）
  - clefs_keysはpage_001で1件のみ
  - bar_line_imgはpage_001/3で1件程度
  - bar_linesは全FPで高い（FP/TP両方に高反応の可能性）
- omr-dln出力は `logs/omr_dln_sr/predictions.json` のみで、マスクは未確認。

**出力ログ**
- mask一覧: `logs/mask_inventory/20251230T074400_homr_debug_masks.json`
- FP重なり統計: `logs/mask_inventory/20251230T074618_fp_mask_overlap.json`

## 2025-12-30 案B sweep（raw/end_recovered基準）※不適合のため参考

**作業目的 / 方針 / 位置づけ**
- endpoint_ratio_overlapを全ページで一括スイープ。
- ただし raw/end_recovered を直接入力したため、row filterが過剰に強くなりFNが大量発生。

**作業時間**
- 2025-12-30 07:48:05 JST

**結果（要点）**
- FNが大幅増加。現行パイプラインの評価と整合しないため参考扱い。

**出力ログ**
- `logs/endpoint_ratio_sweep/20251230T074805_var88_end_recovered/summary.json`

## 2025-12-30 案B sweep（row_filtered基準）※不適合のため参考

**作業目的 / 方針 / 位置づけ**
- row_filteredを入力にendpoint_ratio_overlapを適用。
- row_filtered自体がGTとの一致が弱いことが判明（TPが低い）。

**作業時間**
- 2025-12-30 07:52:46 JST

**結果（要点）**
- row_filteredの段階でFNが大幅に発生し、評価に不向きと判断。

**出力ログ**
- `logs/endpoint_ratio_sweep/20251230T075246_row_filtered/summary.json`

## 2025-12-30 案B sweep（filtered_preds基準：有効）

**作業目的 / 方針 / 位置づけ**
- barline_clefs_low後の `filtered_preds.json` を基準にendpoint_ratio_overlapを適用。
- 既存条件と整合した状態でFN影響を評価。

**作業時間**
- 2025-12-30 07:55:32 JST

**結果（要点）**
- FN=0を維持できる設定が複数あり（例: thr=0.10, y=0.80/1.00/1.20）。
- FP削減は限定的で、page_3のみ1件減（7→6）程度。
- より攻めた設定（thr=0.08）ではpage_001/004/15にFNが発生。

**出力ログ**
- summary: `logs/endpoint_ratio_sweep/20251230T075532_filtered_preds/summary.json`
- config別結果: `logs/endpoint_ratio_sweep/20251230T075532_filtered_preds/thr_0.10_y0.80/<page>/metrics.json`
- FN可視化（FN発生時のみ）:
  - `logs/endpoint_ratio_sweep/20251230T075532_filtered_preds/thr_0.08_y0.80/page_001/page_001_fn_overlay.png`
  - `logs/endpoint_ratio_sweep/20251230T075532_filtered_preds/thr_0.08_y0.80/page_004/page_004_fn_overlay.png`
  - `logs/endpoint_ratio_sweep/20251230T075532_filtered_preds/thr_0.08_y0.80/page_15/page_15_fn_overlay.png`

## 2025-12-30 row bandとstaff maskの比較（row定義確認）

**作業目的 / 方針 / 位置づけ**
- row filterのrow bandが五線幅より広く見える件を確認。
- staff mask（debug_3_staff）からのbandと、preds由来row bandの比較を可視化。

**作業時間**
- 2025-12-30 08:48:52 JST

**検証内容（作用機序）**
- staff mask行の非ゼロ連続領域をband化し、row band（predsクラスタのmin/max）と重ねて可視化。

**実行コマンド（再現用）**
- `.venv_pdf/bin/python tools/render_row_band_compare.py --output-root logs/row_band_compare/20251230T084852_filtered_preds`

**出力ログ**
- まとめ: `logs/row_band_compare/20251230T084852_filtered_preds/summary.json`
- overlay: `logs/row_band_compare/20251230T084852_filtered_preds/page_3_row_vs_staff.png` ほか各ページ

## 2025-12-30 endpoint window基準の再確認（staff_space vs barline高さ）

**作業目的 / 方針 / 位置づけ**
- endpoint windowが画像解像度差に依存していないかを検証。
- staff_space と barline高さ（box高さ）・staff mask band高さを比較。

**作業時間**
- 2025-12-30 09:11:02 JST

**検証内容（作用機序）**
- `filtered_preds.json` のbarline高さ中央値を算出。
- `debug_3_staff` / `debug_15_staffs` のband高さを比較。

**結果（要点）**
- barline高さ中央値はページ間で大きく異なり（page_001≈84px, page_3≈20px）。
- `debug_3_staff` は「五線線のみ」の薄いband（高さ≈6px）で、row band用途には狭すぎる。
- `debug_15_staffs` は全体が1band化されるため、row band用途には不適。

**補足**
- barline高さ比率でendpoint windowを決める再設計が必要だが、基準とするband/heightの取り方が課題。

## 2025-12-30 endpoint windowスケール再検討（barline高さ基準のsweep）

**作業目的 / 方針 / 位置づけ**
- `endpoint_scale_base=barline_height` を導入し、barline高さ基準のスイープを実施。
- probe_scanあり/なしの挙動差を確認。

**作業時間**
- 2025-12-30 09:15:19 JST

**変更点（既存スクリプト拡張）**
- `tools/run_gt_rebuild_hybrid_eval.py` に以下を追加:
  - `--endpoint-scale-base {staff_space,barline_height}`
  - row band用 `--row-band-mode` / `--row-band-mask` / `--row-band-debug`
  - clefs_keys用 `--clefs-keys-apply-mode` / `--clefs-keys-erode`

**実施したスイープ**
- barline高さ基準（x=0.035, y=0.20/0.25/0.30, thr=0.12/0.16/0.20）
  - `logs/gt_rebuild_hybrid_eval/20251230T091519_endpoint_base_barline/`
  - 既存設定と整合せずFNが大きく増加（endbar回復不足と推定）。
- barline高さ基準（x=0.08, y=0.35/0.45/0.55, thr=0.12/0.16/0.20）
  - `logs/gt_rebuild_hybrid_eval/20251230T092322_endpoint_base_barline_x0p08/`
  - FNが解消せず（FP=0, FN=40で固定）。
- probe_scan併用
  - `logs/gt_rebuild_hybrid_eval/20251230T092852_endpoint_base_barline_x0p08_probe/`
  - FN=40が維持。endbar復元がvar88と一致しない。

**補足**
- control runでもvar88のFN=0が再現できず、union_root/scan条件が一致していない可能性が高い。
  - control: `logs/gt_rebuild_hybrid_eval/20251230T093054_control_var88/`
  - probe_x=0.04指定でも同じ: `logs/gt_rebuild_hybrid_eval/20251230T093312_control_var88_probe0p04/`

## 2025-12-30 row band定義の再評価（staff mask使用）

**作業目的 / 方針 / 位置づけ**
- row filterでstaff maskを使うとどうなるかを確認。

**作業時間**
- 2025-12-30 09:35:30 JST

**検証内容**
- `--row-band-mode staff_mask --row-band-mask staff --row-band-debug` を使用。

**結果（要点）**
- row_kept=0となりrow filterが極端に厳しすぎる。
- `debug_3_staff` は五線線のみでbandが薄く、row filterのbandには不適。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251230T093530_rowband_staffmask/`
  - per_pageの `row_band_debug.png` にband可視化あり。

## 2025-12-30 clefs_keys再検討（全幅適用 + erode）

**作業目的 / 方針 / 位置づけ**
- left限定を超えた適用を再検討。mask縮小(erode)でFN悪化を抑制できるか確認。

**作業時間**
- 2025-12-30 09:36:23 JST

**検証内容**
- apply_mode=full, erode=3/5 を試行（overlap_min=0.3）。

**結果（要点）**
- erode=3ではFPが一部減少（page_001, page_004）し、FNは増加しなかった。
- erode=5ではFPが増加傾向。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251230T093623_clef_full_erode/var_erode3/summary_table.md`
- `logs/gt_rebuild_hybrid_eval/20251230T093623_clef_full_erode/var_erode5/summary_table.md`

## 2025-12-30 var88再現の再試行（現行スクリプト）

**作業目的 / 方針 / 位置づけ**
- 既存のvar88結果を現行 `tools/run_gt_rebuild_hybrid_eval.py` で再現できるか確認する。
- var88の `geom_debug.json` / `clefs_keys_filter.json` からパラメータを抽出し、同一条件で再実行。

**作業時間**
- 2025-12-30 10:32:15 JST

**検証内容（作用機序）**
- noteheadフィルタ: open_kernel=5, min_area=20, dilate=7, max_aspect=2.0, min_height=10, max_width=6
- clefs_keys left: dilate=3, left_margin_ratio=0.20, overlap_min=0.30
- endpoint overlap: threshold=0.20, endpoint_x_scale=0.14, endpoint_y_scale=0.80
- endbar: probe_scan 有効、probe_endpoint_x_scale=0.04, probe_endpoint_y_scale=0.80, probe_notehead_dilate=13

**結果（要点）**
- var88と一致せず、FNが残存（page_001 FN=14 / page_004 FN=15 / page_10 FN=4 / page_15 FN=7）。
- end_recovered件数が不足しており、probe_scanの設定差が主因の可能性が高い。
  - page_001 end_recovered: var88=830 vs repro=524
  - page_001 end_recovered_row: var88=323 vs repro=109
  - page_001 end_recovered_geom: var88=106 vs repro=83

**出力ログ**
- 再現試行: `logs/gt_rebuild_hybrid_eval/20251230T103215_repro_var88/`
- 比較元: `logs/gt_rebuild_hybrid_eval/20251230T_hybrid_row_notehead_endbar/var88_clef_filter/`

## 2025-12-30 var88再現の追加試行（probe scan緩和）

**作業目的 / 方針 / 位置づけ**
- end_recovered件数の不足を補うため、probe_scanのピーク抽出条件を緩和して再現性を確認。

**作業時間**
- 2025-12-30 10:36:49 JST

**検証内容（作用機序）**
- `probe_min_peak_distance=2`, `probe_max_per_band=0` に変更（他はvar88設定と同じ）。

**結果（要点）**
- endbar候補が増えすぎてFPが爆発、var88再現には不適。
- FNは解消せず（page_001 FN=14など）。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251230T103649_repro_var88_probe_loose/`

## 2025-12-30 var88再現の追加試行（probe_min_ratio / probe_width）

**作業目的 / 方針 / 位置づけ**
- probe_scanの検出数不足を補うため、閾値と幅の影響を確認。

**作業時間**
- 2025-12-30 10:38:26 JST - 2025-12-30 10:39:23 JST

**検証内容（作用機序）**
- `probe_min_ratio=0.8`（他はvar88設定）
- `probe_width=2`（他はvar88設定）

**結果（要点）**
- 検出数はほぼ増えず、FNは維持（page_001 FN=14のまま）。
- var88のend_recovered件数(830)には届かない。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251230T103826_repro_var88_probe_ratio0p8/`
- `logs/gt_rebuild_hybrid_eval/20251230T103923_repro_var88_probe_w2/`

## 2025-12-30 var88再現の追加試行（probe row / ink / max_per_band）

**作業目的 / 方針 / 位置づけ**
- probe_scanの不足要因を切り分けるため、row条件・ink閾値・max_per_bandを個別に変更。

**作業時間**
- 2025-12-30 10:41:32 JST - 2025-12-30 10:45:11 JST

**検証内容（作用機序）**
- rowを緩和: `probe_row_min_count=1`, `probe_row_max_dist=40`, `probe_row_tol_top=20`, `probe_row_tol_bottom=20`
- ink閾値変更: `probe_ink_threshold=200`
- 検出上限変更: `probe_max_per_band=12`
- row再利用: `probe_row_filter_mode=reuse_rows`

**結果（要点）**
- row緩和とmax_per_band=12はFP増加のみでFN改善に寄与せず。
- ink閾値変更はほぼ影響なし。
- reuse_rowsは追加回復が消失（end_recovered_row=0）。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251230T104132_repro_var88_probe_row_loose/`
- `logs/gt_rebuild_hybrid_eval/20251230T104216_repro_var88_probe_ink200/`
- `logs/gt_rebuild_hybrid_eval/20251230T104348_repro_var88_probe_max12/`
- `logs/gt_rebuild_hybrid_eval/20251230T104511_repro_var88_probe_reuse_rows/`

## 2025-12-30 var88再現の追加試行（probe band height mode）

**作業目的 / 方針 / 位置づけ**
- var88のend_recovered高さが約85pxであるため、probe_scanのband height modeを再検討。

**作業時間**
- 2025-12-30 10:46:36 JST - 2025-12-30 10:49:29 JST

**検証内容（作用機序）**
- `probe_band_height_mode=median_box` を試行（barline高さをbandに反映）。
- 追加で `probe_max_per_band=0`, `probe_min_peak_distance=2`, `probe_min_ratio=0.7` を段階的に調整。

**結果（要点）**
- median_boxでFNが大幅に減少（page_001 FN=7, page_004 FN=7 まで改善）。
- max_per_band=0 + min_peak_distance=2でFNは2〜5に減少。
- min_ratio=0.7まで下げるとFN=0に近づくがFPが増加。
- var88（FN=0, FP低）には未到達だが、band height modeが主要因であることが判明。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251230T104636_repro_var88_probe_medianbox/`
- `logs/gt_rebuild_hybrid_eval/20251230T104742_repro_var88_medianbox_max0/`
- `logs/gt_rebuild_hybrid_eval/20251230T104836_repro_var88_medianbox_max0_min2/`
- `logs/gt_rebuild_hybrid_eval/20251230T104929_repro_var88_medianbox_max0_min2_ratio0p7/`

## 2025-12-30 run_gt_rebuild_hybrid_eval.py のgit履歴確認

**作業目的 / 方針 / 位置づけ**
- 現行スクリプトの形になったタイミングと、aspect filter等の有効化条件を確認。
- var88再現不一致の原因候補を絞るための履歴確認。

**作業時間**
- 2025-12-30 11:06:30 JST

**確認内容**
- `git log --follow` で主要コミットを確認。
  - 36ed3c7: notehead maskのdenoise/ aspect filter追加（デフォルトは無効）。
  - 21235f4: clefs_keysフィルタ導入 + notehead_dilate追加（デフォルトは無効）。
- 現行の `--notehead-max-aspect` / `--notehead-min-height` / `--notehead-max-width` はデフォルト0で、**明示指定時のみ有効**。

**補足**
- var88の `geom_debug.json` には `max_aspect=2.0, min_height=10, max_width=6` が記録されているため、aspect filterは**実行時に明示指定されている**。

## 2025-12-30 sweep 1: probe_band_height_mode

**作業目的 / 方針 / 位置づけ**
- var88再現の主要差分候補として、probe_scanのband height modeを比較。

**作業時間**
- 2025-12-30 14:13:07 JST - 2025-12-30 14:13:39 JST

**検証内容（作用機序）**
- var88と同一パラメータで `probe_band_height_mode` を `staff` / `median_box` で比較。

**結果（要点）**
- `staff` はFNが多く再現できず（page_001 FN=14）。
- `median_box` はFNが大きく減少（page_001 FN=7）。  
  → var88のend_recovered高さ（~85px）に整合し、再現に重要な差分と判断。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251230T141307_sweep_bandheight_staff/`
- `logs/gt_rebuild_hybrid_eval/20251230T141339_sweep_bandheight_median/`

## 2025-12-30 sweep 2: probe_min_ratio / probe_max_per_band

**作業目的 / 方針 / 位置づけ**
- `probe_band_height_mode=median_box` を前提に、peak抽出条件の不一致を確認する。

**作業時間**
- 2025-12-30 14:14:45 JST - 2025-12-30 14:18:25 JST

**検証内容（作用機序）**
- `probe_min_ratio ∈ {0.75, 0.80, 0.85}`  
- `probe_max_per_band ∈ {6, 8, 10}`  
- 他はvar88設定（clefs_keys left + notehead aspect + probe_notehead_dilate=13）。

**結果（要点）**
- FNは改善するが、どの組合せでもFN=0には届かない。  
  - 例: ratio=0.85, max_per_band=10 → page_001/004/10/15 FN=5/5/3/5
- ここでは「probe_min_ratio / max_per_band だけでは再現不能」なことを確認。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251230T141445_sweep_probe_ratio0.75_max6/`
- `logs/gt_rebuild_hybrid_eval/20251230T141445_sweep_probe_ratio0.75_max8/`
- `logs/gt_rebuild_hybrid_eval/20251230T141445_sweep_probe_ratio0.75_max10/`
- `logs/gt_rebuild_hybrid_eval/20251230T141445_sweep_probe_ratio0.80_max6/`
- `logs/gt_rebuild_hybrid_eval/20251230T141445_sweep_probe_ratio0.80_max8/`
- `logs/gt_rebuild_hybrid_eval/20251230T141445_sweep_probe_ratio0.80_max10/`
- `logs/gt_rebuild_hybrid_eval/20251230T141445_sweep_probe_ratio0.85_max6/`
- `logs/gt_rebuild_hybrid_eval/20251230T141445_sweep_probe_ratio0.85_max8/`
- `logs/gt_rebuild_hybrid_eval/20251230T141445_sweep_probe_ratio0.85_max10/`

## 2025-12-30 sweep 3: endbar_staff_mask_mode

**作業目的 / 方針 / 位置づけ**
- endbarのstaff mask選択（staff / staffs）の不一致を確認する。

**作業時間**
- 2025-12-30 14:18:57 JST - 2025-12-30 14:19:30 JST

**検証内容（作用機序）**
- `probe_band_height_mode=median_box`, `probe_min_ratio=0.85`, `probe_max_per_band=10` を固定。
- `endbar_staff_mask_mode` を `staff` / `staffs` で比較。

**結果（要点）**
- `staffs` はendbar回復がほぼ消失（FNが増加）。  
- `staff` は回復が維持されるがFN=0には届かない。  
  → var88再現には **staff** が必須で、staffsは不一致要因と判断。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251230T141857_sweep_endbar_mask_staff/`
- `logs/gt_rebuild_hybrid_eval/20251230T141930_sweep_endbar_mask_staffs/`

## 2025-12-30 指定コマンドの実行確認（CLI差分の検証）

**作業目的 / 方針 / 位置づけ**
- ユーザー指定のコマンドをそのまま実行し、現行スクリプトとのCLI差分を確認。

**作業時間**
- 2025-12-30 14:24:10 JST

**結果（要点）**
- 現行 `tools/run_gt_rebuild_hybrid_eval.py` では `--union-root` が必須で、`--run-tag` / `--images` / `--ground-truth` / `--probe-scan` / `--probe-endpoint-ratio-threshold` は未定義。
- 指定コマンドは別バージョンのCLI仕様である可能性が高い。

**補足**
- `--probe-scan` 相当は現行では `--enable-end-barline-recovery --endbar-method probe_scan`。
- `--probe-endpoint-ratio-threshold` 相当は現行では `--endpoint-ratio-threshold` のみで個別指定不可。

## 2025-12-30 CLI対応のgit履歴調査（run-tag / images / ground-truth）

**作業目的 / 方針 / 位置づけ**
- 指定コマンドに含まれるCLIがどの時点のコードに対応していたかを特定。
- 変更のタイミングと理由を把握。

**作業時間**
- 2025-12-30 14:33:20 JST

**確認内容**
- `tools/run_gt_rebuild_hybrid_eval.py` の履歴では `--run-tag` / `--images` / `--ground-truth` / `--probe-scan` の記録がなく、該当CLIが存在した痕跡は見つからない。
- `src/homr_eval_scripts/homr_evaluator.py` に `--images` / `--run-tag` / `--ground-truth` が存在し、初回導入は `b244f5c`（2025-12-12）コミット。
  - コミット理由: homr評価スクリプトの再配置・評価パイプライン整理（commit messageに記載）。
- `probe-scan` オプションは homr_evaluator には存在せず、現行リポジトリ内で一致するCLIは未確認。

## 2025-12-30 SESSION_LOG_temp.md の履歴確認

**作業目的 / 方針 / 位置づけ**
- 過去セッションのコマンド記録が残っている可能性を確認。

**作業時間**
- 2025-12-30 14:36:50 JST

**確認内容**
- `docs/SESSION_LOG_temp.md` は 2025-12-29 周辺のコミットに存在。
- 当該ログ内には homr evaluator 実行や endbar 回復の記述はあるが、`--images` / `--ground-truth` / `--run-tag` の具体コマンド記載は見つからない。

**補足**
- 該当コマンドは `homr_evaluator.py` のCLI仕様に一致するため、var88とは別系統の評価手順だった可能性が高い。

## 2025-12-30 var88当日のスクリプト更新タイミング確認

**作業目的 / 方針 / 位置づけ**
- var88生成時点に近い `tools/run_gt_rebuild_hybrid_eval.py` のコミット時刻を確認。

**作業時間**
- 2025-12-30 14:41:05 JST

**確認内容**
- 2025-12-30 03:04:54 の `3d0bf23` で barline/clefs_keys_ratio フィルタが追加。
- 2025-12-29 21:07:29 の `4225adf` で clef key調査。
- 2025-12-29 18:53:26 の `21235f4` で記号フィルタ導入。

**補足**
- var88ログのタイムスタンプは `20251230T_hybrid_row_notehead_endbar` で、上記コミット時刻と近接。

## 2025-12-30 コミット切替でのvar88再現試行

**作業目的 / 方針 / 位置づけ**
- 当時のコードに近いコミットへ切り替え、var88の再現可否を確認。

**作業時間**
- 2025-12-30 14:40:10 JST - 2025-12-30 14:40:33 JST

**検証内容（作用機序）**
- `git stash` で現行変更を退避し、`3d0bf23` に checkout（detached HEAD）。
- var88相当パラメータを指定し、`probe_band_height_mode=median_box` で再実行。

**結果（要点）**
- FNが残り、var88（FN=0）には未到達。
  - page_001: TP=71 FP=1 FN=7
  - page_004: TP=105 FP=5 FN=7
  - page_10: TP=151 FP=1 FN=3
  - page_15: TP=107 FP=5 FN=5

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251230T144033_repro_var88_commit3d0b/`

## 2025-12-30 var88生成時刻とコミット整合の再確認

**作業目的 / 方針 / 位置づけ**
- var88生成時点のコードがどのコミットに近いかを再確認する。

**作業時間**
- 2025-12-30 15:04:04 JST

**確認内容**
- var88ログの `summary_table.md` / `clefs_keys_filter.json` のmtimeは 2025-12-29 18:41台。
- `tools/run_gt_rebuild_hybrid_eval.py` のコミット時刻は以下:
  - `21235f4`: 2025-12-29 18:53（clefs_keys導入）
  - `36ed3c7`: 2025-12-29 17:06

**補足**
- var88ログにclefs_keys_filterが含まれるため、コード状態は少なくとも `21235f4` と同等以上。
- mtimeがコミット時刻より前に見えるため、当時の未コミット状態で実行された可能性がある。

## 2025-12-30 コミット21235f4でのvar88再現試行

**作業目的 / 方針 / 位置づけ**
- clefs_keys導入後のコミット（21235f4）でvar88が再現できるか確認。

**作業時間**
- 2025-12-30 15:04:04 JST - 2025-12-30 15:04:25 JST

**結果（要点）**
- 3d0bf23時と同様にFNが残り、var88（FN=0）には未到達。
  - page_001: TP=71 FP=1 FN=7
  - page_004: TP=105 FP=5 FN=7
  - page_10: TP=151 FP=1 FN=3
  - page_15: TP=107 FP=5 FN=5

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251230T150404_repro_var88_commit21235f4/`

## 2025-12-30 var88完全一致の再現手順（復旧）

**作業目的 / 方針 / 位置づけ**
- var88のFN=0/FP低の結果を、現行スクリプトと完全一致で再現する。

**作業時間**
- 2025-12-30 17:45:00 JST

**実施内容**
- 重要差分の特定:
  - `probe_row_filter_mode=reuse_rows` に変更すると end_recovered_row が一致。
  - `probe_endpoint_x_scale=0.04` を明示すると end_recovered_geom が一致。
- 上記差分を反映することで `var88_clef_filter` のTP/FP/FNが完全一致。

**再現環境**
- commit: `f41fa96c9bd7d73201913001ac592e50ce625e3c`
- output: `logs/gt_rebuild_hybrid_eval/repro_var88_from_logs_reuse_rows_probe_eps/`

**実行コマンド（完全一致）**
- `.venv_pdf/bin/python tools/run_gt_rebuild_hybrid_eval.py --output-root logs/gt_rebuild_hybrid_eval/repro_var88_from_logs_reuse_rows_probe_eps --union-root logs/phase5b_confirmed_union_eval --endpoint-ratio-threshold 0.20 --endpoint-x-scale 0.14 --endpoint-y-scale 0.80 --notehead-open-kernel 5 --notehead-min-area 20 --notehead-dilate 7 --notehead-max-aspect 2.0 --notehead-min-height 10 --notehead-max-width 6 --filter-clefs-keys --clefs-keys-dilate 3 --clefs-keys-left-margin-ratio 0.20 --clefs-keys-overlap-min 0.30 --enable-end-barline-recovery --endbar-method probe_scan --endbar-staff-mask-mode staff --probe-width 3 --probe-ink-threshold 180 --probe-min-ratio 0.80 --probe-min-peak-distance 2 --probe-max-per-band 0 --probe-refine-window 4 --probe-band-height-mode median_box --probe-band-height-scale 1.0 --probe-band-height-min 10 --probe-notehead-dilate 13 --probe-row-filter-mode reuse_rows --probe-endpoint-x-scale 0.04 --probe-endpoint-y-scale 0.80`

## 2025-12-30 resumeセッションによるvar88復元の確認

**作業目的 / 方針 / 位置づけ**
- resumeしたセッションで、var88の完全一致再現が確認されたことを反映する。

**作業時間**
- 2025-12-30 18:05:00 JST

**確認内容**
- 完全一致の再現ログ: `logs/gt_rebuild_hybrid_eval/repro_var88_from_logs_reuse_rows_probe_eps/`
- 再現条件は上記「var88完全一致の再現手順（復旧）」のコマンドと一致。

**次の作業予定**
- var88完全一致の再現条件を前提に、残存FPの可視化（overlay + crop）を再生成。
- FPの原因カテゴリ（clef/accidental/stem/装飾）の比率をページ別に集計し、除去ルール候補を1つに絞る。

## 2025-12-30 var88復元結果のFP可視化（postfilter_analysis）

**作業目的 / 方針 / 位置づけ**
- resumeセッションで復元されたvar88の結果に対し、FP残存の可視化を再生成。

**作業時間**
- 2025-12-30 18:43:28 JST

**実行内容**
- `tools/probe_postfilter_analysis.py` を使用し、FP残存とendbarフィルタの効果を可視化。

**出力ログ**
- `logs/probe_postfilter_analysis/20251230T184328_var88_repro/`
  - `page_XXX_fp_remaining.png`
  - `page_XXX_filter_effects.png`
  - `summary.json`

## 2025-12-30 var88復元結果のFP原因分布（マスク重なり）

**作業目的 / 方針 / 位置づけ**
- var88復元結果のFPに対し、homr中間マスクとの重なりで原因カテゴリの当たりを付ける。

**作業時間**
- 2025-12-30 18:45:00 JST

**検証内容（作用機序）**
- FP boxごとにマスク重なり率を算出（clefs_keys / stems_rest / notehead / barline / symbols / notes）。
- 閾値0.2以上の重なり数、および最大重なりラベルを集計。

**出力ログ**
- `logs/fp_category_analysis/20251230T184500_var88_repro/`
  - `summary.json`
  - `page_XXX_fp_mask_ratios.json`

## 2025-12-30 FPマスク重ね合わせクロップの作成

**作業目的 / 方針 / 位置づけ**
- FPに対する各マスク（clefs_keys / stems_rest / notehead / barline / symbols / notes）の重なりを目視確認する。

**作業時間**
- 2025-12-30 19:00:00 JST

**実行内容**
- var88復元結果のFPを最大6件/ページ抽出し、マスクの重ね合わせクロップを生成。

**出力ログ**
- `logs/fp_mask_crops/20251230T190000_var88_repro/`
  - `page_XXX/fp_XX_mask_overlay.png`

## 2025-12-30 FPマスク重ね合わせの目視確認（全ページ）

**作業目的 / 方針 / 位置づけ**
- 各ページのFPクロップ（最大6件/ページ）を目視し、マスクの実用性を判断。

**作業時間**
- 2025-12-30 19:05:00 JST

**目視所見（要点）**
- notesマスクは全FPに強く重なり、識別用途には不向き（過検出気味）。
- symbolsマスクは局所的で一貫性が弱く、単独ルールに使いにくい。
- clefs_keysはpage_004/15で重なりが目立つが、page_001/10では弱い。
- barline/stems_restはpage_001/15で重なりが目立つが、TPにも重なる可能性が高い。

**統計（threshold=0.2）**
- 集計元: `logs/fp_category_analysis/20251230T184500_var88_repro/summary.json`
- aggregate (FP=39):
  - mask_counts_ge_0p2: clefs_keys=9, stems_rest=15, notehead=2, barline=17, symbols=1, notes=39
  - top_label_counts: notes=33, barline=5, clefs_keys=1

## 2025-12-30 FP×マスク成分の衝突統計（clefs_keys / barline）

**作業目的 / 方針 / 位置づけ**
- マスク「含有」(connected component中心ヒット) を使った判定が安全かをFP/TPで比較。

**作業時間**
- 2025-12-30 19:30:00 JST

**実行内容**
- clefs_keys / barline の connected components を算出し、FP/TPで中心ヒット数とoverlap比率を集計。

**出力ログ**
- `logs/fp_component_analysis/20251230T193000_var88_repro/summary.json`

**集計結果（全ページ合算）**
- clefs_keys:
  - center_hit: FP 6/39, TP 9/456
  - overlap>=0.2: FP 9/39, TP 16/456
  - overlap>=0.5: FP 8/39, TP 7/456
- barline:
  - center_hit: FP 17/39, TP 436/456
  - overlap>=0.2: FP 17/39, TP 451/456
  - overlap>=0.5: FP 16/39, TP 439/456

## 2025-12-30 clefs_keys内接コア×endpoint windowによるFP除去テスト

**作業目的 / 方針 / 位置づけ**
- clefs_keysマスクの「内接コア」（distance transformで縮約した成分）と、barline候補のendpoint windowの重なりでFP除去できるかを検証。
- 画像解像度差の影響を避けるため、endpoint windowはbarline median height 比でスケール。

**作業時間**
- 2025-12-30 19:50:00 JST

**実行内容**
- clefs_keys mask componentをdistance transformで縮約し、コア円（core_scale=0.7）を生成。
- barline候補の上端/下端にendpoint windowを作成し、コア円との重なりがあれば除去。
- 2パターン（rx/ryスケール）を比較。

**出力ログ**
- `logs/clefs_keys_endpoint_core/20251230T195000_var88_repro/summary.json`
- `logs/clefs_keys_endpoint_core/20251230T195000_var88_repro/rx0p04_ry0p80/`
  - `page_XXX_removed.json`
- `logs/clefs_keys_endpoint_core/20251230T195000_var88_repro/rx0p06_ry0p60/`
  - `page_XXX_removed.json`

**結果（全ページ合算）**
- rx0p04_ry0p80: TP=425, FP=31, FN=31（removed=51）
- rx0p06_ry0p60: TP=424, FP=30, FN=32（removed=53）

**所見**
- いずれの設定でもFNが大きく増加（var88基準のFN=0から悪化）。
- clefs_keysの内接コアを使っても、現在のendpoint window設定ではTPを巻き込みやすい。

## 2025-12-30 clefs_keys内接コアのsweep（core_scale 0.4-0.7）+ 可視化

**作業目的 / 方針 / 位置づけ**
- clefs_keys内接コアの縮小がFNを抑えつつFP低減できるかを確認。
- 既存結果とsweep結果を比較できるよう、除去対象のoverlay+cropを出力。

**作業時間**
- 2025-12-30 21:50:00 JST

**実行内容**
- clefs_keysマスクからdistance transformで内接コアを生成（core_scale=0.4/0.5/0.6/0.7）。
- endpoint windowはbarline median height比で2パターン（rx0.04/ry0.80, rx0.06/ry0.60）。
- 候補はgeom_keptを用い、評価はgreedy_barline_match(iou=0.5)でTP/FP/FNを算出。
- 除去候補ごとに「コア(緑)+候補(赤)+endpoint window(黄)」のoverlay cropを出力。

**出力ログ**
- `logs/clefs_keys_endpoint_core_sweep/20251230T215027_var88_repro_geomkept/summary.json`
- `logs/clefs_keys_endpoint_core_sweep/20251230T215027_var88_repro_geomkept/core0.40/`
- `logs/clefs_keys_endpoint_core_sweep/20251230T215027_var88_repro_geomkept/core0.50/`
- `logs/clefs_keys_endpoint_core_sweep/20251230T215027_var88_repro_geomkept/core0.60/`
- `logs/clefs_keys_endpoint_core_sweep/20251230T215027_var88_repro_geomkept/core0.70/`

**結果（全ページ合算）**
- core0.40:
  - rx0p04_ry0p80: TP=453, FP=38, FN=21（removed=8）
  - rx0p06_ry0p60: TP=453, FP=38, FN=21（removed=8）
- core0.50:
  - rx0p04_ry0p80: TP=453, FP=38, FN=21（removed=8）
  - rx0p06_ry0p60: TP=453, FP=38, FN=21（removed=8）
- core0.60:
  - rx0p04_ry0p80: TP=455, FP=38, FN=19（removed=4）
  - rx0p06_ry0p60: TP=455, FP=38, FN=19（removed=4）
- core0.70:
  - rx0p04_ry0p80: TP=457, FP=39, FN=17（removed=0）
  - rx0p06_ry0p60: TP=457, FP=39, FN=17（removed=0）

**所見**
- core_scaleを縮小してもFPはほぼ変わらず、FNが残る傾向。
- 2つのendpoint window設定で差がほぼ出ない。

## 2025-12-30 clefs_keys内接コアsweepの可視化（FPと新規FNのみ）

**作業目的 / 方針 / 位置づけ**
- 既存FPと新規FNのみを可視化し、clefs_keysマスクとの衝突判定の妥当性を確認。
- 元マスクと内接コアを同時に重ねて表示（元マスク=青、コア=緑）。

**作業時間**
- 2025-12-30 22:55:00 JST

**実行内容**
- clefs_keysマスクが元画像と解像度不一致のため、画像サイズへ最近傍リサイズして重ね合わせ。
- FPはbaseline（var88）fp_boxesから抽出、FNは「除去されたTP（barline_iou>=0.5）」として定義。
- 可視化は各設定ごとに「FPクロップ」「FNクロップ」のみ保存。

**出力ログ**
- `logs/clefs_keys_endpoint_core_sweep_visuals/20251230T225523_var88_repro_geomkept/summary.json`
- `logs/clefs_keys_endpoint_core_sweep_visuals/20251230T225523_var88_repro_geomkept/core0.40/`
- `logs/clefs_keys_endpoint_core_sweep_visuals/20251230T225523_var88_repro_geomkept/core0.50/`
- `logs/clefs_keys_endpoint_core_sweep_visuals/20251230T225523_var88_repro_geomkept/core0.60/`
- `logs/clefs_keys_endpoint_core_sweep_visuals/20251230T225523_var88_repro_geomkept/core0.70/`

**集計（全ページ合算）**
- core0.40:
  - rx0p04_ry0p80: baseline FP=39, new FN=5, removed FP=9
  - rx0p06_ry0p60: baseline FP=39, new FN=5, removed FP=10
- core0.50:
  - rx0p04_ry0p80: baseline FP=39, new FN=0, removed FP=6
  - rx0p06_ry0p60: baseline FP=39, new FN=0, removed FP=8
- core0.60:
  - rx0p04_ry0p80: baseline FP=39, new FN=0, removed FP=1
  - rx0p06_ry0p60: baseline FP=39, new FN=0, removed FP=3
- core0.70:
  - rx0p04_ry0p80: baseline FP=39, new FN=0, removed FP=1
  - rx0p06_ry0p60: baseline FP=39, new FN=0, removed FP=1

**所見**
- マスクと画像の解像度差が原因で「clef以外に当たって見える」ケースが発生していたため、今回リサイズして可視化を再生成。
- core0.5以上では新規FNは出ないが、FP除去も限定的。

## 2025-12-30 core0.4/0.5の比較可視化（removed FP識別 + マスクノイズ除去）

**作業目的 / 方針 / 位置づけ**
- core0.4とcore0.5を並列に比較し、FP除去の成功/不成功を可視化で判別可能にする。
- clefs_keysマスクの軽いノイズ除去（denoise_v1）を試し、FN増加なしでFP除去が改善するか確認。

**作業時間**
- 2025-12-30 23:25:00 JST

**実行内容**
- 可視化対象は「baseline FP」と「新規FN（除去されたTP）」のみ。
- removed FPは枠色をマゼンタ、未除去FPは赤で表示し、ラベルで識別。
- マスクは元マスクを青、内接コアを緑で重ね合わせ。
- denoise_v1: 3x3 opening + 小面積成分除去（area < max(20, (median_height*0.1)^2)）。

**出力ログ**
- `logs/clefs_keys_endpoint_core_sweep_visuals/20251230T232521_var88_repro_geomkept/summary.json`
- `logs/clefs_keys_endpoint_core_sweep_visuals/20251230T232521_var88_repro_geomkept/raw/`
- `logs/clefs_keys_endpoint_core_sweep_visuals/20251230T232521_var88_repro_geomkept/denoise_v1/`

**集計（全ページ合算）**
- raw core0.4:
  - rx0p04_ry0p80: baseline FP=39, removed FP=9, new FN=5
  - rx0p06_ry0p60: baseline FP=39, removed FP=10, new FN=5
- raw core0.5:
  - rx0p04_ry0p80: baseline FP=39, removed FP=6, new FN=0
  - rx0p06_ry0p60: baseline FP=39, removed FP=8, new FN=0
- denoise_v1 core0.4:
  - rx0p04_ry0p80: baseline FP=39, removed FP=9, new FN=5
  - rx0p06_ry0p60: baseline FP=39, removed FP=10, new FN=5
- denoise_v1 core0.5:
  - rx0p04_ry0p80: baseline FP=39, removed FP=6, new FN=0
  - rx0p06_ry0p60: baseline FP=39, removed FP=8, new FN=0

**所見**
- denoise_v1はrawと同等で、FP除去やFN抑制に変化は見られなかった。

## 2025-12-30 ノイズ除去手法の比較（raw / denoise_v1 / denoise_area / denoise_height）

**作業目的 / 方針 / 位置づけ**
- ノイズ除去でFNを増やさずにFP除去が改善できるかを確認（core0.40/0.50を同時に比較）。
- 各手法についてFP/NEW_FNの可視化を生成し目視確認。

**作業時間**
- 2025-12-30 23:40:00 JST

**実行内容**
- mask_modes: raw / denoise_v1 / denoise_area / denoise_height。
- denoise_area: 小面積成分除去（area < max(30, (median_height*0.20)^2)）。
- denoise_height: 低い成分除去（height < max(8, median_height*0.40)）。
- 可視化はbaseline FPとNEW_FNのみ（removed FPはマゼンタ枠で識別）。

**出力ログ**
- `logs/clefs_keys_endpoint_core_sweep_visuals/20251230T234203_var88_repro_geomkept/summary.json`
- `logs/clefs_keys_endpoint_core_sweep_visuals/20251230T234203_var88_repro_geomkept/raw/`
- `logs/clefs_keys_endpoint_core_sweep_visuals/20251230T234203_var88_repro_geomkept/denoise_v1/`
- `logs/clefs_keys_endpoint_core_sweep_visuals/20251230T234203_var88_repro_geomkept/denoise_area/`
- `logs/clefs_keys_endpoint_core_sweep_visuals/20251230T234203_var88_repro_geomkept/denoise_height/`

**集計（全ページ合算）**
- raw:
  - core0.40: removed FP=9-10, new FN=5
  - core0.50: removed FP=6-8, new FN=0
- denoise_v1:
  - core0.40: removed FP=9-10, new FN=5
  - core0.50: removed FP=6-8, new FN=0
- denoise_area:
  - core0.40: removed FP=9-10, new FN=4
  - core0.50: removed FP=6-8, new FN=0
- denoise_height:
  - core0.40: removed FP=8-9, new FN=5
  - core0.50: removed FP=7, new FN=0

**所見**
- core0.40のFNは残り、ノイズ除去で完全には解消できていない。
- core0.50は全手法でFN=0を維持し、FP除去は6-8件程度で安定。

## 2025-12-30 core0.40のみ除去できるFPの確認 + core0.45試行

**作業目的 / 方針 / 位置づけ**
- core0.40で除去できるがcore0.50で残るFPを特定し、別手法での除去可否を検討。
- 中間値core0.45の可能性を確認。

**作業時間**
- 2025-12-30 23:50:00 JST

**実行内容**
- raw core0.40 vs core0.50（rx0p06_ry0p60）で除去FPの差分を抽出。
- core0.45（raw/denoise_area/denoise_height）で可視化と統計を作成。

**出力ログ**
- 差分リスト: `logs/clefs_keys_endpoint_core_sweep_visuals/20251230T234203_var88_repro_geomkept/only40_not50.json`
- core0.45可視化: `logs/clefs_keys_endpoint_core_sweep_visuals/20251230T234949_var88_repro_geomkept/summary.json`
- core0.45画像: `logs/clefs_keys_endpoint_core_sweep_visuals/20251230T234949_var88_repro_geomkept/*/core0.45/`

**差分（core0.40のみ除去されるFP）**
- page_15: 2件
  - [1568, 1075, 1572, 1149]
  - [2422, 850, 2424, 922]

**core0.45集計（全ページ合算）**
- raw:
  - rx0p04_ry0p80: removed FP=8, new FN=4
  - rx0p06_ry0p60: removed FP=10, new FN=4
- denoise_area:
  - rx0p04_ry0p80: removed FP=8, new FN=4
  - rx0p06_ry0p60: removed FP=10, new FN=4
- denoise_height:
  - rx0p04_ry0p80: removed FP=8, new FN=4
  - rx0p06_ry0p60: removed FP=9, new FN=4

**所見**
- core0.45はFNが残り、core0.50の「FN=0」を維持できない。

## 2025-12-31 core0.50採用の決定

**作業目的 / 方針 / 位置づけ**
- clefs_keys内接コア方式はcore0.50でFN=0を維持できるため、これを採用値として固定する。

**作業時間**
- 2025-12-31 00:10:00 JST

**決定事項**
- clefs_keys内接コアはcore0.50を採用（endpoint windowはrx0p04_ry0p80/0p06_ry0p60のいずれもFN=0）。

**次の作業方針**
- 局所形状フィルタを試行した後、音符密度の観点のフィルタを検討する。

## 2025-12-31 局所形状フィルタ（thin/short component）試行

**作業目的 / 方針 / 位置づけ**
- clefs_keys近傍の細い/短い成分を用いてFPを除去できるか確認。
- core0.50（採用値）後に局所形状フィルタを適用。

**作業時間**
- 2025-12-31 00:10:00 JST

**実行内容**
- clefs_keysマスクのconnected componentsを算出し、成分の高さ/幅が閾値以下なら該当候補を除去。
- 閾値は median_height 比で4通り（hr=0.7/0.9, wr=0.15/0.20）。
- 可視化はbaseline FPとNEW_FNのみ（removed FPはマゼンタ枠で識別）。

**出力ログ**
- `logs/local_shape_filter/20251231T000929_var88_repro/summary.json`
- `logs/local_shape_filter/20251231T000929_var88_repro/hr0.70_wr0.15/`
- `logs/local_shape_filter/20251231T000929_var88_repro/hr0.90_wr0.15/`
- `logs/local_shape_filter/20251231T000929_var88_repro/hr0.70_wr0.20/`
- `logs/local_shape_filter/20251231T000929_var88_repro/hr0.90_wr0.20/`

**集計（全ページ合算）**
- hr0.70_wr0.15: TP=429, FP=28, FN=45, removed FP=2, new FN=34
- hr0.90_wr0.15: TP=428, FP=28, FN=46, removed FP=2, new FN=35
- hr0.70_wr0.20: TP=429, FP=28, FN=45, removed FP=2, new FN=34
- hr0.90_wr0.20: TP=428, FP=28, FN=46, removed FP=2, new FN=35

**所見**
- 局所形状（thin/short成分）基準はTPを大きく巻き込み、FNが大幅に増加。
- FP除去効果は小さく（2件）、実用性が低い。

## 2025-12-31 音符密度フィルタ（小節間隔に基づく近接除去）試行

**作業目的 / 方針 / 位置づけ**
- 小節線間隔の分布から「極端に狭い候補」を除去する音符密度フィルタを評価。
- core0.50適用後にフィルタを重ねる。

**作業時間**
- 2025-12-31 00:30:00 JST

**実行内容**
- 候補をy中心クラスタで行単位にグルーピング（row_tol = median_height*0.6）。
- 同一行内のbarline間隔中央値に対し、最小間隔が ratio * median_spacing 未満なら除去。
- ratio = 0.25 / 0.30 / 0.35 / 0.40。
- 可視化はbaseline FPとNEW_FNのみ（removed FPはマゼンタ枠で識別）。

**出力ログ**
- `logs/density_filter/20251231T001324_var88_repro/summary.json`
- `logs/density_filter/20251231T001324_var88_repro/ratio0.25/`
- `logs/density_filter/20251231T001324_var88_repro/ratio0.30/`
- `logs/density_filter/20251231T001324_var88_repro/ratio0.35/`
- `logs/density_filter/20251231T001324_var88_repro/ratio0.40/`

**集計（全ページ合算）**
- ratio0.25: TP=209, FP=23, FN=265, removed FP=5, new FN=510
- ratio0.30: TP=205, FP=23, FN=269, removed FP=5, new FN=515
- ratio0.35: TP=204, FP=22, FN=270, removed FP=6, new FN=516
- ratio0.40: TP=204, FP=21, FN=270, removed FP=7, new FN=516

**所見**
- 近接除去が過剰でFNが大幅に増加し、現状の定義では実用性が低い。

## 2025-12-31 音符密度フィルタ（noteheadマスク併用）試行

**作業目的 / 方針 / 位置づけ**
- 小節間隔の近接条件に加え、noteheadマスクの空白判定を導入し、過剰なFNを抑制できるか確認。
- core0.50適用後にフィルタを重ねる。

**作業時間**
- 2025-12-31 00:40:00 JST

**実行内容**
- staffマスクのconnected componentsで行を定義し、同一行内の候補をx順に並べて間隔中央値を算出。
- 近接候補（min_dist < ratio * median_spacing）かつ gap内notehead=0 の場合のみ除去。
- 除去対象はbarlineマスクの重なりが小さい側を優先。
- ratio = 0.20 / 0.25 / 0.30。
- 可視化はbaseline FPとNEW_FNのみ（removed FPはマゼンタ枠で識別）。

**出力ログ**
- `logs/density_filter_notehead/20251231T002445_var88_repro/summary.json`
- `logs/density_filter_notehead/20251231T002445_var88_repro/ratio0.20/`
- `logs/density_filter_notehead/20251231T002445_var88_repro/ratio0.25/`
- `logs/density_filter_notehead/20251231T002445_var88_repro/ratio0.30/`

**集計（全ページ合算）**
- ratio0.20: TP=457, FP=30, FN=17, removed FP=0, new FN=0
- ratio0.25: TP=457, FP=30, FN=17, removed FP=0, new FN=0
- ratio0.30: TP=457, FP=30, FN=17, removed FP=0, new FN=0

**所見**
- notehead空白条件を加えてもFPは除去できず、効果なし。

## 2025-12-31 HOMR出力に拍子情報があるかの確認

**作業目的 / 方針 / 位置づけ**
- 拍子・拍数などの情報をHOMR出力から取得可能かを確認。

**作業時間**
- 2025-12-31 01:00:00 JST

**実行内容**
- homr_eval出力内のJSON/CSV/XMLから拍子関連のキーを検索。
- detections.jsonを確認。

**所見**
- homr_evalのJSON/CSVには拍子情報が見当たらない。
- 拍子情報が確実に含まれるのはmusicxmlのみ（現状の中間マスクには明示的な拍子ラベルがない）。

## 2025-12-31 musicxmlの拍子・音符情報の利用方針検討

**作業目的 / 方針 / 位置づけ**
- musicxmlから拍子・音符情報を取り出し、画像側の密度フィルタの補助に使えるかを検討。
- 位置情報は使わず、拍子や音符内容のみを参照する方針。

**作業時間**
- 2025-12-31 01:20:00 JST

**実行内容**
- `page_001.musicxml`を確認し、`<time>`タグが存在することを確認。
- homrの`detections.json`はbboxとsystem/staff indexのみで拍子情報はないことを再確認。

**所見**
- 拍子変更はmusicxml内のmeasure単位で取得可能（変拍子対応の可能性あり）。
- ただし、measure順序を画像側のbarline候補に対応付ける必要があるため、homr barline順序（system_index/staff_index/x順）との簡易アラインが必要。

## 2025-12-31 musicxml補助の密度フィルタ（試作・独立スクリプト）

**作業目的 / 方針 / 位置づけ**
- musicxmlの拍子/音符数を参照し、近接小節の除去判定を弱く補助できるか試す。
- 既存結果と干渉しない独立スクリプトで実験。

**作業時間**
- 2025-12-31 01:40:00 JST

**実行内容**
- `tools/musicxml_density_filter.py` を新規作成（既存結果は参照のみ）。
- musicxmlからmeasure単位の拍子/音符数/休符数/総durationを抽出。
- core0.50後の候補をstaff行ごとに並べ、隣接間隔とmusicxmlの音符数で除去判定。
- 除去は「min_notes以上」「spacing比率<thr」「gap内notehead密度が低い」のみ。

**実行コマンド**
- `PYTHONPATH=. .venv_pdf/bin/python tools/musicxml_density_filter.py --run-tag 20251231T_musicxml_density_try`

**出力ログ**
- `logs/musicxml_density_filter/20251231T_musicxml_density_try/summary.json`
- `logs/musicxml_density_filter/20251231T_musicxml_density_try/page_XXX/pair_stats.json`
- `logs/musicxml_density_filter/20251231T_musicxml_density_try/page_XXX/fp_*.png`
- `logs/musicxml_density_filter/20251231T_musicxml_density_try/page_XXX/fn_*.png`

**集計（全ページ合算）**
- TP=451, FP=28, FN=23
- removed FP=2, new FN=12

**所見**
- 除去効果は小さく、FNが増加。簡易アラインでは十分に安全な条件になっていない。

## 2025-12-31 musicxml方式の改善（detections整列 + 弱い条件）

**作業目的 / 方針 / 位置づけ**
- homr detectionsのstaff_index/x順でmeasure順序を整列し、musicxml方式のアライン精度を改善。
- FN増加を抑えるため、除去条件を弱めた設定を試行。

**作業時間**
- 2025-12-31 02:10:00 JST

**実行内容**
- `--use-detections-align` を追加し、staff単位でdetections順を使用。
- 弱い条件（min_notes, notehead_density_max, ratio）を変更して再評価。

**実行コマンド**
- `PYTHONPATH=. .venv_pdf/bin/python tools/musicxml_density_filter.py --run-tag 20251231T_musicxml_density_align --use-detections-align`
- `PYTHONPATH=. .venv_pdf/bin/python tools/musicxml_density_filter.py --run-tag 20251231T_musicxml_density_align_weak1 --use-detections-align --ratio 0.25 --min-notes 12 --notehead-density-max 0.01`
- `PYTHONPATH=. .venv_pdf/bin/python tools/musicxml_density_filter.py --run-tag 20251231T_musicxml_density_align_weak2 --use-detections-align --ratio 0.25 --min-notes 16 --notehead-density-max 0.005`

**出力ログ**
- `logs/musicxml_density_filter/20251231T_musicxml_density_align/summary.json`
- `logs/musicxml_density_filter/20251231T_musicxml_density_align_weak1/summary.json`
- `logs/musicxml_density_filter/20251231T_musicxml_density_align_weak2/summary.json`

**集計（全ページ合算）**
- align (ratio0.30/min_notes8/density0.02): TP=451, FP=28, FN=23, removed FP=2, new FN=12
- weak1 (ratio0.25/min_notes12/density0.01): TP=457, FP=28, FN=17, removed FP=2, new FN=0
- weak2 (ratio0.25/min_notes16/density0.005): TP=457, FP=28, FN=17, removed FP=2, new FN=0

**所見**
- detections整列の有無で結果差は小さい。
- 弱い条件ではFN=0を維持しつつFPを2件除去できる可能性がある。

## 2025-12-31 probe scanの拡張判定（長い判定バー）実装

**作業目的 / 方針 / 位置づけ**
- stem-like FP対策として、probe scanの判定バーを長くし、全長ink ratioで除去する仕組みを追加。

**作業時間**
- 2025-12-31 01:35:00 JST

**実行内容**
- `detect_probe_scan`に拡張判定バー（extend_scale）と全長ink ratio（extend_max_ratio）を追加。
- CLIに `--probe-extend-scale` / `--probe-extend-max-ratio` を追加。

**所見**
- 実装のみ完了。評価は次工程で実施。

## 2025-12-31 probe scan拡張バーの評価（page_3含む）

**作業目的 / 方針 / 位置づけ**
- 伸長判定バー（extend_scale + extend_max_ratio）がstem-like FP削減に効くかを評価。
- page_3を含む5ページで評価。

**作業時間**
- 2025-12-31 01:50:00 JST

**実行内容**
- 既存条件に `--probe-extend-scale` / `--probe-extend-max-ratio` を追加して比較。
- page_3のマスクは `logs/homr_eval/baseline_for_hybrid/page_3/` を使用。
- baseline（extend_scale=1.0, extend_max_ratio=1.0）も作成。

**実行コマンド**
- baseline:  
  `PYTHONPATH=. .venv_pdf/bin/python tools/run_gt_rebuild_hybrid_eval.py --output-root logs/gt_rebuild_hybrid_eval/probe_extend_baseline --union-root logs/phase5b_confirmed_union_eval ... --probe-extend-scale 1.0 --probe-extend-max-ratio 1.0`
- sweep:  
  `... --output-root logs/gt_rebuild_hybrid_eval/probe_extend_s1.3_r0p90 --probe-extend-scale 1.3 --probe-extend-max-ratio 0.90`  
  `... --output-root logs/gt_rebuild_hybrid_eval/probe_extend_s1.6_r0p90 --probe-extend-scale 1.6 --probe-extend-max-ratio 0.90`  
  `... --output-root logs/gt_rebuild_hybrid_eval/probe_extend_s2.0_r0p90 --probe-extend-scale 2.0 --probe-extend-max-ratio 0.90`

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/probe_extend_baseline/summary_table.md`
- `logs/gt_rebuild_hybrid_eval/probe_extend_s1.3_r0p90/summary_table.md`
- `logs/gt_rebuild_hybrid_eval/probe_extend_s1.6_r0p90/summary_table.md`
- `logs/gt_rebuild_hybrid_eval/probe_extend_s2.0_r0p90/summary_table.md`

**集計（全ページ合算）**
- baseline: TP=606, FP=42, FN=2
- s1.3_r0p90: TP=604, FP=37, FN=4
- s1.6_r0p90: TP=606, FP=39, FN=2
- s2.0_r0p90: TP=606, FP=42, FN=2

**所見**
- extend_scale=1.6はFNを増やさずFPを3件削減（42→39）。
- extend_scale=1.3はFPをさらに削減するがFNが増加。

## 2025-12-31 page_3のFN=2の原因調査

**作業目的 / 方針 / 位置づけ**
- probe_extend評価で発生したpage_3のFN=2について、除去段階を特定する。

**作業時間**
- 2025-12-31 02:20:00 JST

**実行内容**
- `probe_extend_baseline/per_page/page_3/fn_boxes.json` を確認。
- row_filtered / end_recovered_* / geom_kept / clefs_keys_filter の各段階で該当boxが残るかを検証。

**結果**
- FNボックス:
  - [114, 537, 118, 555]
  - [116, 645, 120, 667]
- row_filteredには存在するが、geom_keptには残らない。
- geom_debugではoverlap_ratio=0.0で拒否されておらず、clefs_keys_filterで除外されている。
  - clefs_keys_filter rejected:
    - bbox [115, 536, 116, 557] overlap_ratio=0.9545 (>0.3)
    - bbox [118, 646, 119, 667] overlap_ratio=0.7727 (>0.3)

**所見**
- page_3のFN=2は clefs_keys フィルタによる除去が原因。

## 2025-12-31 clefs_keysの緩和でFN=0を回復

**作業目的 / 方針 / 位置づけ**
- page_3のFN=2を解消するため、clefs_keysの適用範囲（left_margin_ratio）を緩和。

**作業時間**
- 2025-12-31 02:40:00 JST

**実行内容**
- clefs_keys_left_margin_ratioを0.18/0.15で比較し、FN=0条件を探索。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/clefs_left_0p18_baseline/summary_table.md`
- `logs/gt_rebuild_hybrid_eval/clefs_left_0p15_baseline/summary_table.md`

**集計（全ページ合算）**
- left=0.18: TP=608, FP=42, FN=0
- left=0.15: TP=608, FP=65, FN=0

**所見**
- left=0.18でFN=0を維持しつつFPの増加なし（left=0.15はFP増）。
- 基準設定として clefs_keys_left_margin_ratio=0.18 を採用。

## 2025-12-31 probe extend再評価（clefs_keys緩和後）

**作業目的 / 方針 / 位置づけ**
- clefs_keys_left_margin_ratio=0.18 を基準に probe extend を再評価。

**作業時間**
- 2025-12-31 02:50:00 JST

**実行内容**
- baseline（extendなし）と extend_scale=1.6 / extend_max_ratio=0.90 を比較。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/clefs_left_0p18_baseline/summary_table.md`
- `logs/gt_rebuild_hybrid_eval/clefs_left_0p18_extend_s1.6_r0p90/summary_table.md`

**集計（全ページ合算）**
- baseline: TP=608, FP=42, FN=0
- extend_s1.6_r0p90: TP=608, FP=39, FN=0

**所見**
- FN=0を維持しつつFPを3件削減できたため、probe extendは有効。

## 2025-12-31 page_3の残存FP（clefs_left_0p18基準）

**作業目的 / 方針 / 位置づけ**
- page_3で残るFPの位置と性質を確認し、過去のFP=0条件との差分を特定するための材料整理。

**作業時間**
- 2025-12-31 03:05:00 JST

**確認内容**
- `clefs_left_0p18_baseline` と `clefs_left_0p18_extend_s1.6_r0p90` は同じFP（page_3=3件）。
- FP座標:
  - [335, 230, 336, 253]
  - [479, 449, 480, 469]
  - [132, 684, 136, 704]
- マスク重なり: barline/notes=1.0, notehead/stems_rest/symbols=0.0（clefs_keysは1件のみ0.124）。

**所見**
- page_3のFPはclefs_keysやnotehead由来ではなく、barline由来の細線候補。
- probe extendによる増減はなく、基準（clefs_left_0p18）時点で存在。

## 2025-12-31 core0.50適用後の残存FP再分類と可視化

**作業目的 / 方針 / 位置づけ**
- musicxml適用前（core0.50のみ適用）の残存FPを再分類し、原因調査に必要な可視化を作成。

**作業時間**
- 2025-12-31 01:15:00 JST

**実行内容**
- core0.50（clefs_keys内接コア）適用後の残存FPを抽出。
- homrマスク（symbols / stems_rest / notehead / clefs_keys / barline / notes）との重なり比率を計算。
- 全FPについてマスク重ね合わせ可視化（FPボックス付き）を生成。

**出力ログ**
- `logs/fp_reclass_core0p50/20251231T011423_var88_repro/summary.json`
- `logs/fp_reclass_core0p50/20251231T011423_var88_repro/page_001/`
- `logs/fp_reclass_core0p50/20251231T011423_var88_repro/page_004/`
- `logs/fp_reclass_core0p50/20251231T011423_var88_repro/page_10/`
- `logs/fp_reclass_core0p50/20251231T011423_var88_repro/page_15/`
 - `logs/fp_reclass_core0p50/20251231T011423_var88_repro/by_category/`
   - `page_XXX/{clefs_keys|notehead|stems_rest|symbols|barline_only}/`
 - `logs/fp_reclass_core0p50/20251231T011423_var88_repro/by_category/index.json`

**集計（全ページ合算）**
- 残存FP合計=31（page_001=12, page_004=5, page_10=4, page_15=10）
- mask_counts_ge_0p2:
  - symbols=1, stems_rest=14, notehead=2, clefs_keys=2, barline=31, notes=31

**所見**
- 残存FPはbarline/notesマスクに強く重なる（識別には使いにくい）。
- stems_restの重なりが比較的多い（14件）ため、局所的な追加フィルタ候補として再検討余地あり。


## 2025-12-31 endpoint mask拡張（案A/B）評価

**作業目的 / 方針 / 位置づけ**
- noteheadのみのendpoint判定に対し、notehead+stems（案A）とstems_rest単独（案B）を評価。
- clefs_left_0p18 + probe_extend_s1.6_r0p90 を基準設定として比較。

**作業時間**
- 2025-12-31 03:20:00 JST

**実行内容**
- `--endpoint-mask-mode notehead_stems`（案A）と `--endpoint-mask-mode stems_rest`（案B）を追加。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/clefs_left_0p18_extend_s1.6_r0p90_notehead_stems/summary_table.md`
- `logs/gt_rebuild_hybrid_eval/clefs_left_0p18_extend_s1.6_r0p90_stems_rest/summary_table.md`

**集計（全ページ合算）**
- baseline（notehead）: TP=608, FP=39, FN=0
- notehead_stems: TP=597, FP=39, FN=11
- stems_rest: TP=601, FP=39, FN=7

**所見**
- 案A/BはいずれもFNが増加（現状の閾値では不適）。

## 2025-12-31 案A/Bのendpoint ratio sweep（刻み増加）

**作業目的 / 方針 / 位置づけ**
- 案A（notehead_stems）/案B（stems_rest）のendpoint ratio閾値を細かい刻みでsweepし、FN増加なしでFP削減できるか検証。
- baselineは clefs_keys_left_margin_ratio=0.18 + probe extend (scale=1.6, max_ratio=0.90) を維持。

**作業時間**
- 2025-12-31 03:11:23 JST

**作業メモ**
- sweep範囲は 0.22〜0.40 を 0.02刻み（必要に応じて追加検証）。
- 初回実行は `--run-tag` が未対応でエラー。`--output-root` を各runで個別ディレクトリに変更して再実行する。
- sweep一括実行は120秒でタイムアウト。`20251231T031242_notehead_stems_thr0p22〜0p32` まで生成済み。残りは分割実行で継続。

**実行内容**
- 案A（notehead_stems）: 0.22〜0.40（0.02刻み）
- 案B（stems_rest）: 0.22〜0.40（0.02刻み）

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251231T031242_notehead_stems_thr0p22/` 〜 `..._thr0p40/`
- `logs/gt_rebuild_hybrid_eval/20251231T031242_stems_rest_thr0p22/` 〜 `..._thr0p40/`

**集計（全ページ合算）**
- 案A（notehead_stems）:
  - 0.22: TP=599 FP=48 FN=9
  - 0.24: TP=604 FP=112 FN=4
  - 0.26: TP=606 FP=279 FN=2
  - 0.28: TP=608 FP=341 FN=0
  - 0.30: TP=608 FP=344 FN=0
  - 0.32: TP=608 FP=352 FN=0
  - 0.34: TP=608 FP=384 FN=0
  - 0.36: TP=608 FP=394 FN=0
  - 0.38: TP=608 FP=404 FN=0
  - 0.40: TP=608 FP=421 FN=0
- 案B（stems_rest）:
  - 0.22: TP=601 FP=48 FN=7
  - 0.24: TP=605 FP=112 FN=3
  - 0.26: TP=606 FP=279 FN=2
  - 0.28: TP=608 FP=341 FN=0
  - 0.30: TP=608 FP=344 FN=0
  - 0.32: TP=608 FP=352 FN=0
  - 0.34: TP=608 FP=384 FN=0
  - 0.36: TP=608 FP=394 FN=0
  - 0.38: TP=608 FP=404 FN=0
  - 0.40: TP=608 FP=421 FN=0

**所見**
- FN=0は0.28以上で達成するが、FPが大幅増加（baseline FP=39に対して >300）。
- 0.22〜0.26はFPは低めだがFNが発生（FN=2〜9）。

## 2025-12-31 局所経常フィルタ候補（min_height_ratio / stem_outside_staff）の再評価

**作業目的 / 方針 / 位置づけ**
- 次のフィルタとして、既存実装の `barline_min_height_ratio` と `barline_stem_max_height_ratio` を全ページに適用し、
  FN=0維持 + page3のFP削減が可能かを確認。
- baselineは `clefs_keys_left_margin_ratio=0.18` + `barline_clefs_low` + `probe_extend` を維持。

**作業時間**
- 2025-12-31 03:53:51 JST

**実行内容**
- min_height_ratio（staffsマスク）: 0.02 / 0.03
- stem_outside_staff（staffsマスク）: max_height_ratio 0.04 / 0.06, min_band_cover 0.8

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251231T035351_minheight_staffs_r0p02/`
- `logs/gt_rebuild_hybrid_eval/20251231T035351_minheight_staffs_r0p03/`
- `logs/gt_rebuild_hybrid_eval/20251231T035351_stem_staffs_r0p04/`
- `logs/gt_rebuild_hybrid_eval/20251231T035351_stem_staffs_r0p06/`

**集計（全ページ合算）**
- min_height staffs r0.02: FN増（page_10 FN=2, page_15 FN=3）
- min_height staffs r0.03: ほぼ全ページで壊滅的FN
- stem staffs r0.04: baselineと同等（FP変化なし, FN=0）
- stem staffs r0.06: baselineと同等（FP変化なし, FN=0）

**所見**
- min_height_ratioはFN増加が避けられず不適。
- stem_outside_staff（staffs）はFP削減効果がなく、page3の残存FP（3件）は残る。

## 2025-12-31 probe scan拡張の上下ink ratio分離（実装）

**作業目的 / 方針 / 位置づけ**
- probe scanの拡張バーに対し、上はみ出し/下はみ出しのink ratioを別々に評価してstem-like FPを抑制できるか検証。
- 既存の `extend_scale`/`extend_max_ratio` に加え、上下の閾値を導入。

**作業時間**
- 2025-12-31 04:05:00 JST

**変更内容（作用機序）**
- 拡張バーを `top` / `bottom` に分割し、それぞれのink ratioを計算。
- `--probe-extend-top-max-ratio` / `--probe-extend-bottom-max-ratio` を追加。

**変更したファイル**
- `tools/run_gt_rebuild_hybrid_eval.py`



## 2025-12-31 probe scan上下ink ratioの試行

**作業目的 / 方針 / 位置づけ**
- 追加した上下ink ratio閾値で、FN=0を維持しながらFP削減できるか評価。

**作業時間**
- 2025-12-31 04:07:30 JST

**実行内容**
- `probe_extend_scale=1.6`, `probe_extend_max_ratio=0.90` は固定。
- 上下閾値: 0.25 / 0.35 / 0.50（top=bottom）。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251231T094531_probe_ext_tb0p25/`
- `logs/gt_rebuild_hybrid_eval/20251231T094531_probe_ext_tb0p35/`
- `logs/gt_rebuild_hybrid_eval/20251231T094531_probe_ext_tb0p50/`

**集計（全ページ合算）**
- tb0.25: FN増（page_001 FN=6, page_004 FN=4, page_15 FN=4）
- tb0.35: FN増（page_001 FN=1, page_004 FN=4, page_15 FN=1）
- tb0.50: FN増（page_001 FN=1, page_004 FN=1）

**所見**
- 上下ink ratioでの除去はFN増加を招き、現状のままでは採用不可。
- page3のFPは2件まで減るがFNが増えるため不採用。

## 2025-12-31 probe scan上下ink ratio可視化（debug）

**作業目的 / 方針 / 位置づけ**
- 上下のink ratio値と判定バー（band / ext_band）を可視化し、閾値の妥当性を目視検証できるようにする。

**作業時間**
- 2025-12-31 04:03:59 JST

**実行内容**
- `--endbar-debug` を有効化し、probe scanのdebug画像/JSON/クロップを出力。
- 例: `probe-extend-top-max-ratio=0.35`, `probe-extend-bottom-max-ratio=0.35`。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251231T100359_probe_ext_tb0p35_debug/`
  - `per_page/page_3/endbar_debug.png`
  - `per_page/page_3/endbar_debug.json`
  - `per_page/page_3/endbar_debug_crops/`

**補足**
- cropには band（黄）/top（シアン）/bottom（マゼンタ）枠と、ratio値が描画される。

## 2025-12-31 probe scanのFP/FN要因可視化（targeted crops）

**作業目的 / 方針 / 位置づけ**
- クロップ範囲が狭く判読しづらかったため、FP/FNに絞って拡大クロップを再生成。
- 「過去FPがどうなったか」「新規FNがどのような原因か」を追跡可能にする。

**作業時間**
- 2025-12-31 04:12:00 JST

**実行内容**
- baseline（20251231T034745）とprobe_ext_tb0p35_debugを比較。
- baseline FPを「kept/removed」に分類し、new FNを抽出。
- 各対象について 60px マージンの拡大クロップを生成し、probe scanのband/ext band/ratioを重ね描画。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251231T100359_probe_ext_tb0p35_debug/analysis_fp_fn_crops/`
  - `baseline_fp_removed/`
  - `baseline_fp_kept/`
  - `new_fn/`

## 2025-12-31 probe scan debugの再生成（staff band表示・拡大crop）

**作業目的 / 方針 / 位置づけ**
- staff bandとprobe bandのズレを確認できるよう、staff bandを可視化に追加。
- クロップ範囲拡大・文字はみ出し防止のため上部パディングを追加。

**作業時間**
- 2025-12-31 04:47:16 JST

**実行内容**
- debug JSONに `staff_band` を追加。
- targeted cropsで staff band（緑）/ probe band（黄）/ ext band（白）を描画。
- margin=120px, 上部パディング=24px。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251231T104716_probe_ext_tb0p35_debug/`
  - `per_page/page_3/endbar_debug.json`
  - `per_page/page_3/endbar_debug_crops/`
  - `analysis_fp_fn_crops/baseline_fp_removed/`
  - `analysis_fp_fn_crops/baseline_fp_kept/`
  - `analysis_fp_fn_crops/new_fn/`

## 2025-12-31 probe scan可視化の修正（pred band/色変更）

**作業目的 / 方針 / 位置づけ**
- staff bandがずれて見える問題への対応として、probe scan前の既存小節線（pred band）を可視化に採用。
- 背景白に対して視認性が低い色を変更。

**作業時間**
- 2025-12-31 05:01:47 JST

**変更内容**
- debug JSONに `pred_band`（既存小節線boxの上下端）を追加。
- 可視化色変更: pred band=緑 / probe band=青 / ext band=赤。
- targeted cropsは margin=120px, 上部パディング=30px に更新。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251231T110147_probe_ext_tb0p35_debug/`
  - `per_page/page_3/endbar_debug.json`
  - `per_page/page_3/endbar_debug_crops/`
  - `analysis_fp_fn_crops/baseline_fp_removed/`
  - `analysis_fp_fn_crops/baseline_fp_kept/`
  - `analysis_fp_fn_crops/new_fn/`

## 2025-12-31 probe scanのband定義とズレ原因の整理（調査）

**作業目的 / 方針 / 位置づけ**
- bandの定義と判定機序を明確化し、五線とのズレ原因を調査。

**作業時間**
- 2025-12-31 05:10:00 JST

**band定義 / 判定機序（現状）**
- staff band: `staff_mask` から抽出した staff_bands の (y1, y2)。probe scanの行分割の基準。
- probe band（band）: staff band中心に、`median_box` 高さ（同一band内の既存box高さ中央値）を当てて算出した (band_y1, band_y2)。
- ext band: probe band中心に `extend_scale` 倍の高さを持つ帯域（ext_y1, ext_y2）。
- pred band: probe scan前の既存box（geom_kept）から、同一staff band内かつ最も近いxのboxの上下端。
- 判定：probe band内でratioを計算し、ext band全体・上側・下側のink ratioを閾値判定。

**ズレ要因の仮説**
- staff band自体がstaffマスク由来で五線とズレる場合がある。
- probe bandは staff band中心 + median_box 高さなので、既存boxや五線位置とズレる可能性がある。
- ext bandも probe band中心で上下等分のため、五線の実上下と非対称にずれる。
- pred bandが表示されないのは、対象col付近で同一staff bandに既存boxが存在しないため。

**可視化対象の注意**
- page3はbaseline FPのみで新規FNが無いため、FPのクロップのみ表示される。

## 2025-12-31 staffmask非使用のbandモード（既存box由来）試行

**作業目的 / 方針 / 位置づけ**
- staffmaskのずれ対策として、既存小節線boxの上下端からbandを生成するモードを追加。

**作業時間**
- 2025-12-31 05:30:14 JST

**変更内容（作用機序）**
- `--probe-band-source existing_boxes` で staffmaskではなく既存boxのrow統計（top/bottom中央値）からbandを生成。
- band生成は `build_row_stats`（cluster_max_dist/min_row_count）に準拠。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251231T113014_probe_ext_tb0p35_boxesband_debug/`
  - `per_page/page_3/endbar_debug.json`
  - `analysis_fp_fn_crops/baseline_fp_removed/`
  - `analysis_fp_fn_crops/baseline_fp_kept/`
  - `analysis_fp_fn_crops/new_fn/`

## 2025-12-31 probe scan bandの水平スキャン（horiz_scan）試行

**作業目的 / 方針 / 位置づけ**
- staffmaskのズレ回避のため、列方向（xごと）に水平スキャンで五線帯域を推定するモードを追加。

**作業時間**
- 2025-12-31 05:45:43 JST

**変更内容（作用機序）**
- `--probe-band-source horiz_scan` を追加。
- 既存box由来の粗いband（row_stats）内で、x位置の左右幅 `probe-band-scan-width` のink率を計算し、
  一定比率以上の行をstaff line候補として抽出。
- 抽出行の上端/下端をscan bandとして使用し、ext bandをscan band中心に拡張。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251231T114543_probe_ext_tb0p35_hscan_debug/`
  - `per_page/page_3/endbar_debug.json`
  - `analysis_fp_fn_crops/baseline_fp_removed/`
  - `analysis_fp_fn_crops/baseline_fp_kept/`
  - `analysis_fp_fn_crops/new_fn/`

## 2025-12-31 horiz_scanの粗band拡張（scan pad）

**作業目的 / 方針 / 位置づけ**
- 既存box由来の粗bandが狭く、scan bandがずれる問題への対処として上下に拡張して再スキャン。

**作業時間**
- 2025-12-31 05:52:59 JST

**変更内容**
- `--probe-band-scan-pad` を追加（粗bandの上下拡張幅）。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251231T115259_probe_ext_tb0p35_hscan_pad20_debug/`
  - `per_page/page_3/endbar_debug.json`
  - `analysis_fp_fn_crops/baseline_fp_removed/`
  - `analysis_fp_fn_crops/baseline_fp_kept/`
  - `analysis_fp_fn_crops/new_fn/`

## 2025-12-31 horiz_scanのpad比率化＋段全体ink ratioログ

**作業目的 / 方針 / 位置づけ**
- 解像度差に耐えるため、scan padをpxではなく比率で指定。
- 段全体（scan base band）でのink ratio統計をログ化し、不合理値の原因確認に備える。

**作業時間**
- 2025-12-31 06:23:26 JST

**変更内容**
- `--probe-band-scan-pad-ratio` を追加（粗band高さに対する比率）。
- scan base bandの row_ratio_mean / row_ratio_max / row_ratio_lines をdebug記録。
- scan_top_h / scan_bottom_h をdebug記録。
- debug cropに scan base band（黄）、scan band（橙）、scan ext band（紫）を描画。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251231T122326_probe_ext_tb0p35_hscan_padR0p50_debug/`
  - `per_page/page_3/endbar_debug.json`
  - `analysis_fp_fn_crops/baseline_fp_removed/`
  - `analysis_fp_fn_crops/baseline_fp_kept/`
  - `analysis_fp_fn_crops/new_fn/`

**調査メモ（page_004_fn05）**
- FN box: [2101, 791, 2105, 874]
- baseline geom近傍: IoU=0.48（[2100, 807, 2104, 889]）
- debug status: `scan_ratio_low`（scan_ratio=0.76 < min_ratio=0.80）
- scan_base_band=[762, 929], scan_band=[802, 888], scan_top_h=26, scan_bottom_h=26

## 2025-12-31 horiz_scanのline_ratio/min_lines強化（ズレ抑制）

**作業目的 / 方針 / 位置づけ**
- 五線外の線を拾ってしまう問題への対処として、line_ratioを引き上げ、min_linesを5に固定。
- scan bandの抽出は「最小スパンの5ライン窓」を選択するよう改善。

**作業時間**
- 2025-12-31 06:33:52 JST

**変更内容**
- `scan_staff_band_from_ink` で最小スパンの `min_lines` 窓を選択するよう変更。
- scan padは比率指定（pad_ratio=0.5）で維持。
- line_ratio=0.6, min_lines=5 で再実行。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251231T123352_probe_ext_tb0p35_hscan_padR0p50_lr0p60_ml5_debug/`
  - `per_page/page_3/endbar_debug.json`
  - `analysis_fp_fn_crops/baseline_fp_removed/`
  - `analysis_fp_fn_crops/baseline_fp_kept/`
  - `analysis_fp_fn_crops/new_fn/`

## 2025-12-31 row filter bandの可視化拡張（predsモード）

**作業目的 / 方針 / 位置づけ**
- row filterがstaff bandと同じかを確認するため、predsモードでもrow bandを可視化。

**作業時間**
- 2025-12-31 06:40:00 JST

**変更内容**
- `--row-band-debug` 時、staff bandが無い場合は `build_row_stats` のtop/bottomで帯域を描画。

**出力ログ（再実行時に生成）**
- `per_page/<page>/row_band_debug.png`

## 2025-12-31 row band可視化付きの再実行

**作業目的 / 方針 / 位置づけ**
- row filterが参照する帯域（preds由来）を可視化し、scan bandとの整合性を確認。

**作業時間**
- 2025-12-31 14:07:56 JST

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251231T140756_probe_ext_tb0p35_hscan_padR0p50_lr0p60_ml5_debug_rowband/`
  - `per_page/<page>/row_band_debug.png`
  - `analysis_fp_fn_crops/baseline_fp_removed/`
  - `analysis_fp_fn_crops/baseline_fp_kept/`
  - `analysis_fp_fn_crops/new_fn/`

## 2025-12-31 row_stats基準のprobe bandモード試行

**作業目的 / 方針 / 位置づけ**
- row band（preds由来）をprobe band基準として活用するモードを追加し評価。

**作業時間**
- 2025-12-31 14:24:33 JST

**変更内容**
- `--probe-band-source row_stats` を追加（row_filterのrow_statsをbandとして利用）。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251231T142433_probe_ext_tb0p35_rowstats_hscan_padR0p50_lr0p60_ml5_debug_rowband/`
  - `per_page/<page>/row_band_debug.png`
  - `analysis_fp_fn_crops/baseline_fp_removed/`
  - `analysis_fp_fn_crops/baseline_fp_kept/`
  - `analysis_fp_fn_crops/new_fn/`

## 2025-12-31 row_stats band固定のprobe band試行

**作業目的 / 方針 / 位置づけ**
- row_stats bandが正確であるため、probe bandをrow_stats bandに固定して再評価。

**作業時間**
- 2025-12-31 15:08:40 JST

**変更内容**
- `probe-band-source=row_stats` の場合、probe bandをrow_statsのtop/bottomそのままに固定。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251231T150840_probe_ext_tb0p35_rowstats_hscan_padR0p50_lr0p60_ml5_debug_rowband/`
  - `per_page/<page>/row_band_debug.png`
  - `analysis_fp_fn_crops/baseline_fp_removed/`
  - `analysis_fp_fn_crops/baseline_fp_kept/`
  - `analysis_fp_fn_crops/new_fn/`

## 2025-12-31 row_stats bandの上下パディング追加（比率/スタッフ空間）

**作業目的 / 方針 / 位置づけ**
- row_stats bandが内側に寄る問題への対処として、上下パディングを導入。
- 比率指定と staff_space 倍率指定の両方式を追加し、sweepで評価する。

**作業時間**
- 2025-12-31 15:20:00 JST

**変更内容**
- `--probe-band-row-pad-ratio` を追加（row_stats band 高さに対する比率）。
- `--probe-band-row-pad-staff-mult` を追加（staff_space 倍率）。

## 2025-12-31 scan GUIの下準備（row profile保存 + GUI追加）

**作業目的 / 方針 / 位置づけ**
- GUIで横向きのinkratio分布を確認できるように、scan row profileを保存し可視化画面を追加。

**作業時間**
- 2025-12-31 15:45:29 JST

**変更内容**
- `--probe-debug-save-row-profile` を追加し、scan_row_profile を `endbar_debug.json` に保存。
- GUIヘルパに `/scan` を追加し、クリックしたrecordのrow profileを描画。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251231T154529_probe_ext_tb0p35_rowstats_hscan_padR0p50_lr0p60_ml5_debug_rowband_profile/`
  - `per_page/page_001/endbar_debug.json`

## 2025-12-31 GUIエラー回避（missing metrics）

**作業目的 / 方針 / 位置づけ**
- GUI起動時に既存metricsが無い場合でも `/scan` に到達できるように修正。

**作業時間**
- 2025-12-31 15:50:00 JST

**変更内容**
- `tools/gui_helper/app.py` の `/` でMETRICSが無い場合は空の画面を表示（warning付き）。

**追加対応**
- METRICSが無い場合でも、`SCAN_PATH` が存在すれば `/scan` の画面を表示するように変更。

**出力ログ**
- `logs/gt_rebuild_hybrid_eval/20251231T152500_rowband_pad_sweep/`
  - `rowpad_ratio0p05/`
  - `rowpad_ratio0p10/`
  - `rowpad_ratio0p15/`
  - `rowpad_staff0p5/`
  - `rowpad_staff1p0/`
  - `rowpad_staff1p5/`

**集計（全ページ合算）**
- rowpad_ratio0p05: TP=605 FP=7 FN=3
- rowpad_ratio0p10: TP=605 FP=6 FN=3
- rowpad_ratio0p15: TP=573 FP=4 FN=35
- rowpad_staff0p5: TP=568 FP=2 FN=40
- rowpad_staff1p0: TP=568 FP=2 FN=40
- rowpad_staff1p5: TP=568 FP=2 FN=40

**所見**
- ratio 0.05/0.10 はFN=3まで減少するがFN=0には届かない。
- staff_space倍率はFN増が大きく不適。

## 2025-12-31 page_001のrow band内側ずれの原因調査

**作業目的 / 方針 / 位置づけ**
- row_stats bandが五線内側に入る原因を特定し、FN発生の原因を確認する。

**作業時間**
- 2025-12-31 15:20:00 JST

**調査内容**
- page_001のfn00 box: `[1005, 1701, 1009, 1790]`
- debug record: band/staff_band `[1709, 1787]`、pred_band `[1709, 1788]`
- row_filteredから再計算したrow_stats: top/bottom が **1709/1787.5**（同一行のmin/med/maxがほぼ同値）

**所見**
- row_stats bandが「検出boxの高さ中央値」に依存しているため、当該行の検出が短いと band が五線内側に入る。
- その結果、ext top 側の ratio が上がり `extended_top_ratio` によりFNが生じる。
