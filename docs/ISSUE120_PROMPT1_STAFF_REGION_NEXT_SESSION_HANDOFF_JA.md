# Issue 120 Prompt 1 / 五線領域調査 次セッション handoff

## 目的

次セッションは、Issue 120 の E2E パイプラインで `TP=3580` 水準の精度を復旧するために、
現在問題になっている「五線領域の認識」を過去コミットも含めて調査し、日本語ドキュメントにまとめる。

ここまでの大きな流れ:

1. E2E パイプラインで v12 restore 相当の精度復旧を進めている。
2. 現行 best は measure-count `abs_delta_sum=4` まで戻っているが、検出 residual には FP/FN が残る。
3. 残 FP の暫定分類で `fp_out_of_staff` が 29 件あり、staff-region filter が期待通り効いていない疑いが出た。
4. 調査の結果、現行の `staff_vov_threshold=0.0` は CNN-stage staff overlap filter を実質無効化していることが分かった。
5. ただし threshold を単純に上げると、真の GT に一致している TP も落ちて FN が増える。
6. 追加実験では raw staff mask 由来の staff-region band も採用不可だった。原因は「五線領域を正確に把握できていない」ことに寄っている。
7. 現在は、現状実装が作っている五線領域の可視化と、過去コミットで staff mask / staff band の扱いがどう変わったかを調査する段階。

## 最初に読むもの

必読:

- `AGENTS.md`
- `docs/ENVIRONMENTS.md`
- `docs/ai-workflow/WORKFLOW.md`
- `docs/ai-workflow/CODEX_GEMINI_COLLAB.md`
- `docs/ai-workflow/LESSONS.md`
- `docs/ISSUE120_NEXT_SESSION_HANDOFF_PROMPTS.md`
- `docs/ISSUE120_E2E_FULL68_RESTORE_REPORT.md`
- `docs/ISSUE120_RESIDUAL_REVIEW_PLAN.md`

今回の五線領域調査で追加された資料:

- `docs/ISSUE120_STAFF_REGION_FILTER_INVESTIGATION.md`
- `docs/ISSUE120_STAFF_REGION_FILTER_VISUALIZATION_JA.md`
- `docs/ISSUE120_STAFF_REGION_FILTER_EXPERIMENT_REPORT_JA.md`

注意:

- 上記 3 件は現時点では未コミットの可能性がある。`git status --short` で確認すること。
- 調査・実験成果物は必ず `logs/` 配下に置く。
- barline detection / numbering logic では固定 px 閾値を導入せず、`unit_size` ベースで考える。

## 現行 best の固定点

対象 config:

- `configs/evaluation2_e2e_verification_full_v12_restore.yaml`

現在の重要設定:

- `cnn_threshold: 0.5`
- `cnn_min_height_unit_ratio: 2.8`
- `cnn_short_low_confidence_min_height_unit_ratio: 2.9`
- `cnn_short_low_confidence_max_score: 0.9`
- `staff_vov_threshold: 0.0`
- `scan_rightmost_rescue: true`
- `divisi_rescue: true`
- `scan_gap_rescue: true`
- `scan_x_peak_rescue: true`

現行 measure-count KPI:

| variant | pred | gt | net delta | abs delta sum | delta pages |
| --- | ---: | ---: | ---: | ---: | ---: |
| current best soft-short | 3380 | 3384 | -4 | 4 | 2 |

残 count-delta ページ:

- `Sibelius-Violin_Concerto-Viola/page_006`: -3
- `Va_Prokofiev_Symphony1/page_005`: -1

## 参照すべきログ

full 68-page の基準 report:

- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/summary_by_layer.csv`
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/per_page_stats.csv`
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/residuals.csv`
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_count_kpi/measure_count_summary.csv`
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_count_kpi/measure_count_delta_pages.csv`

manual / provisional residual 分類:

- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/manual_review/residual_manual_review_template.csv`
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/manual_review/residual_manual_review_template.before_codex_fill.csv`
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/manual_review/codex_classification_summary.md`
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/manual_review/codex_needs_trace_rows.csv`

staff-region filter 調査:

- `logs/issue120_e2e_recovery/staff_region_filter_investigation/trace_examples.csv`
- `logs/issue120_e2e_recovery/staff_region_filter_investigation/staff_filter_summary.md`
- `logs/issue120_e2e_recovery/staff_region_filter_investigation/staff_recognition_replay_summary.md`
- `logs/issue120_e2e_recovery/staff_region_filter_investigation/staff_vov_replay_summary_by_page.csv`
- `logs/issue120_e2e_recovery/staff_region_filter_investigation/staff_vov_replay_dropped_predictions.csv`
- `logs/issue120_e2e_recovery/staff_region_filter_investigation/gt_staff_band_diagnostics.csv`
- `logs/issue120_e2e_recovery/staff_region_filter_investigation/fp_out_of_staff_local_context.csv`

staff-region band 実験:

- `logs/issue120_e2e_recovery/staff_region_filter_experiment_v1/detection_summary.csv`
- `logs/issue120_e2e_recovery/staff_region_filter_experiment_v1/detection_per_page.csv`
- `logs/issue120_e2e_recovery/staff_region_filter_experiment_v1/dropped_predictions.csv`
- `logs/issue120_e2e_recovery/staff_region_filter_experiment_v1/robust_staff_bands_by_page.csv`
- `logs/issue120_e2e_recovery/staff_region_filter_experiment_v2/detection_summary.csv`
- `logs/issue120_e2e_recovery/staff_region_filter_experiment_v2/detection_per_page.csv`
- `logs/issue120_e2e_recovery/staff_region_filter_experiment_v2/dropped_predictions.csv`
- `logs/issue120_e2e_recovery/staff_region_filter_experiment_v2/staff_region_bands_by_page.csv`

今回方式の五線領域可視化:

- `logs/issue120_e2e_recovery/staff_region_filter_experiment_analysis/visuals/staff_region_visual_manifest.json`
- `logs/issue120_e2e_recovery/staff_region_filter_experiment_analysis/visuals/staff_region_legend.png`
- `logs/issue120_e2e_recovery/staff_region_filter_experiment_analysis/visuals/Shostakovich-Sym5-Va_page_025_staff_region_overview.png`
- `logs/issue120_e2e_recovery/staff_region_filter_experiment_analysis/visuals/Shostakovich-Sym5-Va_page_025_staff_region_failure_crop.png`
- `logs/issue120_e2e_recovery/staff_region_filter_experiment_analysis/visuals/Shostakovich-Sym5-Va_page_010_staff_region_overview.png`
- `logs/issue120_e2e_recovery/staff_region_filter_experiment_analysis/visuals/Shostakovich-Sym5-Va_page_010_staff_region_failure_crop.png`
- `logs/issue120_e2e_recovery/staff_region_filter_experiment_analysis/visuals/Va__Prokofiev_Symphony5_page_021_staff_region_overview.png`
- `logs/issue120_e2e_recovery/staff_region_filter_experiment_analysis/visuals/Va__Prokofiev_Symphony5_page_021_staff_region_failure_crop.png`

## 調査対象コード

五線領域 / staff mask / staff band:

- `src/pipeline/probe_detector/bands.py`
- `src/pipeline/steps/candidate_filters.py`
- `src/pipeline/steps/filters.py`
- `src/pipeline/steps/probe_scan.py`
- `src/pipeline/steps/cnn_scoring.py`
- `src/pipeline/detection/orchestrator.py`
- `src/pipeline/detection/utils.py`
- `src/pipeline/detection/hybrid.py`

評価・再現補助:

- `tools/eval2_full_detection_report.py`
- `tools/eval2_residual_measure_impact.py`
- `tools/eval2_measure_count_kpi.py`
- `tools/create_eval2_full_restore_configs.py`

## ここまで分かっている事実

### 現状の五線領域は 1 種類ではない

seed generation:

- injected HOMR `debug_3_staff.png` を staff mask として使う。
- `candidate_filter_kwargs.min_staff_overlap_ratio: 0.02` で bbox 内の mask pixel overlap を見る。
- ただし raw line mask は細すぎるため、barline bbox の inside-staff 判定には直接向かない。

pass2 probe scan:

- 現行 config は `enable_heuristic_filters: false`。
- そのため seed generation 側の staff mask overlap は pass2 candidate には効かない。

CNN-stage:

- `bands_from=probe_seeds` から seed boxes を読み、row stats / vertical band を作る。
- `filter_by_staff_overlap()` は bbox と band の y 方向 VOV だけを見る。
- `staff_vov_threshold: 0.0` なので、実質的にすべての valid bbox が通る。

### `fp_out_of_staff` 29 件の追跡結果

- 29 件すべてが filtered CNN JSON に残っていた。
- 23 件は seed-stage origin。
- 6 件は pass2-scan-only origin。
- 29 件すべてが「disabled CNN staff filter」によって残ったと見なせる。
- ただし、単純に VOV threshold を上げると TP が落ちるため、原因は threshold だけではない。

### 現行 seed-derived band の VOV を上げた replay

| threshold | delta TP | delta FP | delta FN | dropped base TP | dropped `fp_out_of_staff` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.1 | -5 | -1 | +5 | 5 | 0 |
| 0.25 | -15 | -3 | +15 | 15 | 2 |
| 0.5 | -46 | -14 | +46 | 46 | 7 |

この結果から、現行 seed-derived band は「外側 FP を落とす staff region」としては不十分。
外側に見える FP を覆うことがあり、逆に真の TP を覆えないこともある。

### raw staff mask 由来 band の実験結果

v1: `debug_3_staff.png` 由来 line-mask band。

- `Shostakovich-Sym5-Va/page_025` で line grouping が 1 band に崩壊。
- measure-count `abs_delta_sum=4 -> 44`。

v2: hybrid `*_staff_mask.png` 由来 adaptive band。

- page 025 の 1 band 崩壊は改善した。
- しかし別ページで staff band が欠落・結合し、measure-count `abs_delta_sum=4 -> 50`。

採用不可の理由:

- `fp_out_of_staff` は最大 2-3 件しか落ちない。
- 代わりに TP が 47-57 件落ちる。
- broad な y-only staff-region VOV は count-safe ではない。

## 代表的な失敗ページ

`Shostakovich-Sym5-Va/page_025`:

- v1 で `debug_3_staff.png` 由来 band が 1 本に崩壊。
- v2 では 10 band に戻るが、これは v2 全体の採用可能性を意味しない。
- 可視化:
  - `logs/issue120_e2e_recovery/staff_region_filter_experiment_analysis/visuals/Shostakovich-Sym5-Va_page_025_staff_region_overview.png`
  - `logs/issue120_e2e_recovery/staff_region_filter_experiment_analysis/visuals/Shostakovich-Sym5-Va_page_025_staff_region_failure_crop.png`

`Shostakovich-Sym5-Va/page_010`:

- v2 で band_count が 8 になり、下方 staff が欠落。
- measure-count で `-18` の under-count。
- 可視化:
  - `logs/issue120_e2e_recovery/staff_region_filter_experiment_analysis/visuals/Shostakovich-Sym5-Va_page_010_staff_region_overview.png`

`Va__Prokofiev_Symphony5/page_021`:

- v2 で band_count が 6 になり、複数 staff が結合・欠落。
- measure-count で `-19` の under-count。
- 可視化:
  - `logs/issue120_e2e_recovery/staff_region_filter_experiment_analysis/visuals/Va__Prokofiev_Symphony5_page_021_staff_region_overview.png`

`Shostakovich-Sym5-Va/page_006` / `Sibelius-Violin_Concerto-Viola/page_006` / `Va__Prokofiev_Symphony5/page_002`:

- VOV threshold を上げると GT-matched TP が落ちる代表例。
- 可視化は `staff_region_filter_investigation/visuals/` と `staff_region_filter_experiment_analysis/visuals/` の両方にある。

## 次セッションでやること

### 1. 生成済み可視化をまず確認する

最初に `staff_region_visual_manifest.json` と overview / crop を見る。

見る観点:

- band が staff/system 単位で分かれているか。
- staff が欠落していないか。
- 隣接 staff が結合していないか。
- y-only full-width band のせいで、局所的に五線外の候補を staff 内扱いしていないか。
- raw mask pixel と作成 band の関係が妥当か。

### 2. 過去コミットを調べる

調査目的:

- staff mask / staff band の扱いがいつ、なぜ現在の形になったか。
- `staff_vov_threshold` の default / config 値がいつ `0.0` になったか。
- `bands_from=probe_seeds` にした意図と、副作用が過去の議論・コミットに残っているか。
- pass2 で `enable_heuristic_filters: false` にした理由。
- `debug_3_staff.png` と `*_staff_mask.png` のどちらを信頼する設計だったのか。

推奨コマンド例:

```bash
git log --oneline -- configs/evaluation2_e2e_verification_full_v12_restore.yaml src/pipeline/steps/cnn_scoring.py src/pipeline/steps/probe_scan.py src/pipeline/probe_detector/bands.py src/pipeline/detection/orchestrator.py
git log -S staff_vov_threshold --all -- src configs
git log -S min_staff_overlap_ratio --all -- src configs
git log -S enable_heuristic_filters --all -- src configs
git log -S bands_from --all -- src/pipeline
git log -S staff_bands_from_mask --all -- src/pipeline
```

必要に応じて `git show <commit>` で該当差分を読む。

### 3. 日本語ドキュメントにまとめる

推奨出力:

- `docs/ISSUE120_STAFF_REGION_HISTORY_AND_FAILURE_ANALYSIS_JA.md`

最低限入れる内容:

- 現行の五線領域判断方法。
- 過去コミットで staff mask / staff band / threshold が変わった履歴。
- 現在の方式がなぜ `fp_out_of_staff` を落とせないか。
- なぜ threshold や y-only band を強くすると TP/FN が悪化するか。
- 生成済み可視化から見える failure mode。
- 次に試すべき replay-only 小実験。

### 4. 次の小実験案を具体化する

現時点で有力な方向:

- y-only full-width band ではなく、staff-line group ごとに `(x1, y1, x2, y2)` を持つ local staff membership を作る。
- bbox center x 付近に staff line group が存在するかを見る。
- 全 GT / 現行 TP に先に適用し、TP が落ちる例を可視化する。
- その後に `fp_out_of_staff` と count-affecting FP だけへ効果を見る。

避けること:

- raw line mask pixel overlap をそのまま filter に使う。
- `staff_vov_threshold` を上げるだけの broad filter を再実行する。
- `fp_out_of_staff` の削減数だけ見て採用判断する。
- measure-count `abs_delta_sum=4` を悪化させる変更を pipeline に入れる。

## 次セッション用 copy-paste prompt

```text
Issue 120 の Prompt 1 / 五線領域調査の続きです。目的は、E2E パイプラインで `TP=3580` 水準の精度を復旧するために、現在の staff mask / staff band / staff-region filter がなぜ五線領域を正確に把握できていないかを、過去コミットを含めて調査し、日本語ドキュメントにまとめることです。

