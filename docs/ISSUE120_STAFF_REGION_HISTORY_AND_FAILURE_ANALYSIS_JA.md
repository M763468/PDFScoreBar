# Issue 120 五線領域調査と失敗要因分析

## 1. 現行の五線領域判断方法

現在のE2Eパイプラインにおける五線領域（Staff Region）の判定とフィルタリングは、主に以下の段階に分かれています。

- **Seed generation段階**: 
  `candidate_filter_kwargs.min_staff_overlap_ratio: 0.02` の設定により、候補bbox内の生staff mask（例: `debug_3_staff.png`）ピクセルが占める割合を評価しています。これはピクセル単位の判定ですが、元のline maskが細すぎるため、2%という低い閾値では内外判定として粗く、一部の外側FPもすり抜けます。
- **Pass 2 (probe scan)段階**: 
  現行のconfigでは `enable_heuristic_filters: false` となっているため、この段階で追加・救済される候補に対しては、前述のmask pixel overlapフィルタが適用されません。
- **CNN-stage (Filtering)段階**: 
  - `bands_from=probe_seeds` により、Pass 1で得られたseed boxes群のY座標（`build_row_stats`）から各段のY領域(`[y1, y2]`)を算出しています。
  - 各候補bboxに対し、このY領域（バンド）との垂直方向のオーバーラップ比率（Vertical Overlap Ratio, VOV）を計算します。
  - しかし、現在は `staff_vov_threshold: 0.0` と設定されているため、実質的にいかなるbboxも弾かれることなく通過します。

## 2. 過去コミットにおける変更履歴

関連する設定値やロジックが現在の形に至るまでの主要なコミット履歴は以下の通りです。

- **`2d9d9d7`**: CNNスコアリング段階に `staff-aware geometric filtering` を導入。この際、`staff_vov_threshold` がデフォルト `0.5` として追加されました。
- **`c1e7c10` / `2a0f975`**: probe detectorのリファクタリングを実施し、`staff_bands_from_mask` などのマスクからバンドを生成する基盤が整備されました。
- **`5622d4c`**: Pass 1のseed generationをv12 baselineの挙動に合わせる修正。これにより `enable_heuristic_filters` などの扱いが見直され、Pass 2における候補フィルタが無効化されました。
- **`639d872`**: `staff_vov_threshold` が `0.0` に下げられました。VOV閾値を `0.5` にしておくと、正解の小節線（TP）まで誤って落としてしまい、E2Eのmeasure-count KPIが悪化するため、それを回復（Restore）するための緊急措置でした。この変更により、VOVフィルタは事実上無効化されています。

## 3. 現在の方式が `fp_out_of_staff` を落とせない理由

- **CNN-stageフィルタの無効化**: 最も大きな理由は、最終防衛ラインであるCNN-stageにおいて `staff_vov_threshold: 0.0` となっているため、いかに五線から外れたFP候補であっても除外されない点にあります。
- **Seed生成時の甘い閾値**: Seed generationでのピクセル単位のフィルタ(`min_staff_overlap_ratio`)の閾値が `0.02` と非常に低く、ノイズやかすれとわずかに重なるだけで通過してしまいます。
- **Pass 2候補の無検証**: Pass 2由来の候補に対してはヒューリスティックフィルタ自体が無効化 (`enable_heuristic_filters: false`) されているため、五線領域判定を一切受けずにCNNへ渡ってしまいます。

## 4. なぜ threshold や y-only band を強くすると TP/FN が悪化するか

- **`staff_vov_threshold` を上げた場合（TPのFN化）**: 
  真の小節線であっても、上下に少しはみ出していたり、ページ内の五線がわずかに歪んでいる（skewがある）場合、算出した粗い `[y1, y2]` バンドとのオーバーラップ比率が閾値を下回ってしまい、正しい小節線が脱落します（`Va__Prokofiev_Symphony5/page_002`などで確認済）。
- **`y-only full-width band` (全幅のY領域) の限界**:
  ページ幅全体で共通の1つのY領域(段)を定義するため、五線が水平でない場合、Y領域はその傾きをカバーするために上下に太くなりすぎます。結果として、外側にあるノイズ(FP)がその太いY領域内に収まってしまい生き残るか、逆にバンドをタイトに保つと傾き部分の正解(TP)が落ちてしまうというジレンマに陥ります。

## 5. 生成済み可視化から見える Failure Mode

可視化・実験結果(`staff_region_visual_manifest.json` 等)から、以下のパターンが確認できます。

- **v1 (raw line mask 由来 `debug_3_staff.png`)**: 
  - `Shostakovich-Sym5-Va/page_025` のように、細かいlineセグメントがヒューリスティクスによって誤って過剰結合され、ページ全体が巨大な1つのバンドに崩壊してしまう現象が発生しました（1 bandに崩壊）。
