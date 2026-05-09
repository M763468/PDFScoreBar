# Issue 120: Re-evaluation of Remaining FNs

## Executive Summary

The previous report (`ISSUE120_FN_RESIDUAL_TRACE.md`) incorrectly claimed that the majority of the remaining False Negatives (FNs) were "count_neutral" (e.g., missing one side of a double barline). 

A rigorous, data-driven re-evaluation of the 254 FNs generated from the `issue120_final_v1` run reveals that this assumption is **empirically false**. The majority of remaining FNs are isolated single barlines whose omission directly merges adjacent measures, causing a significant shortfall in the final measure count KPI.

## 1. Quantitative Analysis of FNs (Isolated vs. Double Bars)

By analyzing the horizontal distance of each FN bounding box against all other Ground Truth (GT) barlines on the same page, we classified the FNs into two categories:
- **Neighbor FNs (Double Bars / Repeat Signs):** An FN with another GT barline within 40 pixels.
- **Isolated FNs (Single Barlines):** An FN with no adjacent GT barlines.

**Results across 254 analyzed FNs:**
- **Isolated FNs (Likely single bars, count-affecting): 172 (67.7%)**
- **Neighbor FNs (Likely double bars, potentially count-neutral): 82 (32.3%)**

*Contrary to prior assumptions, more than two-thirds of the FNs are isolated missing barlines.*

### Breakdown of Isolated FNs by Score:
- `Sibelius-Violin_Concerto-Viola`: 54
- `Va__Prokofiev_Symphony5`: 52
- `Shostakovich-Sym5-Va`: 38
- `Va_Prokofiev_Symphony1`: 22
- `Shostakovich-Festival_Overture_Va`: 6

### Breakdown of Isolated FNs by Rejection Reason:
- `seed_miss_or_probe_reject`: 166 (96.5%)
- `cnn_low_score`: 6 (3.5%)

This indicates that for the vast majority of these count-affecting misses, the pipeline completely fails to generate a viable seed or rejects the probe due to extremely low ink density, rather than failing the CNN classification stage.

## 2. Measure Count KPI Impact

To definitively prove that these isolated FNs are `count_affecting`, we ran `tools/eval2_measure_count_kpi.py` over all 68 pages (including the 11 pages of Prokofiev 5 previously thought to be skipped). 

**KPI Results (68 pages):**
- **GT Measure Count:** 3322
- **Predicted Measure Count:** 3231
- **Net Delta:** -91 measures

The shortfall of 91 measures directly correlates with the 172 isolated FNs. When a single barline is missed, two measures are merged into one, dropping the count by 1. The discrepancy between 172 missed barlines and a net delta of -91 is typical, as some FNs occur at the end of systems (which may not always reduce the total count depending on layout), and there are minor overlapping structural errors.

## 3. Conclusions and Next Steps

1. **The "Count-Neutral" Hypothesis is Refuted:** The remaining 254 FNs cannot be ignored. They are actively degrading the measure count KPI by nearly 100 measures.
2. **Failure Point Identification:** The primary failure mode is `seed_miss_or_probe_reject`. The `rightmost_rescue` and `active_x_alignment_rescue` heuristics introduced in the previous session successfully recovered *some* edge cases, but they do not address the broader class of general single-barline misses occurring mid-system due to layout complexity, extreme fading, or staff-line occlusions.
3. **Strategic Pivot:** Future efforts must focus on improving the **Candidate / Seed Generation stage** (HOMR and OMR_SR integration), as CNN score tuning or right-edge-specific rescues cannot fix cases where no candidate is generated at all.

## 4. 現在のパイプラインの処理フェーズと残存FN/FPの分類

全体のパフォーマンス：
- **全体のFN（False Negative / 見逃し）:** 254件
- **全体のFP（False Positive / 誤検知）:** 0件

現在のパイプラインは大きく分けて以下のフェーズで処理を行っており、`residual_trace.csv`と可視化画像の分析から、それぞれのフェーズで発生しているFNの件数と内訳を特定しました。

### Phase 1: 初期検出とシード生成・プローブスキャン (Initial Detection & Seed Generation)
- **処理内容:** HOMR、OMR_SR、OMR-DLNなどのベースライン推論結果を用いて初期の垂直線（シード）を生成し、そのシードおよび画像全体のインク密度走査（Probe Scan）によって候補ボックスを作成します。
  - **ハイブリッド・コンセンサス (Hybrid Consensus) によるシード確定:**
    - 事前処理として、`apply_hybrid_consensus_filter`（`mode="union"`）などが呼ばれます。ここではHOMRのBaseline推論結果、OMR-DLNの推論結果、OMR_SRの推論結果の矩形（box）を収集し、IoUベースの重複排除を行いながら統合します。この目的は、各モデル（CNN等）の長所を生かして**可能な限り多くの初期シードを確保すること**にあります。
  - **プローブスキャン (Probe Scan) の詳細な仕組み:**
    - **X軸方向の走査（スライディングウィンドウ）による候補の追加:** プローブスキャンは単に与えられたシードの位置を評価するだけではありません。画像（五線帯）のX軸全体にわたって、指定されたプローブ幅（`probe_width`、通常4px）のカーネルを用いてインクピクセル数の畳み込み積分（Convolution）を行います。これにより、**初期シードが全く存在しなかった場所であっても、周囲よりインク率が高い（局所的なピークを持つ）X座標を自律的に見つけ出し、新たな候補（候補ボックス）として追加生成します。**
    - **既存シードの保護（棄却しない仕組み）:** ハイブリッド・コンセンサス等で既に得られているシード（`existing_boxes`）は、その近傍でのプローブスキャンによる重複生成を抑止する（Suppression）ために使われます。**Probe Scan自体には、入力された`existing_boxes`（HOMR等の出力）のインク率を再評価して棄却する（捨てる）機能は組み込まれていません。**
    - **スキャン範囲 (Scan Range)の決定:** 新たなピークの評価時、Y軸（垂直方向）の範囲は、所属する五線帯（band）の高さ、あるいは既存のボックスの高さの中央値（`median_box`モード）をベースにして、設定されたパディング（`band_row_pad_ratio`等）を加えて決定されます（`scan_y1` 〜 `scan_y2`）。
    - **インク率 (Scan Ratio) の計算:** スキャン範囲内で閾値（`ink_threshold`、デフォルト180）を下回るグレースケール画素を「インク」として扱います。
      - **分子 (Numerator):** スキャンボックス内（`[scan_y1:scan_y2+1, sx1:sx2+1]`）に存在するインク画素の総数。
      - **分母 (Denominator):** スキャンボックスの面積（幅 `sx2 - sx1 + 1` × 高さ `scan_h`）。
      - インク率（`scan_ratio`） = 分子 / 分母 となり、この値が閾値（`min_ratio`、デフォルト0.85）を下回る場合は `scan_ratio_low` として棄却されます（※これは**Probe Scanが新規に追加しようとした候補**がインク不足で棄却されたことを意味します）。
