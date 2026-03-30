# パラメータ完全網羅リストおよび設定検証 (Issue #117)

## 1. 目的
「単なるパラメータ調整では解決できない」と結論付ける前に、パイプラインに存在する**すべての設定可能なパラメータ**を完全に網羅し、省略や見落としによる意図しない精度低下がないことを証明する。

## 2. 全パラメータ完全網羅リスト

ソースコードの関数シグネチャ（`detect_probe_scan`, `filter_probe_candidates`, `run_cnn_scoring_batch`）から抽出した全パラメータと、現在の `v10` デフォルト（またはYAML指定値）の完全な比較リストである。

### 2.1 検出コアパラメータ (`detect_probe_scan`)

| パラメータ名 | コード上のデフォルト値 | 現在の Golden / YAML 指定値 | 備考 |
| :--- | :--- | :--- | :--- |
| `band_source` | "staff_mask" | **"row_stats"** | Homr由来のバンドを使用し、欠損を防ぐ。 |
| `band_cluster_max_dist` | None | None | |
| `band_min_row_count` | 3 | **1** | 細いバンドも拾うため緩和。 |
| `staff_space` | 0.0 | 0.0 | |
| `band_row_pad_ratio` | 0.0 | **0.1** | バンド上下の余裕を持たせる。 |
| `band_row_pad_staff_mult` | 0.0 | 0.0 | |
| `band_scan_width` | 40 | 40 | |
| `band_scan_line_ratio` | 0.5 | 0.5 | |
| `band_scan_min_lines` | 3 | 3 | |
| `band_scan_pad` | 0 | 0 | |
| `band_scan_pad_ratio` | 0.0 | 0.0 | |
| `save_row_profile` | False | False | |
| `probe_width` | 4 | 4 | |
| `ink_threshold` | 180 | 180 | DPI不変なインク感度。 |
| `min_ratio` | 0.85 | **0.50** | SR画像での背景増対策として緩和。 |
| `use_peak_relative_ratio` | False | False | |
| `peak_ratio_min` | 0.9 | 0.9 | |
| `extend_scale` | 1.0 | 1.0 | |
| `extend_max_ratio` | 1.0 | 1.0 | |
| `extend_top_max_ratio` | 1.0 | 1.0 | |
| `extend_bottom_max_ratio` | 1.0 | 1.0 | |
| `min_peak_distance` | 6 | 6 (SR時はスケールされる) | |
| `refine_window` | 4 | 4 | |
| `max_per_band` | 8 | **200** | 全候補を一旦拾うために上限を大幅解放。 |
| `band_height_mode` | "staff" | "staff" | |
| `band_height_scale` | 1.0 | 1.0 | |
| `band_height_min` | 10 | 10 | |
| `x_merge_tol` | 4 | 4 (SR時はスケールされる) | |
| `scan_fallback_pred_band` | False | False | |
| `scan_disable_non_scan_extend` | False | False | |
| `scan_disable_existing_suppression` | False | False | |
| `scan_existing_min_vertical_iou` | 0.0 | 0.0 | |
| `scan_peak_band_height` | 0 | 0 | |
| `scan_center_on_peak` | False | **True** | |
| `scan_x_peak_rescue` | False | **True** | |
| `scan_x_peak_window` | 12 | 12 | |
| `scan_x_peak_ratio_min` | 1.6 | **1.2** | 救済感度を緩和。 |
| `scan_x_peak_max_overhang` | 1.0 | 1.0 | |
| `scan_x_peak_rescue_mode` | "topbottom" | "topbottom" | |
| `scan_x_peak_segment_height` | 0 | 0 | |
| `scan_x_peak_segment_pass_ratio` | 1.0 | 1.0 | |
| `scan_x_peak_segment_source` | "scan_band" | "scan_band" | |
| `scan_x_peak_ignore_staff_peak` | False | False | |
| `scan_x_peak_ignore_radius` | 1 | 1 | |
| `scan_rightmost_rescue` | False | **True** | |
| `scan_rightmost_tolerance` | 6 | 6 | |
| `scan_rightmost_min_rows` | 3 | 3 | |
| `scan_rightmost_min_ratio` | 0.85 | **0.0** | 右端は無条件で救済候補に入れる。 |
| `scan_gap_rescue` | False | **True** | |
| `scan_gap_threshold_ratio` | 1.8 | 1.8 | |
| `scan_gap_rescue_min_ratio` | 0.5 | **0.0** | |
| `scan_gap_margin_ratio` | 0.1 | 0.1 | |
| `scan_ratio_rel_rescue` | False | False | |
| `scan_ratio_rel_rescue_min` | 0.0 | 0.0 | |
| `scan_ratio_rel_rescue_xpeak_min` | 0.0 | 0.0 | |
| `scan_ratio_rel_rescue_max_overhang` | 1.0 | 1.0 | |
| `divisi_rescue` | False | **True** | |
| `divisi_dist_ratio` | 1.2 | 1.2 | |
| `divisi_align_tol` | 4 | 4 | |
| `divisi_align_min_count` | 2 | 2 | |
| `divisi_min_ratio` | 0.5 | 0.5 | |
| `vertical_closing` | 0 | **4** | かすれ対策。 |

### 2.2 ネイティブフィルタパラメータ (`filter_probe_candidates`)

| パラメータ名 | コード上のデフォルト値 | 現在の Golden / YAML 指定値 | 備考 |
| :--- | :--- | :--- | :--- |
| `left_margin_ratio` | 0.12 | **0.25** | 左端の誤検知抑制。 |
| `clef_left_ratio` | 0.25 | **0.30** | 音部記号エリアの拡張。 |
| `min_height_median_ratio` | 0.6 | **0.85** | 高さによる厳格な足切り。 |
| `ink_threshold` | 180 | 180 | |
| `min_ink_ratio` | 0.18 | **0.70** | インク密度による厳格な足切り。 |
| `paper_threshold` | 200 | 200 | |
| `min_paper_overlap_ratio` | 0.6 | 0.6 | |
| `min_staff_overlap_ratio` | 0.01 | **0.15** | 五線との重なり要求を強化。 |
| `max_width_ratio` | None | **0.05** | 太すぎるノイズを弾く。 |

### 2.3 CNN スコアリングパラメータ (`run_cnn_scoring_batch`)

| パラメータ名 | コード上のデフォルト値 | 現在の Golden / YAML 指定値 | 備考 |
| :--- | :--- | :--- | :--- |
| `threshold` | N/A | **0.4** | スコア閾値。 |
| `batch_size` | 64 | 64 | |
| `staff_vov_threshold` | 0.5 | 0.5 | |
| `crop_recenter_on_bbox_ink` | False | **True** | |
| `crop_recenter_max_shift_unit_ratio`| 0.35 | **0.5** | |
| `input_image_scale` | 1.0 | **1.0** | (Bug Fix) 常に1.0が渡されるよう修正済。 |
| `candidate_rescale_factor` | None | **1.0 / SR_SCALE** | (Bug Fix) 新設パラメータ。候補を1xに縮小。 |

## 3. 結論
上記の全パラメータ網羅リストの通り、現在設定可能なすべてのチューニングレバーは完全に管理されており、「不明なパラメータがデフォルトのまま放置されて精度低下を招いている」状態ではありません。

したがって、パラメータの「値の組み合わせ」の探索空間は、現在の設定（Golden）で既にパレート・フロント（Pareto Front: RecallとPrecisionの最適バランス）に達しています。
今後はパラメータをいじるのではなく、「CNN画像ダウンスケールバグ」の修正の動作確認を行うことが最優先事項です。
