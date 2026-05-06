# Issue 120: 残存エラー (FP/FN) の全件可視化と分類

このドキュメントでは、`staff_vov_threshold: 0.5` のフィルタを適用した後に最終的に残存している **14件の FP** と **28件の FN** を全件網羅し、そのファイルパスと詳細を記録します。

画像パスは、以前の混在したディレクトリではなく、専用に整理された `clean_visuals/` フォルダを指しています。

## 判定に使用したスクリプトと仕組み

この一覧は、以下のパイプライン評価スクリプトによって出力された `measure_impact_residuals.csv` をパースして生成されています。

```bash
PYTHONPATH=.:external/homr .venv_pdf/bin/python tools/eval2_residual_measure_impact.py \
  --manifest logs/issue120_e2e_recovery/eval2_full_configs/manifest.json \
  --run-root logs/full_pipeline_runs/evaluation2_full_v12_restore \
  --gt-root data/evaluation2/annotations \
  --report-dir logs/issue120_e2e_recovery/eval2_full_report_filtered \
  --output-dir logs/issue120_e2e_recovery/eval2_full_report_filtered/measure_impact
```

**判定の仕組み:**
1. `tools/eval2_full_detection_report.py` が、GT と予測結果の IOU / X-distance マッチングを行い、マッチしなかったものを Residuals (FP/FN) として `residuals.csv` に出力します。
2. `tools/eval2_residual_measure_impact.py` がそれを受け取り、小節線カウントに影響を与えるか（`count_impact`）、重複や複雑なペアに起因するものか（`category`）をヒューリスティックに分類し、可視化用の Crop 画像を出力しています。

## 1. 残存 FP (14件)

FP は以下のカテゴリに分類されます。
### near_matched_gt_duplicate (13件)

**Shostakovich-Festival_Overture_Va page_page_008**
- BBox: `[2226, 4133, 2230, 4223]`
- 影響: `dedup_dependent`
- CNN Score: `0.639`
- 画像: `clean_visuals/fps/near_matched_gt_duplicate/Shostakovich-Festival_Overture_Va/page_008_FP_pred26_score0.639.png`

![FP](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fps/near_matched_gt_duplicate/Shostakovich-Festival_Overture_Va/page_008_FP_pred26_score0.639.png)

**Shostakovich-Sym5-Va page_page_004**
- BBox: `[2232, 2629, 2234, 2718]`
- 影響: `dedup_dependent`
- CNN Score: `0.850`
- 画像: `clean_visuals/fps/near_matched_gt_duplicate/Shostakovich-Sym5-Va/page_004_FP_pred39_score0.850.png`

![FP](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fps/near_matched_gt_duplicate/Shostakovich-Sym5-Va/page_004_FP_pred39_score0.850.png)

**Shostakovich-Sym5-Va page_page_006**
- BBox: `[1872, 415, 1874, 508]`
- 影響: `dedup_dependent`
- CNN Score: `0.881`
- 画像: `clean_visuals/fps/near_matched_gt_duplicate/Shostakovich-Sym5-Va/page_006_FP_pred29_score0.881.png`

![FP](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fps/near_matched_gt_duplicate/Shostakovich-Sym5-Va/page_006_FP_pred29_score0.881.png)

**Shostakovich-Sym5-Va page_page_010**
- BBox: `[1175, 2622, 1177, 2717]`
- 影響: `dedup_dependent`
- CNN Score: `0.925`
- 画像: `clean_visuals/fps/near_matched_gt_duplicate/Shostakovich-Sym5-Va/page_010_FP_pred21_score0.925.png`

![FP](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fps/near_matched_gt_duplicate/Shostakovich-Sym5-Va/page_010_FP_pred21_score0.925.png)

**Shostakovich-Sym5-Va page_page_010**
- BBox: `[1440, 1152, 1442, 1252]`
- 影響: `dedup_dependent`
- CNN Score: `0.614`
- 画像: `clean_visuals/fps/near_matched_gt_duplicate/Shostakovich-Sym5-Va/page_010_FP_pred28_score0.614.png`

