# Output & Data Directory Inventory (#99)

このドキュメントは、Issue #99 に基づき、リポジトリ内の主要なデータ・出力ディレクトリ（artifacts, logs, datasets, debug_outputs）の利用状況と履歴を整理したものです。

## 1. ディレクトリ概要と分類

| ディレクトリ | 主な用途 | 重要度 | 共有方針 (Worktree) |
| :--- | :--- | :--- | :--- |
| `artifacts/` | CI/CD結果、一時的なツール出力、検証ログ | **Low (揮発的)** | **Isolated** (worktree毎に保持) |
| `logs/` | パイプライン実行結果、中間ファイル、学習済みモデル | **High (動的)** | **Isolated** (基本。モデルは共有) |
| `datasets/` | CNN学習用データ、マイニングされたサンプル | **High (静的/巨大)** | **Shared** (シンボリックリンク/共通マウント) |
| `debug_outputs/` | アドホックな可視化画像、古いデバッグ出力 | **Low (レガシー)** | **Isolated** (不要なら削除可) |

---

## 2. 時系列・用途別詳細分析

プロジェクトの各フェーズで生成された主要なアセットの「いつ・何のために」を整理しました。

### 2.1 logs/ (Active Pipeline & Models)
最も複雑で重要なディレクトリです。

| サブディレクトリ | 時期 | 用途・背景 | 共有推奨 |
| :--- | :--- | :--- | :--- |
| `homr_eval/` | 2025-09 ~ 2025-12 | 初期~中期のHomrベースライン評価ログ。多くの実験を含む。 | No |
| `oemer_eval/` | 2025-09 ~ 2025-11 | Oemerベースライン評価ログ。 | No |
| `phase3_staff_consistency/` | 2025-12 | 段の一貫性フィルタ（幾何学的制約）の実験結果。 | No |
| `phase4_notehead_geom/` | 2025-12 | 符頭位置に基づくFP削減フィルタの実験。 | No |
| `cnn_barline_classification/` | 2026-01 ~ | **重要**: CNNモデル（pth）とトレーニング履歴。 | **Yes** (Modelのみ) |
| `hybrid_pipeline_bench/` | 2026-01 ~ 2026-02 | 旧オーケストレータ時代のバッチ評価ベンチマーク。 | No |
| `full_pipeline_runs/` | 2026-03 ~ | **現在**: 新パイプライン (`src/pipeline/main.py`) の実行結果。 | No |
| `hybrid_generalization/` | 2026-03 ~ | **現在**: 新パイプラインの中間生成物（中間座標JSON等）。 | No |

### 2.2 datasets/ (Heavy Assets)
CNNモデルの精度向上のための学習データ群です。

| サブディレクトリ | 時期 | 用途・内容 |
| :--- | :--- | :--- |
| `cnn_classifier_v1_rebuild` | 2026-01 | 初期の再構築データセット。 |
| `cnn_classifier_v3_active_learning` | 2026-01 | Active Learning用にマイニングされた難解なサンプル。 |
| `cnn_classifier_v6_base` / `v7_base` | 2026-03 | 最新の学習用ベースセット。 |
| `cnn_classifier_v7_hard_mining` | 2026-03 | Hard Case Miningによって抽出された最終学習用データ。 |

### 2.3 artifacts/ (Ephemeral / Verification)
特定の作業の証跡や、ワークツリー固有のログです。

| ファイル/ディレクトリ | 時期 | 用途 |
| :--- | :--- | :--- |
| `issue_triage.txt` | 2026-03-14 | 直近のIssue整理結果。 |
| `issue25_final_full_verification_*` | 2026-03-09 | Issue #25 (超解像最適化) の最終検証結果。 |
| `smoke_test.log` | 2026-03-14 | 開発中の疎通確認用。 |
| `consistency_check.log` | 2026-03-14 | 整合性チェックの実行結果。 |

### 2.4 debug_outputs/ (Legacy / Ad-hoc)
現在は直接の実行には寄与しない可視化結果です。

| サブディレクトリ | 時期 | 用途 |
| :--- | :--- | :--- |
| `failure_visualizations_v3 ~ v13` | 2026-01 ~ 2026-03 | 各改善フェーズでの失敗ケース可視化。 |
| `x2_investigation` | 2026-03 | x2超解像の効果検証時に生成。 |

---

## 3. Worktree 並列実行への提言

Issue #5/#7 における並列実行環境（git worktree）の構築では、以下のマウント構成を推奨します。

1. **Shared Volume (全Worktreeで共有)**:
    - `datasets/` (巨大な学習データ)
    - `logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/` (現行ベストモデル)
    - `data/` (楽譜PDF/画像、GTデータ)
2. **Isolated Volume (各Worktree固有)**:
    - `artifacts/` (直近のタスクログ、分析結果)
    - `logs/full_pipeline_runs/`, `logs/hybrid_generalization/` (実行結果の混同を避ける)
    - `debug_outputs/` (アドホックな調査結果)
3. **Validation**:
    - `make check-consistency` を活用し、各worktreeから必要な共通アセットにアクセスできるか、Orphanファイルが増えていないかを定期的に確認する。