必ず最初に以下を読んでください:
- AGENTS.md
- docs/ENVIRONMENTS.md
- docs/ai-workflow/WORKFLOW.md
- docs/ai-workflow/CODEX_GEMINI_COLLAB.md
- docs/ai-workflow/LESSONS.md
- docs/ISSUE120_NEXT_SESSION_HANDOFF_PROMPTS.md
- docs/ISSUE120_E2E_FULL68_RESTORE_REPORT.md
- docs/ISSUE120_STAFF_REGION_FILTER_INVESTIGATION.md
- docs/ISSUE120_STAFF_REGION_FILTER_VISUALIZATION_JA.md
- docs/ISSUE120_STAFF_REGION_FILTER_EXPERIMENT_REPORT_JA.md
- docs/ISSUE120_PROMPT1_STAFF_REGION_NEXT_SESSION_HANDOFF_JA.md

背景:
- 現行 best は measure-count `pred=3380`, `gt=3384`, `abs_delta_sum=4`, delta pages=2。
- `fp_out_of_staff` は 29 件あるが、現行 `staff_vov_threshold=0.0` により CNN-stage staff overlap filter は実質無効。
- ただし seed-derived band の VOV threshold を上げると TP が落ちる。
- raw `debug_3_staff.png` 由来 band の v1 と hybrid `*_staff_mask.png` 由来 band の v2 は、どちらも measure-count を大きく悪化させた。
- したがって問題の中心は「五線領域を正確に把握できていないこと」であり、filter threshold 調整だけではない。

