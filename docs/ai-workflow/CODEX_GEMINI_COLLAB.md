# Codex + gemini-cli 併用ワークフロー（作業中最適化）

本ドキュメントは、`Codex` と `gemini-cli` を併用するための運用ルールです。
主担当は固定しません。タスクに応じて `Codex主担当` / `gemini-cli主担当` を切り替えます。
PR前レビュー専用ではなく、**作業しながら使い、実際の効果を見て運用を最適化する**ことを前提にします。

## 目的

- 実装速度を落としすぎずに、設計の見落としとデバッグ詰まりを減らす
- 主担当エージェントが進行を主導し、副担当エージェントを「別視点の仮説生成」に使う
- 有効だった使い方/効かなかった使い方をログに残し、継続的に改善する

## 運用モード（基本）

### モードA: Codex主担当（デフォルト）

- `Codex`:
  - タスク分解
  - リポジトリ編集（原則）
  - テスト/動作確認
  - 最終判断・最終報告
- `gemini-cli`:
  - 別案の提示（設計/実装方針）
  - デバッグ仮説の列挙
  - 中間レビュー（回帰リスク、境界条件、テスト観点）

### モードB: gemini-cli主担当（試験運用）

- `gemini-cli`:
  - 方針探索・論点整理
  - 実装方針の比較
  - 中間レビュー/疑似レビュー
- `Codex`:
  - 指示された範囲の実装（repo編集）
  - ローカル検証（テスト/実行）
  - 実装結果の要約と差分説明

メモ:

- 「主担当 = 最終的な意思決定者」とは限らない。最終判断は、常にローカル実測とユーザー確認を優先する。
- 実装品質/検証の責任を明確にするため、**書き込み担当（single writer）** は都度明示する。

## 利用タイミング（推奨トリガー）

PR前レビューに限定せず、次の場面で使う。

- 仕様解釈が複数あり、実装前に分岐を比較したいとき
- 閾値・ヒューリスティクス設計で候補比較したいとき
- 20-30分以上デバッグで停滞したとき
- 実装途中で「この変更の副作用が気になる」と感じたとき
- テスト観点の抜けを洗いたいとき

使わない/優先度が低い場面:

- 明確な小修正（1-2ファイル、原因が確定）
- 機械的な整形・単純リネーム
- 実行結果でしか判断できず、仮説相談の価値が低いケース

## 運用ルール

- `Single Writer Rule`: 同時編集を避ける。各フェーズで repo 編集担当を1つに固定する。
- `Mode Declaration`: セッション冒頭または主要フェーズ開始時に `Codex主担当` / `gemini-cli主担当` を明示する。
- `Question-First`: `gemini-cli` には広く聞かず、問いを狭く定義して投げる。
- `Evidence-First`: どちらの提案でも、コード確認・テスト・実行結果で検証してから採用する。
- `Decision Log`: 採用/棄却と理由をログに残す（本ファイル末尾のログ欄）。
- `Scope Guard`: 相談結果が有用でも、Issue/タスクの範囲外実装は行わない。

## gemini-cli 呼び出しの定型（テンプレート）

以下は主に `gemini-cli` 相談用テンプレート。`Codex` を相談先にする場合も同じ形式を流用できる。
必要最小限の文脈だけ渡す。

## コマンド実行例（確認済み）

本環境では、Gemini側から `codex` コマンドを、Codex側から `gemini` コマンドを相互に呼び出すことができます。
過去には Codex から Gemini 呼び出しが不安定な時期がありましたが、2026-02-27 時点で以下の条件により安定実行を確認しました。

### Codex -> Gemini 安定実行メモ（2026-02-27）

- 推奨コマンド: `timeout 180s gemini -p "<prompt>"`
- 推奨実行方式:
  - Gemini相談は最初からネットワーク有効な実行経路を選ぶ（既知の失敗手順を先に踏まない）
  - 可能なら `prefix_rule=["gemini","-p"]` を保存して再承認回数を減らす
- 長文入力で詰まりやすい場合:
  - 文書全量貼り付けを避け、要点要約を渡す
  - 質問を分割して複数回呼び出す

### GeminiからCodexを呼び出す（推奨）

