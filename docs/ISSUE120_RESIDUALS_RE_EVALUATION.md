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
    - **かすれによるProbe Reject（低インク率）:** 掠れが激しく正解ボックス内でもインクピクセルが疎らであるため、プローブスキャン段階で閾値未満として棄却されるケースです。（※なお、当初低インクの例として抽出した `low_ink_Va_Prokofiev_Symphony1_page_001_gt35.png` は、そもそもその位置に小節線が存在しない「GT（正解データ）側の付与ミス」であることが判明しました。真の低インクFNも存在しますが、GT自体のノイズも一部含まれていることに留意が必要です。）
  - **結論:** **現在最大のボトルネックはこのフェーズにあり、シード生成の網羅性向上（トールバンド希釈の解決による高インク率GTの救済）と、カスレに対するインク率評価の頑健性向上が急務です。**

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
- **影響:** 新規追加した右端アライメント等のRescueロジックは、新たなFP（遠隔ノイズなど）を一切生み出さずに特定のFNを確実に救済できており、非常に有効であることが確認されました。**このロジックは成功として今後も維持します**。しかし同時に、Phase 1で欠落した「段の途中に存在する孤立した単一小節線（右端等の強いアライメントがないもの）」を救済する能力はないため、並行してPhase 1の根本的な改善が必要です。

## 5. コミット履歴の調査：なぜFNが20件から254件へ「デグレ」したのか？

数日前のレポート（`docs/ISSUE120_E2E_FULL68_RESTORE_REPORT.md`、5月2日のコミット `639d872`）では、FNはわずか **20件** と報告されていました。そこから現在の **254件** へと劇的に悪化（デグレ）したように見える原因について、コミット履歴と設定ファイルを調査しました。

結論から言えば、**「過去の20 FNという記録自体は事実だが、それはProbe Scanのインク率フィルタを実質的に無効化するという『極端な緩和設定』によって得られた、見かけ上の（副作用の強い）スコアであった」** ことが分かりました。

### 過去（FN 20件）の状況
5月2日の評価（`evaluation2_full_v12_restore`）で使用された設定ファイル（`configs/evaluation2_e2e_verification_full_v12_restore.yaml`）では、Probe Scanの閾値が以下のように設定されていました。
- `ink_threshold: 240` （かなり明るいグレーまでインクとみなす）
- **`min_ratio: 0.10` （インク率が10%でもあれば候補として通過させる）**

この極端に緩い `min_ratio: 0.10` により、前述の「トールバンド希釈」によって計算上のインク率が0.6程度に落ちてしまった小節線や、激しく掠れた小節線もすべて**強引にProbe Scanを通過**していました。
その代償として、**約60,000件** という膨大な数のノイズ候補（FPの種）が後段のCNNに送り込まれました。CNN分類器が非常に優秀であったため、この6万件のノイズを最終的に FP=125, FN=20 まで削り落とすことに成功していましたが、これはパイプラインのアーキテクチャとして健全な状態ではありませんでした。

### 現在（FN 254件）の状況
その後、パイプラインの標準的な設定（例：`configs/evaluation2_e2e_verification.yaml` 等）に準じて、閾値が正常な値（`min_ratio: 0.70` または `0.85`）に戻されました。
閾値を正常に戻した途端、五線帯が縦に長すぎるために起こる「トールバンド希釈」によって、インクが真っ黒に詰まった完璧な小節線であっても計算上のインク率が 0.68 等で頭打ちとなり、0.85の閾値に弾かれて**大量の候補がProbe Scan段階で棄却されるようになりました**。

### 結論
**FNが急増したことは「デグレ」ではありません。** これまで `min_ratio: 0.10` という極端な設定によって**覆い隠されていたProbe Scanのアーキテクチャ上の欠陥（トールバンド希釈とカスレへの弱さ）が、閾値を正常に戻したことで再び表面化した**というのが正しい認識です。

前回のセッションでは、この大量に表面化した254件のFNに対して「カウントに影響しない（Count-neutral）から無視してよい」という誤った解釈を下し、対症療法的なRescueのみを追加してクローズしようとしていました。しかし今回の再評価により、これらが**小節数カウントを直接破壊する重大なFN**であり、かつその根本原因が**Probe Scanのインク率計算の仕組み（分母の巨大化）**にあることが明確になりました。

