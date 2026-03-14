# Granular Output & Data Directory Inventory (#99) - Post-Cleanup

このドキュメントは、Issue #99 の一環として実施されたディレクトリ整理（2026-03-14）後の最新状態を記録したものです。

## 1. 削除済みディレクトリ (Removed)

以下のディレクトリは、一時ファイルまたはレガシーな検証結果として完全に削除されました。

- `artifacts/` : 全削除（`issue_triage.txt` 等の一時ファイルも含む）
- `debug_outputs/` : 全削除
- `output/` : 全削除

---

## 2. logs/ (実行ログ・中間生成物・モデル)

`logs/` は整理後も多くの歴史的データを含んでいますが、用途別に分類されています。

| サブディレクトリ | 期間 (Range) | 主な構成 | ステータス・用途 |
| :--- | :--- | :--- | :--- |
| `cnn_barline_classification/` | 2026-01 ~ 2026-03 | PTH, CSV, JSON | **Active**: 学習済みモデルの保管場所。 |
| `full_pipeline_runs/` | 2026-03 ~ (最新) | JSON, PNG | **Active**: 新パイプラインの最新実行結果。 |
| `hybrid_generalization/` | 2025-08 ~ 2026-03 | JSON, PNG, MusicXML | **Mixed**: 最新の中間ファイルと、過去の膨大な試行結果が混在。 |
| `hybrid_pipeline_bench/` | 2026-01 ~ 2026-02 | CSV, JSON, PNG | **Legacy**: 旧オーケストレータ時代のベンチマーク結果。 |
| `homr_eval/` | 2025-08 ~ 2026-02 | MusicXML, PNG, JSON | **Legacy**: Homrベースライン評価の全履歴。 |
| `issue36_prep/` | 2026-02 | JSON, PNG | **Legacy**: 特定Issueの準備用データ。 |
| `archive/` | 2025-08 ~ 2025-11 | PNG, JSON | **Archived**: 昨年の初期実験結果。 |
| `issue23_smoke/` / `issue34_smoke/` | 2026-02 | JSON, PNG | **Reserved**: 回帰テスト用の資産。 |
| `issue31_smoke/` | 2026-02 | JSON | **Legacy**: 一時的なスモークテスト結果。 |
| `analysis/` | 2025-09 ~ 2025-11 | JSON, MD, PNG | **Legacy**: 初期のFN/FP分析結果。 |

---

## 3. datasets/ (CNN学習データセット)

データセットは削除対象外として、全て保持されています。

| サブディレクトリ | 期間 (Range) | 特記事項 |
| :--- | :--- | :--- |
| `cnn_classifier_v1_rebuild` | 2026-01-17 | 13.6万枚のPNGを含む最大セット。 |
| `cnn_classifier_v3_active_learning` | 2026-01-17 | 6.1万枚。 |
| `cnn_classifier_final_v2_fixed` | 2026-01-17 | 6.1万枚。 |
| `cnn_classifier_v5 / v6 / v7` 系統 | 2026-03-02 | 3月のRescue/最新トレーニング用セット。 |

---

## 4. 今後の運用に向けた提言（ディレクトリ管理ルール）

将来的に再びディレクトリが「ごちゃごちゃ」になるのを防ぐため、以下のルールを策定します。

### 4.1 logs/ への集約と構造化
- **原則**: 全ての実行出力（デバッグ画像含む）は `logs/` 配下に集約する。
- **命名規則**: `logs/<category>/<task_id>_<timestamp>/`
    - `category`: `runs` (通常実行), `eval` (評価), `experiments` (実験), `models` (学習)
- **一時ファイル**: 1セッションのみで使い捨てるファイルは、引き続き `temp/` または `artifacts/` (ただしgitignore対象) を検討。

### 4.2 自動クリーンアップの検討
- `make clean-logs`: 30日以上前の `logs/runs/` 配下を削除するターゲットの導入。
- `make check-consistency`: 定期的に Orphan フォルダ（ドキュメントに記載がなく、Active でもないフォルダ）を警告する。

### 4.3 ドキュメントとの同期
- 新しい評価結果ディレクトリを作成した際は、必ず `DEVELOPMENT_LOG.md` または関連Issue報告書にそのパスを明記し、Orphan化を防ぐ。
