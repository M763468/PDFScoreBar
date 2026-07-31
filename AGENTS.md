# AGENTS.md - Rules for AI Agents

## 1. Purpose

This document provides a set of rules and guidelines for AI agents (such as Jules, Gemini, or Codex) contributing to this repository. The goal is to ensure all contributions are safe, consistent, and aligned with the project's standards. This file serves as the "constitution" for AI agents.

## 2. Do's and Don'ts

### Do
- **Adhere to the Issue Scope**: Implement only what is explicitly defined in the `Goal`, `Scope`, and `Acceptance Criteria` of the assigned issue.
- **Follow Established Patterns**: Use existing code patterns, conventions, and architectural styles.
- **Write Necessary Tests**: Provide lightweight tests to validate your implementation, as specified in the issue.
- **Use Standard Labels**: Apply labels as defined in `docs/ai-workflow/LABELS.md`.
- **Follow the Validation Policy**: Use `docs/dev/VALIDATION_POLICY.md` to choose required checks by change type and report skipped/deferred validation explicitly.
- **Update Documentation**: If your changes affect user-facing behavior or system design, indicate that the README or other documentation needs to be updated.

### Don't
- **Do Not Add Unauthorized Dependencies**: Do not add, remove, or update any dependencies unless explicitly instructed to do so in the issue.
- **Do Not Implement Outside Scope**: Do not introduce any functionality or fixes that are not part of the assigned issue. If you identify a potential improvement, suggest it in a comment.
- **Do Not Change Build Configurations**: Do not modify build scripts, CI/CD pipelines, or any other repository configuration files without explicit permission.
- **Do Not Commit or Merge Directly**: All changes must be submitted through a pull request linked to the corresponding issue. Do not merge to `main` or `develop` automatically. *Exception: direct commits are allowed only when explicitly instructed by the user in a local interactive session (e.g., using CLI agents).*
- **Do Not Modify During Investigation**: If the instruction is only for investigation, analysis, or root cause identification, **Do Not** modify any files. Always present findings first and wait for approval before proceeding to implementation.

## 3. Change Policy

- **Propose Before Execute**: For any non-trivial changes or when the fix approach is not explicitly defined, agents must provide a brief summary of the proposed modification and wait for confirmation before execution.
- **Destructive Changes**: Any change that is destructive (e.g., removing a file, altering a public API) must be explicitly approved in the issue description or chat context.
- **Large-Scale Refactoring**: Do not perform large-scale refactoring unless it is the primary goal of the assigned task. Small, localized refactoring for clarity is acceptable.
- **Data Schema Changes**: Any modifications to data schemas or database structures require explicit sign-off from the project maintainers.

## 4. Quality Bar

- **Testing**: All code must be accompanied by tests sufficient to prove it meets the `Acceptance Criteria`. The "How to test" section of the issue should be followed precisely.
- **Linting**: Code must adhere to the project's linting standards. Always run `make format` to fix style issues and `make lint` to verify compliance before submitting changes.
- **Validation Policy**: Follow `docs/dev/VALIDATION_POLICY.md`. Full evaluation is not mandatory for every PR, but evaluation-sensitive changes require full evaluation artifacts or an explicit human skip/defer decision.
- **Blocked Validation**: If GPU, Docker, dataset, model, or sandbox constraints prevent a required check, report the skipped command and exact reason. Do not present a blocked check as success.
- **Pre-Commit / Pre-PR Verification (Mandatory)**: Before creating a commit or opening a PR, you **MUST** run both (1) behavior verification (actual execution path relevant to the change, e.g. smoke run) and (2) tests/lint checks, then report the results. Do not commit or create a PR if these checks have not been completed.
  - Regression workflow reference: `docs/REGRESSION_TEST_WORKFLOW.md`
- **Logging**: Add clear and concise logging for errors and important events. Avoid noisy or verbose logging.
- **PR Descriptions**: Pull request descriptions must be filled out completely, following the `.github/pull_request_template.md`. The `Related Issue` field is mandatory.

## 5. Security

- **No Secrets in Code**: Never hardcode secrets, API keys, or any other sensitive credentials in the source code. Use environment variables or a designated secrets management system.
- **Data Transmission**: Do not transmit any user data or sensitive information to external services unless it is a documented and approved part of the functionality.
- **Input Validation**: Always sanitize and validate user-provided input to prevent common vulnerabilities (e.g., XSS, SQL injection).

## 6. Project-Specific Overrides