![FP](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fps/near_matched_gt_duplicate/Shostakovich-Sym5-Va/page_010_FP_pred28_score0.614.png)

**Shostakovich-Sym5-Va page_page_014**
- BBox: `[2304, 3342, 2308, 3443]`
- 影響: `dedup_dependent`
- CNN Score: `0.612`
- 画像: `clean_visuals/fps/near_matched_gt_duplicate/Shostakovich-Sym5-Va/page_014_FP_pred36_score0.612.png`

![FP](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fps/near_matched_gt_duplicate/Shostakovich-Sym5-Va/page_014_FP_pred36_score0.612.png)

**Sibelius-Violin_Concerto-Viola page_page_002**
- BBox: `[2606, 621, 2610, 838]`
- 影響: `dedup_dependent`
- CNN Score: `0.608`
- 画像: `clean_visuals/fps/near_matched_gt_duplicate/Sibelius-Violin_Concerto-Viola/page_002_FP_pred61_score0.608.png`

![FP](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fps/near_matched_gt_duplicate/Sibelius-Violin_Concerto-Viola/page_002_FP_pred61_score0.608.png)

**Sibelius-Violin_Concerto-Viola page_page_004**
- BBox: `[1190, 552, 1192, 658]`
- 影響: `dedup_dependent`
- CNN Score: `0.691`
- 画像: `clean_visuals/fps/near_matched_gt_duplicate/Sibelius-Violin_Concerto-Viola/page_004_FP_pred14_score0.691.png`

![FP](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fps/near_matched_gt_duplicate/Sibelius-Violin_Concerto-Viola/page_004_FP_pred14_score0.691.png)

**Sibelius-Violin_Concerto-Viola page_page_004**
- BBox: `[1621, 3164, 1625, 3273]`
- 影響: `dedup_dependent`
- CNN Score: `0.998`
- 画像: `clean_visuals/fps/near_matched_gt_duplicate/Sibelius-Violin_Concerto-Viola/page_004_FP_pred36_score0.998.png`

![FP](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fps/near_matched_gt_duplicate/Sibelius-Violin_Concerto-Viola/page_004_FP_pred36_score0.998.png)

**Sibelius-Violin_Concerto-Viola page_page_006**
- BBox: `[2461, 2828, 2463, 2931]`
- 影響: `dedup_dependent`
- CNN Score: `0.989`
- 画像: `clean_visuals/fps/near_matched_gt_duplicate/Sibelius-Violin_Concerto-Viola/page_006_FP_pred32_score0.989.png`

![FP](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fps/near_matched_gt_duplicate/Sibelius-Violin_Concerto-Viola/page_006_FP_pred32_score0.989.png)

**Sibelius-Violin_Concerto-Viola page_page_006**
- BBox: `[2919, 3161, 2921, 3256]`
- 影響: `dedup_dependent`
- CNN Score: `0.894`
- 画像: `clean_visuals/fps/near_matched_gt_duplicate/Sibelius-Violin_Concerto-Viola/page_006_FP_pred43_score0.894.png`

![FP](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fps/near_matched_gt_duplicate/Sibelius-Violin_Concerto-Viola/page_006_FP_pred43_score0.894.png)

**Va__Prokofiev_Symphony5 page_page_016**
- BBox: `[1699, 3565, 1701, 3673]`
- 影響: `dedup_dependent`
- CNN Score: `0.758`
- 画像: `clean_visuals/fps/near_matched_gt_duplicate/Va__Prokofiev_Symphony5/page_016_FP_pred11_score0.758.png`

![FP](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fps/near_matched_gt_duplicate/Va__Prokofiev_Symphony5/page_016_FP_pred11_score0.758.png)

**Va__Prokofiev_Symphony5 page_page_018**
- BBox: `[1863, 2130, 1865, 2238]`
- 影響: `dedup_dependent`
- CNN Score: `0.899`
- 画像: `clean_visuals/fps/near_matched_gt_duplicate/Va__Prokofiev_Symphony5/page_018_FP_pred28_score0.899.png`

