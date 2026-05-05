# Issue 120 Next Session Handoff Prompts

## Purpose

This document is for splitting the next work into focused sessions. It records the current
state, required background, and copy-paste prompts for the next three investigations:

1. Staff-region filtering for apparent outside-staff FP.
2. Divisi/system-spanning FP origin tracing.
3. Remaining FN tracing: right-edge, candidate-stage miss, and CNN low-score cases.

Do not start by adding broad filters or rescues. The next sessions should trace origins,
produce small reproducible diagnostics, and only then propose narrow fixes.

## Common Background For All Prompts

Repository:

- Worktree: `/home/masaki_muramatsu/ws_PDFScoreBar`
- Branch: `fix/probe_seeds`
- Follow `AGENTS.md` and read `docs/ENVIRONMENTS.md` before running commands.
- Experiment outputs must stay under `logs/`.
- Use unit-scaled geometry; do not introduce fixed pixel thresholds in detection/numbering
  logic.

Current committed operating point:

- Commit `95d63d0 Add soft-short low confidence barline filter`
- Current documentation commits:
  - `3d7f7ef Document residual review plan`
  - `4d0b37d Document staged residual review workflow`
- Config: `configs/evaluation2_e2e_verification_full_v12_restore.yaml`
- Detection settings:
  - `cnn_threshold: 0.5`
  - `cnn_min_height_unit_ratio: 2.8`
  - `cnn_short_low_confidence_min_height_unit_ratio: 2.9`
  - `cnn_short_low_confidence_max_score: 0.9`
  - `staff_vov_threshold: 0.0`
  - `scan_rightmost_rescue: true`
  - `divisi_rescue: true`
  - `scan_gap_rescue: true`
  - `scan_x_peak_rescue: true`
- Unit-scaled numbering thresholds:
  - dedup: `1.2u`
  - implicit start: `4.0u`
  - min measure width: `1.8u`

Current measure-count KPI:

| variant | pred | gt | net delta | abs delta sum | delta pages | precision | recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `score_ge_0p5_minh_2p8` | 3381 | 3384 | -3 | 5 | 3 | 0.998225 | 0.997340 |
| `score_ge_0p5_minh_2p8_softshort_2p9_scorelt_0p9` | 3380 | 3384 | -4 | 4 | 2 | 0.998817 | 0.997636 |

Remaining count-delta pages:

- `Sibelius-Violin_Concerto-Viola/page_006`: -3
- `Va_Prokofiev_Symphony1/page_005`: -1

Important artifacts:

- Fixed full-68 report:
  `docs/ISSUE120_E2E_FULL68_RESTORE_REPORT.md`
- Residual review plan:
  `docs/ISSUE120_RESIDUAL_REVIEW_PLAN.md`
- Residual CSV:
  `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_impact/measure_impact_residuals.csv`
- Manual review CSV, partially user-entered and then Codex-provisionally completed:
  `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/manual_review/residual_manual_review_template.csv`
- Pre-Codex-fill backup:
  `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/manual_review/residual_manual_review_template.before_codex_fill.csv`
- Codex provisional summary:
  `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/manual_review/codex_classification_summary.md`
- Needs-trace rows:
  `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/manual_review/codex_needs_trace_rows.csv`
- Visual review:
  - `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/visuals/fp_crops/`
  - `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/visuals/fn_crops/`
  - `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/visuals/overlays/`
  - `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/manual_review/contact_sheets/`

Codex provisional residual classification summary:

| manual class | count |
| --- | ---: |
| `fp_divisi_spanning` | 62 |
| `fp_out_of_staff` | 29 |
| `fp_near_gt_duplicate` | 25 |
| `fp_internal_false_bar` | 9 |
| `fn_double_or_end_one_side` | 6 |
| `fn_right_edge_missing` | 5 |
| `fn_cnn_low_score` | 5 |
| `fn_candidate_stage_miss` | 3 |
| `fn_out_of_staff_gt` | 1 |

Treat these classifications as provisional prioritization, not final truth.

## Experiment History To Preserve

