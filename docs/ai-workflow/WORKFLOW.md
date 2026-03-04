# AI駆動OSS開発ワークフローまとめ（GitHub + gh + LLM）

本ドキュメントは、本リポジトリで実際に運用している **AIを主戦力にした開発フロー** を整理したものです。

対象読者:
- 個人開発 / OSS開発で AI（Jules / Codex / Gemini 等）を活用したい人
- GitHub UI を極力使わず、CLI中心で開発を回したい人

---

## 適用レイヤー（一般論 / リポジトリ特化）

- 本書（`docs/ai-workflow/WORKFLOW.md`）: 他リポジトリにも持ち運べる一般ワークフロー
- リポジトリ特化ルール: 必ず [AGENTS.md](../../AGENTS.md) を優先

このリポジトリでは、環境選択（`docs/ENVIRONMENTS.md` の事前確認）、sandbox制約、`gh`投稿時の安全書式などは `AGENTS.md` を正とします。

---

## 全体像（基本原則）

**1 Issue = 1 AI実装 = 1 Pull Request**

- 人間: 設計・Issue定義・レビュー・マージ判断
- AI: 実装・軽量テスト・PR作成

> AIは「作業者」、人間は「設計者 + 編集者」

---

## 0. 初期化（テンプレ適用直後の10分）

### 新規プロジェクトの場合

テンプレートからリポジトリを新規作成した場合は、まず次を実行します。

```bash
./scripts/init.sh
```

このテンプレートでは、共通スキルは `skills/` に同梱されています。
運用では `.agents/skills` に配置し、エージェントが読み込める構成にします。
導入先で `docs/ai-workflow/` のように場所を変える場合は、READMEやドキュメント内のリンクも合わせて調整してください。

### ワークフローを支える AI スキル (`.agents/skills/`)

各ステップで、以下の専用スキルを活用することで、品質の安定と作業の高速化が図れます。

| ステップ | 推奨スキル | 役割 |
| :--- | :--- | :--- |
| **0. 初期化 / 調査** | `status-check` | 現在の作業状況と次のアクションを整理する |
| **2. Issue設計** | `issue-creation` | ゴール・スコープ・受入条件を網羅した Issue を下書きする |
| | `problem-investigation` | バグの再現手順や根本原因の仮説を整理する |
| **3. 実装** | `issue-solver` | Issue を読み取り、ブランチ作成から実装・検証までを自律的に行う |
| | `test-generation` | 実装に対するテストコードを自動生成・更新する |
| | `long-horizon-task` | 大規模なリファクタリングなど、長期的なタスクの状態を管理する |
| **4. PR作成 / レビュー** | `pr-explanation` | 差分を解析し、PR の目的や変更点を説明する |
| | `pr-review` | リスクやバグ、スコープの逸脱を早期に検知する |
| | `pr-refinement` | レビューコメントを分析し、修正を自動で適用する |
| **その他** | `doc-updater` | コード変更に合わせてドキュメントを最新に保つ |
| | `dependency-management` | 依存関係の整合性をチェック・更新する |
| | `gemini-consultation` | Gemini への相談手順を標準化し、証跡を残す |
| | `change-summary` | 作業完了時に変更内容と影響範囲を要約する |

このスクリプトは以下を確認・初期化します。

- `gh` CLI の有無と認証状態
- Issue / PR テンプレなど必須ファイルの存在
- labels / milestones の初期セットアップ（冪等）

任意の初期Issueもまとめて作る場合は、次のように実行します。

```bash
./scripts/init.sh --with-issues
```

変更内容だけを確認したい場合は dry-run が便利です。

```bash
./scripts/init.sh --dry-run --repo <owner>/<repo>
```

### 既存プロジェクトに導入する場合

すでに動いているプロジェクトにワークフローを導入する場合、まずこのテンプレートリポジトリを適当な場所に `git clone` します。

```bash
git clone https://github.com/your-org/ai-dev-workflow-template.git
```

次に、導入したいあなたのプロジェクトのルートディレクトリで、移植スクリプトを実行します。

```bash
cd /path/to/your-project
/path/to/ai-dev-workflow-template/scripts/import.sh
```

このスクリプトは、以下のファイル群をあなたのプロジェクトにコピーします。

- `.github/`: Issue / PR テンプレート
- `docs/`: ワークフロー関連ドキュメント
- `scripts/`: 初期化・支援スクリプト
- `skills/`: `.agents/skills` ディレクトリにコピーされるAIスキル
- `AGENTS.md`: AIエージェント向けの指示書

ファイルが既に存在する場合は上書きを避けてスキップされ、不足しているファイルのみがコピー（マージ）されます。
移植が完了したら、`./scripts/init.sh` を実行して、GitHubのラベルやマイルストーンをセットアップしてください。

---

## 1. `.github/` に置くべきもの

### 必須ファイル

- `.github/ISSUE_TEMPLATE/*.yml`
- `.github/pull_request_template.md`
- [LABELS.md](LABELS.md): ラベル標準化のための辞書。詳細はこちらを参照してください。

### pull_request_template.md（AI向け最適化）

- Related Issue（Closes #）を必須化
- Scope（In / Out）を明示
- AI側テスト / 人間側テストを分離

これにより:
- AIの先取り実装を防止
- レビュー時の確認点を最小化

---

## 2. Issueの立て方（AIに解かせる前提）

### Issueに必ず書く項目

- Goal（このIssueで達成すること）
- Scope（In / Out）
- Inputs / Outputs（パス・ファイル名を固定）
- CLI usage example
- Acceptance Criteria（チェックリスト）
- How to test
  - AI側確認
  - 人間側確認