### Environment & Execution
- **Check Environments First**: Before executing any code, you **MUST** read `docs/ENVIRONMENTS.md`. This project uses a mix of Docker containers (`pdf_score_dev_gpu`, `homr_eval_gpu`, etc.) and host-based virtual environments (`.venv_pdf`, etc.). Identify the correct environment for your task.
- **Docker Preference**: Prefer running tasks inside the appropriate Docker container whenever possible to ensure reproducibility. For local PR validation helpers, see `docs/dev/codex_local_automation.md`.
- **Pytest-Capable Persistent Pipeline Container**: For repeated full-pipeline / Issue #94 / Issue #120 / MMR evaluation work that also needs repository tests, prefer a named long-lived pytest-capable container instead of repeated `docker run --rm` invocations. The base image remains `pdfscore_pipeline_gpu`, but the persistent local container may have `pytest` installed once in `/opt/venv_pipeline` for validation.
    - Create when absent: `docker run -dit --gpus all --name pdfscore_pipeline_pytest_dev -v "$PWD":/workspace -w /workspace -e PYTHONPATH=/workspace pdfscore_pipeline_gpu bash`
    - Start when stopped: `docker start pdfscore_pipeline_pytest_dev`
    - Install pytest once if missing: `docker exec -w /workspace pdfscore_pipeline_pytest_dev /opt/venv_pipeline/bin/python -m pip install pytest`
    - Run pytest: `docker exec -w /workspace -e PYTHONPATH=/workspace pdfscore_pipeline_pytest_dev /opt/venv_pipeline/bin/python -m pytest <tests-or-options>`
    - Run pipeline/eval commands: `docker exec -w /workspace -e PYTHONPATH=/workspace pdfscore_pipeline_pytest_dev /opt/venv_pipeline/bin/python <script-or-module>`
    - Remove only with explicit user approval: `docker rm -f pdfscore_pipeline_pytest_dev`.
- **Do Not Drop Pytest Coverage Due to Runtime Image Defaults**: If `pdfscore_pipeline_gpu` lacks `pytest`, do not rewrite tests away from pytest or skip tests solely for that reason. Use the pytest-capable persistent container above, or a documented dev/test environment. Only use `unittest` or ad-hoc self-check scripts when they are the better test form for the issue, not as a workaround for a missing test runner.
- **Host Execution**: Some tools (e.g., `gui_helper`) are designed to run on the host. Follow the specific instructions in `docs/ENVIRONMENTS.md`.

### Standard Commands
- **Makefile as Source of Truth**: The `Makefile` in the project root defines the standard commands for development tasks (linting, formatting, etc.).
- **Usage**:
    - `make help`: Check this first to see available commands and their descriptions.
    - `make lint`: Run static analysis.
    - `make format`: Auto-format code.
    - `make test-fast`: Run maintained lightweight tests without GPU or real-data requirements when applicable.
    - `make local-pr-validation PR=<number>`: Summarize changed files, validation categories, commands, logs, skipped validation, and remaining risks.
    - `make local-pr-validation PR=<number> WITH_FULL_EVAL=1 POST_COMMENT=1`: Start the authorized full-evaluation path and post the summary when appropriate.
- **Maintenance**: Developers and Agents should update the `Makefile` and this document when new standard workflows are introduced.

### Branch Policy
- **Read Branch Policy Before Issue Work**: Before starting issue work or opening a PR, read `docs/BRANCH_POLICY.md`.
- **Default Base**: For normal feature, fix, refactor, documentation, and performance work, use `develop` as both the base branch and PR base unless the issue explicitly states that the work is release, hotfix, or promotion work.
- **Stable Branch**: Treat `main` as the stable/release branch. Changes move from `develop` to `main` only through a dedicated promotion PR.
- **Stale Issue Text**: Older issues may still say `Base branch: main` or `PR base: main`. Treat those fields as stale unless the issue is explicitly release, hotfix, or promotion-related; restate the effective branch decision when picking up such an issue.

### Design Principles (Barline Detection)
- **Resolution Independence (Unit-based Scaling)**:
    - **Rule**: NEVER use fixed pixel (px) thresholds for distance or geometry calculations in the barline detection/numbering layers.
    - **Implementation**: Always use `unit_size` (staff line spacing) as the base unit for dynamic scaling.
    - **Current Targets**: Deduplication Threshold (`1.2 * unit_size`), Implicit Start Assumption (`4.0 * unit_size`).
    - **Documentation**: See `docs/GT_PREPARATION_POLICY.md` and `docs/BARLINE_MATCHER.md`.
- **GT Labeling Consistency**:
    - Use specific labels for complex barlines: `double_barline`, `end_barline`, `repeat`.
    - Treat multi-line barlines as a **single logical event** with a single encompassing BBox.

