---
## Phase 6 completed; see NEXT_SESSION_NOTES.md for confirmed outcomes

This log has been cleaned to retain only confirmed Phase 6 results and references.

---
## Phase 6 confirmed outcomes

- Detector-miss total: 35 (page_10=9, page_15=15, page_001=1, page_004=10)
  - Source: `logs/phase5b/trace_stage_analysis/20251221T222504/fn_trace_table.csv`
- GT cleanup completed for all 35 detector-miss items; post-GT recheck:
  - resolved=25, remaining_miss=10, total=35
  - Summary: `logs/phase6_detector_miss/gt_fix_review_full/near_hit_recheck/near_hit_recheck_summary.json`
- Remaining true detector-miss list + categories:
  - `logs/phase6_detector_miss/gt_fix_review_full/POST_GT_RECHECK_SUMMARY.md`

---
## Remaining true detector-miss cases (detector-side work)

- page_004 fn_000 (end_barline)
- page_004 fn_003 (text_dynamic_overlap)
- page_004 fn_005 (dense_chord_accidental)
- page_004 fn_008 (text_dynamic_overlap)
- page_004 fn_011 (double_or_repeat_bar)
- page_10 fn_000 (end_barline)
- page_15 fn_003 (text_dynamic_overlap)
- page_15 fn_007 (notehead_overlap)
- page_15 fn_010 (dense_chord_accidental)
- page_15 fn_021 (double_or_repeat_bar)

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
- `logs/homr_eval/20251229T_endbar3_page004/`
  - end barline recovery 追加: 2件
  - FN回復: 0（TP=0, FP=172, FN=12）
  - overlay: `logs/homr_eval/20251229T_endbar3_page004/page_004/page_004_barline_overlay.png`
- `logs/homr_eval/20251229T_endbar3_page10/`
  - end barline recovery 追加: 0件
  - FN回復: 0（TP=17, FP=216, FN=7）
  - overlay: `logs/homr_eval/20251229T_endbar3_page10/page_10/page_10_barline_overlay.png`
- `logs/homr_eval/20251229T_endbar3_page3_guard/`
  - end barline recovery 追加: 3件
  - 回帰ガード: FPが +1（TP=152, FP=31, FN=0）
  - overlay: `logs/homr_eval/20251229T_endbar3_page3_guard/page_3/page_3_barline_overlay.png`

---
## 2025-12-29 GT候補比較用 overlay（promiscuous_union filtered）

**作業目的 / 方針 / 位置づけ**
- 未ソートGTが不明なため、Phase 5b の promiscuous_union + row filter 出力を基準に、
  `fn_only.json` と `fn_only_corrected.json` を色分けで重ねて目視比較。

**作業時間**
- 2025-12-29 01:15 JST 前後

**変更したファイル（概要のみ）**
- 変更なし（overlay生成のみ）

**試した結果（出力ディレクトリのみ）**
- `logs/phase6_detector_miss/remaining_fn_overlays/20251229T_promiscuous_union_overlay_check/`
  - `page_001_pred_vs_fn_only.png` / `page_001_pred_vs_fn_only_corrected.png`
  - `page_004_pred_vs_fn_only.png` / `page_004_pred_vs_fn_only_corrected.png`
  - `page_10_pred_vs_fn_only.png` / `page_10_pred_vs_fn_only_corrected.png`
  - `page_15_pred_vs_fn_only.png` / `page_15_pred_vs_fn_only_corrected.png`

---
## 2025-12-29 GT再構築用ブラウザツール改修

**作業目的 / 方針 / 位置づけ**
- 未ソートGTが不明なため、既存bboxの読み込み・削除・追加・ズーム/パンを備えたブラウザツールを追加。
- 現行 `coordinate_annotator.py` は LEGACY と明示し、新ツールを推奨。

**作業時間**
- 2025-12-29 01:00 JST 以降

**変更したファイル（概要のみ）**
- `tools/gt_relabel_gui/server.py` / `tools/gt_relabel_gui/index_gt.html` / `tools/gt_relabel_gui/app_gt.js`
- `logs/phase6_detector_miss/gt_rebuild/gt_editor_config.json`
- `docs/ENVIRONMENTS.md` / `data/README.md` / `tools/coordinate_annotator.py`

