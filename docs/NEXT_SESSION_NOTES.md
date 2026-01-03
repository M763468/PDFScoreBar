# Next Session Notes

**Last Updated**: 2025-12-30
**Current Phase**: Post‑Phase 6 → start detector‑side FN analysis (remaining 10)

---
### Note for AI Assistant (Operational Rule)
- The `docs/SESSION_LOG.md` file must **not** be completely overwritten. During a session, new findings and logs should be appended, or only relevant sections should be edited. The file should only be cleared with explicit user permission.
---

## Current Starting Point (Confirmed)
- GT cleanup completed for all 35 detector-miss items.
- Post-GT recheck: resolved=25, remaining true detector-miss=10 (total=35).
  - Summary: `logs/phase6_detector_miss/gt_fix_review_full/near_hit_recheck/near_hit_recheck_summary.json`
  - Remaining list + categories: `logs/phase6_detector_miss/gt_fix_review_full/POST_GT_RECHECK_SUMMARY.md`
- Merge / filter / GT are closed for the remaining 10 cases; next session begins detector-side work on these items.

### Short-term plan (next actions)
- **Current baseline:** var88（clefs_keys left + probe_notehead_dilate=13 + notehead_dilate=7, FN=0維持）.
- **Next focus:** FP起因（clef/time/rest/accidental/stem）の整理と追加マスク/フィルタの検討.
- **Plan:**
  - homr出力から追加マスク可能性を再調査（symbols等の信頼度含む）.
  - 新フィルタ設計→var派生評価（FN=0維持を最優先）.
  - 成果はlogs/で比較し、最終採用のみNEXT_SESSION_NOTESに残す.

### Reproducibility rules (must record)
- Baseline /採用結果は **commit hash + 再現コマンド + 出力パス** を必ず記載。
- `probe_row_filter_mode` / `probe_endpoint_x_scale` など暗黙に効くパラメータは **明示指定** する。
- `union_root` / GT / masks のパスが正しいか、再実行前に再確認する。

## Recent Updates (2025-12-29,30)
- GT再整備完了（page_001 / page_004 / page_10 / page_15）。
  - Logs: `logs/phase6_detector_miss/gt_rebuild/`
  - Data copies: `data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/*_v20251229.json`,
    `data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/*_v20251229.json`,
    `data/training/annotations/page_010/*_v20251229.json`,
    `data/training/annotations/page_015/*_v20251229.json`
- GTエディタの再編集用設定は `logs/phase6_detector_miss/gt_rebuild/gt_editor_config.json`
  - editable source は `gt_rebuild`（再編集時はここから再開）
  - reference は `fn_only_corrected` のみ
- 既知のUI挙動: ページ切り替え時に未保存の手描きbboxがリセットされる（保存後なら問題なし）
- 新GT再評価ログ: `logs/homr_eval/20251229T_gt_rebuild_eval/`
  - page_001: TP=73 FP=30 FN=12
  - page_004: TP=99 FP=71 FN=20
  - page_10: TP=152 FP=85 FN=6
  - page_15: TP=105 FP=47 FN=7
  - aggregate: TP=429 FP=233 FN=45 (P=0.6480 / R=0.9051 / F1=0.7553)

- FP削減の現行ベースは `var88`（clefs_keys左端フィルタ + probe_notehead_dilate=13 + notehead_dilate=7）。
  - Logs: `logs/gt_rebuild_hybrid_eval/20251230T_hybrid_row_notehead_endbar/var88_clef_filter/`
  - Overlays: `logs/gt_rebuild_hybrid_eval/20251230T_hybrid_row_notehead_endbar/var88_clef_filter/overlays/`
  - Repro (commit `f41fa96c9bd7d73201913001ac592e50ce625e3c`):
    - Output: `logs/gt_rebuild_hybrid_eval/repro_var88_from_logs_reuse_rows_probe_eps/`
    - `.venv_pdf/bin/python tools/run_gt_rebuild_hybrid_eval.py --output-root logs/gt_rebuild_hybrid_eval/repro_var88_from_logs_reuse_rows_probe_eps --union-root logs/phase5b_confirmed_union_eval --endpoint-ratio-threshold 0.20 --endpoint-x-scale 0.14 --endpoint-y-scale 0.80 --notehead-open-kernel 5 --notehead-min-area 20 --notehead-dilate 7 --notehead-max-aspect 2.0 --notehead-min-height 10 --notehead-max-width 6 --filter-clefs-keys --clefs-keys-dilate 3 --clefs-keys-left-margin-ratio 0.20 --clefs-keys-overlap-min 0.30 --enable-end-barline-recovery --endbar-method probe_scan --endbar-staff-mask-mode staff --probe-width 3 --probe-ink-threshold 180 --probe-min-ratio 0.80 --probe-min-peak-distance 2 --probe-max-per-band 0 --probe-refine-window 4 --probe-band-height-mode median_box --probe-band-height-scale 1.0 --probe-band-height-min 10 --probe-notehead-dilate 13 --probe-row-filter-mode reuse_rows --probe-endpoint-x-scale 0.04 --probe-endpoint-y-scale 0.80`