The following work has already been done and should not be repeated without a new reason:

1. Crop recenter parity was added to E2E CNN scoring to match the standalone score script.
2. Full 68-page evaluation and visualization tooling was added:
   - `tools/create_eval2_full_restore_configs.py`
   - `tools/eval2_full_detection_report.py`
   - `tools/eval2_residual_measure_impact.py`
   - `tools/eval2_measure_count_kpi.py`
3. Unit-scaled numbering thresholds were adopted:
   - dedup `1.2u`
   - implicit start `4.0u`
   - min measure width `1.8u`
4. Soft-short low-confidence filtering was adopted:
   - hard minimum `2.8u`
   - additionally suppress `height < 2.9u` only when `score < 0.9`
   - improved measure-count `abs_delta_sum` from 5 to 4.
5. Rejected sweeps:
   - `staffcov_v1`: worsened `abs_delta_sum` from 5 to 26.
   - `xalign_rescue_v1`: best tested variant worsened `abs_delta_sum` from 5 to 6.
   - `low_score_gap_rescue_v1`: locally fixed `Va_Prokofiev_Symphony1/page_005`, but
     globally worsened `abs_delta_sum` from 5 to 24.
   - `minh_after_unit_v1`: hard min-height `2.9u` fixed Shostakovich page 018 but created
     new FN on `Va__Prokofiev_Symphony5`; global `abs_delta_sum` worsened to 6.
   - `score_threshold_after_unit_v1`: threshold `0.75` removed the page 018 FP but created
     `Shostakovich-Sym5-Va/page_008` under-count; no global improvement.
   - `numbering_partial_bar_v1`: fixed a prediction count locally but changed GT measure
     extraction (`gt_measure_count 3384 -> 3374`), so it is invalid.

## Prompt 1: Staff-Region Filtering Investigation

Copy-paste prompt for the next session:

```text
Issue 120 の次セッションです。目的は staff-region filtering の現実装と不具合可能性を調査することです。実装変更はまだ行わず、根拠付きの調査結果と小さな検証計画を作ってください。

必ず最初に以下を読んでください:
- AGENTS.md
- docs/ENVIRONMENTS.md
- docs/ISSUE120_E2E_FULL68_RESTORE_REPORT.md
- docs/ISSUE120_RESIDUAL_REVIEW_PLAN.md
- docs/ISSUE120_NEXT_SESSION_HANDOFF_PROMPTS.md

背景:
- 現在の最良設定は `cnn_threshold=0.5`, `cnn_min_height_unit_ratio=2.8`, `cnn_short_low_confidence_min_height_unit_ratio=2.9`, `cnn_short_low_confidence_max_score=0.9`, `staff_vov_threshold=0.0`。
- Codex 暫定分類では `fp_out_of_staff` が 29 件あります。
- 過去に staff-region filter で五線外候補を削除していたはずですが、現在の可視化では五線外 FP が残っています。
- 既に `staffcov_v1` という broad filter sweep は `abs_delta_sum 5 -> 26` と悪化したため、同じ broad filter を繰り返さないでください。

調査対象:
- `src/pipeline/steps/cnn_scoring.py`
- `src/pipeline/probe_detector/bands.py`
- `src/pipeline/steps/probe_scan.py`
- `src/pipeline/detection/orchestrator.py`
- `configs/evaluation2_e2e_verification_full_v12_restore.yaml`

使うデータ:
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/manual_review/residual_manual_review_template.csv`
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/manual_review/codex_needs_trace_rows.csv`
- FP crop/overlay under `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/visuals/`
- full run root `logs/full_pipeline_runs/evaluation2_full_v12_restore`

調査してほしいこと:
1. `staff_vov_threshold=0.0` の意味と、現在 staff overlap filter が実質無効かどうかを確認。
2. `candidate_filter_kwargs.min_staff_overlap_ratio` と CNN 側 `filter_by_staff_overlap` の役割差を整理。
3. `fp_out_of_staff` 代表例 5-10 件について、candidate / scored / filtered のどの段階で残っているか確認。
4. staff band が広すぎるのか、staff mask の読み方が違うのか、または設定で無効化されているのかを切り分け。
5. もし小さな再評価を提案するなら、`fp_out_of_staff` のみに効く条件に限定し、measure-count KPI で `abs_delta_sum` が悪化しない確認方法を示す。

成果物:
- 調査結果を `logs/issue120_e2e_recovery/staff_region_filter_investigation/` に保存。
- 必要なら `docs/ISSUE120_STAFF_REGION_FILTER_INVESTIGATION.md` を作成。
- 最終回答では、実装変更の有無、確認したコードパス、代表例、次の小実験案を報告。
```

