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
## 2025-12-29 GT再構築ツールのtype追加

**作業目的 / 方針 / 位置づけ**
- type に double_barline を追加し、二重線を1本のbboxで記録可能にする。

**作業時間**
- 2025-12-29 02:20 JST 前後

**変更したファイル（概要のみ）**
- `tools/gt_relabel_gui/index_gt.html`

**試した結果（出力ディレクトリのみ）**
- 未確認（ブラウザでの動作確認待ち）

---
## 2025-12-29 GT再構築ツールの編集対象拡張

**作業目的 / 方針 / 位置づけ**
- fn_only / fn_only_corrected 由来のbboxも編集可能にし、由来ごとの色・凡例を表示。

**作業時間**
- 2025-12-29 02:10 JST 前後

**変更したファイル（概要のみ）**
- `tools/gt_relabel_gui/app_gt.js`
- `logs/phase6_detector_miss/gt_rebuild/gt_editor_config.json`

**試した結果（出力ディレクトリのみ）**
- 未確認（ブラウザでの動作確認待ち）