**試した結果（出力ディレクトリのみ）**
- ツールの配置と設定ファイル作成まで完了（ブラウザ起動・手動確認はこれから）

---
## 2025-12-29 GT再構築ツールのUI改善

**作業目的 / 方針 / 位置づけ**
- GT再構築ツールの操作性改善（選択の視認性、削除反映、タイプ付与、凡例）。

**作業時間**
- 2025-12-29 02:00 JST 前後

**変更したファイル（概要のみ）**
- `tools/gt_relabel_gui/app_gt.js`
- `tools/gt_relabel_gui/index_gt.html`
- `tools/gt_relabel_gui/server.py`

**試した結果（出力ディレクトリのみ）**
- 未確認（ブラウザでの動作確認待ち）

---
## 2025-12-29 GT再整備完了（保存 & 配置）

**作業目的 / 方針 / 位置づけ**
- ページ001/004/10/15 のGTを再作成し、今後再編集できる形で保存。
- dataディレクトリに日付付きでコピーして再利用可能にする。

**作業時間**
- 2025-12-29 02:30 JST 前後

**変更したファイル（概要のみ）**
- `logs/phase6_detector_miss/gt_rebuild/page_001_raw.json`
- `logs/phase6_detector_miss/gt_rebuild/page_001_boxes_sorted.json`
- `logs/phase6_detector_miss/gt_rebuild/page_004_raw.json`
- `logs/phase6_detector_miss/gt_rebuild/page_004_boxes_sorted.json`
- `logs/phase6_detector_miss/gt_rebuild/page_10_raw.json`
- `logs/phase6_detector_miss/gt_rebuild/page_10_boxes_sorted.json`
- `logs/phase6_detector_miss/gt_rebuild/page_15_raw.json`
- `logs/phase6_detector_miss/gt_rebuild/page_15_boxes_sorted.json`
- `data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/raw_boxes_v20251229.json`
- `data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/boxes_sorted_v20251229.json`
- `data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/raw_boxes_v20251229.json`
- `data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/boxes_sorted_v20251229.json`
- `data/training/annotations/page_010/raw_boxes_v20251229.json`
- `data/training/annotations/page_010/boxes_sorted_v20251229.json`
- `data/training/annotations/page_015/raw_boxes_v20251229.json`
- `data/training/annotations/page_015/boxes_sorted_v20251229.json`

**試した結果（出力ディレクトリのみ）**
- `logs/phase6_detector_miss/gt_rebuild/`

**メモ**
- ページ切り替え時に未保存の手描きbboxがリセットされる挙動あり（保存済みのページは問題なし）。
- 再編集用の設定は `logs/phase6_detector_miss/gt_rebuild/gt_editor_config.json` を更新（editable=gt_rebuild / reference=fn_only_corrected）。

---
## 2025-12-29 新GTでの再評価（homr evaluator）

**作業目的 / 方針 / 位置づけ**
- GT再整備後の再評価で、真に対処すべきFN/FPを再確認する。

**作業時間**
- 2025-12-29 04:06 JST 前後

**変更したファイル（概要のみ）**
- 変更なし（評価ログ生成のみ）

**試した結果（出力ディレクトリのみ）**
- `logs/homr_eval/20251229T_gt_rebuild_eval/`
  - page_001: TP=73 FP=30 FN=12
  - page_004: TP=99 FP=71 FN=20
  - page_10: TP=152 FP=85 FN=6
  - page_15: TP=105 FP=47 FN=7
  - aggregate: TP=429 FP=233 FN=45 (Precision=0.6480 / Recall=0.9051 / F1=0.7553)

---
## 2025-12-29 GT可視化/編集ツールの改善（FN可視化・重複削除・自動保存）

**作業目的 / 方針 / 位置づけ**
- FNが見えるオーバーレイを作成し、改善対象の確認を容易にする。
- GTエディタで近接重複の削除支援とページ切替時の自動保存を追加する。

**作業時間**
- 2025-12-29 04:20 JST 前後

**前提 / 仮定**
- 近接重複は x中心差 <= 3px かつ縦方向重なり率 >= 0.7 を重複として扱う。
- 重複検出時は高さが小さい方を削除対象とする。
- ページ切替時は自動で保存してから切り替える（未保存保持より再現性優先）。
- homr_evalログ配下への書き込み権限が無い可能性があるため、FN/TP/FPオーバーレイは `logs_user/` に出力する。