### Issue Template Conformance
- **Template-First Issue Bodies**: When creating or updating GitHub Issues, always align the body with the corresponding file in `.github/ISSUE_TEMPLATE/`.
- **Required Headers Must Exist**: For `Task` issues, do not omit `Base branch`, `Branch name`, `PR base`, `Goal`, and `Done` in the issue body.
- **Project Extensions Are Additive**: Sections like `Background`, `Scope`, `Acceptance Criteria`, and `How to test` may be added, but only in addition to (not instead of) required template headers.

### Logs & Artifacts
- **Output Directory**: All experiment logs, metrics, and generated artifacts must be saved under the `logs/` directory. Use structured subdirectories (e.g., `logs/<experiment_name>/<timestamp>/`) to avoid clutter.
- **Skill Artifacts**: Skill-local lightweight summaries may be written under `artifacts/`; pipeline, evaluation, experiment, and generated model/data outputs must be written under `logs/`.
- **Cleanup**: Do not leave temporary files in the project root.
- **Dataset Staging Rule (Required)**: For CNN retraining/evaluation jobs, place working datasets under `datasets/` in this repository before any bulk file operation. Do not run iterative copy/split generation directly on `/mnt/*`.
- **Preflight Check (Required)**: Before launching long training/eval, explicitly verify: `pwd` is repo root, input dataset root is under `datasets/`, and output path is under `logs/`.

### Dependencies
- **Strict Control**: Do not modify `requirements.txt`, `pyproject.toml`, or `Dockerfile` unless the task explicitly requires dependency updates.
- **No Unauthorized Libraries**: Do not install new libraries without user approval.

### Dataset I/O Performance Rule (WSL)
- **Destructive Operations Require Approval**: Any destructive git, filesystem, dataset, model, cache, or log operation requires explicit user approval.
- **Avoid `/mnt/*` for bulk small-file operations**: On this repository, `/mnt/c` `/mnt/d` is mounted via `drvfs/9p`, and metadata-heavy operations (`copytree`, many `cp/stat`, split rebuilds) become extremely slow.
- **Working copy first**: For dataset editing/augmentation/relabel tasks, first copy the working dataset under repository `datasets/` (ext4 side), then perform all file operations there.
- **Use `/mnt/*` as source/archive only**: Treat `/mnt/*` dataset paths as read-mostly source or backup locations, not active scratch space for iterative retraining loops.

### Evaluation-Sensitive Changes
- Treat filter logic, thresholds, seeds, dataset selection, metric calculation, evaluation configs, baseline/canonical artifacts, detector routing, Docker/GPU/model loading, and generated evaluation outputs as evaluation-sensitive.
- Keep evaluation-sensitive diffs minimal and report affected files, command, commit hash, environment, input config/data, log path, and remaining risks.
- Automation must make required validation, skipped validation, and scope-sensitive changes more visible. It must not weaken validation or prevent normal manual development.

### Multi-LLM Collaboration (Codex + gemini-cli)
- **Flexible Primary/Secondary Roles**: In interactive local work, either `Codex` or `gemini-cli` may be the primary driver depending on the task. The primary agent leads planning and decision flow; the secondary agent provides alternative designs, debugging hypotheses, or review feedback.
- **Implementation Delegation is Allowed**: A valid pattern is `gemini-cli` as primary for exploration/reasoning and `Codex` for focused repository edits and verification. The reverse (Codex primary, gemini-cli second opinion) is also valid.
- **Optimize While Working**: Do not limit multi-LLM usage to pre-PR review only. Use it during implementation when helpful, and refine the collaboration pattern based on actual outcomes (speed, bug detection, usefulness).
- **Single Writer Rule**: To avoid conflicts, keep one active file editor at a time in the session. Explicitly choose a single writer before file edits.
- **Evidence-First Adoption**: Suggestions from either agent are hypotheses until validated by local code inspection, tests, or runtime behavior.
- **Prompt/Log Documentation**: Standard prompts and conversation log format for multi-LLM collaboration must be maintained under `docs/ai-workflow/` (see the dedicated collaboration doc) and updated as the workflow evolves.
- **Operational Entry Points (Must Read Order)**:
  1. `docs/ai-workflow/WORKFLOW.md` (general workflow baseline)
  2. `docs/BRANCH_POLICY.md` (branch roles, default base/PR base, and promotion rules)
  3. `docs/ai-workflow/CODEX_GEMINI_COLLAB.md` (Codex/Gemini collaboration protocol)
  4. `docs/ai-workflow/LESSONS.md` (known anti-patterns and heuristics)
  5. This `AGENTS.md` (repository-specific overrides, highest priority inside repo)
