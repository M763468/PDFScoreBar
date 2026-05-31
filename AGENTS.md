# AGENTS.md

Repository-specific guidance for Codex, ChatGPT, Gemini, and human-assisted local work.

## Operating Principles

- Keep changes inside the assigned issue scope. If investigation discovers extra work, report it separately.
- Prefer existing code, Makefile targets, scripts, configs, and documentation before adding new structure.
- Use a topic branch and open a pull request linked to the issue. Do not merge to `main` automatically.
- Do not perform destructive git, filesystem, dataset, model, or log operations without explicit user approval.
- Dependency, CI, Docker, build configuration, release policy, and branch policy changes must be explicitly in scope.
- Do not add, remove, or upgrade dependencies unless the issue explicitly asks for it.

## Runtime Authority

- The authoritative runtime is the user's local WSL/Linux environment with the project GPU setup.
- Cloud containers, web-based GitHub edits, and static reviews are useful for inspection and lightweight checks, but they are not final validation for GPU, Docker, dataset, or full pipeline behavior.
- Read `docs/ENVIRONMENTS.md`, `docs/MANIFEST.md`, `docs/LOG_MANAGEMENT.md`, and `docs/dev/VALIDATION_POLICY.md` before running environment-sensitive commands.
- The current primary pipeline environment is the unified Docker image/container `pdfscore_pipeline_gpu` with Python at `/opt/venv_pipeline/bin/python`.

## Validation Expectations

- Follow `docs/dev/VALIDATION_POLICY.md`; it is the validation contract for both manual and automated local work.
- Match validation weight to the change. Docs-only, comments-only, and small type or formatting updates do not require GPU smoke or full evaluation.
- Use lightweight checks first, such as `make test-fast`, targeted pytest commands, `bash -n` for shell scripts, or static review of docs.
- Use `make verify-pipeline-smoke` or `make verify-gpu-smoke` when a change can affect pipeline execution, Docker/GPU behavior, model loading, dataset access, or evaluation flow.
- Full evaluation is not mandatory for every PR, but evaluation-sensitive changes require full evaluation artifacts or an explicit human skip/defer decision.
- Local full evaluation may be started automatically when user, issue, or PR context has already authorized it.
- If GPU, Docker, dataset, model, or sandbox constraints prevent validation, report the skipped command and exact reason rather than treating it as a successful check.

## Scope and Sensitive Changes

- Do not implement outside the assigned issue's goal, scope, or acceptance criteria. Suggest unrelated improvements in an issue or comment instead.
- If the instruction is only investigation or root-cause analysis, present findings before making code changes.
- Evaluation-sensitive areas include filter logic, thresholds, seeds, dataset selection, metric calculation, evaluation configs, baseline/canonical artifacts, detector routing, and generated evaluation outputs.
- If those areas must change, keep the diff minimal and report the reason, affected files, reproduction command, target commit, and log path.
- When updating experimental values or accuracy/performance claims, include the command, commit hash, environment, input config/data, and log path needed to reproduce the result.
- Keep large datasets, caches, generated logs, and model artifacts out of git. Use symlinks or environment variables for local-only data.

## Testing and Quality Gates

- Add or update tests when behavior changes. For docs-only or workflow-only changes, document why code tests are not applicable.
- Run the minimum validation required by `docs/dev/VALIDATION_POLICY.md` before opening or updating a PR.
- For shell scripts and Makefile changes, run `bash -n` on touched scripts, `make help`, and the relevant script `--help` or metadata-only command.
- For Python behavior changes, run targeted tests and `make test-fast` when applicable.
- For pipeline, detector, Docker/GPU, model-loading, evaluation config, metric, threshold, seed, dataset-selection, baseline, or canonical-artifact changes, report whether GPU smoke and full evaluation were run, skipped, or deferred and why.

## Worktree and Local Data

- Use a dedicated git worktree for issue work when the main clone may contain unrelated work.
- Do not edit another issue's active working tree. Use the original clone only as a worktree manager when requested.
- For local-only assets, prefer `scripts/setup_local_worktree_links.sh` and document the source paths through environment variables instead of committing machine-specific paths.
- Keep worktree run outputs isolated under ignored log/artifact paths unless a tracked doc update is intentionally part of the PR.

## Automation Boundaries

- Automation scripts are optional helpers. Normal manual development with `python`, `pytest`, `make`, Docker, and `gh` must continue to work without them.
- Automation must not weaken validation. It should make required validation, skipped validation, scope-sensitive changes, and remaining risks more visible.
- Local automation may run lightweight checks and, when authorized, GPU smoke or evaluation commands. It must not merge to `main`.
- `gh auth login` is required before scripts can post PR comments. If `gh` is missing, unauthenticated, or network-restricted, scripts should skip posting with a clear reason.
- Codex app sandbox approvals are controlled by the app session. Repository scripts can document required commands, but they cannot grant automatic sandbox-outside execution by themselves.

## Completion Reports

For non-trivial work, final reports and PR bodies should include:

- Issue or PR link.
- Summary of changed files and intent.
- Commands run, pass/fail status, and log paths.
- Validation skipped, failed, or deferred and the exact reason.
- Detected validation categories from `docs/dev/VALIDATION_POLICY.md`.
- Any changes to filters, thresholds, seeds, dataset selection, metrics, evaluation configs, baseline/canonical artifacts, or evaluation behavior.
- Remaining risks and any human decisions still required.