**変更したファイル（概要のみ）**
- `tools/gt_relabel_gui/index_gt.html`（Auto Dedupボタン/dirty表示）
- `tools/gt_relabel_gui/app_gt.js`（dirty追跡/自動保存/近接重複削除）
- `tools/render_detection_quality_overlay.py`（--image-key対応で複数ページのmetricsに対応）

**試した結果（出力ディレクトリのみ）**
- `logs/gt_rebuild_eval_overlays/`
  - `page_001_detection_quality.png`
  - `page_004_detection_quality.png`
  - `page_10_detection_quality.png`
  - `page_15_detection_quality.png`

---
## 2025-12-29 GT再整備後の再評価（hybrid + row + notehead filter）

**作業目的 / 方針 / 位置づけ**
- GT再整備後に、hybrid( homr + omr-dln union ) + row filter + notehead filter を適用した結果で再評価。

**作業時間**
- 2025-12-29 04:40 JST 前後

**前提 / 仮定**
- hybrid 予測は `logs/phase5b_confirmed_union_eval/*_hybrid_preds.json` を使用。
- notehead mask は `logs/homr_eval/20251229T_gt_rebuild_eval/<page>/*_debug_6_notehead.png` を使用。
- notehead filter は page_3 成功時の ratio 近傍を採用（endpoint_ratio_threshold=0.04, x_scale=0.12, y_scale=0.8）。
- 出力先は権限の都合で `logs_user/` に統一。

**変更したファイル（概要のみ）**
- `tools/run_gt_rebuild_hybrid_eval.py`

**試した結果（出力ディレクトリのみ）**
- `logs/gt_rebuild_hybrid_eval/20251229T_hybrid_row_notehead_v1/`
  - summary_table.md
  - overlays/page_001_tp_fp_fn.png
  - overlays/page_004_tp_fp_fn.png
  - overlays/page_10_tp_fp_fn.png
  - overlays/page_15_tp_fp_fn.png
  - per_page/<page>/metrics.json

**結果（summary_table）**
- page_001: TP=68 FP=0 FN=17
- page_004: TP=97 FP=0 FN=22
- page_10: TP=150 FP=0 FN=8
- page_15: TP=103 FP=2 FN=9

---
## 2025-12-29 GT更新後の再評価（v2）とログ整理

**作業目的 / 方針 / 位置づけ**
- page_15 のGT追加後、hybrid + row + notehead filter を再評価。
- FNオーバーレイ色の視認性改善、FP crop 出力、ログの `logs/` 集約。
- 再実行手順をスクリプト化。

**作業時間**
- 2025-12-29 05:10 JST 前後

**前提 / 仮定**
- GTは `logs/phase6_detector_miss/gt_rebuild/*_boxes_sorted.json` を最新として使用。
- FN色はマゼンタで視認性を優先。
- 既存ログを `logs_user/` から `logs/` に移動できる範囲で実施。

**変更したファイル（概要のみ）**
- `tools/run_gt_rebuild_hybrid_eval.py`（FN色変更、FP crop 出力、GT参照パス更新）
- `tools/render_detection_quality_overlay.py`（FN色変更）
- `tools/run_gt_rebuild_hybrid_eval.sh`（再評価の簡易実行）

**試した結果（出力ディレクトリのみ）**
- `logs/gt_rebuild_eval_overlays/`（FN色更新）
- `logs/gt_rebuild_hybrid_eval/20251229T_hybrid_row_notehead_v2/`
  - summary_table.md
  - overlays/page_001_tp_fp_fn.png
  - overlays/page_004_tp_fp_fn.png
  - overlays/page_10_tp_fp_fn.png
  - overlays/page_15_tp_fp_fn.png
  - per_page/<page>/metrics.json
  - per_page/<page>/fp_crops/ (FPがあれば保存)

**結果（summary_table v2）**
- page_001: TP=64 FP=0 FN=14
- page_004: TP=97 FP=0 FN=15
- page_10: TP=150 FP=0 FN=4
- page_15: TP=105 FP=0 FN=7

**メモ**
- `logs_user/gt_rebuild_hybrid_eval/20251229T_hybrid_row_notehead` → `logs/gt_rebuild_hybrid_eval/20251229T_hybrid_row_notehead_v1` に移動。
