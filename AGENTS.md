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

## 7. Skills

- 共通スキルは `skills/` に配置する
- リポジトリ固有の最適化は `.agents/skills` に追加する
- 各スキルは「目的 / 入力 / 出力 / 手順 / 必要なコマンド」を明記する