- **Codex -> Gemini Call Stability Rule**:
  - For this repository, run Gemini consultations with network-enabled execution from the start (outside sandbox when required), not as a fallback after a known-failing step.
  - Prefer longer timeouts (e.g., `timeout 180s gemini -p "<prompt>"`) to allow deeper reasoning.
  - For long contexts, pass summarized inputs and split questions to reduce timeout risk.

## 7. Skills

- 共通スキルは `skills/` に配置する
- リポジトリ固有の最適化は `.agents/skills` に追加する
- 各スキルは「目的 / 入力 / 出力 / 手順 / 必要なコマンド」を明記する
- **利用可能なスキル一覧**:
    - `issue-creation`: Issue の下書き作成
    - `problem-investigation`: バグ調査・原因究明
    - `issue-solver`: Issue の自律解決（実装・検証）
    - `pr-explanation`: PR の説明文生成
    - `pr-review`: PR の自動レビュー
    - `pr-refinement`: レビュー指摘の修正適用
    - `status-check`: 現在の作業状況の要約
    - `change-summary`: 最終的な変更内容の要約
    - `doc-updater`: ドキュメントの自動更新
    - `dependency-management`: 依存関係の管理
    - `test-generation`: テストコードの生成・更新
    - `long-horizon-task`: 長期タスクの状態管理
    - `gemini-consultation`: Gemini への標準化された相談。`.agents/skills/gemini-consultation/SKILL.md` を利用し、相談時の入力整理・実行手順・記録方法を統一します。
    - `codex-delegation`: Codex への実装・検証タスクの委譲。`.agents/skills/codex-delegation/SKILL.md` を利用し、コンテキスト消費を抑えつつ精緻な実装と検証を行います。
    - `graphify`: コードベース構造・依存関係・call path・関連ファイルの事前探索。`.agents/skills/graphify/SKILL.md` と `docs/ai-workflow/GRAPHIFY.md` に従い、共有グラフを広範検索より先に利用します。

詳細は `docs/ai-workflow/WORKFLOW.md` を参照。

## 8. インタラクティブ・プロトコル（対話型セッション専用ルール）

ユーザーとの直接対話において、AIエージェントは透明性と制御性を確保するため、以下の手順を「絶対」として遵守しなければならない。

1. **確認の徹底 (Confirmation Loop)**:
   - Git操作（merge/rebase等）、GitHub Issue作成、ファイルの新規作成・削除など、状態を変更する操作の前には、必ず実行計画を提示し、ユーザーの承諾を得ること。
   - 「〜しますか？」という問いかけに対し、ユーザーが「OK」や「進めて」と回答した後にのみ実行する。

2. **選択肢の提示 (Option Rule)**:
   - 手法が複数存在する場合（例：rebaseかmergeか）、それぞれのメリット・デメリットを簡潔に示し、ユーザーに判断を仰ぐこと。独断で手法を選択してはならない。

3. **実行直前のナレーション (Pre-Call Narration)**:
   - 全てのツール呼び出し（コマンド実行等）の直前には、その意図を説明する1文を必ず添えること。ツールを「無言」で実行してはならない。

4. **逸脱時の自己修正**:
   - もし確認や説明をスキップしてしまったことに気づいた場合、即座に中断し、謝罪した上で不足していた説明を行い、改めて指示を仰ぐこと。

