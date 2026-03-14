# Granular Output & Data Directory Inventory (#99)

このドキュメントは、Issue #99 に基づき、リポジトリ内の主要なデータ・出力ディレクトリ（artifacts, logs, datasets, debug_outputs）の利用状況と履歴を詳細に調査し、 worktree での共有方針を考察したものです。

## 1. artifacts/ (検証履歴と一時出力)

`artifacts/` は、CI/CD や特定のIssue/タスクの検証結果、一時的なツール出力がバージョン管理（v1, v2...）されながら蓄積される領域です。**本質的に一時的なファイルであり、長期保存を目的としていません。**

| サブディレクトリ | 期間 (Range) | 主な構成 (ファイル数と種類) | 用途・背景 | 共有方針 (Worktree) |
| :--- | :--- | :--- | :--- | :--- |
| `issue25_final_full_verification_v*` | 2026-03-08 ~ 03-09 | JSON (多数) | Issue #25 (超解像) の反復検証結果。主に座標データ。 | Isolated |
| `issue25_global_verification_final` | 2026-03-14 | JSON (408) | 超解像最適化の最終グローバル検証結果。 | Isolated |
| `issue25_x2_exact_verification` | 2026-03-08 | PNG, JSON, MusicXML (合計 4238) | x2超解像の精度を厳密に検証した際の大規模成果物。画像を含むため容量大。 | Isolated (削除推奨) |
| `manual_sr_x4` / `prokofiev_p1_sr_x4_v2` | 2026-03-06 | PNG, JPG, JSON (合計 71) | 手動でのSR実行結果。画像ファイルを含むため容量大。 | Isolated (削除推奨) |
| `verify_v12_SRx*` / `verify_sr_bypass` | 2026-03-07 ~ 03-12 | JSON, PNG | v12モデルを用いた特定条件の検証。 | Isolated |
| `issue_triage.txt` | 2026-03-14 | TXT (1) | Issue整理結果。セッション毎に更新。 | Isolated |
| その他 (`*_log.txt`, `*_result.json`) | 最新 | TXT, JSON | CI/CD実行ログやスモークテスト結果。 | Isolated |

**総評**: `artifacts/` は、その名の通り「成果物」ですが、開発サイクル中の検証過程で生成される一時的な中間生成物がほとんどです。特に画像ファイルを含むものは容量が大きくなる傾向があり、worktree 間での共有には適しません。多くはタスク完了後に削除可能です。

---

## 2. logs/ (実行ログ・中間生成物・モデル)

`logs/` は、プロジェクトの実験、パイプライン実行、モデル開発の中心的な場所です。非常に多くのサブディレクトリが存在し、時期と用途が多岐にわたります。

| サブディレクトリ | 期間 (Range) | 主な構成 (ファイル数と種類) | 用途・背景 | 共有方針 (Worktree) | ドキュメント参照 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `homr_eval/` | 2025-09 ~ 2025-12 (一部2026-02まで) | MusicXML, PNG, JPG, JSON, CSV, MD | 初期〜中期のHomrベースライン評価ログ。多くの実験を含む。`sr_inprocess_baseline` は長期参照される。 | Isolated (モデルはShared) | `ENVIRONMENTS.md` |
| `oemer_eval/` | 2025-09 ~ 2025-11 | MusicXML, PNG, JPG, JSON, CSV, MD | 昨年のOemerベースライン評価ログ。 | Isolated | なし |
| `cnn_barline_classification/issue44*` | 2026-01 ~ 2026-03 | PTH, CSV, JSON | **重要**: CNNモデル (`.pth`) とトレーニング履歴、評価結果。`issue44_iter7_final_rescue_v1/cnn_classifier_best.pth` が最新モデル。 | **Shared** (モデルのみ) | `CNN_RETRAINING_GUIDE.md`, `ISSUE44_BASELINE_STATUS_20260227.md`, `ISSUE44_ITER7_FINAL_REPORT.md` など多数 |
| `hybrid_pipeline_bench/` | 2026-01 ~ 2026-02 | PNG, JSON, CSV | 旧オーケストレータ時代のバッチ評価ベンチマーク。 | Isolated | `ISSUE46_FN_DET_EXPERIMENT_LOG.md` |
| `full_pipeline_runs/` | 2026-03 ~ (最新) | JSON, PNG (階層構造) | **現在**: 新パイプライン (`src/pipeline/main.py`) の実行結果。各実行が独立したフォルダ。 | Isolated | `NEXT_SESSION_NOTES.md` |
| `hybrid_generalization/` | 2026-03 ~ (最新) | JSON, PNG (階層構造) | ハイブリッド検出の最新の中間ファイル。各実行が独立したフォルダ。 | Isolated | `NEXT_SESSION_NOTES.md` |
| `model_experiments/` | 2025-12 | JSON, PNG, MD | YOLO-World, OMR-DLN 等の外部モデル評価ログ。 | Isolated | `model_experiments/barline_detection_future_plan.md` |
| `phase3_staff_consistency/` / `phase4_notehead_geom/` | 2025-12 | JSON, PNG, MD | 幾何学的フィルタリングの実験結果と詳細分析。 | Isolated | `DEVELOPMENT_LOG.md` |
| `issue39_staff_mask/` | 2026-02-22 | JSON, PNG | 五線譜マスク検出の分析結果。 | Isolated | なし |
| `issue46_combo_sweeps/` | 2026-02-23 | CSV, JSON | Issue #46 の組み合わせスイープ結果。 | Isolated | `ISSUE46_FN_DET_EXPERIMENT_LOG.md` |
| `analysis/night_run/` | 2025-09 ~ 2025-11 | JSON, LOG, MD, PNG | Nightly Runでの分析結果、FN/FPホットスポット。 | Isolated | `DEVELOPMENT_LOG.md` |
| `test/` (`test_sr/`) | 2026-02-04 | JSON, PNG, MusicXML | 特定の機能のテスト実行ログ。 | Isolated | なし |
| `archive/` | 2025-08 ~ 2025-11 | MusicXML, PNG, JPG, JSON | 過去の実験のアーカイブ。 | Isolated | `DEVELOPMENT_LOG.md` |