設計案の具体化や、リポジトリ広範囲の編集、ローカル検証を依頼する場合に使用します。
Gemini側では標準化されたスキル `.agents/skills/codex-delegation/SKILL.md` を利用して、意図を明確にした上でCodexに指示を出します。

```bash
# 実装案を具体化し、ファイルに書き込んでもらう
# ※ Gemini側で設計の合意が取れた後に実行
gemini-cli> codex exec "src/pipeline/logic.py に、Geminiとの相談で決まった境界条件のチェックを追加してください。"

# 特定の関数のテストケースを自動生成してもらう
gemini-cli> codex exec "utils.py の calculate_unit_size に対する unit test を tests/ に作成してください。"

# 設計段階のセカンドオピニオンを求める（編集させない）
gemini-cli> codex exec --sandbox read-only "この設計案のリスクを、既存の barline_matcher.py の実装と照らし合わせて評価してください。"
```

### CodexからGeminiを呼び出す

論点整理や、複雑なデバッグの仮説立案、ユーザー視点のレビューを依頼する場合に使用します。

```bash
# 実装案のリスク分析（非対話）
codex> gemini -p "この設計案のリスクを3点挙げて"

# 初回プロンプトを渡して、そのまま対話継続
codex> gemini -i "この差分を中間レビューして"
```

運用メモ:

- Geminiは「全体設計・論点整理」を得意とし、Codexは「コードの詳細把握・リポジトリ操作・検証」を得意とします。
- **設計段階（案を練るフェーズ）** でも積極的に `codex exec --sandbox read-only` を使い、Geminiの案をCodexにレビューさせることで、実装前により堅牢な方針を固めることができます。
- 長文コンテキストは必要箇所だけ要約して渡す（貼りすぎると品質/速度が落ちやすい）。

### 1. 設計相談テンプレート

```text
目的:
- <今回の変更で達成したいこと>

制約:
- <Issue/AC/性能/依存関係/既存仕様など>

現状案:
- <Codex側の案を箇条書き>

見てほしい点:
- 代替案を2つ
- 各案のリスク
- テスト観点（境界条件含む）

出力形式:
- 推奨案（理由つき）
- 代替案
- リスク一覧
- テスト観点チェックリスト
```

### 2. デバッグ相談テンプレート

```text
症状:
- <何が起きているか>

再現条件:
- <コマンド/入力/環境>

期待値:
- <本来どうなるべきか>

観測ログ:
- <要点だけ貼る>

試したこと:
- <既に除外した仮説>

依頼:
- 原因仮説を優先度順に5つ
- 各仮説の切り分け手順
- 追加で取るべきログ/観測点
```

### 3. 中間レビュー（作業中レビュー）テンプレート

```text
変更概要:
- <何を変えたか>

主な差分ポイント:
- <関数/モジュール/ロジックの変更点>

懸念:
- <気になっている副作用や未確認点>

依頼:
- 回帰リスク
- 境界条件の見落とし
- 不足テスト
- 命名/責務分割の違和感（あれば）
```

## 会話ログの保存ルール（このファイルに追記）

`gemini-cli` を使った相談は、重要なものだけ本ファイル末尾の「会話ログ」に追記する。
目的は再現性よりも、**意思決定の履歴と有効性の評価**を残すこと。

記録対象（推奨）:

- 実装方針を変えた相談
- デバッグ停滞を解消した相談
- 不採用だが有用な代替案が出た相談

記録を省略してよい例:

- 重複した質問
- 明らかな確認だけの短いやり取り

### ログ記入テンプレート

```md
### YYYY-MM-DD HH:MM JST / <task-or-issue>

- Mode: `<codex_primary | gemini_primary>`
- Writer: `<codex | gemini-cli>`
- Phase: `<design | debug | mid-review>`
- Trigger: <なぜ副担当エージェントを使ったか>
- Question (summary): <投げた問いの要約>
- Secondary answer (summary): <回答要点 3-5行>
- Decision: `<adopted | partially_adopted | rejected | pending>`
- Action taken: <実際に行った変更/確認（誰が担当したか分かるように）>
- Evidence: <テスト結果、ログ、コード参照など>
- Notes: <次回改善したい点（任意）>
```

### セッション終了ルーチン（半自動）

