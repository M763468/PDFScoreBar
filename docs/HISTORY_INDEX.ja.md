# PDFScoreBar 履歴索引

<!-- translation: {"original":"HISTORY_INDEX.md","source":{"sha256":"db030cd94f34349da8e28ccb7d76b54acd1d77a431930043f586bf0e8f925fb4"},"state":"reviewed"} -->

[English / 原文](HISTORY_INDEX.md)（英語正本）

翻訳元: same PR / SHA-256 `db030cd94f34349da8e28ccb7d76b54acd1d77a431930043f586bf0e8f925fb4`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

この文書はナビゲーションの層であり、2つ目の情報の正本ではありません。

## 目的

PDFScoreBar には長い調査の歴史があります。この索引は、古い Issue の状態、引き継ぎのメモ、タスクの計画、実験の日誌を現在のリポジトリの状態として扱わずに、保守担当者や AI エージェントが適切な過去の証拠を見つけられるようにするためのものです。

まず現在のソース・テスト・config と、現在の長く残す文書を使います。過去のリンクをたどるのは、要件、受け入れた契約、回帰の防止、以前の判断を説明する場合だけにします。

## 読む順序

現在のタスクでは次の順に進めます。

1. 現在の依頼から、作業中の Issue / PR を特定します。
2. 現在のソース・テスト・config と、その対象の GitHub の状態を確認します。
3. そのサブシステムに関係する、正規の現在の文書を読みます。
4. 下の系譜は、必要な過去の証拠のためだけに使います。
5. 過去の記録にあるブランチの HEAD、実行タグ、ローカルのパス、ブロックの理由、`next step` の記述は、再確認するまで古いものとして扱います。

関係のない Issue への新しいコメントは、新しいというだけの理由で、現在のタスクの受け入れた契約に優先しません。

## 正規の現在の入口

- [`docs/PIPELINE_ARCHITECTURE.ja.md`](PIPELINE_ARCHITECTURE.ja.md) — 現在の本番アーキテクチャ
- [`docs/history/TWO_HOMR_MILESTONE.md`](history/TWO_HOMR_MILESTONE.md)（英語） — 固定した、受け入れ済みの #274 / [PR #279](https://github.com/M763468/PDFScoreBar/pull/279) の比較のマイルストーン
- [`docs/DOCUMENTATION_INVENTORY.md`](DOCUMENTATION_INVENTORY.md)（英語） — 文書の分類
- [`docs/ENVIRONMENTS.ja.md`](ENVIRONMENTS.ja.md) — 保守対象の実行環境
- [`docs/BRANCH_POLICY.ja.md`](BRANCH_POLICY.ja.md) — ブランチ方針
- [`docs/dev/VALIDATION_POLICY.ja.md`](dev/VALIDATION_POLICY.ja.md) — 検証方針
- [`docs/BARLINE_MATCHER.ja.md`](BARLINE_MATCHER.ja.md) — 検出器のマッチング・評価の契約
- [`docs/GT_PREPARATION_POLICY.ja.md`](GT_PREPARATION_POLICY.ja.md) — GTの方針
- [`docs/SCRIPT_MANAGEMENT.md`](SCRIPT_MANAGEMENT.md) — スクリプトの所有とライフサイクル

## 過去の系譜

### 現在の本番の性能（#447）

