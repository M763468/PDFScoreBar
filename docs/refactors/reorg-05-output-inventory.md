# Output & Data Directory Inventory (#99)

このドキュメントは、Issue #99 に基づき、リポジトリ内の主要なデータ・出力ディレクトリ（artifacts, logs, datasets, debug_outputs）の利用状況を整理したものです。

## 1. ディレクトリ概要と分類

| ディレクトリ | 主な用途 | 重要度 | 共有方針 (Worktree) |
| :--- | :--- | :--- | :--- |
| `artifacts/` | CI/CD結果、一時的なツール出力、Issue分析結果 (triage等) | **Low (揮発的)** | **Isolated** (worktree毎に持つ) |
| `logs/` | パイプライン実行結果、中間ファイル、学習済みモデル | **High (動的)** | **Isolated** (基本。ただしモデルは共有) |
| `datasets/` | CNN学習用データ、マイニングされたサンプル | **High (静的/巨大)** | **Shared** (シンボリックリンクまたは共通マウント) |
| `debug_outputs/` | アドホックな可視化画像、古いデバッグ出力 | **Low (レガシー)** | **Isolated** (不要なら削除可) |

---

## 2. 詳細分析

### 2.1 logs/ (Active Pipeline & Models)
現在のメインライン (`src/pipeline/main.py`) および設定ファイル (`configs/`) が依存している重要なパスです。

- **Essential Assets (Reference):**
    - `logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/`: 現在のバリデーションで使用されている最新の CNN モデル。
- **Primary Outputs:**
    - `logs/full_pipeline_runs/`: パイプライン全体の実行ログと結果。
    - `logs/hybrid_generalization/`: ハイブリッド検出の中間結果。
- **Status:** **Active**. パイプライン実行ごとに新しいディレクトリが生成されるため、worktree間では独立させるのが安全ですが、モデルディレクトリへの参照は共通化が必要です。

### 2.2 datasets/ (Heavy Assets)
- **Contents:** `cnn_classifier_v7_base`, `cnn_classifier_v7_hard_mining` 等。
- **Size:** 巨大。
- **Status:** **Stable / Reference**. 学習時以外は読み取り専用。worktree間で重複して持つ必要はなく、共通のデータストレージを参照すべきです。

### 2.3 artifacts/ (Ephemeral / Triage)
- **Contents:** `smoke_test.log`, `issue_triage.txt`, `consistency_check.log` 等。
- **Status:** **Ephemeral**. 特定の作業（Issue triageやSmoke test）の証跡であり、worktreeに紐づくべき情報です。

### 2.4 debug_outputs/ (Ad-hoc)
- **Contents:** `failure_visualizations_v13`, `x2_investigation` 等。
- **Status:** **Legacy / Stale**. 過去の特定の改善フェーズで生成された可視化結果。現在のメインラインからは直接参照されていません。

---

## 3. Worktree 並列実行への提言

Issue #5/#7 の環境統合において、以下のマウント構成を推奨します。

1. **Shared Volume**: `datasets/` および `logs/cnn_barline_classification/...` (モデルパス)
2. **Isolated Volume**: `artifacts/`, `logs/full_pipeline_runs/`, `debug_outputs/`
3. **Consistency Check**: `make check-consistency` を実行して、MANIFEST.md に記載された「Active」な資産が欠落していないかを常に検証可能にする。