> Acceptance Criteria = 契約書

---

## 3. AIにIssueを解かせる方法

ここでは 2 つの実行モードを分けて扱います。

- モードA（ローカル対話型: Codex / gemini-cli）:
  - 日常運用のデフォルト。ラベル付与は必須ではない。
- モードB（リモート自動実装: Jules）:
  - GitHub上で `assign-to-jules` を明示トリガーとして使う。

### 基本手順

1. Issueを作成
2. 依存IssueがすべてCloseされていることを確認
3. モードBを使う場合のみ `assign-to-jules` ラベルを付与

補足:
- `ai:implement` / `ai:review` は運用メタデータとしては有用だが、実装開始トリガーとしては必須ではない。
- 「どのステップでもAIと協業する」前提なら、ラベル運用は最小限でよい。

### 成功率を上げるコツ

- Issue本文以外の説明を極力しない
- 「A-3以降を実装しない」など禁止事項を明記
- 1 Issueずつ実行（並列にしない）

### 補足: ローカル対話型エージェントの併用（Codex / gemini-cli）

ローカルで `Codex` と `gemini-cli` を併用する場合は、PR前レビュー専用にせず、設計分岐・デバッグ停滞・中間レビューのタイミングで使うと効果が出やすいです。

- 運用ルール・呼び出し定型・会話ログ: [CODEX_GEMINI_COLLAB.md](CODEX_GEMINI_COLLAB.md)
- `Codex主担当` / `gemini-cli主担当` の両モードを試し、実運用ログをもとに最適化する

---

## 4. ブランチ運用（親ブランチとAI作業ブランチ）

1つのテーマ（親Issueやエピック）に対して複数のIssueが立つ場合でも、一貫性のあるブランチ運用を推奨します。

### 親ブランチ（Parent Branch）

- **人間が作成**: `feature/<topic-name>` のような命名規則で、テーマごとに親ブランチを作成し、リモートにpushします。
- **目的**: 複数のAI作業ブランチをまとめるための統合ブランチとして機能します。

### AI作業ブランチ

- **AIが作成**: 親ブランチから、`feature/<issue-number>-<short-description>` のような命名規則で作業ブランチを作成します。
- **Issueで指定**: 子Issue作成時に、`Base branch`項目で親ブランチを指定します（未定の場合は空欄でOK、後からコメントやIssue編集で指定可能）。

### Pull Request (PR) の運用

- **PRの向き先**: AIが作成するPRは、`main`ブランチではなく、指定された親ブランチに向けます。
- **Draft PR**: 可能であればDraft PRとして作成し、レビューの粒度を保ちます。
- **Issueのクローズ**: PRの本文に `Closes #<issue-number>` を含めることで、親ブランチへのマージと同時にIssueがクローズされるようにします。

この運用により、複数Issueにまたがるテーマでも、PRのマージ順序やコンフリクトを管理しやすくなります。
AIエージェントは、Issueで指定されたベースブランチの指示に必ず従ってください。詳細は [AGENTS.md](../../AGENTS.md) も参照してください。

---

## 5. Jules（リモート自動実装）が反応しないとき

- コメントは必ずしも再同期トリガーにならない

### 確実な方法

1. `assign-to-jules` ラベルを一度外す
2. 再度 `assign-to-jules` を付ける

> ラベル付与 = 明示的な開始イベント

---

## 6. gh CLI でのPR / Issue操作

### よく使うコマンド

```bash
# PR一覧
gh pr list

# PR詳細
gh pr view 13

# 差分（Files changed）
gh pr diff 13

# Issue本文
gh issue view 5
```

### コメント・操作

```bash
cat <<'EOF' > /tmp/pr_comment_13.md
Please fix X
EOF
gh pr comment 13 --body-file /tmp/pr_comment_13.md
gh pr merge 13 --squash
gh pr edit 13 --add-label assign-to-jules
```

---

## 7. PRレビューをAIにやらせる（自動化）

### 基本アイデア

1. ghで差分取得
2. LLMに diff + 要件を渡す
3. レビュー文章を生成
4. ghでPRにコメント

---

## 8. ローカル自動レビュー用スクリプト例

> ここは将来的な拡張ポイントです（現時点では未実装でもOK）。

```bash
# PR番号を指定してAIレビュー生成
./tools/review_pr.sh 13 codex

# そのままPRにコメント投稿
./tools/review_pr.sh 13 codex --post
```

このスクリプトは:
- `gh pr diff` で差分取得
- Codex / Gemini に diff を渡す
- マージ可否・修正点・改善案を生成

---

## 9. 実務での判断基準（重要）

- **設計ミス > 実装ミス**
- AIのコードは「下書き」
- マージ基準は Acceptance Criteria のみ

> コード品質は後で直せるが、I/O設計は後で直しにくい

---

## 10. この運用のメリット

- 実装スピードが爆発的に上がる
- 設計が自然に言語化される
- AIを複数切り替えても破綻しない
- private / OSS どちらでも使える

---

## 11. 推奨運用サイクル（まとめ）

```
Issue設計
  ↓
assign-to-jules
  ↓
PR作成
  ↓
AIレビュー（codex/gemini）
  ↓
人間レビュー
  ↓
merge
```

このループを淡々と回すだけで、
**AI主導でも破綻しない開発**が成立します。

---

## 12. AI Agent Rules

AIエージェント向けの具体的なルールやガイドラインについては、リポジトリルートの [AGENTS.md](../../AGENTS.md) を参照してください。
このドキュメントはAIエージェントのための「憲法」として機能し、品質基準や行動規範を定義しています。