5. **GitHubコメント投稿時の安全な書式**:
   - `gh pr comment` / `gh issue comment` で本文にバッククォート（`` ` ``）や `$` を含む場合、シェル展開を避けるため `--body-file` + シングルクォートheredoc（`<<'EOF'`）を使うこと。
   - `--body "..."` へ直接埋め込む方法は原則禁止（コマンド置換や変数展開で本文が破損するため）。

6. **`gh` 実行時のネットワーク制限切り分け（Codex / sandbox）**:
   - `gh issue comment` / `gh pr comment` / `gh api` 実行時に `error connecting to api.github.com` が出た場合、まず **認証エラーと断定しない**。Codex セッションの sandbox が `network_access=false` の場合、GitHub API に到達できず同様のエラーになる。
   - `gh auth status` の結果だけで判断せず、必要に応じて `gh api user` や `gh issue view <number>` などの**読み取り系コマンド**で到達性と認証を切り分けること。
   - GitHub への投稿/更新操作（コメント投稿、Issue/PR 更新など）は、sandbox 内で通信不可のときは **権限昇格（sandbox外）で実行**すること。
   - エージェントは実行前に「ネットワーク制限回避のため権限昇格が必要」である旨を明示し、ユーザー承認を得ること。

7. **GPU/CUDA 実行時の sandbox 切り分け（PyTorch）**:
   - `nvidia-smi` は成功するのに `torch.cuda.is_available()==False` や `cudaGetDeviceCount` 系エラー（例: `Error 304: OS call failed or operation not supported on this OS`）が出る場合、まず **ドライバ/venv破損と断定しない**。Codex の sandbox 内実行では CUDA 初期化が失敗することがある。
   - まず sandbox 内で `torch.__version__`, `torch.version.cuda`, `torch.cuda.is_available()`, `torch.cuda.device_count()` を確認し、OS 側は `nvidia-smi` で切り分けること。
   - `nvidia-smi` 成功かつ PyTorch の CUDA build（例 `+cuXXX`）なのに sandbox 内だけ失敗する場合、**GPUを使う推論/学習コマンドは権限昇格（sandbox外）で実行**すること。
   - 実行前に「sandbox 内では CUDA 初期化が失敗するため、GPU利用のため権限昇格が必要」である旨を明示し、ユーザー承認を得ること。

8. **長時間学習ジョブの sandbox 制約（multiprocessing/semlock）**:
   - `experiments/cnn_classifier/train.py` のような DataLoader 複数worker学習は、sandbox 内だと `PermissionError: [Errno 13]`（`multiprocessing` の `SemLock`）で失敗することがある。
   - この系統の学習ジョブは、最初から **権限昇格（sandbox外）** で実行すること。
   - 失敗後のリトライではなく、初回実行時点で「sandbox制約回避のため権限昇格が必要」と明示して承認を得ること。
   - 学習データ更新は先に `datasets/`（repo ext4側）で完了させ、学習ジョブはその作業用datasetを参照して実行すること。

9. **自律的ピアレビュー（セカンドオピニオンの取得）**:
   - **トリガー条件**: 以下の「高難易度」状況を検知した場合、エージェントは自律的に別エージェント（Codex等）に意見を照会することを検討する。
     - 性能のトレードオフ（Precision向上によりRecallが低下するなど）が発生し、最適解が見えない場合。
     - `barline_matcher.py` や `measure_numbering` 等、システムのコアロジックに破壊的変更を加える場合。
     - 2回以上の試行でバグが修正できない、または原因の仮説が3つ以上並立する場合。
     - アーキテクチャの大きな分岐（A案・B案）において、客観的なリスク評価が必要な場合。
   - **照会手順**:
     - `codex exec --sandbox read-only` を使用し、現在の設計案に対する批判的レビューや代替案を求める。
     - 照会前にユーザーに「Codexに意見を聞いてみます」と宣言する（詳細な承認を待たず、思考プロセスの一環として実行して良い）。
   - **結果の統合**:
     - 照会結果をそのまま採用せず、自分の案と比較した「統合案」をユーザーに提示し、なぜその結論に至ったかの論拠（Rational）を説明する。

### Multi-LLM Role Specialization
- **Gemini CLI**: Architect, Multi-modal Reasoner, Web Researcher. Leads planning and reasoning.
- **Codex**: Implementation Specialist, Repository Navigator, Verification Lead. Leads focused edits and sandbox validation.
- **Consultation Mandate**: Gemini should proactively consult Codex (via `codex exec --sandbox read-only`) for second opinions on complex logic, type safety, or architectural impacts.
- **Knowledge Synthesis Mandate**: Both agents must document newly discovered heuristics, anti-patterns, or visual failure modes in `docs/ai-workflow/LESSONS.md` to prevent regressions in future sessions.

## Graphify利用ガイド

このリポジトリではGraphifyをコードベース構造・依存関係・call path・関連ファイルの事前探索に利用します。

- `graphify-out/graph.json` がある場合、広範な検索より先に `scripts/graphify_query.sh "<question>"` または `.agents/skills/graphify/SKILL.md` を利用する。
- Graphifyの結果は対象source・testで直接確認する。
- 通常の無人生成はcode-onlyとし、document semantic extractionはユーザーがlocal coding sessionまたはGemini API経路と対象scopeを明示した場合だけ行う。
- 共有対象は `graph.json`、`GRAPH_REPORT.md`、`wiki/**`、`MANIFEST.json`だけとし、cacheや環境依存の途中生成物はコミットしない。
- branch固有差分が未反映の場合は直接差分を確認し、必要な場合だけlocal refreshする。
- Graphifyが使えない、古い、または不十分な場合は `rg` / `grep` とsource確認へフォールバックする。