Expected output:

- Whether the current staff filter is disabled, too permissive, or applied at the wrong
  stage.
- A small, unit-scaled, count-safe verification proposal.

## Prompt 2: Divisi/System-Spanning FP Origin Trace

Copy-paste prompt for the next session:

```text
Issue 120 の次セッションです。目的は `fp_divisi_spanning` / system-spanning FP がどこで混入したかを追跡することです。実装変更はまだ行わず、代表例の origin trace と次の小実験計画を作ってください。ただし、Propmpt1はすでに一定の成果を上げています。（成果は`docs/ISSUE120_STAFF_REGION_HISTORY_AND_FAILURE_ANALYSIS_JA.md`に記録済み）

必ず最初に以下を読んでください:
- AGENTS.md
- docs/ENVIRONMENTS.md
- docs/ISSUE120_E2E_FULL68_RESTORE_REPORT.md
- docs/ISSUE120_RESIDUAL_REVIEW_PLAN.md
- docs/ISSUE120_NEXT_SESSION_HANDOFF_PROMPTS.md

背景:
- Codex 暫定分類では `fp_divisi_spanning` が 62 件で最大カテゴリです。
- ユーザー観察では、divisi の二段を通して一本の線として認識しているものがあり、homr の検出には含まれないはずです。
- 現在 config では `divisi_rescue`, `scan_gap_rescue`, `scan_x_peak_rescue`, `scan_rightmost_rescue` が有効です。
- broad な x-align/low-score rescue は過去に全体 measure-count KPI を悪化させています。

調査対象:
- `src/pipeline/probe_detector/__init__.py`
- `src/pipeline/steps/probe_scan.py`
- `src/pipeline/detection/hybrid.py`
- `src/pipeline/detection/orchestrator.py`
- `src/pipeline/core/run_ids.py`

使うデータ:
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/manual_review/residual_manual_review_template.csv`
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/manual_review/codex_needs_trace_rows.csv`
- `logs/full_pipeline_runs/evaluation2_full_v12_restore`
- hybrid/homr output under `logs/hybrid_generalization/verification_full_v12_restore`
- visual crops/overlays under `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/visuals/`

調査してほしいこと:
1. `fp_divisi_spanning` 代表例 10 件を選び、bbox が以下のどこに現れるかを追跡:
   - homr baseline detections
   - SR detections
   - OMR/hybrid union
   - probe seed JSON
   - probe scan candidates
   - scored JSON
   - filtered CNN JSON
2. 混入が `divisi_rescue`, `scan_gap_rescue`, `scan_x_peak_rescue`, `scan_rightmost_rescue` のどれに近いかをコードとログで推定。
3. staff band が divisi を一つの広い system として扱っているか確認。
4. 代表例ごとに `origin_stage`, `suspected_rescue`, `score`, `height_unit_ratio`, `count risk` を CSV にまとめる。
5. 実装案はまだ採用せず、次に試すならどの rescue の条件をどう絞るべきかを提案する。

成果物:
- `logs/issue120_e2e_recovery/divisi_spanning_origin_trace/trace_examples.csv`
- 必要なら代表例 overlay/contact sheet。
- 必要なら `docs/ISSUE120_DIVISI_SPANNING_ORIGIN_TRACE.md`
- 最終回答では、混入段階、原因候補、次の小実験案を報告。
```

Expected output:

- A concrete origin-stage table for representative system-spanning FP.
- A narrowed hypothesis about which rescue/seed path needs adjustment.

