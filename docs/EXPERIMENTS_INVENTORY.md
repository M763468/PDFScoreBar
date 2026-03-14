# Experiments Inventory (台帳)

このドキュメントは、`experiments/` ディレクトリ内に存在する過去の実験コード、調査スクリプトの目的、経緯、最新の更新状況、および現在の mainline との関係を整理した台帳です。

---

## 1. 概要

`experiments/` ディレクトリは、主に以下の目的で使用されています。
- 新機能のプロトタイピング
- 特定の課題（Issue）の調査・原因分析
- 機械学習モデルの学習および性能評価
- ハイパーパラメータのスイープ・最適化

原則として、クローズされた Issue に関連する実験コードは「読み取り専用」の歴史的資料として保存されます。

---

## 2. 実験一覧

### 2.1 完了済み・歴史的資料 (Closed / Historical Reference)

| ディレクトリ | 初回コミット | 直近更新 | ステータス | 目的・概要 | 主要ファイル | 備考 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `issue53_probe_rescue` | 2026-03-02 | 2026-03-12 | **Closed** | Issue #53 (Gap Rescue) の効果検証 | `evaluate_full_rescue_v1.py` | Issue #53 は 2026-03-02 にクローズ済み。 |
| `cnn_classifier` | 2026-01-03 | 2026-02-28 | **Archived** | 小節線分類 CNN の学習・評価 | `train.py` | 現在の `logs/cnn_barline_classification/` モデルの学習に使用された正本。 |
| `models` | 2025-12-07 | 2026-03-06 | **Archived** | 外部モデル (OMR-DLN, Grounding DINO等) の性能評価 | `eval_omr_dln.py` | 2026-03のメインラインリファクタリング時に一部修正。 |
| `phase5b_notehead_geom` | 2025-12-21 | 2026-01-30 | **Stale** | 符頭幾何分析フィルタの評価 | `run_union_notehead_geom_eval.py` | |
| `phase5b_b1_1_omrdln_sweep` | 2025-12-21 | 2026-01-29 | **Stale** | OMR-DLN 閾値探索 | `run_omr_dln_sweep.sh` | |
| `phase5b_b2_phase4_filter_check` | 2025-12-21 | 2026-01-29 | **Stale** | 既存フィルタの適用確認 | `build_union_inputs.py` | |
| `fp_reduction` | 2025-12-07 | 2026-01-30 | **Stale** | 誤検出削減のための定量的分析 | `analyze_fps.py` | |
| `gemini` | 2025-12-07 | 2026-01-29 | **Stale** | LLM を用いた小節線検出の試行 | `incontext_barline_detector.py` | |
| `hybrid` | 2025-12-07 | 2026-01-29 | **Stale** | OpenCV 等を用いた古典的手法の検討 | `opencv_candidate_detector.py` | |

#### `models/omr_dln` 内の類似スクリプト比較
- `eval_omr_dln_measures.py`: `YOLOv8m_Measures.pt` を使用し、小節そのものを検出。
- `eval_omr_dln_barlines_from_measures.py`: 小節検出結果の左右の境界を小節線候補として抽出する実験。
- `eval_omr_dln_all.py`: `YOLOv8x_Symbols.pt` を使用し、楽譜上の全シンボルを検出。
- `eval_omr_dln_all_low_conf.py`: 上記の低信頼度 (Low Confidence) 版。Recall の最大化を目的。

---

## 3. レガシー・アーカイブ (Legacy & Archive)

### `experiments/legacy/`
2025年12月の構成変更以前の古いコード群。
- `archive`: 古い OpenCV ベースの検出コード。
- `investigation_20260102`: 2026年年始の不具合調査。
- `tools_archive`: 古い実行シェルスクリプト。

---

## 4. 最新の正本 (Mainline Reference)

実験の結果、製品版（メインライン）として採用された、あるいは現在推奨されるコードの場所。

- **小節線検出の統合ロジック**: `src/pipeline/detection/hybrid.py`
- **評価用共通モジュール**: `src/common/barline_evaluation.py`
- **CNN 推論 (Scoring)**: `tools/cnn_classifier/score_candidates_batch.py`
- **MMR 分類**: `src/measure_numbering/mmr.py`
- **メインパイプライン**: `src/pipeline/main.py`