![FP](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fps/near_matched_gt_duplicate/Va__Prokofiev_Symphony5/page_018_FP_pred28_score0.899.png)

### remote_fp (1件)

**Va__Prokofiev_Symphony5 page_page_019**
- BBox: `[1561, 4514, 1565, 4614]`
- 影響: `likely_count_affecting`
- CNN Score: `0.835`
- 画像: `clean_visuals/fps/remote_fp/Va__Prokofiev_Symphony5/page_019_FP_pred14_score0.835.png`

![FP](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fps/remote_fp/Va__Prokofiev_Symphony5/page_019_FP_pred14_score0.835.png)

## 2. 残存 FN (28件)

FN は以下のカテゴリに分類されます。
### covered_by_matched_prediction (15件)

**Shostakovich-Festival_Overture_Va page_page_009**
- BBox: `[1232, 1848, 1236, 1959]`
- 影響: `likely_count_neutral`
- 画像: `clean_visuals/fns/covered_by_matched_prediction/Shostakovich-Festival_Overture_Va/page_009_FN_gt12.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/covered_by_matched_prediction/Shostakovich-Festival_Overture_Va/page_009_FN_gt12.png)

**Shostakovich-Sym5-Va page_page_004**
- BBox: `[2728, 1896, 2732, 1995]`
- 影響: `likely_count_neutral`
- 画像: `clean_visuals/fns/covered_by_matched_prediction/Shostakovich-Sym5-Va/page_004_FN_gt39.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/covered_by_matched_prediction/Shostakovich-Sym5-Va/page_004_FN_gt39.png)

**Shostakovich-Sym5-Va page_page_006**
- BBox: `[2726, 2619, 2730, 2718]`
- 影響: `likely_count_neutral`
- 画像: `clean_visuals/fns/covered_by_matched_prediction/Shostakovich-Sym5-Va/page_006_FN_gt30.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/covered_by_matched_prediction/Shostakovich-Sym5-Va/page_006_FN_gt30.png)

**Shostakovich-Sym5-Va page_page_008**
- BBox: `[2743, 428, 2747, 528]`
- 影響: `likely_count_neutral`
- 画像: `clean_visuals/fns/covered_by_matched_prediction/Shostakovich-Sym5-Va/page_008_FN_gt27.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/covered_by_matched_prediction/Shostakovich-Sym5-Va/page_008_FN_gt27.png)

**Shostakovich-Sym5-Va page_page_010**
- BBox: `[2713, 1520, 2717, 1620]`
- 影響: `likely_count_neutral`
- 画像: `clean_visuals/fns/covered_by_matched_prediction/Shostakovich-Sym5-Va/page_010_FN_gt5.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/covered_by_matched_prediction/Shostakovich-Sym5-Va/page_010_FN_gt5.png)

**Shostakovich-Sym5-Va page_page_013**
- BBox: `[1679, 1202, 1683, 1296]`
- 影響: `likely_count_neutral`
- 画像: `clean_visuals/fns/covered_by_matched_prediction/Shostakovich-Sym5-Va/page_013_FN_gt23.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/covered_by_matched_prediction/Shostakovich-Sym5-Va/page_013_FN_gt23.png)

**Shostakovich-Sym5-Va page_page_015**
- BBox: `[2294, 2244, 2298, 2344]`
- 影響: `likely_count_neutral`
- 画像: `clean_visuals/fns/covered_by_matched_prediction/Shostakovich-Sym5-Va/page_015_FN_gt30.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/covered_by_matched_prediction/Shostakovich-Sym5-Va/page_015_FN_gt30.png)

**Shostakovich-Sym5-Va page_page_022**
- BBox: `[2730, 2255, 2734, 2355]`
- 影響: `likely_count_neutral`
- 画像: `clean_visuals/fns/covered_by_matched_prediction/Shostakovich-Sym5-Va/page_022_FN_gt10.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/covered_by_matched_prediction/Shostakovich-Sym5-Va/page_022_FN_gt10.png)

