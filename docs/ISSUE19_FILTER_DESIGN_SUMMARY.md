# Issue #19: CNN前フィルタの設計と実装 - 完了報告

## 1. 概要
本ドキュメントは、Issue #19「CNN前フィルタの設計と実装」が、Issue #44 および #53 の成果によってどのように充足されたかを記述する。

当初の目的であった「CNN Scoring 前に適用するフィルタリング」は、以下の二つのアプローチによって、精度改善と計算コストの最適化の両面で実装・統合が完了した。

## 2. 実装されたフィルタリングロジック

### A. 物理構造ベースの五線クラスタリング (`src/pipeline/probe_detector/bands.py`)
- **内容**: 小節線の高さ（`bbox_h`）を基準とした動的な閾値（`0.5 * bbox_h`）を用いて、五線領域（Staff Band）を正確に特定する。
- **効果**: divisi（近接二段）構造を正しく分離認識できるようになった。これにより、後段の幾何フィルタが正しい小節線を誤って削除するリスクを排除した。

### B. 幾何学的オーバーラップフィルタ (`src/pipeline/filters.py`)
- **内容**: 特定された五線領域と、候補（Candidates）の垂直方向の重なり（Vertical Overlap, VOV）を計算する。
- **統合箇所**: `src/pipeline/cnn_scoring.py` の推論プロセスにおいて、CNN スコア計算と組み合わせて適用。
- **効果**: 五線領域から大きく外れたノイズ（歌詞、装飾記号等）を CNN にかける前に、あるいは CNN スコアと独立に排除可能。

## 3. Issue #19 の Acceptance Criteria に対する充足状況

| 基準 (Acceptance Criteria) | 充足状況 | 根拠 / 参照先 |
| :--- | :--- | :--- |
| フィルタの設計案が文書化されている | 充足 | `docs/ISSUE44_STAFF_BAND_CLUSTERING_FIX.md` |
| 実装位置と入出力が明確化されている | 充足 | `src/pipeline/cnn_scoring.py` 内の `_score_directory` |
| 既存ステップとの整合性が確認されている | 充足 | `feature/batch_orchestrator` ブランチにて統合済み |

## 4. 結論
Issue #19 で意図していた「精度向上のための前処理・フィルタリング」は、物理構造に基づく堅牢なロジックとして `src/pipeline` に実装・統合された。これにより、評価データセット（evaluation2）において Precision 100% / Recall 100% に近い極めて高い精度を達成する基盤が整ったため、本 Issue をクローズする。