- **v2 (region mask 由来 `*_staff_mask.png`)**:
  - 上記の過剰結合は改善（10 bandsに）されましたが、別の問題が発生しました。
  - `Shostakovich-Sym5-Va/page_010`（-18 under-count）や `Va__Prokofiev_Symphony5/page_021`（-19 under-count）のように、一部の五線領域が欠落したり、複数の段が誤って1つに結合してしまいます。
  - このような不正確で大雑把な y-only バンドを用いてフィルタリングを行うと、安全性が担保できずTPがごっそり抜け落ちてしまいます。

## 6. 次に試すべき replay-only 小実験（提案）

現在の「全幅の y-only バンド」や「単純なピクセル重複」に代わるアプローチとして、以下の実験を提案します。

- **実験テーマ**: `local staff membership (x1, y1, x2, y2)` を用いた局所的五線領域の検証
- **概要**: 
  ページ全幅で一律の `(y1, y2)` バンドを作るのではなく、個々の五線（あるいはその水平方向の一部）を表す `(x1, y1, x2, y2)` の局所的な矩形情報として五線領域を定義します。そして、候補のbboxの中心X座標付近において、有効な staff line group が存在し、かつその局所的なY範囲に収まるか（局部的なVOV）を判定します。
- **検証手順**:
  1. 直接パイプラインの実装を変更する前に、別スクリプトを用意し、既存の出力JSONデータ（候補一覧と生マスク画像）を入力として、ローカルバンドの算出とフィルタリングをシミュレーション（replay-only）します。
  2. **TPの保護確認（最優先）**: 全GTおよび現行のTPに対してこのローカル判定を適用し、TPが落ちないか（count-safeであるか）を評価・可視化します。TPを落とすような設定は採用しません。
  3. **FPの削減確認**: TPが落ちないことを確認できた条件下で、残存している `fp_out_of_staff` の29件や、measure-count に悪影響を与えているFPが正しく弾けるかを評価します。

## 7. ローカル五線領域フィルタの実験結果とパイプライン統合

提案された `local staff membership` 手法の有効性を検証するため、パラメータのグリッド探索（`vov_threshold`: 0.5~0.95, `gap_tolerance`: 20~50）を実施しました。

### パラメータ決定と限界
探索の絶対条件として **「全GTに対するドロップが0件（Count-Safe）」** を設定しました。その結果、以下のことが判明しました。
- `vov_threshold` を `0.6` 以上に設定すると、かすれた五線や極端な傾斜を持つ正解小節線（TP）のオーバーラップ率が足りずにドロップしてしまう。
- `gap_tolerance` を `30` 以下に狭めると、五線が途切れている箇所でローカルバンドが分断され、TPのドロップが発生する。
- したがって、TPを完全に保護できる最大パラメータは `vov_threshold = 0.5`, `gap_tolerance = 40` または `50` となり、この設定下で **29件中20件のFPの除外に成功** しました（最大削減数）。

この結果を受け、パイプライン（`src/pipeline/steps/cnn_scoring.py`）のデフォルトパラメータを `staff_vov_threshold=0.5`, `staff_gap_tolerance=40` に更新し、ローカル五線領域フィルタを正式に組み込みました。

### 残存した9件のFPの原因分析
ローカル五線領域フィルタをすり抜けた9件のFPは以下の通りです。
1. `Shostakovich-Sym5-Va_page_007_box_1794_381`
2. `Shostakovich-Sym5-Va_page_013_box_2752_3703`
3. `Sibelius-Violin_Concerto-Viola_page_004` 内の7件（`box_1237_1141`, `box_1772_1493`, `box_2046_1495`, `box_2100_1491`, `box_617_1136`, `box_912_1138`, `box_968_1138`）

**原因考察**:
- **Shostakovich-Sym5-Va の2件**:
  `page_007` については、段間のテキスト（音部記号や指示文字）の水平方向の密集が偶然「五線幅」に近い密度のインク帯を形成し、それが `gap_tolerance` によって五線の一部として結合（過剰結合）されてしまったため、五線の幅を実際より広く認識しています。
  - `logs/issue120_e2e_recovery/staff_region_filter_experiment_v3_local/fp_analysis/kept/Shostakovich-Sym5-Va_page_007_box_1794_381.png`
  - `logs/issue120_e2e_recovery/staff_region_filter_experiment_v3_local/fp_analysis/kept/Shostakovich-Sym5-Va_page_013_box_2752_3703.png`
- **Sibelius-Violin_Concerto-Viola の7件**:
  `page_004` は手書き要素が強い、または密集したスタッカート/テヌート記号やスラー、文字指示が非常に高い密度で連なっているケースです。これらの記号群が水平方向にある程度の幅をもって存在しているため、ローカルなマスクプロファイル上では「短い五線」と区別がつかなくなり、フィルタ条件（`min_height`や`line_ratio_thresh`）をクリアしてしまっています。
  - `logs/issue120_e2e_recovery/staff_region_filter_experiment_v3_local/fp_analysis/kept/Sibelius-Violin_Concerto-Viola_page_004_box_*.png`

これらの残存FPは、もはや「五線領域か否か」という単純な幾何学的位置関係のフィルタの役割を超えており、後続のCNN分類器やテンプレートマッチング、アスペクト比フィルタ等の「形状自体の識別」によって弾くべき対象であると結論付けられます。
