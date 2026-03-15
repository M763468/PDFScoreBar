# ツール・スクリプト台帳 (TOOLS.md)

このドキュメントは、`tools/` および `external/` ディレクトリ（ならびに `src/` 配下の主要なランナー）にあるスクリプトとユーティリティの包括的なリストです。それぞれの用途、作成時の文脈、および実質的な最終更新日を管理します。

> [!NOTE]
> 「実質的最終更新」は、一斉フォーマット修正（2026-01-29等）を除いた、ロジックや機能に変更があった最新の日付を示します。

---

## 1. コア・パイプライン & ランナー

エンドツーエンドの小節線検出および小節番号付与パイプラインを実行するための主要なエントリポイントです。

| スクリプト | 用途 | ステータス | 実質的最終更新 | コンテキスト |
| :--- | :--- | :--- | :--- | :--- |
| `src/pipeline/main.py` | **現在の公式エントリポイント**。 | **Active** | 2026-03-12 | フェーズ毎のモジュール化とデータフロー最適化。 |
| `tools/run_full_pipeline.py` | **旧オーケストレータ**。移行前のメインツール。 | **Legacy** | 2026-02-08 | `src/` 移行後はメンテナンスのみ。 |
| `tools/run_hybrid_pipeline.sh` | ハイブリッド検出実行用シェルラッパー。 | **Legacy** | 2026-01-21 | コンテナ設定の動的解決を導入。 |
| `tools/run_eval_experiment.py` | バッチ評価実験用ランナー。 | **Active** | 2026-02-03 | バッチ検出の改善と src 移行の準備。 |

---

## 2. MMR (多小節休符) スイート

多小節休符の番号検出と認識に特化したツール群です。

| スクリプト | 用途 | ステータス | 実質的最終更新 | コンテキスト |
| :--- | :--- | :--- | :--- | :--- |
| `tools/mmr_training/` | MMR 分類モデルの学習用。 | **Active** | 2026-01-30 | 学習データの拡張と精度向上。 |
| `tools/analyze_mmr_errors.py` | MMR 検出エラーの分析。 | **Legacy** | 2026-01-12 | フェーズ 4 OCR 改善 (精度 100% 達成)。 |
| `tools/analyze_mmr_failures_v2.py` | 強化版の失敗分析 (Sibelius 等)。 | **Legacy** | 2026-01-15 | OCR リトライロジックの評価と導入。 |
| `tools/generate_numbering_overrides.py` | MMR 認識結果からの上書き生成。 | **Active** | 2026-03-04 | ログ設計の見直しと進捗トラッキング。 |
| `tools/generate_numbering_overrides_heuristic.py` | ルールベースの上書き生成。 | **Legacy** | 2026-01-12 | CNN 導入以前のメイン手法。 |

---

## 3. 小節線評価 & 分析

小節線検出の品質を測定するための指標と統計ツールです。

| スクリプト | 用途 | ステータス | 実質的最終更新 | コンテキスト |
| :--- | :--- | :--- | :--- | :--- |
| `tools/evaluate_barline_rules.py` | マッチングルール (IoU 等) の評価。 | **Active** | 2026-02-28 | 閾値の動的設定と KPI 算出の導入 (Issue #48)。 |
| `tools/evaluate_and_visualize.py` | シンプルな評価と可視化。 | **Legacy** | 2026-03-05 | 評価ロジックの微調整。 |
| `tools/analyze_barline_distribution.py` | 小節線間隔の統計分析。 | **Legacy** | 2026-01-04 | 小節番号付与ロジックとの統合。 |
| `tools/analyze_failure_cases.py` | 失敗ケースの自動グループ化。 | **Legacy** | 2025-12-28 | 検出失敗の体系的な分類を試行。 |

---

## 4. 地面真実 (GT) 管理

小節線の Ground Truth を作成、管理するためのツールです。

| スクリプト | 用途 | ステータス | 実質的最終更新 | コンテキスト |
| :--- | :--- | :--- | :--- | :--- |
| `tools/gt_relabel_gui/` | Web ベースの GT 修正ツール。 | **Active** | 2026-02-12 | 複縦線等のラベリング基準への対応。 |
| `tools/gt_relabel_support.py` | GUI のバックエンド。 | **Legacy** | 2025-12-25 | 初期実装。 |
| `tools/barline_gt_helper.py` | GT JSON 操作。 | **Legacy** | 2025-11-20 | 初期実装。 |
| `tools/populate_missing_gt.py` | GT の自動補完。 | **Active** | 2026-02-22 | 複縦線分割ロジックとの統合。 |

---

## 5. デバッグ & 可視化

| スクリプト | 用途 | ステータス | 実質的最終更新 | コンテキスト |
| :--- | :--- | :--- | :--- | :--- |
| `tools/render_barline_boxes_overlay.py` | 小節線オーバーレイ描画。 | **Legacy** | 2025-12-13 | 超解像 (Real-ESRGAN) 統合時の対応。 |
| `tools/visualize_measure_numbering.py` | 小節番号付与結果の可視化。 | **Legacy** | 2026-01-04 | 初期の可視化機能実装。 |
| `tools/debug_ocr_candidates.py` | OCR 候補領域のインスペクション。 | **Legacy** | 2026-01-08 | OCR バリデーションの改善。 |

---

## 6. 構造的推論 (実験的/レガシー)

| スクリプト | 用途 | ステータス | 実質的最終更新 | コンテキスト |
| :--- | :--- | :--- | :--- | :--- |
| `tools/structural_gap_fit.py` | グリッド適合の試み。 | **Legacy** | 2025-12-28 | 実装を試みたが精度不足により断念。 |
| `tools/structural_omr_system_consensus.py` | システム特定ロジック。 | **Legacy** | 2025-12-28 | 実験的な実装。 |
| `tools/split_double_barlines.py` | 複縦線分割。 | **Active** | 2026-02-22 | パイプライン本体への統合とリファクタリング。 |

---

## 7. メンテナンス & その他

| スクリプト | 用途 | ステータス | 実質的最終更新 | コンテキスト |
| :--- | :--- | :--- | :--- | :--- |
| `tools/check_repo_consistency.py` | リポジトリ整合性チェック。 | **Active** | 2026-03-14 | 新規作成 (Issue #95)。 |
| `tools/utils/safe_gh_post.sh` | 安全な GitHub 投稿スクリプト。 | **Active** | 2026-03-13 | |
| `tools/add_measure_numbers.py` | 小節番号の書き込みユーティリティ。 | **Active** | 2026-03-10 | |
| `tools/analyze_divisi_logic.py` | divisi 判定ロジックの分析。 | **Active** | 2026-01-30 | |
| `tools/analyze_fn_prokofiev.py` | Prokofiev における FN 分析。 | **Active** | 2026-03-06 | |
| `tools/vram_monitor.sh` | VRAM 使用量監視。 | **Active** | 2026-03-03 | |
| `src/pdf_to_images.py` | PDF レンダリング。 | **Active** | 2026-02-06 | `pymupdf` への依存追加とロジック修正。 |

---

## 8. 外部依存関係 (`external/`)

- `external/oemer/`: oemer サブモジュール。
- `external/homr/`: homr クローン (ベースライン)。
- `external/omr_dln/`: YOLOv8 実験用。
