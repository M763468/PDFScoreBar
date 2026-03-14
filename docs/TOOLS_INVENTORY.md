# ツール・スクリプト・インベントリ (台帳)

このドキュメントは、`tools/` および `external/` ディレクトリにあるスクリプトとユーティリティの包括的なリストです。それぞれの用途、作成時の文脈、および相互関係を管理します。

---

## 1. コア・パイプライン & ランナー

エンドツーエンドの小節線検出および小節番号付与パイプラインを実行するための主要なエントリポイントです。

| スクリプト | 用途 | コンテキスト / 作成時期 |
| :--- | :--- | :--- |
| `src/pipeline/main.py` | **現在の公式エントリポイント**。モジュール化されたパイプライン全体を制御します。 | 2026-02-05 (Issue #18) |
| `tools/run_full_pipeline.py` | **旧オーケストレータ**。`src/` への移行前に使用されていた以前のエントリポイントです。 | 2026-01-20 |
| `tools/run_hybrid_pipeline.sh` | 特定のコンテナ設定でハイブリッド検出パイプラインを実行するためのシェルラッパー。 | 2026-01-21 |
| `tools/run_eval_experiment.py` | バッチ評価実験を実行するためのランナー。 | 2026-02-03 |

---

## 2. MMR (多小節休符) スイート

多小節休符の番号検出と認識に特化したツール群です。

| スクリプト | 用途 | コンテキスト / 作成時期 |
| :--- | :--- | :--- |
| `tools/mmr_training/` | MMR 分類モデル (ResNet18) の学習スクリプトを含むディレクトリ。 | 2026-01-12 |
| `tools/analyze_mmr_errors.py` | MMR 検出エラーと分類精度の詳細な分析。 | 2026-01-12 |
| `tools/analyze_mmr_failures_v2.py` | Sibelius 形式のレイアウトや OCR リトライロジックに特化した、強化版の失敗分析。 | 2026-01-15 |
| `tools/generate_numbering_overrides.py` | 学習済み MMR CNN と OCR を使用して JSON 上書きファイルを生成。 | 2026-01-04 |
| `tools/generate_numbering_overrides_heuristic.py` | **代替/レガシー**。CNN の代わりにルールベースのヒューリスティックで上書きを生成。 | 2026-01-12 |
| `tools/global_batch_mmr_eval.py` | データセット全体を通じた MMR 検出のバッチ評価。 | 2026-01-15 |

---

## 3. 小節線評価 & 分析

小節線検出の品質を測定するための指標と統計ツールです。

| スクリプト | 用途 | コンテキスト / 作成時期 |
| :--- | :--- | :--- |
| `tools/evaluate_barline_rules.py` | 小節線マッチングルール (IoU, Center-Anchor) の包括的な評価。 | 2026-02-27 (Issue #48) |
| `tools/evaluate_and_visualize.py` | 定性的な可視化をサポートする、よりシンプルな評価スクリプト。 | 2025-12-13 |
| `tools/analyze_barline_distribution.py` | 【実験的】水平方向の小節線の隙間と重なりの統計的分析。 | 2025-10-15 |
| `tools/analyze_failure_cases.py` | 検出失敗ケース (FN/FP) の自動グループ化と分析。 | 2025-12-28 |
| `tools/compare_batch_structure.py` | 異なるバッチ実行間でのディレクトリ構造と結果の比較。 | 2026-01-30 |

---

## 4. 地面真実 (GT) 管理

小節線の Ground Truth を作成、クレンジング、管理するためのツールです。

| スクリプト | 用途 | コンテキスト / 作成時期 |
| :--- | :--- | :--- |
| `tools/gt_relabel_gui/` | 小節線 GT の手動修正と検証のための Web ベースのツール。 | 2025-12-25 |
| `tools/gt_relabel_support.py` | GT 修正 GUI のバックエンドロジック。 | 2025-12-25 |
| `tools/barline_gt_helper.py` | 小節線 GT JSON ファイルを操作するための一般的なユーティリティ。 | 2025-11-20 |
| `tools/populate_missing_gt.py` | 既存の予測値をベースに、新しい画像の GT を自動的に生成。 | 2026-01-12 |
| `tools/inspect_gt_image.py` | 視覚的な検証のために、画像上に GT ボックスを重ねて表示。 | 2025-12-30 |

---

## 5. デバッグ & 可視化

パイプラインの中間段階を調査するための診断ツールです。

| スクリプト | 用途 | コンテキスト / 作成時期 |
| :--- | :--- | :--- |
| `tools/render_barline_boxes_overlay.py` | 検出された小節線を画像オーバーレイとしてレンダリングする標準ツール。 | 2025-10-10 |
| `tools/visualize_measure_numbering.py` | 【実験的な】最終的な小節番号付与結果の可視化。 | 2026-01-04 |
| `tools/debug_ocr_candidates.py` | 生の OCR 候補領域と数値の詳細なインスペクション。 | 2026-01-08 |
| `tools/coordinate_annotator.py` | 画像上のピクセル座標を特定するためのツール。 | 2025-12-15 |
| `tools/crop_debug_image.py` | デバッグのために、大きな楽譜画像から特定の領域を切り出すユーティリティ。 | 2026-01-07 |

---

## 6. 構造的推論 (実験的/レガシー)

レイアウトを考慮した検出を模索したスクリプト。多くは実験的な位置づけです。

| スクリプト | 用途 | ステータス |
| :--- | :--- | :--- |
| `tools/structural_gap_fit.py` | 検出された隙間に基づいて、規則的なグリッドに小節線を適合させる試み。 | 実験的 |
| `tools/structural_omr_system_consensus.py` | 楽譜のシステムを特定するための、ページを跨いだコンセンサスロジック。 | 実験的 |
| `tools/split_double_barlines.py` | 単一の幅広な検出結果を複縦線に分割するロジック。 | 統合済み (リファクタリング) |

---

## 7. メンテナンス & その他

| スクリプト | 用途 | コンテキスト / 作成時期 |
| :--- | :--- | :--- |
| `tools/check_repo_consistency.py` | **メンテナンス用**。Orphan ファイルや古いドキュメントを特定します (Issue #95)。 | 2026-03-14 |
| `tools/vram_monitor.sh` | GPU 負荷の高い実行中に VRAM 使用率を追跡するバックグラウンドスクリプト。 | 2026-01-20 |
| `src/pdf_to_images.py` | 高品質な PDF ページレンダリングツール。 | 2026-02-06 |
| `tools/utils/safe_gh_post.sh` | 一時ファイルを使用して安全に GitHub コメントを投稿するためのラッパー。 | 2026-02-08 |

---

## 8. 外部依存関係 (`external/`)

詳細は `external/README.md` を参照してください。

- `external/oemer/`: oemer OMR ライブラリの Git サブモジュール。
- `external/homr/`: homr リポジトリのクローン (ベースライン検出器)。
- `external/omr_dln/`: YOLOv8 ベースの小節検出実験。
- `external/models/`: 共有モデルの重み保存場所。