**総評**: `logs/` は、研究開発の過程を記録する非常に重要な場所です。特に `cnn_barline_classification/` に含まれる `.pth` モデルファイルは「読み取り専用」として共有されるべき重要なアセットです。その他の実行ログは、個別の実験やパイプライン実行に紐づくため、worktree間で独立して保持するのが適切です。

---

## 3. datasets/ (CNN学習データセット)

`datasets/` は、CNNモデルの学習に使用される大量の画像とメタデータを含むディレクトリです。

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

`debug_outputs/` は、特定のデバッグ作業中に一時的に生成された可視化画像が中心です。

| サブディレクトリ | 期間 (Range) | 主な構成 (ファイル数と種類) | 用途・背景 | 共有方針 (Worktree) | ドキュメント参照 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `failure_visualizations_v3 ~ v13` | 2026-03-02 | PNG (多数) | 3月2日に実施された大規模な失敗ケースの可視化調査。 | Isolated (削除可) | `AI_AGENT_STRATEGY_2026.md`, `LESSONS.md`, `CODEX_GEMINI_COLLAB.md`, `ISSUE44_ITER*` reports |
| `x2_investigation` | 2026-03-08 | PNG (28) | 3月8日に実施されたx2超解像の調査。 | Isolated (削除可) | なし |
| `fn_visualizations` | 2026-03-02 | PNG (4) | FN (False Negative) ケースの可視化。 | Isolated (削除可) | `ISSUE44_ITER5_INTERMEDIATE_REPORT.md` |
| その他 (`*.png`) | 2026-03-02 | PNG (数点) | 各種デバッグ画像。 | Isolated (削除可) | なし |

**総評**: `debug_outputs/` は、過去のデバッグ作業中に生成された一時的な画像ファイルがほとんどです。`ENVIRONMENTS.md` に記載の通り、今後は `logs/` に一本化される方針であり、**既存の `debug_outputs/` は基本的に削除して問題ありません。** ただし、過去のIssue報告で参照されている場合があるため、その文脈を考慮して削除を検討します。

---

## 5. 結論とWorktreeへの提言の更新

上記の詳細調査を踏まえ、`git worktree` での並列実行環境構築に対する提言を更新します。

1.  **Shared Volume (全Worktreeで共有すべきディレクトリ)**:
    -   `datasets/`: 巨大な学習データ。読み取り専用。
    -   `data/`: 楽譜PDF/画像、GTデータ。読み取り専用。
    -   `logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/`: 現行ベストの学習済みモデル（.pthファイル）。読み取り専用。
2.  **Isolated Volume (各Worktree固有に保持すべきディレクトリ)**:
    -   `artifacts/`: 一時的な検証結果やCI/CDログ。タスク完了後に削除推奨。
    -   `logs/full_pipeline_runs/`: 新パイプラインの実行結果。
    -   `logs/hybrid_generalization/`: ハイブリッド検出の中間ファイル。
    -   `logs/homr_eval/`, `logs/oemer_eval/`, `logs/model_experiments/` など過去の実験ログ: 必要に応じて参照するが、worktree間で競合しないよう独立。
    -   `debug_outputs/`: 過去のデバッグ可視化。基本的に削除推奨。
3.  **Validation**:
    -   `make check-consistency` を活用し、各worktreeから必要な共通アセットにアクセスできるか、Orphanファイルが増えていないかを定期的に確認する運用を継続します。

この更新された詳細レポートが Issue #99 の最終的な調査結果となります。