- clefs_keys全域/2ゾーン適用はFN増加で不採用（var89-98 / var109-111）。
  - 比較用crop: `logs/gt_rebuild_hybrid_eval/20251230T_hybrid_row_notehead_endbar/var90_clef_full_0p30/clefs_keys_fp_fn_crops/`
  - 比較用crop: `logs/gt_rebuild_hybrid_eval/20251230T_hybrid_row_notehead_endbar/var105_clefshape_aspect2/clefs_keys_fp_fn_crops/`
  - 差分overlay: `logs/gt_rebuild_hybrid_eval/20251230T_hybrid_row_notehead_endbar/var95_clef_twozone/overlays_diff_vs_var88/`
  - 差分overlay: `logs/gt_rebuild_hybrid_eval/20251230T_hybrid_row_notehead_endbar/var101_minheight_0p70/overlays_diff_vs_var88/`
- GT再編集は `logs/phase6_detector_miss/gt_rebuild/gt_editor_config.json` から再開可能（保存後の手描きbboxは保持、ページ切替時の未保存分はリセットされる点に注意）。
- probe_scanの有効性確認:
  - var16でink_ratio可視化を実施しピーク検出の有効性を確認（`logs/gt_probe_ratio/20251229T_probe_ratio_var16/` 系）。
  - var25で **FN=0**（`max_per_band=0`, `min_peak_distance=2`）を達成（`logs/gt_rebuild_hybrid_eval/20251229T_hybrid_row_notehead_endbar/var25/`）。
- notehead maskはダブルバー誤検出が原因でFNを生むため、aspectフィルタ適用が必須。
- clefs_keysは左端のみ有効で、中央適用はFN増加のため不採用。

## Unmerged Session Notes (From SESSION_LOG)
## 2026-01-02 LLMまとめと今後の方針
### 1. Gemini評価のまとめ
- 2段まとめ + Gemini-Flash (初期): FP hit 4/8, TP false 4。
- 1段分割 + Gemini-3 Flash (strict prompt): FP hit 6/8, TP false 10。
- 確定TP(緑)を手本にしたLR分割 + notehead縦マージン拡張 + Gemini-3 Flash:
  - 残り候補 21件、緑=170件。
  - 途中でクォータ上限により4セグメント未取得。
  - 取得済み分では FP hit 1/8, TP false 2 (暫定)。
- LLMはFPを拾えるが、TP誤判定が残り、安定的な自動除去には不十分。

### 2. 確定TP集合の方針
- FP=0の中間結果として `20251231T_row_ink_profile_baseline` を採用可能。
  - per_page metrics: page_001/004/10/15/3 がすべて FP=0 (FNは残る)。
  - このgeom_keptを「確定TP」として除外し、残りのみLLM判定に回す構成が有望。

### 3. 今後の検討方針 (候補)
A) LLMはレビュー用途に限定
- FP候補をさらに絞り込んで人手確認 or LLM確認数を最小化。
- 例: 1段→左右分割＋notehead縦パディング、タイル化してAPI回数削減。

B) 非LLMの信頼度再スコアリング強化
- notehead/stem/clef mask距離・交差率の追加特徴。
- staff band内の縦連続性/インク率を使ったスコアリング。
- 確定TP集合との差分を「疑義候補」として順位付け。

C) LLM利用時の工夫
- 画像あたりの候補数を絞り、最終的なFP候補だけ送る。
- 確定TP(緑)を手本に残す方式は継続候補。
- 可能なら1画像にタイル化してリクエスト数削減。

D) pipeline側の改善
- FP=0の中間結果で確定TPを固定し、残りだけをprobe scan/後段へ。
- row_filtered + notehead filterを通過した部分は安全集合として扱う運用を検討。

## 2026-01-02 Gemini 1.5 Flash System-Level Review with CoT+Rescue Prompt
- **Purpose**: Test if adding a "Rescue" logic to the Chain-of-Thought prompt prevents False Negatives (TP marked as False) observed in strict mode.
- **Method**:
  - Used `temp_review_images/prompt_cot_rescue.txt` with `gemini-1.5-flash-latest`.
  - Tested on `system_06_L` (contains FP id 171) and `system_03_L` (contains TP id 168).
- **Results**:
  - `system_06_L` (FP id 171): Marked as **TRUE** (False Positive).
    - Reason: "Straight, vertical line... positioned at expected measure boundary... not attached to any note symbol".
    - Regression from strict mode which correctly rejected it.
  - `system_03_L` (TP id 168): Marked as **TRUE** (True Positive).
    - Reason: "Straight, vertical line... matches style of surrounding confirmed barlines...".
    - Improvement from strict mode which incorrectly rejected it.
- **Conclusion**:
  - The "Rescue" logic successfully fixed the False Negative (TP 168 is now True).
  - However, it swung too far and accepted the False Positive (FP 171 is now True).
  - Gemini 1.5 Flash appears to struggle with distinguishing subtle visual artifacts (slight slant/thinness) when the prompt encourages acceptance based on alignment/spacing context.