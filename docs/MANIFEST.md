# Asset Registry (MANIFEST.md)

このドキュメントは、リポジトリ内の最新かつ公式（メインライン）な資産（モデル、データ、コード）を管理するためのレジストリです。

> [!IMPORTANT]
> このリポジトリの作業用 worktree では、`.gitignore` されている `datasets/` や `logs/` 内の資産が欠落している場合があります。実体はメインの開発環境に配置されています。
> また、`make check-consistency` を実行することで、このマニフェストに登録されていない「迷子（Orphan）」の資産を特定し、リポジトリの肥大化や情報の陳腐化を防ぐことができます。

---

## 1. Core Pipeline (Mainline)

現在の公式な実行パスと設定です。

| 項目 | パス / 内容 |
| :--- | :--- |
| **メインエントリポイント** | `src/pipeline/main.py` |
| **推奨設定ファイル** | `configs/evaluation2_e2e_verification_full.yaml` | フル機能の最終検証用 |
| **スモークテスト設定** | `configs/smoke_test.yaml` | 疎通確認用 |
| **検証報告書 (最新)** | `docs/ISSUE13_E2E_VERIFICATION_REPORT.md` (2026-03-13) | |

---

## 2. Official Models & Modules

検証済みの主要なモデルファイルと、パイプラインを構成する核心的なモジュールです。

### 2.1 Models
| モデル名 | 推奨パス | 備考 |
| :--- | :--- | :--- |
| **Barline CNN** | `logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth` | 小節線候補のスコアリング用 |
| **OMR-DLN (YOLO)** | `external/omr_dln/models/public_models/YOLOv8m_Measures.pt` | 小節領域・境界の検出用 |
| **MMR Classifier** | `tools/mmr_training/models/mmr_classifier_best.pth` | 複数小節休みの識別用 |
| **Real-ESRGAN** | `(Container) /opt/models/` | 超解像用 |

### 2.2 Core Modules
| モジュール | パス | 役割 |
| :--- | :--- | :--- |
| **Orchestrator** | `src/pipeline/orchestrator.py` | パイプライン全体の制御 |
| **Detection Logic** | `src/pipeline/detection/hybrid.py` | ハイブリッド検出の統合 |
| **Measure Numbering** | `src/measure_numbering/pipeline.py` | 小節番号の付与ロジック |
| **MMR Engine** | `src/measure_numbering/mmr.py` | MMR 検出と OCR の統合 |

---

## 3. Official Data & Datasets

評価および学習に使用される公式データです。

| データ種別 | パス | 備考 |
| :--- | :--- | :--- |
| **評価セット (Eval 2)** | `data/evaluation2/` | 2025-12-30 GT 再構築済み |
| **学習データセット** | `datasets/` | gitignore 対象。メイン環境の ext4 領域に配置推奨 |
| **Ground Truth Policy** | `docs/GT_PREPARATION_POLICY.md` | ラベリング基準 |

---

## 4. Environment

| 項目 | 名称 / パス | 備考 |
| :--- | :--- | :--- |
| **開発コンテナ** | `sr_eval_gpu` | Dockerfile 参照 |
| **Python 実行環境** | `(Container) /opt/venv_sr/bin/python` | コンテナ内 uv 環境 |
| **サブコンテナ** | `Dockerfile.homr` | Homr 評価用 |
| **超解像モデル** | `(Container) /opt/models/` | Real-ESRGAN モデル内蔵 |

---

## 5. Repository Maintenance

リポジトリの整合性と品質を維持するためのツールです。

| ツール | パス | 役割 |
| :--- | :--- | :--- |
| **整合性チェック** | `tools/check_repo_consistency.py` | 資産の存在、ドキュメントの鮮度、Orphanファイルの確認（ガイドライン） |
| **構成図生成** | `make repo-tree` | ディレクトリ構造の可視化 |