毎回のセッション終了時に、次の 3 点だけは必ず更新する。

1. `Decision Log` 1件追記（このファイル末尾）
2. `LESSONS.md` に再発防止観点を 1 件追記（なければ `N/A` を記録）
3. 証拠（テスト結果 or 実行ログ）を 1 行で残す

最小テンプレート:

```md
### YYYY-MM-DD HH:MM JST / <task>
- Decision: <adopted | partially_adopted | rejected | pending>
- Why: <採用/棄却理由を1-2行>
- Evidence: <test command + pass/fail>
```

`LESSONS.md` 追記テンプレート:

```md
- **lesson_XXX**: <再発防止のルールを1行で>
```

## 運用の見直し（継続改善）

一定期間ごとに会話ログを見返し、以下を調整する。

- どのトリガーで使うと効果が高いか
- どのテンプレートが長すぎる/不足しているか
- 回答の質が高い問いの書き方
- 相談コストに対して効果が薄い使い方（削る）

更新方針:

- このドキュメントを直接更新してよい
- 実運用で有効だったプロンプトはテンプレートへ昇格する
- 形骸化したルールは削除または簡略化する

## 会話ログ

### 2026-02-25 00:00 JST / multi-llm-workflow-docs (initial setup)

- Mode: `codex_primary`
- Writer: `codex`
- Phase: `design`
- Trigger: PR前レビュー専用では利用機会が少ないため、作業中併用へ方針を広げる必要があった
- Question (summary): Codex と gemini-cli をどう workflow に組み込むか。作業しながら最適化する運用案を定義したい
- Secondary answer (summary): gemini-cli をセカンドオピニオンとして、設計分岐・デバッグ停滞・中間レビューで使う案を提示。Single Writer / Evidence-First / Decision Log を中核ルールとする提案
- Decision: `partially_adopted`
- Action taken: `AGENTS.md` に multi-LLM 方針を追加し、`docs/ai-workflow/CODEX_GEMINI_COLLAB.md` を新規作成。後続で `gemini主担当` モードにも拡張し、`WORKFLOW.md` に導線リンクを追加
- Evidence: ドキュメント差分確認（`AGENTS.md`, `docs/ai-workflow/CODEX_GEMINI_COLLAB.md`, `docs/ai-workflow/WORKFLOW.md`）
- Notes: 次回以降は実案件でのデバッグ相談ログを蓄積して、トリガー条件とテンプレートを削る/絞る

### 2026-02-27 14:34 JST / ai-workflow-ops-review

- Mode: `codex_primary`
- Writer: `codex`
- Phase: `mid-review`
- Trigger: `docs/ai-workflow` の運用上の不整合（ラベル、連携不安、ナレッジ更新）を精査する必要があった
- Question (summary): 主要ドキュメントの運用リスクを重大度順に抽出し、改善方針を定義したい
- Secondary answer (summary): Geminiは「状態不整合」「コンテキスト分断」「検証循環」を主要リスクとして提示。特にラベル不整合と連携不安定を優先修正対象にする提案
- Decision: `adopted`
- Action taken: `WORKFLOW.md` / `LABELS.md` / `CODEX_GEMINI_COLLAB.md` を更新し、`assign-to-jules` の位置づけ、`gh` 安全書式、Codex->Gemini安定実行条件、半自動ナレッジ蓄積ルーチンを追記
- Evidence: `timeout 180s gemini -p "<prompt>"` 相当の実行方針で応答取得、加えて上記3ファイルの差分確認
- Notes: 追加で自動化する場合は `Decision Log` と `LESSONS.md` 追記を行う小スクリプト化を検討

## Enhanced Sub-agent Collaboration (2026-02-25 Optimization)

### Reasoning Delegation
Gemini should treat Codex as a "deep-repo auditor" by delegating reasoning tasks that require exhaustive file-system traversal.
- **Audit Protocol**: Use \`codex exec --sandbox read-only\` to verify Gemini's logic against specific modules.

### Vision-Guided Implementation
1. Gemini analyzes detection failures in \`debug_outputs/\`.
2. Gemini designs a fix and generates a \`codex exec\` implementation command.
3. Codex implements the fix and runs verification tests.
