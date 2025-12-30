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