まず確認する可視化:
- logs/issue120_e2e_recovery/staff_region_filter_experiment_analysis/visuals/staff_region_visual_manifest.json
- logs/issue120_e2e_recovery/staff_region_filter_experiment_analysis/visuals/*_staff_region_overview.png
- logs/issue120_e2e_recovery/staff_region_filter_experiment_analysis/visuals/*_staff_region_failure_crop.png

調査対象コード:
- src/pipeline/probe_detector/bands.py
- src/pipeline/steps/candidate_filters.py
- src/pipeline/steps/filters.py
- src/pipeline/steps/probe_scan.py
- src/pipeline/steps/cnn_scoring.py
- src/pipeline/detection/orchestrator.py
- src/pipeline/detection/utils.py
- src/pipeline/detection/hybrid.py
- configs/evaluation2_e2e_verification_full_v12_restore.yaml

やること:
1. 生成済み可視化を見て、v1/v2/current seed-derived band がどのような「五線領域」を作っているか説明する。
2. `git log -S` と `git show` で、`staff_vov_threshold`, `min_staff_overlap_ratio`, `enable_heuristic_filters`, `bands_from`, `staff_bands_from_mask` の履歴を追う。
3. 現行方式が外側 FP を残し、真の TP を落とす理由を、コードパスと可視化の両方から整理する。
4. 調査結果を `docs/ISSUE120_STAFF_REGION_HISTORY_AND_FAILURE_ANALYSIS_JA.md` に日本語でまとめる。
5. 実装変更はまだ行わず、次の replay-only 実験案として local staff membership `(x1, y1, x2, y2)` を提案し、検証条件を明記する。

成果物:
- 日本語調査ドキュメント。
- 必要なら追加ログは `logs/issue120_e2e_recovery/staff_region_history_analysis/` 配下。
- 最終回答では、読んだ資料、確認した過去コミット、主な failure mode、次の実験案を簡潔に報告してください。
```

