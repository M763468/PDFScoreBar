# Granular Output & Data Directory Inventory (#99)

このドキュメントは、各サブディレクトリ内のファイル構成とタイムスタンプ範囲を詳細に調査した結果をまとめたものです。

## 1. artifacts/ (検証履歴と一時出力)

`artifacts/` は、特定のIssueやタスクの検証結果がバージョン管理（v1, v2...）されながら蓄積されています。

| サブディレクトリ | 期間 (Range) | 主な構成 | 用途・背景 |
| :--- | :--- | :--- | :--- |
| `issue25_final_full_verification_v*` | 2026-03-08 ~ 03-09 | JSON (多数) | Issue #25 (超解像) の反復検証。各ページごとの座標データ。 |
| `issue25_global_verification_final` | 2026-03-14 (最新) | JSON (408) | 超解像最適化の最終グローバル検証結果。 |
| `issue25_x2_exact_verification` | 2026-03-08 | PNG, JSON, MusicXML | x2超解像の精度を厳密に検証した際の大規模成果物。 |
| `manual_sr_x4` / `prokofiev_p1_sr_x4_v2` | 2026-03-06 | PNG, JPG, JSON | 手動でのSR実行結果。画像ファイルを含むため容量大。 |
| `verify_v12_SRx*` / `verify_sr_bypass` | 2026-03-07 ~ 03-12 | JSON, PNG | v12モデルを用いた特定条件の検証。 |

---

## 2. datasets/ (CNN学習データセット)

同一ディレクトリ内に異なる時期のデータが混在している箇所を特定しました。特に `v5` 以降は最近の生成です。

| サブディレクトリ | 期間 (Range) | 主な構成 | 用途・特記事項 |
| :--- | :--- | :--- | :--- |
| `cnn_classifier_v1_rebuild` | 2026-01-17 | PNG (13.6万) | 1月のデータ再構築フェーズで生成。非常にファイル数が多い。 |
| `cnn_classifier_v3_active_learning` | 2026-01-17 | PNG (6.1万) | Active Learning用の難解サンプル集。 |
| `cnn_classifier_final_v2_fixed` | 2026-01-17 | PNG (6.1万) | 1月時点の「最終」固定版データセット。 |
| `cnn_classifier_v1_issue44_hcfn_iter*` | 2026-01-03 ~ 02-28 | PNG (6.7万) | 1月作成開始、2月末まで反復的に更新・追加。 |
| `cnn_classifier_v5_rescue_iter1` | **2026-03-02** | PNG (9.1万) | 3月のRescueフェーズで新規生成。 |
| `cnn_classifier_v6_base` / `v7_base` | **2026-03-02** | PNG (9.0万) | 3月の最新トレーニング用。 |
| `cnn_classifier_v7_hard_mining` | **2026-03-02** | PNG (501) | Hard Miningによる最終微調整用。 |

---

## 3. logs/ (実行ログ・中間生成物)

`logs/` 内は、過去の実験結果と最新のパイプライン実行結果が並列に存在しています。

| サブディレクトリ | 期間 (Range) | 主な構成 | 用途・背景 |
| :--- | :--- | :--- | :--- |
| `homr_eval/2025*` | 2025-09 ~ 2025-12 | MusicXML, PNG | 昨年実施されたHomr評価。構造は MusicXML + 画像 + JSON。 |
| `homr_eval/sr_inprocess_baseline` | 2025-08 ~ 2026-02 | PNG, JSON | 長期間にわたって参照・更新されているベースライン。 |
| `oemer_eval/2025*` | 2025-09 ~ 2025-11 | MusicXML, PNG | 昨年のOemer評価。 |
| `issue53_full_eval_rescue_v1` | **2026-03-02** | JSON (多数) | 3月のRescue検証ログ。ファイルはJSONのみ。 |
| `full_pipeline_runs/` | 2026-03-14 (最新) | フォルダ構造 | 新パイプラインの実行結果。実行ごとに最新化される。 |
| `hybrid_generalization/` | 2026-03-14 (最新) | フォルダ構造 | ハイブリッド検出の最新の中間ファイル。 |

---

## 4. debug_outputs/ (可視化デバッグ)

大部分が2026年3月初旬に集中しています。

| サブディレクトリ | 期間 (Range) | 主な構成 | 用途 |
| :--- | :--- | :--- | :--- |
| `failure_visualizations_v3 ~ v13` | 2026-03-02 | PNG | 3月2日に実施された大規模な失敗ケースの可視化調査。 |
| `x2_investigation` | 2026-03-08 | PNG | 3月8日に実施されたx2超解像の調査。 |

---

## 調査結果からの考察

1.  **データの混在**: `datasets/` フォルダ内では、同じ `v1_issue44` 系統でも1月生成のものと2月末まで更新されたものが混在しており、学習データの「鮮度」に注意が必要です。
2.  **検証の反復**: `artifacts/` 内の `issue25` 関連は3月8日から9日にかけて非常に高頻度で更新されており、この時期に超解像ロジックの集中打鍵が行われたことがわかります。
3.  **画像アセットの所在**: `artifacts/` にも `manual_sr_x4` のように重い画像データが一部含まれており、worktree共有時にこれらをどう扱うか（除外するか共有するか）の判断材料になります。