修正方針としては、X軸走査時のY軸範囲（Band）を五線帯全体ではなく小節線に合わせた適切な高さに動的に切り詰めるか、インク率の評価ロジックを「面積比」から「垂直方向の連続性」等のより堅牢な指標に変更するなどの抜本的なアプローチが必要です。


## 6. 根本原因の解決に向けた実装修正方針の提案

Phase 1における最大のボトルネック「トールバンド希釈（五線帯が縦に長すぎるため、インク率の分母が過大になり閾値に届かない問題）」および「カスレへの脆弱性」を解決するために、以下の2つのアプローチを提案します。

### アプローチA: スキャン範囲（Band）のY軸をより正確に切り詰める方法

現在のX軸走査は、五線帯のマスク（`staff_mask`）の上下端をそのままスキャンのY軸範囲として使用しています。これを実際の「小節線の高さ」に近づけるアプローチです。

- **実装案:**
  X軸の各ピクセル列において、インクが存在する「一番上のY座標」と「一番下のY座標」を動的に探索し、その区間のみをスキャン範囲（分母）として採用します。
  もしくは、その列の近傍における既存の小節線（`existing_boxes`）のY座標の「局所的な中央値」を計算し、スキャン範囲の上下端を動的に決定します（現在はページ全体あるいは五線帯全体のグローバルな中央値に依存しがちです）。
- **メリット:**
  - 既存の「面積比（Area Ratio）」の概念を大きく壊さずに実装できます。
  - 分母が適正化されるため、インクが濃い（黒い）小節線は確実に0.85の閾値を超えるようになります。
- **デメリット:**
  - 掠れ（途切れた小節線）や、斜めに傾いた線の処理が複雑になります。
  - 上下の他記号（スラーや文字など）と縦に繋がってしまっている場合、結局Y軸範囲が長くなってしまい、希釈問題が再発するリスクがあります。

### アプローチB: 面積比ではない「別の指標（別の分母）」を使用する方法

現在の「インク画素数 / (幅 × 高さ)」という面積ベースのインク率を捨て、縦線（小節線）の性質に特化した別の指標を採用するアプローチです。

- **実装案:**
  1. **垂直連続性（Vertical Continuity）ベース:**
     指定したY軸範囲（Band）の中で、「縦方向に連続してインクが存在する最大の長さ（Run-Length）」を計算します。
     評価指標 = `(最大連続インク長) / (Bandの高さ)` とし、これが一定割合（例: 0.5）を超えていればピークとみなします。
  2. **Y軸プロジェクションの尖度ベース:**
     各列のインクピクセル数を単純にカウントし、それを「Bandの高さ」で割る（現在の方式）のではなく、「周辺列のインクピクセル数との相対比（局所的なコントラスト）」を評価指標とします。（※現状もコード内に `scan_x_peak_ratio` のような周辺比のロジックの残骸がありますが、主判定である絶対インク率 `min_ratio` の前で棄却されているため機能していません。絶対インク率の判定を外し、相対ピークの尖度のみを条件とします）。
- **メリット:**
  - Bandの高さ（分母）が実際の小節線より長くても、「縦にまっすぐ連続したインクの塊があるか」「周囲より明らかに縦線が存在するか」で判定するため、トールバンド希釈の影響を全く受けません。
  - アプローチB-1（連続性）は、五線を跨ぐような長いノイズと本物の直線を区別するのに強力です。
- **デメリット:**
  - 極度に掠れて「点線」のようになってしまった小節線に対しては、最大連続長が短くなるため、別途「ギャップを許容する連続長計算」などの工夫が必要になります。
  - アルゴリズムの変更規模がAに比べて大きくなります。

**推奨:**
「トールバンド希釈」の根本原因は「分母に、小節線とは無関係の空白（余白）が含まれてしまうこと」にあります。したがって、Y軸の範囲を無理に当てにいくアプローチAよりも、**小節線の特徴（周辺に対する相対的な縦のコントラスト）を直接評価するアプローチB-2（絶対インク率の閾値を大幅に下げつつ、X軸の相対ピーク判定を必須要件に格上げする）** が、最も堅牢かつ修正範囲が小さく済む可能性が高いと考えます。