## Prompt 3: Remaining FN Trace

Copy-paste prompt for the next session:

```text
Issue 120 の次セッションです。目的は FN 側の残課題を `right_edge_missing`, `candidate_stage_miss`, `cnn_low_score`, `count-neutral one-side FN` に分け、最終目標である小節数カウントに効くものだけを次の改善対象にすることです。実装変更はまだ行わず、調査と小実験計画を作ってください。

必ず最初に以下を読んでください:
- AGENTS.md
- docs/ENVIRONMENTS.md
- docs/ISSUE120_E2E_FULL68_RESTORE_REPORT.md
- docs/ISSUE120_RESIDUAL_REVIEW_PLAN.md
- docs/ISSUE120_NEXT_SESSION_HANDOFF_PROMPTS.md

背景:
- 現在の measure-count delta は `Sibelius-Violin_Concerto-Viola/page_006 = -3`, `Va_Prokofiev_Symphony1/page_005 = -1` のみ。
- Codex 暫定分類では FN 側に `fn_right_edge_missing=5`, `fn_cnn_low_score=5`, `fn_candidate_stage_miss=3`, `fn_double_or_end_one_side=6`, `fn_out_of_staff_gt=1` があります。
- ダブルバーや end bar の片側のみ missing は、小節数カウントでは無視できる可能性が高いです。
- `Va_Prokofiev_Symphony1/page_005` の低スコア double-bar candidate は局所的には救済できたが、broad low-score rescue は全体で悪化しました。

調査対象:
- `src/pipeline/probe_detector/__init__.py`
- `src/pipeline/steps/probe_scan.py`
- `src/pipeline/steps/cnn_scoring.py`
- `src/pipeline/detection/orchestrator.py`
- `tools/eval2_measure_count_kpi.py`

使うデータ:
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/manual_review/residual_manual_review_template.csv`
- `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/measure_impact/measure_impact_residuals.csv`
- `logs/full_pipeline_runs/evaluation2_full_v12_restore`
- FN crops/overlays under `logs/issue120_e2e_recovery/eval2_full_report_final_68pages/visuals/`

調査してほしいこと:
1. FN 行を `count_affecting` と `count_neutral` に分け、次の改善対象から one-side double/end FN を除外できるか確認。
2. `Sibelius/page_006` の3件:
   - x=969, x=2143 は candidate-stage miss かを再確認。
   - x=2471 は low-score candidate かを再確認。
   - right-edge rescue と関係するか確認。
3. `Va_Prokofiev_Symphony1/page_005` の double-bar low-score candidate:
   - local rescue が measure count を直す根拠を再確認。
   - broad rescue がなぜ悪化したか、追加された FP のカテゴリを見る。
4. `fn_right_edge_missing` 代表例について、`scan_rightmost_rescue` が有効なのになぜ救えていないかを stage 別に確認。
5. 次に試すなら、Sibelius last-system/right-edge/candidate-stage に限定した小実験と、Va double-bar low-score に限定した小実験を分けて提案。

成果物:
- `logs/issue120_e2e_recovery/fn_residual_trace/fn_trace_summary.csv`
- 必要なら `docs/ISSUE120_FN_RESIDUAL_TRACE.md`
- 最終回答では、count-neutral と count-affecting の切り分け、残る改善候補、小実験の再現方法を報告。
```

Expected output:

- A focused FN worklist that excludes count-neutral one-side cases.
- Separate candidate-stage and CNN-low-score hypotheses for the remaining count-delta pages.

## Recommended Session Order

1. Run Prompt 1 first. Staff-region filter status affects interpretation of both
   `fp_out_of_staff` and some `fp_divisi_spanning` rows.
2. Run Prompt 2 second. Divisi/system-spanning FP is the largest provisional class and may
   point to one rescue path.
3. Run Prompt 3 third. FN work should happen after FP origin tracing because previous broad
   FN rescues caused over-count.

Each session should end with:

- paths of generated logs/docs,
- a clear adopted/rejected list,
- reproduction commands,
- and whether a code change is proposed or deferred.
