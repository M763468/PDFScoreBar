# E2E Seed Generation Discrepancy Investigation (Epic #120)

## 1. 調査目的
`HANDOFF.md` シナリオB に従い、E2Eパイプラインの Seed 生成結果 (`intermediate/probe_seeds`) が、過去のベースラインである `scoring_input_eval2_v12` と同等になるかを調査しました。

事前の実装計画 (`implementation_plan.md.resolved`) では「Pass 1 と Pass 2 が1段階に結合されてしまったこと」が精度劣化の主因とされていましたが、実際に E2E パイプラインを修正して Pass 1 を再現しようとしたところ、出力される候補枠（シード）の数がベースライン（約678件/ページ）に対して極端に少ない（数十件）という別の致命的な差異が発覚しました。

コードレベルで過去のシード生成スクリプト (`tools/repro_accuracy/reproduce_clean_seed_v12.py`) と現在の E2E パイプライン (`orchestrator.py`, `hybrid.py`) を比較調査した結果、以下の 4つの複合的な原因 により、中間結果が全く異なるものになっていることが判明しました。

## 2. 発見された 4つの根本差異 (Root Causes)

### 差異 1: Hybrid Consensus の結合方式 (UNION vs INTERSECTION)
- **v12 (過去)**: `reproduce_clean_seed_v12.py` では、Baseline, SR, OMR の各モデル出力を **UNION (論理和)** して全候補をかき集め、IoU > 0.8 で重複排除したものをシードとして `run_probe_scan_batch` に渡していました（Recall 最大化のため）。
- **E2E (現在)**: `HybridDetector` 内の `apply_hybrid_consensus_filter()` は **INTERSECTION (論理積)** として実装されており、「Baseline の候補のうち、SR または OMR の裏付けがあるもの」だけを抽出しています。これにより、初期シードの時点で候補数が極端に絞り込まれてしまっています。

### 差異 2: Heuristic フィルターの適用対象とタイミング
- **v12 (過去)**: `run_probe_scan_batch` 内ではヒューリスティックフィルターを一切かけず (`enable_heuristic_filters=False`)、出力されたすべての候補（Hybrid 既存枠＋新規生成枠）に対して、後から手動で `filter_probe_candidates(existing_boxes=[])` を実行し、全候補を平等にフィルタリングしていました。
- **E2E (現在)**: `run_probe_scan_batch` 内で `enable_heuristic_filters=True` と指定しているため、Hybrid 既存枠はフィルターをバイパスして保持され、新規生成枠だけがフィルタリングされます。これにより、条件を満たさない質の低い既存枠がそのまま残る一方、既存枠の `median_h` に依存する閾値 (`too_short_vs_existing_median`) が発動し、新規生成枠が過剰に破棄される構造になっています。

### 差異 3: 実行解像度 (1x vs 2x) と スケーリングの二重適用バグ
- **v12 (過去)**: シード生成は **1x (オリジナル) 解像度** の画像上で実行されていました。
- **E2E (現在)**: `orchestrator.py` は `enable_sr=True` の場合、Pass 1 (シード生成) も含めてすべて **2x (SR) 解像度** の画像に適用します。
  - **二重スケーリングのバグ**: 現在の `run_probe_scan_batch` は 2x 解像度で実行した後、出力する JSON 座標を 1x にダウンスケールせずに保存しています。Pass 2 がその JSON を読み込むと、再び `input_image_scale=2.0` を適用するため、**シードが 4x 解像度**にスケーリングされてしまうという重大なバグが内在しています。

### 差異 4: Morphological Closing と DPI 依存性の影響 (`low_paper_overlap` による大量破棄)
- **v12 (過去)**: 300 DPI や 424 DPI などの多様な画像を使っていました。
- **E2E (現在)**: `pdf_to_images.py` により、すべて **360 DPI** に変換されます。さらに 2x SR 画像でフィルタリングを実行すると、`filter_probe_candidates` 内の `_build_page_mask()` で使用している `(15, 15)` のカーネルサイズ（Morphological Closing）が相対的に小さくなり、太くなった黒いバーラインを「紙(Paper)」として白で塗りつぶせなくなります。
  - 結果として、バーラインの候補枠において `low_paper_overlap` が大量発生し、90% 以上の正しい候補がドロップされていました。

---

## 3. 修正計画 (Proposed Plan for Reproducing v12 Seeds)

上記の差異を解消し、`scoring_input_eval2_v12` と同等のシードを E2E パイプライン内で正確に復元するための修正計画です。（※本ドキュメント作成時点では未実装）

### 1. Hybrid Consensus を Pass 1 向けに UNION 対応化
- `src/pipeline/steps/hybrid_consensus.py` の `apply_hybrid_consensus_filter` に `mode="union"` オプションを追加し、Baseline/SR/OMR の全枠を IoU ベースでマージできるようにする。
- `HybridDetector` で `hybrid_consensus_mode` を設定可能にし、Pass 1 のための広いシードソースを確保する。

### 2. `run_probe_scan_batch` のスケーリング出力バグ修正
- `src/pipeline/steps/probe_scan.py` の `run_probe_scan_batch` にて、JSON出力時に `input_image_scale` が 1.0 より大きい場合は、保存前に必ず候補枠を 1x (オリジナル) 解像度にダウンスケールして保存するように修正する。（Pass 2 での 4x 爆発を防ぐため）

### 3. Orchestrator の Pass 1 (Seed Generation) を v12 完全互換に分離
`src/pipeline/detection/orchestrator.py` の `_run_probe_scan()` における `Pass 1` のブロックを以下のように書き換えます。
- 実行画像 (`images`) を SR ではなく **1x オリジナル画像 (`self.images`)** とし、`input_image_scale=1.0` で実行する。
- `staff_mask_dir=None` とし、`band_source="row_stats"` を適用して広域スキャンを行う。
- `enable_heuristic_filters=False` として `run_probe_scan_batch` を実行し、全候補をそのままダンプする。
- 直後に `orchestrator.py` 内で、`filter_probe_candidates` を `existing_boxes=[]` として全候補に対して平等に手動適用し、最終的なクリーンシード (1x解像度) を完成させる。

### 次のステップ
ユーザーからの承認が得られ次第、上記の修正コードを実装し、E2E パイプライン上で生成された `probe_seeds` が `scoring_input_eval2_v12` のファイルサイズ/候補数と同等になることを再確認してから、最終的な E2E の推論・評価に進みます。