**Sibelius-Violin_Concerto-Viola page_page_004**
- BBox: `[2726, 2923, 2730, 3029]`
- 影響: `likely_count_neutral`
- 画像: `clean_visuals/fns/covered_by_matched_prediction/Sibelius-Violin_Concerto-Viola/page_004_FN_gt7.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/covered_by_matched_prediction/Sibelius-Violin_Concerto-Viola/page_004_FN_gt7.png)

**Sibelius-Violin_Concerto-Viola page_page_004**
- BBox: `[2713, 3166, 2720, 3274]`
- 影響: `likely_count_neutral`
- 画像: `clean_visuals/fns/covered_by_matched_prediction/Sibelius-Violin_Concerto-Viola/page_004_FN_gt16.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/covered_by_matched_prediction/Sibelius-Violin_Concerto-Viola/page_004_FN_gt16.png)

**Sibelius-Violin_Concerto-Viola page_page_004**
- BBox: `[1514, 4015, 1518, 4195]`
- 影響: `likely_count_neutral`
- 画像: `clean_visuals/fns/covered_by_matched_prediction/Sibelius-Violin_Concerto-Viola/page_004_FN_gt53.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/covered_by_matched_prediction/Sibelius-Violin_Concerto-Viola/page_004_FN_gt53.png)

**Sibelius-Violin_Concerto-Viola page_page_004**
- BBox: `[1924, 4015, 1928, 4195]`
- 影響: `likely_count_neutral`
- 画像: `clean_visuals/fns/covered_by_matched_prediction/Sibelius-Violin_Concerto-Viola/page_004_FN_gt57.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/covered_by_matched_prediction/Sibelius-Violin_Concerto-Viola/page_004_FN_gt57.png)

**Sibelius-Violin_Concerto-Viola page_page_006**
- BBox: `[3182, 4071, 3186, 4174]`
- 影響: `likely_count_neutral`
- 画像: `clean_visuals/fns/covered_by_matched_prediction/Sibelius-Violin_Concerto-Viola/page_006_FN_gt18.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/covered_by_matched_prediction/Sibelius-Violin_Concerto-Viola/page_006_FN_gt18.png)

**Va_Prokofiev_Symphony1 page_page_003**
- BBox: `[3178, 1239, 3182, 1342]`
- 影響: `likely_count_neutral`
- 画像: `clean_visuals/fns/covered_by_matched_prediction/Va_Prokofiev_Symphony1/page_003_FN_gt64.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/covered_by_matched_prediction/Va_Prokofiev_Symphony1/page_003_FN_gt64.png)

**Va__Prokofiev_Symphony5 page_page_007**
- BBox: `[668, 908, 672, 1018]`
- 影響: `likely_count_neutral`
- 画像: `clean_visuals/fns/covered_by_matched_prediction/Va__Prokofiev_Symphony5/page_007_FN_gt1.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/covered_by_matched_prediction/Va__Prokofiev_Symphony5/page_007_FN_gt1.png)

### isolated_missing (11件)

**Shostakovich-Sym5-Va page_page_003**
- BBox: `[2732, 1161, 2741, 1262]`
- 影響: `likely_count_affecting`
- 画像: `clean_visuals/fns/isolated_missing/Shostakovich-Sym5-Va/page_003_FN_gt36.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/isolated_missing/Shostakovich-Sym5-Va/page_003_FN_gt36.png)

**Shostakovich-Sym5-Va page_page_004**
- BBox: `[2724, 425, 2733, 528]`
- 影響: `likely_count_affecting`
- 画像: `clean_visuals/fns/isolated_missing/Shostakovich-Sym5-Va/page_004_FN_gt19.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/isolated_missing/Shostakovich-Sym5-Va/page_004_FN_gt19.png)

**Shostakovich-Sym5-Va page_page_009**
- BBox: `[2743, 2995, 2752, 3097]`
- 影響: `likely_count_affecting`
- 画像: `clean_visuals/fns/isolated_missing/Shostakovich-Sym5-Va/page_009_FN_gt9.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/isolated_missing/Shostakovich-Sym5-Va/page_009_FN_gt9.png)

