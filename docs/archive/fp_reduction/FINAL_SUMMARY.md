# Barline FP Reduction Project: Final Summary

> [!NOTE]
> This document is a focused summary of the FP-reduction optimization project (Dec 2025).
> For the full chronological development history of the entire repository, see [docs/DEVELOPMENT_LOG.md](../DEVELOPMENT_LOG.md).
> **Repo Restructure (Dec 2025)**: Scripts mentioned here (e.g., `analyze_fps.py`) have been moved to `experiments/fp_reduction/`.

## 1. プロジェクト目的
**「Page 3」における誤検出（False Positive: FP）の削減**
- **初期状態**: True Positive (TP) 152, False Positive (FP) ~35, False Negative (FN) 0.
- **制約**: **FN（検出漏れ）を絶対に増やさないこと**（Recall 1.0 維持）。

## 2. 実施した手法（Heuristics 1〜5）

| 手法 | 内容 | 結果 | ステータス |
| :--- | :--- | :--- | :--- |
| **Heuristic 1: Safe Filter** | 局所的特徴量（Noteheadとの距離, Height, Width, Overlap）によるAND条件フィルタリング | **成功** (-5 FPs, 0 FN) | **採用 (Enabled)** |
| **Heuristic 2: Staff Crossing** | 五線譜との交差数 (<3) と Overlap (<5) を組み合わせたフィルタリング | **失敗** (18 FN) | 却下 (Disabled) |
| **Heuristic 3: Cluster Resolution** | 近接候補 (<15px) の中で「Strength Score」が最大のものを残す | **失敗** (57 FN) | 却下 (Disabled) |
| **Heuristic 4: Tight Duplicate** | 極めて近い (<3px) 重複候補をマージ | **失敗** (3 FN, 0 FP減) | 却下 (Disabled) |
| **Heuristic 5: Measure Grid** | DPを用いて「小節構造」として最適な配置を探索（水平方向のギャップ整合性） | **失敗** (108 FN) | 却下 (Disabled) |

## 3. 分析と結論

### Heuristic 1 だけが成功した理由
Heuristic 1 は「明らかにゴミと分かる極小のノイズ（Noteheadに近い微小点）」のみをターゲットにしました。これは音楽的な構造（小節線そのもの）に踏み込まず、**アーティファクト除去**に徹したため、安全に機能しました。

### 他の手法（H2〜H5）が失敗した共通原因
残りの30個の FP は、**「断片化した True Positive」と幾何学的・文脈的に区別がつかない** ことが判明しました。
- **TPの断片化**: Page 3 の正解小節線（TP）の多くは、かすれや途切れにより「高さが低い」「線が細い」「五線譜をまたがない」という特徴を持っています。
- **FPの類似性**: これらは符幹（Stem）や歌詞の一部ですが、形状が「断片化したTP」と酷似しています。
- **文脈の欠如**: 水平方向の配置（Measure Grid）を見ても、TP自体が不規則（あるいは重複検出）であるため、TPとFPを区別する有意なギャップの違いが見出せませんでした（TPの68%が4px以下のギャップを持つ）。

### Homr / Oemer の限界
現在のパイプライン（Homr/Oemer）は、**セグメンテーション（画素レベルの検出）の段階でバーラインを断片化して出力**しています。
- ポストプロセス（Heuristic）でこれをつなぎ合わせたり選別したりするのは、情報が欠落しているため限界があります。
- 「強い線」を優先すると、「弱い（断片化した）正解」まで消してしまう構造的な問題があります。

### 最終結論
**現状の視覚的ヒューリスティックにおいて、これ以上の FP 削減は不可能である。**
- 現在の FP 30個を削減しようとすると、必ず TP（特に品質の悪いバーライン）を巻き添えにします。
- プロジェクト目標である「FNゼロ」を維持する限り、**Heuristic 1（Safe Filter）適用後の状態（152 TP, 30 FP, 0 FN）が最適解**です。

## 4. 次フェーズに向けた提案
視覚的なルールベース処理（Heuristic）はやり尽くしました。次は別のアプローチが必要です。詳細なロードマップは `docs/future/roadmap.md` を参照してください。

1.  **GUI 補助**: 人間が目視確認できるツールを作成し、怪しい候補をハイライトする。
2.  **上流モデルの改善**: OMRモデル自体（セグメンテーションモデル）を再学習させ、断片化を減らす。
3.  **音楽的文脈の導入**: 音符や拍子記号を認識し、「ここに小節線がなければリズムが合わない」という論理的な推論を行う。
