# Granular Output & Data Directory Inventory (#99) - Updated

このドキュメントは、Issue #99 に基づき、リポジトリ内の主要なデータ・出力ディレクトリの利用状況と履歴を詳細に調査し、 worktree での共有方針を考察したものです。このバージョンは、一部ディレクトリの整理・削除を反映しています。

## 1. artifacts/ (検証履歴と一時出力)

`artifacts/` は、CI/CD や特定のIssue/タスクの検証結果、一時的なツール出力がバージョン管理されながら蓄積される領域です。**本質的に一時的なファイルであり、長期保存を目的としていません。** ユーザーの指示により、このカテゴリのファイルはセッション間で保持せず、必要に応じて削除されます。

| サブディレクトリ | 期間 (Range) | 主な構成 (ファイル数と種類) | 用途・背景 | 共有方針 (Worktree) |
| :--- | :--- | :--- | :--- | :--- |
| `issue_triage.txt` | 2026-03-14 | TXT (1) | Issue整理結果。セッション毎に更新。 | Isolated |
| その他 (`*_log.txt`, `*_result.json`) | 最新 | TXT, JSON | CI/CD実行ログやスモークテスト結果。 | Isolated |

**総評**: `artifacts/` は開発サイクル中の検証過程で生成される一時的な中間生成物がほとんどです。特に画像ファイルを含むものは容量が大きくなる傾向があり、worktree 間での共有には適しません。多くはタスク完了後に削除されます。

---

## 2. logs/ (実行ログ・中間生成物・モデル)

`logs/` は、プロジェクトの実験、パイプライン実行、モデル開発の中心的な場所です。多くのサブディレクトリが存在しますが、不要なものは整理・削除されました。

| サブディレクトリ | 期間 (Range) | 主な構成 (ファイル数と種類) | 用途・背景 | 共有方針 (Worktree) | ドキュメント参照 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `cnn_barline_classification/issue44*` | 2026-01 ~ 2026-03 | PTH, CSV, JSON | **重要**: CNNモデル (`.pth`) とトレーニング履歴、評価結果。`issue44_iter7_final_rescue_v1/cnn_classifier_best.pth` が最新モデル。 | **Shared** (モデルのみ) | `CNN_RETRAINING_GUIDE.md`, `ISSUE44_BASELINE_STATUS_20260227.md`, `ISSUE44_ITER7_FINAL_REPORT.md` など多数 |
| `full_pipeline_runs/` | 2026-03 ~ (最新) | JSON, PNG (階層構造) | **現在**: 新パイプライン (`src/pipeline/main.py`) の実行結果。各実行が独立したフォルダ。 | Isolated | `NEXT_SESSION_NOTES.md` |
| `hybrid_generalization/` | 2026-03 ~ (最新) | JSON, PNG (階層構造) | ハイブリッド検出の最新の中間ファイル。各実行が独立したフォルダ。 | Isolated | `NEXT_SESSION_NOTES.md` |
| `issue23_smoke/` | 2026-02-07 | YAML, PNG, JSON | 回帰テストで使用されるスモークテスト資産。 | Isolated | `REGRESSION_TEST_WORKFLOW.md` |
| `issue34_smoke/` | 2026-02-07 | JSON | 回帰テストで使用されるスモークテスト資産。 | Isolated | `REGRESSION_TEST_WORKFLOW.md` |

**総評**: `logs/` は、研究開発の過程を記録する非常に重要な場所です。特に `cnn_barline_classification/` に含まれる `.pth` モデルファイルは「読み取り専用」として共有されるべき重要なアセットです。その他の実行ログは、個別の実験やパイプライン実行に紐づくため、worktree間で独立して保持するのが適切です。古い実験ログや一時的なログは、ユーザーの指示により整理・削除されました。

---

## 3. datasets/ (CNN学習データセット)

`datasets/` は、CNNモデルの学習に使用される大量の画像とメタデータを含むディレクトリです。このカテゴリのディレクトリは削除されていません。

| サブディレクトリ | 期間 (Range) | 主な構成 (ファイル数と種類) | 用途・特記事項 | 共有方針 (Worktree) |
| :--- | :--- | :--- | :--- | :--- |
| `cnn_classifier_v1_rebuild` | 2026-01-17 | PNG (13.6万) | 1月のデータ再構築フェーズで生成。非常にファイル数が多い。 | **Shared** |
| `cnn_classifier_v3_active_learning` | 2026-01-17 | PNG (6.1万) | Active Learning用の難解サンプル集。 | **Shared** |
| `cnn_classifier_final_v2_fixed` | 2026-01-17 | PNG (6.1万) | 1月時点の「最終」固定版データセット。 | **Shared** |
| `cnn_classifier_v1_issue44_hcfn_iter*` | 2026-01-03 ~ 02-28 | PNG (6.7万) | 1月作成開始、2月末まで反復的に更新・追加。 | **Shared** |
| `cnn_classifier_v5_rescue_iter1` | 2026-03-02 | PNG (9.1万) | 3月のRescueフェーズで新規生成。 | **Shared** |
| `cnn_classifier_v6_base` / `v7_base` | 2026-03-02 | PNG (9.0万) | 3月の最新トレーニング用ベースセット。 | **Shared** |
| `cnn_classifier_v7_hard_mining` | 2026-03-02 | PNG (501) | Hard Miningによって抽出された最終微調整用。 | **Shared** |

**総評**: `datasets/` は、その巨大なサイズと「読み取り専用」に近い利用形態から、worktree間で完全に共有されるべきディレクトリです。シンボリックリンクまたは共通ボリュームマウントが必須です。

---

## 4. debug_outputs/ (可視化デバッグ)

`debug_outputs/` は、過去のデバッグ作業中に一時的に生成された可視化画像が中心でしたが、ユーザーの指示により **全てのコンテンツが削除されました。**

**総評**: `debug_outputs/` は、過去のデバッグ作業中に生成された一時的な画像ファイルがほとんどでした。今後は `logs/` に一本化される方針であり、既存の `debug_outputs/` は完全に削除されました。

---

## 5. 結論とWorktreeへの提言の更新

上記の詳細調査とディレクトリ整理を踏まえ、`git worktree` での並列実行環境構築に対する提言を更新します。

1.  **Shared Volume (全Worktreeで共有すべきディレクトリ)**:
    -   `datasets/`: 巨大な学習データ。読み取り専用。
    -   `data/`: 楽譜PDF/画像、GTデータ。読み取り専用。
    -   `logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/`: 現行ベストの学習済みモデル（.pthファイル）。読み取り専用。
2.  **Isolated Volume (各Worktree固有に保持すべきディレクトリ)**:
    -   `artifacts/`: 一時的な検証結果やCI/CDログ。タスク完了後に削除推奨。
    -   `logs/full_pipeline_runs/`: 新パイプラインの実行結果。
    -   `logs/hybrid_generalization/`: ハイブリッド検出の中間ファイル。
    -   `logs/issue23_smoke/`, `logs/issue34_smoke/`: 回帰テストアセット。
3.  **Validation**:
    -   `make check-consistency` を活用し、各worktreeから必要な共通アセットにアクセスできるか、Orphanファイルが増えていないかを定期的に確認する運用を継続します。

この更新された詳細レポートが Issue #99 の最終的な調査結果となります。