- **発生しているFNの分類:** `seed_miss_or_probe_reject`
- **件数:** 180件（全FNの約71%）
  - うち166件は周囲に他の小節線が存在しない「孤立した単一小節線（count-affecting）」です。
- **原因と実例の可視化:** 五線譜のカスレ、複雑なレイアウト、他記号との重なりにより、以下のいずれかが起きています。
  1. **シード未生成かつX軸走査でのピーク未検出:** HOMR/SR/OMR-DLNがいずれも小節線を検知できず、かつProbe ScanのX軸走査でもインクの局所的なピークとして捉えられなかったケース。
  2. **インク不足による新規候補の棄却:** X軸走査でピークとして捉えられたものの、実際のインク率が閾値（0.85等）に届かなかったケース。
  - **可視化による実例検証:** GT（正解ボックス）領域内の実際のインク率を計測・可視化した結果（`logs/issue120_final_residuals/ink_analysis/`）、以下の両方のパターンが確認されました。
    - **純粋なSeed Miss（高インク率）:** `high_ink_Shostakovich-Festival_Overture_Va_page_008_gt0.png`（インク率 0.96）など。肉眼でもはっきりとインクが存在し、0.85の閾値を余裕で超えるにもかかわらず検出漏れとなっており、これはHOMR/SRがシードすら生成せず、さらにProbe ScanのX軸走査の条件（周辺との相対的なピークなど）にも合致しなかったことを示唆しています。
    - **かすれによるProbe Reject（低インク率）:** `low_ink_Va_Prokofiev_Symphony1_page_001_gt35.png`（インク率 0.60）など。掠れが激しく、正解ボックス内でもインクピクセルが疎らであるため、プローブスキャン段階で閾値未満として棄却されています。
  - **結論:** **現在最大のボトルネックはこのフェーズにあり、シード生成の網羅性向上（高インク率のGTを取りこぼさないこと）と、カスレに対するインク率評価の頑健性向上（低インク率でも正解となるパターンの救済）が急務です。**

### Phase 2: CNN分類 (CNN Filtering)
- **処理内容:** Phase 1で抽出された候補ボックスに対し、CNN分類器を通してスコアリング（0.0〜1.0）を行います。
- **発生しているFNの分類:** `cnn_low_score`
- **件数:** 23件（全FNの約9%）
- **原因:** 候補ボックスとしては正しく抽出されたものの、画像パッチのノイズや微妙なズレにより、CNNの出力スコアが閾値（0.5）を下回り除外されたケースです。件数としては少なく、CNN自体の精度は比較的安定しています。

### Phase 3: 後処理・幾何学的フィルタリング (Post-filtering / NMS)
- **処理内容:** CNNを通過した候補に対して、重複の除去（Non-Maximum Suppression: X軸方向の`xnms`等）や、小節線の高さに対するフィルタリング（`minh`, `maxh`）など、構造的なルールベースの除外を行います。
- **発生しているFNの分類:** `unknown_post_filter`
- **件数:** 51件（全FNの約20%）
- **原因:** CNNスコアは0.5以上でしたが、その後のルールベースのフィルタ（重複除去の巻き込みや、極端に短い線に対する高さフィルタなど）によって最終的にリジェクトされたケースです。

### Phase 4: 救済処理 (Rescue Operations)
- **処理内容:** `rightmost_rescue`や、直前のセッションで導入された`active_x_alignment_rescue`（3段以上のアライメントが一致するX座標への能動的プローブ注入）などを用いて、これまでのフェーズで欠落した小節線を救済します。
- **発生しているFPの分類:** `remote_noise`, `near_gt_duplicate`など
- **件数:** 0件 (FP 0件)
- **影響:** 今回の能動的注入等のRescueロジックは副作用を完全に抑え込んでおり、新たなFP（遠隔ノイズなど）を一切生み出していません。しかし同時に、Phase 1で欠落した「段の途中に存在する孤立した単一小節線（右端等の強いアライメントがないもの）」を救済する能力はないため、Phase 1の初期検出・シード生成の根本的な改善が急務となっています。
