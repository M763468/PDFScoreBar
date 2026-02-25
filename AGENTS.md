# AGENTS.md - Rules for AI Agents

## 1. Purpose

This document provides a set of rules and guidelines for AI agents (such as Jules, Gemini, or Codex) contributing to this repository. The goal is to ensure all contributions are safe, consistent, and aligned with the project's standards. This file serves as the "constitution" for AI agents.

## 2. Do's and Don'ts

### Do
- **Adhere to the Issue Scope**: Implement only what is explicitly defined in the `Goal`, `Scope`, and `Acceptance Criteria` of the assigned issue.
- **Follow Established Patterns**: Use existing code patterns, conventions, and architectural styles.
- **Write Necessary Tests**: Provide lightweight tests to validate your implementation, as specified in the issue.
- **Use Standard Labels**: Apply labels as defined in `docs/LABELS.md`.
- **Update Documentation**: If your changes affect user-facing behavior or system design, indicate that the README or other documentation needs to be updated.

### Don't
- **Do Not Add Unauthorized Dependencies**: Do not add, remove, or update any dependencies unless explicitly instructed to do so in the issue.
- **Do Not Implement Outside Scope**: Do not introduce any functionality or fixes that are not part of the assigned issue. If you identify a potential improvement, suggest it in a comment.
- **Do Not Change Build Configurations**: Do not modify build scripts, CI/CD pipelines, or any other repository configuration files without explicit permission.
- **Do Not Commit Directly**: All changes must be submitted through a pull request linked to the corresponding issue. *Exception: Direct commits are allowed only when explicitly instructed by the user in a local interactive session (e.g., using CLI agents).*
- **Do Not Modify During Investigation**: If the instruction is only for investigation, analysis, or root cause identification, **Do Not** modify any files. Always present findings first and wait for approval before proceeding to implementation.

## 3. Change Policy

- **Propose Before Execute**: For any non-trivial changes or when the fix approach is not explicitly defined, agents must provide a brief summary of the proposed modification and wait for confirmation before execution.
- **Destructive Changes**: Any change that is destructive (e.g., removing a file, altering a public API) must be explicitly approved in the issue description or chat context.
- **Large-Scale Refactoring**: Do not perform large-scale refactoring unless it is the primary goal of the assigned task. Small, localized refactoring for clarity is acceptable.
- **Data Schema Changes**: Any modifications to data schemas or database structures require explicit sign-off from the project maintainers.

## 4. Quality Bar

- **Testing**: All code must be accompanied by tests sufficient to prove it meets the `Acceptance Criteria`. The "How to test" section of the issue should be followed precisely.
- **Linting**: Code must adhere to the project's linting standards. Always run `make format` to fix style issues and `make lint` to verify compliance before submitting changes.
- **Logging**: Add clear and concise logging for errors and important events. Avoid noisy or verbose logging.
- **PR Descriptions**: Pull request descriptions must be filled out completely, following the `.github/pull_request_template.md`. The `Related Issue` field is mandatory.

## 5. Security

- **No Secrets in Code**: Never hardcode secrets, API keys, or any other sensitive credentials in the source code. Use environment variables or a designated secrets management system.
- **Data Transmission**: Do not transmit any user data or sensitive information to external services unless it is a documented and approved part of the functionality.
- **Input Validation**: Always sanitize and validate user-provided input to prevent common vulnerabilities (e.g., XSS, SQL injection).

## 6. Project-Specific Overrides

### Environment & Execution
- **Check Environments First**: Before executing any code, you **MUST** read `docs/ENVIRONMENTS.md`. This project uses a mix of Docker containers (`pdf_score_dev_gpu`, `homr_eval_gpu`, etc.) and host-based virtual environments (`.venv_pdf`, etc.). Identify the correct environment for your task.
- **Docker Preference**: Prefer running tasks inside the appropriate Docker container whenever possible to ensure reproducibility.
- **Host Execution**: Some tools (e.g., `gui_helper`) are designed to run on the host. Follow the specific instructions in `docs/ENVIRONMENTS.md`.

### Standard Commands
- **Makefile as Source of Truth**: The `Makefile` in the project root defines the standard commands for development tasks (linting, formatting, etc.).
- **Usage**:
    - `make help`: Check this first to see available commands and their descriptions.
    - `make lint`: Run static analysis.
    - `make format`: Auto-format code.
- **Maintenance**: Developers and Agents should update the `Makefile` and this document when new standard workflows are introduced.

### Logs & Artifacts
- **Output Directory**: All experiment logs, metrics, and generated artifacts must be saved under the `logs/` directory. Use structured subdirectories (e.g., `logs/<experiment_name>/<timestamp>/`) to avoid clutter.
- **Cleanup**: Do not leave temporary files in the project root.

### Dependencies
- **Strict Control**: Do not modify `requirements.txt`, `pyproject.toml`, or `Dockerfile` unless the task explicitly requires dependency updates.
- **No Unauthorized Libraries**: Do not install new libraries without user approval.

### Multi-LLM Collaboration (Codex + gemini-cli)
- **Flexible Primary/Secondary Roles**: In interactive local work, either `Codex` or `gemini-cli` may be the primary driver depending on the task. The primary agent leads planning and decision flow; the secondary agent provides alternative designs, debugging hypotheses, or review feedback.
- **Implementation Delegation is Allowed**: A valid pattern is `gemini-cli` as primary for exploration/reasoning and `Codex` for focused repository edits and verification. The reverse (Codex primary, gemini-cli second opinion) is also valid.
- **Optimize While Working**: Do not limit multi-LLM usage to pre-PR review only. Use it during implementation when helpful, and refine the collaboration pattern based on actual outcomes (speed, bug detection, usefulness).
- **Single Writer Rule**: To avoid conflicts, keep one active file editor at a time in the session. Explicitly choose a single writer before file edits.
- **Evidence-First Adoption**: Suggestions from either agent are hypotheses until validated by local code inspection, tests, or runtime behavior.
- **Prompt/Log Documentation**: Standard prompts and conversation log format for multi-LLM collaboration must be maintained under `docs/ai-workflow/` (see the dedicated collaboration doc) and updated as the workflow evolves.

## 7. Skills

- 共通スキルは `skills/` に配置する
- リポジトリ固有の最適化は `.agents/skills` に追加する
- 各スキルは「目的 / 入力 / 出力 / 手順 / 必要なコマンド」を明記する

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

### Multi-LLM Role Specialization
- **Gemini CLI**: Architect, Multi-modal Reasoner, Web Researcher. Leads planning and reasoning.
- **Codex**: Implementation Specialist, Repository Navigator, Verification Lead. Leads focused edits and sandbox validation.
- **Consultation Mandate**: Gemini should proactively consult Codex (via \`codex exec --sandbox read-only\`) for second opinions on complex logic or architectural impacts.