- [Issue #447 の統合結果](performance/issue447-results.md)（英語） — 受入条件の判定、加算できない時間の解釈、証拠の系譜、実装のフォローアップ #454/#458/#459。

### Stage-E / 検出器の再構築

主な系譜:

#117 → #119 / #120 → #133–#163

最初に読むもの:

- [Issue #120](https://github.com/M763468/PDFScoreBar/issues/120) と、その受け入れたフォローアップの Issue コメント（再構築の詳細な調査の履歴）
- [Issue #136](https://github.com/M763468/PDFScoreBar/issues/136)（Stage-B のスコアリング・NMS の因果の境界）
- [Issue #142](https://github.com/M763468/PDFScoreBar/issues/142)（CNN スコアリングの NMS を既定で無効にする受け入れた判断と、PR #154 の証拠）
- [Issue #141](https://github.com/M763468/PDFScoreBar/issues/141)（Stage-E のパイプライン全体の検証の記録）
- [Issue #163](https://github.com/M763468/PDFScoreBar/issues/163)（却下した HOMR/SR の重ね合わせの実験、証拠のブランチ・commit、固定したサブセットでの再現の詳細）
- [`docs/history/ISSUE120_EVALUATION_CONTRACT.md`](history/ISSUE120_EVALUATION_CONTRACT.md)
- [`docs/history/ISSUE120_ARTIFACT_RETENTION.md`](history/ISSUE120_ARTIFACT_RETENTION.md)
- [`docs/refactors/issue120/`](refactors/issue120/)

詳細な調査には Issue のスレッドを使います。古い再構築のブランチのモデルや、古い `next step` の節を、現在のブランチの状態として解釈しないでください。

### CNN 分類器 / 候補のマッチング

主な系譜:

#44 → #45 / #46 / #51 / #53 → その後の検出器の再構築 → #296 / [PR #310](https://github.com/M763468/PDFScoreBar/pull/310)

最初に読むもの:

- [Issue #44](https://github.com/M763468/PDFScoreBar/issues/44)（evaluation2 の時期の CNN のベースライン、過去の能動学習のメモ、五線の帯・学習のまとめ）
- [Issue #46](https://github.com/M763468/PDFScoreBar/issues/46)（検出器・CNN の残差の実験と、その最終的な台帳）
- [Issue #51](https://github.com/M763468/PDFScoreBar/issues/51)（修正した残差の分類と、15件の判定）
- [Issue #296](https://github.com/M763468/PDFScoreBar/issues/296) / [PR #310](https://github.com/M763468/PDFScoreBar/pull/310)（検証済みの Stage-E の経路での、現在の生成側の候補に合わせた EfficientNet-B0 の採用）
- 現在のモデル・閾値の挙動については、現在の `configs/dense_full_pipeline.yaml`、ソース、テスト

古い ResNet18 の学習計画と、誤検出に基づく能動学習のガイドは過去のものです。現在の本番の CNN の契約として使わないでください。

### 小節番号付け / MMR

主な系譜:

#94 → #194 / #197 → #200 / #208 / #212 / #213 → #221 / #223 / #224 → #244 / #257 / #264 → #276 / #277

最初に読むもの:

- [Issue #94](https://github.com/M763468/PDFScoreBar/issues/94)（初期の番号付け・MMR のマイルストーンと調査の履歴のまとめ）
- [`docs/refactors/issue94/MMR_CURRENT_STATE.md`](refactors/issue94/MMR_CURRENT_STATE.md)（保守対象・範囲を限った MMR の現状の分析と、その後の68ページでの評価）
- [`docs/refactors/issue414/MMR_STAFF_CONSENSUS.md`](refactors/issue414/MMR_STAFF_CONSENSUS.md)（五線の同点時の OCR の集約、保持している Full68 の比較、残している却下した候補）
- [`docs/history/DEVLOG_MEASURE_NUMBERING.md`](history/DEVLOG_MEASURE_NUMBERING.md)（簡潔な過去のマイルストーンの要約が役立つ場合だけ。以前の日誌の正確な文章は Git の履歴にあります）
- [`docs/refactors/issue194/`](refactors/issue194/)
- [`docs/refactors/issue201/`](refactors/issue201/)
- [Issue #244](https://github.com/M763468/PDFScoreBar/issues/244)（段の先頭の番号付けについての詳細な調査）
- 受け入れた、幾何を基準にし直した下流の契約については #264 / #274 の記録
- 現在の挙動については現在のソース・テスト

過去の台帳は過去のナビゲーションであり、現在の仕様ではありません。

### 楽章を考慮した番号付け

主な系譜:

#268 → #333

最初に読むもの:

- [`docs/MOVEMENT_BOUNDARY_CONTRACT.ja.md`](MOVEMENT_BOUNDARY_CONTRACT.ja.md)（現在の確定済み境界の利用側と、候補・根拠の契約）
- [`docs/history/ISSUE333_MOVEMENT_BOUNDARY_INVESTIGATION.md`](history/ISSUE333_MOVEMENT_BOUNDARY_INVESTIGATION.md)（拡張した7曲のコーパス、ホールドアウト・モデルの比較、レビュー用生成器の証拠、自動検出の判定）
- 番号付けの挙動については現在のソース・テスト

Issue #268 は利用とリセットの意味を所有します。Issue #333 は、小節レベルの楽章の開始の根拠を見つけられず、レビュー専用の幾何による候補の生成器を承認し、黙って動く自動の生成器は承認しませんでした。

### 新しい検出器の復元 / コネクタを考慮したグループ化 / HOMR の補助の再利用

主な系譜:

#245 → #252 / #254 / #255 → #264 → #274 / [PR #279](https://github.com/M763468/PDFScoreBar/pull/279) → #280

最初に読むもの:

- [`docs/PIPELINE_ARCHITECTURE.ja.md`](PIPELINE_ARCHITECTURE.ja.md)（現在の検出器の入力の来歴の契約を含む）
- [`docs/history/TWO_HOMR_MILESTONE.md`](history/TWO_HOMR_MILESTONE.md)（英語）
- [Issue #245](https://github.com/M763468/PDFScoreBar/issues/245) / [PR #251](https://github.com/M763468/PDFScoreBar/pull/251)（`fresh_upstream` と `precomputed_candidate_route` の違いの背景にある詳細な調査）
- さらに詳細な調査が必要な場合は #255 / #264 / #274 の Issue の記録

受け入れた [PR #279](https://github.com/M763468/PDFScoreBar/pull/279) のマイルストーンは、固定した比較の基準です。その後の本番の変更で、受け入れたその記録をさかのぼって書き換えることはありません。

### 性能の最適化

初期の系譜:

#25 / #60 / #70 / #78 → その後の本番の最適化の作業

最近の系譜:

#281 → #283 / #284 → #293 → #294

最初に読むもの:

- [Issue #25](https://github.com/M763468/PDFScoreBar/issues/25)（初期の SR の精度・コストの調査と、復元したタスクログの所見）
- [Issue #60](https://github.com/M763468/PDFScoreBar/issues/60)（初期のデータフロー・MMR のバッチ処理の測定）
- [Issue #70](https://github.com/M763468/PDFScoreBar/issues/70)（初期の 8GB VRAM / tile=400 の性能のマイルストーン）
- [Issue #78](https://github.com/M763468/PDFScoreBar/issues/78)（圧縮した過去の Phase 1–6 のベンチマークの台帳）
- #281（#274 以降で最初の、時間の内訳の枠組み）
- #283（current-x4 の HOMR の最適化）
- #284 / [PR #292](https://github.com/M763468/PDFScoreBar/pull/292)（Real-ESRGAN の最適化）
- #293（#292 以降に測定した積み残し）
- #294 は、作業中のタスクが実際にベースラインの HOMR の置き換えに関わる場合だけ

古いベンチマークの推奨は証拠であり、現在の調整の既定値ではありません。過去の数値に基づいて行動する前に、現在のソース・config と、作業中の性能の Issue を確認してください。

### 下流に影響する x=580 の誤った小節線

主な系譜:

#196 → #202 → #205 / #206 → #296

新しい作業では、#296 を過去の入口として勧めます。その Issue の本文が、古い実験を恒久的な設計の制約ではなく証拠として明示的に分類し直しているためです。

### 製品化 / 利用者向けのワークフロー

主な系譜:

#225 → #226 / #227 / #228 / #229 → #236。関連する #230 / #280

最初に読むもの:

- [`docs/refactors/issue226/`](refactors/issue226/)
- [`docs/refactors/issue227/`](refactors/issue227/)
- [`docs/refactors/issue228/`](refactors/issue228/)
- [`docs/refactors/issue229/`](refactors/issue229/)
- [`docs/manual_correction_review_package.ja.md`](manual_correction_review_package.ja.md)
- [`docs/corrected_final_output.ja.md`](corrected_final_output.ja.md)

現在の挙動については、現在のソースと現在の利用者向け文書を使います。

### 開発の運用 / AI のワークフロー

役立つ目印:

#6 / #45 / #63 / #168 / #173 / #185 / #190 / #230 / #241 / #258 / #261 / #280

最初に読むもの:

- [`AGENTS.md`](../AGENTS.md)（英語）
- [`docs/BRANCH_POLICY.ja.md`](BRANCH_POLICY.ja.md)
- [`docs/ENVIRONMENTS.ja.md`](ENVIRONMENTS.ja.md)
- [`docs/dev/VALIDATION_POLICY.ja.md`](dev/VALIDATION_POLICY.ja.md)
- [`docs/SCRIPT_MANAGEMENT.md`](SCRIPT_MANAGEMENT.md)
- [`docs/ai-workflow/`](ai-workflow/)
- [`docs/DOCUMENTATION_INVENTORY.md`](DOCUMENTATION_INVENTORY.md)（英語）
- [`docs/history/DEVELOPMENT_LOG.md`](history/DEVELOPMENT_LOG.md)（英語。Issue 以前・初期のプロジェクトの起源のマイルストーンを簡潔にまとめた台帳としてだけ）

Issue #45 / PR #184 と Issue #185 / PR #188 は、スクリプトの配置の整理の過去の目印です。Issue #63 は、以前は一時的なタスクの一式にあった、環境・パスのフォローアップのまとめを保持しています。Issue #6 / PR #11 は、標準化した Makefile・ruff の開発ワークフローへの移行を示します。

古い Issue にある一時的な復旧のコマンドやマシン固有のパスは、過去の証拠にすぎません。

## 実験の来歴の規則

重要な調査では、長く残す記録から次の関係を復元できるようにします。

`hypothesis -> script/command -> source/candidate commit -> fixed inputs/provenance -> result -> disposition`

ハーネス、環境、来歴、座標・インデックス、シリアライズの契約の欠陥によって無効になった結果は、無効・置き換え済みとしての表示を残します。修正後の結果と平均してはいけません。

## セッション・引き継ぎの保持の規則

チャットの記録、再開用のプロンプト、タスクのプロンプト、完了した実行計画は、長く残すリポジトリの文書ではありません。

Issue の重要な判断、実験の来歴、受け入れた・却下した結果、フォローアップが GitHub・ソース・テスト・長く残す文書から復元できるようになったら、それらの作業の記録を作業中の文書ツリーに残す必要はありません。

チャットの記録全体をこのリポジトリにコピーしないでください。
