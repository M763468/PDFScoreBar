# AGENTS.md

Repository-specific guidance for Codex, ChatGPT, Gemini, and human-assisted local work.

## Operating Principles

- Keep changes inside the assigned issue scope. If investigation discovers extra work, report it separately.
- Prefer existing code, Makefile targets, scripts, configs, and documentation before adding new structure.
- Do not commit directly to `main`. Use a topic branch and open a pull request linked to the issue.
- Do not perform destructive git, filesystem, dataset, model, or log operations without explicit user approval.
- Do not add, remove, or upgrade dependencies unless the issue explicitly asks for it.

## Runtime Authority

- The authoritative runtime is the user's local WSL/Linux environment with the project GPU setup.
- Cloud containers, web-based GitHub edits, and static reviews are useful for inspection and lightweight checks, but they are not final validation for GPU, Docker, dataset, or full pipeline behavior.
- Read `docs/ENVIRONMENTS.md`, `docs/MANIFEST.md`, and `docs/LOG_MANAGEMENT.md` before running environment-sensitive commands.
- The current primary pipeline environment is the unified Docker image/container `pdfscore_pipeline_gpu` with Python at `/opt/venv_pipeline/bin/python`.

## Validation Expectations

- Match validation weight to the change. Docs-only, comments-only, and small type or formatting updates do not require GPU smoke or full evaluation.
- Use lightweight checks first, such as `make test-fast`, targeted pytest commands, `bash -n` for shell scripts, or static review of docs.
- Use `make verify-pipeline-smoke` or `make verify-gpu-smoke` when a change can affect pipeline execution, Docker/GPU behavior, model loading, dataset access, or evaluation flow.
- Full evaluation is opt-in. Do not require it for every PR; start it only when the user, issue workflow, or an explicit command such as `make verify-full-eval` authorizes the long run.
- If GPU, Docker, dataset, model, or sandbox constraints prevent validation, report the skipped command and exact reason rather than treating it as a successful check.

## Evaluation and Data Rules

- Do not change filter logic, thresholds, seeds, dataset selection, metric calculation, or evaluation parameters casually.
- If those areas must change, keep the diff minimal and report the reason, affected files, reproduction command, target commit, and log path.
- When updating experimental values or accuracy/performance claims, include the command, commit hash, environment, input config/data, and log path needed to reproduce the result.
- Keep large datasets, caches, generated logs, and model artifacts out of git. Use symlinks or environment variables for local-only data.

## Worktree and Local Data

- Use a dedicated git worktree for issue work when the main clone may contain unrelated work.
- Do not edit another issue's active working tree. Use the original clone only as a worktree manager when requested.
- For local-only assets, prefer `scripts/setup_local_worktree_links.sh` and document the source paths through environment variables instead of committing machine-specific paths.
- Keep worktree run outputs isolated under ignored log/artifact paths unless a small tracked doc update is intentionally part of the PR.

## Automation Boundaries

- Automation scripts are optional helpers. Normal manual development with `python`, `pytest`, `make`, Docker, and `gh` must continue to work without them.
- Local automation may run lightweight checks and, when authorized, GPU smoke or evaluation commands. It must not merge to `main`.
- `gh auth login` is required before scripts can post PR comments. If `gh` is missing, unauthenticated, or network-restricted, scripts should skip posting with a clear reason.
- Codex app sandbox approvals are controlled by the app session. Repository scripts can document required commands, but they cannot grant automatic sandbox-outside execution by themselves.

## Completion Reports

For non-trivial work, final reports and PR bodies should include:

- Issue or PR link.
- Summary of changed files and intent.
- Commands run, pass/fail status, and log paths.
- Validation skipped and why.
- Any changes to filters, thresholds, seeds, dataset selection, metrics, or evaluation behavior.
- Remaining risks and any human decisions still required.
