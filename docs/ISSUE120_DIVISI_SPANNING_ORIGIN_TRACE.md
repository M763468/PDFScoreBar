# Issue 120 Divisi/System-Spanning FP Origin Trace Report

## 1. 調査概要

Codex 暫定分類において最大カテゴリ（62件）である `fp_divisi_spanning` について、代表的な例 15 件の混入経路を追跡しました。目的は、これらの system-spanning な FP がパイプラインのどの段階で生成され、なぜ生き残っているかを解明することです。

## 2. 追跡結果まとめ

追跡した 15 件の代表例の混入経路の内訳は以下の通りです。

| 混入段階 (Origin Stage) | 件数 | 推定される混入原因 (Suspected Cause) |
| --- | ---: | --- |
| **OMR (Native)** | 4 | OMR モデル自体が段を跨ぐ小節線やブラケットを一本の線として検出している。 |
| **Probe Seeds (Pass 1)** | 9 | `row_stats` によるバンド生成時に、背の高い OMR 検出結果が近接しているため、複数の段を一つの巨大なバンドとしてクラスタリングしてしまっている。 |
| **Probe Scan (Pass 2)** | 2 | Staff mask (特に SR mask) において、divisi 等で上下の五線がインクで繋がっている箇所を一つの staff band として認識し、そこをスキャンした結果。 |

### 詳細分析: なぜ `probe_seeds` で背の高い候補が出るのか
調査の結果、以下のメカニズムが判明しました：
1. `hybrid_results` (Pass 1 の入力) に OMR 由来の背の高いボックスが含まれている。
2. `row_stats` は `existing_boxes` の中心座標を基にクラスタリングを行うが、背の高いボックスが存在すると、その中心が上下の段の中間に位置するため、隣接する段のボックスを「一つの行」として結合してしまう。
3. 結合された結果、`top` が上の段、`bottom` が下の段という巨大な「偽の staff band」が生成される。
4. `detect_probe_scan` がこの巨大バンドをスキャンし、段間のインク（縦線やブラケット）を小節線として検出する。
5. 生成された候補は `trim_box_to_ink` によって実際のインク範囲まで絞り込まれるが、垂直方向に繋がっているため、依然として段を跨ぐ高さを持つ。

## 3. なぜ生き残っているのか (Filter Failure)

これらの FP が最終結果まで残っている理由は、現在の設定において **`staff_vov_threshold: 0.0`** となっているためです。
Prompt 1 の調査でも示された通り、VOV (Vertical Overlap Ratio) フィルタが無効化されているため、幾何学的に五線領域を逸脱していても除外されません。

## 4. 次の小実験計画 (Proposed Experiment)

これらの system-spanning な FP を効果的に除外するために、以下の実験を提案します。

### 実験テーマ: ローカル五線存在チェックによる system-spanning FP の除外

Prompt 1 で導入された `local_staff_overlap` フィルタを、`fp_divisi_spanning` に対しても適用し、その有効性を検証します。

- **検証手順**:
  1. `docs/ISSUE120_STAFF_REGION_HISTORY_AND_FAILURE_ANALYSIS_JA.md` で成果を上げた `local staff membership` ロジックを使用する。
  2. 候補 bbox の高さが「標準的な 1 段の高さ (約 4.0u)」を大幅に超える場合 (例: `height > 5.0u`)、それは 1 つの五線に収まっていないことを意味する。
  3. このような背の高い候補に対し、その垂直方向の中間に「五線が存在しない隙間」があるか、あるいは「複数の独立した五線領域を跨いでいるか」を判定し、除外する。
  4. **TP の保護**: Shostakovich page 12 等の真の divisi (段を跨ぐ大譜表の小節線) が、VOV 判定によって誤って落とされないことを確認する。

### 実装案の検討
- `detect_probe_scan` 内部で `row_stats` のクラスタリング距離 (`band_cluster_max_dist`) をよりタイトにする (現在は median height の 0.5 倍)。
- ただし、クラスタリングを厳しくしすぎると、歪んだページで同一段内のボックスが分離してしまい、不正確なバンドが生成されるリスクがある。
- したがって、生成段階をいじるよりも、**CNN スコアリング後の `local_staff_overlap` フィルタを強化する** 方が安全かつ効果的であると考えられます。

## 5. 生成された成果物

- `logs/issue120_e2e_recovery/divisi_spanning_origin_trace/trace_examples.csv`
- `docs/ISSUE120_DIVISI_SPANNING_ORIGIN_TRACE.md` (本書)