**Shostakovich-Sym5-Va page_page_015**
- BBox: `[2370, 1149, 2374, 1249]`
- 影響: `likely_count_affecting`
- 画像: `clean_visuals/fns/isolated_missing/Shostakovich-Sym5-Va/page_015_FN_gt4.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/isolated_missing/Shostakovich-Sym5-Va/page_015_FN_gt4.png)

**Shostakovich-Sym5-Va page_page_015**
- BBox: `[2730, 777, 2739, 879]`
- 影響: `likely_count_affecting`
- 画像: `clean_visuals/fns/isolated_missing/Shostakovich-Sym5-Va/page_015_FN_gt42.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/isolated_missing/Shostakovich-Sym5-Va/page_015_FN_gt42.png)

**Sibelius-Violin_Concerto-Viola page_page_006**
- BBox: `[969, 4072, 973, 4175]`
- 影響: `likely_count_affecting`
- 画像: `clean_visuals/fns/isolated_missing/Sibelius-Violin_Concerto-Viola/page_006_FN_gt10.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/isolated_missing/Sibelius-Violin_Concerto-Viola/page_006_FN_gt10.png)

**Sibelius-Violin_Concerto-Viola page_page_006**
- BBox: `[2143, 4072, 2147, 4175]`
- 影響: `likely_count_affecting`
- 画像: `clean_visuals/fns/isolated_missing/Sibelius-Violin_Concerto-Viola/page_006_FN_gt12.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/isolated_missing/Sibelius-Violin_Concerto-Viola/page_006_FN_gt12.png)

**Sibelius-Violin_Concerto-Viola page_page_006**
- BBox: `[2471, 4072, 2475, 4175]`
- 影響: `likely_count_affecting`
- 画像: `clean_visuals/fns/isolated_missing/Sibelius-Violin_Concerto-Viola/page_006_FN_gt14.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/isolated_missing/Sibelius-Violin_Concerto-Viola/page_006_FN_gt14.png)

**Va_Prokofiev_Symphony1 page_page_004**
- BBox: `[2565, 2488, 2569, 2591]`
- 影響: `likely_count_affecting`
- 画像: `clean_visuals/fns/isolated_missing/Va_Prokofiev_Symphony1/page_004_FN_gt29.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/isolated_missing/Va_Prokofiev_Symphony1/page_004_FN_gt29.png)

**Va_Prokofiev_Symphony1 page_page_004**
- BBox: `[2885, 2488, 2889, 2591]`
- 影響: `likely_count_affecting`
- 画像: `clean_visuals/fns/isolated_missing/Va_Prokofiev_Symphony1/page_004_FN_gt32.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/isolated_missing/Va_Prokofiev_Symphony1/page_004_FN_gt32.png)

**Va_Prokofiev_Symphony1 page_page_004**
- BBox: `[847, 2675, 854, 2776]`
- 影響: `likely_count_affecting`
- 画像: `clean_visuals/fns/isolated_missing/Va_Prokofiev_Symphony1/page_004_FN_gt34.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/isolated_missing/Va_Prokofiev_Symphony1/page_004_FN_gt34.png)

### complex_pair_uncovered (2件)

**Va_Prokofiev_Symphony1 page_page_005**
- BBox: `[2363, 3482, 2367, 3585]`
- 影響: `likely_count_affecting`
- 画像: `clean_visuals/fns/complex_pair_uncovered/Va_Prokofiev_Symphony1/page_005_FN_gt40.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/complex_pair_uncovered/Va_Prokofiev_Symphony1/page_005_FN_gt40.png)

**Va_Prokofiev_Symphony1 page_page_005**
- BBox: `[2377, 3496, 2381, 3599]`
- 影響: `likely_count_affecting`
- 画像: `clean_visuals/fns/complex_pair_uncovered/Va_Prokofiev_Symphony1/page_005_FN_gt41.png`

![FN](../../logs/issue120_e2e_recovery/eval2_full_report_filtered/clean_visuals/fns/complex_pair_uncovered/Va_Prokofiev_Symphony1/page_005_FN_gt41.png)

